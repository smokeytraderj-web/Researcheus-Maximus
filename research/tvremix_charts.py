"""Chart rendering for the standalone Technical Analysis feature (TV Remix data only).

Mirrors the rendering approach in ``research/technical.py`` (manual candlestick via
vlines/Rectangle, matplotlib Agg backend, annotated horizontal levels) but operates on
raw TV Remix OHLCV bars rather than a Yahoo-sourced pandas history frame.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(os.getenv("TEMP", "/tmp")) / "researcheus-matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from core.models import TVLevel

NAVY = "#1B2A4A"
GOLD = "#BFA054"
BLUE = "#5378A5"
MUTED = "#7A8491"
GREEN = "#3F7D62"
RED = "#A34B4B"


def _bars_to_frame(bars: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(bars)
    frame["date"] = pd.to_datetime(frame["t"], unit="s", utc=True)
    frame = frame.set_index("date").sort_index()
    return frame.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})


def render_tvremix_price_chart(bars: list[dict], levels: tuple[TVLevel, ...], current_price: float, ticker: str, destination: Path) -> Path:
    """Render an annotated candlestick chart with Fibonacci/structure levels."""
    if not bars:
        raise ValueError("No OHLCV bars were available to render the price chart.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = _bars_to_frame(bars).tail(160)
    close = frame["close"].astype(float)
    open_price = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)

    fig, ax = plt.subplots(figsize=(11, 5.8))
    fig.patch.set_facecolor("white")
    x_values = mdates.date2num(frame.index.to_pydatetime())
    spacing = float(np.median(np.diff(x_values))) if len(x_values) > 1 else 1.0
    candle_width = max(0.32, min(0.72, spacing * 0.64))
    for x_value, opening, maximum, minimum, closing in zip(x_values, open_price, high, low, close):
        candle_color = GREEN if closing >= opening else RED
        ax.vlines(x_value, minimum, maximum, color=candle_color, linewidth=0.65, alpha=0.88, zorder=2)
        body_bottom = min(opening, closing)
        body_height = max(abs(closing - opening), max(closing * 0.0006, 0.01))
        ax.add_patch(
            Rectangle(
                (x_value - candle_width / 2, body_bottom),
                candle_width,
                body_height,
                facecolor=candle_color,
                edgecolor=candle_color,
                linewidth=0.45,
                alpha=0.86,
                zorder=3,
            )
        )

    for level in levels:
        if level.label == "Now":
            continue
        ax.axhline(level.price, color=GOLD if "Fib" in level.label else MUTED, linestyle="--", linewidth=0.8, alpha=0.75, zorder=1)
    ax.axhline(current_price, color=NAVY, linestyle="-", linewidth=1.1, alpha=0.9, zorder=5)

    # Declutter: labels for nearby price levels overlap when placed at their raw
    # data position, so cascade each one down just enough to clear the label above it
    # (same min-gap approach used for the report's price ladder).
    ax.set_xlim(x_values[0], x_values[-1])
    ax.relim()
    ax.autoscale_view()
    fig.canvas.draw()
    label_entries = [(f"{level.label} ${level.price:,.2f}", level.price, False) for level in levels if level.label != "Now"]
    label_entries.append((f"Now ${current_price:,.2f}", current_price, True))
    edge_x = x_values[-1]
    to_display = ax.transData.transform
    to_data = ax.transData.inverted().transform
    placed = sorted(
        ({"text": text, "price": price, "now": is_now, "y_px": to_display((edge_x, price))[1]} for text, price, is_now in label_entries),
        key=lambda item: item["y_px"],
    )
    min_gap_px = 15.0
    for i in range(1, len(placed)):
        if placed[i]["y_px"] - placed[i - 1]["y_px"] < min_gap_px:
            placed[i]["y_px"] = placed[i - 1]["y_px"] + min_gap_px
    x_px = to_display((edge_x, 0))[0]
    for item in placed:
        adjusted_y = to_data((x_px, item["y_px"]))[1]
        ax.annotate(
            item["text"],
            xy=(edge_x, adjusted_y),
            xytext=(6, 0),
            textcoords="offset points",
            fontsize=7.2 if item["now"] else 6.8,
            color=NAVY,
            fontweight="bold" if item["now"] else "normal",
            va="center",
            zorder=6,
        )

    ax.set_title(f"{ticker} | Daily Price Structure (TV Remix)", loc="left", color=NAVY, fontsize=11.2, fontweight="bold")
    ax.set_ylabel("Price (USD)", color=MUTED, fontsize=8)
    ax.grid(axis="y", alpha=0.14, linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D8DDE6")
    ax.spines["bottom"].set_color("#D8DDE6")
    ax.tick_params(colors=MUTED, labelsize=7.6)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.margins(x=0.03)
    fig.tight_layout()
    fig.savefig(destination, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return destination


def render_tvremix_sparkline(bars: list[dict], destination: Path) -> Path:
    """Render a small area sparkline of recent closes."""
    if not bars:
        raise ValueError("No OHLCV bars were available to render the sparkline.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = _bars_to_frame(bars).tail(60)
    close = frame["close"].astype(float)
    color = GREEN if float(close.iloc[-1]) >= float(close.iloc[0]) else RED

    fig, ax = plt.subplots(figsize=(4.6, 1.7))
    fig.patch.set_facecolor("white")
    ax.plot(frame.index, close, color=color, linewidth=1.3, zorder=3)
    ax.fill_between(frame.index, close, close.min(), color=color, alpha=0.10, zorder=2)
    ax.axis("off")
    fig.tight_layout(pad=0.2)
    fig.savefig(destination, dpi=190, bbox_inches="tight", facecolor="white", transparent=False)
    plt.close(fig)
    return destination
