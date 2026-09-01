"""Build a validated ResearchRequest from raw user prompt text.

Extracted from the desktop UI so the PySide6 app and the web backend build
requests through exactly one code path -- a question typed into the desktop
window and the same question posted to the API must parse identically, or the
two surfaces would silently disagree about horizon, custom range, or intent.
"""

from __future__ import annotations

from core.models import Horizon, ResearchRequest
from core.research_prompt import (
    classify_research_intent,
    is_historical_trade_request,
    parse_comparison_prompt,
    parse_custom_range,
    parse_deep_analysis_prompt,
    parse_horizon,
    parse_overview_chart_request,
    parse_portfolio_allocation,
    parse_research_prompt,
)

_HISTORICAL_TRADE_CHARTS = (
    "price_trend",
    "stop_loss",
    "momentum",
    "relative_performance",
    "historical_trades",
)


def horizon_from_text(brief: str) -> Horizon:
    """The horizon stated in the question, defaulting to All Horizons."""
    stated = parse_horizon(brief)
    for horizon in Horizon:
        if horizon.value == stated:
            return horizon
    return Horizon.ALL


def build_general_request(text: str) -> ResearchRequest:
    """General Research: the default question-first workflow."""
    security_query, research_brief = parse_research_prompt(text)
    custom_start, custom_end = parse_custom_range(research_brief)
    historical_trades = is_historical_trade_request(research_brief)
    return ResearchRequest(
        security_query,
        horizon_from_text(research_brief),
        question=research_brief,
        deep_analysis=historical_trades,
        comparison_symbols=("SPY",) if historical_trades else (),
        requested_charts=_HISTORICAL_TRADE_CHARTS if historical_trades else (),
        custom_start=custom_start,
        custom_end=custom_end,
        decision_intent=classify_research_intent(research_brief),
        portfolio_allocation=parse_portfolio_allocation(research_brief),
        historical_trade_examples=historical_trades,
        overview_chart=parse_overview_chart_request(research_brief),
    )


def build_deep_request(text: str) -> ResearchRequest:
    """Deep Technical Analysis: the detailed multi-chart technical workflow."""
    security_query, brief, comparisons, charts = parse_deep_analysis_prompt(text)
    custom_start, custom_end = parse_custom_range(brief)
    return ResearchRequest(
        security_query,
        Horizon.ALL,
        question=brief,
        deep_analysis=True,
        comparison_symbols=comparisons,
        requested_charts=charts,
        custom_start=custom_start,
        custom_end=custom_end,
        decision_intent=classify_research_intent(brief),
        overview_chart=parse_overview_chart_request(brief),
    )


def build_comparison_request(text: str) -> ResearchRequest:
    """Security Comparison: two securities weighed against each other."""
    primary, secondary, brief = parse_comparison_prompt(text)
    custom_start, custom_end = parse_custom_range(brief)
    return ResearchRequest(
        primary,
        Horizon.ALL,
        question=brief,
        comparison_analysis=True,
        comparison_query=secondary,
        custom_start=custom_start,
        custom_end=custom_end,
        decision_intent=classify_research_intent(brief),
        overview_chart=parse_overview_chart_request(brief),
    )


def build_request(text: str, mode: str) -> ResearchRequest:
    """Dispatch to the builder for one of the three research modes."""
    builders = {
        "general": build_general_request,
        "deep": build_deep_request,
        "comparison": build_comparison_request,
    }
    if mode not in builders:
        raise ValueError(f"Unknown research mode: {mode!r}")
    request = builders[mode](text)
    request.validate()
    return request
