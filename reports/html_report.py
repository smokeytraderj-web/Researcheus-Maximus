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
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from pathlib import Path

from core.assessments import condense_reasoning, fundamental_outlook, strip_conclusion_prefix, technical_setup
from core.conviction_checklist import (
    checklist_headlines,
    checklist_narrative,
    checklist_paragraphs,
    checklist_watch,
)
from core.models import ChartRecord, Rating, ResearchRequest, ResearchResult
from research import house_views


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
.reason-index{font-family:'Source Serif 4',Georgia,serif;font-size:24px;line-height:1;color:var(--ink);opacity:.4;font-weight:600}
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
/* The tone classes carry a fill for inline chips; the hero wants the colour only. */
/* Confidence sits with the sources rather than under the rating: it qualifies
   the evidence, and under the rating it read as a second verdict competing with
   the one above it. */
.conf-line{font-size:12px;color:var(--muted);margin:0 0 10px}
.conf-line b{color:var(--ink);font-weight:600}
.pos-bar{display:flex;flex-wrap:wrap;gap:0;background:var(--panel);border-radius:7px;margin-bottom:22px;overflow:hidden}
.pos-cell{flex:1 1 180px;padding:13px 18px;border-right:1px solid var(--line)}
.pos-cell:last-child{border-right:none}
.pos-k{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600;margin-bottom:5px}
.pos-v{font-size:14.5px;font-weight:600;color:var(--ink);font-family:'IBM Plex Mono',monospace}
.pos-v.bull{color:var(--bull)}.pos-v.bear{color:var(--bear)}.pos-v.neutral{color:var(--neutral)}
/* Technical page one states the plan's four figures in the same language as the
   metrics strip beneath them, so the page carries one continuous data block
   rather than two competing treatments of the same kind of information. The two
   strips share a single 2px rule: the second drops its own top border and sits
   flush under the first. */
/* Sections on the Technical page need more air between them than the template's
   36px. The page carries four short, self-contained sections in a row -- the
   read, the reasoning, the data, the plan -- and at the default spacing they ran
   together into one column with rules in it, so the eye could not tell where one
   finished and the next began. Screen only: print separates them by page. */
.tech-report section{margin-top:60px}
.tech-report section:first-of-type{margin-top:36px}
.tech-report .sec-head{padding-bottom:10px;margin-bottom:22px}
/* The plan's levels and the market figures share a visual language but are not
   the same kind of thing: one is a proposed course of action, the other is where
   things stand. Run together as one eight-cell block they read as a single
   table, so each keeps its own label and its own rule. */
.data-group + .data-group{margin-top:26px}
.data-k{font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);
  font-weight:600;margin-bottom:7px}
.plan-line{margin-top:0}
.tl-n{font-size:12.5px;margin-top:3px}
.data-group .topline{margin-top:0}
.plan-line .tl-v{font-size:19px}
/* An entry zone is two prices and a dash -- it wrapped mid-range at strip size. */
.plan-line .tl-v.range{font-size:16.5px}
.hz-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border-top:2px solid var(--ink);border-bottom:1px solid var(--line)}
.hz{padding:13px 20px;border-left:1px solid var(--line-2)}
.hz:first-child{border-left:0;padding-left:0}
.hz-k{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:600}
.hz-v{font-family:'Source Serif 4',serif;font-size:26px;font-weight:700;line-height:1.1;margin-top:6px}
.hz-v.v-bull{color:var(--bull)}.hz-v.v-bear{color:var(--bear)}.hz-v.v-neu{color:var(--neutral)}
.hz-w{font-size:11px;color:var(--muted);margin-top:6px;font-family:'IBM Plex Mono',monospace}
.hz-n{font-size:12px;color:var(--body);margin-top:8px;line-height:1.45}
.hz-note{font-size:12.5px;color:var(--body);line-height:1.6;margin-top:14px;max-width:70ch}
.hz-agree{font-size:12.5px;color:var(--body);line-height:1.6;margin:16px 0 0}
.hz-agree b{color:var(--ink)}
.pr{width:100%;border-collapse:collapse;font-size:13px;margin-top:4px}
.pr th{text-align:left;font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600;padding:0 10px 7px 0;border-bottom:1px solid var(--line)}
.pr th.r,.pr td.r{text-align:right;padding-right:0}
.pr td{padding:8px 10px 8px 0;border-bottom:1px solid var(--line-2);color:var(--body)}
.pr .pr-t{font-family:'IBM Plex Mono',monospace;font-weight:600;color:var(--ink);width:64px}
.pr .pos{color:var(--bull)}.pr .neg{color:var(--bear)}
.pr-self td{background:var(--panel);font-weight:600;color:var(--ink)}
.pr-lede{font-size:13.5px;color:var(--ink);margin:0 0 12px}
.pr-med{font-size:12px;color:var(--muted);margin-top:9px}
.pr-rule{font-size:11.5px;color:var(--muted);line-height:1.55;margin-top:10px;max-width:78ch}
.pr-notes{margin:8px 0 0;padding-left:16px;font-size:11.5px;color:var(--muted);line-height:1.5}
.af-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border-top:2px solid var(--ink);border-bottom:1px solid var(--line)}
.af{padding:14px 18px;border-left:1px solid var(--line-2)}
.af:first-child{border-left:0;padding-left:0}
.af-k{font-size:9.5px;letter-spacing:.11em;text-transform:uppercase;color:var(--muted);font-weight:600}
.af-v{font-size:22px;font-weight:600;color:var(--ink);margin-top:6px}
.af-n{font-size:11.5px;color:var(--muted);margin-top:6px;line-height:1.45}
.af-note{font-size:12px;color:var(--body);line-height:1.55;margin-top:12px;max-width:76ch}
.house-line{margin-top:0}
.hv-profiles{display:grid;grid-template-columns:repeat(2,1fr);gap:0 34px;margin-top:18px}
.hv-list{display:grid;gap:14px}
.hv{border:1px solid var(--line);border-radius:8px;padding:14px 16px;background:#fff}
.hv.stale{border-left:3px solid var(--gold)}
.hv-top{display:flex;align-items:baseline;justify-content:space-between;gap:14px;margin-bottom:10px}
.hv-house{font-family:'Source Serif 4',serif;font-size:16px;font-weight:600;color:var(--ink)}
.hv-age{font-size:11.5px;color:var(--muted)}
.hv-figs{display:flex;flex-wrap:wrap;gap:0 34px;margin:0}
.hv-figs dt{font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600}
.hv-figs dd{margin:3px 0 0;font-size:16px;font-weight:600;color:var(--ink)}
.hv-h{font-size:11px;font-weight:400;color:var(--muted)}
.hv-ctx{font-size:11.5px;color:var(--muted);margin:-4px 0 11px}
.hv-flag{margin-top:11px;padding:9px 12px;background:#FDFAF2;border-left:2px solid var(--gold);font-size:11.5px;color:var(--neutral);line-height:1.5}
.hv-body{margin-top:13px}
.hv-profile{border-collapse:collapse;font-size:12px;width:100%;max-width:420px}
.hv-profile th{text-align:left;font-weight:500;color:var(--muted);padding:5px 10px 5px 0;border-bottom:1px solid var(--line-2)}
.hv-profile td{text-align:right;color:var(--ink);padding:5px 0;border-bottom:1px solid var(--line-2);font-weight:500}
.hv-k{font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600;margin-bottom:6px}
.hv-note-block{margin-top:14px;padding-top:13px;border-top:1px solid var(--line-2)}
.hv-note-title{font-family:'Source Serif 4',serif;font-size:14.5px;font-weight:600;color:var(--ink);line-height:1.35}
.hv-note-sum{font-size:12.5px;line-height:1.6;color:var(--body);margin:7px 0 0}
.hv-note-by{font-size:11px;color:var(--muted);margin-top:7px}
.hv-doc{margin-top:10px;font-size:11.5px;color:var(--muted)}
.hv-stale{margin-top:9px;font-size:11.5px;color:#8A6D1F}
.hv-note{font-size:11.5px;color:var(--muted);line-height:1.5;margin-top:12px}
.action p{font-size:12.5px;line-height:1.5;color:var(--body);margin:0}
.why-block{margin-top:20px;padding:20px 22px;border-left:3px solid var(--gold);background:var(--panel);border-radius:0 4px 4px 0}
.why-block .why-k{font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;font-weight:600;margin-bottom:9px}
.why-block p{font-size:15.5px;color:var(--body);line-height:1.68;margin:0}
.why-block p + p{margin-top:13px}
/* The deterministic checklist reading leads, because it is the part tied
   directly to the five boxes above it; the analyst prose follows. */
.why-block .why-checks{color:var(--ink)}
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
.cc-card{margin-top:16px;margin-bottom:24px}
/* Price-scenario panel (Deep Technical only). The previous version showed the
   same thing three ways at once -- a slider, a dashed level ladder and a side
   column of figures -- so nothing led. This states the tested price once, offers
   the planned levels as discrete choices, which is how the decision is actually
   framed, and puts the consequences in the report's own horizontal figure strip.
   Wording here deliberately avoids the panel's display name: this stylesheet is
   shared with the General brief, which must not mention a control it lacks. */
.scn{border:1px solid var(--line);background:var(--panel);border-radius:10px;padding:22px 24px 20px}
.scn-head{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;flex-wrap:wrap}
.scn-k{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:600}
.scn-price{font-family:'Source Serif 4',Georgia,serif;font-size:40px;font-weight:700;color:var(--ink);line-height:1.05;margin-top:5px}
.scn-delta{font-size:11.5px;color:var(--muted);margin-top:3px}
.scn-chips{display:flex;flex-wrap:wrap;gap:7px;justify-content:flex-end;max-width:430px}
.scn-chip{display:flex;flex-direction:column;align-items:flex-start;gap:2px;cursor:pointer;
  background:#fff;border:1px solid var(--line);border-radius:8px;padding:7px 11px;
  font:600 10px/1.1 'IBM Plex Sans',sans-serif;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
  transition:border-color .13s,color .13s,box-shadow .13s}
.scn-chip span{font-size:12.5px;letter-spacing:0;text-transform:none;color:var(--ink);font-weight:600}
.scn-chip:hover{border-color:var(--ink);color:var(--ink)}
.scn-chip[aria-pressed="true"]{border-color:var(--ink);color:var(--ink);box-shadow:0 0 0 2px rgba(22,35,63,.10)}
/* The tester states what a price is worth against each planned level, rather
   than drawing a picture of where it sits. Two pictures were tried here -- a
   profit-and-loss curve and a zone rail -- and both spent the panel's whole
   area re-drawing four prices the reader can already see, while the question
   being asked ("what is this worth to me") stayed in small type underneath.
   The rows are the answer, so the rows are the panel. Rendered server-side at
   today's price so print and a JS-less reader get a complete table; script
   rewrites two columns as the slider moves. */
.scn-levels{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0 4px}
.scn-levels th{text-align:left;font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);font-weight:600;padding:0 12px 8px 0;border-bottom:1px solid var(--line)}
/* Right-aligned figures still need a gutter: with padding-right zeroed they ran
   straight into the next column -- "-$13,000Plan invalidated". */
.scn-levels th.r,.scn-levels td.r{text-align:right;padding-right:22px}
.scn-levels th:last-child,.scn-levels td:last-child{padding-right:0}
.scn-levels .mean{color:var(--muted);font-size:12px}
.scn-levels td{padding:9px 12px 9px 0;border-bottom:1px solid var(--line-2);color:var(--body)}
.scn-levels .lv{font-weight:600;color:var(--ink)}
.scn-levels .num{font-family:'IBM Plex Mono',monospace}
.scn-levels tr.at td{background:var(--panel)}
.scn-levels tr.at .lv:before{content:"▸ ";color:var(--gold)}
.scn-levels .up{color:var(--bull)}.scn-levels .down{color:var(--bear)}
.scn-slider{margin-top:6px}
.scn-slider input[type=range]{width:100%;display:block}
.scn-ticks{display:flex;justify-content:space-between;font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--muted);margin-top:5px}
.scn .zone{margin-top:14px;padding:13px 15px;border:1px solid var(--line);border-left:3px solid var(--ink);
  background:#fff;border-radius:0 6px 6px 0;font-size:13.5px;line-height:1.5;color:var(--ink-2)}
.scn-out{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--line);
  border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-top:16px}
.scn-cell{background:#fff;padding:12px 14px}
.scn-ck{font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600}
.scn-cv{font-size:19px;font-weight:600;color:var(--ink);margin-top:5px}
.scn-note{font-size:10.5px;color:var(--muted);margin-top:11px;line-height:1.45}
@media (max-width:820px){.scn-out{grid-template-columns:repeat(2,minmax(0,1fr))}.scn-chips{justify-content:flex-start;max-width:none}}
.cc-top{display:flex;align-items:center;gap:16px;padding:0 1px 16px}
.cc-score{font-family:'Source Serif 4',Georgia,serif;font-size:34px;font-weight:700;color:var(--ink);line-height:1;white-space:nowrap}
.cc-score.perfect{color:var(--bull)}
.cc-toptext{flex:1}
.cc-title{font-size:15px;font-weight:600;color:var(--ink)}
.cc-sub{font-size:12.5px;color:var(--muted);margin-top:3px;line-height:1.45}
.cc-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:15px}
/* Each criterion is its own elevated card -- "floating" above the page rather
   than a row in a flat table, so the five read as independent, weighable checks.
   This is the report's most-scanned reasoning, so the cards are sized to command
   real screen space, not tucked away as a compact aside. */
.cc-col{background:#fff;border:1px solid var(--line);border-radius:12px;padding:30px 22px 28px;min-height:236px;position:relative;box-shadow:0 3px 10px rgba(22,35,63,.09);transition:box-shadow .15s ease}
.cc-col:hover{box-shadow:0 7px 18px rgba(22,35,63,.15)}
.cc-col-top{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.cc-box{flex:none;width:30px;height:30px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:17px;font-weight:700}
.cc-box.pass{background:var(--bull);color:#fff}
.cc-box.fail{background:#fff;border:1.5px solid var(--line);color:transparent}
.cc-box.unconfirmed{background:var(--panel);border:1.5px solid var(--line);color:var(--muted);font-size:12px}
.cc-label{flex:1;font-size:16px;font-weight:600;color:var(--ink);line-height:1.25}
/* The info circle takes hover OR focus, so a click (which focuses a button) works
   identically to a hover -- no JS needed, and it stays keyboard-reachable. */
.cc-info{flex:none;width:19px;height:19px;padding:0;border-radius:50%;border:1px solid var(--line);background:#fff;color:var(--muted);font:italic 700 11px/1 'Source Serif 4',Georgia,serif;display:flex;align-items:center;justify-content:center;cursor:help}
.cc-info:hover,.cc-info:focus{background:var(--ink);border-color:var(--ink);color:#fff;outline:none}
.cc-tip{position:absolute;z-index:20;top:100%;left:22px;margin-top:8px;width:210px;background:var(--ink);color:#fff;font-size:11.5px;line-height:1.5;padding:11px 12px;border-radius:7px;box-shadow:0 4px 14px rgba(22,35,63,.22);visibility:hidden;opacity:0;transition:opacity .12s ease}
.cc-col:first-child .cc-tip{left:0}
.cc-col:last-child .cc-tip{left:auto;right:0}
.cc-info:hover+.cc-tip,.cc-info:focus+.cc-tip{visibility:visible;opacity:1}
.cc-detail{font-size:13.5px;color:var(--body);line-height:1.55}
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
@media(max-width:900px){.reason-row{grid-template-columns:34px minmax(0,1fr)}.reason-row.stance{grid-template-columns:104px minmax(0,1fr)}.reason-copy{grid-column:2}.chart-image{max-height:none}.grid3{grid-template-columns:1fr}.cc-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media print{.chart-image{max-height:178mm}.btn,.rail-tools{display:none!important}.reason-row{break-inside:avoid}.page-view[hidden]{display:block!important}.page-view:not(:last-child){break-after:page}
/* The @page margin supplies the printed gutter; the screen one would double it. */
.shell{padding-left:0;padding-right:0}
/* A printed Letter page is ~816px wide, which trips the approved template's
   900px mobile breakpoint -- so print was silently laying both reports out as a
   phone: a stacked masthead, half-width metric strips, and a Conviction
   Checklist in two columns with an orphan fifth card, where the spec requires
   one column per criterion. Restore the intended desktop grids for print. These
   are shared because both reports were affected; the .general-brief copies below
   predate the fix and only ever covered that report. */
.head{flex-direction:row}
.rating{text-align:right}
.topline{grid-template-columns:repeat(4,1fr)}
.cc-grid{grid-template-columns:repeat(5,minmax(0,1fr))}
.grid3{grid-template-columns:repeat(3,1fr)}
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
.general-brief .cc-grid{grid-template-columns:repeat(5,minmax(0,1fr))}
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
.general-brief .question-line{font-size:14.5px;margin-bottom:11px}
.general-brief .answer-card{padding:11px 14px}
.general-brief .answer{font-size:14px;line-height:1.45}
.general-brief .why-block{margin-top:12px;padding:11px 14px}
.general-brief .why-block p{font-size:11.5px;line-height:1.5}
.general-brief .cc-card{margin-top:12px;margin-bottom:14px}
.general-brief .cc-top{padding:0 1px 11px}
.general-brief .cc-score{font-size:21px}
.general-brief .cc-grid{gap:10px}
/* The screen cards are deliberately oversized (min-height, generous padding) to
   command real screen space; print has no such budget, so reset both here rather
   than let the enlarged base bleed into the page count. */
.general-brief .cc-col{padding:11px 12px 10px;min-height:0}
/* The Technical report prints the checklist too, and at screen size its cards
   are ~62mm tall -- enough to be pushed to a page of their own, stranding the
   call above them on a near-empty one. Compact them the same way the brief
   does, and keep the call, the boxes and the reasoning on one page. */
.tech-report .cc-card{margin-top:12px;margin-bottom:12px;break-before:avoid}
.tech-report .cc-top{padding:0 1px 10px}
.tech-report .cc-score{font-size:22px}
.tech-report .cc-grid{gap:9px}
.tech-report .cc-col{padding:10px 11px 9px;min-height:0;box-shadow:none}
.tech-report .cc-col-top{gap:6px;margin-bottom:6px}
.tech-report .cc-box{width:14px;height:14px;border-radius:4px;font-size:10px}
.tech-report .cc-label{font-size:9.5px}
.tech-report .cc-detail{font-size:9px}
.tech-report .cc-explain{font-size:8px}
.tech-report #call{break-inside:auto;margin-top:14px}
/* The screen's 60px between sections is generous on paper, where each section
   already opens its own page or sits under its own rule. */
.tech-report section{margin-top:22px}
.tech-report section:first-of-type{margin-top:14px}
/* Deep Technical prints one major section per page. Each is a distinct piece of
   the argument -- the read, the plan, one chart, the fundamentals, the sources --
   and running two of them together made it ambiguous where one ended and the
   next began. Sections too thin to hold a page alone are paired with the section
   they belong to rather than given a near-empty page, which the spec forbids:
   the checklist keeps its reasoning, the data strip keeps the plan it describes. */
/* The read and Why share page one, because neither fills a page alone and the
   two are one thought: the checklist and the reasoning that reads it. Given a
   page each they came out roughly half empty, which looks unfinished rather than
   clean. That pairing is the *absence* of a rule, not break-before:avoid -- avoid
   welds a section to what precedes it, which made the masthead, checklist and
   reasoning one unbreakable block that no longer fit, stranding the masthead
   alone on page one.

   Only the plan is pinned to a page start. Pinning the data strip instead gives
   the same result on a long report but forces the strip off page one even when
   it would have fitted, so the rule that guarantees the plan opens cleanly is
   the one to keep. */
.tech-report #plan{break-before:page}
/* Not #fundamentals: it already opens a page-view, so a break before it only
   orphans the running strip above it onto a page of its own. */
.tech-report #sources{break-before:page}
/* One chart per page -- but not the first, which belongs with the Charts heading
   rather than leaving it stranded on a page of its own. */
.tech-report .evidence-panel + .evidence-panel{break-before:page}
/* The tabs are a screen control. Print expands every panel, so they navigate
   nothing and only cost space at the head of the charts page. */
.tech-report .evidence-tabs{display:none!important}
/* Likewise the tester's slider and preset chips. Its chart, action zone and
   outcome figures are static conclusions and stay. */
.tech-report .scn-chips,.tech-report .scn-slider{display:none!important}
/* The checklist card cannot split (.cc-card is break-inside:avoid), so any size
   that stops it fitting under the masthead does not shrink page one -- it moves
   the whole card to page two and leaves the masthead alone on a page. Sizes here
   are held at what fits beneath the masthead alongside the reasoning. */
/* The ladder and the plan cards are single figures; splitting one across a page
   boundary produces a page that opens on "2.00x" with no heading above it. */
.tech-report .af-grid,.tech-report .plan{break-inside:avoid}
.tech-report #plan .sec-head{break-after:avoid}
.general-brief .cc-col-top{gap:6px;margin-bottom:7px}
.general-brief .cc-box{width:14px;height:14px;border-radius:4px;font-size:10px}
.general-brief .cc-label{font-size:9.5px}
.general-brief .cc-detail{font-size:9px}
.general-brief .cc-explain{font-size:8px}
.general-brief .reason-list{margin-top:12px!important}
/* When a genuine horizon split pushes the brief to a fourth page, the break
   lands between whole blocks rather than through the middle of the reason
   list, which otherwise opened page two on a stranded half-row. */
.general-brief .reason-list{break-inside:avoid}
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
/* The brief is a pinned three pages. The screen block -- a section head, three
   tall cells and an explanatory line -- costs most of a fourth, so print keeps
   the three conclusions and drops the furniture around them. */
.general-brief #horizons{margin-top:10px;break-inside:avoid}
.general-brief #horizons .sec-head{display:none}
.general-brief .hz-note{display:none}
.general-brief .hz-grid{border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.general-brief .hz{padding:5px 12px}
.general-brief .hz-k{font-size:8px}
.general-brief .hz-v{font-size:14px;margin-top:2px}
.general-brief .hz-w{font-size:8px;margin-top:2px}
.general-brief #sources{margin-top:11px}
.general-brief #sources .sec-head{break-after:avoid}
.general-brief .sources{font-size:10px}
.general-brief .conf-line{font-size:10px;margin-bottom:6px}
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
    css = _approved_css(css_reference) + _DYNAMIC_CSS + _DECK_CSS + extra_css
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400&amp;family=EB+Garamond:ital,wght@0,400;0,600;0,700;1,400&amp;family=IBM+Plex+Sans:wght@400;500;600&amp;family=IBM+Plex+Mono:wght@400;500;600&amp;display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>{body}<script>{script}</script></body>
</html>"""


def _masthead(result: ResearchResult, document_type: str, subline: str = "") -> str:
    """The report header, and the only place the rating is stated.

    It used to be given twice at the same size -- here, and again in a centred
    block a few centimetres below -- which made the top of the page read as two
    competing verdicts. The subline is the caller's, because the old one
    ("Bullish setup - Positive fundamentals") repeated the metrics strip word
    for word.
    """
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
    {f'<div class="rating-sub">{escape(subline)}</div>' if subline else ''}
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


def _masthead_subline(result: ResearchResult) -> str:
    """What the masthead says beneath the rating.

    Normally the horizon. For an All Horizons request where the three conclusions
    differ, the split itself -- so the single rating above it is read as the
    summary it is, and not as the whole answer.
    """
    views = getattr(result, "horizon_views", ())
    if views and len({view.rating.value for view in views}) > 1:
        return " · ".join(
            f"{view.horizon.value.replace(' Term', '')} {view.rating.value}" for view in views
        )
    return f"{result.horizon.value} view"


def _horizon_views_html(result: ResearchResult) -> str:
    """The three horizon conclusions, stated separately.

    Shown for an All Horizons request, directly under the masthead, because the
    disagreement between them is the answer to that request. Blended into one
    rating it disappears -- and the case where it disappears is the case a
    reader most needs: a business the fundamental work rates well while the
    chart is falling.
    """
    views = getattr(result, "horizon_views", ())
    if not views:
        return ""
    ratings = {view.rating.value for view in views}
    # Agreement needs one line, not three columns of the same word. The brief is
    # a pinned three pages, and a block that says nothing new costs one of them.
    if len(ratings) == 1:
        return (
            '<p class="hz-agree">Short, medium and long term all read '
            f'<b>{escape(views[0].rating.value)}</b> — the horizons agree, so the rating above '
            "holds across all three.</p>"
        )
    # Only the weighting differs between the three, so the per-horizon rationale
    # said the same two ratings three times. What changes is stated once beneath.
    cells = "".join(
        f'<div class="hz"><div class="hz-k">{escape(view.horizon.value)}</div>'
        f'<div class="hz-v {_tone(view.rating)[0]}">{escape(view.rating.value)}</div>'
        f'<div class="hz-w">{view.technical_weight}% technical · '
        f'{view.fundamental_weight}% fundamental</div></div>'
        for view in views
    )
    technical = views[0].rating  # any horizon reports the same component ratings
    return (
        '<section id="horizons"><div class="sec-head"><h2>By horizon</h2>'
        '<span class="verdict v-neu">The horizons disagree</span></div>'
        f'<div class="hz-grid">{cells}</div>'
        '<p class="hz-note">Each horizon weighs the same two workstreams differently, so a name can '
        "be one thing to hold for a year and another to trade this month. A single blended rating "
        "would hide that.</p></section>"
    )


def _peer_group_html(result: ResearchResult) -> str:
    """The industry cohort, and where this security sits in it.

    Evidence the broad benchmark cannot give: lagging the market and lagging
    your own industry are different findings, and only the second says anything
    about the company. The selection rule is printed with the table, because a
    peer comparison is only as good as its peer set and a reader has to be able
    to judge it.
    """
    group = getattr(result, "peer_group", None)
    if group is None or not group.usable:
        return ""
    rows = "".join(
        f'<tr><td class="pr-t">{escape(m.ticker)}</td><td>{escape(m.name)}</td>'
        f'<td class="num r {"pos" if (m.return_pct or 0) >= 0 else "neg"}">{m.return_pct:+.1%}</td>'
        f'<td class="num r">{f"{m.forward_pe:.1f}x" if m.forward_pe else "&mdash;"}</td></tr>'
        for m in sorted(group.members, key=lambda m: -(m.return_pct if m.return_pct is not None else -9))
    )
    subject = (
        f'<tr class="pr-self"><td class="pr-t">{escape(result.identity.ticker)}</td>'
        f'<td>{escape(result.identity.company_name)}</td>'
        f'<td class="num r {"pos" if (group.subject_return_pct or 0) >= 0 else "neg"}">'
        f'{group.subject_return_pct:+.1%}</td><td class="num r">&mdash;</td></tr>'
        if group.subject_return_pct is not None else ""
    )
    median = group.median_return()
    standing = group.standing()
    notes = "".join(f"<li>{escape(note)}</li>" for note in group.limitations)
    return (
        '<section id="peers"><div class="sec-head"><h2>Against its industry</h2>'
        f'<span class="verdict v-neu">{escape(group.industry)}</span></div>'
        + (f'<p class="pr-lede">{escape(result.identity.ticker)} ranks {escape(standing)}.</p>'
           if standing else "")
        + '<table class="pr"><thead><tr><th></th><th>Company</th>'
        f'<th class="r">Return</th><th class="r">Forward P/E</th></tr></thead>'
        f"<tbody>{subject}{rows}</tbody></table>"
        + (f'<p class="pr-med">Group median {median:+.1%} over {escape(group.window_label)}.</p>'
           if median is not None else "")
        + f'<p class="pr-rule">{escape(group.selection_rule)} Returns are measured over identical '
        "dates. Forward multiples come from the data provider already normalised; fiscal periods "
        "across an industry do not necessarily align.</p>"
        + (f'<ul class="pr-notes">{notes}</ul>' if notes else "")
        + "</section>"
    )


def _house_strip(result: ResearchResult) -> str:
    """Each house's call, in the same strip language as the plan and the market.

    Woven into the data block rather than given a section of its own: a house's
    rating is one more figure a reader weighs against the others, and putting it
    on a page by itself made it look like a second verdict. Every cell names the
    house, so attribution travels with the number wherever it is read.
    """
    views = getattr(result, "house_views", ())
    if not views:
        return ""
    cells = []
    flags = []
    for view in views:
        age, stale = house_views.freshness(view, result.as_of)
        if view.equity_rating:
            cells.append(
                f'<div class="tl"><div class="tl-k">{escape(view.house)} rating</div>'
                f'<div class="tl-v">{escape(view.equity_rating)}</div>'
                f'<div class="tl-n">{escape(age)}</div></div>'
            )
        if view.price_target is not None:
            note = f"{view.upside_pct:+.1%} on their price" if view.upside_pct is not None else escape(view.target_horizon)
            cells.append(
                f'<div class="tl"><div class="tl-k">{escape(view.house)} target</div>'
                f'<div class="tl-v num">{_money(view.price_target)}</div>'
                f'<div class="tl-n">{note}</div></div>'
            )
        if view.credit_rating:
            scale = escape(view.credit_rating_scale) or "Credit view"
            cells.append(
                f'<div class="tl"><div class="tl-k">{escape(view.house)} credit</div>'
                f'<div class="tl-v">{escape(view.credit_rating)}</div>'
                f'<div class="tl-n">{scale}</div></div>'
            )
        conflict = house_views.price_disagreement(view, result.current_price)
        if conflict:
            flags.append(conflict)
        if stale:
            flags.append(
                f"{view.house}'s view was {age}; confirm it still stands before relying on it."
            )
    if not cells:
        return ""
    warning = (
        f'<div class="hv-flag">{escape(" ".join(flags))}</div>' if flags else ""
    )
    return (
        '<div class="data-group">'
        "<div class=\"data-k\">Research houses &mdash; each on its own scale, not this report&rsquo;s</div>"
        f'<div class="topline house-line">{"".join(cells)}</div>{warning}</div>'
    )


def _house_profile_html(result: ResearchResult) -> str:
    """The house's own profile figures, in the data section with the rest."""
    blocks = []
    for view in getattr(result, "house_views", ()):
        if not view.profile:
            continue
        rows = "".join(
            f'<div class="dr"><dt>{escape(str(label))}</dt><dd>{escape(str(value))}</dd></div>'
            for label, value in view.profile
        )
        context = " · ".join(escape(p) for p in (view.sector, view.region) if p)
        blocks.append(
            f'<div class="metric-group"><div class="dl-h">{escape(view.house)} profile</div>'
            f'<dl class="dl">{rows}</dl>'
            + (f'<div class="hv-ctx">{context}</div>' if context else "")
            + "</div>"
        )
    return f'<div class="hv-profiles">{"".join(blocks)}</div>' if blocks else ""


def _house_notes_html(result: ResearchResult) -> str:
    """The latest note each house published, as a citation and a summary."""
    blocks = []
    for view in getattr(result, "house_views", ()):
        note = view.latest_note
        if note is None:
            continue
        byline = " · ".join(
            escape(part) for part in (note.kind, note.authors, note.published) if part
        )
        blocks.append(
            f'<div class="hv-note-block"><div class="hv-k">{escape(view.house)} &mdash; latest note</div>'
            f'<div class="hv-note-title">{escape(note.title)}</div>'
            + (f'<p class="hv-note-sum">{escape(note.summary)}</p>' if note.summary else "")
            + (f'<div class="hv-note-by">{byline}</div>' if byline else "")
            + "</div>"
        )
    return "".join(blocks)


def _action_figures(plan, entry_mid: float, current_price: float) -> str:
    """The strategy as the numbers that decide it.

    This replaced a level ladder and a reward-to-risk bar. Both drew the same
    four prices the strip above them already stated, and the ladder in
    particular spent a third of the page redrawing a number line. What an
    advisor actually needs here is the arithmetic between those prices --
    what is risked, what is sought, and how far today's price sits from the
    zone -- so that is what is set out.
    """
    risk = max(0.0, entry_mid - plan.stop_level)
    reward = max(0.0, plan.first_target - entry_mid)
    to_entry = (entry_mid / current_price - 1) if current_price else 0.0
    cells = (
        ("Risked per share", f"&minus;{_money(risk)}",
         f"Entry midpoint down to the {_money(plan.stop_level)} stop"),
        ("Sought per share", f"+{_money(reward)}",
         f"Midpoint up to the {_money(plan.first_target)} first target"),
        ("Reward to risk", f"{plan.reward_risk:.2f}&times;",
         "Sought divided by risked, before costs"),
        ("Today versus entry", f"{to_entry:+.1%}",
         "Where price sits against the entry midpoint"),
    )
    figures = "".join(
        f'<div class="af"><div class="af-k">{label}</div>'
        f'<div class="af-v num">{value}</div><div class="af-n">{note}</div></div>'
        for label, value, note in cells
    )
    return (
        f'<div class="af-grid">{figures}</div>'
        f'<p class="af-note">A ${100_000:,.0f} position sized to this plan risks about '
        f'{_money(100_000 * (risk / entry_mid) if entry_mid else 0)} to the stop and seeks about '
        f'{_money(100_000 * (reward / entry_mid) if entry_mid else 0)} to the first target. '
        "Illustrative, before costs and slippage.</p>"
    )


def _plan_line(plan, entry_mid: float) -> str:
    """The plan's four figures, in the metrics strip's own language.

    These used to sit in a rounded grey bar with no supporting note, directly
    above a strip carrying the same kind of information in a different visual
    treatment -- two designs for one idea. Same cells, same rules, same
    typography; the two together read as one data block, and each figure now
    carries the note that says what it is measured against.
    """
    upside = (plan.first_target / entry_mid - 1.0) if entry_mid else 0.0
    return f"""
<div class="topline plan-line">
  <div class="tl"><div class="tl-k">Entry zone</div><div class="tl-v num range">{_money(plan.entry_low)} – {_money(plan.entry_high)}</div><div class="tl-n">Midpoint {_money(entry_mid)}</div></div>
  <div class="tl"><div class="tl-k">Stop</div><div class="tl-v num neg">{_money(plan.stop_level)}</div><div class="tl-n">{plan.stop_pct:.1%} below the midpoint</div></div>
  <div class="tl"><div class="tl-k">First target</div><div class="tl-v num pos">{_money(plan.first_target)}</div><div class="tl-n">{upside:.1%} above the midpoint</div></div>
  <div class="tl"><div class="tl-k">Reward / risk</div><div class="tl-v num">{plan.reward_risk:.2f}×</div><div class="tl-n">Upside per unit of risk</div></div>
</div>"""


def _stated_question(request: ResearchRequest, result: ResearchResult) -> str:
    """The question the report answers, in a form that reads as one.

    Someone who types "AMZN" has not asked anything, so printing "AMZN" under
    "Your question" told the reader nothing and looked like a field that had
    failed to fill. Anything too short to be a question -- a bare ticker, a
    company name -- becomes the question that entry actually implies, named
    against the resolved security so there is no ambiguity about which one.
    """
    asked = request.question.strip() or request.query.strip()
    if asked.endswith("?") or len(asked.split()) >= 4:
        return asked
    return (
        "What does the current evidence say about "
        f"{result.identity.company_name} ({result.identity.ticker})?"
    )


def _general_chart(result: ResearchResult) -> ChartRecord | None:
    if result.overview_chart is not None:
        return result.overview_chart
    if result.chart_path:
        return ChartRecord("Decision evidence", result.chart_path, result.technical.summary)
    return None


def _general_report(result: ResearchResult, request: ResearchRequest) -> str:
    tone_class, tone_name = _tone(result.lead_rating)
    question = _stated_question(request, result)
    answer = strip_conclusion_prefix(result.request_response or result.executive_summary)
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
    qualitative_summary = condense_reasoning(result.executive_summary) or answer
    # Deterministic reading of the five boxes, so the prose beneath them can
    # never drift from the score above them.
    # Two movements, rendered as two paragraphs: what the evidence agrees on,
    # then what the dissent costs. Run together they read as one wall.
    checks_paragraphs = checklist_paragraphs(
        result.conviction_checklist,
        rating=result.lead_rating.value,
        # Seeded by the security and the analysis date: the wording varies
        # between names and between days, and never within one note.
        seed=f"{result.identity.ticker}|{result.as_of}",
    )
    checks_narrative = " ".join(checks_paragraphs)
    checks_html = "".join(f'<p class="why-checks">{escape(part)}</p>' for part in checks_paragraphs)

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
  <div class="rail-tools"><button class="btn" id="deckBtn">Export slides</button><button class="btn" onclick="window.print()">Print / save PDF</button></div>
</nav>
<main class="page general-brief">
{_masthead(result, 'General Research', _masthead_subline(result))}
{_conviction_checklist_html(result.conviction_checklist)}
{_horizon_views_html(result)}
<section id="answer">
  <p class="question-line" style="margin-top:20px"><span>Your question</span>{escape(question)}</p>
  <div class="why-block">
    <div class="why-k">Why</div>
    {checks_html}
    <p>{escape(qualitative_summary)}</p>
  </div>
  <div class="reason-list" style="margin-top:20px">{reason_html}</div>
  {_topline(result)}
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
  {data_html}{_house_profile_html(result)}{_house_notes_html(result)}{_peer_group_html(result)}
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
  <p class="conf-line">Confidence in this view: <b>{escape(result.confidence.value)}</b></p>
  <div class="sources">{_source_html(result)}</div>
  <p class="disc">This material is informational and reflects conditions as of the stated time. Sources are believed reliable but are not guaranteed. Opinions and scenarios may change without notice. Investing involves risk, including possible loss of principal. Firm compliance review is required before client distribution.</p>
  <footer><span>Gottfried &amp; Somberg Wealth Management</span><span class="num">Prepared {_date_only(result.as_of)}</span></footer>
</section>
</main></div>
{_deck_html(result, request, question, checks_narrative, qualitative_summary, (("Evidence", _general_chart(result)),))}"""
    return _document(
        f"{result.identity.ticker} General Research — Technical Analyst Agent",
        "general_research_base.html",
        body,
        _navigation_script() + _deck_script(),
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


def _scenario_levels(plan, current: float, entry_mid: float) -> tuple[str, str]:
    """What a tested price is worth against each planned level.

    Two pictures were tried in this panel -- a profit-and-loss curve and a zone
    rail -- and both had the same fault: they used the panel's whole area to
    redraw four prices already stated above, leaving the question actually being
    asked ("what is this worth to me") in small type underneath. The rows are
    the answer, so the rows are the panel.

    Built server-side at today's price, so print and a reader with no JavaScript
    get a complete, correct table. Script rewrites two columns as the slider
    moves; nothing appears or disappears.
    """
    levels = (
        ("Stop", plan.stop_level, "Plan invalidated"),
        ("Entry zone low", plan.entry_low, "Lower edge of the zone"),
        ("Entry midpoint", entry_mid, "Sizing reference"),
        ("Entry zone high", plan.entry_high, "Upper edge of the zone"),
        ("First target", plan.first_target, "Review risk and sizing"),
        ("Second target", plan.second_target, "Re-underwrite"),
    )
    rows = []
    for label, price, meaning in levels:
        gap = (price / current - 1) if current else 0.0
        rows.append(
            f'<tr data-level="{price!r}"><td class="lv">{label}</td>'
            f'<td class="num">{_money(price)}</td>'
            f'<td class="num r gap {"up" if gap >= 0 else "down"}">{gap:+.1%}</td>'
            f'<td class="num r pnl">{_signed_money(100_000 * gap)}</td>'
            f'<td class="mean">{meaning}</td></tr>'
        )
    table = (
        '<table class="scn-levels"><thead><tr><th>Level</th><th>Price</th>'
        '<th class="r">From test price</th><th class="r">On $100,000</th>'
        '<th>If reached</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )
    geometry = json.dumps({"notional": 100_000.0}, separators=(",", ":"))
    return table, geometry


def _signed_money(value: float) -> str:
    """A P&L figure. Cents are noise on a $100,000 position, so they are dropped."""
    if abs(value) < 0.5:
        return "$0"
    return f"{'−' if value < 0 else '+'}${abs(value):,.0f}"


def _technical_report(result: ResearchResult, request: ResearchRequest) -> str:
    plan = result.technical_plan
    if plan is None:
        return _general_report(result, request)
    tone_class, _ = _tone(result.lead_rating)
    # Same deterministic reading of the five boxes the General brief carries, so
    # both reports explain the rating against the same evidence in the same voice.
    # Two movements, rendered as two paragraphs: what the evidence agrees on,
    # then what the dissent costs. Run together they read as one wall.
    checks_paragraphs = checklist_paragraphs(
        result.conviction_checklist,
        rating=result.lead_rating.value,
        # Seeded by the security and the analysis date: the wording varies
        # between names and between days, and never within one note.
        seed=f"{result.identity.ticker}|{result.as_of}",
    )
    checks_narrative = " ".join(checks_paragraphs)
    checks_html = "".join(f'<p class="why-checks">{escape(part)}</p>' for part in checks_paragraphs)
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
    # Evidence for the checklist's Revisions criterion. Appears only when the
    # estimate history exists -- never as an empty panel to keep a tab count.
    revision_chart = _chart_by_title(result, "estimate revisions")
    if revision_chart is not None:
        charts += (
            (
                "Estimate revisions",
                "evidenceRevisions",
                revision_chart,
                (("var(--bull)", "Estimates raised"), ("var(--bear)", "Estimates cut")),
            ),
        )
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
    # The deck shows the same evidence in the same order as the Charts page, so
    # a slide never presents a view the report does not carry, and never omits
    # one it does.
    deck_charts = tuple((label, chart) for label, _panel, chart, _legend in charts)
    # The count is derived, not written down: tabs appear only when their
    # evidence was produced, so a hardcoded "six views" goes stale the moment a
    # security has no volume profile or no estimate history.
    _words = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight"}
    chart_count_label = f"{_words.get(len(charts), len(charts))} views, one panel"
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
    # Discrete, meaningful levels first: an advisor thinks in "what if it hits the
    # stop", not in dragging a slider until a number looks right. The slider stays
    # for values between them, and the outcome strip reuses the report's own
    # horizontal figure language instead of a competing side column.
    chips = "".join(
        f'<button type="button" class="scn-chip" data-price="{value!r}">{label}<span class="num">{_money(value)}</span></button>'
        for label, value in (
            ("Stop", plan.stop_level),
            ("Entry", entry_mid),
            ("Today", result.current_price),
            ("Target 1", plan.first_target),
            ("Target 2", plan.second_target),
        )
    )
    scenario_graph, scenario_geometry = _scenario_levels(plan, result.current_price, entry_mid)
    scenario_panel = f'''<div class="evidence-panel" id="evidenceScenario" role="tabpanel" aria-labelledby="evidenceScenarioTab" hidden><div class="scn">
  <div class="scn-head">
    <div><div class="scn-k">Test price</div><div class="scn-price num" id="sPrice">{_money(result.current_price)}</div><div class="scn-delta" id="sDelta">At today\'s price</div></div>
    <div class="scn-chips" role="group" aria-label="Jump to a planned level">{chips}</div>
  </div>
  {scenario_graph}
  <div class="scn-slider"><input type="range" id="slider" min="{slider_min:.2f}" max="{slider_max:.2f}" step="0.01" value="{result.current_price:.2f}" aria-label="Test a future price"><div class="scn-ticks"><span>{_money(slider_min)}</span><span>{_money(slider_max)}</span></div></div>
  <div class="zone" id="zone" aria-live="polite"></div>
  <div class="scn-out">
    <div class="scn-cell"><div class="scn-ck">Change from today</div><div class="scn-cv num" id="oChg">0.0%</div></div>
    <div class="scn-cell"><div class="scn-ck">Vs. entry midpoint</div><div class="scn-cv num" id="oEntry">&mdash;</div></div>
    <div class="scn-cell"><div class="scn-ck">Distance to stop</div><div class="scn-cv num" id="oStop">&mdash;</div></div>
    <div class="scn-cell"><div class="scn-ck">On a $100,000 position</div><div class="scn-cv num" id="oPnl">$0</div></div>
  </div>
  <div class="scn-note">Illustrative only. Excludes dividends, commissions, taxes and execution differences.</div>
</div></div>'''
    page2_strip = f'''<div class="p2-strip"><span class="p2-co">{escape(result.identity.company_name)} <span class="num">{escape(result.identity.ticker)}</span></span><span class="p2-px num">{_money(result.current_price)}</span><span class="verdict {tone_class}">{escape(result.lead_rating.value)}</span></div>'''
    body = f"""
<div class="shell">
<nav class="rail" aria-label="Report pages">
  <div class="rail-label">Technical Research</div>
  <a href="#page1" class="page-tab on" data-page="page1">1 — The call</a>
  <a href="#page2" class="page-tab" data-page="page2">2 — Charts</a>
  <a href="#page3" class="page-tab" data-page="page3">3 — Fundamentals</a>
  <div class="rail-tools"><button class="btn" id="advBtn" aria-pressed="false">Advisor detail: off</button><button class="btn" id="deckBtn">Export slides</button><button class="btn" onclick="window.print()">Print / save PDF</button></div>
</nav>
<main class="page tech-report">
<div class="page-view" id="page1">
{_masthead(result, 'Technical Research', f'Confidence {result.confidence.value} · {plan.stance}')}
<section id="call">
  <div class="sec-head"><h2>The read</h2></div>
  {_conviction_checklist_html(result.conviction_checklist)}
</section>
<section id="why">
  <div class="sec-head"><h2>Why</h2></div>
  <div class="why-block">
    {checks_html}
    <p>{escape(condense_reasoning(result.technical.summary))}</p>
  </div>
</section>
<section id="numbers">
  <div class="sec-head"><h2>The data</h2></div>
  <div class="data-group">
    <div class="data-k">Plan levels</div>
    {_plan_line(plan, entry_mid)}
  </div>
  <div class="data-group">
    <div class="data-k">Market and consensus</div>
    {_topline(result)}
  </div>
  {_house_strip(result)}{demo}
</section>
<section id="plan"><div class="sec-head"><h2>Action plan</h2><span class="verdict v-neu">{escape(plan.stance)}</span></div>
  {_action_figures(plan, entry_mid, result.current_price)}
  <div class="plan" style="margin-top:.9em"><div class="pc"><div class="pc-k">Entry zone</div><div class="pc-v">{_money(plan.entry_low)} – {_money(plan.entry_high)}</div><div class="pc-n">{escape(plan.confirmation)}</div></div><div class="pc"><div class="pc-k">Stop / invalidation</div><div class="pc-v" style="color:var(--bear)">{_money(plan.stop_level)}</div><div class="pc-n">{plan.stop_pct:.1%} below entry midpoint. {escape(plan.invalidation)}</div></div><div class="pc"><div class="pc-k">Targets</div><div class="pc-v" style="color:var(--bull)">{_money(plan.first_target)} / {_money(plan.second_target)}</div><div class="pc-n">Planning references, not guaranteed outcomes.</div></div></div>
  <details><summary>Why these levels, and what invalidates them</summary><div class="det-body"><ul>{reasons}</ul></div></details>
  {f'<details class="adv"><summary>Options / hedging reference <span class="adv-flag">Advisor</span></summary><div class="det-body"><p>{escape(plan.options_strategy)} — {escape(plan.options_structure)}</p><p>{escape(plan.options_risk)}</p></div></details>' if plan.options_strategy else ''}
</section>
</div>
<div class="page-view" id="page2" hidden>
{page2_strip}
<section id="charts"><div class="sec-head"><h2>Charts</h2><span class="verdict v-neu">{chart_count_label}</span></div><div class="evidence-tabs" role="tablist">{tabs}{tv_tab}{scenario_tab}</div>{panels}{tv_panel}{scenario_panel}</section>
</div>
<div class="page-view" id="page3" hidden>
{page2_strip}
<section id="fundamentals"><div class="sec-head"><h2>Fundamentals and data</h2><span class="verdict v-neu">{escape(fundamental_outlook(result.fundamental.rating))}</span></div><p class="lede">{escape(result.fundamental.summary)}</p>{_house_notes_html(result)}<details><summary>Signals, risks and rating triggers</summary><div class="det-body"><ul>{''.join(f'<li>{escape(item)}</li>' for item in (*result.fundamental.signals, *result.risks[:3], *result.change_conditions[:3]))}</ul></div></details><div class="grid3" style="margin-top:20px">{data_columns}</div>{_house_profile_html(result)}{_peer_group_html(result)}</section>
<section id="sources"><div class="sec-head"><h2>Sources</h2></div><div class="sources">{_source_html(result)}</div><p class="disc">This material is informational and reflects conditions as of the stated time. Sources are believed reliable but are not guaranteed. Scenarios may change without notice. Investing involves risk, including possible loss of principal. Options require separate suitability, approval and live-chain review. Firm compliance review is required before client distribution.</p><footer><span>Gottfried &amp; Somberg Wealth Management</span><span class="num">Prepared {_date_only(result.as_of)}</span></footer></section>
</div>
</main></div>
{_deck_html(result, request, _stated_question(request, result), checks_narrative, condense_reasoning(result.technical.summary), deck_charts)}"""
    # Every global the tester's script reads has to be defined here. SCN was
    # computed and never emitted, so the panel stopped responding to the slider
    # while a screenshot of its initial state still looked correct.
    script = (
        f"const PLAN={plan_json};\n"
        f"const SCN={scenario_geometry};\n"
        f"const TV_SYMBOL={json.dumps(tv_symbol)};\n"
        + _technical_script()
        + _deck_script()
    )
    return _document(
        f"{result.identity.ticker} Technical Research — Technical Analyst Agent",
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
// The tested price, not the slider, is the source of truth. A range input
// quantizes to its step, so setting it to a planned level lands a fraction of a
// cent short -- enough for "at the first target" to evaluate as "below the first
// target" and print the wrong action. The slider still drives this variable when
// dragged; it just no longer defines it.
var testPrice=null;
// The table is rendered server-side at today's price, so print and a JS-less
// reader get it complete. This rewrites only the two columns that depend on the
// tested price, and marks the row the price has reached.
function drawScenarioGraph(p){
  var rows=document.querySelectorAll('.scn-levels tbody tr');
  if(!rows.length||typeof SCN==='undefined') return;
  rows.forEach(function(row){
    var level=Number(row.dataset.level), gap=p?level/p-1:0;
    var gapCell=row.querySelector('.gap'), pnlCell=row.querySelector('.pnl');
    gapCell.textContent=pct(gap);
    gapCell.className='num r gap '+(gap>=0?'up':'down');
    pnlCell.textContent=Math.abs(gap)<1e-9?'$0':(gap>0?'+':'−')+money(Math.abs(gap*SCN.notional)).replace(/\.\d\d$/,'');
    // The level the tested price has actually reached, reading upward.
    row.classList.toggle('at', Math.abs(level-p)<Math.max(0.005,p*0.0005));
  });
}
function updateScenario(){
  var slider=document.getElementById('slider');if(!slider)return;
  if(testPrice===null)testPrice=Number(slider.value);
  var p=testPrice,chg=p/PLAN.current-1,entry=p/PLAN.entryMid-1,dist=p-PLAN.stop;
  // Below a cent on a $100k position is zero, not a signed nothing.
  if(Math.abs(chg)<1e-7)chg=0; if(Math.abs(entry)<1e-7)entry=0; if(Math.abs(dist)<0.005)dist=0;
  document.getElementById('sPrice').textContent=money(p);document.getElementById('sDelta').textContent=Math.abs(chg)<.0001?"At today's price":pct(chg)+' from today';
  document.getElementById('oChg').textContent=pct(chg);document.getElementById('oEntry').textContent=pct(entry);document.getElementById('oStop').textContent=dist===0?money(0)+' — at the stop':money(Math.abs(dist))+' '+(dist>0?'above':'below');document.getElementById('oPnl').textContent=chg===0?money(0):(chg>0?'+':'−')+money(Math.abs(chg*100000));
  var z=document.getElementById('zone');if(p<=PLAN.stop)z.innerHTML='<b>Invalidated.</b> Price is below the planned stop; the setup no longer qualifies.';else if(p<PLAN.entryLow)z.innerHTML='<b>Below the entry zone.</b> Wait for price to reclaim structure before considering an order.';else if(p<=PLAN.entryHigh)z.innerHTML='<b>Inside the entry zone.</b> Act only if the stated confirmation is present.';else if(p<PLAN.target1)z.innerHTML='<b>Above the entry zone.</b> Avoid chasing; reassess reward to risk.';else if(p<PLAN.target2)z.innerHTML='<b>First target reached.</b> Review risk, sizing and whether to trail the stop.';else z.innerHTML='<b>Second target reached.</b> Re-underwrite rather than assuming further upside.';
  drawScenarioGraph(p);
  // The chip matching the tested price reads as selected, so the preset levels
  // stay meaningful after the slider has been dragged off one of them.
  document.querySelectorAll('.scn-chip').forEach(function(chip){
    chip.setAttribute('aria-pressed', Number(chip.dataset.price)===p ? 'true' : 'false');
  });
}
var slider=document.getElementById('slider');
if(slider){
  slider.addEventListener('input',function(){testPrice=Number(slider.value);updateScenario();});
  document.querySelectorAll('.scn-chip').forEach(function(chip){
    chip.addEventListener('click',function(){
      testPrice=Number(chip.dataset.price);
      // The slider only follows, clamped to its own range: a wide plan can put a
      // target past the end of the track without that changing the tested price.
      slider.value=Math.min(Math.max(testPrice,Number(slider.min)),Number(slider.max));
      updateScenario();
    });
  });
  updateScenario();
}
"""


def build_research_html(result: ResearchResult, request: ResearchRequest, output_path: Path) -> Path:
    """Write a validated, self-contained interactive report."""
    result.validate()
    request.validate()
    html = _technical_report(result, request) if request.deep_analysis else _general_report(result, request)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# Slide deck
#
# A landscape, presentation-shaped view of the same report, for showing a
# conclusion rather than reading one. It lives inside the report file instead of
# being a second artifact: the exported HTML is the retained research record,
# and a deck that could drift from it would be a second version of the answer.
#
# Printing is the export. The report's own Print / save PDF control is already
# the supported PDF path, so the deck reuses it -- a landscape @page rule is
# injected only while the deck is being printed, because @page cannot be scoped
# to a class.
# ---------------------------------------------------------------------------

_DECK_CSS = """
.deck{display:none}
body.deck-on .page,body.deck-on .rail{display:none!important}
body.deck-on .deck{display:block}
body.deck-on{background:#0A1223}
/* Navy is the deck's ground throughout. The structural language is the firm's
   approved client deck (Bloom portfolio review): a gold rule under every page
   title, Garamond for display against a transitional serif for text, italic
   meta, a running foot. Charts are white images and keep their own white field.

   Every size is in em against the slide's own font-size, and that font-size
   tracks the slide's width -- a slide is a fixed canvas, and type fixed in px
   inside a scaling box runs out through the footer on a narrower screen. */
.slide{position:relative;width:1160px;max-width:96vw;aspect-ratio:16/9;margin:24px auto;
  background:#16233F;color:#C9D4E6;padding:2.55em 3.2em 2.2em;box-sizing:border-box;
  overflow:hidden;display:flex;flex-direction:column;
  font-family:'Source Serif 4',Georgia,'Times New Roman',serif;
  font-size:min(18px,1.49vw);line-height:1.45}
.slide.cover{background:linear-gradient(135deg,#1F3055 0%,#182741 46%,#0D172B 100%);
  padding:2.9em 3.7em 2.2em;justify-content:center}
.s-head{display:flex;align-items:baseline;justify-content:space-between;gap:1.6em}
.s-title{font-family:'EB Garamond',Garamond,Georgia,serif;font-size:2.22em;line-height:1.1;
  font-weight:700;margin:0;color:#FFFFFF;letter-spacing:-.004em}
.s-when{font-style:italic;font-size:.89em;color:#8FA3C4;white-space:nowrap}
/* The gold rule under the page title is the template's signature. */
.s-rule{height:2px;background:#BFA054;margin:.78em 0 1.55em}
.s-mid{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:flex-start}
.s-foot{margin-top:auto;display:flex;justify-content:space-between;align-items:baseline;
  font-size:.67em;color:#6E80A0;padding-top:.8em}
/* Slides carry no footnotes. Everything a slide states has to be legible from
   the back of a room, and a 14px italic grey line is not. */

/* --- Cover: the firm's monogram, to the template's own geometry ---------- */
/* Outer ring 11.25% of slide width, inner 9.15%, "GS" at 2.92%, gold #BFA054 --
   measured off the approved deck rather than approximated by eye. */
/* The firm's actual mark, embedded so the report stays self-contained. Sized to
   the approved deck's monogram (11.25% of slide width). It carries the firm name
   and "LLC" in its own ring, so no separate wordmark is set beneath it. */
/* Larger than the deck's drawn monogram was: the real mark carries the firm
   name and "LLC" as type inside its ring, and at 11% of slide width that type
   is not readable. */
.s-mono{text-align:center;margin-bottom:1.5em}
.s-mono img{width:10.6em;height:auto;display:inline-block}
.s-cover-name{font-family:'EB Garamond',Garamond,Georgia,serif;font-size:3.22em;line-height:1.08;
  font-weight:700;color:#FFFFFF;margin:0}
.s-cover-sub{font-family:'EB Garamond',Garamond,Georgia,serif;font-size:1.42em;color:#C6D0E0;
  margin-top:.3em}
.s-cover-rule{width:8.3em;height:2px;background:#BFA054;margin-top:1.2em}
.s-cover-disc{font-style:italic;font-size:.6em;line-height:1.6;color:#7C8DAB;margin-top:1.5em;
  max-width:74ch}

/* --- The call ------------------------------------------------------------ */
.s-ask{font-family:'EB Garamond',Garamond,Georgia,serif;font-size:1.5em;line-height:1.34;
  color:#DCE4F0;margin:0 0 .7em;max-width:34ch}
/* White, not the tone colour: at display size a green or red word was the only
   thing on the page and read as a shout. Direction still shows, in a short rule
   under it. */
.s-rating{font-family:'EB Garamond',Garamond,Georgia,serif;font-size:3.9em;font-weight:700;
  line-height:1;margin:0;color:#FFFFFF}
.s-rating:after{content:"";display:block;width:2.3em;height:3px;margin-top:.28em}
.s-rating.up:after{background:#5FCF95}
.s-rating.down:after{background:#EE9188}
.s-rating.flat:after{background:#E2C179}
.s-stance{font-style:italic;font-size:1.06em;color:#9DAEC8;margin:.5em 0 0}
.s-callgrid{display:grid;grid-template-columns:1.25fr 1fr;gap:2.6em;flex:1;min-height:0;
  align-items:center}
/* --- One divided strip, used wherever parallel figures are stated -------- */
.s-strip{display:grid;border-top:1px solid #33436A;border-bottom:1px solid #33436A}
.s-strip.two{grid-template-columns:repeat(2,minmax(0,1fr))}
.s-strip.four{grid-template-columns:repeat(4,minmax(0,1fr))}
.s-cell{padding:.9em 1.1em 1em;border-left:1px solid #2A3959;min-width:0}
.s-cell:first-child{border-left:0;padding-left:0}
.s-strip.two .s-cell:nth-child(odd){border-left:0;padding-left:0}
.s-strip.two .s-cell:nth-child(-n+2){border-top:0}
.s-strip.two .s-cell:nth-child(n+3){border-top:1px solid #2A3959}
.s-k{font-size:.68em;letter-spacing:.17em;text-transform:uppercase;color:#8296B8}
.s-v{margin-top:.42em;font-family:'EB Garamond',Garamond,Georgia,serif;font-size:1.72em;
  font-weight:600;color:#FFFFFF;line-height:1.1}
.s-v.up{color:#5FCF95}.s-v.down{color:#EE9188}
.s-n{margin-top:.34em;font-size:.86em;line-height:1.4;color:#A9B8D0}

/* --- Why: the reasoning, condensed -------------------------------------- */
.s-why p{font-size:1.16em;line-height:1.55;color:#DCE4F0;margin:0}
.s-why p + p{margin-top:.85em}
.s-why .lead{font-family:'EB Garamond',Garamond,Georgia,serif;font-size:1.5em;line-height:1.35;
  color:#FFFFFF}

/* --- Conviction Checklist: the website's five cards --------------------- */
.s-checks{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.85em;margin-top:.2em}
.s-check{background:rgba(255,255,255,.045);border:1px solid #2E3E5D;border-radius:.55em;
  padding:1.05em 1em 1.15em;display:flex;flex-direction:column}
.s-check-top{display:flex;align-items:center;gap:.5em;margin-bottom:.6em}
.s-box{flex:none;width:1.35em;height:1.35em;border-radius:.28em;display:flex;align-items:center;
  justify-content:center;font-size:.85em;font-weight:700}
.s-box.pass{background:#3F9E6F;color:#fff}
.s-box.fail{background:transparent;border:1.5px solid #4A5C7C;color:transparent}
.s-box.unconfirmed{background:transparent;border:1.5px solid #4A5C7C;color:#8296B8;font-size:.7em}
.s-check-label{font-size:.95em;font-weight:600;color:#FFFFFF;line-height:1.2}
.s-check-read{font-size:.95em;line-height:1.35;color:#DCE4F0}
.s-score{display:flex;align-items:baseline;gap:.55em;margin-bottom:.9em}
.s-score b{font-family:'EB Garamond',Garamond,Georgia,serif;font-size:2em;font-weight:700;
  color:#FFFFFF;line-height:1}
.s-score span{font-size:.75em;letter-spacing:.14em;text-transform:uppercase;color:#8296B8}

/* --- Two columns of findings -------------------------------------------- */
.s-two{display:grid;grid-template-columns:1fr 1fr;gap:2.55em}
.s-col-k{font-size:.7em;letter-spacing:.18em;text-transform:uppercase;color:#8296B8;
  padding-bottom:.5em;border-bottom:1.5px solid #33436A;margin-bottom:.12em}
.s-col.supports .s-col-k{border-bottom-color:#3F9E6F}
.s-col.against .s-col-k{border-bottom-color:#8E504A}
.s-points{list-style:none;margin:0;padding:0}
.s-points li{font-size:1.02em;line-height:1.45;color:#DCE4F0;padding:.68em 0;
  border-bottom:1px solid #253451}
.s-lead{font-size:1.4em;line-height:1.42;color:#FFFFFF;margin:0;max-width:36ch}

/* --- Chart pages -------------------------------------------------------- */
.s-evidence{display:grid;grid-template-columns:1.6fr 1fr;gap:2em;flex:1;min-height:0;
  align-items:stretch}
.s-chart{display:flex;align-items:center;justify-content:center;min-height:0;min-width:0;
  background:#FFFFFF;border-radius:.3em;padding:.7em}
.s-chart img{max-width:100%;max-height:100%;object-fit:contain}
.s-read{display:flex;flex-direction:column;justify-content:center;min-width:0}
.s-read .s-points li{font-size:.92em;padding:.58em 0}
@media print{
  body.deck-on{background:#16233F}
  .slide{margin:0;width:100%;max-width:none;aspect-ratio:auto;height:100vh;
    font-size:min(18px,1.55vw);break-after:page;break-inside:avoid;
    -webkit-print-color-adjust:exact;print-color-adjust:exact}
  .slide:last-child{break-after:auto}
}
"""


_FIRM = "Gottfried &amp; Somberg Wealth Management"

# A deck leaves the room without its report, so the disclosure travels on the
# cover rather than on a slide of its own.
_DECK_DISCLOSURE = (
    "Informational only, and reflecting conditions as of the date shown. Sources are believed "
    "reliable but are not guaranteed. Opinions and scenarios may change without notice. Investing "
    "involves risk, including possible loss of principal. Firm compliance review is required "
    "before client distribution. Internal use only."
)


@lru_cache(maxsize=1)
def _firm_mark() -> str:
    """The firm's mark as an inline image, or nothing if it is not on disk.

    Embedded rather than linked: the report is a single self-contained file that
    has to render from a mail attachment with no network. Cached because it is
    the same bytes on every report.
    """
    data_url = _image_data_url(str(Path(__file__).resolve().parent.parent / "resources" / "gs_logo.png"))
    if not data_url:
        return ""
    return f'<img src="{data_url}" alt="Gottfried &amp; Somberg Wealth Management">'


def _deck_page(title: str, meta: str, body: str, number: int, total: int) -> str:
    """An evidence page: title, gold rule, content, running foot."""
    return (
        f'<section class="slide">'
        f'<div class="s-head"><h2 class="s-title">{escape(title)}</h2>'
        f'<span class="s-when">{escape(meta)}</span></div>'
        f'<div class="s-rule"></div>'
        f'<div class="s-mid">{body}</div>'
        f'<div class="s-foot"><span>{_FIRM}</span>'
        f'<span>Page {number} of {total}</span></div></section>'
    )


def _slide_points(chart: ChartRecord, limit: int = 3, budget: int = 58) -> tuple[str, ...]:
    """A chart's reading, cut to what fits on a slide.

    The insights are written for the report, where a sentence can run thirty
    words. A slide is read from across a room, so this takes the shortest ones
    that fit a word budget rather than truncating mid-thought -- and if every one
    of them is a paragraph, it trims the first to a clause instead of showing a
    chart with nothing said about it.
    """
    candidates = [item.strip() for item in (chart.insights or _insight_bullets(chart.insight)) if item.strip()]
    points: list[str] = []
    used = 0
    for item in candidates:
        length = len(item.split())
        if length > 30 or used + length > budget:
            continue
        points.append(item)
        used += length
        if len(points) == limit:
            break
    if not points and candidates:
        words = candidates[0].split()
        points.append(" ".join(words[:26]) + ("…" if len(words) > 26 else ""))
    return tuple(points)


def _insight_bullets(insight: str) -> tuple[str, ...]:
    """One insight paragraph split into its sentences."""
    return tuple(part.strip() for part in re.split(r"(?<=[.!?])\s+", insight.strip()) if part.strip())


def _condense(paragraph: str, words: int) -> str:
    """Trim a paragraph to a slide's worth of it, on a sentence boundary."""
    sentences = _insight_bullets(paragraph)
    kept: list[str] = []
    used = 0
    for sentence in sentences:
        length = len(sentence.split())
        if kept and used + length > words:
            break
        kept.append(sentence)
        used += length
    return " ".join(kept)


def _deck_html(result: ResearchResult, request: ResearchRequest, question: str,
               checks_narrative: str, reasoning: str,
               charts: Sequence[tuple[str, ChartRecord | None]]) -> str:
    """The report as a short deck, on the firm's approved client-deck template.

    Deliberately not the report reproduced at report density. A slide is read
    from across a room in seconds, so each page carries one idea and the report
    remains where the evidence is set out in full.
    """
    tone_class = _tone(result.lead_rating)[0]
    tone = "up" if tone_class == "v-bull" else "down" if tone_class == "v-bear" else "flat"
    checklist = result.conviction_checklist
    when = _date_only(result.as_of)
    meta = f"{result.identity.ticker} · {when}"
    document = "Technical Research" if request.deep_analysis else "General Research"
    plan = result.technical_plan
    pages: list[tuple[str, str, str]] = []  # (title, meta, body)

    # 1. Why -- the reasoning, condensed. The report's two-movement narrative
    #    leads; the analyst prose that follows it in the report is a third
    #    paragraph there and does not fit a slide.
    paragraphs = checklist_paragraphs(
        checklist, rating=result.lead_rating.value,
        seed=f"{result.identity.ticker}|{result.as_of}",
    ) if checklist else ()
    if paragraphs:
        body = '<div class="s-why">'
        body += f'<p class="lead">{escape(_condense(paragraphs[0], 44))}</p>'
        for part in paragraphs[1:]:
            body += f"<p>{escape(_condense(part, 62))}</p>"
        body += "</div>"
        pages.append(("Why", meta, body))

    # 2. The call. The rating carries the page; the figures that qualify it sit
    #    beside it rather than under it, so neither competes for the eye.
    judged = (checklist.total_count - checklist.unconfirmed_count) if checklist else 0
    cells = [
        ("Confidence", escape(result.confidence.value), "", ""),
        ("Last price", _money(result.current_price), "", ""),
    ]
    if checklist:
        cells.insert(1, ("Conviction", f"{checklist.passed_count} of {judged}", "", ""))
    street = _find_metric(result, "analyst mean target", default="")
    if street and street != "—":
        cells.append(("Street target", escape(street), "",
                      escape(_find_metric(result, "target implied upside", default=""))))
    strip = "".join(
        f'<div class="s-cell"><div class="s-k">{label}</div>'
        f'<div class="s-v {klass}">{value}</div>'
        + (f'<div class="s-n">{note}</div>' if note else "")
        + "</div>"
        for label, value, klass, note in cells
    )
    stance = f'<p class="s-stance">{escape(plan.stance)}</p>' if plan is not None else ""
    pages.append((
        "The call", meta,
        f'<div class="s-callgrid"><div>'
        f'<p class="s-ask">{escape(question)}</p>'
        f'<p class="s-rating {tone}">{escape(result.lead_rating.value)}</p>{stance}</div>'
        f'<div class="s-strip two">{strip}</div></div>',
    ))

    # 3. The checklist, in the same five cards the report page carries.
    if checklist is not None and checklist.criteria:
        icons = {"pass": "&#10003;", "fail": "", "unconfirmed": "?"}
        # The card carries the criterion and a three-word reading. Its full
        # sentence is the report's job; set small and grey on a slide it is the
        # least legible thing on the page and nobody reads it.
        readings = {label: reading for label, reading, _status in checklist_headlines(checklist)}
        cards = "".join(
            f'<div class="s-check"><div class="s-check-top">'
            f'<span class="s-box {item.status}">{icons[item.status]}</span>'
            f'<span class="s-check-label">{escape(item.label)}</span></div>'
            f'<div class="s-check-read">{escape(readings.get(item.label, ""))}</div></div>'
            for item in checklist.criteria
        )
        pages.append((
            "Conviction Checklist", meta,
            f'<div class="s-score"><b>{checklist.passed_count}/{checklist.total_count}</b>'
            f"<span>criteria confirmed</span></div>"
            f'<div class="s-checks">{cards}</div>',
        ))

    # 4. The action plan, on its own page and separate from the market figures.
    if plan is not None:
        entry_mid = (plan.entry_low + plan.entry_high) / 2
        upside = (plan.first_target / entry_mid - 1.0) if entry_mid else 0.0
        pages.append((
            "Action plan", meta,
            '<div class="s-strip four">'
            f'<div class="s-cell"><div class="s-k">Entry zone</div>'
            f'<div class="s-v">{_money(plan.entry_low)}&ndash;{_money(plan.entry_high)}</div>'
            f'<div class="s-n">Midpoint {_money(entry_mid)}</div></div>'
            f'<div class="s-cell"><div class="s-k">Stop</div>'
            f'<div class="s-v down">{_money(plan.stop_level)}</div>'
            f'<div class="s-n">{plan.stop_pct:.1%} below the midpoint</div></div>'
            f'<div class="s-cell"><div class="s-k">First target</div>'
            f'<div class="s-v up">{_money(plan.first_target)}</div>'
            f'<div class="s-n">{upside:.1%} above the midpoint</div></div>'
            f'<div class="s-cell"><div class="s-k">Reward / risk</div>'
            f'<div class="s-v">{plan.reward_risk:.2f}&times;</div>'
            f'<div class="s-n">Upside per unit of risk</div></div>'
            "</div>"
            f'<p class="s-lead" style="margin-top:1.4em">{escape(plan.confirmation)}</p>',
        ))

    # 5. The evidence, chart by chart, each with what it says.
    for _label, chart in charts:
        if chart is None:
            continue
        image = _image_data_url(chart.path)
        if not image:
            continue
        points = _slide_points(chart)
        picture = f'<div class="s-chart"><img src="{image}" alt="{escape(chart.title)}"></div>'
        body = (
            f'<div class="s-evidence">{picture}<div class="s-read"><ul class="s-points">'
            + "".join(f"<li>{escape(point)}</li>" for point in points)
            + "</ul></div></div>"
        ) if points else picture
        pages.append((chart.title, meta, body))

    # 6. The one thing that would change the view.
    watch = checklist_watch(checklist) if checklist is not None else ""
    risk = result.risks[0] if result.risks else ""
    if watch or risk:
        body = (
            f'<p class="s-lead">{escape(watch[:1].upper() + watch[1:])}.</p>'
            if watch
            else '<p class="s-lead">No check currently argues against this view.</p>'
        )
        if risk:
            body += (
                '<div class="s-col-k" style="margin-top:1.9em;max-width:26ch">Principal risk</div>'
                f'<p class="s-points" style="font-size:1.02em;max-width:64ch;margin-top:.8em">'
                f"{escape(risk)}</p>"
            )
        pages.append(("What would change the view", meta, body))

    total = len(pages) + 1
    cover = (
        '<section class="slide cover"><div class="s-mid" style="flex:none">'
        f'<div class="s-mono">{_firm_mark()}</div>'
        f'<h1 class="s-cover-name">{escape(result.identity.company_name)}</h1>'
        f'<div class="s-cover-sub">{escape(document)} &middot; {escape(result.identity.ticker)} '
        f'&middot; {escape(when)}</div>'
        '<div class="s-cover-rule"></div>'
        f'<p class="s-cover-disc">{_DECK_DISCLOSURE}</p></div>'
        f'<div class="s-foot"><span>{_FIRM}</span><span>Page 1 of {total}</span></div></section>'
    )
    return '<div class="deck">' + cover + "".join(
        _deck_page(title, page_meta, body, index, total)
        for index, (title, page_meta, body) in enumerate(pages, 2)
    ) + "</div>"


def _deck_script() -> str:
    """Print the deck in landscape without disturbing the report's own printing.

    An @page rule cannot be scoped to a class, so the landscape page box is
    injected only for the duration of the deck's print and removed afterwards.
    """
    return r"""
(function(){
  var btn=document.getElementById('deckBtn'); if(!btn) return;
  var pageStyle=null;
  function enter(){
    document.body.classList.add('deck-on');
    pageStyle=document.createElement('style');
    pageStyle.textContent='@page{size:297mm 167mm;margin:0}';
    document.head.appendChild(pageStyle);
  }
  function leave(){
    document.body.classList.remove('deck-on');
    if(pageStyle){pageStyle.remove();pageStyle=null;}
  }
  btn.addEventListener('click',function(){
    enter();
    window.addEventListener('afterprint',function once(){leave();window.removeEventListener('afterprint',once);});
    setTimeout(function(){window.print();},60);
  });
})();
"""
