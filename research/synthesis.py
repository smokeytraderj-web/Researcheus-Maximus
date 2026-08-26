"""Provider-neutral structured fundamental, sentiment, and lead synthesis."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from core.models import Horizon, Rating, SourceRecord, SpecialistFinding


RATINGS = [item.value for item in Rating]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fundamental_rating", "fundamental_summary", "fundamental_signals", "sentiment", "risks", "catalysts", "change_conditions", "sources"],
    "properties": {
        "fundamental_rating": {"type": "string", "enum": RATINGS},
        "fundamental_summary": {"type": "string"},
        "fundamental_signals": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 6},
        "sentiment": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 6},
        "catalysts": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
        "change_conditions": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 5},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "url", "supports"],
                "properties": {"name": {"type": "string"}, "url": {"type": "string"}, "supports": {"type": "string"}},
            },
            "maxItems": 12,
        },
    },
}


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    fundamental: SpecialistFinding
    sentiment: str
    risks: tuple[str, ...]
    catalysts: tuple[str, ...]
    change_conditions: tuple[str, ...]
    sources: tuple[SourceRecord, ...]
    provider_label: str
    limitations: tuple[str, ...]


def _prompt(company: str, ticker: str, horizon: Horizon, market: dict, news: list[dict]) -> str:
    return f"""Act as a rigorous fundamental equity analyst and sentiment researcher for Gottfried & Somberg Wealth Management.
Research {company} ({ticker}) for a {horizon.value} decision. Separate reported facts, consensus estimates, commentary, and social sentiment. Prioritize SEC/company investor relations, then reputable financial sources. For social sentiment, examine public X, Reddit, and Stocktwits when accessible; treat it as noisy supporting evidence and ignore promotion or repetition. Never invent missing values. Use current sources and return only the required JSON.

Deterministic market/fundamental snapshot from the application:
{json.dumps(market, default=str, indent=2)[:18000]}

Recent provider news metadata:
{json.dumps(news, default=str, indent=2)[:10000]}
"""


def _normalize(payload: dict, provider_label: str, retrieved_at: str, limitations=()) -> SynthesisResult:
    rating = Rating(payload["fundamental_rating"])
    sources = []
    for item in payload.get("sources", []):
        url = str(item.get("url", "")).strip()
        if url.startswith(("https://", "http://")):
            sources.append(SourceRecord(str(item.get("name", "Source")), url, retrieved_at, str(item.get("supports", "Research evidence"))))
    return SynthesisResult(
        SpecialistFinding(rating, str(payload["fundamental_summary"]), tuple(map(str, payload["fundamental_signals"]))),
        str(payload["sentiment"]), tuple(map(str, payload["risks"])), tuple(map(str, payload["catalysts"])), tuple(map(str, payload["change_conditions"])), tuple(sources), provider_label, tuple(limitations)
    )


def openai_synthesize(company: str, ticker: str, horizon: Horizon, market: dict, news: list[dict], retrieved_at: str, api_key: str = "", model: str = "") -> SynthesisResult:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("OpenAI support is not installed. Re-run pip install -r requirements.txt.") from exc
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OpenAI API key is not configured.")
    selected = model or os.getenv("RESEARCHEUS_OPENAI_MODEL", "gpt-5.6")
    response = OpenAI(api_key=key).responses.create(
        model=selected,
        input=_prompt(company, ticker, horizon, market, news),
        tools=[{"type": "web_search"}],
        text={"format": {"type": "json_schema", "name": "stock_research", "strict": True, "schema": SCHEMA}},
        store=False,
    )
    payload = json.loads(response.output_text)
    return _normalize(payload, f"OpenAI {selected} with web search", retrieved_at)


def ollama_synthesize(company: str, ticker: str, horizon: Horizon, market: dict, news: list[dict], retrieved_at: str, model: str = "") -> SynthesisResult:
    selected = model or os.getenv("RESEARCHEUS_OLLAMA_MODEL", "gpt-oss:20b")
    base = os.getenv("RESEARCHEUS_OLLAMA_URL", "http://localhost:11434").rstrip("/")
    body = json.dumps({
        "model": selected,
        "messages": [{"role": "user", "content": _prompt(company, ticker, horizon, market, news) + "\nSchema:\n" + json.dumps(SCHEMA)}],
        "format": SCHEMA,
        "stream": False,
        "think": "medium",
    }).encode("utf-8")
    request = urllib.request.Request(base + "/api/chat", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Ollama is unavailable. Start Ollama and confirm the configured model is installed.") from exc
    content = data.get("message", {}).get("content", "")
    return _normalize(json.loads(content), f"Local Ollama {selected}", retrieved_at, ("Local Ollama synthesis does not perform independent web search; it uses the retrieved market and news evidence supplied by the app.",))


def deterministic_synthesis(info: dict, news: list[dict], retrieved_at: str) -> SynthesisResult:
    growth = info.get("revenueGrowth")
    earnings_growth = info.get("earningsGrowth")
    forward_pe = info.get("forwardPE")
    debt_equity = info.get("debtToEquity")
    score = 0
    if isinstance(growth, (int, float)):
        score += 2 if growth > 0.15 else 1 if growth > 0 else -1
    if isinstance(earnings_growth, (int, float)):
        score += 2 if earnings_growth > 0.15 else 1 if earnings_growth > 0 else -1
    if isinstance(forward_pe, (int, float)):
        score += 1 if 0 < forward_pe < 25 else -1 if forward_pe > 45 else 0
    if isinstance(debt_equity, (int, float)) and debt_equity > 200:
        score -= 1
    rating = Rating.BUY if score >= 4 else Rating.ADD if score >= 2 else Rating.HOLD if score >= 0 else Rating.REDUCE
    def show(value, percent=False):
        if not isinstance(value, (int, float)):
            return "unavailable"
        return f"{value:.1%}" if percent else f"{value:.1f}"
    signals = (
        f"Reported/provider revenue growth: {show(growth, True)}.",
        f"Reported/provider earnings growth: {show(earnings_growth, True)}.",
        f"Forward P/E: {show(forward_pe)}; debt/equity: {show(debt_equity)}.",
        f"{len(news)} recent news items were available from the market-data provider.",
    )
    return SynthesisResult(
        SpecialistFinding(rating, "A deterministic fundamental screen was completed from available provider fields; deeper narrative synthesis requires OpenAI or Ollama.", signals),
        "Sentiment was not scored because no configured language provider completed narrative analysis.",
        ("Provider fundamentals may be incomplete or use differing fiscal definitions.", "Current filings and social narratives were not independently synthesized."),
        ("Review the latest earnings release and company guidance.",),
        ("Material earnings revisions or guidance changes.", "A break in the prevailing technical structure."),
        (), "Deterministic fallback", ("No AI research provider was available; fundamental and sentiment coverage is reduced.",)
    )

