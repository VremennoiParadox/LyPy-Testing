"""
Configuration management for Spotify Lyrics overlay.
Stores and loads user settings from a JSON file.
"""

import json
import os
import sys

APP_NAME = "LyPy"
LEGACY_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
CONFIG_DIR = os.path.join(
    os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.path.expanduser("~"),
    APP_NAME,
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts")


def resource_path(*segments: str) -> str:
    """Resolve bundled files for normal runs and PyInstaller one-file builds."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *segments)


def scripts_dir() -> str:
    """Bundled scripts (e.g. install_spotify_hook.ps1 = user logon task, not a Spotify hook)."""
    if getattr(sys, "frozen", False):
        return resource_path("scripts")
    return SCRIPTS_DIR


DEFAULT_CONFIG = {
    # ── Window settings ──
    "window_width": 500,
    "window_height": 700,
    "window_opacity": 1.0,
    "always_on_top": True,
    "frameless": True,
    "start_hidden": False,
    "start_at_login": False,
    # While LyPy is running: show/raise when Spotify is the active WMTC session.
    # Does NOT start LyPy from quit; does NOT run when Spotify.exe merely exists idle.
    "auto_show_on_spotify": True,
    # While LyPy is running: raise when Spotify.exe process starts (cold Spotify launch).
    # Does NOT launch LyPy if the app is fully closed. Pair with start_at_login + start_hidden
    # for tray-until-Spotify behaviour (see README "Spotify startup").
    "raise_on_spotify_process_start": False,

    # Lyrics: LRCLIB only (see lyrics_fetcher.py).

    # "Report a bug" opens this URL (set your tracker when you publish the repo).
    "bug_report_url": "https://github.com",

    # ── Appearance (Spotify-matched) ──
    "font_size": 32,
    # Resolved at runtime to Spotify Mix/Circular when installed, else bundled Nunito.
    "font_family": "__spotify_auto__",
    "font_profile_version": 4,
    "bg_saturation": 80,       # 0-100 slider for background color saturation
    "line_spacing": 3,         # 0-10 gap between lyric lines

    # ── Behaviour ──
    "polling_interval_ms": 50,
    "scroll_animation_ms": 400,

}


def save_config(config: dict) -> None:
    """Persist current config to disk."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def _startup_command() -> str:
    """Return the command that should be registered to auto-start the app."""
    exe_path = sys.executable
    if getattr(sys, "frozen", False):
        return f'"{exe_path}"'

    # Running from source: use the current script path with the Python interpreter
    script_path = os.path.abspath(sys.argv[0])
    return f'"{exe_path}" "{script_path}"'


def set_start_at_login(enabled: bool) -> None:
    """Enable or disable launching the app at Windows login."""
    try:
        import winreg
    except ImportError:
        return

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
    except Exception as exc:
        print(f"[LyPy] Failed to update startup registry: {exc}")


def load_config() -> dict:
    """Load config from disk, falling back to defaults for missing keys."""
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    elif os.path.exists(LEGACY_CONFIG_FILE):
        try:
            with open(LEGACY_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config.update(saved)
            save_config(config)
        except (json.JSONDecodeError, OSError):
            pass
    return config
