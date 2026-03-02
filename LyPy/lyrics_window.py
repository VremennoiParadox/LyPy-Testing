"""
PyQt5-based always-on-top lyrics overlay window.
Spotify-style with rounded corners, dynamic gradient backgrounds,
smooth scrolling, and edge-resize support for frameless windows.
"""

import io
import colorsys
import ctypes
from ctypes import wintypes
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QPushButton, QApplication, QSizePolicy,
)
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QRect, QPoint,
)
from PyQt5.QtGui import (
    QColor, QPalette, QLinearGradient, QPainter, QBrush, QPainterPath, QCursor,
)

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


DEFAULT_GRADIENT = ("#121212", "#1a1a2e", "#16213e")
CORNER_RADIUS = 16
EDGE_MARGIN = 6           # pixels from edge that trigger resize

WM_NCHITTEST = 0x0084
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17


def _dominant_color_from_bytes(image_bytes: bytes) -> tuple[int, int, int] | None:
    """
    Extract the dominant colour from album artwork bytes using Pillow.
    Spotify derives its lyrics background gradient from the album cover's
    most prominent colour — we replicate the same approach here.
    """
    if not _HAS_PIL or not image_bytes:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # Down-sample for speed
        img = img.resize((80, 80), Image.LANCZOS)
        pixels = list(img.getdata())

        # Filter out very dark and very bright pixels (backgrounds, glare)
        filtered = [
            (r, g, b) for r, g, b in pixels
            if 30 < (r + g + b) / 3 < 220
        ]
        if not filtered:
            filtered = pixels

        # Simple average for dominant tone
        avg_r = sum(p[0] for p in filtered) // len(filtered)
        avg_g = sum(p[1] for p in filtered) // len(filtered)
        avg_b = sum(p[2] for p in filtered) // len(filtered)
        return (avg_r, avg_g, avg_b)
    except Exception:
        return None


def _gradient_from_rgb(r: int, g: int, b: int) -> tuple[str, str, str]:
    """
    Build a 3-stop Spotify-style gradient from a single dominant colour.
    Top   = the colour itself (muted/darkened)
    Mid   = slightly darker
    Bottom = darkest
    """
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    # Ensure enough saturation so it's not grey
    s = max(s, 0.30)
    # Ensure enough brightness so the gradient is visible
    v = max(v, 0.45)

    def _to_hex(h_, s_, v_):
        cr, cg, cb = colorsys.hsv_to_rgb(h_, s_, v_)
        return f"#{int(cr*255):02x}{int(cg*255):02x}{int(cb*255):02x}"

    top    = _to_hex(h, s * 0.75, v * 0.55)   # rich dark
    mid    = _to_hex(h, s * 0.65, v * 0.35)   # darker
    bottom = _to_hex(h, s * 0.55, v * 0.18)   # near-black
    return (top, mid, bottom)


# ─── Rounded-corner gradient widget ─────────────────────────────────────

class RoundedGradientWidget(QWidget):
    """Paints a rounded-rectangle gradient background."""

    def __init__(self, parent=None, radius=CORNER_RADIUS):
        super().__init__(parent)
        self._colors = DEFAULT_GRADIENT
        self._radius = radius
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_gradient(self, colors: tuple[str, str, str]):
        self._colors = colors
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(),
                            self._radius, self._radius)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(self._colors[0]))
        grad.setColorAt(0.5, QColor(self._colors[1]))
        grad.setColorAt(1.0, QColor(self._colors[2]))
        p.fillPath(path, QBrush(grad))
        p.end()


# ─── Custom frameless title bar ──────────────────────────────────────────

class TitleBar(QWidget):
    close_clicked = pyqtSignal()
    minimise_clicked = pyqtSignal()
    pin_toggled = pyqtSignal(bool)
    settings_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self._drag_pos = None
        self._pinned = False        # starts unpinned (movable)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 6, 12, 0)
        layout.setSpacing(4)

        self.title = QLabel("\u266b LyPy")
        self.title.setStyleSheet(
            "color: rgba(255,255,255,0.65); font-size: 12px;"
            "font-weight: 600; background: transparent;"
        )
        layout.addWidget(self.title)
        layout.addStretch()

        btn = """
            QPushButton {
                border: none; border-radius: 12px;
                color: rgba(255,255,255,0.55); font-size: 13px;
                background: transparent;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); color: #fff; }
        """

        self.settings_btn = QPushButton("\u2699")   # gear icon
        self.settings_btn.setFixedSize(24, 24)
        self.settings_btn.setStyleSheet(btn)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.settings_btn)

        self.pin_btn = QPushButton("\ud83d\udccd")   # unpinned icon
        self.pin_btn.setFixedSize(24, 24)
        self.pin_btn.setStyleSheet(btn)
        self.pin_btn.setToolTip("Pin window (lock position)")
        self.pin_btn.clicked.connect(self._toggle_pin)
        layout.addWidget(self.pin_btn)

        self.min_btn = QPushButton("\u2500")
        self.min_btn.setFixedSize(24, 24)
        self.min_btn.setStyleSheet(btn)
        self.min_btn.clicked.connect(self.minimise_clicked.emit)
        layout.addWidget(self.min_btn)

        self.close_btn = QPushButton("\u2715")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet(
            btn.replace("rgba(255,255,255,0.12)", "rgba(232,17,35,0.75)")
        )
        self.close_btn.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self.close_btn)

        # Collect all action buttons for show/hide on hover
        self._action_buttons = [
            self.settings_btn, self.pin_btn, self.min_btn, self.close_btn
        ]
        # Start hidden
        for b in self._action_buttons:
            b.setVisible(False)

        self.setStyleSheet("background: transparent;")

    def _toggle_pin(self):
        self._pinned = not self._pinned
        if self._pinned:
            self.pin_btn.setText("\ud83d\udccc")
            self.pin_btn.setToolTip("Unpin (unlock position)")
        else:
            self.pin_btn.setText("\ud83d\udccd")
            self.pin_btn.setToolTip("Pin window (lock position)")
        self.pin_toggled.emit(self._pinned)

    # ── Drag support (disabled when pinned) ──
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._pinned:
            self._drag_pos = event.globalPos() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and not self._pinned and (event.buttons() & Qt.LeftButton):
            self.window().move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── Show/hide buttons on hover ──
    def _show_buttons(self):
        for b in self._action_buttons:
            b.setVisible(True)

    def _hide_buttons(self):
        for b in self._action_buttons:
            b.setVisible(False)

    def enterEvent(self, event):
        self._show_buttons()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hide_buttons()
        super().leaveEvent(event)


# ─── Smooth-scrolling scroll area ───────────────────────────────────────

class SmoothScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim = QPropertyAnimation(self.verticalScrollBar(), b"value")
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setDuration(400)

    def smooth_scroll_to(self, value: int):
        self._anim.stop()
        self._anim.setStartValue(self.verticalScrollBar().value())
        self._anim.setEndValue(value)
        self._anim.start()


# ─── Word-wrap label that correctly reports height-for-width ─────────────

class WordWrapLabel(QLabel):
    """QLabel subclass that properly computes height when word-wrapping."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        # Use the label's internal text layout to compute the actual height
        margins = self.contentsMargins()
        inner_w = width - margins.left() - margins.right()
        if inner_w <= 0:
            inner_w = 1
        doc_height = self.fontMetrics().boundingRect(
            0, 0, inner_w, 100000,
            int(self.alignment()) | Qt.TextWordWrap,
            self.text(),
        ).height()
        return doc_height + margins.top() + margins.bottom()

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(0)  # allow shrinking horizontally
        return hint

    def sizeHint(self):
        if self.wordWrap() and self.width() > 0:
            h = self.heightForWidth(self.width())
            return self.minimumSizeHint().expandedTo(
                self.minimumSizeHint().__class__(self.width(), h)
            )
        return super().sizeHint()


# ─── Main lyrics window ─────────────────────────────────────────────────

class LyricsWindow(QMainWindow):
    """Spotify-style lyrics overlay with rounded corners and gradient bg."""

    # Thread-safe signal: carries (track_key, top, mid, bottom) hex strings
    _gradient_ready = pyqtSignal(str, str, str, str)

    def __init__(self, config: dict, media_session, lyrics_fetcher):
        super().__init__()
        self.config = config
        self.media = media_session
        self.lyrics_fetcher = lyrics_fetcher

        self.current_track_key: str | None = None
        self.current_lyrics: dict | None = None
        self.current_line_index: int = -1
        self._gradient = DEFAULT_GRADIENT

        # Edge-resize state
        self._resize_edge = None
        self._resize_start_rect = None
        self._resize_start_pos = None

        # Connect the thread-safe gradient signal
        self._gradient_ready.connect(self._on_gradient_signal)

        self._init_window()
        self._init_ui()
        self._render_idle()
        self._start_polling()

    # ── Window flags ─────────────────────────────────────────────
    def _init_window(self):
        self.setWindowTitle("Spotify Lyrics")
        self.resize(self.config["window_width"], self.config["window_height"])
        self.setMinimumSize(280, 360)

        flags = Qt.Window | Qt.FramelessWindowHint
        if self.config.get("always_on_top"):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        # Translucent background so rounded corners don't show black edges
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

    def nativeEvent(self, eventType, message):
        """Use native Windows hit testing for reliable frameless edge resizing."""
        if self._is_pinned:
            return super().nativeEvent(eventType, message)

        if eventType == "windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCHITTEST:
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                local = self.mapFromGlobal(QPoint(x, y))

                edge = self._edge_at(local)
                if edge == "l":
                    return True, HTLEFT
                if edge == "r":
                    return True, HTRIGHT
                if edge == "t":
                    return True, HTTOP
                if edge == "b":
                    return True, HTBOTTOM
                if edge == "tl":
                    return True, HTTOPLEFT
                if edge == "tr":
                    return True, HTTOPRIGHT
                if edge == "bl":
                    return True, HTBOTTOMLEFT
                if edge == "br":
                    return True, HTBOTTOMRIGHT

        return super().nativeEvent(eventType, message)

    # ── UI layout ────────────────────────────────────────────────
    def _init_ui(self):
        self.bg = RoundedGradientWidget(radius=CORNER_RADIUS)
        self.setCentralWidget(self.bg)

        root = QVBoxLayout(self.bg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        self.title_bar = TitleBar(self)
        self.title_bar.close_clicked.connect(self._quit)
        self.title_bar.minimise_clicked.connect(self.showMinimized)
        self.title_bar.pin_toggled.connect(self._on_pin_toggled)
        root.addWidget(self.title_bar)

        # Scrollable lyrics area
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )

        self.lyrics_container = QWidget()
        self.lyrics_container.setStyleSheet("background: transparent;")
        self.lyrics_layout = QVBoxLayout(self.lyrics_container)
        self.lyrics_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lyrics_layout.setSpacing(4)
        self.lyrics_layout.setContentsMargins(24, 20, 24, 250)
        self.scroll_area.setWidget(self.lyrics_container)

        root.addWidget(self.scroll_area)
        self.lyric_labels: list[QLabel] = []

    # ── Edge-resize support (frameless) ──────────────────────────
    def _edge_at(self, pos: QPoint) -> str | None:
        """Return which edge/corner the cursor is near, or None."""
        r = self.rect()
        x, y = pos.x(), pos.y()
        m = EDGE_MARGIN
        on_left   = x < m
        on_right  = x > r.width() - m
        on_top    = y < m
        on_bottom = y > r.height() - m

        if on_top and on_left:     return "tl"
        if on_top and on_right:    return "tr"
        if on_bottom and on_left:  return "bl"
        if on_bottom and on_right: return "br"
        if on_left:   return "l"
        if on_right:  return "r"
        if on_top:    return "t"
        if on_bottom: return "b"
        return None

    _CURSORS = {
        "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
        "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
        "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
        "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
    }

    @property
    def _is_pinned(self) -> bool:
        return self.title_bar._pinned

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._is_pinned:
            edge = self._edge_at(event.pos())
            if edge:
                self._resize_edge = edge
                self._resize_start_rect = self.geometry()
                self._resize_start_pos = event.globalPos()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Block resize while pinned
        if self._is_pinned:
            self.unsetCursor()
            super().mouseMoveEvent(event)
            return

        if self._resize_edge and self._resize_start_pos:
            delta = event.globalPos() - self._resize_start_pos
            r = QRect(self._resize_start_rect)
            mn_w, mn_h = self.minimumWidth(), self.minimumHeight()
            e = self._resize_edge

            if "r" in e:
                r.setRight(r.right() + delta.x())
            if "b" in e:
                r.setBottom(r.bottom() + delta.y())
            if "l" in e:
                r.setLeft(r.left() + delta.x())
            if "t" in e:
                r.setTop(r.top() + delta.y())

            if r.width() < mn_w:
                if "l" in e:
                    r.setLeft(r.right() - mn_w)
                else:
                    r.setRight(r.left() + mn_w)
            if r.height() < mn_h:
                if "t" in e:
                    r.setTop(r.bottom() - mn_h)
                else:
                    r.setBottom(r.top() + mn_h)

            self.setGeometry(r)
            return

        # Update cursor when hovering near edges
        edge = self._edge_at(event.pos())
        if edge:
            self.setCursor(self._CURSORS[edge])
        else:
            self.unsetCursor()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_edge = None
        self._resize_start_rect = None
        self._resize_start_pos = None
        super().mouseReleaseEvent(event)

    # ── Polling ──────────────────────────────────────────────────
    def _start_polling(self):
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._tick)
        self.poll_timer.start(self.config["polling_interval_ms"])
        QTimer.singleShot(50, self._tick)

    def _tick(self):
        playback = self.media.get_current_playback()

        if not playback:
            if self.current_track_key is not None:
                self.current_track_key = None
                self._set_gradient(DEFAULT_GRADIENT)
                self._render_idle()
            return

        if playback["track_key"] != self.current_track_key:
            self.current_track_key = playback["track_key"]
            self.current_line_index = -1

            # Fetch album art in background thread → apply gradient when ready
            self._set_gradient(DEFAULT_GRADIENT)  # immediate fallback
            self.media.fetch_thumbnail(
                playback["track_key"], self._on_thumbnail_ready
            )

            duration_s = playback["duration_ms"] // 1000 if playback["duration_ms"] else 0
            self.current_lyrics = self.lyrics_fetcher.get_lyrics(
                track_name=playback["track_name"],
                artist=playback["artist"],
                album=playback.get("album", ""),
                duration_s=duration_s,
            )
            self._render_lyrics()

        if self.current_lyrics and self.current_lyrics["synced"]:
            self._highlight_line(playback["progress_ms"])

    # ── Gradient ─────────────────────────────────────────────────
    def _set_gradient(self, colors: tuple[str, str, str]):
        self._gradient = colors
        self.bg.set_gradient(colors)

    def _on_thumbnail_ready(self, track_key: str, thumb_bytes: bytes | None):
        """Called from background thread when thumbnail fetch completes.
        Does color extraction here (on bg thread), then emits a Qt signal
        to safely deliver the gradient to the main thread."""
        if track_key != self.current_track_key:
            return
        if thumb_bytes:
            dominant = _dominant_color_from_bytes(thumb_bytes)
        else:
            dominant = None
        if dominant:
            grad = _gradient_from_rgb(*dominant)
            # Emit thread-safe signal → received on Qt main thread
            self._gradient_ready.emit(track_key, grad[0], grad[1], grad[2])

    def _on_gradient_signal(self, track_key: str, top: str, mid: str, bottom: str):
        """Slot: receives gradient from background thread via signal (main thread)."""
        if track_key == self.current_track_key:
            self._set_gradient((top, mid, bottom))

    def _apply_thumb_gradient(self, track_key: str, rgb: tuple[int, int, int]):
        """Apply gradient on the main thread."""
        if track_key == self.current_track_key:
            self._set_gradient(_gradient_from_rgb(*rgb))

    # ── Idle state ───────────────────────────────────────────────
    def _render_idle(self):
        self._clear_labels()
        idle = WordWrapLabel("Play something on Spotify\u2026")
        idle.setStyleSheet(self._css_inactive())
        idle.setAlignment(Qt.AlignLeft)
        self.lyrics_layout.addWidget(idle)
        self.lyric_labels.append(idle)

    # ── Lyrics rendering ─────────────────────────────────────────
    def _render_lyrics(self):
        self._clear_labels()

        if not self.current_lyrics or not self.current_lyrics["lines"]:
            lbl = WordWrapLabel("No lyrics available")
            lbl.setStyleSheet(self._css_inactive())
            lbl.setAlignment(Qt.AlignLeft)
            self.lyrics_layout.addWidget(lbl)
            self.lyric_labels.append(lbl)
            return

        for line in self.current_lyrics["lines"]:
            text = line["words"].strip() or "\u266a"
            lbl = WordWrapLabel(text)
            lbl.setStyleSheet(self._css_inactive())
            lbl.setAlignment(Qt.AlignLeft)
            self.lyrics_layout.addWidget(lbl)
            self.lyric_labels.append(lbl)

        self.scroll_area.verticalScrollBar().setValue(0)
        # Defer geometry pass so labels know their width and wrap correctly
        QTimer.singleShot(0, self._relayout_labels)

    def _clear_labels(self):
        for lbl in self.lyric_labels:
            lbl.setParent(None)
            lbl.deleteLater()
        self.lyric_labels.clear()
        self.current_line_index = -1

    # ── Highlighting ─────────────────────────────────────────────
    def _highlight_line(self, progress_ms: int):
        if not self.current_lyrics or not self.current_lyrics["lines"]:
            return

        lines = self.current_lyrics["lines"]
        n = len(lines)

        idx = -1
        for i in range(n):
            if lines[i]["time_ms"] <= progress_ms:
                idx = i
            else:
                break

        if idx < 0:
            idx = 0
        if idx == self.current_line_index:
            return

        self.current_line_index = idx

        for i, lbl in enumerate(self.lyric_labels):
            if i < idx:
                lbl.setStyleSheet(self._css_past())
            elif i == idx:
                lbl.setStyleSheet(self._css_active())
            else:
                lbl.setStyleSheet(self._css_inactive())

        if 0 <= idx < len(self.lyric_labels):
            target = self.lyric_labels[idx]
            y = target.y()
            vh = self.scroll_area.viewport().height()
            self.scroll_area.smooth_scroll_to(max(0, y - vh // 3))

    # ── Pin / always-on-top ──────────────────────────────────────
    def _on_pin_toggled(self, pinned: bool):
        """Pin = lock position. Always-on-top stays on."""
        pass  # drag is disabled inside TitleBar when pinned

    @staticmethod
    def _quit():
        QApplication.quit()

    # ── Style helpers (rgba for correct Qt color parsing) ────────
    def _css_active(self) -> str:
        ff = self.config["font_family"]
        fs = self.config["font_size"]
        return (
            f"color: rgba(255, 255, 255, 1.0);"
            f"font-family: {ff};"
            f"font-size: {fs}px;"
            "font-weight: bold;"
            "padding: 6px 4px;"
            "background: transparent;"
        )

    def _css_past(self) -> str:
        ff = self.config["font_family"]
        fs = self.config["font_size"]
        return (
            f"color: rgba(255, 255, 255, 0.45);"
            f"font-family: {ff};"
            f"font-size: {fs}px;"
            "font-weight: bold;"
            "padding: 6px 4px;"
            "background: transparent;"
        )

    def _css_inactive(self) -> str:
        ff = self.config["font_family"]
        fs = self.config["font_size"]
        return (
            f"color: rgba(255, 255, 255, 0.25);"
            f"font-family: {ff};"
            f"font-size: {fs}px;"
            "font-weight: bold;"
            "padding: 6px 4px;"
            "background: transparent;"
        )

    # ── Force relayout on resize so word-wrap labels reflow ──────
    def _relayout_labels(self):
        """Invalidate label geometries so heightForWidth is recalculated."""
        for lbl in self.lyric_labels:
            lbl.updateGeometry()
        self.lyrics_container.adjustSize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_labels()

    # ── Save geometry on close ───────────────────────────────────
    def closeEvent(self, event):
        self.config["window_width"] = self.width()
        self.config["window_height"] = self.height()
        from config import save_config
        save_config(self.config)
        event.accept()
        QApplication.quit()
