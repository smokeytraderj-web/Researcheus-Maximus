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
    score: int

    def as_metrics(self) -> tuple[tuple[str, str], ...]:
        sma200 = "Unavailable" if self.sma200 is None else f"${self.sma200:,.2f}"
        return (
            ("20-day moving average", f"${self.sma20:,.2f}"),
            ("50-day moving average", f"${self.sma50:,.2f}"),
            ("200-day moving average", sma200),
            ("RSI (14)", f"{self.rsi14:.1f}"),
            ("MACD / signal", f"{self.macd:.2f} / {self.macd_signal:.2f}"),
            ("ATR (14)", f"${self.atr14:,.2f}"),
            ("Volume vs. 20-day avg.", f"{self.volume_ratio:.2f}x"),
            ("60-day support / resistance", f"${self.support:,.2f} / ${self.resistance:,.2f}"),
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
    return_1m = float(price / close.iloc[-22] - 1) if len(close) >= 22 else 0.0
    return_3m = float(price / close.iloc[-64] - 1) if len(close) >= 64 else 0.0
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
    score += 1 if return_3m > 0 else -1
    return TechnicalSnapshot(price, sma20, sma50, sma200, rsi14, macd, macd_signal, atr14, volume_ratio, support, resistance, return_1m, return_3m, score)


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
    return SpecialistFinding(
        _rating(snapshot.score),
        f"Price is {trend} its 50-day trend measure; MACD momentum is {momentum}, while RSI is {rsi_text} at {snapshot.rsi14:.1f}.",
        (
            f"Price ${snapshot.price:,.2f} versus 20-day SMA ${snapshot.sma20:,.2f} and 50-day SMA ${snapshot.sma50:,.2f}.",
            f"One-month return {snapshot.return_1m:+.1%}; three-month return {snapshot.return_3m:+.1%}.",
            f"MACD {snapshot.macd:.2f} versus signal {snapshot.macd_signal:.2f}; RSI (14) {snapshot.rsi14:.1f}.",
            f"60-day observed range ${snapshot.support:,.2f} to ${snapshot.resistance:,.2f}; ATR (14) ${snapshot.atr14:,.2f}.",
            f"Latest volume is {snapshot.volume_ratio:.2f}x the 20-day average.",
        ),
    )


def strategies(snapshot: TechnicalSnapshot, horizon: Horizon) -> tuple[Strategy, ...]:
    buffer = max(snapshot.atr14 * 0.5, snapshot.price * 0.005)
    if snapshot.price < snapshot.sma20:
        first = Strategy(
            "Trend reclaim / staged entry",
            f"Wait for a close back through ${snapshot.sma20 - buffer:,.2f}-${snapshot.sma20 + buffer:,.2f}; the current price is below this zone",
            "The zone is reclaimed on a closing basis and MACD momentum turns higher",
            f"Sustained close below ${snapshot.support - buffer:,.2f}",
            "Buying before trend repair can add exposure while downside momentum remains active",
        )
    else:
        first = Strategy(
            "Pullback entry or add",
            f"Monitor ${snapshot.sma20 - buffer:,.2f}-${snapshot.sma20 + buffer:,.2f} around the 20-day trend",
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
    frame = history.dropna(subset=["Close"]).tail(260).copy()
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
    ax.set_title(f"{ticker} — Price, Trend, Support and Resistance", loc="left", color="#14263D", fontweight="bold")
    ax.set_ylabel("Price (USD)")
    ax.grid(alpha=0.18)
    ax.legend(ncol=3, fontsize=8, frameon=False, loc="upper left")
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
