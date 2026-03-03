"""
Spotify Lyrics Overlay — Main entry point.
No login, no credentials, no setup needed.
Just run it and play music!
"""

import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from config import load_config
from spotify_client import MediaSession
from lyrics_fetcher import LyricsFetcher
from lyrics_window import LyricsWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LyPy Lyrics")

    # Dark application style
    app.setStyle("Fusion")
    dark_palette = app.palette()
    dark_palette.setColor(dark_palette.Window, Qt.black)
    dark_palette.setColor(dark_palette.WindowText, Qt.white)
    app.setPalette(dark_palette)

    config = load_config()

    # Build service objects — no credentials needed!
    media = MediaSession()
    lyrics = LyricsFetcher()

    # Launch overlay
    window = LyricsWindow(config, media, lyrics)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
