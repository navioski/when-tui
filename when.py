#!/usr/bin/env python3
"""when-tui — a terminal replica of the Nintendo DS menu screen.

A windowed, character-drawn clock and calendar: title bar, two panes, status
bar, and a hand-drawn 5x7 pixel font for the digital time.

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

# ═══════════════════════════════════════════════════════════════════════
# Geometry
# ═══════════════════════════════════════════════════════════════════════

W, H = 96, 36
ASPECT_Y = 2.0          # a terminal cell is twice as tall as it is wide

# window chrome
ROW_TITLE = 1
ROW_SPLIT = 2
ROW_STATUS = H - 3
COL_SPLIT = 52          # x of the vertical divider between the panes

# ═══════════════════════════════════════════════════════════════════════
# Palette — a DS-ish light UI inside a dark chrome
# ═══════════════════════════════════════════════════════════════════════

PALETTES = {
    "morning": dict(
        chrome="#2F3A4E", chrome_fg="#E9EEF7", chrome_edge="#1D2534",
        paper="#FDFCF7", grid="#E4E2D6", ink="#3A3F4A", dim="#8D94A0",
        face="#FFFFFF", tick="#9AA1AE",
        hour="#2A2F3A", minute="#4A5260", second="#D4613C",
        sun="#FFC9DA", sat="#C2D6FF", head="#39445A", accent="#3F6FD8",
        shadow="#E8E4D6",
    ),
    "afternoon": dict(
        chrome="#31405A", chrome_fg="#E9EFFA", chrome_edge="#1E2738",
        paper="#FAFCFF", grid="#DDE3EE", ink="#37404E", dim="#8894A6",
        face="#FFFFFF", tick="#8E9AAC",
        hour="#262D3A", minute="#48525F", second="#D2436A",
        sun="#FFC9DA", sat="#C2D6FF", head="#39445A", accent="#2F6FD4",
        shadow="#E2E7F0",
    ),
    "evening": dict(
        chrome="#3E3548", chrome_fg="#F2EAF2", chrome_edge="#241F2B",
        paper="#FDF8F4", grid="#E8DFD6", ink="#463D36", dim="#9C8C7E",
        face="#FFFFFF", tick="#94816F",
        hour="#33291F", minute="#54463A", second="#C2503A",
        sun="#FFC9C2", sat="#C8CEEA", head="#463A30", accent="#B96A32",
        shadow="#EAE2D8",
    ),
    "night": dict(
        chrome="#252A40", chrome_fg="#E6E9F8", chrome_edge="#151827",
        paper="#F7F8FD", grid="#DCDEEF", ink="#343850", dim="#8088A2",
        face="#FFFFFF", tick="#7E86A0",
        hour="#22263A", minute="#464C64", second="#6E6EDC",
        sun="#FFC9DA", sat="#C2D6FF", head="#2F3652", accent="#5566D8",
        shadow="#E4E6F4",
    ),
}


def get_time_of_day(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 20:
        return "evening"
    return "night"


def get_scheme(now: datetime | None = None) -> dict:
    return PALETTES[get_time_of_day((now or datetime.now()).hour)]


# ═══════════════════════════════════════════════════════════════════════
# 5x7 pixel font (digits + colon) — the "pixel font" of the digital clock
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
# Canvas: one cell = (char, fg, bg)
# ═══════════════════════════════════════════════════════════════════════


class Canvas:
    def __init__(self, w: int, h: int, bg: str) -> None:
        self.w, self.h = w, h
        self.cells: list[list[tuple[str, str, str]]] = [
            [(" ", bg, bg) for _ in range(w)] for _ in range(h)
        ]

    def put(self, x: int, y: int, ch: str, fg: str, bg: str) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.cells[y][x] = (ch[0], fg, bg)

    def fill(self, x: int, y: int, w: int, h: int, ch: str, fg: str, bg: str) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.put(xx, yy, ch, fg, bg)

    def text(self, x: int, y: int, s: str, fg: str, bg: str) -> None:
        for i, ch in enumerate(s):
            self.put(x + i, y, ch, fg, bg)

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

    def to_text(self) -> Text:
        t = Text()
        for y in range(self.h):
            run_fg = run_bg = None
            buf: list[str] = []
            for x in range(self.w):
                ch, fg, bg = self.cells[y][x]
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
# Pixel layer: two vertical pixels per cell, rendered as "▀"
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


def draw_window(c: Canvas, s: dict, now: datetime) -> None:
    # title bar
    c.fill(0, 0, W, H, " ", s["ink"], s["paper"])
    c.frame(0, 0, W, H, s["chrome_edge"], s["paper"])

    c.fill(1, ROW_TITLE, W - 2, 1, " ", s["chrome_fg"], s["chrome"])
    title = " ░▒▓ WHEN-TUI ▓▒░ "
    c.text(2, ROW_TITLE, title, s["chrome_fg"], s["chrome"])

    stamp = now.strftime("%Y-%m-%d  %H:%M")
    c.text(W - 3 - len(stamp), ROW_TITLE, stamp, s["chrome_fg"], s["chrome"])

    # split under the title bar, with a T junction at the pane divider
    c.hline(1, ROW_SPLIT, W - 2, "═", s["chrome_edge"], s["paper"])
    c.put(0, ROW_SPLIT, "╠", s["chrome_edge"], s["paper"])
    c.put(W - 1, ROW_SPLIT, "╣", s["chrome_edge"], s["paper"])
    c.put(COL_SPLIT, ROW_SPLIT, "╦", s["chrome_edge"], s["paper"])

    # vertical divider between the panes
    c.vline(COL_SPLIT, ROW_SPLIT + 1, ROW_STATUS - ROW_SPLIT - 1,
            "║", s["chrome_edge"], s["paper"])

    # status bar
    c.hline(1, ROW_STATUS, W - 2, "═", s["chrome_edge"], s["paper"])
    c.put(0, ROW_STATUS, "╠", s["chrome_edge"], s["paper"])
    c.put(W - 1, ROW_STATUS, "╣", s["chrome_edge"], s["paper"])
    c.put(COL_SPLIT, ROW_STATUS, "╩", s["chrome_edge"], s["paper"])
    c.fill(1, ROW_STATUS + 1, W - 2, 1, " ", s["chrome_fg"], s["chrome"])
    hints = " ← →  month     T  today     Q  quit "
    c.text(2, ROW_STATUS + 1, hints, s["chrome_fg"], s["chrome"])


# ═══════════════════════════════════════════════════════════════════════
# Clock pane
# ═══════════════════════════════════════════════════════════════════════


def draw_clock(c: Canvas, now: datetime, s: dict) -> None:
    top = ROW_SPLIT + 1
    bottom = ROW_STATUS - 1
    pane_w = COL_SPLIT - 2

    # pixel-font digital time, bottom of the pane
    stamp = now.strftime("%H:%M")
    dw = font_width(stamp, 1, gap=1)
    digit_y = bottom - 7
    draw_font(c, 2 + (pane_w - dw) // 2, digit_y, stamp, s["hour"], s["paper"])

    # analog face fills the rest
    face_rows = digit_y - top - 2
    pw = pane_w - 2
    ph = face_rows * 2
    pc = PixelCanvas(pw, ph, s["paper"])
    cx, cy = (pw - 1) / 2, (ph - 1) / 2
    r = min(cx, cy) - 1

    for k in range(720):
        ang = math.radians(k / 2)
        pc.px(round(cx + r * math.sin(ang)), round(cy - r * math.cos(ang)), s["tick"])
    for k in range(12):
        ang = math.radians(k * 30)
        heavy = k % 3 == 0
        inner = r - (3.4 if heavy else 2.2)
        pc.line(cx + inner * math.sin(ang), cy - inner * math.cos(ang),
                cx + (r - 1) * math.sin(ang), cy - (r - 1) * math.cos(ang),
                s["ink"] if heavy else s["dim"])

    hour_ang = math.radians((now.hour % 12) * 30 + now.minute * 0.5)
    minute_ang = math.radians(now.minute * 6)
    second_ang = math.radians(now.second * 6)

    pc.line(cx, cy, cx - r * 0.15 * math.sin(second_ang),
            cy + r * 0.15 * math.cos(second_ang), s["second"])
    pc.line(cx, cy, cx + r * 0.5 * math.sin(hour_ang),
            cy - r * 0.5 * math.cos(hour_ang), s["hour"], thick=2)
    pc.line(cx, cy, cx + r * 0.72 * math.sin(minute_ang),
            cy - r * 0.72 * math.cos(minute_ang), s["minute"])
    pc.line(cx, cy, cx + r * 0.84 * math.sin(second_ang),
            cy - r * 0.84 * math.cos(second_ang), s["second"])
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            pc.px(int(cx) + dx, int(cy) + dy, s["second"])

    composite(c, 2, top + 1, pc)

    mid = top + 1 + face_rows // 2
    c.text(2 + pw // 2 - 1, top + 3, "12", s["ink"], s["paper"])
    c.text(2 + pw - 5, mid, "3", s["ink"], s["paper"])
    c.text(2 + pw // 2, top + face_rows - 2, "6", s["ink"], s["paper"])
    c.text(2 + 4, mid, "9", s["ink"], s["paper"])


# ═══════════════════════════════════════════════════════════════════════
# Calendar pane
# ═══════════════════════════════════════════════════════════════════════

DOW = ("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa")
CELL_W = 6
GRID_W = CELL_W * 7


def draw_calendar(c: Canvas, year: int, month: int, today: date, s: dict) -> None:
    top, bottom = ROW_SPLIT + 1, ROW_STATUS - 1
    x0 = COL_SPLIT + 1
    pane_w = W - 1 - x0

    weeks = cal_mod.Calendar(cal_mod.SUNDAY).monthdayscalendar(year, month)
    show_today = (year == today.year and month == today.month)

    block_h = 3 + len(weeks)          # title, gap, header, weeks
    top_y = top + max(1, (bottom - top - block_h) // 2)

    title = f"{month:02d}/{year}"
    c.text(x0 + (pane_w - len(title)) // 2, top_y, title, s["ink"], s["paper"])

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

    for wi, week in enumerate(weeks):
        ry = hy + 1 + wi
        for di, day in enumerate(week):
            if day == 0:
                continue
            cell_x = left + di * CELL_W
            is_today = show_today and day == today.day
            if di == 0:
                bg = s["sun"]
            elif di == 6:
                bg = s["sat"]
            else:
                bg = s["paper"]
            fg = s["ink"]
            if is_today:
                bg, fg = s["accent"], "#FFFFFF"
            c.fill(cell_x, ry, CELL_W, 1, " ", fg, bg)
            c.text(cell_x + 2, ry, f"{day:2d}", fg, bg)
            if is_today:
                c.put(cell_x, ry, "[", "#FFFFFF", bg)
                c.put(cell_x + CELL_W - 1, ry, "]", "#FFFFFF", bg)

    if show_today:
        line = today.strftime("%A").upper()
        c.text(x0 + (pane_w - len(line)) // 2, bottom - 1, line, s["dim"], s["paper"])


# ═══════════════════════════════════════════════════════════════════════
# Assemble
# ═══════════════════════════════════════════════════════════════════════


def build_screen(now: datetime, year: int, month: int, today: date,
                 s: dict) -> Canvas:
    c = Canvas(W, H, s["paper"])
    draw_window(c, s, now)
    draw_clock(c, now, s)
    draw_calendar(c, year, month, today, s)
    return c


# ═══════════════════════════════════════════════════════════════════════
# Textual app
# ═══════════════════════════════════════════════════════════════════════


class MainScreen(Widget):
    def __init__(self) -> None:
        super().__init__()
        self._today = date.today()
        self._year = self._today.year
        self._month = self._today.month

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)

    def shift_month(self, delta: int) -> None:
        m = self._month + delta
        self._year += (m - 1) // 12
        self._month = (m - 1) % 12 + 1
        self.refresh()

    def go_today(self) -> None:
        self._today = date.today()
        self._year, self._month = self._today.year, self._today.month
        self.refresh()

    def render(self) -> Text:
        now = datetime.now()
        return build_screen(now, self._year, self._month, self._today,
                            get_scheme(now)).to_text()


class WhenTuiApp(App):
    """Nintendo DS menu screen, in a terminal."""

    CSS = "MainScreen { height: 100%; }"
    BINDINGS = [
        Binding("left", "prev_month", "Prev Month"),
        Binding("right", "next_month", "Next Month"),
        Binding("t", "go_today", "Today"),
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


if __name__ == "__main__":
    WhenTuiApp().run()
