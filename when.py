#!/usr/bin/env python3
"""when-tui — a terminal replica of the Nintendo DS menu screen.

A windowed clock and calendar drawn entirely in characters: title bar, inset
panes, analog face with a day-progress arc, a 5x7 pixel font, lunar date and
solar term, clickable calendar, theme keys and an opening animation.

    ./when.py
"""

from __future__ import annotations

import calendar as cal_mod
import math
import os
import pathlib
import sys
from datetime import date, datetime

# ── run from a clone without activating anything ────────────────────────
_venv_dir = pathlib.Path(__file__).resolve().with_name(".venv")
_venv_py = _venv_dir / "bin" / "python"
# sys.prefix is the venv root when running inside one — comparing sys.executable
# does not work because the venv's python is usually a symlink to the system one.
if _venv_py.exists() and pathlib.Path(sys.prefix) != _venv_dir:
    os.execv(str(_venv_py), [str(_venv_py), *sys.argv])

try:
    from rich.style import Style
    from rich.text import Text
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual import events
    from textual.widget import Widget
except ModuleNotFoundError:
    sys.exit(
        "when-tui needs Textual.\n"
        "\n"
        "  python3 -m venv .venv\n"
        "  .venv/bin/pip install -r requirements.txt\n"
        "  ./when.py\n"
        "\n"
        "(or just: uv run when.py)"
    )

try:
    from lunardate import LunarDate
except ModuleNotFoundError:              # lunar line is optional, not fatal
    LunarDate = None

# ═══════════════════════════════════════════════════════════════════════
# Geometry
# ═══════════════════════════════════════════════════════════════════════

W, H = 96, 36
ASPECT_Y = 2.0

ROW_TITLE = 1
ROW_SPLIT = 2
ROW_STATUS = H - 3
COL_SPLIT = 52

# ═══════════════════════════════════════════════════════════════════════
# Palette
# ═══════════════════════════════════════════════════════════════════════

PALETTES = {
    "morning": dict(
        chrome="#2F3A4E", chrome_fg="#E9EEF7", chrome_edge="#1D2534",
        paper="#FDFCF7", grid="#E4E2D6", ink="#3A3F4A", dim="#8D94A0",
        face="#FFFFFF", tick="#9AA1AE",
        hour="#2A2F3A", minute="#4A5260", second="#D4613C",
        sun="#FFC9DA", sat="#C2D6FF", head="#39445A", accent="#3F6FD8",
        bevel_l="#FFFFFF", bevel_d="#CFCABB", arc="#E8A33C", glow="#FFD98A",
        shadow="#E8E4D6",
    ),
    "afternoon": dict(
        chrome="#31405A", chrome_fg="#E9EFFA", chrome_edge="#1E2738",
        paper="#FAFCFF", grid="#DDE3EE", ink="#37404E", dim="#8894A6",
        face="#FFFFFF", tick="#8E9AAC",
        hour="#262D3A", minute="#48525F", second="#D2436A",
        sun="#FFC9DA", sat="#C2D6FF", head="#39445A", accent="#2F6FD4",
        bevel_l="#FFFFFF", bevel_d="#C9D2E0", arc="#3F8FD8", glow="#8FD0FF",
        shadow="#E2E7F0",
    ),
    "evening": dict(
        chrome="#3E3548", chrome_fg="#F2EAF2", chrome_edge="#241F2B",
        paper="#FDF8F4", grid="#E8DFD6", ink="#463D36", dim="#9C8C7E",
        face="#FFFFFF", tick="#94816F",
        hour="#33291F", minute="#54463A", second="#C2503A",
        sun="#FFC9C2", sat="#C8CEEA", head="#463A30", accent="#B96A32",
        bevel_l="#FFFFFF", bevel_d="#D6C6B4", arc="#D07A3A", glow="#FFC58A",
        shadow="#EAE2D8",
    ),
    "night": dict(
        chrome="#252A40", chrome_fg="#E6E9F8", chrome_edge="#151827",
        paper="#F7F8FD", grid="#DCDEEF", ink="#343850", dim="#8088A2",
        face="#FFFFFF", tick="#7E86A0",
        hour="#22263A", minute="#464C64", second="#6E6EDC",
        sun="#FFC9DA", sat="#C2D6FF", head="#2F3652", accent="#5566D8",
        bevel_l="#FFFFFF", bevel_d="#C6CADF", arc="#7A86E8", glow="#B8BFFF",
        shadow="#E4E6F4",
    ),
}
THEME_ORDER = ("morning", "afternoon", "evening", "night")


def get_time_of_day(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 20:
        return "evening"
    return "night"


def get_scheme(now: datetime | None = None, forced: str | None = None) -> dict:
    name = forced or get_time_of_day((now or datetime.now()).hour)
    return PALETTES[name]


# ═══════════════════════════════════════════════════════════════════════
# Lunar date and solar terms (农历 / 节气)
# ═══════════════════════════════════════════════════════════════════════

LUNAR_MONTHS = "正二三四五六七八九十冬腊"
LUNAR_DAYS = (
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
)

# solar terms indexed by the 15° bucket of the sun's apparent longitude
TERMS = (
    "春分", "清明", "谷雨", "立夏", "小满", "芒种", "夏至", "小暑",
    "大暑", "立秋", "处暑", "白露", "秋分", "寒露", "霜降", "立冬",
    "小雪", "大雪", "冬至", "小寒", "大寒", "立春", "雨水", "惊蛰",
)


def _solar_longitude(d: date) -> float:
    """Apparent ecliptic longitude of the sun, in degrees (low precision)."""
    jd = d.toordinal() + 1721424.5 + 0.5          # noon UT
    n = jd - 2451545.0
    L = 280.460 + 0.9856474 * n
    g = math.radians(357.528 + 0.9856003 * n)
    return (L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360.0


def solar_term(d: date) -> tuple[str, date]:
    """Return (current term, the day it started)."""
    lam = _solar_longitude(d)
    bucket = int(lam // 15)
    cur = d
    for _ in range(20):
        cur = date.fromordinal(cur.toordinal() - 1)
        if int(_solar_longitude(cur) // 15) != bucket:
            cur = date.fromordinal(cur.toordinal() + 1)
            break
    return TERMS[bucket % 24], cur


def lunar_text(d: date) -> str:
    if LunarDate is None:
        return ""
    try:
        ld = LunarDate.from_solar_date(d.year, d.month, d.day)
    except Exception:
        return ""
    month = ("闰" if ld.isLeapMonth else "") + LUNAR_MONTHS[ld.month - 1] + "月"
    return month + LUNAR_DAYS[ld.day - 1]


def dwidth(s: str) -> int:
    """Display width: CJK glyphs take two cells."""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in s)


# ═══════════════════════════════════════════════════════════════════════
# 5x7 pixel font
# ═══════════════════════════════════════════════════════════════════════

FONT: dict[str, list[str]] = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
}


def font_width(text: str, scale: int = 1, gap: int = 1) -> int:
    return len(text) * (5 * scale + gap) - gap


def draw_font(c: "Canvas", x: int, y: int, text: str, fg: str, bg: str,
              scale: int = 1, gap: int = 1) -> None:
    cx = x
    for ch in text:
        glyph = FONT.get(ch, FONT[" "])
        for ry, row in enumerate(glyph):
            for rx, bit in enumerate(row):
                if bit == "1":
                    for sy in range(scale):
                        for sx in range(scale):
                            c.put(cx + rx * scale + sx, y + ry * scale + sy, "█", fg, bg)
        cx += 5 * scale + gap


# ═══════════════════════════════════════════════════════════════════════
# Canvas
# ═══════════════════════════════════════════════════════════════════════


class Canvas:
    def __init__(self, w: int, h: int, bg: str) -> None:
        self.w, self.h = w, h
        self.cells: list[list[tuple[str, str, str]]] = [
            [(" ", bg, bg) for _ in range(w)] for _ in range(h)
        ]

    def put(self, x: int, y: int, ch: str, fg: str, bg: str) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.cells[y][x] = (ch[0] if ch else " ", fg, bg)

    def fill(self, x: int, y: int, w: int, h: int, ch: str, fg: str, bg: str) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.put(xx, yy, ch, fg, bg)

    def text(self, x: int, y: int, s: str, fg: str, bg: str) -> None:
        for i, ch in enumerate(s):
            self.put(x + i, y, ch, fg, bg)

    def wide(self, x: int, y: int, s: str, fg: str, bg: str) -> None:
        """Write a string that may contain CJK glyphs, two cells per glyph."""
        cx = x
        for ch in s:
            if ord(ch) > 0x2E7F:
                self.put(cx, y, ch, fg, bg)
                self.put(cx + 1, y, "\x00", fg, bg)   # continuation cell
                cx += 2
            else:
                self.put(cx, y, ch, fg, bg)
                cx += 1

    def hline(self, x: int, y: int, w: int, ch: str, fg: str, bg: str) -> None:
        for i in range(w):
            self.put(x + i, y, ch, fg, bg)

    def vline(self, x: int, y: int, h: int, ch: str, fg: str, bg: str) -> None:
        for i in range(h):
            self.put(x, y + i, ch, fg, bg)

    def frame(self, x: int, y: int, w: int, h: int, fg: str, bg: str,
              double: bool = True) -> None:
        if double:
            tl, tr, bl, br, hz, vt = "╔", "╗", "╚", "╝", "═", "║"
        else:
            tl, tr, bl, br, hz, vt = "┌", "┐", "└", "┘", "─", "│"
        self.put(x, y, tl, fg, bg)
        self.put(x + w - 1, y, tr, fg, bg)
        self.put(x, y + h - 1, bl, fg, bg)
        self.put(x + w - 1, y + h - 1, br, fg, bg)
        self.hline(x + 1, y, w - 2, hz, fg, bg)
        self.hline(x + 1, y + h - 1, w - 2, hz, fg, bg)
        self.vline(x, y + 1, h - 2, vt, fg, bg)
        self.vline(x + w - 1, y + 1, h - 2, vt, fg, bg)

    def mask_outside(self, x: int, y: int, w: int, h: int, bg: str) -> None:
        for yy in range(self.h):
            for xx in range(self.w):
                if not (x <= xx < x + w and y <= yy < y + h):
                    self.cells[yy][xx] = (" ", bg, bg)

    def to_text(self) -> Text:
        t = Text()
        for y in range(self.h):
            run_fg = run_bg = None
            buf: list[str] = []
            for x in range(self.w):
                ch, fg, bg = self.cells[y][x]
                if ch == "\x00":
                    continue
                if (fg, bg) != (run_fg, run_bg) and buf:
                    t.append("".join(buf), style=Style(color=run_fg, bgcolor=run_bg))
                    buf = []
                run_fg, run_bg = fg, bg
                buf.append(ch)
            if buf:
                t.append("".join(buf), style=Style(color=run_fg, bgcolor=run_bg))
            if y < self.h - 1:
                t.append("\n")
        return t


# ═══════════════════════════════════════════════════════════════════════
# Pixel layer
# ═══════════════════════════════════════════════════════════════════════


class PixelCanvas:
    def __init__(self, w: int, h: int, bg: str) -> None:
        self.w, self.h = w, h
        self.grid = [[bg for _ in range(w)] for _ in range(h)]

    def px(self, x: int, y: int, col: str) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.grid[y][x] = col

    def line(self, x0: float, y0: float, x1: float, y1: float, col: str,
             thick: int = 1) -> None:
        pts = bresenham(round(x0), round(y0), round(x1), round(y1))
        if thick <= 1:
            for x, y in pts:
                self.px(x, y, col)
            return
        for i, (x, y) in enumerate(pts):
            self.px(x, y, col)
            if i == 0:
                continue
            nx, ny = pts[i - 1]
            if abs(x - nx) >= abs(y - ny):
                self.px(x, y + 1, col)
            else:
                self.px(x + 1, y, col)


def composite(c: Canvas, x0: int, y0: int, pc: PixelCanvas) -> None:
    for cy in range(pc.h // 2):
        for cx in range(pc.w):
            top = pc.grid[cy * 2][cx]
            bot = pc.grid[cy * 2 + 1][cx]
            if top == bot:
                c.put(x0 + cx, y0 + cy, " ", top, top)
            else:
                c.put(x0 + cx, y0 + cy, "▀", top, bot)


def bresenham(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    pts = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    cx, cy = x0, y0
    while True:
        pts.append((cx, cy))
        if (cx, cy) == (x1, y1):
            return pts
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy


# ═══════════════════════════════════════════════════════════════════════
# Window chrome
# ═══════════════════════════════════════════════════════════════════════


def bevel(c: Canvas, x: int, y: int, w: int, h: int, s: dict) -> None:
    c.hline(x, y, w, "▀", s["bevel_l"], s["paper"])
    c.vline(x, y + 1, h - 1, "▌", s["bevel_l"], s["paper"])
    c.hline(x + 1, y + h - 1, w - 1, "▄", s["bevel_d"], s["paper"])
    c.vline(x + w - 1, y + 1, h - 2, "▐", s["bevel_d"], s["paper"])


def draw_window(c: Canvas, s: dict, now: datetime, theme_label: str) -> None:
    c.fill(0, 0, W, H, " ", s["ink"], s["paper"])
    c.frame(0, 0, W, H, s["chrome_edge"], s["paper"])

    c.fill(1, ROW_TITLE, W - 2, 1, " ", s["chrome_fg"], s["chrome"])
    c.text(2, ROW_TITLE, "░▒▓", s["glow"], s["chrome"])
    c.text(6, ROW_TITLE, " WHEN-TUI ", s["chrome_fg"], s["chrome"])
    c.text(16, ROW_TITLE, "▓▒░", s["glow"], s["chrome"])
    tag = f" {theme_label.upper()} "
    c.text(22, ROW_TITLE, tag, s["glow"], s["chrome"])

    stamp = now.strftime("%Y-%m-%d   %H:%M:%S")
    c.text(W - 3 - len(stamp), ROW_TITLE, stamp, s["chrome_fg"], s["chrome"])

    c.hline(1, ROW_TITLE + 1, W - 2, "─", s["accent"], s["chrome"])

    c.hline(1, ROW_SPLIT, W - 2, "═", s["chrome_edge"], s["paper"])
    c.put(0, ROW_SPLIT, "╠", s["chrome_edge"], s["paper"])
    c.put(W - 1, ROW_SPLIT, "╣", s["chrome_edge"], s["paper"])
    c.put(COL_SPLIT, ROW_SPLIT, "╦", s["chrome_edge"], s["paper"])
    c.vline(COL_SPLIT, ROW_SPLIT + 1, ROW_STATUS - ROW_SPLIT - 1,
            "║", s["chrome_edge"], s["paper"])

    top = ROW_SPLIT + 1
    ph = ROW_STATUS - ROW_SPLIT - 1
    bevel(c, 1, top, COL_SPLIT - 1, ph, s)
    bevel(c, COL_SPLIT + 1, top, W - COL_SPLIT - 2, ph, s)

    c.hline(1, ROW_STATUS, W - 2, "═", s["chrome_edge"], s["paper"])
    c.put(0, ROW_STATUS, "╠", s["chrome_edge"], s["paper"])
    c.put(W - 1, ROW_STATUS, "╣", s["chrome_edge"], s["paper"])
    c.put(COL_SPLIT, ROW_STATUS, "╩", s["chrome_edge"], s["paper"])
    c.fill(1, ROW_STATUS + 1, W - 2, 1, " ", s["chrome_fg"], s["chrome"])

    segs = [("← →", "month"), ("T", "today"), ("1-4", "theme"), ("Q", "quit")]
    x = 3
    for i, (key, label) in enumerate(segs):
        if i:
            c.text(x - 2, ROW_STATUS + 1, "│", s["chrome_edge"], s["chrome"])
        c.text(x, ROW_STATUS + 1, key, s["glow"], s["chrome"])
        c.text(x + len(key) + 1, ROW_STATUS + 1, label, s["chrome_fg"], s["chrome"])
        x += len(key) + len(label) + 5

    hint = now.strftime("%a %d %b").upper()
    c.text(W - 3 - len(hint), ROW_STATUS + 1, hint, s["chrome_fg"], s["chrome"])


# ═══════════════════════════════════════════════════════════════════════
# Clock pane
# ═══════════════════════════════════════════════════════════════════════


def draw_clock(c: Canvas, now: datetime, s: dict) -> list:
    hits = []
    top = ROW_SPLIT + 2
    bottom = ROW_STATUS - 3
    pane_w = COL_SPLIT - 3
    x0 = 2

    day = 6 <= now.hour < 18
    cap = "◇ CLOCK ◇" if day else "☾ CLOCK ☾"
    c.text(x0 + (pane_w - len(cap)) // 2, ROW_SPLIT + 1, cap,
           s["arc"] if day else s["glow"], s["paper"])

    # smooth seconds: fractional, so the hand sweeps instead of ticking
    seconds = now.second + now.microsecond / 1_000_000

    stamp = now.strftime("%H:%M")
    dw = font_width(stamp, 1, gap=1)
    digit_y = bottom - 7
    draw_font(c, x0 + (pane_w - dw) // 2, digit_y, stamp, s["hour"], s["paper"])

    line = now.strftime("%A · %d %B %Y").upper()
    c.text(x0 + (pane_w - len(line)) // 2, bottom, line, s["dim"], s["paper"])

    lunar = lunar_text(now.date())
    if lunar:
        term, _ = solar_term(now.date())
        sub = f"农历{lunar} · {term}"
        c.wide(x0 + (pane_w - dwidth(sub)) // 2, bottom + 1, sub, s["dim"], s["paper"])

    face_rows = digit_y - top - 4
    pw = pane_w - 2
    ph = face_rows * 2
    pc = PixelCanvas(pw, ph, s["paper"])
    cx, cy = (pw - 1) / 2, (ph - 1) / 2
    r = min(cx, cy) - 1

    for k in range(720):
        ang = math.radians(k / 2)
        pc.px(round(cx + r * math.sin(ang)), round(cy - r * math.cos(ang)), s["tick"])

    frac = (now.hour * 3600 + now.minute * 60 + seconds) / 86400
    for k in range(int(720 * frac)):
        ang = math.radians(k / 2)
        ax, ay = round(cx + r * math.sin(ang)), round(cy - r * math.cos(ang))
        pc.px(ax, ay, s["arc"])
        pc.px(ax + 1, ay, s["arc"])

    for k in range(12):
        ang = math.radians(k * 30)
        heavy = k % 3 == 0
        inner = r - (3.4 if heavy else 2.2)
        pc.line(cx + inner * math.sin(ang), cy - inner * math.cos(ang),
                cx + (r - 1) * math.sin(ang), cy - (r - 1) * math.cos(ang),
                s["ink"] if heavy else s["dim"])

    hour_ang = math.radians((now.hour % 12) * 30 + now.minute * 0.5)
    minute_ang = math.radians((now.minute + seconds / 60) * 6)
    second_ang = math.radians(seconds * 6)

    pc.line(cx, cy, cx - r * 0.15 * math.sin(second_ang),
            cy + r * 0.15 * math.cos(second_ang), s["second"])
    pc.line(cx, cy, cx + r * 0.5 * math.sin(hour_ang),
            cy - r * 0.5 * math.cos(hour_ang), s["hour"], thick=2)
    pc.line(cx, cy, cx + r * 0.72 * math.sin(minute_ang),
            cy - r * 0.72 * math.cos(minute_ang), s["minute"])
    pc.line(cx, cy, cx + r * 0.84 * math.sin(second_ang),
            cy - r * 0.84 * math.cos(second_ang), s["second"])
    tx = round(cx + r * 0.84 * math.sin(second_ang))
    ty = round(cy - r * 0.84 * math.cos(second_ang))
    pc.px(tx, ty, s["glow"])
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            pc.px(int(cx) + dx, int(cy) + dy, s["second"])

    composite(c, x0 + 1, top, pc)

    mid = top + face_rows // 2
    c.text(x0 + pw // 2 - 1, top + 1, "12", s["ink"], s["paper"])
    c.text(x0 + pw - 5, mid, "3", s["ink"], s["paper"])
    c.text(x0 + pw // 2, top + face_rows - 3, "6", s["ink"], s["paper"])
    c.text(x0 + 4, mid, "9", s["ink"], s["paper"])
    return hits


# ═══════════════════════════════════════════════════════════════════════
# Calendar pane
# ═══════════════════════════════════════════════════════════════════════

DOW = ("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa")
CELL_W = 6
GRID_W = CELL_W * 7


def draw_calendar(c: Canvas, year: int, month: int, today: date,
                  selected: date | None, s: dict) -> list[tuple[int, int, int, tuple]]:
    """Returns hit boxes: (x, y, width, (action, payload))."""
    hits: list[tuple[int, int, int, tuple]] = []
    top = ROW_SPLIT + 2
    bottom = ROW_STATUS - 3
    x0 = COL_SPLIT + 2
    pane_w = W - 2 - x0

    cap = "◇ CALENDAR ◇"
    c.text(x0 + (pane_w - len(cap)) // 2, ROW_SPLIT + 1, cap, s["dim"], s["paper"])

    weeks = cal_mod.Calendar(cal_mod.SUNDAY).monthdayscalendar(year, month)
    block_h = 3 + len(weeks)
    top_y = top + max(0, (bottom - top - block_h) // 2)

    title = f"{month:02d}/{year}"
    tx = x0 + (pane_w - len(title)) // 2
    c.text(tx, top_y, title, s["ink"], s["paper"])
    c.text(tx - 4, top_y, "‹", s["dim"], s["paper"])
    c.text(tx + len(title) + 3, top_y, "›", s["dim"], s["paper"])
    hits.append((tx - 4, top_y, 1, ("prev", None)))
    hits.append((tx + len(title) + 3, top_y, 1, ("next", None)))

    left = x0 + (pane_w - GRID_W) // 2
    hy = top_y + 2
    for i, name in enumerate(DOW):
        if i == 0:
            bg, fg = s["sun"], s["ink"]
        elif i == 6:
            bg, fg = s["sat"], s["ink"]
        else:
            bg, fg = s["head"], s["paper"]
        cell_x = left + i * CELL_W
        c.fill(cell_x, hy, CELL_W, 1, " ", fg, bg)
        c.text(cell_x + 2, hy, name, fg, bg)

    cal = cal_mod.Calendar(cal_mod.SUNDAY)
    dates = list(cal.itermonthdates(year, month))
    rows = [dates[i:i + 7] for i in range(0, len(dates), 7)]
    for ri, week in enumerate(rows):
        ry = hy + 1 + ri
        for di, d in enumerate(week):
            cell_x = left + di * CELL_W
            in_month = (d.month == month)
            is_today = (d == today)
            is_sel = (selected is not None and d == selected)
            if di == 0:
                bg = s["sun"]
            elif di == 6:
                bg = s["sat"]
            else:
                bg = s["paper"]
            fg = s["ink"] if in_month else s["dim"]
            if is_sel and not is_today:
                bg, fg = s["head"], s["paper"]
            if is_today:
                bg, fg = s["accent"], "#FFFFFF"
            c.fill(cell_x, ry, CELL_W, 1, " ", fg, bg)
            c.text(cell_x + 2, ry, f"{d.day:2d}", fg, bg)
            if is_today:
                c.put(cell_x, ry, "[", "#FFFFFF", bg)
                c.put(cell_x + CELL_W - 1, ry, "]", "#FFFFFF", bg)
            elif is_sel:
                c.put(cell_x, ry, "‹", s["accent"], bg)
                c.put(cell_x + CELL_W - 1, ry, "›", s["accent"], bg)
            hits.append((cell_x, ry, CELL_W, ("day", d)))

    iso = today.isocalendar()
    doy = today.timetuple().tm_yday
    total = date(today.year, 12, 31).timetuple().tm_yday
    foot = f"W{iso[1]:02d} · DAY {doy}/{total}"
    c.text(x0 + (pane_w - len(foot)) // 2, bottom, foot, s["dim"], s["paper"])
    return hits


# ═══════════════════════════════════════════════════════════════════════
# Assemble
# ═══════════════════════════════════════════════════════════════════════


def build_screen(now: datetime, year: int, month: int, today: date,
                 s: dict, theme_label: str,
                 selected: date | None = None,
                 reveal: float = 1.0) -> tuple[Canvas, list]:
    c = Canvas(W, H, s["paper"])
    draw_window(c, s, now, theme_label)
    hits = draw_clock(c, now, s)
    hits += draw_calendar(c, year, month, today, selected, s)

    if reveal < 1.0:
        vw = max(1, int(W * reveal))
        vh = max(1, int(H * reveal))
        c.mask_outside((W - vw) // 2, (H - vh) // 2, vw, vh, s["paper"])
    return c, hits


# ═══════════════════════════════════════════════════════════════════════
# Textual app
# ═══════════════════════════════════════════════════════════════════════


class MainScreen(Widget):
    def __init__(self) -> None:
        super().__init__()
        self._today = date.today()
        self._year = self._today.year
        self._month = self._today.month
        self._theme: str | None = None
        self._selected: date | None = None
        self._reveal = 0.0
        self._hits: list = []

    # ── lifecycle ─────────────────────────────────────────────────────
    def on_mount(self) -> None:
        self.set_interval(0.1, self._tick)          # 10 fps: smooth seconds

    def _tick(self) -> None:
        if self._reveal < 1.0:                      # opening animation
            self._reveal = min(1.0, self._reveal + 0.12)
        self.refresh()

    # ── state ─────────────────────────────────────────────────────────
    def shift_month(self, delta: int) -> None:
        m = self._month + delta
        self._year += (m - 1) // 12
        self._month = (m - 1) % 12 + 1
        self.refresh()

    def go_today(self) -> None:
        self._today = date.today()
        self._year, self._month = self._today.year, self._today.month
        self._selected = None
        self.refresh()

    def cycle_theme(self, index: int) -> None:
        self._theme = THEME_ORDER[index - 1]
        self.refresh()

    # ── mouse ─────────────────────────────────────────────────────────
    def on_click(self, event: events.Click) -> None:
        for (hx, hy, hw, payload) in self._hits:
            if hx <= event.x < hx + hw and hy == event.y:
                action, value = payload
                if action == "prev":
                    self.shift_month(-1)
                elif action == "next":
                    self.shift_month(1)
                else:
                    d = value
                    if d.month != self._month or d.year != self._year:
                        self._year, self._month = d.year, d.month
                    self._selected = d
                    self.refresh()
                return

    # ── render ────────────────────────────────────────────────────────
    def render(self) -> Text:
        now = datetime.now()
        s = get_scheme(now, self._theme)
        label = self._theme or get_time_of_day(now.hour)
        c, hits = build_screen(now, self._year, self._month, self._today,
                               s, label, self._selected, self._reveal)
        self._hits = hits
        return c.to_text()


class WhenTuiApp(App):
    """Nintendo DS menu screen, in a terminal."""

    CSS = "MainScreen { height: 100%; }"
    BINDINGS = [
        Binding("left", "prev_month", "Prev Month"),
        Binding("right", "next_month", "Next Month"),
        Binding("t", "go_today", "Today"),
        Binding("1", "theme1", "Morning"),
        Binding("2", "theme2", "Afternoon"),
        Binding("3", "theme3", "Evening"),
        Binding("4", "theme4", "Night"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        self._main = MainScreen()
        yield self._main

    def action_prev_month(self) -> None:
        self._main.shift_month(-1)

    def action_next_month(self) -> None:
        self._main.shift_month(1)

    def action_go_today(self) -> None:
        self._main.go_today()

    def action_theme1(self) -> None:
        self._main.cycle_theme(1)

    def action_theme2(self) -> None:
        self._main.cycle_theme(2)

    def action_theme3(self) -> None:
        self._main.cycle_theme(3)

    def action_theme4(self) -> None:
        self._main.cycle_theme(4)


if __name__ == "__main__":
    WhenTuiApp().run()
