# 🎵 LyPy — Lyrics Overlay

A lightweight, always-on-top desktop widget that shows **time-synced lyrics** for whatever you're playing — right on your screen in real-time.

**Zero login. Zero API keys. Zero cookies. Just run it.**

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green)
![Windows](https://img.shields.io/badge/OS-Windows%2010%2F11-blue)

---

## Supported Music Apps

LyPy works with any app that registers with the Windows Media Transport Controls API, including:

- **Spotify**
- **YouTube Music**
- **Apple Music**
- **Amazon Music**
- **Tidal**
- **Deezer**
- **Yandex Music**
- Any browser-based or desktop player that exposes WMTC (e.g. Microsoft Edge, Google Chrome, Mozilla Firefox)

> **Note:** If two or more apps are playing at the same time, LyPy will warn you to stop playback in all but one app to avoid sync issues.

---

## Features

- **Live synced lyrics** — current line highlighted as the song plays
- **Works with multiple music apps** — Spotify, YouTube Music, Apple Music, and more
- **No login or credentials required** — reads playback from Windows + lyrics from LRCLIB.net
- **Multi-app conflict warning** — tells you when more than one app is playing simultaneously
- **Always-on-top** overlay you can pin/unpin
- **Resizable & draggable** window
- **Dynamic album-art gradient** background
- **Customisable** — font size, opacity, colours, window size (all saved automatically)
- **Auto-scrolls** to the active lyric line

---

## How it works

1. **Windows Media Transport Controls API** detects what song is currently playing (track, artist, position, play/pause) — no login needed
2. **LRCLIB.net** (free open-source API) provides time-synced lyrics — no API key needed
3. The overlay displays the lyrics and highlights the current line in sync

---

## Prerequisites

- **Windows 10 or 11**
- **Python 3.10+** installed ([python.org](https://www.python.org/downloads/))
- A supported music app playing on your desktop

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the app

```bash
python main.py
```

That's it! No setup dialog, no credentials. Just play a song and the lyrics appear.

---

## Usage

1. **Play a song** in any supported app
2. The overlay detects the song and shows synced lyrics automatically
3. **Drag** the title bar to reposition
4. **Resize** from the edges/corners
5. Click 📌 to pin/lock the window position
6. The window size is remembered between sessions

### Customisation

Edit `settings.json` to change:

| Setting | Default | Description |
|---------|---------|-------------|
| `window_width` | 420 | Width in pixels |
| `window_height` | 650 | Height in pixels |
| `window_opacity` | 0.92 | 0.3 – 1.0 |
| `font_size` | 18 | Lyrics font size |
| `bg_color` | `#0d0d0d` | Background colour |
| `text_color` | `#717171` | Inactive lyrics colour |
| `active_text_color` | `#ffffff` | Active lyric line colour |
| `polling_interval_ms` | 1000 | How often to check playback (ms) |
| `always_on_top` | true | Pin window above others |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Play something…" shown despite music playing | Make sure you're using the desktop app, not a browser tab |
| "No lyrics available" | Not all tracks have lyrics on LRCLIB.net |
| Multi-app warning shown | Stop playback in all but one music app |
| Window doesn't detect song | Ensure the app registers with Windows Media Transport Controls |
| `winrt` install fails | Make sure you're on Windows 10+ with Python 3.10+ |
| Window disappears after un-pin | Click the taskbar icon to bring it back |

---

## Project Structure

```
LyPy/
├── main.py              # Entry point (just run it!)
├── config.py            # Settings load/save
├── spotify_client.py    # Windows Media Session reader (no auth)
├── lyrics_fetcher.py    # LRCLIB.net lyrics fetcher (no auth)
├── lyrics_window.py     # PyQt5 overlay window
├── requirements.txt     # Python dependencies
├── settings.json        # Auto-generated config (after first run)
└── README.md            # This file
```

---

## Legal Note

This app reads playback info from the **Windows Media Transport Controls API** and fetches lyrics from **LRCLIB.net** (an open-source community lyrics database). It is not affiliated with or endorsed by any music streaming service. Use for personal use only.
