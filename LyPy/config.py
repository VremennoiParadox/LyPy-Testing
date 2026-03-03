"""
Configuration management for Spotify Lyrics overlay.
Stores and loads user settings from a JSON file.
"""

import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULT_CONFIG = {
    # ── Window settings ──
    "window_width": 500,
    "window_height": 700,
    "window_opacity": 1.0,
    "always_on_top": True,
    "frameless": True,

    # ── Appearance (Spotify-matched) ──
    "font_size": 28,
    "font_family": "Segoe UI, Circular, Helvetica, Arial, sans-serif",
    "bg_saturation": 80,       # 0-100 slider for background color saturation
    "line_spacing": 3,         # 0-10 gap between lyric lines

    # ── Behaviour ──
    "polling_interval_ms": 50,
    "scroll_animation_ms": 400,

}


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
    return config


def save_config(config: dict) -> None:
    """Persist current config to disk."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
