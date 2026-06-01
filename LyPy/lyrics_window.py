"""
PyQt5-based always-on-top lyrics overlay window.
Spotify-style with rounded corners, dynamic gradient backgrounds,
smooth scrolling, and edge-resize support for frameless windows.
"""

import os
import threading
import colorsys
import ctypes
from ctypes import wintypes
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QPushButton, QApplication, QSizePolicy,
    QSlider, QComboBox, QGroupBox, QFormLayout, QStyleFactory,
    QCheckBox, QLineEdit, QFrame,
)
from PyQt5.QtCore import (
    Qt, QSize, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QRect, QPoint,
)
from PyQt5.QtGui import (
    QIcon, QPixmap, QColor, QPalette, QLinearGradient, QPainter,
    QBrush, QPainterPath, QCursor, QFont, QFontDatabase, QDesktopServices,
)
from PyQt5.QtCore import QUrl

from album_color import spotify_background_rgb
from config import resource_path as _resource_path, scripts_dir
from lyrics_providers import is_synced_lyrics
from settings_styles import PANEL_SS
from spotify_font import (
    apply_lyrics_font_to_config,
    make_lyrics_font,
    resolve_lyrics_font_family,
)


DEFAULT_GRADIENT = ("#1a1a2e", "#141425", "#0e0e1a")
CORNER_RADIUS = 16
EDGE_MARGIN = 6           # pixels from edge that trigger resize

# Window size: lyrics can shrink freely; settings enforce a larger floor while open.
MIN_WINDOW_SIZE = QSize(280, 360)
SETTINGS_WINDOW_MIN = QSize(420, 640)

WM_NCHITTEST = 0x0084
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17


def _gradient_from_rgb(r: int, g: int, b: int, saturation_pct: int = 80) -> tuple[str, str, str]:
    """
    Build a 3-stop Spotify-style gradient from a single dominant colour.
    saturation_pct (0-100) controls how vivid the background is.
    """
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    sat_factor = (saturation_pct / 100.0) ** 0.5
    s = min(s * sat_factor, 1.0)
    s = max(s, 0.08)
    v = min(max(v, 0.35), 0.88)

    def _to_hex(h_, s_, v_):
        cr, cg, cb = colorsys.hsv_to_rgb(h_, s_, v_)
        return f"#{int(cr*255):02x}{int(cg*255):02x}{int(cb*255):02x}"

    # Subtle vertical wash (no near-black fade at the bottom).
    top = _to_hex(h, s * 0.94, v * 0.58)
    mid = _to_hex(h, s * 0.92, v * 0.52)
    bottom = _to_hex(h, s * 0.90, v * 0.46)
    return (top, mid, bottom)


# ─── Rounded-corner gradient widget ─────────────────────────────────────

class RoundedGradientWidget(QWidget):
    """Paints a rounded-rectangle gradient background with optional dim overlay."""

    def __init__(self, parent=None, radius=CORNER_RADIUS):
        super().__init__(parent)
        self._colors = DEFAULT_GRADIENT
        self._radius = radius
        self._dim = 0          # 0-255 overlay darkness (0 = off)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_gradient(self, colors: tuple[str, str, str]):
        self._colors = colors
        self.update()

    def set_dim(self, alpha: int):
        """Set overlay darkness (0 = normal, ~160 = translucent settings look)."""
        self._dim = max(0, min(255, alpha))
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
        if self._dim > 0:
            p.fillPath(path, QBrush(QColor(0, 0, 0, self._dim)))
        p.end()


# ─── Custom frameless title bar ──────────────────────────────────────────

class TitleBar(QWidget):
    close_clicked = pyqtSignal()
    minimise_clicked = pyqtSignal()
    pin_toggled = pyqtSignal(bool)
    settings_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    play_pause_clicked = pyqtSignal()
    next_clicked = pyqtSignal()

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
        self.title.setMaximumWidth(80)
        layout.addWidget(self.title)

        # ── Inline progress bar (between title and buttons) ──
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar, 1)   # stretch=1 fills available space

        btn = """
            QPushButton {
                border: none; border-radius: 12px;
                color: rgba(255,255,255,0.55); font-size: 13px;
                background: transparent;
            }
            QPushButton:hover { background: rgba(255,255,255,0.12); color: #fff; }
        """
        # ── Asset loader ──
        def _icon(name: str) -> QIcon:
            path = _resource_path("assets", f"{name}.png")
            pix = QPixmap(path)
            return QIcon(pix)

        _glass_style = (
            "QPushButton { background: transparent; border: none; }"
            "QPushButton:hover { background: rgba(255,255,255,0.10); border-radius: 14px; }"
            "QPushButton:pressed { background: rgba(255,255,255,0.04); }"
        )
        _icon_sz = QSize(22, 22)
        _btn_sz  = 28

        # ── Pin button ──
        self._icon_pin        = _icon("btn_pin")
        self._icon_pin_locked = _icon("btn_pin_locked")
        self.pin_btn = QPushButton()
        self.pin_btn.setIcon(self._icon_pin)
        self.pin_btn.setIconSize(_icon_sz)
        self.pin_btn.setFixedSize(_btn_sz, _btn_sz)
        self.pin_btn.setStyleSheet(_glass_style)
        self.pin_btn.setToolTip("Pin window (lock position)")
        self.pin_btn.clicked.connect(self._toggle_pin)
        layout.addWidget(self.pin_btn)

        # ── Media controls ──
        self._icon_play  = _icon("btn_play")
        self._icon_pause = _icon("btn_pause")

        self.prev_btn = QPushButton()
        self.prev_btn.setIcon(_icon("btn_prev"))
        self.prev_btn.setIconSize(_icon_sz)
        self.prev_btn.setFixedSize(_btn_sz, _btn_sz)
        self.prev_btn.setStyleSheet(_glass_style)
        self.prev_btn.setToolTip("Previous")
        self.prev_btn.clicked.connect(self.prev_clicked.emit)
        layout.addWidget(self.prev_btn)

        self.play_pause_btn = QPushButton()
        self.play_pause_btn.setIcon(self._icon_pause)
        self.play_pause_btn.setIconSize(_icon_sz)
        self.play_pause_btn.setFixedSize(_btn_sz, _btn_sz)
        self.play_pause_btn.setStyleSheet(_glass_style)
        self.play_pause_btn.setToolTip("Play / Pause")
        self.play_pause_btn.clicked.connect(self.play_pause_clicked.emit)
        layout.addWidget(self.play_pause_btn)

        self.next_btn = QPushButton()
        self.next_btn.setIcon(_icon("btn_next"))
        self.next_btn.setIconSize(_icon_sz)
        self.next_btn.setFixedSize(_btn_sz, _btn_sz)
        self.next_btn.setStyleSheet(_glass_style)
        self.next_btn.setToolTip("Next")
        self.next_btn.clicked.connect(self.next_clicked.emit)
        layout.addWidget(self.next_btn)

        # ── Settings button ──
        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(_icon("btn_settings"))
        self.settings_btn.setIconSize(_icon_sz)
        self.settings_btn.setFixedSize(_btn_sz, _btn_sz)
        self.settings_btn.setStyleSheet(_glass_style)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.settings_btn)

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
            self.pin_btn, self.prev_btn, self.play_pause_btn,
            self.next_btn, self.settings_btn, self.min_btn, self.close_btn,
        ]
        # Force Fusion style so Windows native renderer doesn't paint a black
        # hover background that ignores our transparent stylesheet.
        _fusion = QStyleFactory.create("Fusion")
        for b in self._action_buttons:
            b.setStyle(_fusion)
            b.setAttribute(Qt.WA_TranslucentBackground)
            b.setVisible(False)

        self.setStyleSheet("background: transparent;")

    def _toggle_pin(self):
        self._pinned = not self._pinned
        if self._pinned:
            self.pin_btn.setIcon(self._icon_pin_locked)
            self.pin_btn.setToolTip("Unpin (unlock position)")
        else:
            self.pin_btn.setIcon(self._icon_pin)
            self.pin_btn.setToolTip("Pin window (lock position)")
        self.pin_toggled.emit(self._pinned)

    def set_playing(self, playing: bool):
        """Swap the play/pause icon to reflect the current playback state."""
        self.play_pause_btn.setIcon(
            self._icon_pause if playing else self._icon_play
        )

    def set_progress(self, progress_ms: int, duration_ms: int):
        self.progress_bar.set_progress(progress_ms, duration_ms)

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
        self.progress_bar.setVisible(True)

    def _hide_buttons(self):
        for b in self._action_buttons:
            b.setVisible(False)
        self.progress_bar.setVisible(False)

    def enterEvent(self, event):
        self._show_buttons()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hide_buttons()
        super().leaveEvent(event)


# ─── Thin song-progress bar (title-bar overlay) ─────────────────────────

class ProgressBar(QWidget):
    """Inline progress bar drawn as a thin pill, vertically centred in the title bar.

    Width tiers degrade gracefully:
    - Tier 1 (widest): left time + bar + right time
    - Tier 2: left time + right time (no bar)
    - Tier 3: compact "2:25 / 4:07" centered
    - Tier 4 (narrowest): nothing drawn
    """

    _BAR_H   = 3
    _PAD     = 6
    _MIN_BAR = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress    = 0.0
        self._progress_ms = 0
        self._duration_ms = 0
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    @staticmethod
    def _fmt(ms: int) -> str:
        s   = ms // 1000
        m, s = divmod(s, 60)
        return f"{m}:{s:02d}"

    def set_progress(self, progress_ms: int, duration_ms: int):
        self._progress_ms = progress_ms
        self._duration_ms = duration_ms
        if duration_ms and duration_ms > 0:
            self._progress = max(0.0, min(1.0, progress_ms / duration_ms))
        else:
            self._progress = 0.0
        self.update()

    def paintEvent(self, _event):
        w = self.width()
        h = self.height()
        if w < 1:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        font = p.font()
        font.setPointSize(8)
        font.setWeight(QFont.Medium)
        p.setFont(font)
        fm = p.fontMetrics()

        left_txt  = self._fmt(self._progress_ms)
        right_txt = self._fmt(self._duration_ms)
        lw = fm.horizontalAdvance(left_txt)
        rw = fm.horizontalAdvance(right_txt)
        gap = 6
        both_w = lw + gap + rw
        compact_txt = f"{left_txt} / {right_txt}"
        cw = fm.horizontalAdvance(compact_txt)

        text_color = QColor(255, 255, 255, 160)
        p.setPen(text_color)
        cy = h // 2

        bar_room = w - both_w - self._PAD * 2
        if bar_room >= self._MIN_BAR:
            # Tier 1: full layout
            p.drawText(QRect(0, 0, lw, h), Qt.AlignVCenter | Qt.AlignLeft, left_txt)
            p.drawText(QRect(w - rw, 0, rw, h), Qt.AlignVCenter | Qt.AlignRight, right_txt)
            bh = self._BAR_H
            bar_x = lw + self._PAD
            bar_w = bar_room
            bar_y = cy - bh // 2
            r = bh / 2
            track = QPainterPath()
            track.addRoundedRect(bar_x, bar_y, bar_w, bh, r, r)
            p.fillPath(track, QBrush(QColor(255, 255, 255, 45)))
            fill_w = int(bar_w * self._progress)
            if fill_w > 0:
                fill = QPainterPath()
                fill.addRoundedRect(bar_x, bar_y, fill_w, bh, r, r)
                p.fillPath(fill, QBrush(QColor(255, 255, 255, 200)))
        elif w >= both_w:
            # Tier 2: two times side by side, no bar
            p.drawText(QRect(0, 0, lw, h), Qt.AlignVCenter | Qt.AlignLeft, left_txt)
            p.drawText(QRect(w - rw, 0, rw, h), Qt.AlignVCenter | Qt.AlignRight, right_txt)
        elif w >= cw:
            # Tier 3: compact "2:25 / 4:07"
            p.drawText(QRect(0, 0, w, h), Qt.AlignVCenter | Qt.AlignHCenter, compact_txt)
        # Tier 4: too narrow, draw nothing

        p.end()


# ─── Smooth-scrolling scroll area ───────────────────────────────────────

class SmoothScrollArea(QScrollArea):
    def __init__(self, parent=None, scroll_duration_ms: int = 400):
        super().__init__(parent)
        self._anim = QPropertyAnimation(self.verticalScrollBar(), b"value")
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.set_scroll_duration(scroll_duration_ms)

    def set_scroll_duration(self, ms: int) -> None:
        self._anim.setDuration(max(0, int(ms)))

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
            return self.minimumSizeHint().expandedTo(QSize(self.width(), h))
        return super().sizeHint()


# ─── Inline settings panel ───────────────────────────────────────────────

class SettingsPanel(QWidget):
    """Scrollable inline settings sheet; back arrow autosaves and closes."""
    closed = pyqtSignal()
    saved = pyqtSignal()

    def minimumSizeHint(self):
        return QSize(400, 520)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self._advanced_open = False
        self.setObjectName("settingsPanel")
        self.setStyleSheet(PANEL_SS)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 4, 16, 12)
        root.setSpacing(0)

        top_row = QHBoxLayout()
        self.back_btn = QPushButton("\u2190")
        self.back_btn.setObjectName("backBtn")
        self.back_btn.setFixedSize(32, 32)
        self.back_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.back_btn.setToolTip("Save and go back")
        self.back_btn.clicked.connect(self._on_back)
        top_row.addWidget(self.back_btn)
        top_row.addStretch()
        root.addLayout(top_row)

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setObjectName("settingsScrollContent")
        col = QVBoxLayout(content)
        col.setContentsMargins(4, 0, 4, 8)
        col.setSpacing(0)

        col.addWidget(self._section_title("Appearance"))
        col.addLayout(self._inline_slider(
            "Font size", 14, 48, config["font_size"], "px", "size"))
        col.addSpacing(14)
        col.addLayout(self._inline_slider(
            "Line spacing", 0, 10, config.get("line_spacing", 3), "px", "spacing"))
        col.addSpacing(14)
        col.addLayout(self._inline_slider(
            "Color saturation", 0, 100, config.get("bg_saturation", 80), "%", "sat"))

        col.addWidget(self._divider())
        col.addWidget(self._section_title("Behaviour"))
        col.addWidget(self._switch_row(
            "Start LyPy at Windows login", "start_at_login",
            config.get("start_at_login", False)))
        col.addSpacing(10)
        col.addWidget(self._switch_row(
            "Show when Spotify is the active player",
            "auto_show_on_spotify",
            config.get("auto_show_on_spotify", True)))
        col.addSpacing(10)
        col.addWidget(self._switch_row(
            "Raise when Spotify.exe starts (LyPy already running)",
            "raise_on_spotify_process_start",
            config.get("raise_on_spotify_process_start", False)))
        col.addSpacing(10)
        col.addWidget(self._switch_row(
            "Launch hidden to tray", "start_hidden",
            config.get("start_hidden", False)))
        col.addWidget(self._divider())
        self._advanced_toggle = QPushButton("\u25b8  Advanced")
        self._advanced_toggle.setObjectName("collapseHeader")
        self._advanced_toggle.setCursor(QCursor(Qt.PointingHandCursor))
        self._advanced_toggle.clicked.connect(self._toggle_advanced)
        col.addWidget(self._advanced_toggle)

        self._advanced_body = QWidget()
        adv = QVBoxLayout(self._advanced_body)
        adv.setContentsMargins(0, 4, 0, 0)
        adv.setSpacing(12)
        adv.addWidget(self._plain_field(
            "Bug report URL", "bug_report_url",
            config.get("bug_report_url", "https://github.com")))
        self._open_scripts_btn = QPushButton("Open optional Windows hook script folder")
        self._open_scripts_btn.setObjectName("linkAction")
        self._open_scripts_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._open_scripts_btn.clicked.connect(self._open_scripts_folder)
        adv.addWidget(self._open_scripts_btn)
        self._advanced_body.setVisible(False)
        col.addWidget(self._advanced_body)

        col.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        actions.addStretch()
        self.bug_btn = QPushButton("Report a bug")
        self.bug_btn.setObjectName("textAction")
        self.bug_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.bug_btn.clicked.connect(self._open_bug_report)
        actions.addWidget(self.bug_btn)
        self.reset_btn = QPushButton("Reset to defaults")
        self.reset_btn.setObjectName("textActionDanger")
        self.reset_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.reset_btn.clicked.connect(self._on_reset)
        actions.addWidget(self.reset_btn)
        actions.addStretch()
        root.addLayout(actions)

    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setObjectName("sectionTitle")
        return lbl

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setObjectName("settingsDivider")
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        return line

    def _inline_slider(
        self, label: str, lo: int, hi: int, value: int, suffix: str, attr: str,
    ) -> QVBoxLayout:
        block = QVBoxLayout()
        block.setSpacing(8)
        header = QHBoxLayout()
        name_lbl = QLabel(label)
        name_lbl.setObjectName("settingLabel")
        header.addWidget(name_lbl)
        header.addStretch()
        val_lbl = QLabel(f"{value}{suffix}")
        val_lbl.setObjectName("valueLabel")
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(val_lbl)
        block.addLayout(header)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(value)
        slider.valueChanged.connect(
            lambda v, l=val_lbl, s=suffix: l.setText(f"{v}{s}"))
        block.addWidget(slider)

        setattr(self, f"_{attr}_slider", slider)
        setattr(self, f"_{attr}_label", val_lbl)
        return block

    def _switch_row(self, label: str, attr: str, checked: bool) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(12)
        text = QLabel(label)
        text.setObjectName("settingLabel")
        text.setWordWrap(True)
        h.addWidget(text, 1)
        checkbox = QCheckBox()
        checkbox.setObjectName("switchCheck")
        checkbox.setChecked(checked)
        checkbox.setCursor(QCursor(Qt.PointingHandCursor))
        h.addWidget(checkbox, 0, Qt.AlignRight | Qt.AlignVCenter)
        setattr(self, f"_{attr}_checkbox", checkbox)
        return row

    def _secret_field(self, caption: str, attr: str, value: str) -> QWidget:
        return self._text_field(caption, attr, value, secret=True)

    def _plain_field(self, caption: str, attr: str, value: str) -> QWidget:
        return self._text_field(caption, attr, value, secret=False)

    def _text_field(self, caption: str, attr: str, value: str, *, secret: bool) -> QWidget:
        block = QWidget()
        v = QVBoxLayout(block)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        lbl = QLabel(caption)
        lbl.setObjectName("fieldCaption")
        v.addWidget(lbl)
        edit = QLineEdit(value)
        edit.setObjectName("settingsField")
        if secret:
            edit.setEchoMode(QLineEdit.Password)
        v.addWidget(edit)
        setattr(self, f"_{attr}_edit", edit)
        return block

    def _toggle_advanced(self):
        self._advanced_open = not self._advanced_open
        self._advanced_body.setVisible(self._advanced_open)
        chevron = "\u25be  " if self._advanced_open else "\u25b8  "
        self._advanced_toggle.setText(f"{chevron}Advanced")

    def _open_bug_report(self):
        url = self.config.get("bug_report_url") or "https://github.com"
        QDesktopServices.openUrl(QUrl(url))

    def _open_scripts_folder(self):
        d = scripts_dir()
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(d)))

    def _persist_config(self) -> bool:
        """Write widgets to config; return True if lyric cache should clear."""
        self.config["font_size"] = self._size_slider.value()
        self.config["line_spacing"] = self._spacing_slider.value()
        self.config["bg_saturation"] = self._sat_slider.value()
        self.config["start_at_login"] = self._start_at_login_checkbox.isChecked()
        self.config["auto_show_on_spotify"] = self._auto_show_on_spotify_checkbox.isChecked()
        self.config["raise_on_spotify_process_start"] = (
            self._raise_on_spotify_process_start_checkbox.isChecked()
        )
        self.config["start_hidden"] = self._start_hidden_checkbox.isChecked()
        self.config["bug_report_url"] = (
            self._bug_report_url_edit.text().strip() or "https://github.com"
        )

        from config import save_config, set_start_at_login

        save_config(self.config)
        set_start_at_login(self.config["start_at_login"])
        return False

    def _on_back(self):
        if self._persist_config():
            win = self.parent()
            if hasattr(win, "lyrics_fetcher"):
                win.lyrics_fetcher.clear_cache()
        self.saved.emit()
        self.closed.emit()

    def _on_reset(self):
        from config import DEFAULT_CONFIG, save_config, set_start_at_login

        for key, val in DEFAULT_CONFIG.items():
            self.config[key] = val
        save_config(self.config)
        set_start_at_login(self.config.get("start_at_login", False))
        self.sync_from_config()
        win = self.parent()
        if hasattr(win, "lyrics_fetcher"):
            win.lyrics_fetcher.clear_cache()
        self.saved.emit()

    def sync_from_config(self):
        self._size_slider.setValue(self.config["font_size"])
        self._size_label.setText(f"{self.config['font_size']}px")
        sp = self.config.get("line_spacing", 3)
        self._spacing_slider.setValue(sp)
        self._spacing_label.setText(f"{sp}px")
        sat = self.config.get("bg_saturation", 80)
        self._sat_slider.setValue(sat)
        self._sat_label.setText(f"{sat}%")
        self._start_at_login_checkbox.setChecked(self.config.get("start_at_login", False))
        self._auto_show_on_spotify_checkbox.setChecked(self.config.get("auto_show_on_spotify", True))
        self._raise_on_spotify_process_start_checkbox.setChecked(
            self.config.get("raise_on_spotify_process_start", False)
        )
        self._start_hidden_checkbox.setChecked(self.config.get("start_hidden", False))
        self._bug_report_url_edit.setText(self.config.get("bug_report_url", "https://github.com"))


# ─── Main lyrics window ─────────────────────────────────────────────────

class LyricsWindow(QMainWindow):
    """Spotify-style lyrics overlay with rounded corners and gradient bg."""

    # Thread-safe signals
    _gradient_ready = pyqtSignal(str, str, str, str)
    _playback_ready = pyqtSignal(object)
    _lyrics_ready = pyqtSignal(int, str, object)

    def __init__(self, config: dict, media_session, lyrics_fetcher):
        super().__init__()
        self.config = config
        self.media = media_session
        self.lyrics_fetcher = lyrics_fetcher
        apply_lyrics_font_to_config(self.config)

        self.current_track_key: str | None = None
        self._playback_worker_running = False
        self._lyrics_gen = 0
        self._last_progress_ms = 0
        self._last_duration_ms = 0

        self._gradient_ready.connect(self._on_gradient_signal)
        self._playback_ready.connect(self._on_playback_result)
        self._lyrics_ready.connect(self._on_lyrics_ready)
        self.current_lyrics: dict | None = None
        self.current_line_index: int = -1
        self._gradient = DEFAULT_GRADIENT

        # Edge-resize state
        self._resize_edge = None
        self._resize_start_rect = None
        self._resize_start_pos = None

        self._saved_settings_geometry: QRect | None = None
        self._settings_geo_anim: QPropertyAnimation | None = None

        self._init_window()
        self._init_ui()
        self._render_idle()
        self._start_polling()

    # ── Window flags ─────────────────────────────────────────────
    def _init_window(self):
        self.setWindowTitle("LyPy Lyrics")
        win_icon = QIcon(_resource_path("assets", "app_icon.png"))
        if not win_icon.isNull():
            self.setWindowIcon(win_icon)
        self.resize(self.config["window_width"], self.config["window_height"])
        self.setMinimumSize(MIN_WINDOW_SIZE.width(), MIN_WINDOW_SIZE.height())

        flags = Qt.Window | Qt.FramelessWindowHint
        if self.config.get("always_on_top"):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        # Translucent background so rounded corners don't show black edges
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._apply_window_opacity()

    def nativeEvent(self, eventType, message):
        """Use native Windows hit testing for reliable frameless edge resizing."""
        if self._is_pinned:
            return super().nativeEvent(eventType, message)

        if eventType == "windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCHITTEST:
                x = ctypes.c_int16(msg.lParam & 0xFFFF).value
                y = ctypes.c_int16((msg.lParam >> 16) & 0xFFFF).value
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
        self.title_bar.settings_clicked.connect(self._open_settings)
        self.title_bar.prev_clicked.connect(self._media_prev)
        self.title_bar.play_pause_clicked.connect(self._media_play_pause)
        self.title_bar.next_clicked.connect(self._media_next)
        root.addWidget(self.title_bar)

        # Scrollable lyrics area
        self.scroll_area = SmoothScrollArea(
            scroll_duration_ms=int(self.config.get("scroll_animation_ms", 400)),
        )
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
        self.lyrics_layout.setSpacing(self.config.get("line_spacing", 3))
        self._apply_lyrics_bottom_margin()
        self.scroll_area.setWidget(self.lyrics_container)

        root.addWidget(self.scroll_area)
        self.lyric_labels: list[QLabel] = []

        # Inline settings panel (hidden by default)
        self.settings_panel = SettingsPanel(self.config, self)
        self.settings_panel.closed.connect(self._close_settings)
        self.settings_panel.saved.connect(self._on_settings_saved)
        self.settings_panel.setVisible(False)
        root.addWidget(self.settings_panel)
        self._settings_open = False

    def _apply_lyrics_bottom_margin(self):
        fs = int(self.config.get("font_size", 28))
        bottom = max(120, int(fs * 4.5) + 48)
        self.lyrics_layout.setContentsMargins(24, 20, 24, bottom)

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

        self._spotify_was_running = False
        self._spotify_timer = QTimer(self)
        self._spotify_timer.timeout.connect(self._tick_spotify_process)
        self._spotify_timer.start(3000)

    def _tick_spotify_process(self):
        if not self.config.get("raise_on_spotify_process_start", False):
            return
        try:
            from spotify_process import spotify_exe_running
            on = spotify_exe_running()
        except Exception:
            return
        if on and not self._spotify_was_running:
            if not self.isVisible():
                self.showNormal()
            self.raise_()
            self.activateWindow()
        self._spotify_was_running = on

    def _tick(self):
        if self._playback_worker_running:
            return
        self._playback_worker_running = True
        threading.Thread(target=self._poll_playback, daemon=True).start()

    def _poll_playback(self):
        playback = self.media.get_current_playback()
        self._playback_ready.emit(playback)

    def _on_playback_result(self, playback):
        self._playback_worker_running = False

        if playback and self.config.get("auto_show_on_spotify", True):
            if playback.get("source_app", "").lower() == "spotify" and not self.isVisible():
                self.showNormal()
                self.raise_()
                self.activateWindow()

        if not playback:
            if self.current_track_key is not None:
                self._lyrics_gen += 1
                self.current_track_key = None
                self.current_lyrics = None
                self._set_gradient(DEFAULT_GRADIENT)
                self._render_idle()
            return

        if playback.get("conflict"):
            self._lyrics_gen += 1
            self.current_track_key = "__multi_app_conflict__"
            self.current_lyrics = None
            self.current_line_index = -1
            self._set_gradient(DEFAULT_GRADIENT)
            self._render_conflict(playback.get("playing_apps", []))
            return

        self._last_progress_ms = playback.get("progress_ms", 0)
        self._last_duration_ms = playback.get("duration_ms", 0)

        if playback["track_key"] != self.current_track_key:
            self._lyrics_gen += 1
            gen = self._lyrics_gen
            self.current_track_key = playback["track_key"]
            self.current_line_index = -1
            self.current_lyrics = None

            self._set_gradient(DEFAULT_GRADIENT)
            self.media.fetch_thumbnail(
                playback["track_key"], gen, self._on_thumbnail_ready
            )

            self._render_fetching_lyrics()

            snap = {
                "track_name": playback["track_name"],
                "artist": playback["artist"],
                "album": playback.get("album", ""),
                "duration_ms": self._last_duration_ms,
                "track_key": playback["track_key"],
            }
            threading.Thread(
                target=self._fetch_lyrics_worker,
                args=(gen, snap),
                daemon=True,
            ).start()

        if self.current_lyrics and self.current_lyrics.get("lines"):
            self._highlight_line(self._last_progress_ms, self._last_duration_ms)

        self.title_bar.set_playing(playback.get("is_playing", True))
        self.title_bar.set_progress(self._last_progress_ms, self._last_duration_ms)

    def _fetch_lyrics_worker(self, gen: int, snap: dict):
        duration_s = snap["duration_ms"] // 1000 if snap.get("duration_ms") else 0
        result = self.lyrics_fetcher.get_lyrics(
            track_name=snap["track_name"],
            artist=snap["artist"],
            album=snap.get("album", ""),
            duration_s=duration_s,
        )
        self._lyrics_ready.emit(gen, snap["track_key"], result)

    def _on_lyrics_ready(self, gen: int, track_key: str, result: object):
        if gen != self._lyrics_gen:
            return
        if self.current_track_key != track_key:
            return
        self.current_lyrics = result if isinstance(result, dict) else None
        if not self.current_lyrics:
            self.current_lyrics = {"synced": False, "lines": []}
        self._render_lyrics()
        if self.current_lyrics.get("lines"):
            self._highlight_line(self._last_progress_ms, self._last_duration_ms)

    # ── Gradient ─────────────────────────────────────────────────
    def _set_gradient(self, colors: tuple[str, str, str]):
        self._gradient = colors
        self.bg.set_gradient(colors)

    def _on_thumbnail_ready(
        self, track_key: str, generation: int, thumb_bytes: bytes | None
    ):
        """Called from background thread when thumbnail fetch completes.
        Does color extraction here (on bg thread), then emits a Qt signal
        to safely deliver the gradient to the main thread."""
        if generation != self._lyrics_gen:
            return
        if track_key != self.current_track_key:
            return
        if thumb_bytes:
            dominant = spotify_background_rgb(thumb_bytes)
        else:
            dominant = None
        if dominant:
            sat = self.config.get("bg_saturation", 80)
            grad = _gradient_from_rgb(*dominant, saturation_pct=sat)
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
    def _render_fetching_lyrics(self):
        self._clear_labels()
        msg = WordWrapLabel("Fetching lyrics\u2026")
        self._apply_lyric_label_style(msg, self._css_inactive())
        msg.setAlignment(Qt.AlignLeft)
        self.lyrics_layout.addWidget(msg)
        self.lyric_labels.append(msg)

    def _render_idle(self):
        self._clear_labels()
        idle = WordWrapLabel("Play something\u2026")
        self._apply_lyric_label_style(idle, self._css_inactive())
        idle.setAlignment(Qt.AlignLeft)
        self.lyrics_layout.addWidget(idle)
        self.lyric_labels.append(idle)

    def _render_conflict(self, apps: list[str]):
        self._clear_labels()
        apps_text = ", ".join(apps) if apps else "multiple apps"
        warning = WordWrapLabel(
            "Multiple media apps are playing at the same time "
            f"({apps_text}).\n\n"
            "To avoid sync bugs, please play music in only one app."
        )
        self._apply_lyric_label_style(warning, self._css_inactive())
        warning.setAlignment(Qt.AlignLeft)
        self.lyrics_layout.addWidget(warning)
        self.lyric_labels.append(warning)

    # ── Lyrics rendering ─────────────────────────────────────────
    def _render_lyrics(self):
        self._clear_labels()

        if not self.current_lyrics or not self.current_lyrics["lines"]:
            lbl = WordWrapLabel("No lyrics available")
            self._apply_lyric_label_style(lbl, self._css_inactive())
            lbl.setAlignment(Qt.AlignLeft)
            self.lyrics_layout.addWidget(lbl)
            self.lyric_labels.append(lbl)
            return

        for line in self.current_lyrics["lines"]:
            text = line["words"].strip()
            lbl = WordWrapLabel(text if text else " ")
            self._apply_lyric_label_style(lbl, self._css_inactive())
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
    def _highlight_line(self, progress_ms: int, duration_ms: int = 0):
        if not self.current_lyrics or not self.current_lyrics.get("lines"):
            return

        lines = self.current_lyrics["lines"]
        n = len(lines)
        if n == 0:
            return

        if is_synced_lyrics(self.current_lyrics):
            idx = 0
            for i in range(n):
                if lines[i]["time_ms"] <= progress_ms:
                    idx = i
                else:
                    break
        elif duration_ms > 0:
            # Plain lyrics: approximate active line from playback position.
            idx = int((progress_ms / duration_ms) * max(n - 1, 0))
            idx = max(0, min(n - 1, idx))
        else:
            return

        if idx == self.current_line_index:
            return

        self.current_line_index = idx

        for i, lbl in enumerate(self.lyric_labels):
            if i < idx:
                self._apply_lyric_label_style(lbl, self._css_past())
            elif i == idx:
                self._apply_lyric_label_style(lbl, self._css_active())
            else:
                self._apply_lyric_label_style(lbl, self._css_inactive())

        if 0 <= idx < len(self.lyric_labels):
            target = self.lyric_labels[idx]
            y = target.y()
            vh = self.scroll_area.viewport().height()
            self.scroll_area.smooth_scroll_to(max(0, y - vh // 3))

    # ── Pin / always-on-top ──────────────────────────────────────
    def _on_pin_toggled(self, pinned: bool):
        """Pin = lock position. Always-on-top stays on."""
        pass  # drag is disabled inside TitleBar when pinned

    # ── Media controls ───────────────────────────────────────────
    def _media_prev(self):
        self.media.skip_previous()

    def _media_play_pause(self):
        self.media.play_pause()

    def _media_next(self):
        self.media.skip_next()

    # ── Settings ─────────────────────────────────────────────────
    def _stop_settings_geo_anim(self) -> None:
        if self._settings_geo_anim is not None:
            self._settings_geo_anim.stop()
            self._settings_geo_anim.deleteLater()
            self._settings_geo_anim = None

    def _clamp_rect_to_available_screen(self, rect: QRect) -> QRect:
        scr = QApplication.primaryScreen().availableGeometry()
        r = QRect(rect)
        margin = 12
        max_w = max(MIN_WINDOW_SIZE.width(), scr.width() - margin * 2)
        max_h = max(MIN_WINDOW_SIZE.height(), scr.height() - margin * 2)
        if r.width() > max_w:
            r.setWidth(max_w)
        if r.height() > max_h:
            r.setHeight(max_h)
        if r.right() > scr.right() - margin:
            r.moveRight(scr.right() - margin)
        if r.bottom() > scr.bottom() - margin:
            r.moveBottom(scr.bottom() - margin)
        if r.left() < scr.left() + margin:
            r.moveLeft(scr.left() + margin)
        if r.top() < scr.top() + margin:
            r.moveTop(scr.top() + margin)
        return r

    def _rect_for_settings_mode(self, saved: QRect) -> QRect:
        """Grow to at least SETTINGS_WINDOW_MIN if the saved lyrics window was smaller."""
        tw = max(saved.width(), SETTINGS_WINDOW_MIN.width())
        th = max(saved.height(), SETTINGS_WINDOW_MIN.height())
        return self._clamp_rect_to_available_screen(QRect(saved.topLeft(), QSize(tw, th)))

    def _open_settings(self):
        if self._settings_open:
            self._close_settings()
            return
        self._stop_settings_geo_anim()
        self._saved_settings_geometry = QRect(self.geometry())
        self._settings_open = True
        self.settings_panel.sync_from_config()
        self.scroll_area.setVisible(False)
        self.settings_panel.setVisible(True)
        self.bg.set_dim(140)   # translucent dark overlay

        # While settings are visible, do not allow shrinking below a comfortable layout.
        self.setMinimumSize(
            SETTINGS_WINDOW_MIN.width(),
            SETTINGS_WINDOW_MIN.height(),
        )

        target = self._rect_for_settings_mode(self._saved_settings_geometry)
        if target != self.geometry():
            self._settings_geo_anim = QPropertyAnimation(self, b"geometry", self)
            self._settings_geo_anim.setDuration(280)
            self._settings_geo_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._settings_geo_anim.setStartValue(self.geometry())
            self._settings_geo_anim.setEndValue(target)
            self._settings_geo_anim.start()

    def _close_settings(self):
        if not self._settings_open:
            return
        self._stop_settings_geo_anim()
        self._settings_open = False
        self.settings_panel.setVisible(False)
        self.scroll_area.setVisible(True)
        self.bg.set_dim(0)     # restore normal gradient

        self.setMinimumSize(MIN_WINDOW_SIZE.width(), MIN_WINDOW_SIZE.height())
        if self._saved_settings_geometry is not None:
            restored = self._clamp_rect_to_available_screen(self._saved_settings_geometry)
            self.setGeometry(restored)
            self._saved_settings_geometry = None

    def _on_settings_saved(self):
        """Apply config changes after save."""
        from config import set_start_at_login

        set_start_at_login(self.config.get("start_at_login", False))
        self.lyrics_fetcher.set_config(self.config)
        self._lyrics_gen += 1
        self._apply_window_opacity()
        self.scroll_area.set_scroll_duration(
            int(self.config.get("scroll_animation_ms", 400))
        )
        self._apply_lyrics_bottom_margin()
        self._refresh_styles()
        self.lyrics_layout.setSpacing(self.config.get("line_spacing", 3))
        self.current_track_key = None

    def _refresh_styles(self):
        """Re-apply CSS to all visible lyric labels after settings change."""
        for i, lbl in enumerate(self.lyric_labels):
            if i < self.current_line_index:
                self._apply_lyric_label_style(lbl, self._css_past())
            elif i == self.current_line_index:
                self._apply_lyric_label_style(lbl, self._css_active())
            else:
                self._apply_lyric_label_style(lbl, self._css_inactive())

    def _apply_window_opacity(self) -> None:
        opacity = float(self.config.get("window_opacity", 1.0))
        self.setWindowOpacity(max(0.1, min(1.0, opacity)))

    def save_window_geometry(self) -> None:
        if self._settings_open and self._saved_settings_geometry is not None:
            self.config["window_width"] = self._saved_settings_geometry.width()
            self.config["window_height"] = self._saved_settings_geometry.height()
        else:
            self.config["window_width"] = self.width()
            self.config["window_height"] = self.height()
        from config import save_config

        save_config(self.config)

    def _quit(self):
        self.close()

    # ── Lyrics typography (Spotify Mix / Circular when available) ─
    def _primary_lyrics_family(self) -> str:
        return resolve_lyrics_font_family()

    def _make_lyric_font(self) -> QFont:
        return make_lyrics_font(
            self._primary_lyrics_family(),
            int(self.config.get("font_size", 32)),
            bold=True,
        )

    def _apply_lyric_label_style(self, lbl: QLabel, css: str) -> None:
        lbl.setFont(self._make_lyric_font())
        lbl.setStyleSheet(css)

    # ── Style helpers (rgba for correct Qt color parsing) ────────
    def _css_active(self) -> str:
        sp = self.config.get("line_spacing", 3)
        pad = max(2, sp + 2)
        return (
            "color: rgba(255, 255, 255, 1.0);"
            f"padding: {pad}px 4px;"
            "background: transparent;"
        )

    def _css_past(self) -> str:
        sp = self.config.get("line_spacing", 3)
        pad = max(2, sp + 2)
        return (
            "color: rgba(255, 255, 255, 0.55);"
            f"padding: {pad}px 4px;"
            "background: transparent;"
        )

    def _css_inactive(self) -> str:
        sp = self.config.get("line_spacing", 3)
        pad = max(2, sp + 2)
        return (
            "color: rgba(255, 255, 255, 0.32);"
            f"padding: {pad}px 4px;"
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
        self.save_window_geometry()
        event.accept()
        QApplication.quit()
