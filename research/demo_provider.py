"""Deterministic demo provider for end-to-end UI and PDF validation.

This provider intentionally produces synthetic evidence. It must never be
presented as live market research.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import numpy as np
import pandas as pd

from core.models import (
    ComparisonAssessment,
    ChartRecord,
    Confidence,
    Rating,
    ResearchRequest,
    ResearchResult,
    SecurityIdentity,
    SourceRecord,
    SpecialistFinding,
    Strategy,
    TechnicalActionPlan,
)
from research.technical import (
    analyze_history,
    fibonacci_decision_insight,
    momentum_decision_insight,
    render_chart,
    render_fibonacci_chart,
    render_momentum_chart,
    render_total_return_chart,
    total_return_chart_insights,
)


KNOWN = {
    "AAPL": ("Apple Inc.", "AAPL", "NASDAQ"),
    "APPLE": ("Apple Inc.", "AAPL", "NASDAQ"),
    "AXON": ("Axon Enterprise, Inc.", "AXON", "NASDAQ"),
    "WMT": ("Walmart Inc.", "WMT", "NYSE"),
    "WALMART": ("Walmart Inc.", "WMT", "NYSE"),
    "MSFT": ("Microsoft Corporation", "MSFT", "NASDAQ"),
    "MICROSOFT": ("Microsoft Corporation", "MSFT", "NASDAQ"),
    "NVDA": ("NVIDIA Corporation", "NVDA", "NASDAQ"),
    "AVGO": ("Broadcom Inc.", "AVGO", "NASDAQ"),
    "SPY": ("SPDR S&P 500 ETF Trust", "SPY", "NYSE Arca"),
}


class DemoResearchProvider:
    """Return stable synthetic content without calling external services."""

    def run(self, request: ResearchRequest, workspace=None) -> ResearchResult:
        request.validate()
        key = request.query.strip().upper()
        company, ticker, exchange = KNOWN.get(
            key, (request.query.strip().title(), key.replace(" ", "")[:8], "Unconfirmed")
        )
        digest = hashlib.sha256(ticker.encode("utf-8")).digest()
        price = round(40 + int.from_bytes(digest[:2], "big") % 360 + digest[2] / 255, 2)
        now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="minutes")
        range_label = (
            f"{request.custom_start} to {request.custom_end}"
            if request.custom_start
            else "six-month"
        )
        technical = SpecialistFinding(
            Rating.ADD,
            "The synthetic multi-timeframe setup is constructive but requires confirmation.",
            (
                "Price is modeled above a rising intermediate trend average.",
                "Momentum is positive without an extreme synthetic reading.",
                f"Synthetic {range_label} Fibonacci retracement levels: 38.2% ${price * 0.94:,.2f}, 50% ${price * 0.90:,.2f}, and 61.8% ${price * 0.86:,.2f}.",
                "Volume confirmation remains incomplete in demo mode.",
            ),
        )
        entry_low = price * 0.93
        entry_high = price * 0.95
        entry_mid = (entry_low + entry_high) / 2
        stop_level = price * 0.87
        first_target = price * 1.08
        second_target = price * 1.14
        technical_plan = TechnicalActionPlan(
            stance="Add on a controlled pullback",
            market_condition="Trending higher - synthetic demo",
            order_type="Limit order near modeled support",
            entry_low=entry_low,
            entry_high=entry_high,
            stop_level=stop_level,
            stop_pct=(entry_mid - stop_level) / entry_mid,
            first_target=first_target,
            second_target=second_target,
            reward_risk=(first_target - entry_mid) / (entry_mid - stop_level),
            confirmation="The modeled support zone holds and momentum turns higher.",
            invalidation=f"A sustained close below ${stop_level:,.2f} invalidates the synthetic setup.",
            rationale=(
                "Entry is modeled near short-term trend and Fibonacci support.",
                "The stop is below modeled structure with a volatility buffer.",
                "Targets are synthetic workflow values and are not live forecasts.",
            ),
            options_strategy="Optional defined-risk bullish expression: call spread",
            options_structure="Synthetic planning example only; verify a live option chain, expiration, strikes, and liquidity.",
            options_risk="The entire debit can be lost and options are not suitable for every investor.",
        )
        chart_path = ""
        overview_chart = None
        if workspace is not None and not request.comparison_analysis:
            if request.custom_start and request.custom_end:
                dates = pd.bdate_range(request.custom_start, request.custom_end)
                period_start = request.custom_start
                period_end = request.custom_end
                period_label = f"{request.custom_start} to {request.custom_end}"
            else:
                dates = pd.bdate_range(end=dt.date.today(), periods=260)
                period_start = dt.date.today().replace(month=1, day=1).isoformat()
                period_end = dt.date.today().isoformat()
                period_label = "YTD"
            position = np.linspace(0, 1, len(dates))
            primary_shape = 0.82 + 0.18 * position + np.sin(position * 18) * 0.018
            primary_close = primary_shape / primary_shape[-1] * price
            spy_shape = 0.91 + 0.09 * position + np.sin(position * 12) * 0.009
            spy_close = spy_shape / spy_shape[-1] * 100
            primary_history = pd.DataFrame(
                {
                    "Close": primary_close,
                    "High": primary_close * 1.012,
                    "Low": primary_close * 0.988,
                    "Volume": np.linspace(900_000, 1_300_000, len(dates)),
                },
                index=dates,
            )
            spy_history = pd.DataFrame(
                {
                    "Close": spy_close,
                    "High": spy_close * 1.006,
                    "Low": spy_close * 0.994,
                    "Volume": np.linspace(50_000_000, 62_000_000, len(dates)),
                },
                index=dates,
            )
            demo_snapshot = analyze_history(primary_history)
            chart_path = str(
                render_chart(
                    primary_history,
                    ticker,
                    demo_snapshot,
                    workspace / "technical-chart.png",
                    technical_plan,
                )
            )
            if request.overview_chart == "price_trend":
                overview_chart = ChartRecord(
                    "Price Trend and Moving Averages",
                    chart_path,
                    technical.summary,
                    (technical.summary, *technical.signals[:2]),
                )
            elif request.overview_chart == "fibonacci":
                lead_path = render_fibonacci_chart(
                    primary_history,
                    ticker,
                    demo_snapshot,
                    workspace / "lead-fibonacci-chart.png",
                )
                insight = fibonacci_decision_insight(demo_snapshot, technical.rating)
                overview_chart = ChartRecord("Fibonacci Structure", str(lead_path), insight, (insight,))
            elif request.overview_chart == "momentum":
                lead_path = render_momentum_chart(
                    primary_history,
                    ticker,
                    workspace / "lead-momentum-chart.png",
                )
                insight = momentum_decision_insight(demo_snapshot, technical.rating)
                overview_chart = ChartRecord("Momentum - RSI and MACD", str(lead_path), insight, (insight,))
            else:
                overview_benchmark = "SPY" if ticker != "SPY" else ""
                histories = (
                    {ticker: primary_history, "SPY": spy_history}
                    if ticker != "SPY"
                    else {ticker: primary_history}
                )
                lead_path = render_total_return_chart(
                    histories,
                    workspace / "lead-total-return-chart.png",
                    period_label,
                    overview_benchmark,
                    period_start,
                    period_end,
                )
                insights = total_return_chart_insights(
                    histories,
                    ticker,
                    overview_benchmark,
                    period_label,
                    technical.rating,
                    period_start,
                    period_end,
                )
                overview_chart = ChartRecord(
                    f"{period_label} Total Return",
                    str(lead_path),
                    insights[0],
                    insights,
                )
        comparison = None
        if request.comparison_analysis:
            second_key = request.comparison_query.strip().upper()
            second_company, second_ticker, second_exchange = KNOWN.get(
                second_key,
                (request.comparison_query.strip().title(), second_key.replace(" ", "")[:8], "Unconfirmed"),
            )
            second_digest = hashlib.sha256(second_ticker.encode("utf-8")).digest()
            second_price = round(40 + int.from_bytes(second_digest[:2], "big") % 360 + second_digest[2] / 255, 2)
            secondary_technical = SpecialistFinding(
                Rating.HOLD,
                "The synthetic comparison setup is balanced and awaits stronger trend confirmation.",
                ("Synthetic momentum is neutral.", "Synthetic trend evidence is mixed."),
            )
            comparison = ComparisonAssessment(
                secondary_identity=SecurityIdentity(second_company, second_ticker, second_exchange, "USD"),
                secondary_price=second_price,
                secondary_technical=secondary_technical,
                preferred_ticker=ticker,
                verdict=f"{ticker} has the stronger synthetic {'range-end' if request.custom_start else 'current'} evidence profile for workflow testing.",
                rationale=(
                    f"{ticker} leads on the modeled technical setup and three-month return.",
                    "Demo values are synthetic and cannot support an investment decision.",
                ),
                metrics=(
                    ("Current price", f"${price:,.2f}", f"${second_price:,.2f}", "Reference only"),
                    ("Technical setup", "Bullish", "Neutral", ticker),
                    (
                        "Fibonacci position (38.2% / 50% / 61.8%)",
                        f"Above 38.2%; ${price * 0.94:,.2f} / ${price * 0.90:,.2f} / ${price * 0.86:,.2f}",
                        f"38.2%-50% zone; ${second_price * 0.94:,.2f} / ${second_price * 0.90:,.2f} / ${second_price * 0.86:,.2f}",
                        "Included in technical setup",
                    ),
                    ("Three-month return", "12.4%", "7.8%", ticker),
                    ("Forward P/E", "24.10x", "26.40x", ticker),
                ),
            )
        result = ResearchResult(
            identity=SecurityIdentity(company, ticker, exchange, "USD"),
            horizon=request.horizon,
            as_of=now,
            current_price=price,
            technical=technical,
            fundamental=SpecialistFinding(
                Rating.HOLD,
                "The synthetic business profile is stable, while valuation leaves limited margin for error.",
                (
                    "Modeled earnings direction is positive.",
                    "Modeled valuation is above its illustrative historical range.",
                    "No live SEC or YCharts facts are used in demo mode.",
                ),
            ),
            sentiment="Neutral to constructive in synthetic demo data; no public posts were retrieved.",
            lead_rating=Rating.ADD,
            confidence=Confidence.LOW,
            executive_summary=(
                f"Direct answer: the synthetic workflow rates {company} Add, but demo evidence cannot support a real buy or sell decision. "
                f"{company} receives an illustrative Add rating for the {request.horizon.value.lower()} horizon. "
                "The demo technical setup is constructive, while the demo fundamental view is more balanced. "
                "This result validates the application workflow and is not live investment research."
            ),
            key_metrics=(
                ("Illustrative current price", f"${price:,.2f}"),
                ("Technical setup", "Bullish"),
                ("Fundamental outlook", "Balanced"),
                ("Overall confidence", "Low — demo evidence"),
                (
                    "Fibonacci 38.2% / 50% / 61.8%",
                    f"${price * 0.94:,.2f} / ${price * 0.90:,.2f} / ${price * 0.86:,.2f}",
                ),
            ),
            strategies=(
                Strategy(
                    "Confirmation entry",
                    f"After a confirmed move above modeled resistance with Fibonacci support near ${price * 0.90:,.2f}",
                    "Price and volume confirm together",
                    "Close back below the breakout area",
                    "False breakout and broad-market reversal",
                ),
                Strategy(
                    "Pullback monitor",
                    f"Near modeled trend support and the synthetic 50% Fibonacci level at ${price * 0.90:,.2f}",
                    "Support holds and momentum turns higher",
                    "Sustained break below modeled support",
                    "Momentum deterioration",
                ),
            ),
            risks=(
                "All values and signals in this build are synthetic.",
                "Live earnings, valuation, chart, and event risks have not been retrieved.",
            ),
            catalysts=("Live catalyst research is not connected in demo mode.",),
            change_conditions=(
                "A live-source conflict or materially different technical structure.",
                "New official filings, earnings results, or guidance.",
            ),
            sources=(
                SourceRecord("Researcheus Demo Provider", "synthetic://demo", now, "Workflow validation only"),
            ),
            provider_label="Deterministic demo provider",
            request_response=(
                f"This demo report addresses the request about {company.rstrip('.')}. Live provider facts are required for a client-ready answer."
                if request.question.strip()
                else ""
            ),
            limitations=("Synthetic values only; no live research sources were contacted.",),
            demo_mode=True,
            chart_path=chart_path,
            analysis_mode=(
                "Security Comparison"
                if request.comparison_analysis
                else "Deep Technical Analysis"
                if request.deep_analysis
                else "Standard Research"
            ),
            comparison=comparison,
            ycharts_status="YCharts is not queried in Demo / Offline Test mode.",
            technical_plan=technical_plan,
            overview_chart=overview_chart,
        )
        result.validate()
        return result
