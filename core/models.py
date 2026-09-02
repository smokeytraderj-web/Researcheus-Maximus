"""Typed boundaries for the investment-research workflow."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from enum import Enum

from core.conviction_checklist import ConvictionChecklist


class Horizon(str, Enum):
    SHORT = "Short Term"
    MEDIUM = "Medium Term"
    LONG = "Long Term"
    ALL = "All Horizons"


class Rating(str, Enum):
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    ADD = "Add"
    HOLD = "Hold"
    REDUCE = "Reduce"
    SELL = "Sell"
    AVOID = "Avoid"


class Confidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    query: str
    horizon: Horizon
    purchase_price: float | None = None
    quantity: float | None = None
    risk_tolerance: str = ""
    question: str = ""
    deep_analysis: bool = False
    comparison_symbols: tuple[str, ...] = ()
    requested_charts: tuple[str, ...] = ()
    comparison_analysis: bool = False
    comparison_query: str = ""
    custom_start: str = ""
    custom_end: str = ""
    decision_intent: str = "research"
    portfolio_allocation: tuple[int, int] = ()
    historical_trade_examples: bool = False
    overview_chart: str = ""

    def validate(self) -> None:
        if not self.query.strip():
            raise ValueError("Enter a company name or ticker.")
        if self.purchase_price is not None and self.purchase_price <= 0:
            raise ValueError("Purchase price must be greater than zero.")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if len(self.comparison_symbols) > 3:
            raise ValueError("Deep analysis supports up to three comparison symbols.")
        if self.overview_chart not in {"", "relative_performance", "price_trend", "stop_loss", "fibonacci", "momentum"}:
            raise ValueError("The requested overview chart is not supported.")
        if self.portfolio_allocation:
            if len(self.portfolio_allocation) != 2 or sum(self.portfolio_allocation) != 100:
                raise ValueError("Portfolio allocation must contain equity and fixed-income percentages totaling 100%.")
        if self.comparison_analysis and not self.comparison_query.strip():
            raise ValueError("Enter two securities or funds to compare.")
        if bool(self.custom_start) != bool(self.custom_end):
            raise ValueError("A custom analysis range requires both a start and end date.")
        if self.custom_start and self.custom_end:
            try:
                start = dt.date.fromisoformat(self.custom_start)
                end = dt.date.fromisoformat(self.custom_end)
            except ValueError as exc:
                raise ValueError("Custom analysis dates must use YYYY-MM-DD format.") from exc
            if start >= end:
                raise ValueError("The custom analysis start date must be before the end date.")
            if end > dt.date.today():
                raise ValueError("The custom analysis end date cannot be in the future.")
            if (end - start).days < 90:
                raise ValueError("Choose at least a 90-day custom range for reliable technical analysis.")


@dataclass(frozen=True, slots=True)
class SecurityIdentity:
    company_name: str
    ticker: str
    exchange: str
    currency: str


@dataclass(frozen=True, slots=True)
class SourceRecord:
    name: str
    locator: str
    retrieved_at: str
    supports: str


@dataclass(frozen=True, slots=True)
class HouseView:
    """A named research house's published view on a security.

    Third-party commentary, carried as attributed data rather than reproduced
    analysis: a rating, a target, a credit view and the date they were
    published, with the document they came from.

    The house's rating is kept verbatim and is never mapped into this app's own
    seven-label scale. An Overweight from J.P. Morgan is not this app's Buy --
    the scales have different definitions and different horizons -- and
    collapsing them would let another firm's call be read as ours. It is shown
    beside the Lead rating as evidence, exactly as the source hierarchy places
    analyst commentary: an input, never the conclusion.
    """

    house: str
    ticker: str
    equity_rating: str = ""
    price_target: float | None = None
    currency: str = "USD"
    target_horizon: str = ""
    credit_rating: str = ""
    credit_rating_scale: str = ""
    analyst: str = ""
    published: str = ""
    document: str = ""
    locator: str = ""
    retrieved_at: str = ""
    profile: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.house.strip():
            raise ValueError("A house view must name the house that published it.")
        if not self.ticker.strip():
            raise ValueError("A house view must name the security it covers.")
        if not (self.equity_rating.strip() or self.credit_rating.strip()
                or self.price_target is not None):
            raise ValueError(
                "A house view must carry a rating, a credit rating or a price target; "
                "an empty citation is not evidence."
            )
        if self.price_target is not None and self.price_target <= 0:
            raise ValueError("A price target must be greater than zero.")
        # An undated rating cannot be weighed: the reader has no way to tell a
        # view published yesterday from one published two years ago.
        if not self.published.strip():
            raise ValueError("A house view must carry the date it was published.")

    def age_days(self, as_of: str) -> int | None:
        """Days between publication and the analysis date, or None if unparseable."""
        import datetime as _dt

        try:
            published = _dt.date.fromisoformat(self.published.strip()[:10])
            current = _dt.date.fromisoformat(as_of.strip()[:10])
        except (ValueError, AttributeError):
            return None
        return (current - published).days


@dataclass(frozen=True, slots=True)
class SpecialistFinding:
    rating: Rating
    summary: str
    signals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Strategy:
    name: str
    action_zone: str
    confirmation: str
    invalidation: str
    risk: str


@dataclass(frozen=True, slots=True)
class TechnicalActionPlan:
    stance: str
    market_condition: str
    order_type: str
    entry_low: float
    entry_high: float
    stop_level: float
    stop_pct: float
    first_target: float
    second_target: float
    reward_risk: float
    confirmation: str
    invalidation: str
    rationale: tuple[str, ...]
    options_strategy: str = ""
    options_structure: str = ""
    options_risk: str = ""


@dataclass(frozen=True, slots=True)
class ChartRecord:
    title: str
    path: str
    insight: str
    insights: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoricalTradeCase:
    signal_date: str
    entry_date: str
    entry_price: float
    initial_stop: float
    exit_date: str
    exit_price: float
    return_pct: float
    outcome: str
    rationale: str
    exit_reason: str
    chart_path: str = ""


@dataclass(frozen=True, slots=True)
class PortfolioFitAssessment:
    equity_target_pct: int
    fixed_income_target_pct: int
    security_role: str
    fit_label: str
    summary: str
    evidence: tuple[str, ...]
    watchouts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComparisonAssessment:
    secondary_identity: SecurityIdentity
    secondary_price: float
    secondary_technical: SpecialistFinding
    preferred_ticker: str
    verdict: str
    rationale: tuple[str, ...]
    metrics: tuple[tuple[str, str, str, str], ...]
    benchmark_ticker: str = ""
    benchmark_label: str = ""
    benchmark_return: float | None = None
    primary_chart_return: float | None = None
    secondary_chart_return: float | None = None


@dataclass(frozen=True, slots=True)
class ResearchResult:
    identity: SecurityIdentity
    horizon: Horizon
    as_of: str
    current_price: float
    technical: SpecialistFinding
    fundamental: SpecialistFinding
    sentiment: str
    lead_rating: Rating
    confidence: Confidence
    executive_summary: str
    key_metrics: tuple[tuple[str, str], ...]
    strategies: tuple[Strategy, ...]
    risks: tuple[str, ...]
    catalysts: tuple[str, ...]
    change_conditions: tuple[str, ...]
    sources: tuple[SourceRecord, ...]
    provider_label: str = ""
    request_response: str = ""
    limitations: tuple[str, ...] = ()
    chart_path: str = ""
    demo_mode: bool = False
    ycharts_audit: tuple[tuple[str, str, str], ...] = ()
    analysis_mode: str = "Standard Research"
    chartbook: tuple[ChartRecord, ...] = ()
    comparison: ComparisonAssessment | None = None
    ycharts_status: str = ""
    historical_trade_cases: tuple[HistoricalTradeCase, ...] = ()
    portfolio_fit: PortfolioFitAssessment | None = None
    technical_plan: TechnicalActionPlan | None = None
    overview_chart: ChartRecord | None = None
    conviction_checklist: ConvictionChecklist | None = None
    house_views: tuple[HouseView, ...] = ()

    def validate(self) -> None:
        if self.current_price <= 0:
            raise ValueError("Current price must be greater than zero.")
        if not self.sources:
            raise ValueError("At least one source record is required.")
        if not self.executive_summary.strip():
            raise ValueError("Executive summary is required.")


@dataclass(frozen=True, slots=True)
class TVGaugeReading:
    timeframe: str
    rating_label: str
    rating_value: float
    oscillators_label: str
    moving_averages_label: str
    indicators: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, slots=True)
class TVLevel:
    label: str
    price: float
    pct_from_now: float


@dataclass(frozen=True, slots=True)
class TVTechnicalReport:
    query: str
    resolved_symbol: str
    company_name: str
    current_price: float
    change_pct: float
    as_of: str
    gauges: tuple[TVGaugeReading, ...]
    confluence_label: str
    levels: tuple[TVLevel, ...]
    summary_bullets: tuple[tuple[str, str], ...]
    headline: str
    chart_read: str
    market_cap: float | None
    volume: float | None
    beta: float | None
    period_returns: tuple[tuple[str, float], ...]
    analyst_rating: str
    analyst_score: float | None
    price_target_low: float | None
    price_target_avg: float | None
    price_target_high: float | None
    price_chart_path: str
    sparkline_path: str
    sources: tuple[SourceRecord, ...]
    error: str = ""

    @property
    def available(self) -> bool:
        return not self.error and bool(self.resolved_symbol)
