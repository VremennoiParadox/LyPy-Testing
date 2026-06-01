"""
Lyrics typeface: Spotify Mix when user supplies files, else auto-installed Nunito Sans.
"""

from __future__ import annotations

import os
from typing import Iterable

from PyQt5.QtGui import QFont, QFontDatabase

from config import CONFIG_DIR, resource_path
from font_pack import ensure_font_pack

SPOTIFY_MIX_FAMILY = "Spotify Mix"
LYPY_LYRICS_FAMILY = "Nunito Sans"

_FONT_EXTS = (".ttf", ".otf", ".woff", ".woff2")

_PACK_BOLD = "NunitoSans-Bold.ttf"
_PACK_REGULAR = "NunitoSans-Regular.ttf"
_LEGACY_VARIABLE = "Nunito-Variable.ttf"

_resolved_family: str | None = None
_loaded_font_ids: list[int] = []


def _pack_font_paths() -> list[str]:
    paths: list[str] = []
    for directory in (
        os.path.join(CONFIG_DIR, "fonts"),
        resource_path("assets", "fonts"),
    ):
        for name in (_PACK_BOLD, _PACK_REGULAR, _LEGACY_VARIABLE):
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                paths.append(path)
    return paths


def _user_font_dirs() -> list[str]:
    appdata = os.environ.get("APPDATA") or ""
    dirs = [
        os.path.join(CONFIG_DIR, "fonts"),
        resource_path("assets", "fonts"),
    ]
    if appdata:
        dirs.append(os.path.join(appdata, "Spicetify", "Assets", "Fonts"))
    return [d for d in dirs if os.path.isdir(d)]


def _iter_spotify_install_roots() -> Iterable[str]:
    local = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("ProgramFiles", r"C:\Program Files")
    prog86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for root in (
        os.path.join(local, "Spotify"),
        os.path.join(prog, "Spotify"),
        os.path.join(prog86, "Spotify"),
    ):
        if os.path.isdir(root):
            yield root
    packages = os.path.join(local, "Packages")
    if os.path.isdir(packages):
        try:
            for name in os.listdir(packages):
                if "spotify" in name.lower():
                    yield os.path.join(packages, name)
        except OSError:
            pass


def _font_file_priority(path: str) -> tuple[int, str]:
    name = os.path.basename(path).lower()
    score = 0
    if "mix" in name and "spotify" in name:
        score -= 40
    elif "mix" in name:
        score -= 30
    elif "nunitosans" in name and "bold" in name:
        score -= 25
    elif "circular" in name and "spotify" in name:
        score -= 20
    elif "spotify" in name:
        score -= 10
    if any(w in name for w in ("extrabold", "extra-bold", "black", "heavy")):
        score -= 8
    elif "bold" in name:
        score -= 5
    elif "regular" in name or "book" in name:
        score += 2
    return (score, name)


def _collect_spotify_font_files() -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add_from_dir(directory: str, *, limit: int = 32) -> None:
        try:
            for name in os.listdir(directory):
                if len(found) >= limit:
                    return
                low = name.lower()
                if not low.endswith(_FONT_EXTS):
                    continue
                if not any(
                    token in low
                    for token in ("mix", "spotify", "circular", "sans")
                ):
                    continue
                path = os.path.join(directory, name)
                if path not in seen:
                    seen.add(path)
                    found.append(path)
        except OSError:
            pass

    for d in _user_font_dirs():
        add_from_dir(d, limit=24)

    for root in _iter_spotify_install_roots():
        try:
            for dirpath, _dirnames, filenames in os.walk(root):
                if len(found) >= 32:
                    break
                for name in filenames:
                    low = name.lower()
                    if not low.endswith(_FONT_EXTS):
                        continue
                    if not any(
                        t in low for t in ("mix", "spotify", "circular")
                    ):
                        continue
                    path = os.path.join(dirpath, name)
                    if path not in seen:
                        seen.add(path)
                        found.append(path)
        except OSError:
            continue

    found.sort(key=_font_file_priority)
    return found


def _family_names() -> dict[str, str]:
    return {f.lower(): f for f in QFontDatabase().families()}


def _pick_spotify_mix_family() -> str | None:
    families = _family_names()
    if SPOTIFY_MIX_FAMILY.lower() in families:
        return families[SPOTIFY_MIX_FAMILY.lower()]
    for key, display in families.items():
        if "spotify" in key and "mix" in key:
            return display
    return None


def _pick_nunito_sans_family() -> str | None:
    families = _family_names()
    if LYPY_LYRICS_FAMILY.lower() in families:
        return families[LYPY_LYRICS_FAMILY.lower()]
    for key, display in families.items():
        if "nunito" in key and "sans" in key:
            return display
    for key, display in families.items():
        if key.startswith("nunito"):
            return display
    return None


def _load_font_file(path: str) -> str | None:
    fid = QFontDatabase.addApplicationFont(path)
    if fid < 0:
        return None
    _loaded_font_ids.append(fid)
    fams = QFontDatabase.applicationFontFamilies(fid)
    return fams[0] if fams else None


def _load_pack_fonts() -> str | None:
    for path in _pack_font_paths():
        _load_font_file(path)
    return _pick_nunito_sans_family()


def _load_spotify_mix_fonts() -> str | None:
    for path in _collect_spotify_font_files():
        if "nunito" in os.path.basename(path).lower():
            continue
        _load_font_file(path)
    return _pick_spotify_mix_family()


def setup_lyrics_fonts() -> str:
    """
    Download font pack if needed, register fonts, return primary family name.
    Call once after QApplication is created.
    """
    global _resolved_family
    _resolved_family = None

    ensure_font_pack()

    family = _pick_spotify_mix_family()
    if not family:
        family = _load_spotify_mix_fonts()
    if not family:
        family = _load_pack_fonts()
    if not family:
        family = LYPY_LYRICS_FAMILY if _pick_nunito_sans_family() else "Segoe UI"

    _resolved_family = family
    return family


def resolve_lyrics_font_family() -> str:
    if _resolved_family:
        return _resolved_family
    return setup_lyrics_fonts()


def default_font_family_config() -> str:
    primary = resolve_lyrics_font_family()
    if primary.lower() == SPOTIFY_MIX_FAMILY.lower() or (
        "spotify" in primary.lower() and "mix" in primary.lower()
    ):
        quoted = f'"{primary}"'
        return f'{quoted}, "{LYPY_LYRICS_FAMILY}", "Segoe UI", sans-serif'

    quoted = f'"{LYPY_LYRICS_FAMILY}"' if primary == LYPY_LYRICS_FAMILY else (
        f'"{primary}"' if " " in primary else primary
    )
    return f'{quoted}, "Segoe UI", Helvetica, Arial, sans-serif'


def _effective_family(requested: str) -> str:
    resolved = resolve_lyrics_font_family()
    req = requested.strip().strip('"').strip("'")

    if req.lower() == SPOTIFY_MIX_FAMILY.lower():
        mix = _pick_spotify_mix_family()
        if mix:
            return mix
        sans = _pick_nunito_sans_family()
        return sans or resolved

    if "nunito" in req.lower():
        return _pick_nunito_sans_family() or resolved

    families = _family_names()
    if req.lower() in families:
        return families[req.lower()]

    return resolved


def make_lyrics_font(family: str, pixel_size: int, *, bold: bool = True) -> QFont:
    use_family = _effective_family(family)
    font = QFont(use_family)
    font.setPixelSize(max(12, int(pixel_size)))
    if bold:
        font.setWeight(QFont.Bold)
        font.setBold(True)
    else:
        font.setWeight(QFont.Normal)
        font.setBold(False)
    return font


def _mirror_spotify_mix_to_user_fonts_dir() -> None:
    """Copy SpotifyMix*.ttf from bundled assets into %LOCALAPPDATA%\\LyPy\\fonts\\."""
    import shutil

    src_dir = resource_path("assets", "fonts")
    dest_dir = os.path.join(CONFIG_DIR, "fonts")
    os.makedirs(dest_dir, exist_ok=True)
    try:
        for name in os.listdir(src_dir):
            if not name.lower().startswith("spotifymix"):
                continue
            if not name.lower().endswith((".ttf", ".otf")):
                continue
            shutil.copy2(os.path.join(src_dir, name), os.path.join(dest_dir, name))
    except OSError:
        pass


def apply_lyrics_font_to_config(config: dict) -> None:
    _mirror_spotify_mix_to_user_fonts_dir()
    setup_lyrics_fonts()
    version = int(config.get("font_profile_version") or 0)
    current = (config.get("font_family") or "").strip()

    if _pick_spotify_mix_family():
        config["font_family"] = default_font_family_config()
        config["font_profile_version"] = 5
        return

    if version < 4:
        config["font_family"] = default_font_family_config()
        config["font_profile_version"] = 4
        return

    auto_values = {
        "",
        "__spotify_auto__",
        "Segoe UI, Circular, Helvetica, Arial, sans-serif",
    }
    if current in auto_values:
        config["font_family"] = default_font_family_config()
