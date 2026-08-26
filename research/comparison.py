"""Deterministic, transparent two-security comparison scoring."""

from __future__ import annotations

from collections.abc import Callable

from core.assessments import technical_setup
from core.models import ComparisonAssessment, Rating, SecurityIdentity, SpecialistFinding
from research.technical import TechnicalSnapshot


def _number(mapping: dict, *keys: str) -> float | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _money(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    return f"${value:,.2f}"


def _percent(value: float) -> str:
    return f"{value:.1%}"


def _multiple(value: float) -> str:
    return f"{value:.2f}x"


def _target_upside(info: dict, price: float) -> float | None:
    target = _number(info, "targetMeanPrice")
    return target / price - 1 if target is not None and target > 0 and price > 0 else None


def _fibonacci_context(snapshot: TechnicalSnapshot) -> str:
    if snapshot.price >= snapshot.fib_38_2:
        position = "Above 38.2%"
    elif snapshot.price >= snapshot.fib_50:
        position = "38.2%-50% zone"
    elif snapshot.price >= snapshot.fib_61_8:
        position = "50%-61.8% zone"
    else:
        position = "Below 61.8%"
    return (
        f"{position}; ${snapshot.fib_38_2:,.2f} / "
        f"${snapshot.fib_50:,.2f} / ${snapshot.fib_61_8:,.2f}"
    )


def build_comparison_assessment(
    primary_identity: SecurityIdentity,
    primary_price: float,
    primary_info: dict,
    primary_snapshot: TechnicalSnapshot,
    primary_technical: SpecialistFinding,
    secondary_identity: SecurityIdentity,
    secondary_price: float,
    secondary_info: dict,
    secondary_snapshot: TechnicalSnapshot,
    secondary_technical: SpecialistFinding,
) -> ComparisonAssessment:
    """Compare only like-for-like available evidence and disclose every scoring edge."""
    rows: list[tuple[str, str, str, str]] = []
    primary_score = 0
    secondary_score = 0
    primary_edges: list[str] = []
    secondary_edges: list[str] = []

    price_label = (
        "Range-end price"
        if primary_snapshot.fibonacci_range_label != "Six-month"
        else "Current price"
    )
    rows.append((price_label, _money(primary_price), _money(secondary_price), "Reference only"))

    ratings = list(Rating)
    primary_rating_index = ratings.index(primary_technical.rating)
    secondary_rating_index = ratings.index(secondary_technical.rating)
    if primary_rating_index < secondary_rating_index:
        edge = primary_identity.ticker
        primary_score += 1
        primary_edges.append("stronger technical setup")
    elif secondary_rating_index < primary_rating_index:
        edge = secondary_identity.ticker
        secondary_score += 1
        secondary_edges.append("stronger technical setup")
    else:
        edge = "Comparable"
    rows.append(
        (
            "Technical setup",
            technical_setup(primary_technical.rating),
            technical_setup(secondary_technical.rating),
            edge,
        )
    )
    rows.append(
        (
            "Fibonacci position (38.2% / 50% / 61.8%)",
            _fibonacci_context(primary_snapshot),
            _fibonacci_context(secondary_snapshot),
            "Included in technical setup",
        )
    )

    def add_metric(
        label: str,
        primary_value: float | None,
        secondary_value: float | None,
        formatter: Callable[[float], str],
        *,
        higher_is_better: bool,
        reason: str,
        minimum_gap: float = 0.05,
        require_positive: bool = False,
    ) -> None:
        nonlocal primary_score, secondary_score
        if primary_value is None or secondary_value is None:
            return
        if require_positive and (primary_value <= 0 or secondary_value <= 0):
            return
        scale = max(abs(primary_value), abs(secondary_value), 1e-9)
        comparable = abs(primary_value - secondary_value) / scale < minimum_gap
        if comparable:
            edge = "Comparable"
        else:
            primary_wins = primary_value > secondary_value if higher_is_better else primary_value < secondary_value
            if primary_wins:
                edge = primary_identity.ticker
                primary_score += 1
                primary_edges.append(reason)
            else:
                edge = secondary_identity.ticker
                secondary_score += 1
                secondary_edges.append(reason)
        rows.append((label, formatter(primary_value), formatter(secondary_value), edge))

    add_metric(
        f"{primary_snapshot.performance_label} return",
        primary_snapshot.analysis_return if primary_snapshot.analysis_return is not None else primary_snapshot.return_3m,
        secondary_snapshot.analysis_return if secondary_snapshot.analysis_return is not None else secondary_snapshot.return_3m,
        _percent,
        higher_is_better=True,
        reason="stronger three-month performance",
        minimum_gap=0.15,
    )
    add_metric(
        "Forward P/E",
        _number(primary_info, "forwardPE"),
        _number(secondary_info, "forwardPE"),
        _multiple,
        higher_is_better=False,
        reason="lower forward earnings multiple",
        require_positive=True,
    )
    add_metric(
        "Price / sales",
        _number(primary_info, "priceToSalesTrailing12Months"),
        _number(secondary_info, "priceToSalesTrailing12Months"),
        _multiple,
        higher_is_better=False,
        reason="lower sales multiple",
        require_positive=True,
    )
    add_metric(
        "Revenue growth",
        _number(primary_info, "revenueGrowth"),
        _number(secondary_info, "revenueGrowth"),
        _percent,
        higher_is_better=True,
        reason="stronger revenue growth",
        minimum_gap=0.15,
    )
    add_metric(
        "Earnings growth",
        _number(primary_info, "earningsGrowth"),
        _number(secondary_info, "earningsGrowth"),
        _percent,
        higher_is_better=True,
        reason="stronger earnings growth",
        minimum_gap=0.15,
    )
    add_metric(
        "Profit margin",
        _number(primary_info, "profitMargins"),
        _number(secondary_info, "profitMargins"),
        _percent,
        higher_is_better=True,
        reason="higher profit margin",
        minimum_gap=0.10,
    )
    add_metric(
        "Analyst target upside",
        _target_upside(primary_info, primary_price),
        _target_upside(secondary_info, secondary_price),
        _percent,
        higher_is_better=True,
        reason="greater available analyst-target upside",
        minimum_gap=0.15,
    )
    add_metric(
        "Fund expense ratio",
        _number(primary_info, "annualReportExpenseRatio", "netExpenseRatio"),
        _number(secondary_info, "annualReportExpenseRatio", "netExpenseRatio"),
        _percent,
        higher_is_better=False,
        reason="lower fund expense ratio",
        require_positive=True,
    )
    add_metric(
        "Three-year average return",
        _number(primary_info, "threeYearAverageReturn"),
        _number(secondary_info, "threeYearAverageReturn"),
        _percent,
        higher_is_better=True,
        reason="higher three-year average return",
        minimum_gap=0.10,
    )

    evidence_context = (
        "range-end"
        if primary_snapshot.fibonacci_range_label != "Six-month"
        else "current"
    )
    if primary_score > secondary_score:
        preferred = primary_identity.ticker
        verdict = (
            f"{primary_identity.ticker} has the stronger {evidence_context} evidence profile, scoring "
            f"{primary_score} category edges to {secondary_score}."
        )
    elif secondary_score > primary_score:
        preferred = secondary_identity.ticker
        verdict = (
            f"{secondary_identity.ticker} has the stronger {evidence_context} evidence profile, scoring "
            f"{secondary_score} category edges to {primary_score}."
        )
    else:
        preferred = "No clear edge"
        verdict = (
            f"The available evidence does not establish a clear winner; both securities score {primary_score} category edges."
        )

    rationale = []
    if primary_edges:
        rationale.append(f"{primary_identity.ticker} leads on " + ", ".join(dict.fromkeys(primary_edges)) + ".")
    if secondary_edges:
        rationale.append(f"{secondary_identity.ticker} leads on " + ", ".join(dict.fromkeys(secondary_edges)) + ".")
    rationale.append("The preference is evidence-relative, not a universal recommendation; portfolio role, taxes, and risk capacity can change the decision.")
    return ComparisonAssessment(
        secondary_identity,
        secondary_price,
        secondary_technical,
        preferred,
        verdict,
        tuple(rationale),
        tuple(rows),
    )
