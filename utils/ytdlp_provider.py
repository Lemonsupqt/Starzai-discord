"""
yt-dlp based music provider — YouTube & SoundCloud fallback.

Provides async search and stream-URL extraction for songs that
JioSaavn doesn't carry.  Uses ``yt_dlp`` as a library (no subprocess)
and runs blocking calls in a thread-pool executor so the event loop
stays responsive.

Supported search prefixes:
    • ``ytsearch:<query>``  — YouTube
    • ``scsearch:<query>``  — SoundCloud

All results are normalised into the same dict shape that
``music_api.normalize_song`` returns so the rest of the codebase
doesn't need to know which provider served the track.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── yt-dlp options ─────────────────────────────────────────────────────
# Shared across all calls.  ``extract_flat`` is *not* used because we
# need the full info dict (with direct audio URL) for playback.
_BASE_OPTS: Dict[str, Any] = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",        # bind to ipv4
    "socket_timeout": 15,
    "extract_flat": False,
    # Don't download the file — we only want the info dict + direct URL
    "skip_download": True,
}

# Lighter options used when we only need metadata (no audio URL).
_FLAT_OPTS: Dict[str, Any] = {
    **_BASE_OPTS,
    "extract_flat": "in_playlist",
}

QUALITY_MAP = {
    "320kbps": 320,
    "160kbps": 160,
    "96kbps": 96,
    "48kbps": 48,
}


# =====================================================================
#  Normalisation helpers
# =====================================================================

def _extract_audio_url(info: Dict[str, Any]) -> str:
    """Pick the best audio-only URL from *info*, falling back to ``url``."""
    # yt-dlp populates 'url' with the selected format's URL
    url = info.get("url", "")

    # If requested_formats is present (e.g. merged video+audio), prefer
    # the audio-only stream.
    for fmt in info.get("requested_formats", []):
        if fmt.get("acodec") != "none" and fmt.get("vcodec") in ("none", None):
            return fmt.get("url", url)

    return url


def normalize_ytdlp_result(
    info: Dict[str, Any],
    source: str = "youtube",
) -> Dict[str, Any]:
    """Map a yt-dlp *info_dict* to the app's normalised song format.

    The returned dict is **identical** in shape to what
    ``music_api.normalize_song`` produces so downstream code
    (playback, queue, embeds, download) works without changes.
    """
    title = info.get("track") or info.get("title") or "Unknown"
    artist = (
        info.get("artist")
        or info.get("uploader")
        or info.get("channel")
        or "Unknown"
    )
    album = info.get("album") or ""
    duration = int(info.get("duration") or 0)

    # Thumbnail — prefer the highest-res available
    thumbnail = info.get("thumbnail") or ""
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        # yt-dlp usually lists them ascending; take the last
        thumbnail = thumbnails[-1].get("url", thumbnail)

    audio_url = _extract_audio_url(info)
    abr = int(info.get("abr") or 0)

    # Build a download_urls list compatible with _pick_best_url()
    download_urls: List[Dict[str, str]] = []
    if audio_url:
        quality_label = f"{abr}kbps" if abr else "320kbps"
        download_urls.append({"quality": quality_label, "url": audio_url})

    # Permanent page URL for re-extraction when stream URLs expire
    webpage_url = info.get("webpage_url") or info.get("original_url") or ""

    return {
        "id": info.get("id") or "",
        "name": title,
        "artist": artist,
        "album": album,
        "year": str(info.get("release_year") or ""),
        "duration": duration,
        "duration_formatted": f"{duration // 60}:{duration % 60:02d}" if duration else "0:00",
        "language": "",
        "has_lyrics": False,
        "image": thumbnail,
        "download_urls": download_urls,
        "best_url": audio_url,
        # ── Extra fields for provider-aware logic ──
        "source": source,            # "youtube" | "soundcloud"
        "webpage_url": webpage_url,   # permanent URL for re-extraction
    }


# =====================================================================
#  Synchronous yt-dlp wrappers (run in executor)
# =====================================================================

def _ytdlp_search_sync(
    query: str,
    *,
    limit: int = 5,
    prefix: str = "ytsearch",
) -> List[Dict[str, Any]]:
    """Blocking: search via yt-dlp and return a list of info dicts."""
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp is not installed — YouTube/SoundCloud fallback unavailable")
        return []

    opts = {
        **_BASE_OPTS,
        "default_search": prefix,
    }

    search_term = f"{prefix}{limit}:{query}"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(search_term, download=False)

            if not result:
                return []

            entries = result.get("entries") or []
            if not entries and result.get("id"):
                # Single result (not a search page)
                entries = [result]

            return [e for e in entries if e]
    except Exception as exc:
        logger.warning("yt-dlp search failed for '%s': %s", query, exc)
        return []


def _ytdlp_extract_url_sync(webpage_url: str) -> Optional[Dict[str, Any]]:
    """Blocking: extract a fresh stream URL from a permanent page URL."""
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp is not installed")
        return None

    try:
        with yt_dlp.YoutubeDL(_BASE_OPTS) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
            return info
    except Exception as exc:
        logger.warning("yt-dlp extract failed for '%s': %s", webpage_url, exc)
        return None


# =====================================================================
#  Async public API
# =====================================================================

async def search_youtube(query: str, *, limit: int = 5) -> List[Dict[str, Any]]:
    """Search YouTube and return normalised song dicts."""
    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(
        None,
        partial(_ytdlp_search_sync, query, limit=limit, prefix="ytsearch"),
    )
    return [normalize_ytdlp_result(r, source="youtube") for r in raw]


async def search_soundcloud(query: str, *, limit: int = 5) -> List[Dict[str, Any]]:
    """Search SoundCloud and return normalised song dicts."""
    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(
        None,
        partial(_ytdlp_search_sync, query, limit=limit, prefix="scsearch"),
    )
    return [normalize_ytdlp_result(r, source="soundcloud") for r in raw]


async def extract_stream_url(webpage_url: str) -> Optional[Dict[str, Any]]:
    """Re-extract a fresh audio stream URL from a permanent page URL.

    Returns a normalised song dict with an updated ``best_url``, or
    ``None`` if extraction fails.
    """
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(
        None,
        partial(_ytdlp_extract_url_sync, webpage_url),
    )
    if not info:
        return None

    source = "soundcloud" if "soundcloud.com" in (webpage_url or "") else "youtube"
    return normalize_ytdlp_result(info, source=source)


async def refresh_song(song: Dict[str, Any]) -> Dict[str, Any]:
    """Given a song dict with ``source`` and ``webpage_url``, refresh
    the stream URL.  Returns the song dict with updated URLs.

    If the song is from JioSaavn (no ``webpage_url``), it is returned
    unchanged.
    """
    webpage_url = song.get("webpage_url")
    if not webpage_url:
        return song  # JioSaavn — URLs don't expire

    refreshed = await extract_stream_url(webpage_url)
    if refreshed and refreshed.get("best_url"):
        song["best_url"] = refreshed["best_url"]
        song["download_urls"] = refreshed["download_urls"]
    return song
