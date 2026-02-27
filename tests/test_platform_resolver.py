"""
Tests for the platform URL resolver.
"""

import unittest

from utils.platform_resolver import (
    APPLE_MUSIC_PATTERN,
    APPLE_MUSIC_SONG_PATTERN,
    DEEZER_PATTERN,
    SPOTIFY_PATTERN,
    _resolve_apple_music_album,
    _resolve_apple_music_song,
    is_music_url,
)


# ── URL pattern tests ────────────────────────────────────────────────


class TestSpotifyPattern(unittest.TestCase):
    def test_standard_url(self):
        url = "https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
        m = SPOTIFY_PATTERN.search(url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "6rqhFgbbKwnb9MLmUQDhG6")

    def test_intl_url(self):
        url = "https://open.spotify.com/intl-de/track/6rqhFgbbKwnb9MLmUQDhG6"
        m = SPOTIFY_PATTERN.search(url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "6rqhFgbbKwnb9MLmUQDhG6")

    def test_no_scheme(self):
        url = "open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
        m = SPOTIFY_PATTERN.search(url)
        self.assertIsNotNone(m)

    def test_http_scheme(self):
        url = "http://open.spotify.com/track/abc123"
        m = SPOTIFY_PATTERN.search(url)
        self.assertIsNotNone(m)

    def test_non_track_url_no_match(self):
        url = "https://open.spotify.com/album/abc123"
        m = SPOTIFY_PATTERN.search(url)
        self.assertIsNone(m)

    def test_unrelated_url_no_match(self):
        self.assertIsNone(SPOTIFY_PATTERN.search("https://google.com"))


class TestDeezerPattern(unittest.TestCase):
    def test_standard_url(self):
        url = "https://www.deezer.com/en/track/12345678"
        m = DEEZER_PATTERN.search(url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "12345678")

    def test_no_www(self):
        url = "https://deezer.com/track/12345678"
        m = DEEZER_PATTERN.search(url)
        self.assertIsNotNone(m)

    def test_different_lang(self):
        url = "https://www.deezer.com/fr/track/99999"
        m = DEEZER_PATTERN.search(url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "99999")

    def test_album_url_no_match(self):
        url = "https://www.deezer.com/en/album/12345"
        m = DEEZER_PATTERN.search(url)
        self.assertIsNone(m)


class TestAppleMusicPattern(unittest.TestCase):
    def test_album_with_track(self):
        url = "https://music.apple.com/us/album/song-name/1234567890?i=9876543210"
        m = APPLE_MUSIC_PATTERN.search(url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "us")
        self.assertEqual(m.group(2), "song-name")
        self.assertEqual(m.group(3), "1234567890")
        self.assertEqual(m.group(4), "9876543210")

    def test_album_without_track(self):
        url = "https://music.apple.com/gb/album/album-name/1234567890"
        m = APPLE_MUSIC_PATTERN.search(url)
        self.assertIsNotNone(m)
        self.assertIsNone(m.group(4))

    def test_song_direct_link(self):
        url = "https://music.apple.com/us/song/cool-song/1234567890"
        m = APPLE_MUSIC_SONG_PATTERN.search(url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "us")
        self.assertEqual(m.group(2), "cool-song")
        self.assertEqual(m.group(3), "1234567890")


# ── is_music_url tests ───────────────────────────────────────────────


class TestIsMusicUrl(unittest.TestCase):
    def test_spotify(self):
        self.assertTrue(is_music_url("https://open.spotify.com/track/abc123"))

    def test_deezer(self):
        self.assertTrue(is_music_url("https://deezer.com/en/track/12345"))

    def test_apple_album(self):
        self.assertTrue(
            is_music_url("https://music.apple.com/us/album/test/123?i=456")
        )

    def test_apple_song(self):
        self.assertTrue(
            is_music_url("https://music.apple.com/us/song/test/123")
        )

    def test_plain_text_not_url(self):
        self.assertFalse(is_music_url("hello world"))

    def test_other_url(self):
        self.assertFalse(is_music_url("https://youtube.com/watch?v=abc"))

    def test_whitespace_stripped(self):
        self.assertTrue(
            is_music_url("  https://open.spotify.com/track/abc123  ")
        )


# ── Apple Music resolution tests ─────────────────────────────────────


class TestResolveAppleMusicAlbum(unittest.TestCase):
    def test_converts_hyphens_to_spaces(self):
        url = "https://music.apple.com/us/album/my-cool-song/123?i=456"
        m = APPLE_MUSIC_PATTERN.search(url)
        result = _resolve_apple_music_album(m)
        self.assertEqual(result, "my cool song")

    def test_url_decoding(self):
        url = "https://music.apple.com/us/album/hello%20world/123"
        m = APPLE_MUSIC_PATTERN.search(url)
        result = _resolve_apple_music_album(m)
        self.assertEqual(result, "hello world")


class TestResolveAppleMusicSong(unittest.TestCase):
    def test_converts_hyphens_to_spaces(self):
        url = "https://music.apple.com/us/song/another-great-track/789"
        m = APPLE_MUSIC_SONG_PATTERN.search(url)
        result = _resolve_apple_music_song(m)
        self.assertEqual(result, "another great track")

    def test_url_decoding(self):
        url = "https://music.apple.com/us/song/hello%20world/123"
        m = APPLE_MUSIC_SONG_PATTERN.search(url)
        result = _resolve_apple_music_song(m)
        self.assertEqual(result, "hello world")


# ── Async resolution tests (Spotify & Deezer) ────────────────────────


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
    """Minimal fake for aiohttp.ClientSession."""

    def __init__(self, response):
        self._response = response

    def get(self, url, **kwargs):
        return self._response


class TestResolveSpotifyAsync(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_title(self):
        from utils.platform_resolver import _resolve_spotify

        resp = _FakeResponse(200, {"title": "Song Name by Artist"})
        session = _FakeSession(resp)
        result = await _resolve_spotify(
            "https://open.spotify.com/track/abc123", session
        )
        self.assertEqual(result, "Song Name by Artist")

    async def test_returns_none_on_failure(self):
        from utils.platform_resolver import _resolve_spotify

        resp = _FakeResponse(500)
        session = _FakeSession(resp)
        result = await _resolve_spotify(
            "https://open.spotify.com/track/abc123", session
        )
        self.assertIsNone(result)

    async def test_returns_none_on_empty_title(self):
        from utils.platform_resolver import _resolve_spotify

        resp = _FakeResponse(200, {"title": ""})
        session = _FakeSession(resp)
        result = await _resolve_spotify(
            "https://open.spotify.com/track/abc123", session
        )
        self.assertIsNone(result)


class TestResolveDeezerAsync(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_title_and_artist(self):
        from utils.platform_resolver import _resolve_deezer

        data = {"title": "Cool Song", "artist": {"name": "Cool Artist"}}
        resp = _FakeResponse(200, data)
        session = _FakeSession(resp)
        result = await _resolve_deezer("123", session)
        self.assertEqual(result, "Cool Song Cool Artist")

    async def test_returns_title_only_when_no_artist(self):
        from utils.platform_resolver import _resolve_deezer

        data = {"title": "Solo", "artist": {}}
        resp = _FakeResponse(200, data)
        session = _FakeSession(resp)
        result = await _resolve_deezer("123", session)
        self.assertEqual(result, "Solo")

    async def test_returns_none_on_failure(self):
        from utils.platform_resolver import _resolve_deezer

        resp = _FakeResponse(404)
        session = _FakeSession(resp)
        result = await _resolve_deezer("123", session)
        self.assertIsNone(result)


class TestResolveUrlAsync(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_spotify_url(self):
        from utils.platform_resolver import resolve_url

        resp = _FakeResponse(200, {"title": "Test by Artist"})
        session = _FakeSession(resp)
        result = await resolve_url(
            "https://open.spotify.com/track/abc123", session
        )
        self.assertEqual(result, "Test by Artist")

    async def test_resolves_apple_music_url(self):
        from utils.platform_resolver import resolve_url

        session = _FakeSession(_FakeResponse(200))
        result = await resolve_url(
            "https://music.apple.com/us/song/my-track/123", session
        )
        self.assertEqual(result, "my track")

    async def test_returns_none_for_unknown_url(self):
        from utils.platform_resolver import resolve_url

        session = _FakeSession(_FakeResponse(200))
        result = await resolve_url("https://youtube.com/watch?v=abc", session)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
