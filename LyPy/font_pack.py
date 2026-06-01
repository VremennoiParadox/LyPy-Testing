"""
Download and install the LyPy lyrics font pack (OFL-licensed Nunito Sans).

Spotify Mix is proprietary and cannot be bundled. On first run we fetch Nunito Sans
Bold + Regular from Fontsource CDN (same family used as the Spotify-like fallback).
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

from config import CONFIG_DIR, resource_path

FONT_PACK_VERSION = 1

# Fontsource / Google Fonts OFL — latin TTF files.
_PACK_FILES: tuple[tuple[str, str], ...] = (
    (
        "NunitoSans-Bold.ttf",
        "https://cdn.jsdelivr.net/fontsource/fonts/nunito-sans@5.2.5/latin-700-normal.ttf",
    ),
    (
        "NunitoSans-Regular.ttf",
        "https://cdn.jsdelivr.net/fontsource/fonts/nunito-sans@5.2.5/latin-400-normal.ttf",
    ),
)


def _pack_dirs() -> list[str]:
    dirs = [os.path.join(CONFIG_DIR, "fonts")]
    bundled = resource_path("assets", "fonts")
    if bundled not in dirs:
        dirs.append(bundled)
    return dirs


def _pack_marker_path() -> str:
    return os.path.join(CONFIG_DIR, "fonts", f".font_pack_v{FONT_PACK_VERSION}")


def _download(url: str, dest: str) -> bool:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LyPy/2.0 (font-pack)"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if len(data) < 1000:
            return False
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        print(f"[LyPy] Font download failed ({os.path.basename(dest)}): {e}")
        return False


def ensure_font_pack(*, force: bool = False) -> bool:
    """
    Ensure Nunito Sans Bold/Regular exist under %LOCALAPPDATA%\\LyPy\\fonts\\
    (and bundled assets/fonts when writable). Returns True if Bold is present.
    """
    primary_dir = os.path.join(CONFIG_DIR, "fonts")
    os.makedirs(primary_dir, exist_ok=True)

    marker = _pack_marker_path()
    bold_name = _PACK_FILES[0][0]
    bold_path = os.path.join(primary_dir, bold_name)

    if not force and os.path.isfile(bold_path) and os.path.isfile(marker):
        return True

    ok = True
    for filename, url in _PACK_FILES:
        dest = os.path.join(primary_dir, filename)
        if not force and os.path.isfile(dest) and os.path.getsize(dest) > 1000:
            continue
        if not _download(url, dest):
            ok = False

    # Mirror into bundled assets when developing (optional).
    bundled_dir = resource_path("assets", "fonts")
    try:
        os.makedirs(bundled_dir, exist_ok=True)
        for filename, _url in _PACK_FILES:
            src = os.path.join(primary_dir, filename)
            if os.path.isfile(src):
                dst = os.path.join(bundled_dir, filename)
                if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src):
                    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                        fdst.write(fsrc.read())
    except OSError:
        pass

    if ok and os.path.isfile(bold_path):
        try:
            with open(marker, "w", encoding="utf-8") as f:
                f.write("ok\n")
        except OSError:
            pass
        return True

    return os.path.isfile(bold_path) and os.path.getsize(bold_path) > 1000
