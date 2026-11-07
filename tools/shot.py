#!/usr/bin/env python3
"""Render the screen to a PNG (for the README).

    python3 tools/shot.py shots/when-tui.png

Draws block glyphs as rectangles so the half-block clock face is reproduced
faithfully, which a text renderer would not do.
"""
import sys
from datetime import date, datetime

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, "/Users/sebastian-heisenberg/deepseek-harness/computer/github/when-tui-redesign")
import when  # noqa: E402

CW, CH = 14, 28
FONT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 23)

# block-element glyphs rendered as rectangles instead of font glyphs
BLOCK = {
    "█": (1, 1), "▀": (1, 0), "▄": (0, 1), "▌": (0, 0),
    "▐": (0, 0), "▖": (0, 0), "▗": (0, 0), "▘": (0, 0), "▙": (1, 1),
    "▛": (1, 1), "▜": (1, 1), "▟": (1, 1), "▁": (0, 0), "▂": (0, 0),
    "▃": (0, 0), "▅": (0, 0), "▆": (0, 0), "▇": (1, 0),
}


def draw_cell(d, x, y, ch, fg, bg):
    px, py = x * CW, y * CH
    d.rectangle([px, py, px + CW - 1, py + CH - 1], fill=bg)
    if ch == " ":
        return
    if ch == "▀":
        d.rectangle([px, py, px + CW - 1, py + CH // 2 - 1], fill=fg)
    elif ch == "▄":
        d.rectangle([px, py + CH // 2, px + CW - 1, py + CH - 1], fill=fg)
    elif ch == "█":
        d.rectangle([px, py, px + CW - 1, py + CH - 1], fill=fg)
    else:
        d.text((px, py + 1), ch, font=FONT, fill=fg)


def render(out, now=None, year=None, month=None, today=None):
    now = now or datetime.now()
    today = today or now.date()
    year = year or now.year
    month = month or now.month
    canvas = when.build_screen(now, year, month, today, when.get_scheme(now))
    img = Image.new("RGB", (canvas.w * CW, canvas.h * CH), "white")
    d = ImageDraw.Draw(img)
    for y in range(canvas.h):
        for x in range(canvas.w):
            draw_cell(d, x, y, *canvas.cells[y][x])
    img.save(out)
    print(f"  wrote {out}  {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/when-preview.png"
    render(out, now=datetime(2025, 11, 18, 3, 59, 30),
           year=2025, month=11, today=date(2025, 11, 18))
