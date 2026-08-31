"""Render the standalone Technical Analysis report (TV Remix data only).

A single-page dashboard in the same navy/gold/white editorial system as the
rest of the app, built from a ``TVTechnicalReport`` -- no fundamentals, no
Lead Analyst synthesis, one data source end to end.
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path

from core.models import TVTechnicalReport
from reports.html_report import _date_only, _document, _image_data_url, _money

_EXTRA_CSS = r"""
.tv-summary{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--gold);border-radius:8px;padding:20px 22px;margin-bottom:24px}
.tv-summary h2{margin:0 0 14px;font-family:'Source Serif 4',Georgia,serif;font-size:19px;color:var(--ink)}
.tv-bullets{list-style:none;margin:0;padding:0}
.tv-bullets li{padding:7px 0;font-size:13px;line-height:1.52;border-bottom:1px solid var(--line-2)}
.tv-bullets li:last-child{border-bottom:none}
.tv-bullets b{color:var(--gold);text-transform:uppercase;font-size:10px;letter-spacing:.07em;margin-right:8px}
.tv-note{font-size:10.5px;color:var(--muted);margin-top:10px}
.tv-grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-bottom:24px;align-items:start}
.tv-card{border:1px solid var(--line);border-radius:8px;padding:16px 18px}
.tv-card h3{margin:0 0 12px;font-size:13.5px;color:var(--ink);font-family:'Source Serif 4',Georgia,serif;font-weight:600}
.tv-tabs{display:flex;gap:6px;margin-bottom:12px}
.tv-tab{border:1px solid var(--line);background:#fff;border-radius:6px;padding:5px 12px;font-size:11px;cursor:pointer;color:var(--muted);font-family:inherit}
.tv-tab[aria-selected="true"]{background:var(--ink);color:#fff;border-color:var(--ink)}
.tv-gauge-panel[hidden]{display:none}
.tv-gauge-label{text-align:center;font-weight:700;font-size:15px;margin-top:2px;color:var(--ink)}
.tv-gauge-sub{text-align:center;font-size:10.5px;color:var(--muted);margin-bottom:10px}
.tv-ind-table{width:100%;border-collapse:collapse;font-size:12px}
.tv-ind-table td{padding:6px 0;border-bottom:1px solid var(--line-2)}
.tv-ind-table td:last-child{text-align:right}
.tv-tag{font-size:9.5px;font-weight:700;padding:2px 8px;border-radius:10px;letter-spacing:.02em}
.tv-tag.buy{background:#E7F1EB;color:var(--bull)}
.tv-tag.sell{background:#F6E9E9;color:var(--bear)}
.tv-tag.neutral{background:var(--panel);color:var(--muted)}
.tv-ladder-row{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--line-2);font-size:12px}
.tv-ladder-row:last-child{border-bottom:none}
.tv-ladder-row.now{font-weight:700;color:var(--ink);background:var(--gold-soft);margin:0 -6px;padding:7px 6px;border-radius:4px;border-bottom:none}
.tv-ladder-row span.num{font-family:'IBM Plex Mono',monospace}
.tv-snapshot-price{font-family:'IBM Plex Mono',monospace;font-size:24px;color:var(--ink);font-weight:600}
.tv-snapshot-chg{font-size:12.5px;margin-left:8px;font-family:'IBM Plex Mono',monospace}
.tv-badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700}
.tv-badge.buy{background:#E7F1EB;color:var(--bull)}
.tv-badge.sell{background:#F6E9E9;color:var(--bear)}
.tv-badge.neutral{background:var(--panel);color:var(--muted)}
.tv-returns{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}
.tv-return-chip{font-size:10px;padding:3px 8px;border-radius:5px;background:var(--panel);color:var(--ink);font-family:'IBM Plex Mono',monospace}
.tv-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px;font-size:10.5px;color:var(--muted);text-align:center}
.tv-stats b{display:block;font-size:13px;color:var(--ink);font-family:'IBM Plex Mono',monospace;font-weight:600}
.tv-chart-read{font-size:13px;color:var(--body);line-height:1.6;margin-bottom:20px}
.tv-spark{width:100%;height:auto;display:block;margin-top:10px}
"""


def _tag_class(tag: str) -> str:
    return {"Buy": "buy", "Sell": "sell", "Neutral": "neutral"}.get(tag, "neutral")


def _gauge_svg(value: float) -> str:
    value = max(-1.0, min(1.0, value))
    angle_deg = 180 - (value + 1) / 2 * 180
    angle_rad = math.radians(angle_deg)
    cx, cy, radius = 100, 92, 78
    needle_x = cx + radius * 0.84 * math.cos(angle_rad)
    needle_y = cy - radius * 0.84 * math.sin(angle_rad)
    x1, y1 = cx - radius, cy
    x2, y2 = cx + radius, cy
    return f'''<svg viewBox="0 0 200 104" width="100%" height="100" role="img" aria-label="Rating gauge">
<defs><linearGradient id="tvGaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
<stop offset="0%" stop-color="#A34B4B"/><stop offset="50%" stop-color="#BFA054"/><stop offset="100%" stop-color="#3F7D62"/>
</linearGradient></defs>
<path d="M {x1:.1f},{y1:.1f} A {radius},{radius} 0 1 0 {x2:.1f},{y2:.1f}" fill="none" stroke="url(#tvGaugeGrad)" stroke-width="10" stroke-linecap="round"/>
<line x1="{cx}" y1="{cy}" x2="{needle_x:.1f}" y2="{needle_y:.1f}" stroke="#1B2A4A" stroke-width="3" stroke-linecap="round"/>
<circle cx="{cx}" cy="{cy}" r="5" fill="#1B2A4A"/>
</svg>'''


def _short_scale(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:,.1f}T"
    if magnitude >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.1f}B"
    if magnitude >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    return f"${value:,.0f}"


def _volume_scale(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.1f}B"
    if magnitude >= 1_000_000:
        return f"{value / 1_000_000:,.1f}M"
    if magnitude >= 1_000:
        return f"{value / 1_000:,.1f}K"
    return f"{value:,.0f}"


def _gauge_panel(report: TVTechnicalReport) -> str:
    tabs = "".join(
        f'<button class="tv-tab" role="tab" aria-selected="{str(index == 0).lower()}" aria-controls="tvGauge{gauge.timeframe}" id="tvGauge{gauge.timeframe}Tab">{escape(gauge.timeframe)}</button>'
        for index, gauge in enumerate(report.gauges)
    )
    panels = "".join(
        f'''<div class="tv-gauge-panel" id="tvGauge{gauge.timeframe}" role="tabpanel" aria-labelledby="tvGauge{gauge.timeframe}Tab"{"" if index == 0 else " hidden"}>
{_gauge_svg(gauge.rating_value)}
<div class="tv-gauge-label">{escape(gauge.rating_label or "Neutral")}</div>
<div class="tv-gauge-sub">Oscillators {escape(gauge.oscillators_label or "n/a")} &middot; Moving averages {escape(gauge.moving_averages_label or "n/a")}</div>
<table class="tv-ind-table">{"".join(f'<tr><td>{escape(name)}</td><td class="num">{escape(value)}</td><td style="text-align:right"><span class="tv-tag {_tag_class(tag)}">{escape(tag or "—")}</span></td></tr>' for name, value, tag in gauge.indicators)}</table>
</div>'''
        for index, gauge in enumerate(report.gauges)
    )
    return f'<div class="tv-card"><h3>Multi-timeframe gauge</h3><div class="tv-tabs" role="tablist">{tabs}</div>{panels}</div>'


def _levels_panel(report: TVTechnicalReport) -> str:
    rows = "".join(
        f'<div class="tv-ladder-row{" now" if level.label == "Now" else ""}"><span>{escape(level.label)}</span>'
        f'<span class="num">{_money(level.price)} <span style="color:var(--muted)">({level.pct_from_now:+.1%})</span></span></div>'
        for level in report.levels
    )
    return f'<div class="tv-card"><h3>Key levels</h3>{rows or "<p class=\'tv-note\'>No validated swing structure was available.</p>"}</div>'


def _snapshot_panel(report: TVTechnicalReport) -> str:
    change_class = "tv-badge buy" if report.change_pct >= 0 else "tv-badge sell"
    rating_class = "buy" if "buy" in report.analyst_rating.lower() else "sell" if "sell" in report.analyst_rating.lower() else "neutral"
    returns = "".join(
        f'<span class="tv-return-chip">{escape(label)} {value:+.1f}%</span>' for label, value in report.period_returns
    )
    spark = f'<img class="tv-spark" src="{_image_data_url(report.sparkline_path)}" alt="Recent price trend">' if report.sparkline_path else ""
    targets = ""
    if report.price_target_avg is not None:
        low = _money(report.price_target_low) if report.price_target_low is not None else "—"
        high = _money(report.price_target_high) if report.price_target_high is not None else "—"
        targets = f'<div class="tv-note">Analyst targets: {low} – {high}, average {_money(report.price_target_avg)}.</div>'
    stats = []
    if report.market_cap is not None:
        stats.append(("Market cap", _short_scale(report.market_cap)))
    if report.volume is not None:
        stats.append(("Volume", _volume_scale(report.volume)))
    if report.beta is not None:
        stats.append(("Beta", f"{report.beta:.2f}"))
    stats_html = "".join(f"<div><b>{escape(value)}</b>{escape(label)}</div>" for label, value in stats)
    return f'''<div class="tv-card">
<h3>{escape(report.company_name)} &middot; {escape(report.resolved_symbol)}</h3>
<span class="tv-snapshot-price">{_money(report.current_price)}</span><span class="tv-snapshot-chg" style="color:{"var(--bull)" if report.change_pct >= 0 else "var(--bear)"}">{report.change_pct:+.2f}%</span>
{f'<span class="{("tv-badge " + rating_class)}" style="margin-left:10px">{escape(report.analyst_rating)}</span>' if report.analyst_rating else ""}
{spark}
<div class="tv-returns">{returns}</div>
{targets}
<div class="tv-stats">{stats_html}</div>
</div>'''


def _source_html(report: TVTechnicalReport) -> str:
    rows = []
    for source in report.sources:
        name = escape(source.name)
        locator = escape(source.locator, quote=True)
        supports = escape(source.supports)
        if source.locator.startswith(("https://", "http://")):
            name = f'<a class="source-link" href="{locator}" target="_blank" rel="noreferrer">{name}</a>'
        rows.append(f"<div><b>{name}</b> — {supports}</div>")
    return "".join(rows)


_TAB_SCRIPT = r"""
document.querySelectorAll('.tv-tabs').forEach(function(group){
  var buttons=[].slice.call(group.querySelectorAll('.tv-tab'));
  buttons.forEach(function(button){button.addEventListener('click',function(){
    buttons.forEach(function(item){item.setAttribute('aria-selected','false');document.getElementById(item.getAttribute('aria-controls')).hidden=true});
    button.setAttribute('aria-selected','true');document.getElementById(button.getAttribute('aria-controls')).hidden=false;
  })});
});
"""


def build_tvremix_html(report: TVTechnicalReport, output_path: Path) -> Path:
    """Write a self-contained, validated Technical Analysis report (TV Remix only)."""
    if not report.available:
        raise ValueError(report.error or "TV Remix technical report is not available.")

    bullets = "".join(
        f'<li><b>{escape(label)}</b>{escape(text)}</li>' for label, text in report.summary_bullets
    )
    price_chart = (
        f'<figure class="chart"><div class="chart-title">Price structure</div><img class="chart-image" src="{_image_data_url(report.price_chart_path)}" alt="Price chart"></figure>'
        if report.price_chart_path
        else '<div class="chart-empty">No validated price chart was available.</div>'
    )
    body = f"""
<div class="shell">
<nav class="rail" aria-label="Sections">
  <div class="rail-label">Technical Analysis</div>
  <a href="#tvSummary" class="on">Summary</a><a href="#tvEvidence">Evidence</a><a href="#tvChart">Price chart</a><a href="#tvSources">Sources</a>
  <div class="rail-tools"><button class="btn" onclick="window.print()">Print / save PDF</button></div>
</nav>
<main class="page">
<div class="mast">
  <div class="firm">Gottfried &amp; Somberg Wealth Management</div>
  <div class="doctype">Technical Analysis &middot; TV Remix</div>
</div>
<div class="head">
  <div>
    <h1>{escape(report.company_name)}</h1>
    <div class="ticker-strip"><b>{escape(report.resolved_symbol)}</b><span class="dot"></span>{escape(_date_only(report.as_of))}</div>
  </div>
</div>
<section id="tvSummary">
  <div class="tv-summary">
    <h2>{escape(report.headline)}</h2>
    <ul class="tv-bullets">{bullets}</ul>
    <div class="tv-note">Not investment advice. Supplemental technical read from TV Remix, not a substitute for full Single Stock Research.</div>
  </div>
</section>
<section id="tvEvidence">
  <div class="tv-grid3">
    {_gauge_panel(report)}
    {_levels_panel(report)}
    {_snapshot_panel(report)}
  </div>
</section>
<section id="tvChart">
  <div class="sec-head"><h2>Chart read</h2></div>
  <p class="tv-chart-read">{escape(report.chart_read)}</p>
  {price_chart}
</section>
<section id="tvSources">
  <div class="sec-head"><h2>Sources</h2></div>
  <div class="sources">{_source_html(report)}</div>
  <p class="disc">This material is informational and reflects TV Remix conditions as of the stated time. Sources are believed reliable but are not guaranteed. Investing involves risk, including possible loss of principal. Firm compliance review is required before client distribution.</p>
  <footer><span>Gottfried &amp; Somberg Wealth Management</span><span class="num">Prepared {escape(_date_only(report.as_of))}</span></footer>
</section>
</main></div>"""
    html = _document(
        f"{report.resolved_symbol} Technical Analysis — Researcheus Maximus",
        "general_research_base.html",
        body,
        _TAB_SCRIPT,
        extra_css=_EXTRA_CSS,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
