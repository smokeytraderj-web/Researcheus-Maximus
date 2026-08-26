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

from core.models import Horizon, Rating, SpecialistFinding, Strategy


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
            "Trend reclaim / staged entry",
            f"Wait for a close back through ${snapshot.sma20 - buffer:,.2f}-${snapshot.sma20 + buffer:,.2f}; monitor Fibonacci support at ${snapshot.fib_50:,.2f} and ${snapshot.fib_61_8:,.2f}",
            "The zone is reclaimed on a closing basis and MACD momentum turns higher",
            f"Sustained close below ${snapshot.support - buffer:,.2f}",
            "Buying before trend repair can add exposure while downside momentum remains active",
        )
    else:
        first = Strategy(
            "Pullback entry or add",
            f"Monitor ${snapshot.sma20 - buffer:,.2f}-${snapshot.sma20 + buffer:,.2f} around the 20-day trend, with Fibonacci support at ${snapshot.fib_50:,.2f} and ${snapshot.fib_61_8:,.2f}",
            "The zone holds on a closing basis and momentum turns higher",
            f"Sustained close below ${min(snapshot.support, snapshot.sma50) - buffer:,.2f}",
            "Trend support can fail during event-driven or broad-market selling",
        )
    return (
        first,
        Strategy(
            "Breakout confirmation",
            f"Above ${snapshot.resistance + buffer:,.2f} after a confirmed range breakout",
            "Closing breakout with above-average volume and positive relative momentum",
            f"Close back below ${snapshot.resistance - buffer:,.2f}",
            "False breakout, gap reversal, or weak volume confirmation",
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
    ax.axhline(snapshot.support, color="#B65050", linestyle="--", linewidth=0.9, label="60d support")
    ax.axhline(snapshot.resistance, color="#4A8A68", linestyle="--", linewidth=0.9, label="60d resistance")
    for level, label, color in (
        (snapshot.fib_38_2, "Fib 38.2%", "#8E6BB8"),
        (snapshot.fib_50, "Fib 50%", "#7D7D7D"),
        (snapshot.fib_61_8, "Fib 61.8%", "#B06F57"),
    ):
        ax.axhline(level, color=color, linestyle=":", linewidth=0.9, label=label)
    ax.set_title(
        f"{ticker} - Price, Trend, Fibonacci, Support and Resistance",
        loc="left",
        color="#14263D",
        fontweight="bold",
    )
    ax.set_ylabel("Price (USD)")
    ax.grid(alpha=0.18)
    ax.legend(ncol=4, fontsize=7.2, frameon=False, loc="upper left")
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
        ax.plot(
            normalized.index,
            normalized[column],
            color=palette[index % len(palette)],
            linewidth=1.8 if index == 0 else 1.25,
            label=column,
        )
    ax.axhline(100, color="#8B929A", linewidth=0.7)
    ax.set_title("Normalized Relative Performance - Starting Value 100", loc="left", color="#14263D", fontweight="bold")
    ax.set_ylabel("Indexed value")
    ax.grid(alpha=0.18)
    ax.legend(ncol=4, fontsize=8, frameon=False, loc="upper left")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    fig.tight_layout()
    fig.savefig(destination, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return destination


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
