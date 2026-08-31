"""Deterministic technical-analysis calculations and chart rendering."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(os.getenv("TEMP", "/tmp")) / "researcheus-matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from core.assessments import technical_setup
from core.models import HistoricalTradeCase, Horizon, Rating, SpecialistFinding, Strategy, TechnicalActionPlan


_HOVER_PAD_INCHES = 0.1  # matches savefig's default pad when bbox_inches="tight"


def _hover_sidecar(
    fig,
    ax,
    destination: Path,
    x_values,
    labels: list[str],
    series: list[tuple[str, list[str]]],
    primary: list[float],
    bottom_ax=None,
) -> None:
    """Write the read-out data for a chart's hover overlay beside its PNG.

    The report embeds this so the browser can show the exact dated values behind
    a chart instead of only a picture of them.  ``savefig(bbox_inches="tight")``
    crops the figure, so the plot rectangle in the saved image is *not*
    ``ax.get_position()``; it has to be recomputed against the same tight bbox
    savefig will use, or the overlay drifts away from the pixels underneath.

    Positions are stored as 0-1 fractions of the saved image, so the overlay
    stays aligned at any rendered width without the browser knowing anything
    about dates or prices.

    ``bottom_ax`` extends the crosshair down through a second stacked panel (RSI
    over MACD, say) so one hover reads across both.  Pass an empty ``primary``
    for such charts: the marker dot only makes sense against a single y-axis.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    tight = fig.get_tightbbox(renderer)
    origin_x = tight.x0 - _HOVER_PAD_INCHES
    origin_y = tight.y0 - _HOVER_PAD_INCHES
    total_width = tight.width + 2 * _HOVER_PAD_INCHES
    total_height = tight.height + 2 * _HOVER_PAD_INCHES
    box = ax.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
    lower = (
        box
        if bottom_ax is None
        else bottom_ax.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
    )

    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()
    x_span = (x_max - x_min) or 1.0
    y_span = (y_max - y_min) or 1.0
    x_positions = list(x_values)

    points = []
    for index, label in enumerate(labels):
        if index >= len(x_positions):
            break
        value = primary[index] if index < len(primary) else None
        points.append(
            {
                "x": round((float(x_positions[index]) - x_min) / x_span, 5),
                # Image y grows downward, so invert against the axis range.
                "y": None if value is None else round((y_max - value) / y_span, 5),
                "label": label,
                "values": [column[index] if index < len(column) else "" for _name, column in series],
            }
        )

    payload = {
        "frame": {
            "left": round((box.x0 - origin_x) / total_width, 5),
            "right": round((box.x1 - origin_x) / total_width, 5),
            "top": round(1.0 - (box.y1 - origin_y) / total_height, 5),
            "bottom": round(1.0 - (lower.y0 - origin_y) / total_height, 5),
        },
        "series": [name for name, _column in series],
        "points": points,
    }
    destination.with_suffix(destination.suffix + ".json").write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )


@dataclass(frozen=True, slots=True)
class VolumeProfile:
    """Volume traded at each price level over the analysed window.

    ``point_of_control`` is the most-traded price; ``value_area_low/high`` bound
    the prices covering ``VALUE_AREA_SHARE`` of total volume around it.  These are
    the levels that tend to act as support and resistance because real size
    changed hands there, which a time-based volume bar cannot show.
    """

    prices: tuple[float, ...]
    volumes: tuple[float, ...]
    point_of_control: float
    value_area_low: float
    value_area_high: float
    total_volume: float


VALUE_AREA_SHARE = 0.70


def volume_profile(history: pd.DataFrame, bins: int = 26) -> VolumeProfile | None:
    """Distribute each session's volume across the price range it actually traded.

    Returns ``None`` when the security reports no usable volume (some funds), so
    callers omit the evidence rather than publishing an empty or invented profile.
    """
    frame = history.dropna(subset=["High", "Low", "Close"]).copy()
    if "Volume" not in frame.columns or frame.empty:
        return None
    volume = frame["Volume"].astype(float).fillna(0.0)
    if float(volume.abs().sum()) <= 0:
        return None

    high = frame["High"].astype(float)
    low = frame["Low"].astype(float)
    floor_price, ceiling_price = float(low.min()), float(high.max())
    if not np.isfinite(floor_price) or not np.isfinite(ceiling_price) or ceiling_price <= floor_price:
        return None

    edges = np.linspace(floor_price, ceiling_price, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    buckets = np.zeros(bins, dtype=float)

    # Spread a session's volume evenly over the bins its range covers, rather than
    # dumping it all at the close -- a wide-range day genuinely traded throughout.
    for bar_low, bar_high, bar_volume in zip(low.to_numpy(), high.to_numpy(), volume.to_numpy()):
        if bar_volume <= 0:
            continue
        first = int(np.clip(np.searchsorted(edges, bar_low, side="right") - 1, 0, bins - 1))
        last = int(np.clip(np.searchsorted(edges, bar_high, side="left") - 1, 0, bins - 1))
        if last < first:
            last = first
        buckets[first : last + 1] += bar_volume / (last - first + 1)

    total = float(buckets.sum())
    if total <= 0:
        return None

    control_index = int(buckets.argmax())
    # Grow outward from the point of control, always taking the heavier side, until
    # the requested share of volume is enclosed -- the standard value-area rule.
    low_index = high_index = control_index
    covered = buckets[control_index]
    while covered < total * VALUE_AREA_SHARE and (low_index > 0 or high_index < bins - 1):
        below = buckets[low_index - 1] if low_index > 0 else -1.0
        above = buckets[high_index + 1] if high_index < bins - 1 else -1.0
        if above >= below:
            high_index += 1
            covered += buckets[high_index]
        else:
            low_index -= 1
            covered += buckets[low_index]

    return VolumeProfile(
        prices=tuple(float(value) for value in centers),
        volumes=tuple(float(value) for value in buckets),
        point_of_control=float(centers[control_index]),
        value_area_low=float(edges[low_index]),
        value_area_high=float(edges[high_index + 1]),
        total_volume=total,
    )


def volume_profile_insight(profile: VolumeProfile, price: float) -> str:
    """One decision-relevant sentence about where price sits in the profile."""
    control = profile.point_of_control
    if price > profile.value_area_high:
        location = (
            f"Price ${price:,.2f} is above the value area, so there is little traded volume "
            f"overhead; ${profile.value_area_high:,.2f} is the first shelf back inside it."
        )
    elif price < profile.value_area_low:
        location = (
            f"Price ${price:,.2f} is below the value area, leaving heavy supply overhead; "
            f"${profile.value_area_low:,.2f} is the first hurdle back inside it."
        )
    else:
        side = "above" if price >= control else "below"
        location = (
            f"Price ${price:,.2f} is inside the value area and {side} the point of control, "
            f"which tends to act as a magnet while the range holds."
        )
    return (
        f"Most volume changed hands at ${control:,.2f}, with "
        f"{VALUE_AREA_SHARE:.0%} of it between ${profile.value_area_low:,.2f} and "
        f"${profile.value_area_high:,.2f}. {location}"
    )


NAVY = "#1B2A4A"
GOLD = "#BFA054"
BLUE = "#5378A5"
MUTED = "#7A8491"
GREEN = "#3F7D62"
RED = "#A34B4B"
PALE = "#F3F5F8"


@dataclass(frozen=True, slots=True)
class TechnicalSnapshot:
    price: float
    sma20: float
    sma50: float
    sma200: float | None
    rsi14: float
    macd: float
    macd_signal: float
    atr14: float
    volume_ratio: float
    support: float
    resistance: float
    return_1m: float
    return_3m: float
    fib_swing_low: float
    fib_swing_high: float
    fib_38_2: float
    fib_50: float
    fib_61_8: float
    score: int
    fibonacci_range_label: str = "Six-month"
    analysis_return: float | None = None
    performance_label: str = "Three-month"
    volume_available: bool = True

    def as_metrics(self) -> tuple[tuple[str, str], ...]:
        sma200 = "Unavailable" if self.sma200 is None else f"${self.sma200:,.2f}"
        metrics = [
            (
                f"{self.performance_label} return",
                f"{(self.analysis_return if self.analysis_return is not None else self.return_3m):+.1%}",
            ),
            ("20-day moving average", f"${self.sma20:,.2f}"),
            ("50-day moving average", f"${self.sma50:,.2f}"),
            ("200-day moving average", sma200),
            ("RSI (14)", f"{self.rsi14:.1f}"),
            ("MACD / signal", f"{self.macd:.2f} / {self.macd_signal:.2f}"),
            ("ATR (14)", f"${self.atr14:,.2f}"),
            ("60-day support / resistance", f"${self.support:,.2f} / ${self.resistance:,.2f}"),
            (
                f"{self.fibonacci_range_label} Fibonacci swing range",
                f"${self.fib_swing_low:,.2f} / ${self.fib_swing_high:,.2f}",
            ),
            (
                "Fibonacci 38.2% / 50% / 61.8%",
                f"${self.fib_38_2:,.2f} / ${self.fib_50:,.2f} / ${self.fib_61_8:,.2f}",
            ),
        ]
        if self.volume_available:
            metrics.insert(7, ("Volume vs. 20-day avg.", f"{self.volume_ratio:.2f}x"))
        return tuple(metrics)


def _rsi(close: pd.Series, periods: int = 14) -> pd.Series:
    change = close.diff()
    gains = change.clip(lower=0).ewm(alpha=1 / periods, adjust=False).mean()
    losses = (-change.clip(upper=0)).ewm(alpha=1 / periods, adjust=False).mean()
    rs = gains / losses.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def historical_trade_examples(
    history: pd.DataFrame,
    max_cases: int = 3,
) -> tuple[HistoricalTradeCase, ...]:
    """Find reproducible long-entry case studies without using future data in the signal."""
    frame = history.dropna(subset=["Close", "High", "Low", "Volume"]).copy()
    if len(frame) < 80:
        return ()
    close = frame["Close"].astype(float)
    high = frame["High"].astype(float)
    low = frame["Low"].astype(float)
    open_price = frame["Open"].astype(float) if "Open" in frame else close
    volume = frame["Volume"].astype(float).fillna(0)
    frame["SMA20"] = close.rolling(20).mean()
    frame["SMA50"] = close.rolling(50).mean()
    frame["RSI"] = _rsi(close)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    frame["MACD"] = ema12 - ema26
    frame["MACDSignal"] = frame["MACD"].ewm(span=9, adjust=False).mean()
    previous = close.shift(1)
    true_range = pd.concat([(high - low), (high - previous).abs(), (low - previous).abs()], axis=1).max(axis=1)
    frame["ATR"] = true_range.rolling(14).mean()
    frame["VolumeRatio"] = volume / volume.rolling(20).mean().replace(0, np.nan)
    frame["Prior10Low"] = low.shift(1).rolling(10).min()
    signal = (
        (close > frame["SMA20"])
        & (close.shift(1) <= frame["SMA20"].shift(1))
        & (frame["SMA50"] > frame["SMA50"].shift(10))
        & (frame["MACD"] > frame["MACD"].shift(1))
        & frame["RSI"].between(45, 72)
        & (frame["VolumeRatio"] >= 0.8)
    )
    cases = []
    last_exit_index = -1
    candidate_positions = np.flatnonzero(signal.fillna(False).to_numpy())
    for signal_index in candidate_positions:
        entry_index = signal_index + 1
        if entry_index >= len(frame) or entry_index <= last_exit_index:
            continue
        entry = float(open_price.iloc[entry_index])
        if not np.isfinite(entry) or entry <= 0:
            entry = float(close.iloc[entry_index])
        atr = float(frame["ATR"].iloc[signal_index])
        prior_low = float(frame["Prior10Low"].iloc[signal_index])
        volatility_stop = entry - 2.0 * atr
        structure_stop = prior_low - 0.25 * atr
        initial_stop = min(entry * 0.995, max(volatility_stop, structure_stop))
        trailing_stop = initial_stop
        exit_index = min(entry_index + 40, len(frame) - 1)
        exit_price = float(close.iloc[exit_index])
        exit_reason = "Forty-session review exit"
        for index in range(entry_index + 1, min(entry_index + 41, len(frame))):
            if float(low.iloc[index]) <= trailing_stop:
                exit_index = index
                exit_price = trailing_stop
                exit_reason = "Protective stop was reached"
                break
            if float(close.iloc[index]) < float(frame["SMA20"].iloc[index]) and float(frame["MACD"].iloc[index]) < float(frame["MACDSignal"].iloc[index]):
                exit_index = index
                exit_price = float(close.iloc[index])
                exit_reason = "Price lost the 20-day trend while MACD weakened"
                break
            new_trailing_stop = max(
                float(frame["SMA20"].iloc[index]) - 0.75 * float(frame["ATR"].iloc[index]),
                float(close.iloc[entry_index:index + 1].max()) - 2.5 * float(frame["ATR"].iloc[index]),
            )
            trailing_stop = max(trailing_stop, min(new_trailing_stop, float(close.iloc[index]) * 0.995))
        trade_return = exit_price / entry - 1
        cases.append(
            HistoricalTradeCase(
                signal_date=frame.index[signal_index].date().isoformat(),
                entry_date=frame.index[entry_index].date().isoformat(),
                entry_price=entry,
                initial_stop=initial_stop,
                exit_date=frame.index[exit_index].date().isoformat(),
                exit_price=exit_price,
                return_pct=trade_return,
                outcome="Gain" if trade_return > 0 else "Loss",
                rationale=(
                    f"Close reclaimed the 20-day average while the 50-day trend was rising; "
                    f"RSI was {float(frame['RSI'].iloc[signal_index]):.1f}, MACD was improving, and volume was "
                    f"{float(frame['VolumeRatio'].iloc[signal_index]):.2f}x its 20-day average."
                ),
                exit_reason=exit_reason,
            )
        )
        last_exit_index = exit_index
        if len(cases) >= max_cases:
            break
    return tuple(cases)


def render_trade_case_chart(
    history: pd.DataFrame,
    ticker: str,
    trade: HistoricalTradeCase,
    destination: Path,
) -> Path:
    """Render a real-market historical chart with entry, initial stop, and exit markers."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = history.dropna(subset=["Close"]).copy()
    entry_stamp = pd.Timestamp(trade.entry_date)
    exit_stamp = pd.Timestamp(trade.exit_date)
    entry_location = frame.index.get_indexer([entry_stamp], method="nearest")[0]
    exit_location = frame.index.get_indexer([exit_stamp], method="nearest")[0]
    start = max(0, entry_location - 25)
    end = min(len(frame), exit_location + 16)
    view = frame.iloc[start:end]
    close = view["Close"].astype(float)
    sma20 = frame["Close"].astype(float).rolling(20).mean().iloc[start:end]
    sma50 = frame["Close"].astype(float).rolling(50).mean().iloc[start:end]
    fig, (ax, vol) = plt.subplots(2, 1, figsize=(10.5, 5.6), gridspec_kw={"height_ratios": [4, 1]}, sharex=True)
    fig.patch.set_facecolor("white")
    ax.plot(view.index, close, color=NAVY, linewidth=1.8, label="Close")
    ax.plot(view.index, sma20, color=GOLD, linewidth=1.1, label="SMA 20")
    ax.plot(view.index, sma50, color=BLUE, linewidth=1.1, label="SMA 50")
    ax.scatter(pd.Timestamp(trade.entry_date), trade.entry_price, marker="^", s=80, color="#2E7D52", zorder=5, label=f"Entry ${trade.entry_price:,.2f}")
    ax.scatter(pd.Timestamp(trade.exit_date), trade.exit_price, marker="X", s=75, color="#A94442", zorder=5, label=f"Exit ${trade.exit_price:,.2f}")
    ax.axhline(trade.initial_stop, color="#A94442", linestyle="--", linewidth=1.0, label=f"Initial stop ${trade.initial_stop:,.2f}")
    ax.set_title(f"{ticker} - Historical Trade Case: {trade.entry_date} Entry", loc="left", color=NAVY, fontweight="bold")
    ax.set_ylabel("Price (USD)")
    ax.grid(alpha=0.18)
    ax.legend(ncol=3, fontsize=8, frameon=False, loc="upper left")
    colors_v = np.where(close.diff().fillna(0) >= 0, "#6E9D85", "#C77A7A")
    vol.bar(view.index, view["Volume"].fillna(0).astype(float), color=colors_v, width=1.0, alpha=0.75)
    vol.set_ylabel("Volume")
    vol.grid(axis="y", alpha=0.15)
    vol.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    vol.xaxis.set_major_formatter(mdates.ConciseDateFormatter(vol.xaxis.get_major_locator()))
    fig.tight_layout()
    fig.savefig(destination, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return destination


def analyze_history(history: pd.DataFrame) -> TechnicalSnapshot:
    required = {"Close", "High", "Low", "Volume"}
    if history.empty or not required.issubset(history.columns):
        raise ValueError("Live price history is incomplete.")
    frame = history.dropna(subset=["Close", "High", "Low"]).copy()
    if len(frame) < 60:
        raise ValueError("At least 60 trading sessions are required for technical analysis.")
    close = frame["Close"].astype(float)
    high = frame["High"].astype(float)
    low = frame["Low"].astype(float)
    volume = frame["Volume"].astype(float).fillna(0)
    volume_available = bool(float(volume.abs().sum()) > 0)
    sma20_s = close.rolling(20).mean()
    sma50_s = close.rolling(50).mean()
    sma200_s = close.rolling(200).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_s = ema12 - ema26
    signal_s = macd_s.ewm(span=9, adjust=False).mean()
    previous = close.shift(1)
    true_range = pd.concat([(high - low), (high - previous).abs(), (low - previous).abs()], axis=1).max(axis=1)
    atr = true_range.rolling(14).mean()
    price = float(close.iloc[-1])
    sma20 = float(sma20_s.iloc[-1])
    sma50 = float(sma50_s.iloc[-1])
    raw_sma200 = sma200_s.iloc[-1]
    sma200 = None if pd.isna(raw_sma200) else float(raw_sma200)
    rsi14 = float(_rsi(close).iloc[-1])
    macd = float(macd_s.iloc[-1])
    macd_signal = float(signal_s.iloc[-1])
    atr14 = float(atr.iloc[-1])
    vol_avg = float(volume.rolling(20).mean().iloc[-1])
    volume_ratio = float(volume.iloc[-1] / vol_avg) if vol_avg > 0 else 0.0
    support = float(low.tail(60).min())
    resistance = float(high.tail(60).max())
    custom_range = bool(history.attrs.get("custom_range"))
    fibonacci_window = frame if custom_range else frame.tail(min(126, len(frame)))
    fibonacci_range_label = str(history.attrs.get("analysis_range_label") or "Six-month")
    fib_swing_low = float(fibonacci_window["Low"].astype(float).min())
    fib_swing_high = float(fibonacci_window["High"].astype(float).max())
    fib_range = fib_swing_high - fib_swing_low
    fib_38_2 = fib_swing_high - fib_range * 0.382
    fib_50 = fib_swing_high - fib_range * 0.500
    fib_61_8 = fib_swing_high - fib_range * 0.618
    return_1m = float(price / close.iloc[-22] - 1) if len(close) >= 22 else 0.0
    return_3m = float(price / close.iloc[-64] - 1) if len(close) >= 64 else 0.0
    analysis_return = float(price / close.iloc[0] - 1) if custom_range else return_3m
    performance_label = "Analysis-range" if custom_range else "Three-month"
    score = 0
    score += 1 if price > sma20 else -1
    score += 1 if price > sma50 else -1
    if sma200 is not None:
        score += 1 if price > sma200 else -1
    score += 1 if macd > macd_signal else -1
    if rsi14 >= 70:
        score -= 1
    elif rsi14 >= 50:
        score += 1
    elif rsi14 < 30:
        score += 0
    else:
        score -= 1
    score += 1 if analysis_return > 0 else -1
    score += 1 if price >= fib_50 else -1
    return TechnicalSnapshot(
        price=price,
        sma20=sma20,
        sma50=sma50,
        sma200=sma200,
        rsi14=rsi14,
        macd=macd,
        macd_signal=macd_signal,
        atr14=atr14,
        volume_ratio=volume_ratio,
        support=support,
        resistance=resistance,
        return_1m=return_1m,
        return_3m=return_3m,
        fib_swing_low=fib_swing_low,
        fib_swing_high=fib_swing_high,
        fib_38_2=fib_38_2,
        fib_50=fib_50,
        fib_61_8=fib_61_8,
        score=score,
        fibonacci_range_label=fibonacci_range_label,
        analysis_return=analysis_return,
        performance_label=performance_label,
        volume_available=volume_available,
    )


def _rating(score: int) -> Rating:
    if score >= 6:
        return Rating.STRONG_BUY
    if score >= 4:
        return Rating.BUY
    if score >= 2:
        return Rating.ADD
    if score >= -1:
        return Rating.HOLD
    if score >= -3:
        return Rating.REDUCE
    return Rating.SELL


def technical_finding(snapshot: TechnicalSnapshot) -> SpecialistFinding:
    if snapshot.price >= snapshot.fib_38_2:
        fibonacci_text = f"above the 38.2% retracement, in the upper portion of the {snapshot.fibonacci_range_label.lower()} swing range"
    elif snapshot.price >= snapshot.fib_50:
        fibonacci_text = "between the 38.2% and 50% retracement levels"
    elif snapshot.price >= snapshot.fib_61_8:
        fibonacci_text = "between the 50% and 61.8% retracement levels"
    else:
        fibonacci_text = "below the 61.8% retracement, signaling a deeper technical retracement"
    rating = _rating(snapshot.score)
    return SpecialistFinding(
        rating,
        trend_decision_insight(snapshot, rating),
        (
            f"Price ${snapshot.price:,.2f} versus 20-day SMA ${snapshot.sma20:,.2f} and 50-day SMA ${snapshot.sma50:,.2f}.",
            (
                f"One-month return {snapshot.return_1m:+.1%}; "
                f"{snapshot.performance_label.lower()} return {(snapshot.analysis_return if snapshot.analysis_return is not None else snapshot.return_3m):+.1%}."
            ),
            f"MACD {snapshot.macd:.2f} versus signal {snapshot.macd_signal:.2f}; RSI (14) {snapshot.rsi14:.1f}.",
            f"60-day observed range ${snapshot.support:,.2f} to ${snapshot.resistance:,.2f}; ATR (14) ${snapshot.atr14:,.2f}.",
            (
                f"Fibonacci: price is {fibonacci_text}; 38.2%, 50%, and 61.8% levels are "
                f"${snapshot.fib_38_2:,.2f}, ${snapshot.fib_50:,.2f}, and ${snapshot.fib_61_8:,.2f}."
            ),
            (
                f"Latest volume is {snapshot.volume_ratio:.2f}x the 20-day average."
                if snapshot.volume_available
                else "Daily trading volume was not reported for this fund, so volume was excluded from the setup."
            ),
        ),
    )


def trend_decision_insight(snapshot: TechnicalSnapshot, rating: Rating) -> str:
    """Explain how the moving-average structure affects the technical conclusion."""
    setup = technical_setup(rating).lower()
    if snapshot.price > snapshot.sma20 and snapshot.price > snapshot.sma50:
        return (
            f"Because price ${snapshot.price:,.2f} is above both the 20-day (${snapshot.sma20:,.2f}) and 50-day "
            f"(${snapshot.sma50:,.2f}) averages, trend evidence supports the {setup} setup. A confirmed close above "
            f"${snapshot.resistance:,.2f} would strengthen the case; a close back below ${snapshot.sma20:,.2f} would weaken it."
        )
    reclaim = max(snapshot.sma20, snapshot.sma50)
    return (
        f"Because price ${snapshot.price:,.2f} is below at least one key trend average, the chart does not yet confirm a durable advance. "
        f"A close above about ${reclaim:,.2f} would improve the {setup} setup, while a break below ${snapshot.support:,.2f} would keep downside risk open."
    )


def fibonacci_decision_insight(snapshot: TechnicalSnapshot, rating: Rating) -> str:
    """Translate the current Fibonacci position into the next confirmation and risk level."""
    setup = technical_setup(rating).lower()
    if snapshot.price >= snapshot.fib_38_2:
        return (
            f"Because price is above the 38.2% level at ${snapshot.fib_38_2:,.2f}, the upper part of the swing range remains in play. "
            f"Holding that level supports the {setup} setup, and a confirmed break above ${snapshot.resistance:,.2f} would point to the "
            f"${snapshot.fib_swing_high:,.2f} swing high as the next reference."
        )
    if snapshot.price >= snapshot.fib_50:
        return (
            f"Price is between the 50% (${snapshot.fib_50:,.2f}) and 38.2% (${snapshot.fib_38_2:,.2f}) levels. "
            f"Reclaiming ${snapshot.fib_38_2:,.2f} would improve the {setup} setup; losing ${snapshot.fib_50:,.2f} would put "
            f"${snapshot.fib_61_8:,.2f} in play."
        )
    if snapshot.price >= snapshot.fib_61_8:
        return (
            f"Price is holding between the 61.8% (${snapshot.fib_61_8:,.2f}) and 50% (${snapshot.fib_50:,.2f}) retracements. "
            f"A close above ${snapshot.fib_50:,.2f} is the next repair signal for the {setup} setup; a break below "
            f"${snapshot.fib_61_8:,.2f} would expose the ${snapshot.fib_swing_low:,.2f} swing low."
        )
    return (
        f"Price is below the 61.8% retracement at ${snapshot.fib_61_8:,.2f}, so the prior advance has materially weakened. "
        f"The {setup} setup would need a close back above that level to improve; otherwise the ${snapshot.fib_swing_low:,.2f} swing low remains the next risk reference."
    )


def momentum_decision_insight(snapshot: TechnicalSnapshot, rating: Rating) -> str:
    """Explain whether RSI and MACD confirm or challenge the technical conclusion."""
    setup = technical_setup(rating).lower()
    macd_state = "above" if snapshot.macd > snapshot.macd_signal else "below"
    if snapshot.macd > snapshot.macd_signal and 45 <= snapshot.rsi14 < 70:
        implication = f"momentum confirms the {setup} setup"
    elif snapshot.macd <= snapshot.macd_signal and snapshot.rsi14 < 45:
        implication = f"momentum does not confirm an upgrade from the {setup} setup"
    elif snapshot.rsi14 >= 70:
        implication = "momentum is strong but stretched, so chasing price carries higher reversal risk"
    elif snapshot.rsi14 <= 30:
        implication = "the stock is oversold, but that is only an early watch signal until MACD and price turn higher"
    else:
        implication = f"momentum is mixed and therefore leaves the {setup} setup unchanged"
    return (
        f"MACD ({snapshot.macd:.2f}) is {macd_state} its signal ({snapshot.macd_signal:.2f}) and RSI is {snapshot.rsi14:.1f}; "
        f"{implication}."
    )


def windowed_return_pct(history: pd.DataFrame, *, custom_range: bool, minimum_sessions: int = 20) -> float | None:
    """Total return over the same lookback window used for relative-performance evidence.

    Shared by the relative-performance narrative below and by the Conviction
    Checklist, so both read "relative strength" over an identical window.
    """
    if history is None or "Close" not in history:
        return None
    closes = history["Close"].dropna().astype(float)
    required = minimum_sessions if custom_range else 64
    if len(closes) < required:
        return None
    start_index = 0 if custom_range else -64
    return float(closes.iloc[-1] / closes.iloc[start_index] - 1)


def incorporate_relative_performance(
    finding: SpecialistFinding,
    primary_history: pd.DataFrame,
    comparison_histories: dict[str, pd.DataFrame],
) -> tuple[SpecialistFinding, tuple[tuple[str, str], ...], str]:
    """Add transparent three-month relative strength evidence to the technical view."""
    primary = primary_history["Close"].dropna().astype(float)
    custom_range = bool(primary_history.attrs.get("custom_range"))
    minimum_sessions = 20 if custom_range else 64
    if len(primary) < minimum_sessions or not comparison_histories:
        return finding, (), "Relative-performance evidence was unavailable."

    primary_return = float(primary.iloc[-1] / primary.iloc[0 if custom_range else -64] - 1)
    return_label = "analysis range" if custom_range else "three months"
    relative_results = []
    metrics = []
    for symbol, history in comparison_histories.items():
        comparison = history["Close"].dropna().astype(float)
        if len(comparison) < minimum_sessions:
            continue
        comparison_return = float(comparison.iloc[-1] / comparison.iloc[0 if custom_range else -64] - 1)
        relative = primary_return - comparison_return
        relative_results.append(relative)
        metrics.append(
            (
                f"{'Analysis-range' if custom_range else '3-month'} return vs. {symbol}",
                f"{primary_return:+.1%} vs. {comparison_return:+.1%} ({relative:+.1%} relative)",
            )
        )
    if not relative_results:
        return finding, (), "Relative-performance evidence was unavailable."

    average_relative = float(np.mean(relative_results))
    ratings = list(Rating)
    original_index = ratings.index(finding.rating)
    adjustment = -1 if average_relative >= 0.08 else 1 if average_relative <= -0.08 else 0
    adjusted_rating = ratings[max(0, min(len(ratings) - 1, original_index + adjustment))]
    original_setup = technical_setup(finding.rating)
    adjusted_setup = technical_setup(adjusted_rating)
    direction = "outperforming" if average_relative > 0 else "underperforming" if average_relative < 0 else "matching"
    symbols = ", ".join(comparison_histories)
    insight = (
        f"The stock returned {primary_return:+.1%} over the {return_label} and is {direction} the comparison set "
        f"({symbols}) by {average_relative:+.1%} on average."
    )
    if adjustment:
        if original_setup == adjusted_setup:
            direction_word = "strengthened" if adjustment < 0 else "weakened"
            insight += f" This {direction_word} the internal technical score by one step; the Technical Setup remains {adjusted_setup}."
        else:
            insight += f" This changed the Technical Setup from {original_setup} to {adjusted_setup}."
    else:
        insight += f" Relative strength did not change the {adjusted_setup} Technical Setup."
    revised = SpecialistFinding(
        adjusted_rating,
        f"{finding.summary} {insight}",
        finding.signals + (insight,),
    )
    return revised, tuple(metrics), insight


def strategies(snapshot: TechnicalSnapshot, horizon: Horizon) -> tuple[Strategy, ...]:
    buffer = max(snapshot.atr14 * 0.5, snapshot.price * 0.005)
    if snapshot.price < snapshot.sma20:
        first = Strategy(
            "Wait for the trend to improve",
            f"Consider a gradual entry only after price moves back above about ${snapshot.sma20:,.2f}",
            "Price closes above that level and momentum begins improving",
            f"Price closes below about ${snapshot.support - buffer:,.2f}",
            "The stock may continue falling before the trend actually turns",
        )
    else:
        first = Strategy(
            "Buy gradually on a pullback",
            f"Watch roughly ${snapshot.sma20 - buffer:,.2f}-${snapshot.sma20 + buffer:,.2f}, near the short-term trend",
            "Price stops falling in that area and begins moving higher",
            f"Price closes below about ${min(snapshot.support, snapshot.sma50) - buffer:,.2f}",
            "A market decline or company news could push price through support",
        )
    return (
        first,
        Strategy(
            "Buy after a clear breakout",
            f"Consider an entry after price closes above about ${snapshot.resistance + buffer:,.2f}",
            "Price stays above the breakout level and trading volume is stronger than normal",
            f"Price falls back below about ${snapshot.resistance - buffer:,.2f}",
            "The breakout may fail and quickly reverse",
        ),
    )


def _option_strike_step(price: float) -> float:
    if price < 50:
        return 1.0
    if price < 200:
        return 2.5
    if price < 500:
        return 5.0
    return 10.0


def _rounded_strike(value: float, *, up: bool) -> float:
    step = _option_strike_step(value)
    scaled = value / step
    rounded = np.ceil(scaled) if up else np.floor(scaled)
    return float(max(step, rounded * step))


def technical_action_plan(
    snapshot: TechnicalSnapshot,
    rating: Rating,
    quote_type: str = "EQUITY",
) -> TechnicalActionPlan:
    """Convert technical evidence into a conditional entry, risk, target, and options plan."""
    price = snapshot.price
    atr = max(snapshot.atr14, price * 0.005)
    atr_pct = atr / price
    trend_gap = abs(snapshot.sma20 - snapshot.sma50) / price
    trending_higher = (
        price > snapshot.sma20 > snapshot.sma50
        and snapshot.macd > snapshot.macd_signal
        and trend_gap >= 0.005
    )
    trending_lower = (
        price < snapshot.sma20 < snapshot.sma50
        and snapshot.macd < snapshot.macd_signal
        and trend_gap >= 0.005
    )
    if trending_higher:
        market_condition = "Trending higher"
    elif trending_lower:
        market_condition = "Trending lower"
    elif atr_pct >= 0.04:
        market_condition = "Volatile and mixed"
    else:
        market_condition = "Choppy / range-bound"

    positive = rating in {Rating.STRONG_BUY, Rating.BUY, Rating.ADD}
    negative = rating in {Rating.REDUCE, Rating.SELL, Rating.AVOID}
    pullback_levels = [
        level
        for level in (
            snapshot.sma20,
            snapshot.sma50,
            snapshot.fib_38_2,
            snapshot.fib_50,
            snapshot.fib_61_8,
            snapshot.support,
        )
        if 0 < level <= price - max(atr * 0.35, price * 0.01)
    ]

    if negative or trending_lower:
        reclaim = max(snapshot.sma20, snapshot.sma50)
        entry_center = reclaim + atr * 0.15
        entry_low = reclaim - atr * 0.10
        entry_high = reclaim + atr * 0.25
        stance = "Wait - no new bullish position"
        order_type = "No order until trend confirmation"
        confirmation = (
            f"Require a closing move above ${reclaim:,.2f}, followed by improving MACD, before considering an entry."
        )
    else:
        entry_center = max(pullback_levels) if pullback_levels else price - atr
        entry_low = max(0.01, entry_center - atr * 0.30)
        entry_high = entry_center + atr * 0.30
        if trending_higher and positive:
            stance = "Add on a controlled pullback"
            order_type = "Limit order near technical support"
            confirmation = (
                f"The ${entry_low:,.2f}-${entry_high:,.2f} zone must hold on a closing basis while momentum remains constructive."
            )
        else:
            stance = "Use a patient entry - do not chase"
            order_type = "Patient limit order in the support zone"
            confirmation = (
                f"Wait for a reversal inside ${entry_low:,.2f}-${entry_high:,.2f} and a close back above the short-term trend."
            )

    entry_mid = (entry_low + entry_high) / 2
    stop_candidates = [
        level
        for level in (
            snapshot.support,
            snapshot.fib_61_8,
            snapshot.fib_50,
            snapshot.sma50,
            snapshot.sma20,
        )
        if 0 < level < entry_low - atr * 0.25
    ]
    stop_anchor = max(stop_candidates) if stop_candidates else entry_mid - atr * 2.0
    structural_stop = stop_anchor - atr * 0.35
    minimum_risk_stop = entry_mid - max(atr * 1.5, entry_mid * 0.03)
    stop_level = max(0.01, min(structural_stop, minimum_risk_stop))
    risk_per_share = max(0.01, entry_mid - stop_level)
    stop_pct = risk_per_share / entry_mid

    structural_targets = sorted(
        {
            float(level)
            for level in (
                price,
                snapshot.fib_61_8,
                snapshot.fib_50,
                snapshot.fib_38_2,
                snapshot.resistance,
                snapshot.fib_swing_high,
            )
            if level > entry_mid + atr * 0.50
        }
    )
    first_target = next(
        (level for level in structural_targets if level >= entry_mid + risk_per_share * 1.50),
        structural_targets[0] if structural_targets else entry_mid + risk_per_share * 1.5,
    )
    higher_targets = [level for level in structural_targets if level > first_target + atr * 0.25]
    second_target = higher_targets[-1] if higher_targets else max(first_target, entry_mid + risk_per_share * 2.0)
    reward_risk = max(0.0, (first_target - entry_mid) / risk_per_share)

    if stop_pct > 0.15 and not negative:
        stance = "Wait for a tighter setup"
        order_type = "No order - structural stop is too wide"
        confirmation = (
            f"Wait until support rises or price forms a tighter base; the current technical stop requires {stop_pct:.1%} risk."
        )
    elif reward_risk < 1.50 and not negative:
        stance = "Wait for a better reward-to-risk setup"
        order_type = "No order - first target offers less than 1.5x reward / risk"
        confirmation = (
            "Wait for a lower entry, a tighter structural stop, or a higher confirmed target before considering the trade."
        )
    invalidation = (
        f"A sustained close below ${stop_level:,.2f} invalidates the setup; the stop is {stop_pct:.1%} below the planned entry midpoint."
    )
    rationale = (
        f"The entry zone is anchored to the nearest usable support cluster around ${entry_center:,.2f}, not an arbitrary discount.",
        f"The ${stop_level:,.2f} stop sits below structure with an ATR buffer; its {stop_pct:.1%} distance is calculated rather than fixed at 7%.",
        f"The first technical objective is ${first_target:,.2f}; estimated reward/risk from the entry midpoint is {reward_risk:.2f}x.",
        f"Market condition is {market_condition.lower()}, based on moving-average alignment, MACD, and ATR.",
    )

    options_strategy = ""
    options_structure = ""
    options_risk = ""
    normalized_type = quote_type.upper().replace(" ", "")
    optionable_reference = normalized_type in {"EQUITY", "ETF"} and price >= 5
    actionable_entry = not order_type.lower().startswith("no order")
    if optionable_reference and (actionable_entry or negative or trending_lower):
        if negative or trending_lower:
            protective_strike = _rounded_strike(stop_level, up=False)
            options_strategy = "Existing position only: protective put or collar review"
            options_structure = (
                f"Planning reference: review a put strike near ${protective_strike:,.2f} with 45-90 days to expiration, "
                "or finance part of the hedge with a covered call. Verify the live chain before use."
            )
            options_risk = "Protection costs premium and can expire worthless; a collar also caps upside. Options are not suitable for every investor."
        elif market_condition in {"Choppy / range-bound", "Volatile and mixed"}:
            put_strike = _rounded_strike(entry_mid, up=False)
            options_strategy = "Optional stock-entry alternative: cash-secured put"
            options_structure = (
                f"Planning reference: 30-60 days to expiration with a strike near ${put_strike:,.2f}; reserve enough cash for 100 shares "
                "and use it only if assignment at that price is acceptable. Verify the live chain before use."
            )
            options_risk = "Losses can be substantial if the stock falls far below the strike; assignment remains possible. Options are not suitable for every investor."
        else:
            long_strike = _rounded_strike(price, up=False)
            short_strike = max(long_strike + _option_strike_step(price), _rounded_strike(first_target, up=True))
            options_strategy = "Optional defined-risk bullish expression: call spread"
            options_structure = (
                f"Planning reference: 45-90 days to expiration, buy a call near ${long_strike:,.2f} and sell a call near ${short_strike:,.2f}. "
                "Only consider it if the debit is reasonable versus the spread width and the live chain is liquid."
            )
            options_risk = "The entire debit can be lost by expiration and upside is capped at the short strike. Options are not suitable for every investor."

    return TechnicalActionPlan(
        stance=stance,
        market_condition=market_condition,
        order_type=order_type,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_level=stop_level,
        stop_pct=stop_pct,
        first_target=first_target,
        second_target=second_target,
        reward_risk=reward_risk,
        confirmation=confirmation,
        invalidation=invalidation,
        rationale=rationale,
        options_strategy=options_strategy,
        options_structure=options_structure,
        options_risk=options_risk,
    )


def _stop_reference(
    snapshot: TechnicalSnapshot,
    plan: TechnicalActionPlan,
) -> tuple[str, float]:
    """Return the nearest usable structural level beneath the planned entry."""
    atr = max(snapshot.atr14, snapshot.price * 0.005)
    candidates = (
        ("60-day support", snapshot.support),
        ("Fibonacci 61.8%", snapshot.fib_61_8),
        ("Fibonacci 50%", snapshot.fib_50),
        ("50-day average", snapshot.sma50),
        ("20-day average", snapshot.sma20),
    )
    usable = [
        (label, float(level))
        for label, level in candidates
        if 0 < float(level) < plan.entry_low - atr * 0.25
    ]
    if usable:
        return max(usable, key=lambda item: item[1])
    return "volatility-derived support", max(plan.stop_level, (plan.entry_low + plan.entry_high) / 2 - atr * 2.0)


def stop_loss_decision_insights(
    snapshot: TechnicalSnapshot,
    plan: TechnicalActionPlan,
) -> tuple[str, ...]:
    """Explain the structure, volatility buffer, and payoff behind the stop."""
    entry_mid = (plan.entry_low + plan.entry_high) / 2
    atr = max(snapshot.atr14, snapshot.price * 0.005)
    risk_per_share = max(0.01, entry_mid - plan.stop_level)
    reference_label, reference_level = _stop_reference(snapshot, plan)
    buffer = max(0.0, reference_level - plan.stop_level)
    atr_multiple = risk_per_share / atr
    if plan.reward_risk >= 1.50:
        payoff = (
            f"Target 1 at ${plan.first_target:,.2f} offers {plan.reward_risk:.2f}x estimated reward/risk, "
            "meeting the 1.5x minimum used for an actionable setup."
        )
    else:
        payoff = (
            f"Target 1 at ${plan.first_target:,.2f} offers only {plan.reward_risk:.2f}x estimated reward/risk; "
            "the setup should be monitored rather than entered until the payoff improves."
        )
    order_context = (
        "This is a planning reference rather than an active order because confirmation is still required."
        if plan.order_type.lower().startswith("no order")
        else "The stop becomes relevant only after the entry and confirmation conditions are satisfied."
    )
    return (
        f"Structure: the nearest usable invalidation reference is {reference_label} near ${reference_level:,.2f}; the stop is placed beyond it at ${plan.stop_level:,.2f}.",
        f"Volatility: the stop is {plan.stop_pct:.1%} below the entry midpoint, equal to {atr_multiple:.1f}x current ATR, with a ${buffer:,.2f} buffer beneath that structural reference.",
        payoff,
        order_context,
    )


def render_chart(
    history: pd.DataFrame,
    ticker: str,
    snapshot: TechnicalSnapshot,
    destination: Path,
    plan: TechnicalActionPlan | None = None,
) -> Path:
    """Render a minimal annotated candlestick view grounded in dated price structure."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = history.dropna(subset=["Close", "High", "Low"]).copy()
    if not history.attrs.get("custom_range"):
        frame = frame.tail(120)
    close = frame["Close"].astype(float)
    open_price = (
        frame["Open"].astype(float).fillna(close.shift(1)).fillna(close)
        if "Open" in frame and frame["Open"].notna().any()
        else close.shift(1).fillna(close)
    )
    high = frame["High"].astype(float)
    low = frame["Low"].astype(float)
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    fig, ax = plt.subplots(figsize=(10.5, 5.7))
    fig.patch.set_facecolor("white")
    x_values = mdates.date2num(frame.index.to_pydatetime())
    spacing = float(np.median(np.diff(x_values))) if len(x_values) > 1 else 1.0
    candle_width = max(0.32, min(0.72, spacing * 0.64))
    for x_value, opening, maximum, minimum, closing in zip(
        x_values,
        open_price,
        high,
        low,
        close,
    ):
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
    ax.plot(frame.index, sma20, color=GOLD, linewidth=1.25, label="20-day average", zorder=4)
    ax.plot(frame.index, sma50, color=BLUE, linewidth=1.15, label="50-day average", zorder=4)
    if plan is not None:
        reference_label, reference_level = _stop_reference(snapshot, plan)
        ax.axhspan(
            plan.entry_low,
            plan.entry_high,
            color=GOLD,
            alpha=0.12,
            label=f"Entry ${plan.entry_low:,.2f}-${plan.entry_high:,.2f}",
        )
        ax.axhline(
            reference_level,
            color=MUTED,
            linestyle="-.",
            linewidth=0.9,
            label=f"Structure ${reference_level:,.2f}",
        )
        ax.axhline(
            plan.stop_level,
            color=RED,
            linestyle="--",
            linewidth=1.0,
            label=f"Stop ${plan.stop_level:,.2f}",
        )
        ax.axhline(
            plan.first_target,
            color=GREEN,
            linestyle=":",
            linewidth=1.1,
            label=f"Target 1 ${plan.first_target:,.2f}",
        )

    arrow_style = dict(arrowstyle="->", color=NAVY, linewidth=0.85, shrinkA=2, shrinkB=2)
    latest_date = frame.index[-1]
    latest_close = float(close.iloc[-1])
    latest_sma20 = float(sma20.iloc[-1])
    latest_sma50 = float(sma50.iloc[-1])
    if latest_close > latest_sma20 and latest_close > latest_sma50:
        trend_label = "Price above 20D + 50D"
        trend_offset = (-92, 34)
    elif latest_close < latest_sma20 and latest_close < latest_sma50:
        trend_label = "Price below 20D + 50D"
        trend_offset = (-92, -42)
    else:
        trend_label = "Trend averages split"
        trend_offset = (-88, 34)
    ax.annotate(
        trend_label,
        xy=(latest_date, latest_close),
        xytext=trend_offset,
        textcoords="offset points",
        fontsize=7.4,
        color=NAVY,
        fontweight="bold",
        arrowprops=arrow_style,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#D8DDE6", alpha=0.94),
        zorder=7,
    )

    spread = sma20 - sma50
    crossings = spread.mul(spread.shift(1)).lt(0)
    crossing_dates = crossings[crossings].index
    if len(crossing_dates):
        cross_date = crossing_dates[-1]
        cross_value = float(close.loc[cross_date])
        bullish_cross = float(spread.loc[cross_date]) > 0
        ax.annotate(
            "Bullish 20/50 cross" if bullish_cross else "Bearish 20/50 cross",
            xy=(cross_date, cross_value),
            xytext=(16, 38 if bullish_cross else -46),
            textcoords="offset points",
            fontsize=7.2,
            color=NAVY,
            arrowprops=arrow_style,
            bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor="#D8DDE6", alpha=0.92),
            zorder=7,
        )

    support_window = low.tail(min(60, len(low)))
    support_date = support_window.idxmin()
    support_value = float(support_window.loc[support_date])
    if not len(crossing_dates) or abs((latest_date - support_date).days) > 18:
        ax.annotate(
            f"Support test ${support_value:,.2f}",
            xy=(support_date, support_value),
            xytext=(-10, -42),
            textcoords="offset points",
            fontsize=7.2,
            color=NAVY,
            arrowprops=arrow_style,
            bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor="#D8DDE6", alpha=0.92),
            zorder=7,
        )

    ax.set_title(f"{ticker} | Daily Price Structure", loc="left", color=NAVY, fontsize=11.2, fontweight="bold")
    ax.set_ylabel("Price (USD)", color=MUTED, fontsize=8)
    ax.grid(axis="y", alpha=0.14, linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D8DDE6")
    ax.spines["bottom"].set_color("#D8DDE6")
    ax.tick_params(colors=MUTED, labelsize=7.6)
    ax.legend(ncol=3, fontsize=7.1, frameon=False, loc="upper left")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.margins(x=0.018)
    fig.tight_layout()
    _hover_sidecar(
        fig,
        ax,
        destination,
        x_values,
        [stamp.strftime("%d %b %Y") for stamp in frame.index],
        [
            ("Close", [f"${value:,.2f}" for value in close]),
            ("Open", [f"${value:,.2f}" for value in open_price]),
            ("High / Low", [f"${high_v:,.2f} / ${low_v:,.2f}" for high_v, low_v in zip(high, low)]),
            ("20-day avg", ["—" if pd.isna(value) else f"${value:,.2f}" for value in sma20]),
            ("50-day avg", ["—" if pd.isna(value) else f"${value:,.2f}" for value in sma50]),
        ],
        [float(value) for value in close],
    )
    fig.savefig(destination, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return destination


def render_stop_loss_evidence_chart(
    history: pd.DataFrame,
    ticker: str,
    snapshot: TechnicalSnapshot,
    plan: TechnicalActionPlan,
    destination: Path,
) -> Path:
    """Show exactly why the proposed stop sits beyond structure and normal volatility."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = history.dropna(subset=["Close", "High", "Low"]).copy()
    if not history.attrs.get("custom_range"):
        frame = frame.tail(160)
    close = frame["Close"].astype(float)
    high = frame["High"].astype(float)
    low = frame["Low"].astype(float)
    previous = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - previous).abs(), (low - previous).abs()],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(14).mean()
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    entry_mid = (plan.entry_low + plan.entry_high) / 2
    risk_per_share = max(0.01, entry_mid - plan.stop_level)
    current_atr = max(snapshot.atr14, snapshot.price * 0.005)
    atr_multiple = risk_per_share / current_atr
    reference_label, reference_level = _stop_reference(snapshot, plan)

    fig, (price_ax, atr_ax) = plt.subplots(
        2,
        1,
        figsize=(10.5, 6.3),
        gridspec_kw={"height_ratios": [4.4, 1.25]},
        sharex=True,
    )
    fig.patch.set_facecolor("white")
    price_ax.plot(frame.index, close, color=NAVY, linewidth=2.0, label="Close")
    price_ax.plot(frame.index, sma20, color=GOLD, linewidth=1.15, label="SMA 20")
    price_ax.plot(frame.index, sma50, color=BLUE, linewidth=1.05, label="SMA 50")
    price_ax.axhspan(
        plan.entry_low,
        plan.entry_high,
        color=GOLD,
        alpha=0.16,
        label=f"Entry zone ${plan.entry_low:,.2f}-${plan.entry_high:,.2f}",
    )
    price_ax.axhspan(
        plan.stop_level,
        plan.entry_low,
        color=RED,
        alpha=0.055,
        label="Defined risk to stop",
    )
    price_ax.axhline(
        reference_level,
        color=MUTED,
        linestyle="-.",
        linewidth=1.0,
        label=f"{reference_label.title()} ${reference_level:,.2f}",
    )
    price_ax.axhline(
        plan.stop_level,
        color=RED,
        linestyle="--",
        linewidth=1.35,
        label=f"Structural stop ${plan.stop_level:,.2f}",
    )
    price_ax.axhline(
        plan.first_target,
        color=GREEN,
        linestyle=":",
        linewidth=1.25,
        label=f"Target 1 ${plan.first_target:,.2f} ({plan.reward_risk:.2f}x R:R)",
    )
    price_ax.set_title(
        f"{ticker} - Stop-Loss Evidence: Structure and Volatility",
        loc="left",
        color=NAVY,
        fontweight="bold",
    )
    price_ax.set_ylabel("Price (USD)")
    price_ax.grid(alpha=0.14)
    price_ax.legend(ncol=3, fontsize=7.5, frameon=False, loc="upper left")

    atr_ax.plot(atr.index, atr, color=GOLD, linewidth=1.5, label="ATR (14)")
    atr_ax.axhline(
        risk_per_share,
        color=RED,
        linestyle="--",
        linewidth=1.1,
        label=f"Entry-to-stop risk ${risk_per_share:,.2f}",
    )
    atr_ax.text(
        0.99,
        0.84,
        f"Stop distance = {atr_multiple:.1f}x current ATR",
        transform=atr_ax.transAxes,
        ha="right",
        va="top",
        color=NAVY,
        fontsize=8.5,
        fontweight="bold",
    )
    atr_ax.set_ylabel("Daily range")
    atr_ax.grid(axis="y", alpha=0.14)
    atr_ax.legend(ncol=2, fontsize=7.5, frameon=False, loc="upper left")
    atr_ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    atr_ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(atr_ax.xaxis.get_major_locator()))
    fig.tight_layout()
    fig.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return destination


def render_fibonacci_chart(
    history: pd.DataFrame,
    ticker: str,
    snapshot: TechnicalSnapshot,
    destination: Path,
) -> Path:
    """Render Fibonacci structure separately so the primary trend chart stays legible."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = history.dropna(subset=["Close"]).copy()
    if not history.attrs.get("custom_range"):
        frame = frame.tail(260)
    close = frame["Close"].astype(float)
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    fig.patch.set_facecolor("white")
    ax.plot(frame.index, close, color=NAVY, linewidth=1.9, label="Close")
    for level, label, color in (
        (snapshot.fib_swing_high, "Swing high", GREEN),
        (snapshot.fib_38_2, "38.2%", "#8E6BB8"),
        (snapshot.fib_50, "50.0%", "#7D7D7D"),
        (snapshot.fib_61_8, "61.8%", "#B06F57"),
        (snapshot.fib_swing_low, "Swing low", RED),
    ):
        ax.axhline(level, color=color, linestyle="--" if "Swing" in label else ":", linewidth=1.0, label=f"{label}  ${level:,.2f}")
    ax.set_title(
        f"{ticker} - {snapshot.fibonacci_range_label} Fibonacci Structure",
        loc="left",
        color=NAVY,
        fontweight="bold",
    )
    ax.set_ylabel("Price (USD)")
    ax.grid(alpha=0.18)
    ax.legend(ncol=3, fontsize=8, frameon=False, loc="upper left")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    fig.tight_layout()
    fig.savefig(destination, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return destination


def render_track_record_chart(index, picks_curve, benchmark_curve, benchmark: str, destination: Path) -> Path:
    """Cumulative return of the picks against the benchmark over the same dates."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10.6, 4.9))
    fig.patch.set_facecolor("white")

    final = float(picks_curve.iloc[-1])
    ax.plot(index, picks_curve * 100, color=NAVY, linewidth=2.0, label=f"Our buy-side picks {final:+.1%}", zorder=4)
    if benchmark_curve is not None:
        ax.plot(
            index,
            benchmark_curve * 100,
            color=GOLD,
            linewidth=1.6,
            linestyle="--",
            label=f"{benchmark} {float(benchmark_curve.iloc[-1]):+.1%}",
            zorder=3,
        )
    ax.axhline(0, color=MUTED, linewidth=0.8, zorder=2)

    ax.set_title("Track record — cumulative return of picks vs benchmark", loc="left",
                 color=NAVY, fontsize=11.2, fontweight="bold")
    ax.set_ylabel("Cumulative return (%)", color=MUTED, fontsize=8)
    ax.grid(alpha=0.15, linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D8DDE6")
    ax.spines["bottom"].set_color("#D8DDE6")
    ax.tick_params(colors=MUTED, labelsize=7.6)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    fig.tight_layout()
    fig.savefig(destination, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return destination


def render_options_chart(snapshot, ticker: str, destination: Path) -> Path:
    """The volatility smile for the front expiry, with the move it implies.

    Reads as one picture: the curve shows what the option market charges at each
    strike, the shaded band shows the one-standard-deviation move that pricing
    implies, and the tilt of the curve is the skew.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    front = snapshot.front
    fig, ax = plt.subplots(figsize=(10.6, 4.9))
    fig.patch.set_facecolor("white")

    # The chain quotes one implied volatility per strike -- puts and calls at the
    # same strike carry the same IV by put-call parity -- so this is a single curve.
    # Its tilt is the skew: richer downside strikes lift the left-hand side.
    strikes = list(snapshot.smile_strikes)
    if strikes:
        ax.plot(
            strikes,
            list(snapshot.smile_call_iv),
            color=NAVY,
            linewidth=1.8,
            marker="o",
            markersize=3.2,
            label="Implied volatility by strike",
            zorder=4,
        )

    if front is not None and snapshot.spot > 0:
        low = snapshot.spot - front.expected_move
        high = snapshot.spot + front.expected_move
        ax.axvspan(
            low,
            high,
            color=BLUE,
            alpha=0.10,
            zorder=1,
            label=f"Expected move to expiry ±${front.expected_move:,.2f}",
        )
        ax.axvline(snapshot.spot, color=RED, linestyle="--", linewidth=1.1, zorder=3)

    ax.legend(ncol=2, fontsize=7.4, frameon=False, loc="upper right")
    # Annotate after the axes limits settle so the labels sit where they are drawn.
    if front is not None and snapshot.spot > 0:
        bottom, top = ax.get_ylim()
        ax.set_ylim(bottom - (top - bottom) * 0.12, top)
        bottom, top = ax.get_ylim()
        ax.annotate(
            f"Spot ${snapshot.spot:,.2f}",
            xy=(snapshot.spot, bottom),
            xytext=(0, 16),
            textcoords="offset points",
            fontsize=7.6,
            color=RED,
            fontweight="bold",
            ha="center",
        )
        for edge, label in ((low, f"−1σ ${low:,.2f}"), (high, f"+1σ ${high:,.2f}")):
            ax.annotate(
                label,
                xy=(edge, bottom),
                xytext=(0, 5),
                textcoords="offset points",
                fontsize=7.0,
                color=MUTED,
                ha="center",
            )

    heading = f"{ticker} | Implied volatility by strike"
    if front is not None:
        heading += f" — {front.expiration} ({front.days_to_expiry}d)"
    ax.set_title(heading, loc="left", color=NAVY, fontsize=11.2, fontweight="bold")
    ax.set_xlabel("Strike (USD)", color=MUTED, fontsize=8)
    ax.set_ylabel("Implied volatility (%)", color=MUTED, fontsize=8)
    ax.grid(alpha=0.15, linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D8DDE6")
    ax.spines["bottom"].set_color("#D8DDE6")
    ax.tick_params(colors=MUTED, labelsize=7.6)
    fig.tight_layout()
    fig.savefig(destination, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return destination


def render_volume_profile_chart(
    history: pd.DataFrame,
    ticker: str,
    profile: VolumeProfile,
    destination: Path,
) -> Path:
    """Price beside the volume traded at each level, sharing one price axis.

    Reading them together is the point: the histogram shows *where* size changed
    hands, and the price panel shows whether the market is currently defending or
    rejecting those levels.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = history.dropna(subset=["Close"]).copy()
    if not history.attrs.get("custom_range"):
        frame = frame.tail(180)
    close = frame["Close"].astype(float)

    fig, (price_ax, profile_ax) = plt.subplots(
        1, 2, figsize=(10.8, 5.4), sharey=True, gridspec_kw={"width_ratios": [3.1, 1.0], "wspace": 0.03}
    )
    fig.patch.set_facecolor("white")

    price_ax.plot(close.index, close, color=NAVY, linewidth=1.4, zorder=3)
    price_ax.axhspan(profile.value_area_low, profile.value_area_high, color=GOLD, alpha=0.11, zorder=1)
    price_ax.axhline(profile.point_of_control, color=GOLD, linewidth=1.3, zorder=2)
    price_ax.set_title(f"{ticker} | Volume by price", loc="left", color=NAVY, fontsize=11.2, fontweight="bold")
    price_ax.set_ylabel("Price (USD)", color=MUTED, fontsize=8)
    price_ax.grid(axis="y", alpha=0.14, linewidth=0.7)
    price_ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    price_ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(price_ax.xaxis.get_major_locator()))

    heights = (profile.prices[1] - profile.prices[0]) * 0.86 if len(profile.prices) > 1 else 1.0
    for price_level, level_volume in zip(profile.prices, profile.volumes):
        inside = profile.value_area_low <= price_level <= profile.value_area_high
        is_control = abs(price_level - profile.point_of_control) < 1e-9
        profile_ax.barh(
            price_level,
            level_volume,
            height=heights,
            color=GOLD if is_control else (BLUE if inside else "#C9D2DE"),
            alpha=1.0 if is_control else (0.75 if inside else 0.6),
            zorder=2,
        )
    profile_ax.set_xlabel("Volume", color=MUTED, fontsize=8)
    profile_ax.grid(axis="x", alpha=0.12, linewidth=0.6)
    profile_ax.tick_params(labelleft=False)
    profile_ax.set_xticks([])

    latest = float(close.iloc[-1])
    price_ax.axhline(latest, color=RED, linestyle="--", linewidth=1.0, zorder=4)
    for axis, label, value, colour in (
        (profile_ax, f"POC ${profile.point_of_control:,.2f}", profile.point_of_control, GOLD),
        (profile_ax, f"Now ${latest:,.2f}", latest, RED),
    ):
        axis.annotate(
            label,
            xy=(axis.get_xlim()[1], value),
            xytext=(4, 0),
            textcoords="offset points",
            fontsize=7.4,
            color=colour,
            fontweight="bold",
            va="center",
            annotation_clip=False,
        )

    for axis in (price_ax, profile_ax):
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.spines["left"].set_color("#D8DDE6")
        axis.spines["bottom"].set_color("#D8DDE6")
        axis.tick_params(colors=MUTED, labelsize=7.6)

    # The POC/Now labels sit outside the right axis, which tight_layout cannot
    # account for; savefig's tight bbox already captures them.
    fig.subplots_adjust(left=0.07, right=0.88, top=0.92, bottom=0.10, wspace=0.03)
    fig.savefig(destination, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return destination


def render_momentum_chart(history: pd.DataFrame, ticker: str, destination: Path) -> Path:
    """Render RSI and MACD panels from the same verified history used in the rating."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    close = history["Close"].dropna().astype(float)
    if not history.attrs.get("custom_range"):
        close = close.tail(260)
    rsi = _rsi(close)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    fig, (rsi_ax, macd_ax) = plt.subplots(2, 1, figsize=(10.5, 5.2), sharex=True)
    fig.patch.set_facecolor("white")
    rsi_ax.plot(rsi.index, rsi, color=NAVY, linewidth=1.5, label="RSI (14)")
    rsi_ax.axhline(70, color=RED, linestyle="--", linewidth=0.9)
    rsi_ax.axhline(30, color=GREEN, linestyle="--", linewidth=0.9)
    rsi_ax.fill_between(rsi.index, 30, 70, color=PALE, alpha=0.7)
    rsi_ax.set_ylim(0, 100)
    rsi_ax.set_ylabel("RSI")
    rsi_ax.set_title(f"{ticker} - Momentum: RSI and MACD", loc="left", color=NAVY, fontweight="bold")
    rsi_ax.grid(alpha=0.16)
    macd_ax.plot(macd.index, macd, color=NAVY, linewidth=1.3, label="MACD")
    macd_ax.plot(signal.index, signal, color=GOLD, linewidth=1.2, label="Signal")
    colors_v = np.where(histogram >= 0, "#6E9D85", "#C77A7A")
    macd_ax.bar(histogram.index, histogram, color=colors_v, width=1.0, alpha=0.65, label="Histogram")
    macd_ax.axhline(0, color=MUTED, linewidth=0.7)
    macd_ax.set_ylabel("MACD")
    macd_ax.grid(alpha=0.16)
    macd_ax.legend(ncol=3, fontsize=8, frameon=False, loc="upper left")
    macd_ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    macd_ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(macd_ax.xaxis.get_major_locator()))
    fig.tight_layout()
    _hover_sidecar(
        fig,
        rsi_ax,
        destination,
        mdates.date2num(close.index.to_pydatetime()),
        [stamp.strftime("%d %b %Y") for stamp in close.index],
        [
            ("Close", [f"${value:,.2f}" for value in close]),
            ("RSI (14)", ["—" if pd.isna(value) else f"{value:.1f}" for value in rsi]),
            ("MACD", [f"{value:.2f}" for value in macd]),
            ("Signal", [f"{value:.2f}" for value in signal]),
            ("Histogram", [f"{value:+.2f}" for value in histogram]),
        ],
        [],  # two panels share the crosshair, so no single-axis marker dot
        bottom_ax=macd_ax,
    )
    fig.savefig(destination, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return destination


def render_relative_performance_chart(
    histories: dict[str, pd.DataFrame],
    destination: Path,
    benchmark_symbol: str = "",
) -> Path:
    """Render normalized performance on common trading dates for valid comparisons."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    closes = {
        symbol: history["Close"].dropna().astype(float).rename(symbol)
        for symbol, history in histories.items()
        if not history.empty and "Close" in history.columns
    }
    frame = pd.concat(closes.values(), axis=1, join="inner").dropna()
    if not any(history.attrs.get("custom_range") for history in histories.values()):
        frame = frame.tail(260)
    if len(frame) < 20:
        raise ValueError("At least 20 common trading sessions are required for a comparison chart.")
    normalized = frame.divide(frame.iloc[0]).multiply(100)
    palette = [NAVY, GOLD, BLUE, GREEN]
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    fig.patch.set_facecolor("white")
    for index, column in enumerate(normalized.columns):
        period_return = float(normalized[column].iloc[-1] / 100 - 1)
        is_benchmark = bool(benchmark_symbol and column == benchmark_symbol)
        ax.plot(
            normalized.index,
            normalized[column],
            color=palette[index % len(palette)],
            linewidth=1.5 if is_benchmark else 1.9,
            linestyle="--" if is_benchmark else "-",
            alpha=0.85 if is_benchmark else 1.0,
            label=f"{column}  {period_return:+.1%}",
        )
    ax.axhline(100, color=MUTED, linewidth=0.7)
    title = "Performance vs Sector Benchmark" if benchmark_symbol else "Normalized Relative Performance"
    ax.set_title(f"{title} - Starting Value 100", loc="left", color=NAVY, fontweight="bold")
    ax.set_ylabel("Indexed value")
    ax.grid(alpha=0.18)
    ax.legend(ncol=4, fontsize=8, frameon=False, loc="upper left")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    fig.tight_layout()
    _hover_sidecar(
        fig,
        ax,
        destination,
        mdates.date2num(normalized.index.to_pydatetime()),
        [stamp.strftime("%d %b %Y") for stamp in normalized.index],
        # Indexed to 100 at the start, so read each series as a return from day one.
        [
            (str(column), [f"{value / 100 - 1:+.1%}" for value in normalized[column]])
            for column in normalized.columns
        ],
        [float(value) for value in normalized[normalized.columns[0]]],
    )
    fig.savefig(destination, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return destination


def _common_period_closes(
    histories: dict[str, pd.DataFrame],
    start_date: str = "",
    end_date: str = "",
) -> pd.DataFrame:
    closes = {
        symbol: history["Close"].dropna().astype(float).rename(symbol)
        for symbol, history in histories.items()
        if not history.empty and "Close" in history.columns
    }
    if not closes:
        return pd.DataFrame()
    frame = pd.concat(closes.values(), axis=1, join="inner").dropna()
    if frame.empty:
        return frame
    index_tz = getattr(frame.index, "tz", None)
    if start_date:
        start = pd.Timestamp(start_date)
        if index_tz is not None:
            start = start.tz_localize(index_tz)
        frame = frame.loc[frame.index >= start]
    if end_date:
        end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
        if index_tz is not None:
            end = end.tz_localize(index_tz)
        frame = frame.loc[frame.index < end]
    return frame


def period_total_returns(
    histories: dict[str, pd.DataFrame],
    start_date: str = "",
    end_date: str = "",
) -> dict[str, float]:
    """Calculate total returns on the exact common dates shown in the lead chart."""
    frame = _common_period_closes(histories, start_date, end_date)
    if len(frame) < 20:
        return {}
    return {
        str(column): float(frame[column].iloc[-1] / frame[column].iloc[0] - 1)
        for column in frame.columns
    }


def total_return_chart_insights(
    histories: dict[str, pd.DataFrame],
    primary_symbol: str,
    benchmark_symbol: str,
    period_label: str,
    rating: Rating,
    start_date: str = "",
    end_date: str = "",
) -> tuple[str, ...]:
    """Explain the visible relative-return evidence in direct decision language."""
    returns = period_total_returns(histories, start_date, end_date)
    primary_return = returns.get(primary_symbol)
    benchmark_return = returns.get(benchmark_symbol)
    if primary_return is None:
        return (f"{period_label} return evidence was unavailable for {primary_symbol}.",)
    if not benchmark_symbol:
        return (
            f"{primary_symbol} returned {primary_return:+.1%} over {period_label}.",
            "This is a standalone performance view because the researched security is the default benchmark.",
        )
    if benchmark_return is None:
        return (
            f"{primary_symbol} returned {primary_return:+.1%} over {period_label}.",
            f"{benchmark_symbol} comparison data was unavailable, so no relative-strength conclusion was used.",
        )
    relative = primary_return - benchmark_return
    direction = "outperformed" if relative > 0 else "underperformed" if relative < 0 else "matched"
    if relative >= 0.05:
        decision_effect = f"The relative strength supports the {technical_setup(rating)} technical setup."
    elif relative <= -0.05:
        decision_effect = f"The relative weakness is a caution against upgrading the {technical_setup(rating)} technical setup."
    else:
        decision_effect = f"The performance gap is modest and does not change the {technical_setup(rating)} technical setup."
    return (
        f"{primary_symbol} returned {primary_return:+.1%}; {benchmark_symbol} returned {benchmark_return:+.1%} over {period_label}.",
        f"{primary_symbol} {direction} {benchmark_symbol} by {abs(relative):.1%}.",
        decision_effect,
    )


def render_total_return_chart(
    histories: dict[str, pd.DataFrame],
    destination: Path,
    period_label: str,
    benchmark_symbol: str = "SPY",
    start_date: str = "",
    end_date: str = "",
) -> Path:
    """Render a calm cumulative-total-return chart for the report's lead visual."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = _common_period_closes(histories, start_date, end_date)
    if len(frame) < 20:
        raise ValueError("At least 20 common trading sessions are required for a total-return chart.")
    total_return = frame.divide(frame.iloc[0]).subtract(1).multiply(100)
    palette = [NAVY, GOLD, BLUE, GREEN]
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    fig.patch.set_facecolor("white")
    for index, column in enumerate(total_return.columns):
        ending_return = float(total_return[column].iloc[-1])
        is_benchmark = bool(benchmark_symbol and column == benchmark_symbol)
        ax.plot(
            total_return.index,
            total_return[column],
            color=palette[index % len(palette)],
            linewidth=1.7 if is_benchmark else 2.2,
            linestyle="--" if is_benchmark else "-",
            alpha=0.9 if is_benchmark else 1.0,
            label=f"{column}  {ending_return:+.1f}%",
        )
    ax.axhline(0, color=MUTED, linewidth=0.8)
    symbols = " vs. ".join(str(column) for column in total_return.columns)
    ax.set_title(
        f"{symbols} - {period_label} Total Return",
        loc="left",
        color=NAVY,
        fontweight="bold",
    )
    ax.set_ylabel("Total return (%)")
    ax.grid(alpha=0.16)
    ax.legend(ncol=3, fontsize=8.5, frameon=False, loc="upper left")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    fig.tight_layout()
    fig.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return destination


def relative_performance_returns(histories: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Return chart-period total returns on the exact common dates used by the chart."""
    closes = {
        symbol: history["Close"].dropna().astype(float).rename(symbol)
        for symbol, history in histories.items()
        if not history.empty and "Close" in history.columns
    }
    if len(closes) < 2:
        return {}
    frame = pd.concat(closes.values(), axis=1, join="inner").dropna()
    if not any(history.attrs.get("custom_range") for history in histories.values()):
        frame = frame.tail(260)
    if len(frame) < 20:
        return {}
    return {
        str(column): float(frame[column].iloc[-1] / frame[column].iloc[0] - 1)
        for column in frame.columns
    }


def risk_chart_insight(history: pd.DataFrame, ticker: str) -> str:
    close = history["Close"].dropna().astype(float)
    if not history.attrs.get("custom_range"):
        close = close.tail(260)
    returns = close.pct_change().dropna()
    drawdown = close / close.cummax() - 1
    annualized_volatility = float(returns.tail(63).std() * np.sqrt(252)) if len(returns) >= 20 else 0.0
    sizing = "smaller position sizing and wider risk limits" if annualized_volatility >= 0.35 else "normal position sizing with a defined exit level"
    return (
        f"{ticker}'s analysis-range maximum drawdown was {float(drawdown.min()):.1%}; ending drawdown is "
        f"{float(drawdown.iloc[-1]):.1%}, with three-month annualized volatility of {annualized_volatility:.1%}. "
        f"This risk profile argues for {sizing}; it affects implementation rather than changing the rating by itself."
    )


def render_risk_chart(history: pd.DataFrame, ticker: str, destination: Path) -> Path:
    """Render one-year drawdown and rolling realized volatility."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    close = history["Close"].dropna().astype(float)
    if not history.attrs.get("custom_range"):
        close = close.tail(260)
    returns = close.pct_change()
    drawdown = close / close.cummax() - 1
    volatility = returns.rolling(20).std() * np.sqrt(252)
    fig, (drawdown_ax, volatility_ax) = plt.subplots(2, 1, figsize=(10.5, 5.2), sharex=True)
    fig.patch.set_facecolor("white")
    drawdown_ax.fill_between(drawdown.index, drawdown, 0, color="#C77A7A", alpha=0.65)
    drawdown_ax.plot(drawdown.index, drawdown, color=RED, linewidth=1.0)
    drawdown_ax.set_title(f"{ticker} - Drawdown and Realized Volatility", loc="left", color=NAVY, fontweight="bold")
    drawdown_ax.set_ylabel("Drawdown")
    drawdown_ax.yaxis.set_major_formatter(lambda value, _position: f"{value:.0%}")
    drawdown_ax.grid(alpha=0.16)
    volatility_ax.plot(volatility.index, volatility, color=NAVY, linewidth=1.4)
    volatility_ax.set_ylabel("20d ann. vol.")
    volatility_ax.yaxis.set_major_formatter(lambda value, _position: f"{value:.0%}")
    volatility_ax.grid(alpha=0.16)
    volatility_ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    volatility_ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(volatility_ax.xaxis.get_major_locator()))
    fig.tight_layout()
    fig.savefig(destination, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return destination
