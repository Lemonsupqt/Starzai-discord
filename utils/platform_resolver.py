"""
Platform URL resolver for Spotify, Deezer, and Apple Music links.

Extracts song metadata from platform URLs and converts them to
search queries usable by the music API.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import quote, unquote

import aiohttp

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15  # seconds

# ── URL patterns ──────────────────────────────────────────────────────
SPOTIFY_PATTERN = re.compile(
    r"(?:https?://)?open\.spotify\.com/(?:intl-\w+/)?track/([a-zA-Z0-9]+)"
)
DEEZER_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?deezer\.com/(?:\w+/)?track/(\d+)"
)
APPLE_MUSIC_PATTERN = re.compile(
    r"(?:https?://)?music\.apple\.com/(\w+)/album/([^/]+)/(\d+)(?:\?i=(\d+))?"
)
# Also match direct song links
APPLE_MUSIC_SONG_PATTERN = re.compile(
    r"(?:https?://)?music\.apple\.com/(\w+)/song/([^/]+)/(\d+)"
)


def is_music_url(text: str) -> bool:
    """Check if the given text contains a recognized music platform URL."""
    text = text.strip()
    return bool(
        SPOTIFY_PATTERN.search(text)
        or DEEZER_PATTERN.search(text)
        or APPLE_MUSIC_PATTERN.search(text)
        or APPLE_MUSIC_SONG_PATTERN.search(text)
    )


async def resolve_url(url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Resolve a music platform URL to a search query string.

    Supports:
    - Spotify track URLs (via oEmbed)
    - Deezer track URLs (via Deezer public API)
    - Apple Music URLs (extracted from URL path)

    Returns
    -------
    Optional[str]
        A search query string, or None if resolution fails.
    """
    url = url.strip()

    # ── Spotify ───────────────────────────────────────────────────
    match = SPOTIFY_PATTERN.search(url)
    if match:
        return await _resolve_spotify(url, session)

    # ── Deezer ────────────────────────────────────────────────────
    match = DEEZER_PATTERN.search(url)
    if match:
        return await _resolve_deezer(url, match.group(1), session)

    # ── Apple Music (album link with ?i= track param) ─────────────
    match = APPLE_MUSIC_PATTERN.search(url)
    if match:
        return _resolve_apple_music_album(match)

    # ── Apple Music (direct song link) ────────────────────────────
    match = APPLE_MUSIC_SONG_PATTERN.search(url)
    if match:
        return _resolve_apple_music_song(match)

    return None


async def _resolve_spotify(url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """Resolve a Spotify track URL via the oEmbed endpoint."""
    try:
        encoded_url = quote(url, safe="")
        oembed_url = f"https://open.spotify.com/oembed?url={encoded_url}"
        async with session.get(
            oembed_url,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                logger.warning("Spotify oEmbed returned %d", resp.status)
                return None

            data = await resp.json(content_type=None)
            title = data.get("title", "")
            if title:
                # oEmbed title is usually "Song Name by Artist Name"
                # Clean it up for search
                logger.info("Resolved Spotify URL to: %s", title)
                return title

    except Exception as exc:
        logger.warning("Spotify URL resolution failed: %s", exc)

    return None


async def _resolve_deezer(
    url: str, track_id: str, session: aiohttp.ClientSession
) -> Optional[str]:
    """Resolve a Deezer track URL via their public API."""
    try:
        api_url = f"https://api.deezer.com/track/{track_id}"
        async with session.get(
            api_url,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                logger.warning("Deezer API returned %d", resp.status)
                return None

            data = await resp.json(content_type=None)
            title = data.get("title", "")
            artist_obj = data.get("artist", {})
            artist_name = artist_obj.get("name", "") if isinstance(artist_obj, dict) else ""

            if title and artist_name:
                query = f"{title} {artist_name}"
                logger.info("Resolved Deezer URL to: %s", query)
                return query
            elif title:
                return title

    except Exception as exc:
        logger.warning("Deezer URL resolution failed: %s", exc)

    return None


def _resolve_apple_music_album(match: re.Match) -> Optional[str]:
    """Extract search query from an Apple Music album URL with track param."""
    # match groups: (lang, album-slug, album-id, track-id?)
    album_slug = match.group(2)
    if album_slug:
        # Convert hyphens to spaces and decode URL encoding
        query = unquote(album_slug).replace("-", " ")
        logger.info("Resolved Apple Music URL to: %s", query)
        return query
    return None


def _resolve_apple_music_song(match: re.Match) -> Optional[str]:
    """Extract search query from an Apple Music song URL."""
    # match groups: (lang, song-slug, song-id)
    song_slug = match.group(2)
    if song_slug:
        query = unquote(song_slug).replace("-", " ")
        logger.info("Resolved Apple Music song URL to: %s", query)
        return query
    return None
