"""
tMinimal flat control icons for LyPy — simple white shapes on transparent PNG.
Run from the LyPy folder: python generate_icons.py
"""

import os

from PIL import Image, ImageDraw

SIZE = 64
os.makedirs("assets", exist_ok=True)

FG = (255, 255, 255, 230)
FG_SOFT = (255, 255, 255, 165)


def _blank() -> Image.Image:
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))


def _save(name: str, img: Image.Image) -> None:
    path = os.path.join("assets", f"{name}.png")
    img.save(path)
    print(f"Saved {path}")


def draw_btn_prev() -> Image.Image:
    img = _blank()
    d = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    bar_w = max(2, int(SIZE * 0.06))
    tri_w = int(SIZE * 0.22)
    tri_h = int(SIZE * 0.32)
    gap = 4
    left = cx - (bar_w + gap + tri_w) // 2
    d.rectangle([left, cy - tri_h // 2, left + bar_w, cy + tri_h // 2], fill=FG)
    tx = left + bar_w + gap
    d.polygon(
        [(tx, cy - tri_h // 2), (tx + tri_w, cy), (tx, cy + tri_h // 2)],
        fill=FG,
    )
    return img


def draw_btn_next() -> Image.Image:
    img = _blank()
    d = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    bar_w = max(2, int(SIZE * 0.06))
    tri_w = int(SIZE * 0.22)
    tri_h = int(SIZE * 0.32)
    gap = 4
    right = cx + (bar_w + gap + tri_w) // 2
    d.rectangle([right - bar_w, cy - tri_h // 2, right, cy + tri_h // 2], fill=FG)
    tx = right - bar_w - gap - tri_w
    d.polygon(
        [(tx + tri_w, cy - tri_h // 2), (tx, cy), (tx + tri_w, cy + tri_h // 2)],
        fill=FG,
    )
    return img


def draw_btn_play() -> Image.Image:
    img = _blank()
    d = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    w = int(SIZE * 0.26)
    h = int(SIZE * 0.32)
    x = cx - w // 2 + int(SIZE * 0.02)
    d.polygon([(x, cy - h // 2), (x + w, cy), (x, cy + h // 2)], fill=FG)
    return img


def draw_btn_pause() -> Image.Image:
    img = _blank()
    d = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    bw = max(3, int(SIZE * 0.09))
    bh = int(SIZE * 0.32)
    gap = int(SIZE * 0.1)
    lx = cx - gap // 2 - bw
    rx = cx + gap // 2
    d.rounded_rectangle([lx, cy - bh // 2, lx + bw, cy + bh // 2], radius=2, fill=FG)
    d.rounded_rectangle([rx, cy - bh // 2, rx + bw, cy + bh // 2], radius=2, fill=FG)
    return img


def draw_btn_pin() -> Image.Image:
    """Small map pin, tilted (movable)."""
    img = _blank()
    d = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    r = int(SIZE * 0.1)
    hx = cx - int(SIZE * 0.04)
    hy = cy - int(SIZE * 0.1)
    d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=FG)
    d.polygon(
        [
            (hx, hy + r),
            (cx + int(SIZE * 0.1), cy + int(SIZE * 0.22)),
            (hx - int(SIZE * 0.06), cy + int(SIZE * 0.12)),
        ],
        fill=FG,
    )
    return img


def draw_btn_pin_locked() -> Image.Image:
    """Straight pin + anchor bar."""
    img = _blank()
    d = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    r = int(SIZE * 0.1)
    hx, hy = cx, cy - int(SIZE * 0.1)
    d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=FG)
    tip_y = cy + int(SIZE * 0.2)
    d.polygon(
        [
            (hx - int(SIZE * 0.05), hy + r),
            (hx + int(SIZE * 0.05), hy + r),
            (hx, tip_y),
        ],
        fill=FG,
    )
    bw = int(SIZE * 0.18)
    by = tip_y - 3
    d.rectangle([hx - bw // 2, by, hx + bw // 2, by + max(2, int(SIZE * 0.035))], fill=FG)
    return img


def draw_btn_settings() -> Image.Image:
    """Three horizontal sliders with knobs — minimal settings cue."""
    img = _blank()
    d = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2
    w = int(SIZE * 0.38)
    track_h = max(2, int(SIZE * 0.028))
    x0 = cx - w // 2
    positions = [(0.18, 0.72), (0.55, 0.45), (0.32, 0.58)]
    ys = [cy - int(SIZE * 0.1), cy, cy + int(SIZE * 0.1)]
    for y, (start_f, end_f) in zip(ys, positions):
        xa = x0 + int(w * min(start_f, end_f))
        xb = x0 + int(w * max(start_f, end_f))
        if xb <= xa:
            xb = xa + 4
        d.rectangle([xa, y - track_h // 2, xb, y + track_h // 2], fill=FG_SOFT)
        kx = xa + (xb - xa) // 2
        kr = int(SIZE * 0.05)
        d.ellipse([kx - kr, y - kr, kx + kr, y + kr], fill=FG)
    return img


def draw_app_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 28
    d.rounded_rectangle(
        [pad, pad, 256 - pad, 256 - pad],
        radius=48,
        fill=(30, 215, 96, 255),
    )
    d.ellipse([88, 72, 128, 112], fill=(20, 20, 20, 255))
    d.rectangle([118, 88, 132, 200], fill=(20, 20, 20, 255))
    d.ellipse([118, 176, 188, 220], fill=(20, 20, 20, 255))
    return img


if __name__ == "__main__":
    _save("btn_prev", draw_btn_prev())
    _save("btn_next", draw_btn_next())
    _save("btn_play", draw_btn_play())
    _save("btn_pause", draw_btn_pause())
    _save("btn_pin", draw_btn_pin())
    _save("btn_pin_locked", draw_btn_pin_locked())
    _save("btn_settings", draw_btn_settings())
    _save("app_icon", draw_app_icon())
    print("Done.")
