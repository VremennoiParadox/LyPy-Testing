"""
Lyrics from LRCLIB only (https://lrclib.net) — synced LRC when available.

LRCLIB is used as the single source: large community database with timed and
plain lyrics. All highlighting/sync is driven by LRCLIB timestamps when present.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from lyrics_providers import LRCLIB_PROVIDER, is_synced_lyrics


class LyricsFetcher:
    """LRCLIB exact match, then LRCLIB search. Prefers synced LRC over plain."""

    _MISS_TTL_S = 120.0
    _MISS_TTL_NETWORK_S = 45.0

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config if config is not None else {}
        self._cache: dict[str, dict] = {}
        self._miss_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def set_config(self, config: dict[str, Any]) -> None:
        self._config = config

    def _cache_key(
        self,
        track_name: str,
        artist: str,
        album: str = "",
        duration_s: int = 0,
    ) -> str:
        album_norm = (album or "").lower().strip()
        bucket = duration_s // 5 if duration_s > 0 else 0
        return (
            f"lrclib|{artist}|{track_name}|{album_norm}|{bucket}".lower().strip()
        )

    def _is_miss_cached(self, key: str) -> bool:
        until = self._miss_until.get(key)
        if until is None:
            return False
        if time.monotonic() < until:
            return True
        del self._miss_until[key]
        return False

    def _remember_miss(self, key: str, *, network_heavy: bool = False) -> None:
        ttl = self._MISS_TTL_NETWORK_S if network_heavy else self._MISS_TTL_S
        self._miss_until[key] = time.monotonic() + ttl

    @staticmethod
    def _has_lines(got: dict | None) -> bool:
        return bool(got and got.get("lines"))

    @staticmethod
    def _pick_best(candidates: list[dict | None]) -> dict | None:
        best_plain: dict | None = None
        for got in candidates:
            if not got or not got.get("lines"):
                continue
            if is_synced_lyrics(got):
                return got
            if best_plain is None:
                best_plain = got
        return best_plain

    def _fetch_lrclib(
        self,
        track_name: str,
        artist: str,
        album: str,
        duration_s: int,
    ) -> tuple[dict | None, bool]:
        """Returns (lyrics, had_network_error)."""
        cfg = self._config
        network_error = False

        try:
            exact, net_err = LRCLIB_PROVIDER.fetch_exact(
                track_name, artist, album, duration_s, cfg
            )
        except Exception as e:
            print(f"[LyricsFetcher] lrclib exact: {e}")
            exact, net_err = None, True

        if net_err:
            network_error = True

        if is_synced_lyrics(exact):
            return exact, network_error

        search: dict | None = None
        try:
            search = LRCLIB_PROVIDER.fetch_search(
                track_name, artist, album, duration_s, cfg
            )
        except Exception as e:
            print(f"[LyricsFetcher] lrclib search: {e}")

        return self._pick_best([exact, search]), network_error

    def get_lyrics(
        self,
        track_name: str,
        artist: str,
        album: str = "",
        duration_s: int = 0,
    ) -> dict | None:
        """
        Returns {"synced": bool, "lines": [...]}.
        Empty lines means no lyrics found (still a dict, not None).
        """
        key = self._cache_key(track_name, artist, album, duration_s)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            if self._is_miss_cached(key):
                return {"synced": False, "lines": []}

        result, network_error = self._fetch_lrclib(
            track_name, artist, album, duration_s
        )

        with self._lock:
            if not self._has_lines(result):
                self._remember_miss(key, network_heavy=network_error)
                return {"synced": False, "lines": []}

            self._cache[key] = result
            return result

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._miss_until.clear()
