"""Image Hook Generator — يُولّد صورة hook مربعة 1080×1080 لكل بوست.

Three render modes:
  - signal mode (post.type == "signal") → بطاقة PNL على نمط Binance Futures:
      Hook لاتيني للعلو، رقم PNL ضخم، LONG/SHORT badge، Entry/SL/TP.
  - punchy mode (أي نوع آخر) → خلفية داكنة، 3-5 كلمات HUGE في المنتصف،
      عمود لوني جانبي (أخضر/أحمر/أصفر)، contrast عالٍ جدًا.
  - giveaway mode → خلفية صفراء/ذهبية مع hook واضح "FREE USDT".

Pillow لا يدعم تشكيل النص العربي، لذا كل نص داخل الصورة لاتيني UPPERCASE.
الـ caption العربي يعيش في body البوست.
"""
from __future__ import annotations

import os
import re
import textwrap
from typing import Any

from PIL import Image, ImageDraw, ImageFont

import config
from modules import hook_extractor

CANVAS = 1080
PADDING = 80

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
    "news": {
        "bg_top": (40, 32, 8),
        "bg_bottom": (70, 55, 12),
        "accent": (252, 213, 53),
        "text": (255, 255, 255),
        "subtext": (240, 220, 160),
    },
    "giveaway": {
        "bg_top": (252, 213, 53),
        "bg_bottom": (240, 185, 11),
        "accent": (0, 0, 0),
        "text": (0, 0, 0),
        "subtext": (60, 50, 0),
    },
}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
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
    size = start_size
    while size >= min_size:
        font = _font(size, bold=True)
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
        text = " ".join(str(k) for k in keywords[:5])
    else:
        text = post.get("hook", "")
    text = re.sub(r"[^A-Za-z0-9$ ]", "", text).strip()
    return text.upper() or "CRYPTO"


# ---------------------------------------------------------------------------
# Render: PNL card style (CryptoZhiga inspired)
# ---------------------------------------------------------------------------
def _render_signal_card(post: dict[str, Any]) -> Image.Image:
    direction = "up" if (post.get("side") == "Long") else (
        "down" if post.get("side") == "Short" else _direction_from(post))
    palette = COLORS[direction]
    img = _gradient(palette["bg_top"], palette["bg_bottom"])
    draw = ImageDraw.Draw(img)

    coin = (post.get("coin") or "BTC").upper()
    cashtag = post.get("cashtag") or f"${coin}"
    side = post.get("side") or ("LONG" if direction == "up" else "SHORT")
    side_up = side.upper()
    leverage = post.get("leverage") or 20
    pnl = post.get("pnl_pct")

    # Top: cashtag + USDT Perpetual line
    top_font = _font(58, bold=True)
    draw.text((PADDING, PADDING - 10), f"{cashtag} USDT", font=top_font, fill=palette["text"])
    sub_font = _font(32)
    draw.text((PADDING, PADDING + 60), "Perpetual · Binance Futures",
              font=sub_font, fill=palette["subtext"])

    # Side + leverage badge top-right
    badge_text = f"{side_up}  {leverage}x"
    badge_font = _font(40, bold=True)
    bw = draw.textlength(badge_text, font=badge_font)
    bx = CANVAS - PADDING - bw - 32
    by = PADDING - 4
    draw.rounded_rectangle([(bx, by), (CANVAS - PADDING, by + 70)],
                           radius=14, fill=palette["accent"])
    draw.text((bx + 16, by + 14), badge_text, font=badge_font, fill=(0, 0, 0))

    # Big PNL number — center hero
    pnl_str = (f"+{pnl}%" if pnl is not None and pnl >= 0
               else (f"{pnl}%" if pnl is not None else "BINANCE FUTURES"))
    pnl_font = _font(220, bold=True) if pnl is not None else _font(110, bold=True)
    pnl_w = draw.textlength(pnl_str, font=pnl_font)
    while pnl_w > CANVAS - PADDING * 2 and pnl_font.size > 80:
        pnl_font = _font(pnl_font.size - 10, bold=True)
        pnl_w = draw.textlength(pnl_str, font=pnl_font)
    pnl_y = (CANVAS // 2) - 130
    # shadow
    draw.text(((CANVAS - pnl_w) // 2 + 4, pnl_y + 4), pnl_str,
              font=pnl_font, fill=(0, 0, 0))
    draw.text(((CANVAS - pnl_w) // 2, pnl_y), pnl_str,
              font=pnl_font, fill=palette["accent"])

    # Levels rows: Entry / SL / TP1 / TP2 / TP3
    rows = [
        ("Entry", post.get("entry") or "-"),
        ("SL", post.get("sl") or "-"),
        ("TP1", post.get("tp1") or "-"),
        ("TP2", post.get("tp2") or "-"),
        ("TP3", post.get("tp3") or "-"),
    ]
    # Two columns: labels left, values right
    row_font = _font(40, bold=True)
    label_font = _font(36)
    base_y = pnl_y + pnl_font.size + 50
    col_label_x = PADDING + 20
    col_val_x = CANVAS - PADDING - 20
    line_h = 60
    for i, (label, val) in enumerate(rows):
        y = base_y + i * line_h
        draw.text((col_label_x, y), label, font=label_font, fill=palette["subtext"])
        val_s = str(val)
        vw = draw.textlength(val_s, font=row_font)
        draw.text((col_val_x - vw, y - 4), val_s, font=row_font, fill=palette["text"])

    # Bottom branding (single line, no overlap with TP3)
    brand = "SIGNAL · Binance Square"
    brand_font = _font(28, bold=True)
    bw = draw.textlength(brand, font=brand_font)
    draw.text(((CANVAS - bw) // 2, CANVAS - PADDING + 8), brand,
              font=brand_font, fill=palette["subtext"])

    return img


# ---------------------------------------------------------------------------
# Render: default keyword hook (analysis / debate / news / wrap_up / giveaway)
# ---------------------------------------------------------------------------
def _render_keyword_hook(post: dict[str, Any]) -> Image.Image:
    direction = _direction_from(post)
    palette = COLORS[direction]
    img = _gradient(palette["bg_top"], palette["bg_bottom"])
    draw = ImageDraw.Draw(img)

    cashtag = post.get("cashtag") or f"${post.get('coin', 'BTC')}"
    cashtag_font = _font(64, bold=True)
    draw.text((PADDING, PADDING), cashtag, font=cashtag_font, fill=palette["accent"])

    change = (post.get("source_signal") or {}).get("change_24h")
    if change is not None:
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "•")
        ch_text = f"{arrow} {change:+.2f}%"
        ch_font = _font(48, bold=True)
        w = draw.textlength(ch_text, font=ch_font)
        draw.text((CANVAS - PADDING - w, PADDING + 8), ch_text,
                  font=ch_font, fill=palette["accent"])

    headline = _headline_text(post)
    max_w = CANVAS - PADDING * 2
    font, lines = _shrink_to_fit(draw, headline, max_w)
    line_h = font.size + 12
    total_h = line_h * len(lines)
    y = (CANVAS - total_h) // 2
    for ln in lines:
        w = draw.textlength(ln, font=font)
        x = (CANVAS - w) // 2
        draw.text((x + 3, y + 3), ln, font=font, fill=(0, 0, 0))
        draw.text((x, y), ln, font=font, fill=palette["text"])
        y += line_h

    tag = (post.get("type") or "post").upper()
    tag_font = _font(36, bold=True)
    draw.rectangle(
        [(PADDING, CANVAS - PADDING - 70),
         (PADDING + draw.textlength(tag, font=tag_font) + 60, CANVAS - PADDING - 10)],
        fill=palette["accent"],
    )
    draw.text((PADDING + 30, CANVAS - PADDING - 60), tag, font=tag_font, fill=(0, 0, 0))

    brand = "Binance Square"
    brand_font = _font(34)
    bw = draw.textlength(brand, font=brand_font)
    draw.text((CANVAS - PADDING - bw, CANVAS - PADDING - 50), brand,
              font=brand_font, fill=palette["subtext"])
    return img


def _palette_for(post: dict[str, Any]) -> tuple[str, dict]:
    """Smart mapping: post type + direction → (palette_key, palette).

    أخضر = صعود / Long
    أحمر = هبوط / Short
    أصفر = خبر / giveaway / محايد
    """
    ptype = (post.get("type") or "").lower()
    if ptype == "giveaway":
        return "giveaway", COLORS["giveaway"]
    if ptype == "news":
        return "news", COLORS["news"]
    side = (post.get("side") or "").lower()
    if side == "long":
        return "up", COLORS["up"]
    if side == "short":
        return "down", COLORS["down"]
    d = _direction_from(post)
    return d, COLORS[d]


def _wrap_words(words: list[str], max_per_line: int) -> list[str]:
    """Greedy word-wrap. We tune max_per_line per font fitness check."""
    if not words:
        return []
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        if len(cur) >= max_per_line:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


def _fit_hook(draw: ImageDraw.ImageDraw, hook: str, max_w: int, max_h: int,
              max_lines: int = 2) -> tuple[ImageFont.ImageFont, list[str]]:
    """Find the largest font + line split that fits hook in (max_w x max_h)."""
    words = [w for w in hook.split() if w]
    for size in range(360, 100, -10):
        font = _font(size, bold=True)
        for words_per_line in (1, 2, 3, 4, 5):
            lines = _wrap_words(words, words_per_line)
            if len(lines) > max_lines:
                continue
            widest = max((draw.textlength(ln, font=font) for ln in lines), default=0)
            total_h = len(lines) * int(size * 1.05)
            if widest <= max_w and total_h <= max_h:
                return font, lines
    return _font(100, bold=True), _wrap_words(words, 2)[:max_lines]


def _draw_punchy_hook(draw: ImageDraw.ImageDraw, hook: str,
                     palette: dict, *, top_y: int = 280, bottom_y: int = 820) -> None:
    """يرسم hook في الوسط بأكبر خط ممكن، contrast عالٍ (outline ذكي حسب اللون)."""
    max_w = CANVAS - 2 * PADDING
    max_h = bottom_y - top_y
    font, lines = _fit_hook(draw, hook, max_w, max_h, max_lines=2)
    line_h = int(font.size * 1.05)
    total_h = line_h * len(lines)
    y = top_y + (max_h - total_h) // 2

    # Pick an outline that contrasts with text color.
    text_color = palette["text"]
    text_lum = sum(text_color) / 3
    outline_color = (255, 255, 255) if text_lum < 128 else (0, 0, 0)

    for ln in lines:
        w = draw.textlength(ln, font=font)
        x = (CANVAS - w) // 2
        # 8-direction outline for max contrast
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-3, -3), (3, -3), (-3, 3), (3, 3)):
            draw.text((x + dx, y + dy), ln, font=font, fill=outline_color)
        draw.text((x, y), ln, font=font, fill=text_color)
        y += line_h


def _render_punchy_hook(post: dict[str, Any]) -> Image.Image:
    """النمط الرئيسي لإيقاف الـ scroll: خلفية داكنة + 3-5 كلمات ضخمة."""
    direction, palette = _palette_for(post)

    # Dark background — slightly darker than gradient for max contrast
    img = _gradient(
        tuple(max(0, c - 6) for c in palette["bg_top"]),  # type: ignore[arg-type]
        tuple(max(0, c - 6) for c in palette["bg_bottom"]),  # type: ignore[arg-type]
    )
    draw = ImageDraw.Draw(img)

    # Side color bar (left edge): the visual identifier
    bar_w = 24
    draw.rectangle([(0, 0), (bar_w, CANVAS)], fill=palette["accent"])
    # Same bar on the right for symmetry
    draw.rectangle([(CANVAS - bar_w, 0), (CANVAS, CANVAS)], fill=palette["accent"])

    # Top: cashtag + tiny direction arrow + 24h change
    cashtag = post.get("cashtag") or f"${post.get('coin', 'BTC')}"
    cashtag_font = _font(72, bold=True)
    draw.text((PADDING, PADDING - 10), cashtag.upper(),
              font=cashtag_font, fill=palette["accent"])

    change = (post.get("source_signal") or {}).get("change_24h")
    if change is None:
        change = post.get("change_24h")
    if change is not None:
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "•")
        ch_text = f"{arrow} {change:+.2f}%"
        ch_font = _font(48, bold=True)
        w = draw.textlength(ch_text, font=ch_font)
        draw.text((CANVAS - PADDING - w, PADDING + 8), ch_text,
                  font=ch_font, fill=palette["accent"])

    # Middle: the HOOK (3-5 huge words)
    hook = hook_extractor.extract_hook(post)
    post["image_hook"] = hook  # store for downstream consumers (UI, log)
    _draw_punchy_hook(draw, hook, palette, top_y=260, bottom_y=820)

    # Bottom: type badge + brand
    tag = (post.get("type") or "post").upper()
    tag_font = _font(36, bold=True)
    tag_w = draw.textlength(tag, font=tag_font) + 60
    draw.rounded_rectangle(
        [(PADDING, CANVAS - PADDING - 70),
         (PADDING + tag_w, CANVAS - PADDING - 10)],
        radius=14, fill=palette["accent"],
    )
    # Tag text must contrast with the badge fill (accent).
    accent_lum = sum(palette["accent"]) / 3
    tag_fill = (255, 255, 255) if accent_lum < 128 else (0, 0, 0)
    draw.text((PADDING + 30, CANVAS - PADDING - 60), tag,
              font=tag_font, fill=tag_fill)

    brand = "BINANCE SQUARE"
    brand_font = _font(30, bold=True)
    bw = draw.textlength(brand, font=brand_font)
    draw.text((CANVAS - PADDING - bw, CANVAS - PADDING - 50),
              brand, font=brand_font, fill=palette["subtext"])
    return img


def render_hook_image(post: dict[str, Any], out_dir: str | None = None) -> str:
    """Render and save a 1080x1080 hook image; return the file path.

    Strategy (smart mapping):
      - signal posts → PNL card style (numbers + Long/Short badge + Entry/SL/TP)
      - everything else → punchy hook style (3-5 huge words on dark bg + color bar)
      - color follows direction: green=up, red=down, yellow=news/giveaway/flat
    """
    out_dir = out_dir or config.OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    if post.get("type") == "signal":
        img = _render_signal_card(post)
        direction = "up" if post.get("side") == "Long" else "down"
    else:
        img = _render_punchy_hook(post)
        direction, _ = _palette_for(post)

    fname = f"{post.get('id', 'post')}_{post.get('type', 'post')}_{direction}.png"
    out_path = os.path.join(out_dir, fname)
    img.save(out_path, "PNG", optimize=True)
    return out_path
