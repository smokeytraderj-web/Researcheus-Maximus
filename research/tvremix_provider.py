"""Optional supplemental technical evidence from the TV Remix MCP server.

This is additive, never a replacement for the deterministic Yahoo-based
technical analysis in ``research/technical.py``. If TV Remix is not
configured, unreachable, or returns nothing usable, callers get an evidence
object with ``.error`` set and no values -- nothing here is ever guessed or
invented to fill a gap.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

_SERVER_URL = "https://tvremix.xyz/api/mcp/v1"
_ENV_VAR = "TVREMIX_API_KEY"
_TIMEOUT_SECONDS = 20.0


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


async def _fetch(symbol: str, api_key: str) -> TVRemixEvidence:
    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {api_key}"})
    async with streamable_http_client(_SERVER_URL, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            search = await session.call_tool("search_symbols", {"query": symbol})
            search_data = _tool_result_json(search) or {}
            candidates = (search_data.get("data") or {}).get("symbols") or search_data.get("symbols") or []
            resolved = ""
            if candidates and isinstance(candidates, list):
                # Prefer a plain "stock" listing over depositary receipts, ETPs, etc.
                stock_first = [c for c in candidates if isinstance(c, dict) and c.get("type") == "stock"]
                first = (stock_first or candidates)[0]
                resolved = str(first.get("symbol") or "") if isinstance(first, dict) else ""
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
