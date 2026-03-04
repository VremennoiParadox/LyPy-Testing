"""
Generates plain white symbol PNGs for the LyPy media controls.
Run once: python generate_icons.py
Produces assets/btn_prev.png, assets/btn_play.png, assets/btn_next.png,
         assets/btn_pause.png
"""

import os
from PIL import Image, ImageDraw

SIZE = 64   # px (displayed at ~16x16 via Qt scaling inside a glass button)
os.makedirs("assets", exist_ok=True)


def _blank() -> tuple[Image.Image, ImageDraw.Draw]:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _draw_prev() -> Image.Image:
    """|◄  bar + left-pointing triangle"""
    img, d = _blank()
    cx = cy = SIZE / 2
    ic = (255, 255, 255, 245)

    bw, bh = int(SIZE * 0.09), int(SIZE * 0.46)
    bx = int(cx - SIZE * 0.30)
    by = int(cy - bh / 2)
    d.rectangle([bx, by, bx + bw, by + bh], fill=ic)

    tw, th = int(SIZE * 0.28), int(SIZE * 0.44)
    tx = int(cx + SIZE * 0.00)
    d.polygon([
        (tx,       int(cy)),
        (tx + tw,  int(cy - th / 2)),
        (tx + tw,  int(cy + th / 2)),
    ], fill=ic)
    return img


def _draw_play() -> Image.Image:
    """▶  right-pointing triangle"""
    img, d = _blank()
    cx = cy = SIZE / 2
    ic = (255, 255, 255, 245)

    tw, th = int(SIZE * 0.38), int(SIZE * 0.46)
    tx = int(cx - tw * 0.45)
    d.polygon([
        (tx,       int(cy - th / 2)),
        (tx,       int(cy + th / 2)),
        (tx + tw,  int(cy)),
    ], fill=ic)
    return img


def _draw_pause() -> Image.Image:
    """⏸  two vertical bars"""
    img, d = _blank()
    cx = cy = SIZE / 2
    ic = (255, 255, 255, 245)

    bw = int(SIZE * 0.13)
    bh = int(SIZE * 0.46)
    gap = int(SIZE * 0.10)
    by  = int(cy - bh / 2)
    lx  = int(cx - gap / 2 - bw)
    d.rectangle([lx, by, lx + bw, by + bh], fill=ic)
    rx = int(cx + gap / 2)
    d.rectangle([rx, by, rx + bw, by + bh], fill=ic)
    return img


def _draw_next() -> Image.Image:
    """►|  right-pointing triangle + bar"""
    img, d = _blank()
    cx = cy = SIZE / 2
    ic = (255, 255, 255, 245)

    tw, th = int(SIZE * 0.28), int(SIZE * 0.44)
    tx = int(cx - SIZE * 0.28)
    d.polygon([
        (tx,       int(cy - th / 2)),
        (tx,       int(cy + th / 2)),
        (tx + tw,  int(cy)),
    ], fill=ic)

    bw, bh = int(SIZE * 0.09), int(SIZE * 0.46)
    bx = int(cx + SIZE * 0.21)
    by = int(cy - bh / 2)
    d.rectangle([bx, by, bx + bw, by + bh], fill=ic)
    return img


icons = {
    "btn_prev":  _draw_prev,
    "btn_play":  _draw_play,
    "btn_pause": _draw_pause,
    "btn_next":  _draw_next,
}

for name, fn in icons.items():
    img = fn()
    path = os.path.join("assets", f"{name}.png")
    img.save(path)
    print(f"Saved {path}")

print("Done.")

    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _make_glass_base() -> Image.Image:
    """Circular glass body with radial gradient + specular shine."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    cx = cy = SIZE / 2
    r  = SIZE / 2 - 2          # radius leaving 2px margin

    # ── radial gradient body ─────────────────────────────────────────────
    # centre: bright blue-white; edge: deeper saturated blue
    center_col = (210, 218, 255, 210)   # light blue-white, semi-opaque
    edge_col   = ( 90, 110, 210, 175)   # deeper blue, slightly more opaque

    body = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    for px in range(SIZE):
        for py in range(SIZE):
            dx, dy = px - cx, py - cy
            dist = math.sqrt(dx*dx + dy*dy)
            if dist <= r:
                t = dist / r                # 0 at centre, 1 at edge
                col = _blend(center_col, edge_col, t ** 0.6)
                body.putpixel((px, py), tuple(col))

    # ── top-left specular shine ──────────────────────────────────────────
    shine = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shine)
    # An ellipse in the upper-left quadrant
    sw, sh = int(r * 1.1), int(r * 0.7)
    sx = int(cx - sw * 0.55)
    sy = int(cy - r * 0.85)
    sd.ellipse([sx, sy, sx + sw, sy + sh], fill=(255, 255, 255, 175))
    shine = shine.filter(ImageFilter.GaussianBlur(radius=7))

    # ── inner dark ring near edge (depth) ───────────────────────────────
    inner = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    id_ = ImageDraw.Draw(inner)
    ri = int(r)
    cm = int(cx)
    id_.ellipse([cm - ri, cm - ri, cm + ri, cm + ri],
                outline=(0, 0, 40, 55), width=2)
    inner = inner.filter(ImageFilter.GaussianBlur(radius=1))

    # ── compose body + shine + inner ring ───────────────────────────────
    combined = Image.alpha_composite(body, shine)
    combined = Image.alpha_composite(combined, inner)

    # ── rim highlight (thin white border) ────────────────────────────────
    rim = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    rd.ellipse([2, 2, SIZE - 3, SIZE - 3],
               outline=(255, 255, 255, 105), width=1)
    combined = Image.alpha_composite(combined, rim)

    img = Image.alpha_composite(img, combined)
    return img


def _draw_prev(img: Image.Image) -> Image.Image:
    """⏮  vertical bar on left  +  left-pointing filled triangle."""
    d = ImageDraw.Draw(img)
    cx = cy = SIZE / 2
    ic = (255, 255, 255, 235)

    # Vertical bar
    bw, bh = 4, int(SIZE * 0.35)
    bx = int(cx - SIZE * 0.22)
    by = int(cy - bh / 2)
    d.rectangle([bx, by, bx + bw, by + bh], fill=ic)

    # Triangle pointing left
    tw = int(SIZE * 0.22)
    th = int(SIZE * 0.34)
    tx = int(cx + SIZE * 0.04)
    d.polygon([
        (tx,       int(cy)),
        (tx + tw,  int(cy - th / 2)),
        (tx + tw,  int(cy + th / 2)),
    ], fill=ic)
    return img


def _draw_play(img: Image.Image) -> Image.Image:
    """▶  right-pointing filled triangle."""
    d = ImageDraw.Draw(img)
    cx = cy = SIZE / 2
    ic = (255, 255, 255, 235)

    tw = int(SIZE * 0.30)
    th = int(SIZE * 0.38)
    tx = int(cx - tw * 0.45)   # slight left offset so triangle looks centred
    d.polygon([
        (tx,       int(cy - th / 2)),
        (tx,       int(cy + th / 2)),
        (tx + tw,  int(cy)),
    ], fill=ic)
    return img


def _draw_pause(img: Image.Image) -> Image.Image:
    """⏸  two vertical bars."""
    d = ImageDraw.Draw(img)
    cx = cy = SIZE / 2
    ic = (255, 255, 255, 235)

    bw = int(SIZE * 0.10)
    bh = int(SIZE * 0.36)
    gap = int(SIZE * 0.09)
    by  = int(cy - bh / 2)
    # left bar
    lx = int(cx - gap / 2 - bw)
    d.rectangle([lx, by, lx + bw, by + bh], fill=ic)
    # right bar
    rx = int(cx + gap / 2)
    d.rectangle([rx, by, rx + bw, by + bh], fill=ic)
    return img


def _draw_next(img: Image.Image) -> Image.Image:
    """⏭  right-pointing filled triangle  +  vertical bar on right."""
    d = ImageDraw.Draw(img)
    cx = cy = SIZE / 2
    ic = (255, 255, 255, 235)

    # Triangle pointing right
    tw = int(SIZE * 0.22)
    th = int(SIZE * 0.34)
    tx = int(cx - SIZE * 0.26)
    d.polygon([
        (tx,       int(cy - th / 2)),
        (tx,       int(cy + th / 2)),
        (tx + tw,  int(cy)),
    ], fill=ic)

    # Vertical bar
    bw, bh = 4, int(SIZE * 0.35)
    bx = int(cx + SIZE * 0.18)
    by = int(cy - bh / 2)
    d.rectangle([bx, by, bx + bw, by + bh], fill=ic)
    return img


# ── generate ─────────────────────────────────────────────────────────────

icons = {
    "btn_prev":  _draw_prev,
    "btn_play":  _draw_play,
    "btn_pause": _draw_pause,
    "btn_next":  _draw_next,
}

for name, draw_fn in icons.items():
    base = _make_glass_base()
    result = draw_fn(base)
    path = os.path.join("assets", f"{name}.png")
    result.save(path)
    print(f"Saved {path}")

print("Done.")
