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
    InputStreamOptions,
)


class MediaSession:
    """Reads current playback from the Windows media overlay (no auth)."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._manager = None
        self._thumb_cache: dict[str, bytes | None] = {}  # track_key → bytes

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

    async def _read_thumbnail(self, info) -> bytes | None:
        """Read the album art thumbnail from the media session."""
        try:
            thumb_ref = info.thumbnail
            if thumb_ref is None:
                return None
            stream = await thumb_ref.open_read_async()
            size = stream.size
            if size == 0 or size > 10_000_000:  # sanity check
                return None
            reader = DataReader(stream.get_input_stream_at(0))
            await reader.load_async(size)
            buf = bytearray(size)
            reader.read_bytes(buf)
            return bytes(buf)
        except Exception as e:
            print(f"[MediaSession] Thumbnail read failed: {e}")
            return None

    async def _get_playback(self) -> dict | None:
        manager = await self._ensure_manager()
        sessions = list(manager.get_sessions())
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

        if len(playing_sessions) > 1:
            unique_apps = list(dict.fromkeys(playing_apps))
            return {
                "conflict": True,
                "playing_apps": unique_apps,
            }

        session = manager.get_current_session()
        if not session and len(playing_sessions) == 1:
            session = playing_sessions[0]
        if not session:
            return None

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

        # Raw position from the API (only updates on play/pause/seek)
        raw_pos_ms = int(timeline.position.total_seconds() * 1000)
        duration_ms = int(timeline.end_time.total_seconds() * 1000)
        is_playing = (
            playback_info.playback_status == PlaybackStatus.PLAYING
        )

        # Interpolate actual position using the last-updated timestamp
        # This eliminates the "stale position" delay
        progress_ms = raw_pos_ms
        try:
            last_updated = timeline.last_updated_time
            if last_updated and is_playing:
                now = datetime.now(timezone.utc)
                # winrt DateTime → Python datetime conversion
                if hasattr(last_updated, 'timestamp'):
                    elapsed_s = now.timestamp() - last_updated.timestamp()
                else:
                    elapsed_s = 0
                if 0 < elapsed_s < 300:  # sanity: within 5 minutes
                    progress_ms = raw_pos_ms + int(elapsed_s * 1000)
                    progress_ms = min(progress_ms, duration_ms)
        except Exception:
            pass  # fall back to raw position

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

    # ── media control internals ───────────────────────────────────
    async def _send_control(self, action: str) -> None:
        manager = await self._ensure_manager()
        session = manager.get_current_session()
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

    # ── public (sync) API ────────────────────────────────────────
    def get_current_playback(self) -> dict | None:
        """
        Return a dict with current media info, or None if nothing is playing.
        """
        try:
            return self._loop.run_until_complete(self._get_playback())
        except Exception as e:
            print(f"[MediaSession] Error: {e}")
            return None

    def play_pause(self) -> None:
        """Toggle play/pause on the current media session."""
        try:
            self._loop.run_until_complete(self._send_control("play_pause"))
        except Exception as e:
            print(f"[MediaSession] play_pause error: {e}")

    def skip_next(self) -> None:
        """Skip to next track."""
        try:
            self._loop.run_until_complete(self._send_control("next"))
        except Exception as e:
            print(f"[MediaSession] skip_next error: {e}")

    def skip_previous(self) -> None:
        """Skip to previous track."""
        try:
            self._loop.run_until_complete(self._send_control("previous"))
        except Exception as e:
            print(f"[MediaSession] skip_previous error: {e}")

    def fetch_thumbnail(self, track_key: str, callback) -> None:
        """
        Fetch album art in a background thread. Calls callback(track_key, bytes|None)
        on completion. Safe to call from the Qt main thread.
        """
        if track_key in self._thumb_cache:
            callback(track_key, self._thumb_cache[track_key])
            return

        def _worker():
            loop = asyncio.new_event_loop()
            try:
                manager = loop.run_until_complete(MediaManager.request_async())
                session = manager.get_current_session()
                if not session:
                    callback(track_key, None)
                    return
                info = loop.run_until_complete(
                    session.try_get_media_properties_async()
                )
                result = loop.run_until_complete(self._read_thumbnail(info))
                self._thumb_cache[track_key] = result
                # Keep cache bounded
                if len(self._thumb_cache) > 20:
                    oldest = next(iter(self._thumb_cache))
                    del self._thumb_cache[oldest]
                callback(track_key, result)
            except Exception as e:
                print(f"[MediaSession] Thumbnail thread error: {e}")
                callback(track_key, None)
            finally:
                loop.close()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
