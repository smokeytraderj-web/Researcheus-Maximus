"""Typed boundaries for the single-stock research workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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

    def validate(self) -> None:
        if not self.query.strip():
            raise ValueError("Enter a company name or ticker.")
        if self.purchase_price is not None and self.purchase_price <= 0:
            raise ValueError("Purchase price must be greater than zero.")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if len(self.comparison_symbols) > 3:
            raise ValueError("Deep analysis supports up to three comparison symbols.")


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
class ChartRecord:
    title: str
    path: str
    insight: str


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
    limitations: tuple[str, ...] = ()
    chart_path: str = ""
    demo_mode: bool = False
    ycharts_audit: tuple[tuple[str, str, str], ...] = ()
    analysis_mode: str = "Standard Research"
    chartbook: tuple[ChartRecord, ...] = ()

    def validate(self) -> None:
        if self.current_price <= 0:
            raise ValueError("Current price must be greater than zero.")
        if not self.sources:
            raise ValueError("At least one source record is required.")
        if not self.executive_summary.strip():
            raise ValueError("Executive summary is required.")
