"""Deterministic technical-analysis calculations and chart rendering."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(os.getenv("TEMP", "/tmp")) / "researcheus-matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.models import HistoricalTradeCase, Horizon, Rating, SpecialistFinding, Strategy


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

    def as_metrics(self) -> tuple[tuple[str, str], ...]:
        sma200 = "Unavailable" if self.sma200 is None else f"${self.sma200:,.2f}"
        return (
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
            ("Volume vs. 20-day avg.", f"{self.volume_ratio:.2f}x"),
            ("60-day support / resistance", f"${self.support:,.2f} / ${self.resistance:,.2f}"),
            (
                f"{self.fibonacci_range_label} Fibonacci swing range",
                f"${self.fib_swing_low:,.2f} / ${self.fib_swing_high:,.2f}",
            ),
            (
                "Fibonacci 38.2% / 50% / 61.8%",
                f"${self.fib_38_2:,.2f} / ${self.fib_50:,.2f} / ${self.fib_61_8:,.2f}",
            ),
        )


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
    ax.plot(view.index, close, color="#14263D", linewidth=1.8, label="Close")
    ax.plot(view.index, sma20, color="#B08D57", linewidth=1.1, label="SMA 20")
    ax.plot(view.index, sma50, color="#4E7298", linewidth=1.1, label="SMA 50")
    ax.scatter(pd.Timestamp(trade.entry_date), trade.entry_price, marker="^", s=80, color="#2E7D52", zorder=5, label=f"Entry ${trade.entry_price:,.2f}")
    ax.scatter(pd.Timestamp(trade.exit_date), trade.exit_price, marker="X", s=75, color="#A94442", zorder=5, label=f"Exit ${trade.exit_price:,.2f}")
    ax.axhline(trade.initial_stop, color="#A94442", linestyle="--", linewidth=1.0, label=f"Initial stop ${trade.initial_stop:,.2f}")
    ax.set_title(f"{ticker} - Historical Trade Case: {trade.entry_date} Entry", loc="left", color="#14263D", fontweight="bold")
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
    volume_ratio = float(volume.iloc[-1] / vol_avg) if vol_avg > 0 else 1.0
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
    trend = "above" if snapshot.price > snapshot.sma50 else "below"
    momentum = "positive" if snapshot.macd > snapshot.macd_signal else "negative"
    rsi_text = "overbought" if snapshot.rsi14 >= 70 else "oversold" if snapshot.rsi14 <= 30 else "neutral"
    if snapshot.price >= snapshot.fib_38_2:
        fibonacci_text = f"above the 38.2% retracement, in the upper portion of the {snapshot.fibonacci_range_label.lower()} swing range"
    elif snapshot.price >= snapshot.fib_50:
        fibonacci_text = "between the 38.2% and 50% retracement levels"
    elif snapshot.price >= snapshot.fib_61_8:
        fibonacci_text = "between the 50% and 61.8% retracement levels"
    else:
        fibonacci_text = "below the 61.8% retracement, signaling a deeper technical retracement"
    return SpecialistFinding(
        _rating(snapshot.score),
        f"Price is {trend} its 50-day trend measure; MACD momentum is {momentum}, while RSI is {rsi_text} at {snapshot.rsi14:.1f}.",
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
            f"Latest volume is {snapshot.volume_ratio:.2f}x the 20-day average.",
        ),
    )


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
    direction = "outperforming" if average_relative > 0 else "underperforming" if average_relative < 0 else "matching"
    symbols = ", ".join(comparison_histories)
    insight = (
        f"The stock returned {primary_return:+.1%} over the {return_label} and is {direction} the comparison set "
        f"({symbols}) by {average_relative:+.1%} on average."
    )
    if adjustment:
        insight += f" This moved the technical rating from {finding.rating.value} to {adjusted_rating.value}."
    else:
        insight += " Relative strength did not change the technical rating."
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


def render_chart(history: pd.DataFrame, ticker: str, snapshot: TechnicalSnapshot, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = history.dropna(subset=["Close"]).copy()
    if not history.attrs.get("custom_range"):
        frame = frame.tail(260)
    close = frame["Close"].astype(float)
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    fig, (ax, vol) = plt.subplots(2, 1, figsize=(10.5, 7.0), gridspec_kw={"height_ratios": [4, 1]}, sharex=True)
    fig.patch.set_facecolor("white")
    ax.plot(frame.index, close, color="#14263D", linewidth=1.8, label="Close")
    ax.plot(frame.index, sma20, color="#B08D57", linewidth=1.2, label="SMA 20")
    ax.plot(frame.index, sma50, color="#4E7298", linewidth=1.2, label="SMA 50")
    if sma200.notna().any():
        ax.plot(frame.index, sma200, color="#8B929A", linewidth=1.1, label="SMA 200")
    ax.set_title(
        f"{ticker} - Price Trend and Moving Averages",
        loc="left",
        color="#14263D",
        fontweight="bold",
    )
    ax.set_ylabel("Price (USD)")
    ax.grid(alpha=0.18)
    ax.legend(ncol=4, fontsize=8, frameon=False, loc="upper left")
    volume = frame["Volume"].fillna(0).astype(float)
    colors_v = np.where(close.diff().fillna(0) >= 0, "#6E9D85", "#C77A7A")
    vol.bar(frame.index, volume, color=colors_v, width=1.0, alpha=0.75)
    vol.set_ylabel("Volume")
    vol.grid(axis="y", alpha=0.15)
    vol.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    vol.xaxis.set_major_formatter(mdates.ConciseDateFormatter(vol.xaxis.get_major_locator()))
    fig.tight_layout()
    fig.savefig(destination, dpi=170, bbox_inches="tight")
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
    ax.plot(frame.index, close, color="#14263D", linewidth=1.9, label="Close")
    for level, label, color in (
        (snapshot.fib_swing_high, "Swing high", "#4A8A68"),
        (snapshot.fib_38_2, "38.2%", "#8E6BB8"),
        (snapshot.fib_50, "50.0%", "#7D7D7D"),
        (snapshot.fib_61_8, "61.8%", "#B06F57"),
        (snapshot.fib_swing_low, "Swing low", "#B65050"),
    ):
        ax.axhline(level, color=color, linestyle="--" if "Swing" in label else ":", linewidth=1.0, label=f"{label}  ${level:,.2f}")
    ax.set_title(
        f"{ticker} - {snapshot.fibonacci_range_label} Fibonacci Structure",
        loc="left",
        color="#14263D",
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
    rsi_ax.plot(rsi.index, rsi, color="#14263D", linewidth=1.5, label="RSI (14)")
    rsi_ax.axhline(70, color="#B65050", linestyle="--", linewidth=0.9)
    rsi_ax.axhline(30, color="#4A8A68", linestyle="--", linewidth=0.9)
    rsi_ax.fill_between(rsi.index, 30, 70, color="#F3F5F7", alpha=0.7)
    rsi_ax.set_ylim(0, 100)
    rsi_ax.set_ylabel("RSI")
    rsi_ax.set_title(f"{ticker} - Momentum: RSI and MACD", loc="left", color="#14263D", fontweight="bold")
    rsi_ax.grid(alpha=0.16)
    macd_ax.plot(macd.index, macd, color="#14263D", linewidth=1.3, label="MACD")
    macd_ax.plot(signal.index, signal, color="#B08D57", linewidth=1.2, label="Signal")
    colors_v = np.where(histogram >= 0, "#6E9D85", "#C77A7A")
    macd_ax.bar(histogram.index, histogram, color=colors_v, width=1.0, alpha=0.65, label="Histogram")
    macd_ax.axhline(0, color="#8B929A", linewidth=0.7)
    macd_ax.set_ylabel("MACD")
    macd_ax.grid(alpha=0.16)
    macd_ax.legend(ncol=3, fontsize=8, frameon=False, loc="upper left")
    macd_ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    macd_ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(macd_ax.xaxis.get_major_locator()))
    fig.tight_layout()
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
    palette = ["#14263D", "#B08D57", "#4E7298", "#6E9D85"]
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
    ax.axhline(100, color="#8B929A", linewidth=0.7)
    title = "Performance vs Sector Benchmark" if benchmark_symbol else "Normalized Relative Performance"
    ax.set_title(f"{title} - Starting Value 100", loc="left", color="#14263D", fontweight="bold")
    ax.set_ylabel("Indexed value")
    ax.grid(alpha=0.18)
    ax.legend(ncol=4, fontsize=8, frameon=False, loc="upper left")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    fig.tight_layout()
    fig.savefig(destination, dpi=170, bbox_inches="tight")
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
    return (
        f"{ticker}'s analysis-range maximum drawdown was {float(drawdown.min()):.1%}; ending drawdown is "
        f"{float(drawdown.iloc[-1]):.1%}, with three-month annualized volatility of {annualized_volatility:.1%}."
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
    drawdown_ax.plot(drawdown.index, drawdown, color="#B65050", linewidth=1.0)
    drawdown_ax.set_title(f"{ticker} - Drawdown and Realized Volatility", loc="left", color="#14263D", fontweight="bold")
    drawdown_ax.set_ylabel("Drawdown")
    drawdown_ax.yaxis.set_major_formatter(lambda value, _position: f"{value:.0%}")
    drawdown_ax.grid(alpha=0.16)
    volatility_ax.plot(volatility.index, volatility, color="#14263D", linewidth=1.4)
    volatility_ax.set_ylabel("20d ann. vol.")
    volatility_ax.yaxis.set_major_formatter(lambda value, _position: f"{value:.0%}")
    volatility_ax.grid(alpha=0.16)
    volatility_ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    volatility_ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(volatility_ax.xaxis.get_major_locator()))
    fig.tight_layout()
    fig.savefig(destination, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return destination
