"""
Spotify Lyrics Overlay — Main entry point.
No login, no credentials, no setup needed.
Just run it and play music!
"""

import sys

from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QStyle
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

from config import load_config, set_start_at_login, resource_path
from font_pack import ensure_font_pack
from spotify_client import MediaSession
from lyrics_fetcher import LyricsFetcher
from lyrics_window import LyricsWindow
from spotify_font import setup_lyrics_fonts


def create_tray_icon(app: QApplication, window: LyricsWindow) -> QSystemTrayIcon:
    icon = QIcon(resource_path("assets", "app_icon.png"))
    if icon.isNull():
        icon = app.style().standardIcon(QStyle.SP_ComputerIcon)
    tray_icon = QSystemTrayIcon(icon, app)
    tray_menu = QMenu()

    show_action = tray_menu.addAction("Show Lyrics")
    hide_action = tray_menu.addAction("Hide Lyrics")
    quit_action = tray_menu.addAction("Quit")

    show_action.triggered.connect(lambda: window.showNormal() or window.raise_() or window.activateWindow())
    hide_action.triggered.connect(window.hide)
    quit_action.triggered.connect(app.quit)

    tray_icon.setContextMenu(tray_menu)
    tray_icon.setToolTip("LyPy Lyrics Overlay")
    tray_icon.activated.connect(lambda reason: window.showNormal() or window.raise_() or window.activateWindow() if reason == QSystemTrayIcon.Trigger else None)
    tray_icon.show()
    return tray_icon


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LyPy Lyrics")
    app.setQuitOnLastWindowClosed(False)

    # OFL font pack (Nunito Sans) — first run downloads to %LOCALAPPDATA%\\LyPy\\fonts\\
    ensure_font_pack()
    setup_lyrics_fonts()

    # Dark application style
    app.setStyle("Fusion")
    dark_palette = app.palette()
    dark_palette.setColor(dark_palette.Window, Qt.black)
    dark_palette.setColor(dark_palette.WindowText, Qt.white)
    app.setPalette(dark_palette)

    config = load_config()
    set_start_at_login(config.get("start_at_login", False))

    app_icon = QIcon(resource_path("assets", "app_icon.png"))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    # Build service objects — no credentials needed!
    media = MediaSession()
    lyrics = LyricsFetcher(config)

    # Launch overlay
    window = LyricsWindow(config, media, lyrics)
    app.aboutToQuit.connect(window.save_window_geometry)
    tray_icon = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray_icon = create_tray_icon(app, window)
    else:
        print("[LyPy] System tray unavailable; running without tray icon.")

    if config.get("start_hidden", False) and tray_icon is None:
        window.show()
    elif not config.get("start_hidden", False):
        window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
