"""
Tests for the lyrics fetcher.
"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from utils.lyrics import LyricsFetcher


class _FakeResponse:
    """Minimal fake for aiohttp.ClientResponse."""

    def __init__(self, status: int = 200, data=None):
        self.status = status
        self._data = data

    async def json(self, content_type=None):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeSession:
    """Minimal fake for aiohttp.ClientSession.get."""

    def __init__(self, responses=None):
        # responses is a list of _FakeResponse; consumed in order
        self._responses = list(responses) if responses else []
        self._call_index = 0

    def get(self, url, **kwargs):
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp
        return _FakeResponse(status=500)


class TestLyricsFetcherLrclib(unittest.IsolatedAsyncioTestCase):
    async def test_returns_lyrics_from_lrclib(self):
        data = [
            {
                "trackName": "Test Song",
                "artistName": "Test Artist",
                "albumName": "Test Album",
                "duration": 200,
                "plainLyrics": "Hello world\nSecond line",
                "syncedLyrics": "[00:00] Hello world",
                "instrumental": False,
            }
        ]
        session = _FakeSession([_FakeResponse(200, data)])
        fetcher = LyricsFetcher(session)
        result = await fetcher.search("Test Song")

        self.assertIsNotNone(result)
        self.assertEqual(result["track"], "Test Song")
        self.assertEqual(result["artist"], "Test Artist")
        self.assertEqual(result["lyrics"], "Hello world\nSecond line")
        self.assertFalse(result["instrumental"])
        self.assertEqual(result["source"], "LRCLIB")

    async def test_instrumental_returned_only_when_no_lyrics(self):
        """Instrumental should only be returned when no non-instrumental results exist."""
        data = [
            {
                "trackName": "Inst Track",
                "artistName": "Artist",
                "albumName": "Album",
                "duration": 100,
                "plainLyrics": None,
                "instrumental": True,
            }
        ]
        session = _FakeSession([_FakeResponse(200, data)])
        fetcher = LyricsFetcher(session)
        result = await fetcher.search("Inst Track")

        self.assertIsNotNone(result)
        self.assertTrue(result["instrumental"])
        self.assertIsNone(result["lyrics"])

    async def test_instrumental_skipped_when_lyrics_exist(self):
        """If both instrumental and lyrical results exist, prefer lyrics."""
        data = [
            {
                "trackName": "Track Inst",
                "artistName": "A",
                "albumName": "",
                "duration": 100,
                "plainLyrics": None,
                "instrumental": True,
            },
            {
                "trackName": "Track Lyrics",
                "artistName": "A",
                "albumName": "",
                "duration": 100,
                "plainLyrics": "Actual lyrics here",
                "instrumental": False,
            },
        ]
        session = _FakeSession([_FakeResponse(200, data)])
        fetcher = LyricsFetcher(session)
        result = await fetcher.search("Track")

        self.assertIsNotNone(result)
        self.assertFalse(result["instrumental"])
        self.assertEqual(result["lyrics"], "Actual lyrics here")

    async def test_lrclib_404_returns_none(self):
        session = _FakeSession([_FakeResponse(404)])
        fetcher = LyricsFetcher(session)
        result = await fetcher._search_lrclib("unknown")
        self.assertIsNone(result)

    async def test_lrclib_empty_list(self):
        session = _FakeSession([_FakeResponse(200, [])])
        fetcher = LyricsFetcher(session)
        result = await fetcher._search_lrclib("empty")
        self.assertIsNone(result)

    async def test_entries_with_empty_lyrics_skipped(self):
        data = [
            {
                "trackName": "T",
                "artistName": "A",
                "plainLyrics": "   ",
                "instrumental": False,
            }
        ]
        session = _FakeSession([_FakeResponse(200, data)])
        fetcher = LyricsFetcher(session)
        result = await fetcher._search_lrclib("T")
        self.assertIsNone(result)


class TestLyricsFetcherOvh(unittest.IsolatedAsyncioTestCase):
    async def test_returns_lyrics_from_ovh(self):
        data = {"lyrics": "Line one\nLine two"}
        session = _FakeSession([_FakeResponse(200, data)])
        fetcher = LyricsFetcher(session)
        result = await fetcher._search_lyrics_ovh("Artist", "Title")

        self.assertIsNotNone(result)
        self.assertEqual(result["lyrics"], "Line one\nLine two")
        self.assertEqual(result["source"], "lyrics.ovh")

    async def test_missing_artist_returns_none(self):
        session = _FakeSession([])
        fetcher = LyricsFetcher(session)
        result = await fetcher._search_lyrics_ovh("", "Title")
        self.assertIsNone(result)

    async def test_missing_title_returns_none(self):
        session = _FakeSession([])
        fetcher = LyricsFetcher(session)
        result = await fetcher._search_lyrics_ovh("Artist", "")
        self.assertIsNone(result)

    async def test_ovh_404_returns_none(self):
        session = _FakeSession([_FakeResponse(404)])
        fetcher = LyricsFetcher(session)
        result = await fetcher._search_lyrics_ovh("X", "Y")
        self.assertIsNone(result)

    async def test_empty_lyrics_returns_none(self):
        data = {"lyrics": ""}
        session = _FakeSession([_FakeResponse(200, data)])
        fetcher = LyricsFetcher(session)
        result = await fetcher._search_lyrics_ovh("A", "B")
        self.assertIsNone(result)

    async def test_url_encodes_artist_and_title(self):
        """Special characters in artist/title should be URL-encoded."""
        data = {"lyrics": "Encoded lyrics"}
        session = _FakeSession([_FakeResponse(200, data)])
        # Track the URL called
        called_urls = []
        original_get = session.get

        def tracking_get(url, **kwargs):
            called_urls.append(url)
            return original_get(url, **kwargs)

        session.get = tracking_get
        fetcher = LyricsFetcher(session)
        result = await fetcher._search_lyrics_ovh("AC/DC", "Back In Black")

        self.assertIsNotNone(result)
        # Verify the URL was encoded (no raw slashes in artist name)
        self.assertEqual(len(called_urls), 1)
        self.assertIn("AC%2FDC", called_urls[0])
        self.assertIn("Back%20In%20Black", called_urls[0])


class TestLyricsFetcherSearch(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_to_ovh_with_explicit_artist_title(self):
        """If LRCLIB returns nothing, try lyrics.ovh with artist+title."""
        lrclib_resp = _FakeResponse(200, [])
        ovh_resp = _FakeResponse(200, {"lyrics": "Fallback lyrics"})
        session = _FakeSession([lrclib_resp, ovh_resp])
        fetcher = LyricsFetcher(session)
        result = await fetcher.search("query", artist="A", title="B")

        self.assertIsNotNone(result)
        self.assertEqual(result["lyrics"], "Fallback lyrics")
        self.assertEqual(result["source"], "lyrics.ovh")

    async def test_fallback_to_ovh_with_dash_split(self):
        """If query contains ' - ', try splitting for lyrics.ovh."""
        lrclib_resp = _FakeResponse(200, [])
        ovh_resp = _FakeResponse(200, {"lyrics": "Split lyrics"})
        session = _FakeSession([lrclib_resp, ovh_resp])
        fetcher = LyricsFetcher(session)
        result = await fetcher.search("Artist - Title")

        self.assertIsNotNone(result)
        self.assertEqual(result["lyrics"], "Split lyrics")

    async def test_returns_none_when_all_fail(self):
        lrclib_resp = _FakeResponse(200, [])
        session = _FakeSession([lrclib_resp])
        fetcher = LyricsFetcher(session)
        result = await fetcher.search("nothing here")
        self.assertIsNone(result)


class TestLyricsFetcherGetForSong(unittest.IsolatedAsyncioTestCase):
    async def test_delegates_to_search(self):
        data = [
            {
                "trackName": "Song",
                "artistName": "Artist",
                "albumName": "",
                "duration": 0,
                "plainLyrics": "Lyrics text",
                "instrumental": False,
            }
        ]
        session = _FakeSession([_FakeResponse(200, data)])
        fetcher = LyricsFetcher(session)
        result = await fetcher.get_for_song("Artist", "Song")

        self.assertIsNotNone(result)
        self.assertEqual(result["lyrics"], "Lyrics text")


if __name__ == "__main__":
    unittest.main()
