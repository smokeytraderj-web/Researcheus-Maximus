"""Build the interactive, client-facing Researcheus research report.

The HTML reports are the primary client experience.  They use the approved
editorial templates in ``resources`` as their visual contract, while every
value, sentence, source, and chart is bound from a validated ResearchResult.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

from core.assessments import fundamental_outlook, technical_setup
from core.models import ChartRecord, Rating, ResearchRequest, ResearchResult


_ROOT = Path(__file__).resolve().parents[1]
_RESOURCES = _ROOT / "resources"


@dataclass(frozen=True, slots=True)
class _Metric:
    label: str
    value: str


def _approved_css(reference: str) -> str:
    """Reuse only the approved reference stylesheet, never its seeded data."""
    source = (_RESOURCES / reference).read_text(encoding="utf-8")
    start = source.index("<style>") + len("<style>")
    end = source.index("</style>", start)
    return source[start:end]


_DYNAMIC_CSS = r"""
.chart-image{display:block;width:100%;height:auto;max-height:700px;object-fit:contain}
#charts .chart{padding:18px 20px 12px}
.page-view[hidden]{display:none}
.p2-strip{display:flex;align-items:center;gap:14px;padding-bottom:14px;margin-bottom:22px;border-bottom:1px solid var(--line)}
.p2-co{font-family:'Source Serif 4',Georgia,serif;font-size:15px;font-weight:600;color:var(--ink)}
.p2-px{font-size:14px;color:var(--ink-2);margin-left:auto}
.rail a.page-tab{font-size:13.5px}
.chart-empty{min-height:280px;display:grid;place-items:center;background:var(--panel);color:var(--muted);font-size:12px}
.question-line{font-family:'Source Serif 4',Georgia,serif;font-size:18px;line-height:1.5;color:var(--ink);margin:0 0 16px}
.question-line span{display:block;font-family:'IBM Plex Sans',Arial,sans-serif;font-size:9.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--gold);font-weight:600;margin-bottom:5px}
.reason-list{border-top:1px solid var(--line)}
.reason-row{display:grid;grid-template-columns:42px 190px minmax(0,1fr);gap:18px;padding:14px 0;border-bottom:1px solid var(--line-2);align-items:start}
.reason-index{font-family:'Source Serif 4',Georgia,serif;font-size:24px;line-height:1;color:var(--gold);font-weight:600}
.reason-title{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink);font-weight:600;padding-top:3px}
.reason-copy{font-size:13px;color:var(--body);line-height:1.52}
.comparison-table{width:100%;border-collapse:collapse;font-size:12px}
.comparison-table th{padding:9px 10px;text-align:left;background:var(--ink);color:#fff;font-size:9.5px;letter-spacing:.08em;text-transform:uppercase}
.comparison-table td{padding:9px 10px;border-bottom:1px solid var(--line-2);vertical-align:top}
.comparison-table tbody tr:nth-child(even){background:var(--panel)}
.source-link{color:var(--ink-2);text-decoration:none}.source-link:hover{text-decoration:underline}
.demo-note{padding:10px 13px;background:#FDFAF2;border-left:2px solid var(--gold);font-size:11px;color:var(--neutral);margin-top:14px}
.risk-list{margin:0;padding-left:18px}.risk-list li{margin-bottom:7px}
.report-meta{font-size:10.5px;color:var(--muted)}
.hidden-print-note{font-size:10.5px;color:var(--muted);margin-top:8px}
.rating-word.v-bull{background:none;color:var(--bull)}
.rating-word.v-bear{background:none;color:var(--bear)}
.rating-word.v-neu{background:none;color:var(--neutral)}
@media(max-width:900px){.reason-row{grid-template-columns:34px minmax(0,1fr)}.reason-copy{grid-column:2}.chart-image{max-height:none}}
@media print{.chart-image{max-height:178mm}.btn,.rail-tools{display:none!important}.reason-row{break-inside:avoid}.page-view[hidden]{display:block!important}.page-view:not(:last-child){break-after:page}}
"""


def _date_only(value: str) -> str:
    return value[:10] if len(value) >= 10 else value


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _tone(rating: Rating) -> tuple[str, str]:
    if rating in {Rating.STRONG_BUY, Rating.BUY, Rating.ADD}:
        return "v-bull", "bull"
    if rating in {Rating.REDUCE, Rating.SELL, Rating.AVOID}:
        return "v-bear", "bear"
    return "v-neu", "neutral"


def _metrics(result: ResearchResult) -> tuple[_Metric, ...]:
    return tuple(
        _Metric(str(label), str(value))
        for label, value in result.key_metrics
        if value and "unavailable" not in str(value).lower()
    )


def _find_metric(result: ResearchResult, *terms: str, default: str = "—") -> str:
    lowered = tuple(term.lower() for term in terms)
    for metric in _metrics(result):
        label = metric.label.lower()
        if any(term in label for term in lowered):
            return metric.value
    return default


# Keyword rules for sorting key metrics into the Data section's three columns.
# Checked in order; the first matching bucket wins, so more specific terms
# (an explicit "price target") must be listed before generic ones.
_POSITION_TERMS = (
    "purchase price",
    "quantity",
    "position value",
    "entry zone",
    "stop / invalidation",
    "first / second target",  # plan-specific — distinct from analyst/YCharts price targets
    "reward / risk",
)
_VALUATION_TERMS = (
    "market cap",
    "p/e",
    "revenue growth",
    "earnings growth",
    "analyst",
    "street consensus",
    "ycharts",
    "debt",
    "expense ratio",
    "distribution yield",
    "fund ",
    "security type",
    "current price",
    "range-end price",
)


def _metric_group(label: str) -> int:
    lowered = label.lower()
    if any(term in lowered for term in _POSITION_TERMS):
        return 0
    if any(term in lowered for term in _VALUATION_TERMS):
        return 2
    return 1  # trend & momentum is the default bucket


def _grouped_metrics(result: ResearchResult) -> tuple[list[_Metric], list[_Metric], list[_Metric]]:
    """Sort key metrics into (position & risk, trend & momentum, company & valuation)."""
    groups: tuple[list[_Metric], list[_Metric], list[_Metric]] = ([], [], [])
    for metric in _metrics(result):
        groups[_metric_group(metric.label)].append(metric)
    return groups


def _image_data_url(path_value: str) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_file():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _chart_html(chart: ChartRecord | None, element_id: str, legend: tuple[tuple[str, str], ...] = ()) -> str:
    if chart is None:
        return '<div class="chart-empty">No validated chart was available for this view.</div>'
    data_url = _image_data_url(chart.path)
    title = escape(chart.title)
    if data_url:
        visual = f'<img class="chart-image" src="{data_url}" alt="{title}">'
    else:
        visual = '<div class="chart-empty">The validated chart image could not be loaded.</div>'
    legend_html = ""
    if legend:
        keys = "".join(
            f'<span class="key"><i class="swatch" style="background:{color}"></i>{escape(text)}</span>'
            for color, text in legend
        )
        legend_html = f'<div class="chart-legend">{keys}</div>'
    insight = escape(chart.insight or (chart.insights[0] if chart.insights else ""))
    implication = (
        f'<div class="takeaway"><span class="tk">Decision implication</span><p>{insight}</p></div>'
        if insight
        else ""
    )
    return (
        f'<figure class="chart" id="{escape(element_id)}">'
        f'<div class="chart-title">{title}</div>{visual}{legend_html}</figure>{implication}'
    )


def _legend_metric(result: ResearchResult, *terms: str) -> str | None:
    value = _find_metric(result, *terms, default="")
    return value or None


def _price_chart_legend(result: ResearchResult, plan) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = [("var(--ink)", "Close")]
    sma20 = _legend_metric(result, "20-day moving average")
    if sma20:
        items.append(("var(--gold)", f"20-day avg {sma20}"))
    sma50 = _legend_metric(result, "50-day moving average")
    if sma50:
        items.append(("#5B7BA8", f"50-day avg {sma50}"))
    if plan is not None:
        items.append(("var(--gold-soft)", f"Entry zone {_money(plan.entry_low)}–{_money(plan.entry_high)}"))
        items.append(("var(--bear)", f"Stop {_money(plan.stop_level)}"))
    return tuple(items)


def _momentum_chart_legend(result: ResearchResult) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    rsi = _legend_metric(result, "RSI")
    if rsi:
        items.append(("var(--ink)", f"RSI {rsi}"))
    macd_signal = _legend_metric(result, "MACD / signal")
    if macd_signal and "/" in macd_signal:
        macd_value, signal_value = (part.strip() for part in macd_signal.split("/", 1))
        items.append(("#5B7BA8", f"MACD {macd_value}"))
        items.append(("var(--gold)", f"Signal {signal_value}"))
    return tuple(items)


def _relative_chart_legend(result: ResearchResult) -> tuple[tuple[str, str], ...]:
    for metric in _metrics(result):
        label = metric.label.lower()
        if "return vs." not in label:
            continue
        benchmark = metric.label.split("vs.", 1)[1].strip()
        match = re.match(r"\s*([+-]?[\d.]+%)\s*vs\.\s*([+-]?[\d.]+%)", metric.value)
        if not match:
            continue
        return (
            ("var(--ink)", f"{result.identity.ticker} {match.group(1)}"),
            ("var(--gold)", f"{benchmark} {match.group(2)}"),
        )
    return ()


def _fibonacci_chart_legend(result: ResearchResult) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = [("var(--ink)", "Close")]
    levels = _legend_metric(result, "fibonacci 38.2")
    if levels:
        items.append(("var(--muted)", f"Retracement levels {levels}"))
    swing = _legend_metric(result, "fibonacci swing range")
    if swing:
        items.append(("var(--gold)", f"Swing range {swing}"))
    return tuple(items)


def _source_html(result: ResearchResult) -> str:
    rows = []
    for source in result.sources:
        name = escape(source.name)
        locator = escape(source.locator, quote=True)
        supports = escape(source.supports)
        if source.locator.startswith(("https://", "http://")):
            name = f'<a class="source-link" href="{locator}" target="_blank" rel="noreferrer">{name}</a>'
        rows.append(f"<div><b>{name}</b> — {supports}</div>")
    return "".join(rows)


def _document(title: str, css_reference: str, body: str, script: str = "") -> str:
    css = _approved_css(css_reference) + _DYNAMIC_CSS
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&amp;family=IBM+Plex+Sans:wght@400;500;600&amp;family=IBM+Plex+Mono:wght@400;500;600&amp;display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>{body}<script>{script}</script></body>
</html>"""


def _masthead(result: ResearchResult, document_type: str) -> str:
    setup = technical_setup(result.technical.rating)
    outlook = fundamental_outlook(result.fundamental.rating)
    tone_class, _ = _tone(result.lead_rating)
    return f"""
<div class="mast">
  <div class="firm">Gottfried &amp; Somberg Wealth Management</div>
  <div class="doctype">{escape(document_type)}</div>
</div>
<div class="head">
  <div>
    <h1>{escape(result.identity.company_name)}</h1>
    <div class="ticker-strip"><b>{escape(result.identity.ticker)}</b><span class="dot"></span>{escape(result.identity.exchange)}<span class="dot"></span>{escape(result.identity.currency)}<span class="dot"></span>{escape(_date_only(result.as_of))}</div>
  </div>
  <div class="rating">
    <div class="rating-cap">Overall view</div>
    <div class="rating-word {tone_class}">{escape(result.lead_rating.value)}</div>
    <div class="rating-sub">{escape(setup)} setup · {escape(outlook)} fundamentals</div>
  </div>
</div>"""


def _topline(result: ResearchResult) -> str:
    return f"""
<div class="topline">
  <div class="tl"><div class="tl-k">Last price</div><div class="tl-v num">{_money(result.current_price)}</div><div class="tl-n">As of {_date_only(result.as_of)}</div></div>
  <div class="tl"><div class="tl-k">Technical setup</div><div class="tl-v">{escape(technical_setup(result.technical.rating))}</div><div class="tl-n">Trend and momentum</div></div>
  <div class="tl"><div class="tl-k">Fundamental view</div><div class="tl-v">{escape(fundamental_outlook(result.fundamental.rating))}</div><div class="tl-n">Business and valuation</div></div>
  <div class="tl"><div class="tl-k">Street target</div><div class="tl-v num">{escape(_find_metric(result, 'analyst mean target'))}</div><div class="tl-n">{escape(_find_metric(result, 'target implied upside', default='Consensus reference'))}</div></div>
</div>"""


def _general_chart(result: ResearchResult) -> ChartRecord | None:
    if result.overview_chart is not None:
        return result.overview_chart
    if result.chart_path:
        return ChartRecord("Decision evidence", result.chart_path, result.technical.summary)
    return None


def _general_report(result: ResearchResult, request: ResearchRequest) -> str:
    tone_class, _ = _tone(result.lead_rating)
    question = request.question.strip() or f"What does the current evidence say about {result.identity.ticker}?"
    answer = result.request_response.strip() or result.executive_summary.strip()
    technical_reason = result.technical.signals[0] if result.technical.signals else result.technical.summary
    fundamental_reason = result.fundamental.signals[0] if result.fundamental.signals else result.fundamental.summary
    risk_reason = result.risks[0] if result.risks else "The conclusion remains conditional on the cited evidence and decision triggers."
    reasons = (
        ("Technical timing", technical_reason),
        ("Business and value", fundamental_reason),
        ("Key risk", risk_reason),
    )
    reason_html = "".join(
        f'<div class="reason-row"><div class="reason-index">{index:02d}</div><div class="reason-title">{escape(title)}</div><div class="reason-copy">{escape(copy)}</div></div>'
        for index, (title, copy) in enumerate(reasons, 1)
    )
    plan = result.technical_plan
    if plan:
        actions = (
            ("Position", plan.stance, plan.market_condition),
            ("Entry", f"{_money(plan.entry_low)} – {_money(plan.entry_high)}", plan.confirmation),
            ("Risk", f"Stop {_money(plan.stop_level)}", plan.invalidation),
        )
    else:
        strategy = result.strategies[0] if result.strategies else None
        actions = (
            ("Position", result.lead_rating.value, result.executive_summary),
            ("Entry", strategy.action_zone if strategy else "No specific entry level supported", strategy.confirmation if strategy else "Wait for new evidence"),
            ("Risk", strategy.invalidation if strategy else "Use the cited decision triggers", strategy.risk if strategy else risk_reason),
        )
    action_html = "".join(
        f'<div class="action"><div class="action-k">{escape(label)}</div><div class="action-v">{escape(value)}</div><p>{escape(note)}</p></div>'
        for label, value, note in actions
    )
    metrics = _metrics(result)[:12]
    metric_rows = "".join(
        f'<div class="dr"><dt>{escape(metric.label)}</dt><dd>{escape(metric.value)}</dd></div>'
        for metric in metrics
    )
    risks = "".join(f"<li>{escape(item)}</li>" for item in result.risks[:4]) or "<li>No additional risk item was reported.</li>"
    triggers = "".join(f"<li>{escape(item)}</li>" for item in result.change_conditions[:4]) or "<li>Reassess when price structure or primary-source evidence changes.</li>"
    demo = '<div class="demo-note">Demonstration mode uses synthetic evidence and is not a client investment recommendation.</div>' if result.demo_mode else ""
    body = f"""
<div class="shell">
<nav class="rail" aria-label="Sections">
  <div class="rail-label">General Research</div>
  <a href="#answer" class="on">The answer</a><a href="#action">What we should do</a><a href="#evidence">Evidence</a><a href="#data">Essential data</a><a href="#risks">Risks &amp; triggers</a><a href="#sources">Sources</a>
  <div class="rail-tools"><button class="btn" onclick="window.print()">Print / save PDF</button></div>
</nav>
<main class="page">
{_masthead(result, 'General Research')}{_topline(result)}
<section id="answer">
  <div class="sec-head"><h2>The answer</h2><span class="verdict {tone_class}">{escape(result.lead_rating.value)}</span></div>
  <p class="question-line"><span>Your question</span>{escape(question)}</p>
  <div class="answer-card"><div class="answer-label">Direct answer</div><p class="answer">{escape(answer)}</p></div>
  <div class="reason-list" style="margin-top:20px">{reason_html}</div>{demo}
</section>
<section id="action"><div class="sec-head"><h2>What we should do</h2></div><div class="action-grid">{action_html}</div></section>
<section id="evidence"><div class="sec-head"><h2>Evidence</h2><span class="verdict v-neu">One decision chart</span></div>{_chart_html(_general_chart(result), 'generalEvidence')}</section>
<section id="data"><div class="sec-head"><h2>Essential data</h2></div><dl class="dl">{metric_rows}</dl></section>
<section id="risks"><div class="sec-head"><h2>Risks and decision triggers</h2></div><div class="grid3"><div><div class="dl-h">Primary risks</div><ul class="risk-list">{risks}</ul></div><div><div class="dl-h">What changes the view</div><ul class="risk-list">{triggers}</ul></div><div><div class="dl-h">Current sentiment</div><p>{escape(result.sentiment)}</p></div></div></section>
<section id="sources"><div class="sec-head"><h2>Sources</h2></div><div class="sources">{_source_html(result)}</div><p class="disc">This material is informational and reflects conditions as of the stated time. Sources are believed reliable but are not guaranteed. Opinions and scenarios may change without notice. Investing involves risk, including possible loss of principal. Firm compliance review is required before client distribution.</p><footer><span>Gottfried &amp; Somberg Wealth Management</span><span class="num">Prepared {_date_only(result.as_of)}</span></footer></section>
</main></div>"""
    return _document(
        f"{result.identity.ticker} General Research — Researcheus Maximus",
        "general_research_base.html",
        body,
        _navigation_script(),
    )


def _chart_by_title(result: ResearchResult, *terms: str) -> ChartRecord | None:
    lowered = tuple(term.lower() for term in terms)
    for chart in result.chartbook:
        title = chart.title.lower()
        if any(term in title for term in lowered):
            return chart
    return None


def _technical_report(result: ResearchResult, request: ResearchRequest) -> str:
    plan = result.technical_plan
    if plan is None:
        return _general_report(result, request)
    tone_class, _ = _tone(result.lead_rating)
    # Use the raw price-vs-average signal (not the full narrative summary) so this
    # chart's takeaway doesn't just repeat "The call" section verbatim.
    price_insight = result.technical.signals[0] if result.technical.signals else result.technical.summary
    price_chart = ChartRecord("Price structure", result.chart_path, price_insight) if result.chart_path else result.overview_chart
    charts = (
        ("Price structure", "evidencePrice", price_chart, _price_chart_legend(result, plan)),
        ("Momentum", "evidenceMomentum", _chart_by_title(result, "momentum"), _momentum_chart_legend(result)),
        ("Relative strength", "evidenceRelative", _chart_by_title(result, "relative"), _relative_chart_legend(result)),
        ("Fibonacci", "evidenceFibonacci", _chart_by_title(result, "fibonacci"), _fibonacci_chart_legend(result)),
    )
    tabs = "".join(
        f'<button class="evidence-tab" role="tab" aria-selected="{str(index == 0).lower()}" aria-controls="{panel_id}" id="{panel_id}Tab">{escape(label)}</button>'
        for index, (label, panel_id, _chart, _legend) in enumerate(charts)
    )
    panels = "".join(
        f'<div class="evidence-panel" id="{panel_id}" role="tabpanel" aria-labelledby="{panel_id}Tab"{("" if index == 0 else " hidden")}>{_chart_html(chart, panel_id + "Chart", legend)}</div>'
        for index, (_label, panel_id, chart, legend) in enumerate(charts)
    )
    reasons = "".join(f"<li>{escape(item)}</li>" for item in plan.rationale)
    groups = _grouped_metrics(result)
    group_names = ("Position and risk", "Trend and momentum", "Company and valuation")
    data_columns = "".join(
        '<dl class="dl"><div class="dl-h">{}</div>{}</dl>'.format(
            escape(group_names[index]),
            "".join(f'<div class="dr"><dt>{escape(metric.label)}</dt><dd>{escape(metric.value)}</dd></div>' for metric in group[:9]),
        )
        for index, group in enumerate(groups)
    )
    action_low = min(plan.stop_level, plan.entry_low, result.current_price)
    action_high = max(plan.second_target, plan.first_target, plan.entry_high, result.current_price)
    spread = max(action_high - action_low, result.current_price * 0.1)
    slider_min = max(0.01, action_low - spread * 0.16)
    slider_max = action_high + spread * 0.12
    entry_mid = (plan.entry_low + plan.entry_high) / 2
    plan_json = json.dumps(
        {
            "current": result.current_price,
            "entryLow": plan.entry_low,
            "entryHigh": plan.entry_high,
            "entryMid": entry_mid,
            "stop": plan.stop_level,
            "target1": plan.first_target,
            "target2": plan.second_target,
            "min": slider_min,
            "max": slider_max,
        },
        separators=(",", ":"),
    )
    demo = '<div class="demo-note">Demonstration mode uses synthetic evidence and is not a client investment recommendation.</div>' if result.demo_mode else ""
    scenario_tab = f'<button class="evidence-tab" role="tab" aria-selected="false" aria-controls="evidenceScenario" id="evidenceScenarioTab">Scenario tester</button>'
    scenario_panel = f'''<div class="evidence-panel" id="evidenceScenario" role="tabpanel" aria-labelledby="evidenceScenarioTab" hidden><div class="scen"><div><div class="slider-lab"><span class="big num" id="sPrice">{_money(result.current_price)}</span><span class="k" id="sDelta">At today's price</span></div><div class="slider-control"><input type="range" id="slider" min="{slider_min:.2f}" max="{slider_max:.2f}" step="0.01" value="{result.current_price:.2f}" aria-label="Test a future price"><div class="ticks"><span style="left:0%">{_money(slider_min)}</span><span style="left:100%">{_money(slider_max)}</span></div></div><div class="zone" id="zone" aria-live="polite"></div></div><div class="out"><div class="o-row"><span class="o-k">Change from today</span><span class="o-v num" id="oChg">0.0%</span></div><div class="o-row"><span class="o-k">Vs. entry midpoint</span><span class="o-v num" id="oEntry">—</span></div><div class="o-row"><span class="o-k">Distance to stop</span><span class="o-v num" id="oStop">—</span></div><div class="o-row"><span class="o-k">On a $100,000 position</span><span class="o-v num" id="oPnl">$0</span></div><div class="o-note">Illustrative only. Excludes dividends, commissions, taxes and execution differences.</div></div></div></div>'''
    page2_strip = f'''<div class="p2-strip"><span class="p2-co">{escape(result.identity.company_name)} <span class="num">{escape(result.identity.ticker)}</span></span><span class="p2-px num">{_money(result.current_price)}</span><span class="verdict {tone_class}">{escape(result.lead_rating.value)}</span></div>'''
    body = f"""
<div class="shell">
<nav class="rail" aria-label="Report pages">
  <div class="rail-label">Technical Research</div>
  <a href="#page1" class="page-tab on" data-page="page1">1 — The call</a>
  <a href="#page2" class="page-tab" data-page="page2">2 — Charts &amp; data</a>
  <div class="rail-tools"><button class="btn" id="advBtn" aria-pressed="false">Advisor detail: off</button><button class="btn" onclick="window.print()">Print / save PDF</button></div>
</nav>
<main class="page">
<div class="page-view" id="page1">
{_masthead(result, 'Technical Research')}{_topline(result)}
<section id="call"><div class="sec-head"><h2>The call</h2><span class="verdict {tone_class}">{escape(result.lead_rating.value)}</span></div><p class="lede">{escape(result.request_response or result.executive_summary)}</p><p>{escape(result.technical.summary)}</p>{demo}</section>
<section id="plan"><div class="sec-head"><h2>Action plan</h2><span class="verdict v-neu">{escape(plan.stance)}</span></div>
  <div class="ladder-wrap"><div class="ladder" id="ladder"></div><div class="rr"><div class="rr-k">Reward to risk</div><div class="rr-big num">{plan.reward_risk:.2f}×</div><div class="rr-note">Entry midpoint {_money(entry_mid)} to first target {_money(plan.first_target)}, measured against a {_money(plan.stop_level)} stop.</div><div class="rrbar"><div class="up" style="flex:{max(plan.reward_risk, 0.01):.2f}"></div><div class="dn" style="flex:1"></div></div><div class="rrleg"><span>+{_money(max(0, plan.first_target-entry_mid))} upside</span><span>−{_money(max(0, entry_mid-plan.stop_level))} risk</span></div></div></div>
  <div class="plan" style="margin-top:16px"><div class="pc"><div class="pc-k">Entry zone</div><div class="pc-v">{_money(plan.entry_low)} – {_money(plan.entry_high)}</div><div class="pc-n">{escape(plan.confirmation)}</div></div><div class="pc"><div class="pc-k">Stop / invalidation</div><div class="pc-v" style="color:var(--bear)">{_money(plan.stop_level)}</div><div class="pc-n">{plan.stop_pct:.1%} below entry midpoint. {escape(plan.invalidation)}</div></div><div class="pc"><div class="pc-k">Targets</div><div class="pc-v" style="color:var(--bull)">{_money(plan.first_target)} / {_money(plan.second_target)}</div><div class="pc-n">Planning references, not guaranteed outcomes.</div></div></div>
  <details><summary>Why these levels, and what invalidates them</summary><div class="det-body"><ul>{reasons}</ul></div></details>
  {f'<details class="adv"><summary>Options / hedging reference <span class="adv-flag">Advisor</span></summary><div class="det-body"><p>{escape(plan.options_strategy)} — {escape(plan.options_structure)}</p><p>{escape(plan.options_risk)}</p></div></details>' if plan.options_strategy else ''}
</section>
</div>
<div class="page-view" id="page2" hidden>
{page2_strip}
<section id="charts"><div class="sec-head"><h2>Charts</h2><span class="verdict v-neu">Five views, one panel</span></div><div class="evidence-tabs" role="tablist">{tabs}{scenario_tab}</div>{panels}{scenario_panel}</section>
<section id="fundamentals"><div class="sec-head"><h2>Fundamentals and data</h2><span class="verdict v-neu">{escape(fundamental_outlook(result.fundamental.rating))}</span></div><p class="lede">{escape(result.fundamental.summary)}</p><details><summary>Signals, risks and rating triggers</summary><div class="det-body"><ul>{''.join(f'<li>{escape(item)}</li>' for item in (*result.fundamental.signals, *result.risks[:3], *result.change_conditions[:3]))}</ul></div></details><div class="grid3" style="margin-top:20px">{data_columns}</div></section>
<section id="sources"><div class="sec-head"><h2>Sources</h2></div><div class="sources">{_source_html(result)}</div><p class="disc">This material is informational and reflects conditions as of the stated time. Sources are believed reliable but are not guaranteed. Scenarios may change without notice. Investing involves risk, including possible loss of principal. Options require separate suitability, approval and live-chain review. Firm compliance review is required before client distribution.</p><footer><span>Gottfried &amp; Somberg Wealth Management</span><span class="num">Prepared {_date_only(result.as_of)}</span></footer></section>
</div>
</main></div>"""
    script = f"const PLAN={plan_json};\n" + _technical_script()
    return _document(
        f"{result.identity.ticker} Technical Research — Researcheus Maximus",
        "technical_research_base.html",
        body,
        script,
    )


def _navigation_script() -> str:
    return r"""
document.querySelectorAll('.rail a').forEach(function(link){
  link.addEventListener('click',function(){document.querySelectorAll('.rail a').forEach(function(a){a.classList.remove('on')});link.classList.add('on')});
});
"""


def _technical_script() -> str:
    return _navigation_script() + r"""
function bindTabs(buttonSelector,panelSelector){
  var buttons=[].slice.call(document.querySelectorAll(buttonSelector));
  buttons.forEach(function(button){button.addEventListener('click',function(){
    buttons.forEach(function(item){item.setAttribute('aria-selected','false')});
    document.querySelectorAll(panelSelector).forEach(function(panel){panel.hidden=true});
    button.setAttribute('aria-selected','true');document.getElementById(button.getAttribute('aria-controls')).hidden=false;
  })});
}
bindTabs('.evidence-tab','.evidence-panel');
document.querySelectorAll('[data-evidence-index]').forEach(function(link){link.addEventListener('click',function(){var i=Number(link.dataset.evidenceIndex);var tabs=document.querySelectorAll('.evidence-tab');if(tabs[i])tabs[i].click()})});
var pageTabs=[].slice.call(document.querySelectorAll('.page-tab'));
pageTabs.forEach(function(tab){tab.addEventListener('click',function(event){
  event.preventDefault();
  pageTabs.forEach(function(item){item.classList.remove('on')});
  tab.classList.add('on');
  document.querySelectorAll('.page-view').forEach(function(view){view.hidden=(view.id!==tab.dataset.page)});
})});
var adv=document.getElementById('advBtn');if(adv)adv.addEventListener('click',function(){var on=document.body.classList.toggle('advisor');adv.setAttribute('aria-pressed',String(on));adv.textContent='Advisor detail: '+(on?'on':'off')});
function money(v){return '$'+v.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}
function pct(v){return (v>=0?'+':'')+(v*100).toFixed(1)+'%'}
function updateScenario(){
  var slider=document.getElementById('slider');if(!slider)return;var p=Number(slider.value),chg=p/PLAN.current-1,entry=p/PLAN.entryMid-1,dist=p-PLAN.stop;
  document.getElementById('sPrice').textContent=money(p);document.getElementById('sDelta').textContent=Math.abs(chg)<.0001?"At today's price":pct(chg)+' from today';
  document.getElementById('oChg').textContent=pct(chg);document.getElementById('oEntry').textContent=pct(entry);document.getElementById('oStop').textContent=money(Math.abs(dist))+' '+(dist>=0?'above':'below');document.getElementById('oPnl').textContent=(chg>=0?'+':'−')+money(Math.abs(chg*100000));
  var z=document.getElementById('zone');if(p<PLAN.stop)z.innerHTML='<b>Invalidated.</b> Price is below the planned stop; the setup no longer qualifies.';else if(p<PLAN.entryLow)z.innerHTML='<b>Below the entry zone.</b> Wait for price to reclaim structure before considering an order.';else if(p<=PLAN.entryHigh)z.innerHTML='<b>Inside the entry zone.</b> Act only if the stated confirmation is present.';else if(p<PLAN.target1)z.innerHTML='<b>Above the entry zone.</b> Avoid chasing; reassess reward to risk.';else if(p<PLAN.target2)z.innerHTML='<b>First target reached.</b> Review risk, sizing and whether to trail the stop.';else z.innerHTML='<b>Second target reached.</b> Re-underwrite rather than assuming further upside.';
}
var slider=document.getElementById('slider');if(slider){slider.addEventListener('input',updateScenario);updateScenario()}
(function(){
  var levels=[{p:PLAN.target2,l:'Second target',c:'tgt'},{p:PLAN.target1,l:'First target',c:'tgt'},{p:PLAN.entryMid,l:'Entry midpoint',c:'entry'},{p:PLAN.current,l:'Now',c:'now'},{p:PLAN.stop,l:'Stop',c:'stop'}];
  var lo=Math.min(PLAN.stop,PLAN.current,PLAN.entryLow),hi=Math.max(PLAN.target2,PLAN.current,PLAN.entryHigh),pad=(hi-lo)*.08;lo-=pad;hi+=pad;
  function y(p){return (1-(p-lo)/(hi-lo))*100}var h='<div class="lzone" style="top:'+y(PLAN.entryHigh)+'%;height:'+(y(PLAN.entryLow)-y(PLAN.entryHigh))+'%"></div>';
  levels.forEach(function(level){var tag=level.c==='now'?'<span class="lnow-chip">Now</span>':'<span class="ltag"><strong>'+level.l+'</strong></span>';h+='<div class="lrow '+level.c+'" style="top:'+y(level.p)+'%"><span class="lprice num">'+money(level.p)+'</span><span class="lrule"></span>'+tag+'</div>'});
  var ladder=document.getElementById('ladder');if(ladder)ladder.innerHTML=h;
})();
"""


def build_research_html(result: ResearchResult, request: ResearchRequest, output_path: Path) -> Path:
    """Write a validated, self-contained interactive report."""
    result.validate()
    request.validate()
    html = _technical_report(result, request) if request.deep_analysis else _general_report(result, request)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
