"""
Fetches time-synced lyrics from LRCLIB.net — a free, open-source API.
No login, no API key, no cookies required.
"""

import re
import requests


class LyricsFetcher:
    """Fetches synced lyrics from LRCLIB.net (free, no auth)."""

    API_URL = "https://lrclib.net/api/get"
    SEARCH_URL = "https://lrclib.net/api/search"

    HEADERS = {
        "User-Agent": "SpotifyLyricsOverlay/1.0 (https://github.com)",
    }

    def __init__(self):
        self._cache: dict[str, dict] = {}

    # ── LRC timestamp parser ─────────────────────────────────────
    @staticmethod
    def _parse_lrc(lrc_text: str) -> list[dict]:
        """
        Parse LRC-formatted lyrics into a list of {time_ms, words}.

        LRC format:  [mm:ss.xx] Lyric text
        """
        lines = []
        pattern = re.compile(r"\[(\d{2}):(\d{2})\.(\d{2,3})\]\s*(.*)")
        for raw in lrc_text.strip().splitlines():
            m = pattern.match(raw.strip())
            if m:
                mins, secs, frac, words = m.groups()
                # Normalise fractional part to milliseconds
                if len(frac) == 2:
                    ms = int(frac) * 10
                else:
                    ms = int(frac)
                time_ms = int(mins) * 60_000 + int(secs) * 1000 + ms
                lines.append({"time_ms": time_ms, "words": words})
        return lines

    # ── public API ───────────────────────────────────────────────
    def get_lyrics(self, track_name: str, artist: str,
                   album: str = "", duration_s: int = 0) -> dict | None:
        """
        Fetch lyrics for the given track.

        Returns:
            {"synced": bool, "lines": [{"time_ms": int, "words": str}, ...]}
            or None on error.
        """
        cache_key = f"{artist}|{track_name}".lower().strip()
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._try_exact(track_name, artist, album, duration_s)
        if not result:
            result = self._try_search(track_name, artist)
        if not result:
            result = {"synced": False, "lines": []}

        self._cache[cache_key] = result
        return result

    # ── internal helpers ─────────────────────────────────────────
    def _try_exact(self, track: str, artist: str,
                   album: str, duration_s: int) -> dict | None:
        """Try the exact-match LRCLIB endpoint."""
        try:
            params: dict = {
                "track_name": track,
                "artist_name": artist,
            }
            if album:
                params["album_name"] = album
            if duration_s > 0:
                params["duration"] = duration_s

            resp = requests.get(
                self.API_URL,
                headers=self.HEADERS,
                params=params,
                timeout=8,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return self._parse_response(resp.json())
        except Exception as e:
            print(f"[LyricsFetcher] Exact lookup failed: {e}")
            return None

    def _try_search(self, track: str, artist: str) -> dict | None:
        """Fallback: search LRCLIB and pick the best match."""
        try:
            resp = requests.get(
                self.SEARCH_URL,
                headers=self.HEADERS,
                params={"q": f"{artist} {track}"},
                timeout=8,
            )
            resp.raise_for_status()
            results = resp.json()

            if not results:
                return None

            # Prefer results with synced lyrics
            for r in results:
                if r.get("syncedLyrics"):
                    return self._parse_response(r)
            # Fall back to first result with plain lyrics
            for r in results:
                if r.get("plainLyrics"):
                    return self._parse_response(r)
            return None
        except Exception as e:
            print(f"[LyricsFetcher] Search failed: {e}")
            return None

    def _parse_response(self, data: dict) -> dict | None:
        """Parse an LRCLIB response object into our standard format."""
        synced_lrc = data.get("syncedLyrics")
        if synced_lrc:
            lines = self._parse_lrc(synced_lrc)
            if lines:
                return {"synced": True, "lines": lines}

        # Fall back to plain (unsynced) lyrics
        plain = data.get("plainLyrics", "")
        if plain:
            lines = [
                {"time_ms": 0, "words": line}
                for line in plain.strip().splitlines()
                if line.strip()
            ]
            return {"synced": False, "lines": lines}

        return None

    def clear_cache(self) -> None:
        self._cache.clear()
