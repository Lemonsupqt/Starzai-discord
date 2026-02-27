"""
Music API wrapper with multi-endpoint fallback.

Searches and retrieves songs from multiple JioSaavn API mirrors,
normalizing the response format across different endpoint variants.
All user-facing references use "Powered by StarzAI" branding.
"""

from __future__ import annotations

import asyncio
import html
import logging
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ── Internal API endpoints (NEVER expose to users) ──────────────────
MUSIC_APIS: List[str] = [
    "https://jiosaavn-api2.vercel.app",
    "https://jiosaavn-api-privatecvc2.vercel.app",
    "https://saavn.dev/api",
    "https://jiosaavn-api.vercel.app",
]

API_TIMEOUT = 30  # seconds per endpoint

QUALITY_TIERS: List[str] = ["12kbps", "48kbps", "96kbps", "160kbps", "320kbps"]

# Qualities we offer for download (user-facing)
DOWNLOAD_QUALITIES: List[str] = ["96kbps", "160kbps", "320kbps"]


def _safe_unescape(text: Any) -> str:
    """HTML-unescape a value, returning empty string for non-strings."""
    if not text:
        return ""
    if not isinstance(text, str):
        return str(text)
    return html.unescape(text)


def _extract_url(entry: Dict[str, Any]) -> str:
    """Extract URL from a download/image entry that may use 'url' or 'link' key."""
    return entry.get("url") or entry.get("link") or ""


def _extract_artist(song: Dict[str, Any]) -> str:
    """Extract artist string from either response format."""
    # Format A: primaryArtists is a plain string
    if isinstance(song.get("primaryArtists"), str) and song["primaryArtists"]:
        return _safe_unescape(song["primaryArtists"])

    # Format A: primaryArtists could also be a list
    if isinstance(song.get("primaryArtists"), list):
        names = [a.get("name", "") for a in song["primaryArtists"] if isinstance(a, dict)]
        if names:
            return _safe_unescape(", ".join(n for n in names if n))

    # Format B: artists.primary is an array of objects
    artists_obj = song.get("artists")
    if isinstance(artists_obj, dict):
        primary = artists_obj.get("primary")
        if isinstance(primary, list) and primary:
            names = [a.get("name", "") for a in primary if isinstance(a, dict)]
            joined = ", ".join(n for n in names if n)
            if joined:
                return _safe_unescape(joined)

    # Fallback: try 'artist' key or featured artists
    if song.get("artist"):
        return _safe_unescape(song["artist"])

    return "Unknown"


def _extract_image(song: Dict[str, Any]) -> str:
    """Extract the best quality image URL (prefer 500x500)."""
    images = song.get("image")
    if not images or not isinstance(images, list):
        return ""

    # Try to find 500x500
    for img in images:
        if isinstance(img, dict) and img.get("quality") == "500x500":
            return _extract_url(img)

    # Fall back to the last (highest quality) entry
    if images and isinstance(images[-1], dict):
        return _extract_url(images[-1])

    return ""


def _extract_download_urls(song: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract and normalise the download URL array."""
    raw = song.get("downloadUrl") or song.get("download_url") or []
    if not isinstance(raw, list):
        return []

    result: List[Dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        quality = entry.get("quality", "")
        url = _extract_url(entry)
        if quality and url:
            result.append({"quality": quality, "url": url})
    return result


def _pick_best_url(download_urls: List[Dict[str, str]], preferred: str = "320kbps") -> str:
    """Pick the best available download URL by quality preference."""
    if not download_urls:
        return ""

    # Preference cascade
    preference_order = [preferred]
    # Build fallback chain
    if preferred in QUALITY_TIERS:
        idx = QUALITY_TIERS.index(preferred)
        # Add lower qualities as fallback
        for i in range(idx - 1, -1, -1):
            preference_order.append(QUALITY_TIERS[i])

    url_map = {d["quality"]: d["url"] for d in download_urls}

    for q in preference_order:
        if q in url_map:
            return url_map[q]

    # Absolute fallback: highest available
    for q in reversed(QUALITY_TIERS):
        if q in url_map:
            return url_map[q]

    # Last resort: last entry
    return download_urls[-1]["url"] if download_urls else ""


def _get_url_for_quality(download_urls: List[Dict[str, str]], quality: str) -> str:
    """Get URL for a specific quality tier, with fallback."""
    url_map = {d["quality"]: d["url"] for d in download_urls}
    if quality in url_map:
        return url_map[quality]
    return _pick_best_url(download_urls, quality)


def _format_duration(seconds: Any) -> str:
    """Convert seconds to M:SS format."""
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "0:00"
    minutes = total // 60
    secs = total % 60
    return f"{minutes}:{secs:02d}"


def normalize_song(song: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a single song object from any endpoint format."""
    download_urls = _extract_download_urls(song)
    album_obj = song.get("album")
    album_name = ""
    if isinstance(album_obj, dict):
        album_name = album_obj.get("name", "")
    elif isinstance(album_obj, str):
        album_name = album_obj

    duration_raw = song.get("duration", 0)
    try:
        duration_sec = int(duration_raw)
    except (TypeError, ValueError):
        duration_sec = 0

    return {
        "id": song.get("id", ""),
        "name": _safe_unescape(song.get("name", "Unknown")),
        "artist": _extract_artist(song),
        "album": _safe_unescape(album_name),
        "year": str(song["year"]) if song.get("year") is not None else "",
        "duration": duration_sec,
        "duration_formatted": _format_duration(duration_sec),
        "language": song.get("language", ""),
        "has_lyrics": bool(song.get("hasLyrics")),
        "image": _extract_image(song),
        "download_urls": download_urls,
        "best_url": _pick_best_url(download_urls),
    }


def normalize_songs(songs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise a list of song objects."""
    return [normalize_song(s) for s in songs if isinstance(s, dict)]


class MusicAPI:
    """Async wrapper around multiple JioSaavn API endpoints with automatic fallback."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    # ── Search ────────────────────────────────────────────────────────

    async def search(self, query: str, limit: int = 7) -> Optional[List[Dict[str, Any]]]:
        """
        Search for songs across all API endpoints with automatic fallback.

        Returns a normalised list of song dicts, or None if every endpoint fails.
        """
        for api_base in MUSIC_APIS:
            try:
                url = f"{api_base}/search/songs"
                async with self._session.get(
                    url,
                    params={"query": query, "limit": limit},
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("Music API %s returned status %d", api_base, resp.status)
                        continue

                    data = await resp.json(content_type=None)

                    # Handle nested data structures
                    results = None
                    if isinstance(data, dict):
                        # Try data.data.results (double-wrapped)
                        inner = data.get("data")
                        if isinstance(inner, dict):
                            results = inner.get("results")
                            # Some endpoints wrap again
                            if results is None:
                                inner2 = inner.get("data")
                                if isinstance(inner2, dict):
                                    results = inner2.get("results")
                        # Try data.results directly
                        if results is None:
                            results = data.get("results")

                    if results and isinstance(results, list):
                        normalised = normalize_songs(results)
                        if normalised:
                            logger.info(
                                "Music search '%s' returned %d results from %s",
                                query, len(normalised), api_base,
                            )
                            return normalised

            except asyncio.TimeoutError:
                logger.warning("Music API %s timed out for query '%s'", api_base, query)
            except Exception as exc:
                logger.warning("Music API %s error for query '%s': %s", api_base, query, exc)

        logger.error("All music APIs failed for query: %s", query)
        return None

    # ── Get song by ID ────────────────────────────────────────────────

    async def get_song_by_id(self, song_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single song by ID (fallback when search results lack download URLs).

        Returns a normalised song dict, or None if every endpoint fails.
        """
        for api_base in MUSIC_APIS:
            try:
                url = f"{api_base}/songs/{song_id}"
                async with self._session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                ) as resp:
                    if resp.status != 200:
                        continue

                    data = await resp.json(content_type=None)

                    song_data = None
                    if isinstance(data, dict):
                        inner = data.get("data")
                        if isinstance(inner, list) and inner:
                            song_data = inner[0]
                        elif isinstance(inner, dict):
                            # Could be the song itself or another wrapper
                            if inner.get("id"):
                                song_data = inner
                            else:
                                results = inner.get("results") or inner.get("data")
                                if isinstance(results, list) and results:
                                    song_data = results[0]
                                elif isinstance(results, dict) and results.get("id"):
                                    song_data = results
                        elif data.get("id"):
                            song_data = data

                    if song_data and isinstance(song_data, dict):
                        normalised = normalize_song(song_data)
                        if normalised.get("id"):
                            logger.info("Fetched song %s from %s", song_id, api_base)
                            return normalised

            except asyncio.TimeoutError:
                logger.warning("Music API %s timed out for song ID '%s'", api_base, song_id)
            except Exception as exc:
                logger.warning("Music API %s error for song ID '%s': %s", api_base, song_id, exc)

        logger.error("All music APIs failed for song ID: %s", song_id)
        return None

    # ── Ensure download URLs ──────────────────────────────────────────

    async def ensure_download_urls(self, song: Dict[str, Any]) -> Dict[str, Any]:
        """
        If a song object is missing download URLs, fetch them via get_song_by_id.
        Returns the (potentially updated) song dict.
        """
        if song.get("download_urls") and song.get("best_url"):
            return song

        song_id = song.get("id")
        if not song_id:
            return song

        logger.info("Song '%s' missing download URLs, fetching by ID", song.get("name", ""))
        full_song = await self.get_song_by_id(song_id)
        if full_song and full_song.get("download_urls"):
            song["download_urls"] = full_song["download_urls"]
            song["best_url"] = full_song["best_url"]

        return song


__all__ = [
    "MusicAPI",
    "MUSIC_APIS",
    "QUALITY_TIERS",
    "DOWNLOAD_QUALITIES",
    "normalize_song",
    "normalize_songs",
    "_pick_best_url",
    "_get_url_for_quality",
    "_format_duration",
]
