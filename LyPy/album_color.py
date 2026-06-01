"""
Spotify-like background colour from album art (reverse-engineered recipe).

Picks a vivid, slightly dark cluster — not a flat average. See Inobtenio / Colorfy
analyses of Spotify's color-lyrics behaviour.
"""

from __future__ import annotations

import colorsys
import io

try:
    from PIL import Image

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def _chroma(r: float, g: float, b: float) -> float:
    """Opponent-space chroma (0–1 RGB inputs)."""
    return (
        (r - g) ** 2 + ((r + g) * 0.5 - b) ** 2
    ) ** 0.5


def _darkness(r: float, g: float, b: float) -> float:
    """HSP brightness → darkness in 0..1."""
    lum = (0.299 * r * r + 0.587 * g * g + 0.114 * b * b) ** 0.5
    return 1.0 - lum


def _spotify_tune_rgb(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Saturation boost + darken (readable white lyrics)."""
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if v < 0.06 or v > 0.97:
        return (90, 90, 96)
    if s < 0.04 and 0.2 < v < 0.85:
        return (90, 90, 96)
    s = min(s * 1.12, 1.0)
    v = min(v * 0.82, 0.92)
    s = max(s, 0.12)
    v = max(v, 0.28)
    cr, cg, cb = colorsys.hsv_to_rgb(h, s, v)
    return (int(cr * 255), int(cg * 255), int(cb * 255))


def spotify_background_rgb(image_bytes: bytes) -> tuple[int, int, int] | None:
    """
    Extract an RGB triplet for the lyrics gradient, Spotify-style.
  """
    if not _HAS_PIL or not image_bytes:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = img.resize((100, 100), Image.LANCZOS)
        w, h = img.size
        total_px = w * h

        # Median-cut palette (~16 clusters) then score like Spotify heuristics.
        q = img.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
        palette = q.getpalette()
        if not palette:
            return None

        best_rgb: tuple[int, int, int] | None = None
        best_score = -1.0

        for count, idx in q.getcolors() or []:
            if idx is None:
                continue
            base = int(idx) * 3
            if base + 2 >= len(palette):
                continue
            r, g, b = palette[base], palette[base + 1], palette[base + 2]
            lum = (r + g + b) / 3
            if lum < 18 or lum > 238:
                continue
            rf, gf, bf = r / 255.0, g / 255.0, b / 255.0

            chroma = _chroma(rf, gf, bf)
            dark = _darkness(rf, gf, bf)
            dom = count / total_px

            # Inobtenio-style score: vivid + somewhat dark hues win over muddy average.
            score = 4.2 * chroma + 1.35 * dark + 0.65 * dom
            if score > best_score:
                best_score = score
                best_rgb = (r, g, b)

        if best_rgb is None:
            pixels = list(img.getdata())
            filtered = [
                p for p in pixels if 30 < sum(p) / 3 < 220
            ] or pixels
            r = sum(p[0] for p in filtered) // len(filtered)
            g = sum(p[1] for p in filtered) // len(filtered)
            b = sum(p[2] for p in filtered) // len(filtered)
            best_rgb = (r, g, b)

        return _spotify_tune_rgb(*best_rgb)
    except Exception:
        return None
