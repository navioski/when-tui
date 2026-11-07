# when-tui

A **windowed clock and calendar drawn entirely in characters** — title bar, two
panes, status bar, a big analog face and a hand-built 5x7 pixel font for the
time. Runs in the terminal with [Textual](https://textual.textualize.io/).

![when-tui](shots/when-tui.png)

The palette follows the time of day (`morning` → `afternoon` → `evening` → `night`),
the way the DS tints its own menu.

## Requirements

- Python **3.10+**
- [`textual`](https://textual.textualize.io/) (pinned in `requirements.txt`)
- A terminal of at least **96 × 36** cells

## Install & run

```bash
git clone https://github.com/navioski/when-tui.git
cd when-tui

# with uv (recommended — creates the venv for you)
uv run when.py

# or plain pip
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./when.py
```

`when.py` is executable and re-executes itself through `./.venv/bin/python` when
that venv exists, so `./when.py` is enough once the venv is set up. Without a
venv it prints the three commands above instead of a traceback.

## Keys

| Key | Action |
|---|---|
| <kbd>←</kbd> / <kbd>→</kbd> | previous / next month |
| <kbd>t</kbd> | jump back to today |
| <kbd>q</kbd> | quit |

## What's on screen

| Part | What it is |
|---|---|
| Title bar | `░▒▓ WHEN-TUI ▓▒░`, date and 24-hour time, accent hairline underneath |
| Panes | Inset bevels: light on the top/left edge, dark on the bottom/right |
| Clock pane | Section caption, the analog face, then the time in a **5x7 pixel font**, then the weekday and date |
| Clock face | Rim, 12 hour ticks, hour/minute/second hands, a glowing tip on the second hand, and **a day-progress arc** — the rim is repainted clockwise as the 24 hours pass |
| Calendar pane | `‹ MM/YYYY ›`, a contiguous weekday bar (Sundays pink, Saturdays blue), days from the neighbouring months dimmed, today bracketed in the accent colour |
| Calendar footer | ISO week and day of the year (`W47 · DAY 322/365`) |
| Status bar | Segmented key hints on the left, weekday on the right |

The palette rotates with the time of day: `morning`, `afternoon`, `evening`,
`night` — each with its own accent, arc and glow colour.

## How it's drawn

Two layers do all the work:

1. A `Canvas` of `(char, fg, bg)` cells — one character per cell, colours carried
   by the style. Boxes, cards, the calendar grid and all text live here.
2. A `PixelCanvas` for the clock face: each pixel is half a cell tall, so a cell
   is rendered as `▀` with the top pixel as the foreground colour and the bottom
   pixel as the background colour. That doubles the vertical resolution and is
   what makes the face look round instead of stepped.

No images, no fonts, no assets — everything is characters and colour.

## Verified

Tested on **Python 3.14.5 + textual 8.2.8** (macOS, 2026-11), rendered as a 96 × 38
canvas.
