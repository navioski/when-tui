#!/usr/bin/env python3
"""when-tui — a terminal replica of the Nintendo DS menu screen.

Draws the DS "standby" menu: grid-paper background, analog clock, month
calendar with coloured weekend columns, the app tiles and the empty GBA slot.

    python3 when.py
"""

from __future__ import annotations

import calendar as cal_mod
import math
from datetime import date, datetime

from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widget import Widget

# ═══════════════════════════════════════════════════════════════════════
# Canvas size — 96 × 38 character cells is roughly the DS's 4:3 screen
# ═══════════════════════════════════════════════════════════════════════

W, H = 96, 38

# Vertical stretch of a terminal cell: two cells wide == one cell tall.
ASPECT_Y = 2.0

# ═══════════════════════════════════════════════════════════════════════
# Palettes — the DS tints its menu by time of day
# ═══════════════════════════════════════════════════════════════════════

PALETTES = {
    "morning": dict(
        paper="#FCFAF4", grid="#E8E4D8", ink="#4A4A52", dim="#9A9AA6",
        frame="#B8B4A6", face="#FFFFFF", tick="#8A8A96",
        hour="#3A3A44", minute="#5A5A66", second="#D0603C",
        sun_col="#FFC9DA", sat_col="#BFD4FF", head="#3E4658",
        card="#E2DED2", card_edge="#8E8A7E", gba="#D8D4C8", accent="#E0A040",
    ),
    "afternoon": dict(
        paper="#F8FAFC", grid="#DEE4EE", ink="#424A58", dim="#94A0B0",
        frame="#AAB4C4", face="#FFFFFF", tick="#8090A0",
        hour="#2E3644", minute="#505C6C", second="#D84C6A",
        sun_col="#FFC9DA", sat_col="#BFD4FF", head="#3E4658",
        card="#DDE4EE", card_edge="#8894A6", gba="#D2DAE6", accent="#3E7BD8",
    ),
    "evening": dict(
        paper="#FAF6F2", grid="#E6DED6", ink="#4E4438", dim="#A09484",
        frame="#BCAE9C", face="#FFFFFF", tick="#90806E",
        hour="#3C3226", minute="#5C5044", second="#C05030",
        sun_col="#FFC9C0", sat_col="#C4CCE8", head="#4A3E30",
        card="#E6DED2", card_edge="#948674", gba="#DCD2C4", accent="#C07038",
    ),
    "night": dict(
        paper="#F2F3FA", grid="#DCDEEF", ink="#3C3C50", dim="#8C8CA4",
        frame="#A8A8C0", face="#FFFFFF", tick="#7A7A96",
        hour="#2A2A3C", minute="#4E4E64", second="#6A6AD8",
        sun_col="#FFC9DA", sat_col="#BFD4FF", head="#343A54",
        card="#D8DAEC", card_edge="#8288A2", gba="#CED0E4", accent="#5A6AD0",
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
    now = now or datetime.now()
    return PALETTES[get_time_of_day(now.hour)]


# ═══════════════════════════════════════════════════════════════════════
# Canvas: one cell = (char, fg, bg)
# ═══════════════════════════════════════════════════════════════════════


class Canvas:
    def __init__(self, w: int, h: int, bg: str) -> None:
        self.w, self.h = w, h
        self.bg = bg
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
              double: bool = False) -> None:
        """Draw a box outline (x, y, w, h) with corners."""
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

    def shadow(self, x: int, y: int, w: int, h: int, col: str) -> None:
        """Soft drop shadow to the right and below."""
        for yy in range(y + 1, y + h + 1):
            self.put(x + w, yy, " ", col, col)
        for xx in range(x + 1, x + w + 1):
            self.put(xx, y + h, " ", col, col)

    def to_text(self) -> Text:
        t = Text()
        for y in range(self.h):
            run_ch, run_fg, run_bg = None, None, None
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
# Drawing helpers
# ═══════════════════════════════════════════════════════════════════════


class PixelCanvas:
    """A colour grid at twice the vertical resolution of a text cell.

    Each cell becomes a "▀" (top pixel in the foreground colour, bottom pixel
    in the background colour), so a 32x32 pixel face costs 32x16 cells.
    """

    def __init__(self, w: int, h: int, bg: str) -> None:
        self.w, self.h = w, h
        self.grid = [[bg for _ in range(w)] for _ in range(h)]

    def px(self, x: int, y: int, col: str) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.grid[y][x] = col

    def line(self, x0: float, y0: float, x1: float, y1: float, col: str,
             thick: int = 1) -> None:
        """Bresenham line; `thick` 2 draws a second pixel across the line."""
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
            if abs(x - nx) >= abs(y - ny):      # mostly horizontal -> thicken down
                self.px(x, y + 1, col)
            else:                                # mostly vertical -> thicken right
                self.px(x + 1, y, col)

    def ring(self, cx: float, cy: float, r: float, col: str, width: float = 1.0) -> None:
        for y in range(self.h):
            for x in range(self.w):
                d = math.hypot(x - cx, y - cy)
                if abs(d - r) < width:
                    self.px(x, y, col)


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


def hand_tip(cx: int, cy: int, angle: float, length: float) -> tuple[float, float]:
    return cx + length * math.sin(angle), cy - length * math.cos(angle) / ASPECT_Y


# ═══════════════════════════════════════════════════════════════════════
# Background: grid paper
# ═══════════════════════════════════════════════════════════════════════


def draw_paper(c: Canvas, s: dict) -> None:
    c.fill(0, 0, W, H, " ", s["dim"], s["paper"])
    for x in range(0, W, 12):
        c.vline(x, 0, H, "│", s["grid"], s["paper"])
    for y in range(0, H, 6):
        c.hline(0, y, W, "─", s["grid"], s["paper"])


# ═══════════════════════════════════════════════════════════════════════
# Clock panel
# ═══════════════════════════════════════════════════════════════════════

CLOCK_X, CLOCK_Y, CLOCK_W, CLOCK_H = 3, 2, 40, 18


def draw_clock(c: Canvas, now: datetime, s: dict) -> None:
    x0, y0, w, h = CLOCK_X, CLOCK_Y, CLOCK_W, CLOCK_H
    c.shadow(x0, y0, w, h, s["grid"])
    c.fill(x0, y0, w, h, " ", s["ink"], s["face"])
    c.frame(x0, y0, w, h, s["frame"], s["face"])

    pw, ph = w - 4, (h - 2) * 2          # pixel canvas inside the frame
    pc = PixelCanvas(pw, ph, s["face"])
    cx, cy = (pw - 1) / 2, (ph - 1) / 2
    r = min(cx, cy) - 1.5

    # face: crisp 1px rim + 12 hour ticks
    for k in range(720):
        ang = math.radians(k / 2)
        pc.px(round(cx + r * math.sin(ang)), round(cy - r * math.cos(ang)), s["tick"])
    for k in range(12):
        ang = math.radians(k * 30)
        heavy = k % 3 == 0
        inner = r - (3.2 if heavy else 2.2)
        pc.line(cx + inner * math.sin(ang), cy - inner * math.cos(ang),
                cx + (r - 1) * math.sin(ang), cy - (r - 1) * math.cos(ang),
                s["ink"] if heavy else s["dim"], thick=1)

    def hand(angle: float, length: float, col: str, thick: int) -> None:
        pc.line(cx, cy, cx + length * math.sin(angle),
                cy - length * math.cos(angle), col, thick=thick)

    hour_ang = math.radians((now.hour % 12) * 30 + now.minute * 0.5)
    minute_ang = math.radians(now.minute * 6)
    second_ang = math.radians(now.second * 6)

    pc.line(cx, cy, cx - r * 0.16 * math.sin(second_ang),
            cy + r * 0.16 * math.cos(second_ang), s["second"])
    hand(hour_ang, r * 0.52, s["hour"], thick=2)
    hand(minute_ang, r * 0.76, s["minute"], thick=1)
    hand(second_ang, r * 0.88, s["second"], thick=1)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            pc.px(int(cx) + dx, int(cy) + dy, s["second"])

    composite(c, x0 + 2, y0 + 1, pc)

    # numerals on top of the pixel face
    c.text(x0 + w // 2 - 1, y0 + 4, "12", s["ink"], s["face"])
    c.text(x0 + w - 6, y0 + h // 2, "3", s["ink"], s["face"])
    c.text(x0 + w // 2, y0 + h - 5, "6", s["ink"], s["face"])
    c.text(x0 + 4, y0 + h // 2, "9", s["ink"], s["face"])


# ═══════════════════════════════════════════════════════════════════════
# Calendar panel
# ═══════════════════════════════════════════════════════════════════════

CAL_X, CAL_Y, CAL_W, CAL_H = 46, 2, 47, 18
DOW = ("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa")
CELL_W = 6          # columns per day cell
GRID_W = CELL_W * 7  # 42


def draw_calendar(c: Canvas, year: int, month: int, today: date, s: dict) -> None:
    x0, y0, w, h = CAL_X, CAL_Y, CAL_W, CAL_H
    c.shadow(x0, y0, w, h, s["grid"])
    c.fill(x0, y0, w, h, " ", s["ink"], s["face"])
    c.frame(x0, y0, w, h, s["frame"], s["face"])

    left = x0 + (w - GRID_W) // 2

    # month / year header
    title = f"{month:02d}/{year}"
    c.text(x0 + (w - len(title)) // 2, y0 + 2, title, s["ink"], s["face"])

    # weekday header bar
    hy = y0 + 4
    for i, name in enumerate(DOW):
        sel = (i == 0, i == 6)
        bg = s["sun_col"] if i == 0 else (s["sat_col"] if i == 6 else s["head"])
        fg = s["head"] if i in (0, 6) else s["face"]
        cell_x = left + i * CELL_W
        c.fill(cell_x, hy, CELL_W - 1, 1, " ", fg, bg)
        c.text(cell_x + 1, hy, name, fg, bg)

    weeks = cal_mod.Calendar(cal_mod.SUNDAY).monthdayscalendar(year, month)
    show_today = (year == today.year and month == today.month)

    for wi, week in enumerate(weeks):
        ry = hy + 1 + wi
        for di, day in enumerate(week):
            cell_x = left + di * CELL_W
            if day == 0:
                continue
            is_today = show_today and day == today.day
            if di == 0:
                bg, fg = s["sun_col"], s["ink"]
            elif di == 6:
                bg, fg = s["sat_col"], s["ink"]
            else:
                bg, fg = s["face"], s["ink"]
            if is_today:
                bg, fg = s["accent"], "#FFFFFF"
            c.fill(cell_x, ry, CELL_W - 1, 1, " ", fg, bg)
            label = f"{day:2d}"
            c.text(cell_x + 2, ry, label, fg, bg)
            if is_today:
                # little selection brackets
                c.put(cell_x, ry, "[", "#FFFFFF", bg)
                c.put(cell_x + CELL_W - 2, ry, "]", "#FFFFFF", bg)

    # today's weekday under the grid
    if show_today:
        line = today.strftime("%A").upper()
        c.text(x0 + (w - len(line)) // 2, y0 + h - 2, line, s["dim"], s["face"])


# ═══════════════════════════════════════════════════════════════════════
# Cards, GBA slot and the icon strip
# ═══════════════════════════════════════════════════════════════════════


def draw_card(c: Canvas, x: int, y: int, w: int, h: int, s: dict,
              title: str = "", subtitle: str = "", icon: str = "") -> None:
    c.shadow(x, y, w, h, s["grid"])
    c.fill(x, y, w, h, " ", s["ink"], s["card"])
    c.frame(x, y, w, h, s["card_edge"], s["card"])

    if icon:
        draw_icon(c, icon, x + 3, y + (h - 3) // 2, s)

    if title:
        tx = x + (13 if icon else 3)
        c.text(tx, y + h // 2 - 1, title, s["ink"], s["card"])
    if subtitle:
        tx = x + (13 if icon else 3)
        c.text(tx, y + h // 2 + 1, subtitle, s["dim"], s["card"])


def draw_icon(c: Canvas, kind: str, x: int, y: int, s: dict) -> None:
    """Small hand-drawn icons (no external glyphs, so no font surprises)."""
    bg = s["card"]
    if kind == "tetris":
        blocks = [("#E8B830", 0, 0), ("#E8B830", 1, 0), ("#E8B830", 2, 0),
                  ("#4FA8E0", 1, 1), ("#D05070", 2, 1)]
        for col, dx, dy in blocks:
            c.put(x + dx, y + dy, "█", col, bg)
    elif kind == "picto":
        # outlined speech bubble with a tail
        c.hline(x + 1, y, 4, "▄", s["accent"], bg)
        for dy in (1, 2):
            c.put(x, y + dy, "█", s["accent"], bg)
            c.put(x + 5, y + dy, "█", s["accent"], bg)
        c.hline(x + 1, y + 3, 4, "▀", s["accent"], bg)
        c.put(x + 1, y + 4, "▀", s["accent"], bg)
    elif kind == "download":
        # three wireless waves over a DS body
        c.text(x, y, "▂▄▆", s["accent"], bg)
        c.text(x, y + 1, "▐▌", s["ink"], bg)
        c.text(x + 2, y + 1, "▐▌", s["ink"], bg)
    elif kind == "gba":
        for dy in range(2):
            for dx in range(4):
                c.put(x + dx, y + dy, "▒", s["dim"], bg)


def draw_tiles(c: Canvas, s: dict) -> None:
    # TETRIS DS — the wide card
    draw_card(c, 12, 21, 72, 5, s, "TETRIS DS", "Nintendo", "tetris")
    # PICTOCHAT / DS Download Play — side by side
    draw_card(c, 12, 27, 34, 4, s, "PICTOCHAT", "", "picto")
    draw_card(c, 49, 27, 35, 4, s, "DS Download Play", "", "download")


def draw_gba(c: Canvas, s: dict) -> None:
    x, y, w, h = 12, 32, 72, 4
    c.shadow(x, y, w, h, s["grid"])
    c.fill(x, y, w, h, " ", s["dim"], s["gba"])
    c.frame(x, y, w, h, s["card_edge"], s["gba"])

    draw_icon(c, "gba", x + 3, y + 1, {**s, "card": s["gba"]})

    msg = "There is no Game Pak inserted."
    c.text(x + 11, y + 1, msg, s["ink"], s["gba"])
    c.text(x + 11, y + 2, "GBA", s["dim"], s["gba"])


def draw_icons(c: Canvas, s: dict) -> None:
    y = H - 2
    # little sun (brightness)
    c.put(3, y, "▄", s["accent"], s["paper"])
    c.put(2, y - 1, "▖", s["accent"], s["paper"])
    c.put(4, y - 1, "▗", s["accent"], s["paper"])
    c.put(3, y - 1, "█", s["accent"], s["paper"])
    # DS icon: two stacked screens
    c.text(W // 2 - 2, y - 1, "▄▄▄▄", s["ink"], s["paper"])
    c.text(W // 2 - 2, y, "▀▀▀▀", s["ink"], s["paper"])


# ═══════════════════════════════════════════════════════════════════════
# Assemble
# ═══════════════════════════════════════════════════════════════════════


def build_screen(now: datetime, year: int, month: int, today: date,
                 s: dict) -> Canvas:
    c = Canvas(W, H, s["paper"])
    draw_paper(c, s)
    draw_clock(c, now, s)
    draw_calendar(c, year, month, today, s)
    draw_tiles(c, s)
    draw_gba(c, s)
    draw_icons(c, s)
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
