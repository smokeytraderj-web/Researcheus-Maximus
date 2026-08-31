"""Optional supplemental technical evidence from the TV Remix MCP server.

This is additive, never a replacement for the deterministic Yahoo-based
technical analysis in ``research/technical.py``. If TV Remix is not
configured, unreachable, or returns nothing usable, callers get an evidence
object with ``.error`` set and no values -- nothing here is ever guessed or
invented to fill a gap.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from dataclasses import dataclass, field

from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from core.models import SourceRecord, TVGaugeReading, TVLevel, TVTechnicalReport
from research.options import ExpiryVolatility, OptionsSnapshot, build_expiry_volatility

_SERVER_URL = "https://tvremix.xyz/api/mcp/v1"
_ENV_VAR = "TVREMIX_API_KEY"
_TIMEOUT_SECONDS = 20.0
_GAUGE_TIMEFRAMES = ("1D", "4h", "1h")


@dataclass(frozen=True, slots=True)
class TVRemixEvidence:
    resolved_symbol: str = ""
    metrics: tuple[tuple[str, str], ...] = ()
    signals: tuple[str, ...] = ()
    error: str = ""

    @property
    def available(self) -> bool:
        return not self.error and bool(self.metrics or self.signals)


def tvremix_api_key() -> str:
    """Read the TV Remix API key from the environment only; never store or log it."""
    return os.environ.get(_ENV_VAR, "").strip()


def _tool_result_json(result: types.CallToolResult) -> dict | None:
    if result.is_error:
        return None
    if isinstance(result.structured_content, dict):
        return result.structured_content
    for block in result.content:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


async def _resolve_symbol(session: ClientSession, query: str) -> tuple[str, str]:
    """Resolve a ticker/company query to (EXCHANGE:TICKER, company description)."""
    search = await session.call_tool("search_symbols", {"query": query})
    search_data = _tool_result_json(search) or {}
    candidates = (search_data.get("data") or {}).get("symbols") or search_data.get("symbols") or []
    if candidates and isinstance(candidates, list):
        # Prefer a plain "stock" listing over depositary receipts, ETPs, etc.
        stock_first = [c for c in candidates if isinstance(c, dict) and c.get("type") == "stock"]
        first = (stock_first or candidates)[0]
        if isinstance(first, dict):
            return str(first.get("symbol") or ""), str(first.get("description") or "")
    return "", ""


async def _fetch(symbol: str, api_key: str) -> TVRemixEvidence:
    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {api_key}"})
    async with streamable_http_client(_SERVER_URL, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            resolved, _company = await _resolve_symbol(session, symbol)
            if not resolved:
                return TVRemixEvidence(error=f"TV Remix could not resolve a symbol for '{symbol}'.")

            swing = await session.call_tool("analyze_swing_tool", {"symbol": resolved})
            swing_data = _tool_result_json(swing)
            if swing_data is None:
                return TVRemixEvidence(resolved_symbol=resolved, error="TV Remix swing analysis was unavailable or returned no usable data.")

            metrics: list[tuple[str, str]] = []
            signals: list[str] = []
            trend = swing_data.get("trend") or {}
            direction = trend.get("direction")
            strength = trend.get("strength")
            if direction:
                label = direction.capitalize() + (f" ({strength})" if strength else "")
                metrics.append(("TV Remix swing trend", label))
            fibonacci = swing_data.get("fibonacci") or {}
            swing_high = fibonacci.get("swing_high")
            swing_low = fibonacci.get("swing_low")
            if swing_high is not None and swing_low is not None:
                metrics.append(("TV Remix swing range", f"${swing_low:,.2f} - ${swing_high:,.2f}"))
            swing_points = swing_data.get("swing_points") or []
            if swing_points and isinstance(swing_points, list):
                latest = swing_points[-1]
                point_type = str(latest.get("type") or "").capitalize()
                point_label = latest.get("label") or ""
                point_price = latest.get("price")
                point_time = str(latest.get("time") or "")[:10]
                if point_type and point_price is not None:
                    signals.append(
                        f"TV Remix swing structure: most recent swing is a {point_type.lower()}"
                        f"{f' ({point_label})' if point_label else ''} at ${point_price:,.2f}"
                        f"{f' on {point_time}' if point_time else ''}."
                    )
            if direction and swing_points:
                signals.append(
                    f"TV Remix trend read: {direction} with {trend.get('swings_aligned', 'several')} aligned swings over "
                    f"{swing_data.get('bars_analyzed', 'the analyzed')} bars."
                )

            try:
                rating_result = await session.call_tool("get_technicals_rating", {"symbol": resolved})
                rating_data = _tool_result_json(rating_result)
            except Exception:  # noqa: BLE001 - one failing supplemental call must not drop the rest
                rating_data = None
            if rating_data:
                summary = (rating_data.get("data") or {}).get("summary") or {}
                recommendation = summary.get("recommendation")
                value = summary.get("value")
                if recommendation:
                    label = str(recommendation) + (f" ({value:.2f})" if isinstance(value, (int, float)) else "")
                    metrics.append(("TV Remix aggregate rating", label))
                    signals.append(f"TV Remix aggregate technical rating: {recommendation}, blending oscillator and moving-average scores.")

            try:
                smc_result = await session.call_tool("analyze_smc_tool", {"symbol": resolved})
                smc_data = _tool_result_json(smc_result)
            except Exception:  # noqa: BLE001 - one failing supplemental call must not drop the rest
                smc_data = None
            if smc_data:
                bias = smc_data.get("bias") or {}
                bias_direction = bias.get("direction")
                bias_confidence = bias.get("confidence")
                bias_reasoning = bias.get("reasoning")
                if bias_direction:
                    label = str(bias_direction).capitalize() + (f" ({bias_confidence} confidence)" if bias_confidence else "")
                    metrics.append(("TV Remix smart-money bias", label))
                if bias_reasoning:
                    signals.append(f"TV Remix smart-money structure: {bias_reasoning}")
                premium_discount = smc_data.get("premium_discount") or {}
                zone = premium_discount.get("zone")
                equilibrium = premium_discount.get("equilibrium")
                swing_high_pd = premium_discount.get("swing_high")
                if zone and equilibrium is not None and swing_high_pd is not None:
                    signals.append(
                        f"TV Remix zone read: price is trading in the {str(zone).replace('_', ' ')}, "
                        f"between equilibrium ${equilibrium:,.2f} and swing high ${swing_high_pd:,.2f}."
                    )
                order_blocks = smc_data.get("order_blocks") or []
                untested_bullish = [
                    ob for ob in order_blocks
                    if isinstance(ob, dict) and ob.get("bias") == "bullish" and not ob.get("mitigated")
                ]
                if untested_bullish:
                    nearest = max(untested_bullish, key=lambda ob: ob.get("high", 0))
                    low, high = nearest.get("low"), nearest.get("high")
                    if low is not None and high is not None:
                        signals.append(f"TV Remix nearest untested bullish order block: ${low:,.2f}-${high:,.2f}.")

            try:
                mtf_result = await session.call_tool("analyze_multi_timeframe", {"symbol": resolved})
                mtf_data = _tool_result_json(mtf_result)
            except Exception:  # noqa: BLE001 - one failing supplemental call must not drop the rest
                mtf_data = None
            if mtf_data:
                confluence = (mtf_data.get("data") or {}).get("confluence") or {}
                alignment = confluence.get("alignment")
                if alignment:
                    metrics.append(("TV Remix multi-timeframe alignment", str(alignment).replace("_", " ").title()))
                    signals.append(
                        f"TV Remix multi-timeframe read: {confluence.get('bullish_count', 0)} bullish / "
                        f"{confluence.get('bearish_count', 0)} bearish / {confluence.get('neutral_count', 0)} neutral "
                        f"across {confluence.get('timeframes_analyzed', 'the analyzed')} timeframes ({str(alignment).replace('_', ' ')})."
                    )

            return TVRemixEvidence(resolved_symbol=resolved, metrics=tuple(metrics), signals=tuple(signals))


def fetch_tvremix_evidence(symbol: str, api_key: str = "", *, timeout: float = _TIMEOUT_SECONDS) -> TVRemixEvidence:
    """Synchronous entry point: safe to call from a worker thread's blocking context.

    ``api_key`` (typically pasted into Research Settings) takes priority; falls
    back to the ``TVREMIX_API_KEY`` environment variable, same pattern as the
    OpenAI key. Returns an evidence object with ``.error`` set (never raises)
    when TV Remix is not configured, unreachable, or fails -- so a missing or
    broken integration degrades to "no supplemental evidence" rather than
    breaking a research run.
    """
    api_key = api_key.strip() or tvremix_api_key()
    if not api_key:
        return TVRemixEvidence(error="TV Remix is not configured (TVREMIX_API_KEY is not set).")
    try:
        return asyncio.run(asyncio.wait_for(_fetch(symbol, api_key), timeout=timeout))
    except asyncio.TimeoutError:
        return TVRemixEvidence(error="TV Remix request timed out.")
    except Exception as exc:  # noqa: BLE001 - never let an optional supplemental source break research
        return TVRemixEvidence(error=f"TV Remix request failed: {exc}")


# --- Options-implied evidence for Deep Technical Analysis. ---

# Near-dated, roughly monthly, and further out: enough to show a term structure
# without pulling the whole board.
_OPTION_EXPIRY_TARGET_DAYS = (14, 45, 100)


async def _fetch_options(query: str, api_key: str) -> OptionsSnapshot:
    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {api_key}"})
    async with streamable_http_client(_SERVER_URL, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resolved, _name = await _resolve_symbol(session, query)
            if not resolved:
                return OptionsSnapshot(query, 0.0, (), (), (), (), "", f"Could not resolve '{query}'.")

            listing = _tool_result_json(
                await session.call_tool("get_option_expirations", {"underlying_symbol": resolved})
            )
            rows = ((listing or {}).get("data") or {}).get("expirations") or []
            dates = [str(row.get("expiration")) for row in rows if isinstance(row, dict) and row.get("expiration")]
            if not dates:
                return OptionsSnapshot(resolved, 0.0, (), (), (), (), "", "No listed options were available.")

            today = dt.date.today()
            chosen: list[str] = []
            for target in _OPTION_EXPIRY_TARGET_DAYS:
                best, best_gap = "", 10**6
                for value in dates:
                    if value in chosen:
                        continue
                    try:
                        days = (dt.date.fromisoformat(value) - today).days
                    except ValueError:
                        continue
                    if days < 5:
                        continue
                    if abs(days - target) < best_gap:
                        best, best_gap = value, abs(days - target)
                if best:
                    chosen.append(best)
            if not chosen:
                return OptionsSnapshot(resolved, 0.0, (), (), (), (), "", "No usable option expirations were available.")

            expiries: list[ExpiryVolatility] = []
            spot = 0.0
            smile_strikes: tuple[float, ...] = ()
            smile_calls: tuple[float, ...] = ()
            smile_puts: tuple[float, ...] = ()
            smile_expiration = ""
            for expiration in chosen:
                try:
                    payload = _tool_result_json(
                        await session.call_tool(
                            "get_option_chain", {"symbol": resolved, "expiration": expiration}
                        )
                    )
                except Exception:  # noqa: BLE001 - one bad expiry must not drop the rest
                    continue
                chain = (payload or {}).get("data") or {}
                summary = build_expiry_volatility(chain)
                if summary is None:
                    continue
                expiries.append(summary)
                spot = float(chain.get("underlying_price") or spot)
                if not smile_strikes:
                    # The volatility smile is drawn from the front expiry, which quotes
                    # the widest strike range.
                    calls = {c["strike"]: c["iv"] for c in chain.get("calls") or [] if c.get("iv") is not None}
                    puts = {p["strike"]: p["iv"] for p in chain.get("puts") or [] if p.get("iv") is not None}
                    shared = sorted(set(calls) & set(puts))
                    if shared:
                        smile_strikes = tuple(float(strike) for strike in shared)
                        smile_calls = tuple(float(calls[strike]) for strike in shared)
                        smile_puts = tuple(float(puts[strike]) for strike in shared)
                        smile_expiration = summary.expiration

            if not expiries:
                return OptionsSnapshot(resolved, 0.0, (), (), (), (), "", "Option chains returned no usable volatility.")
            return OptionsSnapshot(
                symbol=resolved,
                spot=spot,
                expiries=tuple(expiries),
                smile_strikes=smile_strikes,
                smile_call_iv=smile_calls,
                smile_put_iv=smile_puts,
                smile_expiration=smile_expiration,
            )


def fetch_options_snapshot(query: str, api_key: str = "", *, timeout: float = _TIMEOUT_SECONDS) -> OptionsSnapshot:
    """Options-implied volatility evidence; never raises, sets ``.error`` instead."""
    api_key = api_key.strip() or tvremix_api_key()
    if not api_key:
        return OptionsSnapshot(query, 0.0, (), (), (), (), "", "TV Remix is not configured.")
    try:
        return asyncio.run(asyncio.wait_for(_fetch_options(query, api_key), timeout=timeout))
    except asyncio.TimeoutError:
        return OptionsSnapshot(query, 0.0, (), (), (), (), "", "Options request timed out.")
    except Exception as exc:  # noqa: BLE001 - optional evidence must never break research
        return OptionsSnapshot(query, 0.0, (), (), (), (), "", f"Options request failed: {exc}")


async def _fetch_earnings_history(query: str, api_key: str) -> dict:
    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {api_key}"})
    async with streamable_http_client(_SERVER_URL, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resolved, _name = await _resolve_symbol(session, query)
            if not resolved:
                return {}
            payload = _tool_result_json(
                await session.call_tool("get_earnings_history", {"symbol": resolved})
            )
            return ((payload or {}).get("data") or {}) if payload else {}


def fetch_earnings_history(query: str, api_key: str = "", *, timeout: float = _TIMEOUT_SECONDS) -> dict:
    """Raw earnings-history payload, or an empty mapping; never raises."""
    api_key = api_key.strip() or tvremix_api_key()
    if not api_key:
        return {}
    try:
        return asyncio.run(asyncio.wait_for(_fetch_earnings_history(query, api_key), timeout=timeout))
    except Exception:  # noqa: BLE001 - optional evidence must never break research
        return {}


# --- Standalone "Technical Analysis" feature: TV Remix only, no Yahoo/fundamentals. ---


def tag_rsi(value: float | None) -> str:
    """Classify an RSI(14) reading using TradingView's published oscillator rule."""
    if value is None:
        return ""
    if value > 70:
        return "Sell"
    if value < 30:
        return "Buy"
    return "Neutral"


def tag_macd(macd: float | None, signal: float | None) -> str:
    """Classify a MACD line using TradingView's published rule: above signal = Buy."""
    if macd is None or signal is None:
        return ""
    return "Buy" if macd > signal else "Sell"


def tag_sma(price: float | None, average: float | None) -> str:
    """Classify a moving average using TradingView's published rule: price above average = Buy."""
    if price is None or average is None:
        return ""
    return "Buy" if price > average else "Sell"


def _fib_levels(swing_high: float, swing_low: float) -> tuple[tuple[str, float], ...]:
    span = swing_high - swing_low
    return (
        ("Fib 100% (swing high)", swing_high),
        ("Fib 78.6%", swing_high - span * 0.214),
        ("Fib 61.8%", swing_high - span * 0.382),
        ("Fib 50%", swing_high - span * 0.5),
        ("Fib 38.2%", swing_high - span * 0.618),
        ("Fib 23.6%", swing_high - span * 0.764),
        ("Fib 0% (swing low)", swing_low),
    )


def _build_levels(swing_high: float, swing_low: float, current_price: float) -> tuple[TVLevel, ...]:
    levels = [
        TVLevel(label=label, price=price, pct_from_now=(price / current_price - 1) if current_price else 0.0)
        for label, price in _fib_levels(swing_high, swing_low)
    ]
    levels.append(TVLevel(label="Now", price=current_price, pct_from_now=0.0))
    levels.sort(key=lambda lvl: lvl.price, reverse=True)
    return tuple(levels)


def _empty_technical_report(query: str, resolved: str, company_name: str, now: str, error: str) -> TVTechnicalReport:
    return TVTechnicalReport(
        query=query,
        resolved_symbol=resolved,
        company_name=company_name,
        current_price=0.0,
        change_pct=0.0,
        as_of=now,
        gauges=(),
        confluence_label="",
        levels=(),
        summary_bullets=(),
        headline="",
        chart_read="",
        market_cap=None,
        volume=None,
        beta=None,
        period_returns=(),
        analyst_rating="",
        analyst_score=None,
        price_target_low=None,
        price_target_avg=None,
        price_target_high=None,
        price_chart_path="",
        sparkline_path="",
        sources=(),
        error=error,
    )


async def _fetch_technical_report(query: str, api_key: str) -> tuple[TVTechnicalReport, list[dict]]:
    now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="minutes")
    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {api_key}"})
    async with streamable_http_client(_SERVER_URL, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            resolved, company_name = await _resolve_symbol(session, query)
            if not resolved:
                return _empty_technical_report(query, "", "", now, f"TV Remix could not resolve a symbol for '{query}'."), []

            mtf_result = await session.call_tool(
                "analyze_multi_timeframe", {"symbol": resolved, "timeframes": list(_GAUGE_TIMEFRAMES)}
            )
            mtf_data = _tool_result_json(mtf_result)
            if not mtf_data or not mtf_data.get("data"):
                return (
                    _empty_technical_report(
                        query, resolved, company_name, now,
                        "TV Remix multi-timeframe analysis was unavailable or returned no usable data.",
                    ),
                    [],
                )

            data = mtf_data["data"]
            price_block = data.get("price") or {}
            current_price = float(price_block.get("price") or 0.0)
            change_pct = float(price_block.get("change") or 0.0)
            timeframes = data.get("timeframes") or {}
            confluence = data.get("confluence") or {}
            confluence_label = str(confluence.get("alignment") or "").replace("_", " ").title()

            gauges: list[TVGaugeReading] = []
            for timeframe in _GAUGE_TIMEFRAMES:
                tf_data = timeframes.get(timeframe)
                if not isinstance(tf_data, dict):
                    continue
                rating = tf_data.get("rating") or {}
                osc = tf_data.get("oscillators") or {}
                mas = tf_data.get("moving_averages") or {}
                rsi = osc.get("rsi")
                macd = osc.get("macd")
                macd_signal = osc.get("macd_signal")
                sma50 = mas.get("sma50")
                sma200 = mas.get("sma200")
                indicators: list[tuple[str, str, str]] = []
                if isinstance(rsi, (int, float)):
                    indicators.append(("RSI (14)", f"{rsi:.2f}", tag_rsi(rsi)))
                if isinstance(macd, (int, float)) and isinstance(macd_signal, (int, float)):
                    indicators.append(("MACD Level (12,26)", f"{macd:.2f}", tag_macd(macd, macd_signal)))
                if isinstance(sma50, (int, float)):
                    indicators.append(("SMA (50)", f"{sma50:.2f}", tag_sma(current_price, sma50)))
                if isinstance(sma200, (int, float)):
                    indicators.append(("SMA (200)", f"{sma200:.2f}", tag_sma(current_price, sma200)))
                rating_value = rating.get("value")
                gauges.append(
                    TVGaugeReading(
                        timeframe=timeframe,
                        rating_label=str(rating.get("summary") or ""),
                        rating_value=float(rating_value) if isinstance(rating_value, (int, float)) else 0.0,
                        oscillators_label=str(rating.get("oscillators") or ""),
                        moving_averages_label=str(rating.get("moving_averages") or ""),
                        indicators=tuple(indicators),
                    )
                )

            primary_timeframe_data = timeframes.get("1D") or {}
            primary_osc = primary_timeframe_data.get("oscillators") or {}
            adx = primary_osc.get("adx")
            rsi_1d = primary_osc.get("rsi")

            try:
                smc_result = await session.call_tool("analyze_smc_tool", {"symbol": resolved})
                smc_data = _tool_result_json(smc_result) or {}
            except Exception:  # noqa: BLE001 - one failing supplemental call must not drop the rest
                smc_data = {}
            bias = smc_data.get("bias") or {}
            premium_discount = smc_data.get("premium_discount") or {}

            try:
                swing_result = await session.call_tool("analyze_swing_tool", {"symbol": resolved})
                swing_data = _tool_result_json(swing_result) or {}
            except Exception:  # noqa: BLE001 - one failing supplemental call must not drop the rest
                swing_data = {}
            fibonacci = swing_data.get("fibonacci") or {}
            swing_high = fibonacci.get("swing_high")
            swing_low = fibonacci.get("swing_low")
            trend_direction = str((swing_data.get("trend") or {}).get("direction") or "")

            levels: tuple[TVLevel, ...] = ()
            if isinstance(swing_high, (int, float)) and isinstance(swing_low, (int, float)) and swing_high > swing_low:
                levels = _build_levels(float(swing_high), float(swing_low), current_price)

            resistances = sorted((lvl for lvl in levels if lvl.price > current_price), key=lambda lvl: lvl.price)
            supports = sorted((lvl for lvl in levels if lvl.price < current_price), key=lambda lvl: lvl.price, reverse=True)
            nearest_resistance = resistances[0] if resistances else None
            next_resistance = resistances[1] if len(resistances) > 1 else None
            nearest_support = supports[0] if supports else None

            try:
                sym_result = await session.call_tool(
                    "get_symbol_data",
                    {
                        "symbol": resolved,
                        "columns": ["beta_1_year", "market_cap_basic", "volume", "Perf.5D", "Perf.1M", "Perf.6M", "Perf.YTD", "Perf.Y"],
                    },
                )
                sym_data = (_tool_result_json(sym_result) or {}).get("data") or {}
            except Exception:  # noqa: BLE001 - one failing supplemental call must not drop the rest
                sym_data = {}
            beta = sym_data.get("beta_1_year")
            market_cap = sym_data.get("market_cap_basic")
            volume = sym_data.get("volume")
            period_returns = tuple(
                (label, float(sym_data[key]))
                for label, key in (("5D", "Perf.5D"), ("1M", "Perf.1M"), ("6M", "Perf.6M"), ("YTD", "Perf.YTD"), ("1Y", "Perf.Y"))
                if isinstance(sym_data.get(key), (int, float))
            )

            try:
                forecast_result = await session.call_tool("get_forecasts", {"symbol": resolved})
                forecast_data = (_tool_result_json(forecast_result) or {}).get("data") or {}
            except Exception:  # noqa: BLE001 - one failing supplemental call must not drop the rest
                forecast_data = {}
            analyst = forecast_data.get("analyst_rating") or {}
            targets = forecast_data.get("price_targets") or {}
            analyst_rating = str(analyst.get("recommendation") or "")
            analyst_score = analyst.get("score") if isinstance(analyst.get("score"), (int, float)) else None
            price_target_low = targets.get("low") if isinstance(targets.get("low"), (int, float)) else None
            price_target_avg = targets.get("average") if isinstance(targets.get("average"), (int, float)) else None
            price_target_high = targets.get("high") if isinstance(targets.get("high"), (int, float)) else None

            try:
                earnings_result = await session.call_tool("get_earnings_calendar", {"symbols": [resolved], "limit": 1})
                earnings_rows = ((_tool_result_json(earnings_result) or {}).get("data") or {}).get("earnings") or []
            except Exception:  # noqa: BLE001 - one failing supplemental call must not drop the rest
                earnings_rows = []
            next_earnings = ""
            if earnings_rows and isinstance(earnings_rows, list) and isinstance(earnings_rows[0], dict):
                next_earnings = str(earnings_rows[0].get("next_earnings_date") or "")

            try:
                ohlcv_result = await session.call_tool("get_ohlcv", {"symbol": resolved, "interval": "1D", "count": 260})
                bars = (_tool_result_json(ohlcv_result) or {}).get("bars") or []
            except Exception:  # noqa: BLE001 - one failing supplemental call must not drop the rest
                bars = []

            primary_gauge = next((g for g in gauges if g.timeframe == "1D"), None)
            bullets: list[tuple[str, str]] = []
            if primary_gauge:
                bullets.append(
                    (
                        "Read",
                        f"{primary_gauge.rating_label or 'Neutral'} on the 1D read ({primary_gauge.rating_value:.2f}); "
                        f"oscillators {primary_gauge.oscillators_label.lower() or 'unavailable'}, "
                        f"moving averages {primary_gauge.moving_averages_label.lower() or 'unavailable'}. "
                        f"Multi-timeframe alignment: {confluence_label.lower() or 'unavailable'}.",
                    )
                )
            if nearest_support and nearest_resistance:
                bullets.append(
                    (
                        "Levels",
                        f"Price ${current_price:,.2f} sits between support {nearest_support.label} at ${nearest_support.price:,.2f} "
                        f"({nearest_support.pct_from_now:+.1%}) and resistance {nearest_resistance.label} at ${nearest_resistance.price:,.2f} "
                        f"({nearest_resistance.pct_from_now:+.1%}).",
                    )
                )
            zone = premium_discount.get("zone")
            if zone:
                bullets.append(
                    (
                        "Zone",
                        f"Price is trading in the {str(zone).replace('_', ' ')} of the recent swing range, per smart-money structure "
                        f"(bias: {bias.get('direction') or 'unavailable'}, {bias.get('confidence') or 'unrated'} confidence).",
                    )
                )
            if isinstance(adx, (int, float)):
                regime = "a trending regime" if adx >= 25 else "a choppy, range-bound regime"
                bullets.append(
                    (
                        "Risk",
                        f"Trend strength (ADX) is {adx:.1f}, indicating {regime}; size conviction on directional signals accordingly.",
                    )
                )
            catalyst_parts: list[str] = []
            if next_earnings:
                try:
                    days_out = (dt.date.fromisoformat(next_earnings) - dt.date.today()).days
                    catalyst_parts.append(f"Next earnings report: {next_earnings} (in {days_out}d).")
                except ValueError:
                    catalyst_parts.append(f"Next earnings report: {next_earnings}.")
            if nearest_resistance and next_resistance:
                catalyst_parts.append(f"A close above ${nearest_resistance.price:,.2f} would open ${next_resistance.price:,.2f}.")
            if catalyst_parts:
                bullets.append(("Catalyst", " ".join(catalyst_parts)))

            headline = (
                f"{resolved.split(':')[-1]}: {primary_gauge.rating_label if primary_gauge else 'Mixed'} technical read, "
                f"{confluence_label.lower() or 'mixed signal'} across timeframes."
            )

            chart_read = ""
            if bars:
                chart_read = (
                    f"The daily chart shows a {trend_direction or 'developing'} structure over the analyzed window, "
                    f"with the last close at ${current_price:,.2f}."
                )
                if isinstance(rsi_1d, (int, float)):
                    chart_read += f" RSI is at {rsi_1d:.1f} ({(tag_rsi(rsi_1d) or 'unrated').lower()})."
                if isinstance(adx, (int, float)):
                    chart_read += f" ADX at {adx:.1f} suggests {'a trending' if adx >= 25 else 'a choppy'} regime."
                if nearest_resistance:
                    chart_read += f" Price is testing {nearest_resistance.label} at ${nearest_resistance.price:,.2f}."
                    if next_resistance:
                        chart_read += f" A break above would open {next_resistance.label} at ${next_resistance.price:,.2f}."

            sources = (
                SourceRecord(
                    "TV Remix",
                    f"https://www.tradingview.com/symbols/{resolved.replace(':', '-')}/",
                    now,
                    "Technical rating, market structure and price history",
                ),
            )

            report = TVTechnicalReport(
                query=query,
                resolved_symbol=resolved,
                company_name=company_name or resolved,
                current_price=current_price,
                change_pct=change_pct,
                as_of=now,
                gauges=tuple(gauges),
                confluence_label=confluence_label,
                levels=levels,
                summary_bullets=tuple(bullets),
                headline=headline,
                chart_read=chart_read,
                market_cap=float(market_cap) if isinstance(market_cap, (int, float)) else None,
                volume=float(volume) if isinstance(volume, (int, float)) else None,
                beta=float(beta) if isinstance(beta, (int, float)) else None,
                period_returns=period_returns,
                analyst_rating=analyst_rating,
                analyst_score=float(analyst_score) if analyst_score is not None else None,
                price_target_low=float(price_target_low) if price_target_low is not None else None,
                price_target_avg=float(price_target_avg) if price_target_avg is not None else None,
                price_target_high=float(price_target_high) if price_target_high is not None else None,
                price_chart_path="",
                sparkline_path="",
                sources=sources,
            )
            return report, bars


def fetch_tvremix_technical_report(
    query: str, api_key: str = "", *, timeout: float = _TIMEOUT_SECONDS
) -> tuple[TVTechnicalReport, list[dict]]:
    """Synchronous entry point for the standalone Technical Analysis feature.

    Returns ``(report, bars)`` -- ``bars`` are the raw OHLCV rows the caller
    uses to render the price chart and sparkline (rendering needs a
    destination path, which this module doesn't own). Never raises; a
    misconfigured or unreachable TV Remix instead yields a report with
    ``.error`` set.
    """
    api_key = api_key.strip() or tvremix_api_key()
    if not api_key:
        now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="minutes")
        return _empty_technical_report(query, "", "", now, "TV Remix is not configured (add an API key in Settings)."), []
    try:
        return asyncio.run(asyncio.wait_for(_fetch_technical_report(query, api_key), timeout=timeout))
    except asyncio.TimeoutError:
        now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="minutes")
        return _empty_technical_report(query, "", "", now, "TV Remix request timed out."), []
    except Exception as exc:  # noqa: BLE001 - never let this feature crash the app
        now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="minutes")
        return _empty_technical_report(query, "", "", now, f"TV Remix request failed: {exc}"), []
