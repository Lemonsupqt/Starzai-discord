"""
Lyrics fetcher with LRCLIB primary and lyrics.ovh fallback.

Returns plain-text lyrics for a given query or artist+title pair.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

LRCLIB_BASE = "https://lrclib.net/api"
LYRICS_OVH_BASE = "https://api.lyrics.ovh/v1"
REQUEST_TIMEOUT = 15  # seconds per request


class LyricsFetcher:
    """Async lyrics fetcher using LRCLIB (primary) and lyrics.ovh (fallback)."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    # ── Primary: LRCLIB ───────────────────────────────────────────────

    async def _search_lrclib(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search LRCLIB for lyrics.

        Returns the first result with plainLyrics, or None.
        """
        try:
            async with self._session.get(
                f"{LRCLIB_BASE}/search",
                params={"q": query},
                headers={"User-Agent": "StarzAI-Discord/1.0"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    logger.warning("LRCLIB returned status %d for query '%s'", resp.status, query)
                    return None

                data: List[Dict[str, Any]] = await resp.json(content_type=None)

                if not isinstance(data, list):
                    return None

                # Two-pass scan: first try to find a result with actual lyrics,
                # then fall back to instrumental if that's all that's available.
                instrumental_fallback: Optional[Dict[str, Any]] = None

                for entry in data:
                    if not isinstance(entry, dict):
                        continue

                    if entry.get("instrumental"):
                        # Remember the first instrumental, but keep looking for lyrics
                        if instrumental_fallback is None:
                            instrumental_fallback = {
                                "track": entry.get("trackName", ""),
                                "artist": entry.get("artistName", ""),
                                "album": entry.get("albumName", ""),
                                "duration": entry.get("duration", 0),
                                "lyrics": None,
                                "synced_lyrics": None,
                                "instrumental": True,
                                "source": "LRCLIB",
                            }
                        continue

                    plain = entry.get("plainLyrics")
                    if plain and plain.strip():
                        return {
                            "track": entry.get("trackName", ""),
                            "artist": entry.get("artistName", ""),
                            "album": entry.get("albumName", ""),
                            "duration": entry.get("duration", 0),
                            "lyrics": plain.strip(),
                            "synced_lyrics": entry.get("syncedLyrics", ""),
                            "instrumental": False,
                            "source": "LRCLIB",
                        }

                # No lyrics found — return the instrumental result if we had one
                if instrumental_fallback is not None:
                    return instrumental_fallback

        except asyncio.TimeoutError:
            logger.warning("LRCLIB timed out for query '%s'", query)
        except Exception as exc:
            logger.warning("LRCLIB error for query '%s': %s", query, exc)

        return None

    # ── Fallback: lyrics.ovh ──────────────────────────────────────────

    async def _search_lyrics_ovh(self, artist: str, title: str) -> Optional[Dict[str, Any]]:
        """
        Fetch lyrics from lyrics.ovh using exact artist + title.

        Returns a lyrics dict or None.
        """
        if not artist or not title:
            return None

        try:
            # URL-encode artist and title via the params mechanism
            url = f"{LYRICS_OVH_BASE}/{artist}/{title}"
            async with self._session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json(content_type=None)
                lyrics_text = data.get("lyrics", "").strip() if isinstance(data, dict) else ""
                if lyrics_text:
                    return {
                        "track": title,
                        "artist": artist,
                        "album": "",
                        "duration": 0,
                        "lyrics": lyrics_text,
                        "synced_lyrics": None,
                        "instrumental": False,
                        "source": "lyrics.ovh",
                    }

        except asyncio.TimeoutError:
            logger.warning("lyrics.ovh timed out for '%s - %s'", artist, title)
        except Exception as exc:
            logger.warning("lyrics.ovh error for '%s - %s': %s", artist, title, exc)

        return None

    # ── Public API ────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        artist: str = "",
        title: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Search for lyrics using LRCLIB (primary) with lyrics.ovh fallback.

        Parameters
        ----------
        query : str
            Free-text search query (used for LRCLIB).
        artist : str
            Artist name (used for lyrics.ovh fallback).
        title : str
            Song title (used for lyrics.ovh fallback).

        Returns
        -------
        Optional[Dict]
            Lyrics result dict with keys: track, artist, album, duration,
            lyrics, synced_lyrics, instrumental, source.
            Returns None if no lyrics found anywhere.
        """
        # Try LRCLIB first
        result = await self._search_lrclib(query)
        if result:
            return result

        # Fallback to lyrics.ovh if we have artist + title
        if artist and title:
            result = await self._search_lyrics_ovh(artist, title)
            if result:
                return result

        # Try to split query into artist - title for lyrics.ovh
        if " - " in query:
            parts = query.split(" - ", 1)
            result = await self._search_lyrics_ovh(parts[0].strip(), parts[1].strip())
            if result:
                return result

        return None

    async def get_for_song(self, artist: str, title: str) -> Optional[Dict[str, Any]]:
        """
        Convenience method: search lyrics for a known artist + title.
        Tries "{artist} {title}" on LRCLIB first, then lyrics.ovh.
        """
        query = f"{artist} {title}".strip()
        return await self.search(query, artist=artist, title=title)
