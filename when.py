#!/usr/bin/env python3
"""NDS Standby Screen — terminal TUI replica of the Nintendo DS menu screen.

Usage:  python3 nds_standby.py
"""

import math
import calendar as cal_mod
from datetime import datetime, date

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Label

from rich.text import Text
from rich.style import Style

# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

ASPECT_Y = 2.0
CLOCK_SIZE = 27
CLOCK_RADIUS = 13
CX = CY = CLOCK_SIZE // 2

BOX_INNER_W = 31   # inner width of each box (between borders)
BOX_INNER_H = 31   # inner height of each box (between borders)
BOX_WIDTH = BOX_INNER_W + 2   # 33  (including border chars)
BOX_HEIGHT = BOX_INNER_H + 2  # 33

# ═══════════════════════════════════════════════════════════════════════
# Color schemes — time-of-day accents on dark boxes, white background
# ═══════════════════════════════════════════════════════════════════════

COLOR_SCHEMES = {
    "morning": {
        "app_bg":      "#F0F0F0",
        "box_bg":      "#1E2640",
        "box_border":  "#B0B8C8",
        "foreground":  "#D0D4E0",
        "clock_circle":"#4A5580",
        "hour_hand":   "#E8E8F0",
        "minute_hand": "#8890B0",
        "second_hand": "#60B0D0",
        "center_dot":  "#E8E8F0",
        "tick_mark":   "#A0A8C0",
        "number":      "#C0C4D8",
        "today_bg":    "#4A90D9",
        "header":      "#C0C8E0",
    },
    "afternoon": {
        "app_bg":      "#F5F5F0",
        "box_bg":      "#2A2A2A",
        "box_border":  "#C0C0C0",
        "foreground":  "#D8D8D8",
        "clock_circle":"#585858",
        "hour_hand":   "#F0F0F0",
        "minute_hand": "#909090",
        "second_hand": "#E08040",
        "center_dot":  "#F0F0F0",
        "tick_mark":   "#B0B0B0",
        "number":      "#C8C8C8",
        "today_bg":    "#D08040",
        "header":      "#D0D0D0",
    },
    "evening": {
        "app_bg":      "#F2EFE8",
        "box_bg":      "#2E2218",
        "box_border":  "#C8B8A0",
        "foreground":  "#D8CCB8",
        "clock_circle":"#5C4430",
        "hour_hand":   "#F0E8D8",
        "minute_hand": "#907860",
        "second_hand": "#D06040",
        "center_dot":  "#F0E8D8",
        "tick_mark":   "#B8A088",
        "number":      "#D0C0A8",
        "today_bg":    "#C06030",
        "header":      "#D8CCB8",
    },
    "night": {
        "app_bg":      "#E8E8F0",
        "box_bg":      "#181830",
        "box_border":  "#A0A0C0",
        "foreground":  "#C0C0E0",
        "clock_circle":"#383870",
        "hour_hand":   "#E0E0F8",
        "minute_hand": "#6868A0",
        "second_hand": "#8888FF",
        "center_dot":  "#E0E0F8",
        "tick_mark":   "#9898C0",
        "number":      "#B8B8D8",
        "today_bg":    "#5050B0",
        "header":      "#C0C0E0",
    },
}


def get_time_of_day(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    elif 12 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 20:
        return "evening"
    else:
        return "night"


def get_scheme(now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now()
    return COLOR_SCHEMES[get_time_of_day(now.hour)]


def _text_width(t: Text) -> int:
    return len(t.plain.rstrip("\n"))


# ═══════════════════════════════════════════════════════════════════════
# Drawing helpers
# ═══════════════════════════════════════════════════════════════════════

def bresenham_line(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    cx, cy = x0, y0
    while True:
        points.append((cx, cy))
        if cx == x1 and cy == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy
    return points


def hand_endpoint(cx: int, cy: int, angle: float, length: float) -> tuple[float, float]:
    x = cx + length * math.sin(angle)
    y = cy - length * math.cos(angle) / ASPECT_Y
    return x, y


def is_on_circle(x: int, y: int, cx: int, cy: int, radius: float,
                 tolerance: float = 0.8) -> bool:
    dx = x - cx
    dy = (y - cy) * ASPECT_Y
    dist = math.sqrt(dx * dx + dy * dy)
    return abs(dist - radius) < tolerance


def _hour_angle(hour: int, minute: int) -> float:
    return math.radians((hour % 12) * 30 + minute * 0.5)


def _min_sec_angle(value: int) -> float:
    return math.radians(value * 6)


# ═══════════════════════════════════════════════════════════════════════
# Clock renderer
# ═══════════════════════════════════════════════════════════════════════

def _build_clock_canvas(now: datetime) -> list[list[tuple[str, str]]]:
    """Build a CLOCK_SIZE×CLOCK_SIZE grid of (char, tag) tuples."""
    canvas: list[list[tuple[str, str]]] = [
        [(" ", "") for _ in range(CLOCK_SIZE)] for _ in range(CLOCK_SIZE)
    ]

    # Circle outline
    for y in range(CLOCK_SIZE):
        for x in range(CLOCK_SIZE):
            if is_on_circle(x, y, CX, CY, CLOCK_RADIUS):
                canvas[y][x] = ("·", "clock_circle")

    # Hour tick marks
    for h in range(12):
        angle = math.radians(h * 30)
        ex, ey = hand_endpoint(CX, CY, angle, CLOCK_RADIUS)
        ix, iy = round(ex), round(ey)
        if 0 <= ix < CLOCK_SIZE and 0 <= iy < CLOCK_SIZE:
            canvas[iy][ix] = ("▪", "tick_mark")

    # Hour numbers 1-12
    for h in range(1, 13):
        angle = math.radians(h * 30)
        ex, ey = hand_endpoint(CX, CY, angle, CLOCK_RADIUS - 3.5)
        label = str(h)
        start_x = round(ex) - (1 if h >= 10 else 0)
        iy = round(ey)
        for ci, ch in enumerate(label):
            px = start_x + ci
            if 0 <= px < CLOCK_SIZE and 0 <= iy < CLOCK_SIZE:
                canvas[iy][px] = (ch, "number")

    # Hands (back to front)
    h_angle = _hour_angle(now.hour, now.minute)
    _draw_hand(canvas, CX, CY, h_angle, CLOCK_RADIUS * 0.45, "hour_hand", "█")

    m_angle = _min_sec_angle(now.minute)
    _draw_hand(canvas, CX, CY, m_angle, CLOCK_RADIUS * 0.72, "minute_hand", "▓")

    s_angle = _min_sec_angle(now.second)
    _draw_hand(canvas, CX, CY, s_angle, CLOCK_RADIUS * 0.88, "second_hand", "·")
    tail_angle = s_angle + math.pi
    _draw_hand(canvas, CX, CY, tail_angle, CLOCK_RADIUS * 0.15, "second_hand", "·")

    # Center dot (last)
    canvas[CY][CX] = ("●", "center_dot")
    return canvas


def _draw_hand(canvas: list[list[tuple[str, str]]],
               cx: int, cy: int, angle: float, length: float,
               tag: str, char: str) -> None:
    ex, ey = hand_endpoint(cx, cy, angle, length)
    ex_i = max(0, min(CLOCK_SIZE - 1, round(ex)))
    ey_i = max(0, min(CLOCK_SIZE - 1, round(ey)))
    points = bresenham_line(cx, cy, ex_i, ey_i)
    for px, py in points[1:]:
        canvas[py][px] = (char, tag)


def _render_clock(now: datetime, scheme: dict) -> Text:
    """Build a BOX_WIDTH × BOX_HEIGHT Rich Text of the clock."""
    canvas = _build_clock_canvas(now)
    text = Text()
    bg = scheme["box_bg"]
    border_c = scheme["box_border"]
    border_style = Style(color=border_c, bgcolor=bg)

    # How many blank rows above the clock to vertically center the 27-line canvas
    # in the BOX_INNER_H (31) space, leaving 1 row for the digital time.
    canvas_h = CLOCK_SIZE          # 27
    digital_h = 1
    content_h = canvas_h + digital_h  # 28
    pad_top = (BOX_INNER_H - content_h) // 2   # (31-28)//2 = 1
    pad_bot = BOX_INNER_H - content_h - pad_top # 31-28-1 = 2

    # Top border
    text.append("┌" + "─" * BOX_INNER_W + "┐\n", style=border_style)

    # Top padding rows
    for _ in range(pad_top):
        text.append("│" + " " * BOX_INNER_W + "│\n", style=border_style)

    # Canvas rows (horizontally centered: 2-space padding on each side)
    side_pad = (BOX_INNER_W - CLOCK_SIZE) // 2  # (31-27)//2 = 2
    for row in canvas:
        text.append("│" + " " * side_pad, style=border_style)
        for ch, tag in row:
            color = scheme.get(tag, scheme["foreground"])
            if tag:
                text.append(ch, style=Style(color=color, bgcolor=bg))
            else:
                text.append(" ", style=Style(color=bg, bgcolor=bg))
        text.append(" " * side_pad + "│\n", style=border_style)

    # Bottom padding rows
    for _ in range(pad_bot):
        text.append("│" + " " * BOX_INNER_W + "│\n", style=border_style)

    # Digital time row
    time_str = now.strftime("%H:%M:%S")
    digital = f"  {time_str}  ".center(BOX_INNER_W)
    text.append("│", style=border_style)
    text.append(digital, style=Style(color=scheme["foreground"], bgcolor=bg, bold=True))
    text.append("│\n", style=border_style)

    # Bottom border
    text.append("└" + "─" * BOX_INNER_W + "┘", style=border_style)

    return text


# ═══════════════════════════════════════════════════════════════════════
# Calendar renderer
# ═══════════════════════════════════════════════════════════════════════

def _render_calendar(year: int, month: int, today: date, scheme: dict) -> Text:
    """Build a BOX_WIDTH × BOX_HEIGHT Rich Text of the monthly calendar."""
    text = Text()
    bg = scheme["box_bg"]
    border_c = scheme["box_border"]
    border_style = Style(color=border_c, bgcolor=bg)
    base_style = Style(color=scheme["foreground"], bgcolor=bg)
    today_style = Style(color="#FFFFFF", bgcolor=scheme["today_bg"], bold=True)
    header_style = Style(color=scheme["header"], bgcolor=bg, bold=True)

    month_name = cal_mod.month_name[month]
    dow = "Su Mo Tu We Th Fr Sa"   # 20 chars
    WEEK_CHARS = 21                  # 7 days × 3 chars per day

    cal = cal_mod.Calendar(cal_mod.SUNDAY)
    weeks = cal.monthdayscalendar(year, month)
    show_today = (year == today.year and month == today.month)

    # Build week lines (each exactly WEEK_CHARS)
    week_lines: list[str] = []
    for week in weeks:
        parts: list[str] = []
        for day in week:
            if day == 0:
                parts.append("   ")
            else:
                parts.append(f"{day:2} ")
        week_lines.append("".join(parts))  # exactly 21 chars, no strip

    # Content lines: [header, blank, dow] + week_lines
    content_count = 3 + len(week_lines)
    pad_top = (BOX_INNER_H - content_count) // 2
    pad_bot = BOX_INNER_H - content_count - pad_top

    def _fmt_line(s: str, w: int = WEEK_CHARS) -> str:
        """Centre a string within BOX_INNER_W, keeping calendar grid aligned."""
        lp = (BOX_INNER_W - w) // 2
        return " " * lp + s + " " * (BOX_INNER_W - w - lp)

    # Top border
    text.append("┌" + "─" * BOX_INNER_W + "┐\n", style=border_style)

    # Top padding
    for _ in range(pad_top):
        text.append("│" + " " * BOX_INNER_W + "│\n", style=border_style)

    # Header
    hdr = f"{month_name} {year}".center(BOX_INNER_W)
    text.append("│", style=border_style)
    text.append(hdr, style=header_style)
    text.append("│\n", style=border_style)

    # Blank row
    text.append("│" + " " * BOX_INNER_W + "│\n", style=border_style)

    # Day-of-week headers
    text.append("│", style=border_style)
    text.append(_fmt_line(dow, 20), style=base_style)
    text.append("│\n", style=border_style)

    # Week rows with today highlighting
    lp = (BOX_INNER_W - WEEK_CHARS) // 2
    for week_str in week_lines:
        text.append("│", style=border_style)
        text.append(" " * lp, style=base_style)
        col = 0
        while col < 7:
            pos = col * 3
            day_str = week_str[pos:pos + 2]
            if show_today and day_str.strip() and int(day_str) == today.day:
                text.append(day_str, style=today_style)
            else:
                text.append(day_str, style=base_style)
            text.append(" ", style=base_style)  # trailing space after each day
            col += 1
        text.append(" " * (BOX_INNER_W - lp - WEEK_CHARS), style=base_style)
        text.append("│\n", style=border_style)

    # Bottom padding
    for _ in range(pad_bot):
        text.append("│" + " " * BOX_INNER_W + "│\n", style=border_style)

    # Bottom border
    text.append("└" + "─" * BOX_INNER_W + "┘", style=border_style)

    return text


# ═══════════════════════════════════════════════════════════════════════
# Combined screen widget — clock left, calendar right, same-size boxes
# ═══════════════════════════════════════════════════════════════════════

class MainScreen(Widget):
    """Renders the analog clock and calendar side by side in equal boxes."""

    def __init__(self) -> None:
        super().__init__()
        self._today = date.today()
        self._year = self._today.year
        self._month = self._today.month

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)

    def go_prev_month(self) -> None:
        if self._month == 1:
            self._month = 12
            self._year -= 1
        else:
            self._month -= 1
        self.refresh()

    def go_next_month(self) -> None:
        if self._month == 12:
            self._month = 1
            self._year += 1
        else:
            self._month += 1
        self.refresh()

    def go_today(self) -> None:
        self._today = date.today()
        self._year = self._today.year
        self._month = self._today.month
        self.refresh()

    def _tick(self) -> None:
        self.refresh()

    def render(self) -> Text:
        now = datetime.now()
        scheme = get_scheme(now)

        clock_text = _render_clock(now, scheme)
        cal_text = _render_calendar(self._year, self._month, self._today, scheme)

        clock_lines = clock_text.split("\n")
        cal_lines = cal_text.split("\n")

        max_lines = max(len(clock_lines), len(cal_lines))
        gap = 3

        app_bg = scheme["app_bg"]
        gap_style = Style(color=app_bg, bgcolor=app_bg)

        result = Text()
        for i in range(max_lines):
            cl = clock_lines[i] if i < len(clock_lines) else Text()
            ca = cal_lines[i] if i < len(cal_lines) else Text()

            cw = _text_width(cl)
            result.append_text(cl)
            if cw < BOX_WIDTH:
                result.append(" " * (BOX_WIDTH - cw), style=gap_style)

            result.append(" " * gap, style=gap_style)

            result.append_text(ca)

            if i < max_lines - 1:
                result.append("\n")
        return result


# ═══════════════════════════════════════════════════════════════════════
# Application
# ═══════════════════════════════════════════════════════════════════════

class NDSStandbyApp(App):
    """TUI replica of the Nintendo DS standby screen."""

    CSS = """
    Screen {
        background: #F0F0F0;
    }

    #nav-hint {
        dock: bottom;
        height: 1;
        content-align: center middle;
        background: #E0E0E0;
    }

    MainScreen {
        width: auto;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("left", "prev_month", "Prev Month"),
        Binding("right", "next_month", "Next Month"),
        Binding("t", "go_today", "Today"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        self._main = MainScreen()
        yield self._main
        yield Label(" ← → navigate month   T today   Q quit", id="nav-hint")

    def on_mount(self) -> None:
        # Apply initial app background
        scheme = get_scheme()
        self.screen.styles.background = scheme["app_bg"]

    def action_prev_month(self) -> None:
        self._main.go_prev_month()

    def action_next_month(self) -> None:
        self._main.go_next_month()

    def action_go_today(self) -> None:
        self._main.go_today()


if __name__ == "__main__":
    NDSStandbyApp().run()
