"""Image Hook Generator — produce 1080x1080 hook images with Pillow.

Design rules:
  - Square 1080x1080 (Binance Square renders square images well).
  - Background is a subtle gradient: green for up, red for down, neutral for flat.
  - The hook is rendered LARGE in 3-5 keywords (uppercase).
  - Coin cashtag is rendered prominently in the corner.
  - Direction arrow + 24h change% if available.
  - No external dependencies beyond Pillow.
"""
from __future__ import annotations

import os
import re
import textwrap
from typing import Any

from PIL import Image, ImageDraw, ImageFont

import config

CANVAS = 1080
PADDING = 80

# Color palette — calm, brand-safe, high-contrast.
COLORS = {
    "up": {
        "bg_top": (8, 33, 22),
        "bg_bottom": (15, 79, 47),
        "accent": (14, 203, 129),
        "text": (255, 255, 255),
        "subtext": (180, 230, 200),
    },
    "down": {
        "bg_top": (43, 14, 14),
        "bg_bottom": (94, 25, 25),
        "accent": (246, 70, 93),
        "text": (255, 255, 255),
        "subtext": (255, 200, 200),
    },
    "flat": {
        "bg_top": (20, 22, 28),
        "bg_bottom": (35, 40, 52),
        "accent": (240, 185, 11),
        "text": (255, 255, 255),
        "subtext": (200, 200, 210),
    },
}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Try a few common fonts; fall back to default."""
    candidates = [
        # Prefer DejaVu (preinstalled on most Linux/Ubuntu systems incl. CI).
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


def _gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (CANVAS, CANVAS), top)
    draw = ImageDraw.Draw(img)
    for y in range(CANVAS):
        t = y / (CANVAS - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (CANVAS, y)], fill=(r, g, b))
    return img


def _wrap(text: str, max_chars: int) -> list[str]:
    return textwrap.wrap(text, width=max_chars) or [text]


def _shrink_to_fit(draw: ImageDraw.ImageDraw, text: str, max_w: int,
                   start_size: int = 130, min_size: int = 60) -> tuple[ImageFont.ImageFont, list[str]]:
    """Pick a font size and line wrap so the headline fits the canvas width."""
    size = start_size
    while size >= min_size:
        font = _font(size, bold=True)
        # Try wrapping at increasing widths until lines fit.
        for chars in (10, 12, 14, 16, 18, 22):
            lines = _wrap(text, chars)
            widest = max(draw.textlength(ln, font=font) for ln in lines)
            if widest <= max_w and len(lines) <= 3:
                return font, lines
        size -= 8
    font = _font(min_size, bold=True)
    return font, _wrap(text, 18)


def _direction_from(post: dict[str, Any]) -> str:
    d = (post.get("direction") or "").lower()
    if d in COLORS:
        return d
    return "flat"


def _headline_text(post: dict[str, Any]) -> str:
    keywords = post.get("hook_keywords") or []
    if keywords:
        text = " ".join(keywords[:5])
    else:
        text = post.get("hook", "")
    text = re.sub(r"[^A-Za-z0-9$ ]", "", text).strip()
    return text.upper() or "CRYPTO"


def render_hook_image(post: dict[str, Any], out_dir: str | None = None) -> str:
    """Render and save a 1080x1080 hook image; return the file path."""
    out_dir = out_dir or config.OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    direction = _direction_from(post)
    palette = COLORS[direction]
    img = _gradient(palette["bg_top"], palette["bg_bottom"])
    draw = ImageDraw.Draw(img)

    # Top bar — cashtag + 24h change.
    cashtag = post.get("cashtag") or f"${post.get('coin', 'BTC')}"
    cashtag_font = _font(64, bold=True)
    draw.text((PADDING, PADDING), cashtag, font=cashtag_font, fill=palette["accent"])

    change = post.get("source_signal", {}).get("change_24h")
    if change is not None:
        # Arrow tracks actual price change, not the post's stance.
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "•")
        ch_text = f"{arrow} {change:+.2f}%"
        ch_font = _font(48, bold=True)
        w = draw.textlength(ch_text, font=ch_font)
        draw.text((CANVAS - PADDING - w, PADDING + 8), ch_text,
                  font=ch_font, fill=palette["accent"])

    # Headline — center.
    headline = _headline_text(post)
    max_w = CANVAS - PADDING * 2
    font, lines = _shrink_to_fit(draw, headline, max_w)

    line_h = font.size + 12
    total_h = line_h * len(lines)
    y = (CANVAS - total_h) // 2
    for ln in lines:
        w = draw.textlength(ln, font=font)
        x = (CANVAS - w) // 2
        # subtle shadow
        draw.text((x + 3, y + 3), ln, font=font, fill=(0, 0, 0))
        draw.text((x, y), ln, font=font, fill=palette["text"])
        y += line_h

    # Bottom — type tag + brand.
    tag = (post.get("type") or "post").upper()
    tag_font = _font(36, bold=True)
    draw.rectangle(
        [(PADDING, CANVAS - PADDING - 70), (PADDING + draw.textlength(tag, font=tag_font) + 60, CANVAS - PADDING - 10)],
        fill=palette["accent"],
    )
    draw.text((PADDING + 30, CANVAS - PADDING - 60), tag, font=tag_font, fill=(0, 0, 0))

    brand = "Binance Square"
    brand_font = _font(34)
    bw = draw.textlength(brand, font=brand_font)
    draw.text((CANVAS - PADDING - bw, CANVAS - PADDING - 50), brand,
              font=brand_font, fill=palette["subtext"])

    # Save.
    fname = f"{post.get('id', 'post')}_{direction}.png"
    out_path = os.path.join(out_dir, fname)
    img.save(out_path, "PNG", optimize=True)
    return out_path
