"""
Pluggable lyric sources. Each returns the same shape as LyricsFetcher:
{"synced": bool, "lines": [{"time_ms": int, "words": str}, ...]} or None.
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import quote

import requests
from requests.exceptions import RequestException

HEADERS = {
    "User-Agent": "LyPy/2.0 (https://github.com; lyrics overlay; +https://lrclib.net)",
}

# LRCLIB can be slow; allow enough time for a response on typical home networks.
_TIMEOUT_EXACT_S = 10.0
_TIMEOUT_SEARCH_S = 12.0
_TIMEOUT_OVH_S = 4.0

_SESSION: requests.Session | None = None


def http_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update(HEADERS)
    return _SESSION


def parse_lrc(lrc_text: str) -> list[dict]:
    """Parse LRC into [{"time_ms", "words"}, ...]. Ignores non-timestamp lines."""
    lines: list[dict] = []
    # Minutes 1–3 digits; seconds 2 digits; fractional: centiseconds (2) or ms (3).
    pattern = re.compile(r"\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]\s*(.*)")
    for raw in lrc_text.strip().splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        # Strip word-level tags like <00:12.34> inside line if present on same line
        m = pattern.match(raw)
        if m:
            mins, secs, frac, words = m.groups()
            if not frac:
                ms = 0
            elif len(frac) == 1:
                ms = int(frac) * 100
            elif len(frac) == 2:
                ms = int(frac) * 10
            else:
                ms = int(frac)
            time_ms = int(mins) * 60_000 + int(secs) * 1000 + ms
            lines.append({"time_ms": time_ms, "words": words})
    return lines


def lyrics_timestamps_usable(lines: list[dict]) -> bool:
    """True if lines look like real LRC (not plain text with time_ms=0 everywhere)."""
    ts = [int(ln.get("time_ms", 0)) for ln in lines]
    if not ts:
        return False
    return max(ts) > 200 or len(set(ts)) > 1


def is_synced_lyrics(lyrics: dict | None) -> bool:
    """True when lyrics can drive line highlighting from timestamps."""
    if not lyrics or not lyrics.get("lines"):
        return False
    return bool(lyrics.get("synced")) and lyrics_timestamps_usable(lyrics["lines"])


def plain_to_lines(text: str) -> list[dict]:
    return [
        {"time_ms": 0, "words": line}
        for line in text.strip().splitlines()
        if line.strip()
    ]


def normalize_query(track: str, artist: str) -> tuple[str, str]:
    t = re.sub(r"\s*\((feat\.|ft\.|featuring)[^)]+\)", "", track, flags=re.I)
    t = re.sub(r"\s*\[.*?\]", "", t).strip()
    a = re.sub(r"\s*\((feat\.|ft\.|featuring)[^)]+\)", "", artist, flags=re.I)
    a = re.sub(r"\s*\[.*?\]", "", a).strip()
    return t, a


class LyricsProvider(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(
        self,
        track_name: str,
        artist: str,
        album: str,
        duration_s: int,
        config: dict[str, Any],
    ) -> dict | None:
        ...


class LrclibProvider(LyricsProvider):
    name = "lrclib"
    API_URL = "https://lrclib.net/api/get"
    SEARCH_URL = "https://lrclib.net/api/search"

    def _parse_lrclib_payload(self, data: dict) -> dict | None:
        synced_lrc = data.get("syncedLyrics")
        if synced_lrc:
            lines = parse_lrc(synced_lrc)
            if lines:
                return {"synced": True, "lines": lines}
        plain = data.get("plainLyrics", "")
        if plain:
            lines = plain_to_lines(plain)
            if lines:
                return {"synced": False, "lines": lines}
        return None

    def _exact_params(
        self,
        track_name: str,
        artist: str,
        album: str,
        duration_s: int,
    ) -> dict:
        params: dict = {
            "track_name": track_name,
            "artist_name": artist,
        }
        if album:
            params["album_name"] = album
        if duration_s > 0:
            params["duration"] = duration_s
        return params

    def fetch_exact(
        self,
        track_name: str,
        artist: str,
        album: str,
        duration_s: int,
        config: dict[str, Any],
    ) -> tuple[dict | None, bool]:
        """
        LRCLIB GET /api/get only.
        Returns (lyrics_or_none, network_error). network_error is True on
        connection failures/timeouts (fetcher may still try search).
        """
        track_name, artist = normalize_query(track_name, artist)
        params = self._exact_params(track_name, artist, album, duration_s)
        last_err: RequestException | None = None
        for attempt in range(2):
            try:
                resp = http_session().get(
                    self.API_URL,
                    params=params,
                    timeout=_TIMEOUT_EXACT_S,
                )
                if resp.status_code == 404:
                    return None, False
                resp.raise_for_status()
                return self._parse_lrclib_payload(resp.json()), False
            except RequestException as e:
                last_err = e
                if attempt == 0:
                    continue
        print(f"[Lyrics:{self.name}] exact: {last_err}")
        return None, True
        except Exception as e:
            print(f"[Lyrics:{self.name}] exact: {e}")
            return None, False

    def fetch_search(
        self,
        track_name: str,
        artist: str,
        album: str,
        duration_s: int,
        config: dict[str, Any],
    ) -> dict | None:
        """LRCLIB GET /api/search (runs after exact + parallel ovh miss)."""
        track_name, artist = normalize_query(track_name, artist)
        try:
            resp = http_session().get(
                self.SEARCH_URL,
                params={"q": f"{artist} {track_name}"},
                timeout=_TIMEOUT_SEARCH_S,
            )
            resp.raise_for_status()
            results = resp.json()
            if not results:
                return None

            def _rank(item: dict) -> tuple[int, int]:
                synced = 1 if item.get("syncedLyrics") else 0
                dur_diff = 9999
                if duration_s > 0 and item.get("duration") is not None:
                    try:
                        dur_diff = abs(int(item["duration"]) - duration_s)
                    except (TypeError, ValueError):
                        dur_diff = 9999
                return (synced, -dur_diff)

            ranked = sorted(results, key=_rank, reverse=True)
            for r in ranked:
                out = self._parse_lrclib_payload(r)
                if out:
                    return out
        except RequestException as e:
            print(f"[Lyrics:{self.name}] search: {e}")
        except Exception as e:
            print(f"[Lyrics:{self.name}] search: {e}")
        return None

    def fetch(
        self,
        track_name: str,
        artist: str,
        album: str,
        duration_s: int,
        config: dict[str, Any],
    ) -> dict | None:
        out, _net_err = self.fetch_exact(
            track_name, artist, album, duration_s, config
        )
        if out:
            return out
        return self.fetch_search(
            track_name, artist, album, duration_s, config
        )


class LyricsOvhProvider(LyricsProvider):
    name = "lyrics_ovh"

    def fetch(
        self,
        track_name: str,
        artist: str,
        album: str,
        duration_s: int,
        config: dict[str, Any],
    ) -> dict | None:
        track_name, artist = normalize_query(track_name, artist)
        if not track_name or not artist:
            return None
        path_artist = quote(artist, safe="")
        path_track = quote(track_name, safe="")
        url = f"https://api.lyrics.ovh/v1/{path_artist}/{path_track}"
        try:
            resp = http_session().get(url, timeout=_TIMEOUT_OVH_S)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            lyrics = data.get("lyrics") or ""
            lines = plain_to_lines(lyrics)
            if lines:
                return {"synced": False, "lines": lines}
        except Exception as e:
            print(f"[Lyrics:{self.name}] {e}")
        return None


class SyncedlyricsCommunityProvider(LyricsProvider):
    """Megalobiz / NetEase style LRC via optional syncedlyrics package."""

    name = "syncedlyrics_community"

    def fetch(
        self,
        track_name: str,
        artist: str,
        album: str,
        duration_s: int,
        config: dict[str, Any],
    ) -> dict | None:
        try:
            import syncedlyrics  # type: ignore
        except ImportError:
            return None

        track_name, artist = normalize_query(track_name, artist)
        q = f"{artist} {track_name}".strip()
        if not q:
            return None
        providers = config.get("syncedlyrics_providers") or [
            "Megalobiz",
            "NetEase",
        ]
        try:
            try:
                lrc = syncedlyrics.search(
                    q,
                    save_path=None,
                    providers=list(providers),
                )
            except TypeError:
                lrc = syncedlyrics.search(q, save_path=None)
            if not lrc or not isinstance(lrc, str):
                return None
            lines = parse_lrc(lrc)
            if lines:
                return {"synced": True, "lines": lines}
            plain = plain_to_lines(lrc)
            if plain:
                return {"synced": False, "lines": plain}
        except Exception as e:
            print(f"[Lyrics:{self.name}] {e}")
        return None


class GeniusProvider(LyricsProvider):
    name = "genius"

    _html_block = re.compile(
        r'<div[^>]*data-lyrics-container="true"[^>]*>(.*?)</div>',
        re.DOTALL | re.IGNORECASE,
    )
    _br = re.compile(r"<br\s*/?>", re.I)

    def fetch(
        self,
        track_name: str,
        artist: str,
        album: str,
        duration_s: int,
        config: dict[str, Any],
    ) -> dict | None:
        token = (config.get("genius_access_token") or "").strip()
        if not token:
            return None
        track_name, artist = normalize_query(track_name, artist)
        q = f"{artist} {track_name}".strip()
        if not q:
            return None
        try:
            r = requests.get(
                "https://api.genius.com/search",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": q},
                timeout=6,
            )
            r.raise_for_status()
            hits = (r.json().get("response") or {}).get("hits") or []
            if not hits:
                return None
            url = (hits[0].get("result") or {}).get("url")
            if not url:
                return None
            page = requests.get(
                url,
                headers={**HEADERS, "Accept-Language": "en,ru;q=0.9"},
                timeout=8,
            )
            page.raise_for_status()
            text = self._extract_lyrics_html(page.text)
            lines = plain_to_lines(text)
            if lines:
                return {"synced": False, "lines": lines}
        except Exception as e:
            print(f"[Lyrics:{self.name}] {e}")
        return None

    def _extract_lyrics_html(self, page_html: str) -> str:
        parts: list[str] = []
        for m in self._html_block.finditer(page_html):
            chunk = m.group(1)
            chunk = re.sub(r"<[^>]+>", "", chunk)
            chunk = self._br.sub("\n", chunk)
            chunk = html.unescape(chunk)
            parts.append(chunk.strip())
        return "\n".join(p for p in parts if p)


class MusixmatchProvider(LyricsProvider):
    name = "musixmatch"

    def fetch(
        self,
        track_name: str,
        artist: str,
        album: str,
        duration_s: int,
        config: dict[str, Any],
    ) -> dict | None:
        key = (config.get("musixmatch_api_key") or "").strip()
        if not key:
            return None
        track_name, artist = normalize_query(track_name, artist)
        try:
            r = requests.get(
                "https://apic.musixmatch.com/ws/1.1/matcher.lyrics.get",
                params={
                    "apikey": key,
                    "q_track": track_name,
                    "q_artist": artist,
                    "f_has_lyrics": 1,
                },
                headers=HEADERS,
                timeout=8,
            )
            r.raise_for_status()
            body = r.json()
            msg = body.get("message", {})
            if msg.get("header", {}).get("status_code") != 200:
                return None
            lyrics = (msg.get("body") or {}).get("lyrics") or {}
            text = lyrics.get("lyrics_body") or ""
            marker = "******* This Lyrics is NOT for Commercial use *******"
            if marker in text:
                text = text.split(marker, 1)[0].strip()
            # Musixmatch returns placeholder for instrumental
            if "instrumental" in text.lower() and len(text) < 80:
                return None
            lines = plain_to_lines(text)
            if lines:
                return {"synced": False, "lines": lines}
        except Exception as e:
            print(f"[Lyrics:{self.name}] {e}")
        return None


# Shared instances: fetcher tries LRCLIB first, then (when extended) this tail only.
LRCLIB_PROVIDER = LrclibProvider()
LYRICS_OVH_PROVIDER = LyricsOvhProvider()
SYNCEDLYRICS_COMMUNITY_PROVIDER = SyncedlyricsCommunityProvider()
GENIUS_PROVIDER = GeniusProvider()
MUSIXMATCH_PROVIDER = MusixmatchProvider()

EXTENDED_TAIL: list[LyricsProvider] = [
    LYRICS_OVH_PROVIDER,
    SYNCEDLYRICS_COMMUNITY_PROVIDER,
    GENIUS_PROVIDER,
    MUSIXMATCH_PROVIDER,
]
