"""
Media session reader using the Windows Media Transport Controls API.
Zero login / zero credentials — reads whatever is playing on the system
(Spotify, browser, any media app) straight from Windows.
"""

import asyncio
import threading
from datetime import datetime, timezone
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winrt.windows.storage.streams import (
    DataReader,
)


class MediaSession:
    """Reads current playback from the Windows media overlay (no auth)."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, name="media-async", daemon=True)
        self._manager = None
        self._display_session = None
        self._thumb_cache: dict[str, bytes | None] = {}
        self._thumb_lock = threading.Lock()
        self._thumb_waiters: dict[str, list[tuple[int, object]]] = {}
        self._thread.start()
        if not self._ready.wait(timeout=10.0):
            raise RuntimeError("[MediaSession] Media asyncio loop failed to start")

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def _submit(self, coro, timeout: float = 15.0):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    @staticmethod
    def _app_display_name(app_id: str) -> str:
        app = (app_id or "").lower()
        if "spotify" in app:
            return "Spotify"
        if "youtube" in app or "ytmusic" in app:
            return "YouTube Music"
        if "applemusic" in app or "apple music" in app or "itunes" in app:
            return "Apple Music"
        if "amazon music" in app or "amazonmusic" in app or "amzn" in app:
            return "Amazon Music"
        if "tidal" in app:
            return "Tidal"
        if "deezer" in app:
            return "Deezer"
        if "yandex" in app or "yandexmusic" in app:
            return "Yandex Music"
        if "msedge" in app:
            return "Microsoft Edge"
        if "chrome" in app:
            return "Google Chrome"
        if "firefox" in app:
            return "Mozilla Firefox"
        return app_id or "Unknown"

    # ── async internals ──────────────────────────────────────────
    async def _ensure_manager(self):
        if self._manager is None:
            self._manager = await MediaManager.request_async()
        return self._manager

    def _collect_playing_sessions(self, sessions) -> tuple[list, list[str]]:
        playing_sessions = []
        playing_apps = []
        for s in sessions:
            try:
                pb_info = s.get_playback_info()
                if pb_info.playback_status == PlaybackStatus.PLAYING:
                    playing_sessions.append(s)
                    app_id = s.source_app_user_model_id
                    playing_apps.append(self._app_display_name(app_id))
            except Exception:
                continue
        return playing_sessions, playing_apps

    def _resolve_display_session(self, manager, sessions):
        """Pick the same session used for on-screen metadata (not a stale current)."""
        playing_sessions, playing_apps = self._collect_playing_sessions(sessions)
        if len(playing_sessions) > 1:
            unique_apps = list(dict.fromkeys(playing_apps))
            return None, {"conflict": True, "playing_apps": unique_apps}

        session = manager.get_current_session()
        if not session and len(playing_sessions) == 1:
            session = playing_sessions[0]
        return session, None

    async def _read_thumbnail(self, info) -> bytes | None:
        """Read the album art thumbnail from the media session."""
        stream = None
        try:
            thumb_ref = info.thumbnail
            if thumb_ref is None:
                return None
            stream = await thumb_ref.open_read_async()
            size = stream.size
            if size == 0 or size > 10_000_000:
                return None
            reader = DataReader(stream.get_input_stream_at(0))
            await reader.load_async(size)
            buf = bytearray(size)
            reader.read_bytes(buf)
            return bytes(buf)
        except Exception as e:
            print(f"[MediaSession] Thumbnail read failed: {e}")
            return None
        finally:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    async def _get_playback(self) -> dict | None:
        manager = await self._ensure_manager()
        sessions = list(manager.get_sessions())
        session, conflict = self._resolve_display_session(manager, sessions)
        if conflict:
            self._display_session = None
            return conflict
        if not session:
            self._display_session = None
            return None

        self._display_session = session

        try:
            info = await session.try_get_media_properties_async()
        except Exception:
            return None

        timeline = session.get_timeline_properties()
        playback_info = session.get_playback_info()

        title = info.title or ""
        artist = info.artist or ""
        source_app = self._app_display_name(session.source_app_user_model_id)

        if not title:
            return None

        track_key = f"{artist} — {title}".strip()

        raw_pos_ms = int(timeline.position.total_seconds() * 1000)
        duration_ms = int(timeline.end_time.total_seconds() * 1000)
        is_playing = playback_info.playback_status == PlaybackStatus.PLAYING

        progress_ms = raw_pos_ms
        try:
            last_updated = timeline.last_updated_time
            if last_updated and is_playing:
                now = datetime.now(timezone.utc)
                if hasattr(last_updated, "timestamp"):
                    elapsed_s = now.timestamp() - last_updated.timestamp()
                else:
                    elapsed_s = 0
                if 0 < elapsed_s < 300:
                    progress_ms = raw_pos_ms + int(elapsed_s * 1000)
                    progress_ms = min(progress_ms, duration_ms)
        except Exception:
            pass

        return {
            "conflict": False,
            "track_key": track_key,
            "track_name": title,
            "artist": artist,
            "album": info.album_title or "",
            "duration_ms": duration_ms,
            "progress_ms": progress_ms,
            "is_playing": is_playing,
            "source_app": source_app,
        }

    async def _send_control(self, action: str) -> None:
        session = self._display_session
        if session is None:
            manager = await self._ensure_manager()
            sessions = list(manager.get_sessions())
            session, _ = self._resolve_display_session(manager, sessions)
        if not session:
            return
        try:
            if action == "play_pause":
                await session.try_toggle_play_pause_async()
            elif action == "next":
                await session.try_skip_next_async()
            elif action == "previous":
                await session.try_skip_previous_async()
        except Exception as e:
            print(f"[MediaSession] Control '{action}' failed: {e}")

    async def _fetch_thumbnail_for_display(self) -> bytes | None:
        session = self._display_session
        if session is None:
            manager = await self._ensure_manager()
            sessions = list(manager.get_sessions())
            session, _ = self._resolve_display_session(manager, sessions)
        if not session:
            return None
        try:
            info = await session.try_get_media_properties_async()
        except Exception:
            return None
        return await self._read_thumbnail(info)

    def _trim_thumb_cache(self) -> None:
        while len(self._thumb_cache) > 20:
            oldest = next(iter(self._thumb_cache))
            del self._thumb_cache[oldest]

    def _dispatch_thumbnail_waiters(self, track_key: str, data: bytes | None) -> None:
        with self._thumb_lock:
            self._thumb_cache[track_key] = data
            self._trim_thumb_cache()
            waiters = self._thumb_waiters.pop(track_key, [])
        for generation, callback in waiters:
            try:
                callback(track_key, generation, data)
            except Exception as e:
                print(f"[MediaSession] Thumbnail callback error: {e}")

    def _thumbnail_done(self, track_key: str, fut) -> None:
        try:
            data = fut.result()
        except Exception as e:
            print(f"[MediaSession] Thumbnail fetch error: {e}")
            data = None
        self._dispatch_thumbnail_waiters(track_key, data)

    # ── public (sync) API ────────────────────────────────────────
    def get_current_playback(self) -> dict | None:
        """Return a dict with current media info, or None if nothing is playing."""
        try:
            return self._submit(self._get_playback())
        except Exception as e:
            print(f"[MediaSession] Error: {e}")
            return None

    def play_pause(self) -> None:
        try:
            self._submit(self._send_control("play_pause"), timeout=5.0)
        except Exception as e:
            print(f"[MediaSession] play_pause error: {e}")

    def skip_next(self) -> None:
        try:
            self._submit(self._send_control("next"), timeout=5.0)
        except Exception as e:
            print(f"[MediaSession] skip_next error: {e}")

    def skip_previous(self) -> None:
        try:
            self._submit(self._send_control("previous"), timeout=5.0)
        except Exception as e:
            print(f"[MediaSession] skip_previous error: {e}")

    def fetch_thumbnail(self, track_key: str, generation: int, callback) -> None:
        """
        Fetch album art on the media asyncio loop. Calls
        callback(track_key, generation, bytes|None) on completion.
        Coalesces concurrent requests for the same track_key.
        """
        with self._thumb_lock:
            if track_key in self._thumb_cache:
                callback(track_key, generation, self._thumb_cache[track_key])
                return
            waiters = self._thumb_waiters.setdefault(track_key, [])
            waiters.append((generation, callback))
            if len(waiters) > 1:
                return

        fut = asyncio.run_coroutine_threadsafe(
            self._fetch_thumbnail_for_display(), self._loop
        )
        fut.add_done_callback(lambda f, tk=track_key: self._thumbnail_done(tk, f))
