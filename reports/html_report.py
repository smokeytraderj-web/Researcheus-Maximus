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
/* The shell is centred with a max width, but below that width it ran edge to edge,
   leaving the navigation rail flush against the window with no gutter -- which reads
   as the report being clipped on the left. */
.shell{padding-left:26px;padding-right:26px;box-sizing:border-box}
.chart-image{display:block;width:100%;height:auto;max-height:800px;object-fit:contain}
#charts .chart{padding:18px 20px 12px}
.page-view[hidden]{display:none}
.p2-strip{display:flex;align-items:center;gap:14px;padding-bottom:14px;margin-bottom:22px;border-bottom:1px solid var(--line)}
.p2-co{font-family:'Source Serif 4',Georgia,serif;font-size:15px;font-weight:600;color:var(--ink)}
.p2-px{font-size:14px;color:var(--ink-2);margin-left:auto}
.tv-widget{width:100%;height:760px}
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
.reason-row.stance{grid-template-columns:104px 178px minmax(0,1fr)}
.stance-chip{display:inline-block;font-size:8.5px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;padding:4px 9px;border-radius:11px;white-space:nowrap;margin-top:1px}
.stance-chip.supports{background:#E7F1EB;color:var(--bull)}
.stance-chip.challenges{background:#F6E9E9;color:var(--bear)}
.stance-chip.partial{background:var(--panel);color:var(--neutral)}
.stance-chip.watch{background:#FDF6E7;color:#8A6D2F}
.verdict-hero{text-align:center;padding:30px 0 26px;border-bottom:1px solid var(--line)}
.verdict-hero .vh-cap{font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.13em;font-weight:600;margin-bottom:11px}
/* The tone classes carry a fill for inline chips; the hero wants the colour only. */
.verdict-hero .vh-word{font-family:'Source Serif 4',Georgia,serif;font-size:46px;line-height:1;font-weight:600;margin-bottom:9px;background:none!important;padding:0}
.verdict-hero .vh-sub{font-size:12px;color:var(--muted)}
.verdict-hero .vh-sub b{color:var(--ink)}
.pos-bar{display:flex;flex-wrap:wrap;gap:0;background:var(--panel);border-radius:7px;margin-bottom:22px;overflow:hidden}
.pos-cell{flex:1 1 180px;padding:13px 18px;border-right:1px solid var(--line)}
.pos-cell:last-child{border-right:none}
.pos-k{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600;margin-bottom:5px}
.pos-v{font-size:14.5px;font-weight:600;color:var(--ink);font-family:'IBM Plex Mono',monospace}
.pos-v.bull{color:var(--bull)}.pos-v.bear{color:var(--bear)}.pos-v.neutral{color:var(--neutral)}
.action p{font-size:12.5px;line-height:1.5;color:var(--body);margin:0}
.why-block{margin-top:20px;padding:16px 18px;border-left:3px solid var(--gold);background:var(--panel);border-radius:0 4px 4px 0}
.why-block .why-k{font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;font-weight:600;margin-bottom:9px}
.why-block p{font-size:13.5px;color:var(--body);line-height:1.62;margin:0}
.ev-note{font-size:12.5px;color:var(--body);margin-bottom:16px;padding:12px 15px;background:var(--panel);border-left:3px solid var(--gold);border-radius:0 4px 4px 0;line-height:1.6}
.ev-note b{color:var(--ink)}
.metric-group{margin-bottom:22px}
/* .grid3 is defined only in the technical stylesheet, so the general brief -- which
   uses the same markup -- was silently stacking these three columns. */
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:0 34px}
/* Hover read-out layered over a static chart.  The image stays the source of
   truth -- these are absolutely-positioned marks on top of it, so print and
   no-JS keep the full chart and simply lose the interaction. */
.chart-interactive{position:relative;display:block;line-height:0;cursor:crosshair}
.chart-interactive .chart-image{display:block}
.ch-cross{position:absolute;top:0;width:1px;background:var(--ink);opacity:.4;display:none;pointer-events:none;z-index:4}
.ch-dot{position:absolute;width:9px;height:9px;margin:-5px 0 0 -5px;border-radius:50%;background:var(--gold);border:2px solid #fff;box-shadow:0 0 0 1px var(--ink);display:none;pointer-events:none;z-index:5}
.ch-readout{position:absolute;top:10px;display:none;pointer-events:none;z-index:6;background:#fff;border:1px solid var(--line);border-radius:6px;padding:9px 11px;box-shadow:0 2px 10px rgba(22,35,63,.13);min-width:158px;line-height:1.5}
.ch-readout .ch-date{font-size:10px;letter-spacing:.06em;text-transform:uppercase;font-weight:700;color:var(--ink);margin-bottom:6px}
.ch-row{display:flex;justify-content:space-between;gap:16px;font-size:11px}
.ch-row .ch-k{color:var(--muted)}
.ch-row .ch-v{font-family:'IBM Plex Mono',monospace;color:var(--ink);font-weight:500}
.chart-hint{font-size:10px;color:var(--muted);margin-top:6px;font-style:italic}
/* Conviction Checklist: five deterministic, independent criteria (core/conviction_checklist.py)
   shown as checkboxes with a headline score.  Supplementary evidence, never a rating label.
   Horizontal, one column per criterion, so the whole thing reads at a glance right under
   the masthead -- this is the report's most-scanned piece of reasoning, not a buried detail. */
.cc-card{margin-top:18px;margin-bottom:20px}
.cc-top{display:flex;align-items:center;gap:14px;padding:0 1px 16px}
.cc-score{font-family:'Source Serif 4',Georgia,serif;font-size:26px;font-weight:700;color:var(--ink);line-height:1;white-space:nowrap}
.cc-score.perfect{color:var(--bull)}
.cc-toptext{flex:1}
.cc-title{font-size:12.5px;font-weight:600;color:var(--ink)}
.cc-sub{font-size:10px;color:var(--muted);margin-top:2px;line-height:1.4}
.cc-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:16px}
/* Each criterion is its own elevated card -- "floating" above the page rather
   than a row in a flat table, so the five read as independent, weighable checks. */
.cc-col{background:#fff;border:1px solid var(--line);border-radius:10px;padding:17px 15px 15px;position:relative;box-shadow:0 2px 7px rgba(22,35,63,.08);transition:box-shadow .15s ease}
.cc-col:hover{box-shadow:0 5px 14px rgba(22,35,63,.14)}
.cc-col-top{display:flex;align-items:center;gap:7px;margin-bottom:9px}
.cc-box{flex:none;width:16px;height:16px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}
.cc-box.pass{background:var(--bull);color:#fff}
.cc-box.fail{background:#fff;border:1.5px solid var(--line);color:transparent}
.cc-box.unconfirmed{background:var(--panel);border:1.5px solid var(--line);color:var(--muted);font-size:9px}
.cc-label{flex:1;font-size:10.5px;font-weight:600;color:var(--ink);line-height:1.25}
/* The info circle takes hover OR focus, so a click (which focuses a button) works
   identically to a hover -- no JS needed, and it stays keyboard-reachable. */
.cc-info{flex:none;width:14px;height:14px;padding:0;border-radius:50%;border:1px solid var(--line);background:#fff;color:var(--muted);font:italic 700 9px/1 'Source Serif 4',Georgia,serif;display:flex;align-items:center;justify-content:center;cursor:help}
.cc-info:hover,.cc-info:focus{background:var(--ink);border-color:var(--ink);color:#fff;outline:none}
.cc-tip{position:absolute;z-index:20;top:100%;left:14px;margin-top:6px;width:172px;background:var(--ink);color:#fff;font-size:10px;line-height:1.45;padding:9px 10px;border-radius:6px;box-shadow:0 4px 14px rgba(22,35,63,.22);visibility:hidden;opacity:0;transition:opacity .12s ease}
.cc-col:first-child .cc-tip{left:0}
.cc-col:last-child .cc-tip{left:auto;right:0}
.cc-info:hover+.cc-tip,.cc-info:focus+.cc-tip{visibility:visible;opacity:1}
.cc-detail{font-size:10px;color:var(--body);line-height:1.4}
/* Screen relies on the hover/click tooltip above; print can't hover, so it gets the
   same explanation as a small static caption instead of losing it entirely. */
.cc-explain{display:none}
@media print{
.cc-card{break-inside:avoid}
.cc-col{box-shadow:none}
.cc-box.pass{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.cc-info,.cc-tip{display:none!important}
.cc-explain{display:block;font-size:8.5px;color:var(--muted);font-style:italic;line-height:1.35;margin-top:3px}
}
.trigger-list{margin:0;padding:0;list-style:none}
.trigger-list li{font-size:12.5px;color:var(--body);line-height:1.5;padding:6px 0 6px 15px;position:relative}
.trigger-list li:before{content:"→";position:absolute;left:0;color:var(--gold);font-weight:600}
@media(max-width:900px){.reason-row{grid-template-columns:34px minmax(0,1fr)}.reason-row.stance{grid-template-columns:104px minmax(0,1fr)}.reason-copy{grid-column:2}.chart-image{max-height:none}.grid3{grid-template-columns:1fr}.cc-grid{grid-template-columns:repeat(2,1fr)}}
@media print{.chart-image{max-height:178mm}.btn,.rail-tools{display:none!important}.reason-row{break-inside:avoid}.page-view[hidden]{display:block!important}.page-view:not(:last-child){break-after:page}
/* The @page margin supplies the printed gutter; the screen one would double it. */
.shell{padding-left:0;padding-right:0}
/* The stance chips, position bar and callout panels carry meaning through
   colour, so keep their fills in print instead of letting them wash out. */
.ch-cross,.ch-dot,.ch-readout,.chart-hint{display:none!important}
.chart-interactive{cursor:auto}
/* Deep Technical prints every chart panel, so the charts section must be allowed
   to flow across pages.  With the template's blanket section{break-inside:avoid}
   it jumped wholesale to the next page instead, stranding the running strip above
   it on a near-empty page.  Keep each individual panel intact, not the whole set. */
/* The TradingView panel is a live embed: in print it is a 760px empty box that
   costs a whole blank page, so drop it and say where the live view lives. */
.tech-report #evidenceTradingView{display:none!important}
.tech-report #charts{break-inside:auto}
.tech-report .p2-strip{break-after:avoid;break-inside:avoid}
.tech-report .evidence-panel{break-inside:avoid;margin-top:14px}
.tech-report .chart-image{max-height:132mm}
.tech-report figure.chart{break-inside:avoid}
.tech-report .takeaway{break-before:avoid;break-inside:avoid}
.tech-report #fundamentals{break-inside:auto}
.chart-empty{min-height:0;padding:14px;font-style:italic}
.stance-chip,.pos-bar,.why-block,.ev-note,.demo-note{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.pos-bar,.metric-group,.why-block,.ev-note{break-inside:avoid}
.verdict-hero{padding:14px 0 12px;break-inside:avoid}.verdict-hero .vh-word{font-size:34px}
.pos-bar{margin-bottom:14px}.metric-group{margin-bottom:14px}
/* Hold the approved three-page General Research brief: (1) answer and reasoning,
   (2) action plan with its chart, (3) data, risks, sources.  The base template's
   blanket per-section break rules would otherwise spread these across six pages,
   so pin the two intended breaks and tighten the type enough to fit -- compressing
   spacing and scale, never dropping evidence or dropping below readable sizes. */
/* A printed Letter page is ~816px wide, which trips the approved template's
   900px mobile breakpoint -- so print was silently getting the stacked phone
   layout.  Restore the intended desktop grids for the brief. */
.general-brief .head{flex-direction:row}
.general-brief .rating{text-align:right}
.general-brief .topline{grid-template-columns:repeat(4,1fr)}
.general-brief .tl{border-left:1px solid var(--line);padding-left:12px}
.general-brief .tl:first-child{border-left:0;padding-left:0}
.general-brief .action-grid,.general-brief .data-grid,.general-brief .risk-grid,.general-brief .grid3{grid-template-columns:repeat(3,1fr)}
.general-brief .cc-grid{grid-template-columns:repeat(5,1fr)}
.general-brief .reason-row.stance{grid-template-columns:92px 148px minmax(0,1fr)}
.general-brief .reason-copy{grid-column:auto}
.general-brief section{break-inside:auto;margin-top:14px}
.general-brief #answer{break-before:auto}
/* #action no longer forces its own page: the Conviction Checklist makes the answer
   section's length vary with the score (an all-pass or all-fail read is shorter
   than a mixed one with several detail lines), and a fixed break here was
   stranding a mostly-empty page whenever that content ran long. Letting it flow
   costs the guaranteed page-1/page-2 split but never strands blank space. */
.general-brief #action{break-before:auto}
.general-brief #evidence{break-before:auto}
.general-brief #data{break-before:page}
.general-brief #risks,.general-brief #sources{break-before:auto}
.general-brief .sec-head{margin-bottom:9px}
.general-brief .sec-head h2{font-size:16px}
.general-brief .topline{margin-top:10px}
.general-brief .tl{padding:8px 12px}
.general-brief .tl-v{font-size:14px}
.general-brief .verdict-hero{padding:11px 0 9px}
.general-brief .verdict-hero .vh-word{font-size:29px;margin-bottom:5px}
.general-brief .question-line{font-size:14.5px;margin-bottom:11px}
.general-brief .answer-card{padding:11px 14px}
.general-brief .answer{font-size:14px;line-height:1.45}
.general-brief .why-block{margin-top:12px;padding:11px 14px}
.general-brief .why-block p{font-size:11.5px;line-height:1.5}
.general-brief .cc-card{margin-top:12px;margin-bottom:14px}
.general-brief .cc-top{padding:0 1px 11px}
.general-brief .cc-score{font-size:21px}
.general-brief .cc-grid{gap:10px}
.general-brief .cc-col{padding:11px 12px 10px}
.general-brief .cc-col-top{margin-bottom:7px}
.general-brief .cc-label{font-size:9.5px}
.general-brief .cc-detail{font-size:9px}
.general-brief .cc-explain{font-size:8px}
.general-brief .reason-list{margin-top:12px!important}
.general-brief .reason-row{padding:6px 0}
.general-brief .reason-copy{font-size:11.5px;line-height:1.45}
.general-brief .pos-cell{padding:9px 14px}
.general-brief .action-grid{gap:11px}
.general-brief .ev-note{padding:9px 13px;font-size:11px;margin-bottom:11px}
.general-brief .chart-image{max-height:108mm}
/* .takeaway is a sibling of figure.chart, not nested in it (see _chart_html), so
   avoiding a break inside the figure alone still let its caption strip separate
   onto the next page by itself.  break-before:avoid on the caption is what keeps
   image and caption together, pulling the whole pair to the next page as a unit
   when they do not both fit. */
.general-brief figure.chart{break-inside:avoid;break-after:avoid}
.general-brief .takeaway{break-inside:avoid;break-before:avoid}
.general-brief .dr{padding:3px 0}
.general-brief .dl-h{margin-bottom:4px}
.general-brief .metric-group{margin-bottom:11px}
.general-brief .risk-list li,.general-brief .trigger-list li{font-size:11px;margin-bottom:2px;padding-top:2px;padding-bottom:2px}
.general-brief #sources{margin-top:11px}
.general-brief #sources .sec-head{break-after:avoid}
.general-brief .sources{font-size:10px}
/* Same orphan risk as the chart caption above: nothing stopped the disclosure
   paragraph or the firm footer from splitting onto a page of their own beneath
   an otherwise-full sources list. */
.general-brief .disc{font-size:8.5px;line-height:1.38;margin-top:7px;break-before:avoid;break-inside:avoid}
.general-brief footer{margin-top:8px;padding-top:8px;break-before:avoid}}
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


def _conviction_checklist_html(checklist) -> str:
    """The five-point checklist card, or nothing when a result carries none.

    Horizontal, one column per criterion, meant to sit right under the masthead
    where it reads at a glance -- this is the report's most-scanned reasoning,
    not a buried detail. Each column carries a hover/click info circle with a
    plain-English explanation of what that criterion measures (`explanation`,
    fixed per criterion in core/conviction_checklist.py), kept separate from
    `detail`, which is this security's actual reading against it. Print can't
    hover, so `.cc-explain` repeats the same explanation as a static caption
    instead of losing it there.
    """
    if checklist is None or not checklist.criteria:
        return ""
    icons = {"pass": "✓", "fail": "", "unconfirmed": "?"}
    cols = "".join(
        f'<div class="cc-col"><div class="cc-col-top">'
        f'<div class="cc-box {item.status}">{icons[item.status]}</div>'
        f'<div class="cc-label">{escape(item.label)}</div>'
        f'<button type="button" class="cc-info" aria-label="What {escape(item.label)} measures">i</button>'
        f'<div class="cc-tip" role="tooltip">{escape(item.explanation)}</div>'
        f'</div><div class="cc-detail">{escape(item.detail)}</div>'
        f'<div class="cc-explain">{escape(item.explanation)}</div></div>'
        for item in checklist.criteria
    )
    score_class = "perfect" if checklist.is_perfect else ""
    sub = "Five independent, deterministic criteria — supplementary evidence, not a rating."
    if checklist.unconfirmed_count:
        sub += f" {checklist.unconfirmed_count} could not be confirmed from the available evidence."
    return f"""<div class="cc-card">
  <div class="cc-top">
    <div class="cc-score {score_class}">{checklist.passed_count}/{checklist.total_count}</div>
    <div class="cc-toptext"><div class="cc-title">Conviction Checklist</div><div class="cc-sub">{escape(sub)}</div></div>
  </div>
  <div class="cc-grid">{cols}</div>
</div>"""


def _stance(specialist: Rating, lead: Rating) -> tuple[str, str]:
    """Whether a specialist rating agrees with the lead rating, as (css_class, label).

    Directional agreement only -- Buy vs Strong Buy still "supports".  A neutral
    on either side is "partial" rather than a conflict, and only an outright
    bull/bear split counts as "challenges".
    """
    specialist_tone = _tone(specialist)[1]
    lead_tone = _tone(lead)[1]
    if specialist_tone == lead_tone:
        return "supports", "Supports"
    if "neutral" in (specialist_tone, lead_tone):
        return "partial", "Partial"
    return "challenges", "Challenges"


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


def _hover_payload(path_value: str) -> str:
    """The read-out data a chart renderer wrote beside its PNG, if it wrote any.

    Charts that expose their plotted series get a hover read-out in the browser;
    charts that don't simply stay static, so this is safe to call for all of them.
    """
    if not path_value:
        return ""
    sidecar = Path(path_value + ".json")
    if not sidecar.is_file():
        return ""
    raw = sidecar.read_text(encoding="utf-8")
    # Escaped so the payload can never close its own <script> element.
    return raw.replace("<", "\\u003c")


def _chart_html(chart: ChartRecord | None, element_id: str, legend: tuple[tuple[str, str], ...] = ()) -> str:
    if chart is None:
        return '<div class="chart-empty">No validated chart was available for this view.</div>'
    data_url = _image_data_url(chart.path)
    title = escape(chart.title)
    if data_url:
        visual = f'<img class="chart-image" src="{data_url}" alt="{title}">'
        hover = _hover_payload(chart.path)
        if hover:
            visual = (
                f'<div class="chart-interactive">{visual}'
                '<div class="ch-cross"></div><div class="ch-dot"></div><div class="ch-readout"></div>'
                f'<script type="application/json" class="ch-data">{hover}</script></div>'
                '<div class="chart-hint">Hover the chart for the values on any date.</div>'
            )
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


def _volume_chart_legend(result: ResearchResult) -> tuple[tuple[str, str], ...]:
    return (
        ("var(--ink)", "Close"),
        ("var(--gold)", "Point of control — most-traded price"),
        ("#5378A5", "Value area — 70% of volume"),
        ("var(--bear)", "Current price"),
    )


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


def _document(title: str, css_reference: str, body: str, script: str = "", extra_css: str = "") -> str:
    css = _approved_css(css_reference) + _DYNAMIC_CSS + extra_css
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
    tone_class, tone_name = _tone(result.lead_rating)
    question = request.question.strip() or f"What does the current evidence say about {result.identity.ticker}?"
    answer = result.request_response.strip() or result.executive_summary.strip()
    technical_reason = result.technical.signals[0] if result.technical.signals else result.technical.summary
    fundamental_reason = result.fundamental.signals[0] if result.fundamental.signals else result.fundamental.summary
    risk_reason = result.risks[0] if result.risks else "The conclusion remains conditional on the cited evidence and decision triggers."
    # Each supporting reason carries whether that workstream agrees with the lead
    # rating.  This replaces a decorative 01/02/03 sequence -- these are parallel
    # evidence dimensions, not steps -- and surfaces the agreement/disagreement
    # the rating policy requires us to state explicitly.
    reasons = (
        ("Technical timing", technical_reason, _stance(result.technical.rating, result.lead_rating)),
        ("Business and value", fundamental_reason, _stance(result.fundamental.rating, result.lead_rating)),
        ("Key risk", risk_reason, ("watch", "Watch")),
    )
    reason_html = "".join(
        f'<div class="reason-row stance"><div><span class="stance-chip {chip}">{escape(chip_label)}</span></div>'
        f'<div class="reason-title">{escape(title)}</div><div class="reason-copy">{escape(copy)}</div></div>'
        for title, copy, (chip, chip_label) in reasons
    )
    # The bar states the three levels at a glance; the cards below then carry the
    # conditions attached to them.  Keeping the levels out of the cards avoids
    # printing the same three numbers twice in the same section.
    plan = result.technical_plan
    strategy = result.strategies[0] if result.strategies else None
    if plan:
        position_value = plan.stance
        entry_value = f"{_money(plan.entry_low)} – {_money(plan.entry_high)}"
        stop_value = _money(plan.stop_level)
        actions = (
            ("Market condition", plan.market_condition),
            ("Confirmation needed", plan.confirmation),
            ("Invalidation", plan.invalidation),
        )
    else:
        position_value = result.lead_rating.value
        entry_value = strategy.action_zone if strategy else "No specific entry level supported"
        stop_value = strategy.invalidation if strategy else "Use the cited decision triggers"
        actions = (
            ("Market condition", result.executive_summary),
            ("Confirmation needed", strategy.confirmation if strategy else "Wait for new evidence"),
            ("Invalidation", strategy.risk if strategy else risk_reason),
        )
    action_html = "".join(
        f'<div class="action"><div class="action-k">{escape(label)}</div><p>{escape(note)}</p></div>'
        for label, note in actions
    )
    # Group the data by the story it tells rather than one flat list.  Reuses the
    # same keyword rules as the technical report; the position/risk group is
    # deliberately omitted here because the plan above already states those levels.
    all_metrics = _metrics(result)
    _position_metrics, trend_metrics, valuation_metrics = _grouped_metrics(result)

    def metric_group_html(label: str, metrics: list[_Metric]) -> str:
        if not metrics:
            return ""
        rows = "".join(f'<div class="dr"><dt>{escape(m.label)}</dt><dd>{escape(m.value)}</dd></div>' for m in metrics)
        return f'<div class="metric-group"><div class="dl-h">{label}</div><dl class="dl">{rows}</dl></div>'

    data_html = (
        metric_group_html("Business and valuation", valuation_metrics[:6])
        + metric_group_html("Trend and momentum", trend_metrics[:6])
    ) or metric_group_html("Key figures", list(all_metrics[:8]))

    risks = "".join(f"<li>{escape(item)}</li>" for item in result.risks[:4]) or "<li>No additional risk item was reported.</li>"
    trigger_items = result.change_conditions[:4] or (
        "Reassess when price structure or primary-source evidence changes.",
    )
    triggers = "".join(f"<li>{escape(item)}</li>" for item in trigger_items)
    demo = '<div class="demo-note">Demonstration mode uses synthetic evidence and is not a client investment recommendation.</div>' if result.demo_mode else ""
    qualitative_summary = result.executive_summary.strip() if result.executive_summary.strip() else answer

    # Numbers behind the rating, alongside the chart -- the chart carries the
    # visual case, so this strip carries the figures it cannot show.  Draw from
    # valuation and trend, never the position plan: those levels are already
    # stated in the action bar directly above, and repeating them says nothing.
    key_metrics_list = (valuation_metrics[:2] + trend_metrics[:2]) or list(all_metrics[:3])
    key_figures = (
        " &nbsp;&middot;&nbsp; ".join(f"{escape(m.label)} <b>{escape(m.value)}</b>" for m in key_metrics_list)
        if key_metrics_list
        else "Supporting figures are listed under Essential data."
    )

    body = f"""
<div class="shell">
<nav class="rail" aria-label="Sections">
  <div class="rail-label">General Research</div>
  <a href="#answer" class="on">The answer</a><a href="#action">What we should do</a><a href="#evidence">Evidence</a><a href="#data">Essential data</a><a href="#risks">Risks &amp; triggers</a><a href="#sources">Sources</a>
  <div class="rail-tools"><button class="btn" onclick="window.print()">Print / save PDF</button></div>
</nav>
<main class="page general-brief">
{_masthead(result, 'General Research')}
{_conviction_checklist_html(result.conviction_checklist)}
{_topline(result)}
<section id="answer">
  <div class="verdict-hero">
    <div class="vh-cap">Our recommendation</div>
    <div class="vh-word {tone_class}">{escape(result.lead_rating.value)}</div>
    <div class="vh-sub">Confidence <b>{escape(result.confidence.value)}</b></div>
  </div>
  <p class="question-line" style="margin-top:24px"><span>Your question</span>{escape(question)}</p>
  <div class="answer-card"><div class="answer-label">Direct answer</div><p class="answer">{escape(answer)}</p></div>
  <div class="why-block">
    <div class="why-k">Why</div>
    <p>{escape(qualitative_summary)}</p>
  </div>
  <div class="reason-list" style="margin-top:20px">{reason_html}</div>
  {demo}
</section>
<section id="action">
  <div class="sec-head"><h2>What we should do</h2></div>
  <div class="pos-bar">
    <div class="pos-cell"><div class="pos-k">Position</div><div class="pos-v {tone_name}">{escape(position_value)}</div></div>
    <div class="pos-cell"><div class="pos-k">Entry</div><div class="pos-v">{escape(entry_value)}</div></div>
    <div class="pos-cell"><div class="pos-k">Stop</div><div class="pos-v bear">{escape(stop_value)}</div></div>
  </div>
  <div class="action-grid">{action_html}</div>
</section>
<section id="evidence">
  <div class="sec-head"><h2>Evidence</h2><span class="verdict v-neu">One decision chart</span></div>
  <div class="ev-note"><b>Figures behind this view:</b> {key_figures}</div>
  {_chart_html(_general_chart(result), 'generalEvidence')}
</section>
<section id="data">
  <div class="sec-head"><h2>Essential data</h2></div>
  {data_html}
</section>
<section id="risks">
  <div class="sec-head"><h2>Risks and decision triggers</h2></div>
  <div class="grid3">
    <div>
      <div class="dl-h">Primary risks</div>
      <ul class="risk-list">{risks}</ul>
    </div>
    <div>
      <div class="dl-h">What changes the view</div>
      <ul class="trigger-list">{triggers}</ul>
    </div>
    <div>
      <div class="dl-h">Current sentiment</div>
      <p>{escape(result.sentiment)}</p>
    </div>
  </div>
</section>
<section id="sources">
  <div class="sec-head"><h2>Sources</h2></div>
  <div class="sources">{_source_html(result)}</div>
  <p class="disc">This material is informational and reflects conditions as of the stated time. Sources are believed reliable but are not guaranteed. Opinions and scenarios may change without notice. Investing involves risk, including possible loss of principal. Firm compliance review is required before client distribution.</p>
  <footer><span>Gottfried &amp; Somberg Wealth Management</span><span class="num">Prepared {_date_only(result.as_of)}</span></footer>
</section>
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


def _tradingview_symbol(result: ResearchResult) -> str:
    """Map our exchange metadata to TradingView's exchange codes for the public widget."""
    value = result.identity.exchange.upper().replace(" ", "")
    if any(token in value for token in ("NASDAQ", "NMS", "NGM", "NCM")):
        exchange = "NASDAQ"
    elif "NYSE" in value or value in {"NYQ", "ASE"}:
        exchange = "NYSE"
    elif "AMEX" in value:
        exchange = "AMEX"
    else:
        exchange = value or "NASDAQ"
    return f"{exchange}:{result.identity.ticker}"


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
    # Volume by price only exists when the security reported usable volume, so this
    # tab appears alongside the fixed four rather than showing an empty panel.
    volume_chart = _chart_by_title(result, "volume by price")
    if volume_chart is not None:
        charts += (("Volume by price", "evidenceVolume", volume_chart, _volume_chart_legend(result)),)
    options_chart = _chart_by_title(result, "options and volatility")
    if options_chart is not None:
        charts += (
            (
                "Options & volatility",
                "evidenceOptions",
                options_chart,
                (
                    ("var(--ink)", "Implied volatility by strike"),
                    ("#5378A5", "Expected move to expiry"),
                    ("var(--bear)", "Spot"),
                ),
            ),
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
    tv_symbol = _tradingview_symbol(result)
    tv_tab = '<button class="evidence-tab" role="tab" aria-selected="false" aria-controls="evidenceTradingView" id="evidenceTradingViewTab">TradingView</button>'
    tv_panel = '<div class="evidence-panel" id="evidenceTradingView" role="tabpanel" aria-labelledby="evidenceTradingViewTab" hidden><figure class="chart" style="padding:0"><div id="tvWidget" class="tv-widget"></div></figure></div>'
    scenario_tab = f'<button class="evidence-tab" role="tab" aria-selected="false" aria-controls="evidenceScenario" id="evidenceScenarioTab">Scenario tester</button>'
    scenario_panel = f'''<div class="evidence-panel" id="evidenceScenario" role="tabpanel" aria-labelledby="evidenceScenarioTab" hidden><div class="scen"><div><div class="slider-lab"><span class="big num" id="sPrice">{_money(result.current_price)}</span><span class="k" id="sDelta">At today's price</span></div><div class="slider-control"><input type="range" id="slider" min="{slider_min:.2f}" max="{slider_max:.2f}" step="0.01" value="{result.current_price:.2f}" aria-label="Test a future price"><div class="ticks"><span style="left:0%">{_money(slider_min)}</span><span style="left:100%">{_money(slider_max)}</span></div></div><div class="zone" id="zone" aria-live="polite"></div></div><div class="out"><div class="o-row"><span class="o-k">Change from today</span><span class="o-v num" id="oChg">0.0%</span></div><div class="o-row"><span class="o-k">Vs. entry midpoint</span><span class="o-v num" id="oEntry">—</span></div><div class="o-row"><span class="o-k">Distance to stop</span><span class="o-v num" id="oStop">—</span></div><div class="o-row"><span class="o-k">On a $100,000 position</span><span class="o-v num" id="oPnl">$0</span></div><div class="o-note">Illustrative only. Excludes dividends, commissions, taxes and execution differences.</div></div></div></div>'''
    page2_strip = f'''<div class="p2-strip"><span class="p2-co">{escape(result.identity.company_name)} <span class="num">{escape(result.identity.ticker)}</span></span><span class="p2-px num">{_money(result.current_price)}</span><span class="verdict {tone_class}">{escape(result.lead_rating.value)}</span></div>'''
    body = f"""
<div class="shell">
<nav class="rail" aria-label="Report pages">
  <div class="rail-label">Technical Research</div>
  <a href="#page1" class="page-tab on" data-page="page1">1 — The call</a>
  <a href="#page2" class="page-tab" data-page="page2">2 — Charts</a>
  <a href="#page3" class="page-tab" data-page="page3">3 — Fundamentals</a>
  <div class="rail-tools"><button class="btn" id="advBtn" aria-pressed="false">Advisor detail: off</button><button class="btn" onclick="window.print()">Print / save PDF</button></div>
</nav>
<main class="page tech-report">
<div class="page-view" id="page1">
{_masthead(result, 'Technical Research')}{_topline(result)}
<section id="call">
  <div class="verdict-hero">
    <div class="vh-cap">The call</div>
    <div class="vh-word {tone_class}">{escape(result.lead_rating.value)}</div>
    <div class="vh-sub">Confidence <b>{escape(result.confidence.value)}</b> &nbsp;·&nbsp; {escape(plan.stance)}</div>
  </div>
  <div class="pos-bar" style="margin-top:20px">
    <div class="pos-cell"><div class="pos-k">Entry</div><div class="pos-v">{_money(plan.entry_low)} – {_money(plan.entry_high)}</div></div>
    <div class="pos-cell"><div class="pos-k">Stop</div><div class="pos-v bear">{_money(plan.stop_level)}</div></div>
    <div class="pos-cell"><div class="pos-k">First target</div><div class="pos-v bull">{_money(plan.first_target)}</div></div>
    <div class="pos-cell"><div class="pos-k">Reward / risk</div><div class="pos-v">{plan.reward_risk:.2f}×</div></div>
  </div>
  <p class="lede" style="margin-top:18px">{escape(result.request_response or result.executive_summary)}</p><p>{escape(result.technical.summary)}</p>{demo}
</section>
<section id="plan"><div class="sec-head"><h2>Action plan</h2><span class="verdict v-neu">{escape(plan.stance)}</span></div>
  <div class="ladder-wrap"><div class="ladder" id="ladder"></div><div class="rr"><div class="rr-k">Reward to risk</div><div class="rr-big num">{plan.reward_risk:.2f}×</div><div class="rr-note">Entry midpoint {_money(entry_mid)} to first target {_money(plan.first_target)}, measured against a {_money(plan.stop_level)} stop.</div><div class="rrbar"><div class="up" style="flex:{max(plan.reward_risk, 0.01):.2f}"></div><div class="dn" style="flex:1"></div></div><div class="rrleg"><span>+{_money(max(0, plan.first_target-entry_mid))} upside</span><span>−{_money(max(0, entry_mid-plan.stop_level))} risk</span></div></div></div>
  <div class="plan" style="margin-top:16px"><div class="pc"><div class="pc-k">Entry zone</div><div class="pc-v">{_money(plan.entry_low)} – {_money(plan.entry_high)}</div><div class="pc-n">{escape(plan.confirmation)}</div></div><div class="pc"><div class="pc-k">Stop / invalidation</div><div class="pc-v" style="color:var(--bear)">{_money(plan.stop_level)}</div><div class="pc-n">{plan.stop_pct:.1%} below entry midpoint. {escape(plan.invalidation)}</div></div><div class="pc"><div class="pc-k">Targets</div><div class="pc-v" style="color:var(--bull)">{_money(plan.first_target)} / {_money(plan.second_target)}</div><div class="pc-n">Planning references, not guaranteed outcomes.</div></div></div>
  <details><summary>Why these levels, and what invalidates them</summary><div class="det-body"><ul>{reasons}</ul></div></details>
  {f'<details class="adv"><summary>Options / hedging reference <span class="adv-flag">Advisor</span></summary><div class="det-body"><p>{escape(plan.options_strategy)} — {escape(plan.options_structure)}</p><p>{escape(plan.options_risk)}</p></div></details>' if plan.options_strategy else ''}
</section>
</div>
<div class="page-view" id="page2" hidden>
{page2_strip}
<section id="charts"><div class="sec-head"><h2>Charts</h2><span class="verdict v-neu">Six views, one panel</span></div><div class="evidence-tabs" role="tablist">{tabs}{tv_tab}{scenario_tab}</div>{panels}{tv_panel}{scenario_panel}</section>
</div>
<div class="page-view" id="page3" hidden>
{page2_strip}
<section id="fundamentals"><div class="sec-head"><h2>Fundamentals and data</h2><span class="verdict v-neu">{escape(fundamental_outlook(result.fundamental.rating))}</span></div><p class="lede">{escape(result.fundamental.summary)}</p><details><summary>Signals, risks and rating triggers</summary><div class="det-body"><ul>{''.join(f'<li>{escape(item)}</li>' for item in (*result.fundamental.signals, *result.risks[:3], *result.change_conditions[:3]))}</ul></div></details><div class="grid3" style="margin-top:20px">{data_columns}</div></section>
<section id="sources"><div class="sec-head"><h2>Sources</h2></div><div class="sources">{_source_html(result)}</div><p class="disc">This material is informational and reflects conditions as of the stated time. Sources are believed reliable but are not guaranteed. Scenarios may change without notice. Investing involves risk, including possible loss of principal. Options require separate suitability, approval and live-chain review. Firm compliance review is required before client distribution.</p><footer><span>Gottfried &amp; Somberg Wealth Management</span><span class="num">Prepared {_date_only(result.as_of)}</span></footer></section>
</div>
</main></div>"""
    script = f"const PLAN={plan_json};\nconst TV_SYMBOL={json.dumps(tv_symbol)};\n" + _technical_script()
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
""" + _hover_script()


def _hover_script() -> str:
    """Crosshair read-out for charts whose renderer exported its plotted series.

    Everything is measured off the rendered image box, so the marks stay aligned
    at any width; charts without data, and printing, are untouched.
    """
    return r"""
document.querySelectorAll('.chart-interactive').forEach(function(box){
  var tag=box.querySelector('script.ch-data'); if(!tag) return;
  var data; try{data=JSON.parse(tag.textContent);}catch(e){return;}
  var points=(data&&data.points)||[]; if(!points.length) return;
  var frame=data.frame, names=data.series||[];
  var image=box.querySelector('img'), cross=box.querySelector('.ch-cross');
  var dot=box.querySelector('.ch-dot'), readout=box.querySelector('.ch-readout');
  function hide(){cross.style.display='none';dot.style.display='none';readout.style.display='none';}
  function move(event){
    var rect=image.getBoundingClientRect(); if(!rect.width) return;
    var left=frame.left*rect.width, right=frame.right*rect.width;
    var top=frame.top*rect.height, bottom=frame.bottom*rect.height;
    var x=event.clientX-rect.left;
    if(x<left||x>right){hide();return;}
    var wanted=(x-left)/(right-left), pick=0, best=Infinity;
    for(var i=0;i<points.length;i++){
      var gap=Math.abs(points[i].x-wanted);
      if(gap<best){best=gap;pick=i;}
    }
    var point=points[pick], px=left+point.x*(right-left);
    cross.style.display='block';cross.style.left=px+'px';
    cross.style.top=top+'px';cross.style.height=(bottom-top)+'px';
    if(point.y===null||point.y===undefined){dot.style.display='none';}
    else{dot.style.display='block';dot.style.left=px+'px';dot.style.top=(top+point.y*(bottom-top))+'px';}
    var rows='';
    for(var s=0;s<names.length;s++){
      rows+='<div class="ch-row"><span class="ch-k">'+names[s]+'</span><span class="ch-v">'+((point.values&&point.values[s])||'—')+'</span></div>';
    }
    readout.innerHTML='<div class="ch-date">'+point.label+'</div>'+rows;
    readout.style.display='block';
    var width=readout.offsetWidth, place=px+16;
    if(place+width>rect.width-4){place=px-width-16;}
    if(place<4){place=4;}
    readout.style.left=place+'px';
  }
  box.addEventListener('mousemove',move);
  box.addEventListener('mouseleave',hide);
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
(function(){
  var loaded=false,loading=false;
  function init(){
    if(typeof TradingView==='undefined')return;
    new TradingView.widget({
      autosize:true,symbol:TV_SYMBOL,interval:'D',timezone:'America/New_York',theme:'light',style:'1',
      locale:'en',toolbar_bg:'#F6F7F9',enable_publishing:false,hide_top_toolbar:false,hide_legend:false,
      container_id:'tvWidget'
    });
    loaded=true;
  }
  function load(){
    if(loaded)return;
    if(typeof TradingView!=='undefined'){init();return}
    if(loading)return;
    loading=true;
    var s=document.createElement('script');s.src='https://s3.tradingview.com/tv.js';s.onload=init;
    document.head.appendChild(s);
  }
  var tab=document.getElementById('evidenceTradingViewTab');if(tab)tab.addEventListener('click',load);
})();
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
  var H=238;
  function y(p){return (1-(p-lo)/(hi-lo))*H}
  var zTop=y(PLAN.entryHigh),zBottom=y(PLAN.entryLow);
  var h='<div class="lzone" style="top:'+(zTop/H*100)+'%;height:'+((zBottom-zTop)/H*100)+'%"></div>';
  // Declutter: labels for nearby price levels overlap when placed at their raw
  // linear position, so push each one down just enough to clear the label above it.
  var placed=levels.map(function(level){return {level:level,y:y(level.p)}}).sort(function(a,b){return a.y-b.y});
  var minGap=26;
  for(var i=1;i<placed.length;i++){
    if(placed[i].y-placed[i-1].y<minGap)placed[i].y=placed[i-1].y+minGap;
  }
  placed.forEach(function(item){
    var level=item.level;
    var tag=level.c==='now'?'<span class="lnow-chip">Now</span>':'<span class="ltag"><strong>'+level.l+'</strong></span>';
    h+='<div class="lrow '+level.c+'" style="top:'+(item.y/H*100)+'%"><span class="lprice num">'+money(level.p)+'</span><span class="lrule"></span>'+tag+'</div>';
  });
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
