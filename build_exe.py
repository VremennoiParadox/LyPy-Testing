"""Build LyPy as a single Windows executable (PyInstaller onefile)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY_SCRIPT = ROOT / "LyPy" / "main.py"
ASSET_DIR = ROOT / "LyPy" / "assets"
BUNDLED_FONT_BOLD = ASSET_DIR / "fonts" / "NunitoSans-Bold.ttf"
BUNDLED_FONT_LEGACY = ASSET_DIR / "fonts" / "Nunito-Variable.ttf"
SCRIPTS_DIR = ROOT / "scripts"
DIST_DIR = ROOT / "dist"
WORK_DIR = ROOT / "build"

_REQUIRED_ICONS = (
    "app_icon.png",
    "btn_play.png",
    "btn_pause.png",
    "btn_settings.png",
)


def _die(message: str, *, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _data_argument(src: Path, dest: str) -> str:
    sep = ";" if os.name == "nt" else ":"
    return f"{src}{sep}{dest}"


def preflight() -> None:
    """Verify repo layout before invoking PyInstaller."""
    if not ENTRY_SCRIPT.is_file():
        _die(
            f"Entry script not found: {ENTRY_SCRIPT}\n"
            "Run this script from the repository root (same folder as build_exe.py)."
        )

    if not ASSET_DIR.is_dir():
        _die(
            f"Missing assets folder: {ASSET_DIR}\n"
            "Generate UI assets first:\n"
            "  cd LyPy\n"
            "  py -3 generate_icons.py\n"
            "Or from repo root:  py -3 scripts/build_windows.ps1"
        )

    missing_icons = [
        name for name in _REQUIRED_ICONS if not (ASSET_DIR / name).is_file()
    ]
    if missing_icons:
        _die(
            f"Missing icon(s) in {ASSET_DIR}: {', '.join(missing_icons)}\n"
            "Regenerate assets:\n"
            "  cd LyPy && py -3 generate_icons.py"
        )

    if not BUNDLED_FONT_BOLD.is_file() and not BUNDLED_FONT_LEGACY.is_file():
        try:
            sys.path.insert(0, str(ROOT / "LyPy"))
            from font_pack import ensure_font_pack

            ensure_font_pack(force=True)
        except Exception as exc:
            _die(
                f"Missing lyrics font pack under {ASSET_DIR / 'fonts'}\n"
                f"Auto-download failed: {exc}\n"
                "Run once with internet:  py -3 LyPy/main.py\n"
                "Or:  py -3 -c \"from font_pack import ensure_font_pack; ensure_font_pack(force=True)\""
            )
        if not BUNDLED_FONT_BOLD.is_file() and not BUNDLED_FONT_LEGACY.is_file():
            _die(
                f"Missing lyrics font: {BUNDLED_FONT_BOLD}\n"
                "Run LyPy once online or place NunitoSans-Bold.ttf in LyPy/assets/fonts/."
            )

    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        _die(
            "PyInstaller is not installed.\n"
            "Install build dependencies from the repo root:\n"
            "  py -3 -m pip install -r requirements-dev.txt"
        )


def main() -> None:
    preflight()

    from PyInstaller.__main__ import run as pyinstaller_run

    print("Running PyInstaller (onefile, windowed). Expect ~80-150 MB dist/LyPy.exe with PyQt5.")
    locked = DIST_DIR / "LyPy.exe"
    if locked.is_file():
        try:
            locked.unlink()
        except OSError as exc:
            _die(
                f"Cannot overwrite {locked}: {exc}\n"
                "Close any running LyPy.exe (or tray instance) and rebuild."
            )
    print(f"  Entry:  {ENTRY_SCRIPT}")
    print(f"  Output: {DIST_DIR / 'LyPy.exe'}")

    pyinstaller_run([
        str(ENTRY_SCRIPT),
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "LyPy",
        "--distpath", str(DIST_DIR),
        "--workpath", str(WORK_DIR),
        "--add-data", _data_argument(ASSET_DIR, "assets"),
        "--add-data", _data_argument(SCRIPTS_DIR, "scripts"),
        "--collect-all", "PyQt5",
        "--collect-all", "winrt",
        "--hidden-import", "lyrics_providers",
        "--hidden-import", "font_pack",
        "--hidden-import", "spotify_font",
        "--hidden-import", "album_color",
    ])

    exe = DIST_DIR / "LyPy.exe"
    if not exe.is_file():
        _die(
            f"PyInstaller finished but {exe} was not created.\n"
            "Check build/LyPy/warn-LyPy.txt for missing modules."
        )
    size_mb = exe.stat().st_size / (1024 * 1024)
    print(f"Built {exe} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
