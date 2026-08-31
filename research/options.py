"""Options-implied evidence: what the option market is pricing for this security.

Deliberately narrow.  The available chain carries strikes, expiries, prices, IV and
Greeks, but **no open interest and no volume**, and no historical IV.  So this module
publishes what that data genuinely supports -- at-the-money implied volatility, the
expected move it implies, delta skew, and the term structure -- and does not attempt
IV rank, put/call ratio, or max pain, which cannot be computed from it without
inventing inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_TRADING_DAYS_PER_YEAR = 365.0
_SKEW_DELTA = 0.25


@dataclass(frozen=True, slots=True)
class ExpiryVolatility:
    expiration: str
    days_to_expiry: int
    atm_iv: float
    expected_move: float
    expected_move_pct: float
    put_skew: float | None  # 25-delta put IV minus 25-delta call IV, in IV points


@dataclass(frozen=True, slots=True)
class OptionsSnapshot:
    symbol: str
    spot: float
    expiries: tuple[ExpiryVolatility, ...]
    smile_strikes: tuple[float, ...]
    smile_call_iv: tuple[float, ...]
    smile_put_iv: tuple[float, ...]
    smile_expiration: str
    error: str = ""

    @property
    def available(self) -> bool:
        return not self.error and bool(self.expiries)

    @property
    def front(self) -> ExpiryVolatility | None:
        return self.expiries[0] if self.expiries else None


def _interpolate(x_values: list[float], y_values: list[float], target: float) -> float | None:
    """Linear interpolation on points sorted by x, refusing to extrapolate.

    Returning ``None`` outside the sampled range matters: a chain that only reaches
    0.32 delta cannot report a 0.25-delta figure, and guessing one would be a
    fabricated number presented as an observation.
    """
    pairs = sorted(
        (x, y) for x, y in zip(x_values, y_values) if x is not None and y is not None
    )
    if len(pairs) < 2:
        return None
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    if target < xs[0] or target > xs[-1]:
        return None
    for index in range(1, len(xs)):
        if xs[index] >= target:
            left_x, right_x = xs[index - 1], xs[index]
            left_y, right_y = ys[index - 1], ys[index]
            if right_x == left_x:
                return left_y
            weight = (target - left_x) / (right_x - left_x)
            return left_y + weight * (right_y - left_y)
    return ys[-1]


def atm_implied_volatility(contracts: list[dict], spot: float) -> float | None:
    """IV at the money, interpolated across strikes rather than snapped to one row."""
    strikes = [c.get("strike") for c in contracts]
    ivs = [c.get("iv") for c in contracts]
    interpolated = _interpolate(strikes, ivs, spot)
    if interpolated is not None:
        return interpolated
    # Spot outside the quoted strikes: fall back to the nearest quoted strike.
    usable = [c for c in contracts if c.get("strike") is not None and c.get("iv") is not None]
    if not usable:
        return None
    return float(min(usable, key=lambda c: abs(float(c["strike"]) - spot))["iv"])


def expected_move(spot: float, annual_iv_pct: float, days_to_expiry: int) -> float:
    """One standard-deviation move implied for the period, in price terms."""
    if spot <= 0 or annual_iv_pct <= 0 or days_to_expiry <= 0:
        return 0.0
    return spot * (annual_iv_pct / 100.0) * math.sqrt(days_to_expiry / _TRADING_DAYS_PER_YEAR)


def delta_skew(calls: list[dict], puts: list[dict], target_delta: float = _SKEW_DELTA) -> float | None:
    """25-delta put IV minus 25-delta call IV, in IV points.

    Positive means downside protection is priced richer than equivalent upside --
    the market is paying up for puts.  ``None`` when the chain does not quote far
    enough out to reach that delta on both sides.
    """
    put_iv = _interpolate(
        [abs(p["delta"]) for p in puts if p.get("delta") is not None and p.get("iv") is not None],
        [p["iv"] for p in puts if p.get("delta") is not None and p.get("iv") is not None],
        target_delta,
    )
    call_iv = _interpolate(
        [abs(c["delta"]) for c in calls if c.get("delta") is not None and c.get("iv") is not None],
        [c["iv"] for c in calls if c.get("delta") is not None and c.get("iv") is not None],
        target_delta,
    )
    if put_iv is None or call_iv is None:
        return None
    return put_iv - call_iv


def build_expiry_volatility(chain: dict) -> ExpiryVolatility | None:
    """Summarise one expiration's chain, or None when it carries nothing usable."""
    calls = [c for c in (chain.get("calls") or []) if isinstance(c, dict)]
    puts = [p for p in (chain.get("puts") or []) if isinstance(p, dict)]
    if not calls and not puts:
        return None
    spot = chain.get("underlying_price")
    if not isinstance(spot, (int, float)) or spot <= 0:
        return None
    spot = float(spot)

    atm = atm_implied_volatility(calls + puts, spot)
    if atm is None:
        return None
    reference = calls[0] if calls else puts[0]
    days = int(reference.get("days_till_expiration") or 0)
    move = expected_move(spot, atm, days)
    return ExpiryVolatility(
        expiration=str(chain.get("expiration") or reference.get("expiration") or ""),
        days_to_expiry=days,
        atm_iv=float(atm),
        expected_move=move,
        expected_move_pct=(move / spot) if spot else 0.0,
        put_skew=delta_skew(calls, puts),
    )


def options_insight(snapshot: OptionsSnapshot) -> str:
    """One decision-relevant sentence about what the option market is pricing."""
    front = snapshot.front
    if front is None:
        return ""
    parts = [
        f"Options price {front.atm_iv:.1f}% implied volatility into {front.expiration} "
        f"({front.days_to_expiry} days), an expected move of about "
        f"±${front.expected_move:,.2f} ({front.expected_move_pct:.1%})."
    ]
    if front.put_skew is not None:
        if front.put_skew > 1.5:
            parts.append(
                f"Puts trade {front.put_skew:.1f} IV points over equivalent calls, so the market is "
                "paying up for downside protection."
            )
        elif front.put_skew < -1.5:
            parts.append(
                f"Calls trade {abs(front.put_skew):.1f} IV points over equivalent puts, an unusual "
                "skew that leans toward upside speculation."
            )
        else:
            parts.append("Put and call volatility are close to balanced, showing no strong directional bid.")
    if len(snapshot.expiries) > 1:
        later = snapshot.expiries[-1]
        difference = later.atm_iv - front.atm_iv
        shape = "rising with time" if difference > 0.5 else ("inverted" if difference < -0.5 else "flat")
        parts.append(
            f"The term structure is {shape} ({front.atm_iv:.1f}% at {front.days_to_expiry}d "
            f"versus {later.atm_iv:.1f}% at {later.days_to_expiry}d)."
        )
    return " ".join(parts)
