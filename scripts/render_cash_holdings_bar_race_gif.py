from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "output" / "cash_holdings_mom_bar_race_last_2_years.html"
GIF_PATH = ROOT / "output" / "cash_holdings_mom_bar_race_last_2_years.gif"

SYMBOLS = ["liquidUSD", "liquidETH", "liquidBTC", "USDC", "USDT"]
COLORS = {
    "liquidUSD": "#1f6f8b",
    "liquidETH": "#7a4cc2",
    "liquidBTC": "#c47b1f",
    "USDC": "#2774ca",
    "USDT": "#1c8a5a",
}

WIDTH = 1100
HEIGHT = 620
SCALE = 2
FRAMES_PER_MONTH = 14
FRAME_DURATION_MS = 42


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size * SCALE)
    return ImageFont.load_default(size=size * SCALE)


FONT_TITLE = load_font(31, bold=True)
FONT_SUBTITLE = load_font(15)
FONT_META = load_font(13)
FONT_BAR = load_font(18, bold=True)
FONT_VALUE = load_font(17, bold=True)
FONT_MONTH = load_font(46, bold=True)
FONT_AXIS = load_font(12)


def parse_observations() -> list[list[object]]:
    html = HTML_PATH.read_text()
    match = re.search(r"const observations = (\[[\s\S]*?\]);", html)
    if not match:
        raise RuntimeError(f"Could not find observations array in {HTML_PATH}")
    return json.loads(match.group(1))


def month_range() -> list[str]:
    months: list[str] = []
    year, month = 2024, 4
    while (year, month) <= (2026, 4):
        months.append(date(year, month, 1).isoformat())
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def money(value: float) -> str:
    return f"${value:,.0f}"


def compact(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.0f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return "$0"


def month_label(month: str) -> str:
    labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    year = int(month[:4])
    month_num = int(month[5:7])
    return f"{labels[month_num - 1]} {year}"


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def build_month_rows() -> dict[str, dict[str, dict[str, float | str]]]:
    rows = {
        month: {
            symbol: {
                "symbol": symbol,
                "total_usd": 0.0,
                "total_eth": 0.0,
                "holders": 0.0,
                "month_end_day": "no balance",
            }
            for symbol in SYMBOLS
        }
        for month in month_range()
    }

    for month, month_end_day, symbol, total_usd, total_eth, holders in parse_observations():
        if month in rows and symbol in rows[month]:
            rows[month][symbol] = {
                "symbol": symbol,
                "total_usd": float(total_usd),
                "total_eth": float(total_eth),
                "holders": float(holders),
                "month_end_day": str(month_end_day),
            }
    return rows


def rank_positions(snapshot: dict[str, dict[str, float | str]]) -> dict[str, int]:
    ordered = sorted(SYMBOLS, key=lambda symbol: (-float(snapshot[symbol]["total_usd"]), symbol))
    return {symbol: rank for rank, symbol in enumerate(ordered)}


def draw_rounded_rect(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], radius: int, fill: str) -> None:
    draw.rounded_rectangle(tuple(v * SCALE for v in xy), radius=radius * SCALE, fill=fill)


def render_frame(
    current: dict[str, dict[str, float | str]],
    next_rows: dict[str, dict[str, float | str]],
    current_ranks: dict[str, int],
    next_ranks: dict[str, int],
    t: float,
    current_month: str,
    max_value: float,
) -> Image.Image:
    k = ease(t)
    img = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), "#ffffff")
    draw = ImageDraw.Draw(img)

    ink = "#17202a"
    muted = "#64717f"
    line = "#d9e0e7"
    left = 42
    top = 132
    chart_width = 760
    bar_height = 58
    gap = 20

    draw.text((left * SCALE, 28 * SCALE), "ether.fi Cash Holdings MoM Bar Race", fill=ink, font=FONT_TITLE)
    draw.text(
        (left * SCALE, 72 * SCALE),
        "Monthly latest-snapshot balances, zero-filled before each symbol appears",
        fill=muted,
        font=FONT_SUBTITLE,
    )

    total = 0.0
    values: dict[str, float] = {}
    y_positions: dict[str, float] = {}
    for symbol in SYMBOLS:
        value = float(current[symbol]["total_usd"]) + (
            float(next_rows[symbol]["total_usd"]) - float(current[symbol]["total_usd"])
        ) * k
        values[symbol] = value
        total += value
        y_positions[symbol] = current_ranks[symbol] + (next_ranks[symbol] - current_ranks[symbol]) * k

    draw.text((842 * SCALE, 30 * SCALE), "Latest selected total", fill=muted, font=FONT_META)
    draw.text((842 * SCALE, 52 * SCALE), money(total), fill=ink, font=FONT_TITLE)

    for tick in range(5):
        value = max_value * tick / 4
        x = left + (value / max_value) * chart_width
        if tick:
            draw.line([(x * SCALE, (top - 12) * SCALE), (x * SCALE, 530 * SCALE)], fill=line, width=SCALE)
        draw.text(((x - 18) * SCALE, 548 * SCALE), compact(value), fill=muted, font=FONT_AXIS)

    for symbol in sorted(SYMBOLS, key=lambda item: y_positions[item]):
        y = top + y_positions[symbol] * (bar_height + gap)
        width = max(0.0, values[symbol] / max_value * chart_width)
        if values[symbol] > 0:
            draw_rounded_rect(draw, (left, int(y), left + max(6, int(width)), int(y) + bar_height), 7, COLORS[symbol])
        draw.text(((left + 16) * SCALE, (y + 18) * SCALE), symbol, fill="#ffffff" if values[symbol] > 0 else muted, font=FONT_BAR)
        draw.text(((left + width + 14) * SCALE, (y + 18) * SCALE), money(values[symbol]), fill=ink, font=FONT_VALUE)

    draw.text((842 * SCALE, 430 * SCALE), month_label(current_month), fill=ink, font=FONT_MONTH)
    draw.text((845 * SCALE, 486 * SCALE), "through 2026-04-24" if current_month == "2026-04-01" else "month-end snapshot", fill=muted, font=FONT_META)
    draw.text((left * SCALE, 594 * SCALE), "Source: ether.fi analytics catalog, Cash AUM balances", fill=muted, font=FONT_META)

    return img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def main() -> None:
    monthly = build_month_rows()
    months = month_range()
    max_value = max(float(row["total_usd"]) for snapshot in monthly.values() for row in snapshot.values())
    frames: list[Image.Image] = []

    for idx, month in enumerate(months):
        next_month = months[min(idx + 1, len(months) - 1)]
        current = monthly[month]
        next_rows = monthly[next_month]
        current_ranks = rank_positions(current)
        next_ranks = rank_positions(next_rows)
        frame_count = FRAMES_PER_MONTH if idx < len(months) - 1 else FRAMES_PER_MONTH * 2
        for frame in range(frame_count):
            t = frame / frame_count
            frames.append(render_frame(current, next_rows, current_ranks, next_ranks, t, month, max_value))

    GIF_PATH.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        GIF_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {GIF_PATH} ({len(frames)} frames)")


if __name__ == "__main__":
    main()
