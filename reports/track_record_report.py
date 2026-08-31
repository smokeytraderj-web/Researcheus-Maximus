"""Render the track record of buy-side picks: the evidence this product works."""

from __future__ import annotations

from html import escape
from pathlib import Path

from reports.html_report import _document, _image_data_url

_EXTRA_CSS = r"""
.tr-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;background:var(--panel);border-radius:8px;overflow:hidden;margin-bottom:26px}
.tr-stat{padding:16px 18px;border-right:1px solid var(--line)}
.tr-stat:last-child{border-right:none}
.tr-k{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600;margin-bottom:6px}
.tr-v{font-size:23px;font-weight:600;color:var(--ink);font-family:'IBM Plex Mono',monospace;line-height:1.1}
.tr-v.bull{color:var(--bull)}.tr-v.bear{color:var(--bear)}
.tr-n{font-size:10.5px;color:var(--muted);margin-top:5px}
.tr-table{width:100%;border-collapse:collapse;font-size:12px}
.tr-table th{padding:9px 10px;text-align:left;background:var(--ink);color:#fff;font-size:9px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap}
.tr-table td{padding:8px 10px;border-bottom:1px solid var(--line-2);vertical-align:top}
.tr-table tbody tr:nth-child(even){background:var(--panel)}
.tr-table .num{font-family:'IBM Plex Mono',monospace;text-align:right;white-space:nowrap}
.pos{color:var(--bull)}.neg{color:var(--bear)}
.tr-open{font-size:9px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;border-radius:10px;background:var(--gold-soft);color:#8A6D2F}
.tr-closed{font-size:9px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;border-radius:10px;background:var(--panel);color:var(--muted)}
.tr-empty{padding:34px 26px;background:var(--panel);border-left:3px solid var(--gold);border-radius:0 6px 6px 0;font-size:13.5px;color:var(--body);line-height:1.6}
.tr-method{font-size:11.5px;color:var(--muted);line-height:1.6;margin-top:14px}
@media print{.tr-stats{-webkit-print-color-adjust:exact;print-color-adjust:exact}.tr-table{break-inside:auto}.tr-table tr{break-inside:avoid}}
"""


def _pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "—"
    return f"{value:+.1%}" if signed else f"{value:.0%}"


def _tone(value: float | None) -> str:
    if value is None:
        return ""
    return "pos" if value > 0 else ("neg" if value < 0 else "")


def _stat(label: str, value: str, note: str, tone: str = "") -> str:
    return (
        f'<div class="tr-stat"><div class="tr-k">{escape(label)}</div>'
        f'<div class="tr-v {tone}">{escape(value)}</div><div class="tr-n">{escape(note)}</div></div>'
    )


def build_track_record_html(record, chart_path: str, as_of: str, output_path: Path) -> Path:
    """Write the self-contained track-record report."""
    if not record.has_picks:
        body = f"""
<div class="shell">
<nav class="rail" aria-label="Sections">
  <div class="rail-label">Track Record</div><a href="#tr" class="on">Picks</a>
  <div class="rail-tools"><button class="btn" onclick="window.print()">Print / save PDF</button></div>
</nav>
<main class="page">
<div class="mast"><div class="firm">Gottfried &amp; Somberg Wealth Management</div><div class="doctype">Track Record</div></div>
<div class="head"><div><h1>No picks recorded yet</h1>
<div class="ticker-strip">{escape(as_of[:10])}</div></div></div>
<section id="tr"><div class="tr-empty">
The track record builds itself from finalised research. Every time a report is finalised with a
buy-side rating &mdash; Strong Buy, Buy, or Add &mdash; that call is recorded with its date and price,
and scored from then on against SPY over the same dates.
<br><br>Nothing is shown here yet because no live call has been finalised.
Past picks are never back-filled or simulated, so this page stays empty until the calls are real.
</div></section>
</main></div>"""
        html = _document("Track Record — Researcheus Maximus", "general_research_base.html", body, "", extra_css=_EXTRA_CSS)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    rows = []
    for item in sorted(record.scored, key=lambda entry: entry.pick.opened_at, reverse=True):
        pick = item.pick
        state = '<span class="tr-open">Open</span>' if pick.is_open else '<span class="tr-closed">Closed</span>'
        closed_note = "" if pick.is_open else f"<br><span style='color:var(--muted);font-size:10.5px'>closed on {escape(pick.closed_by_rating)}</span>"
        rows.append(
            f"<tr><td>{escape(pick.opened_at)}</td>"
            f"<td><b>{escape(pick.ticker)}</b><br><span style='color:var(--muted);font-size:10.5px'>{escape(pick.company)}</span></td>"
            f"<td>{escape(pick.rating)}<br><span style='color:var(--muted);font-size:10.5px'>{escape(pick.horizon)}</span></td>"
            f"<td>{state}{closed_note}</td>"
            f"<td class='num'>${pick.entry_price:,.2f}</td>"
            f"<td class='num'>${item.exit_price:,.2f}</td>"
            f"<td class='num {_tone(item.return_pct)}'>{_pct(item.return_pct)}</td>"
            f"<td class='num'>{_pct(item.benchmark_return_pct)}</td>"
            f"<td class='num {_tone(item.excess_pct)}'>{_pct(item.excess_pct)}</td></tr>"
        )

    unscored_note = ""
    if record.unscored:
        names = ", ".join(sorted({pick.ticker for pick in record.unscored}))
        unscored_note = (
            f'<p class="tr-method"><b>Not scored:</b> {escape(names)} &mdash; a price needed to measure '
            "these could not be resolved, so they are excluded rather than estimated.</p>"
        )

    chart = (
        f'<figure class="chart"><div class="chart-title">Cumulative return vs {escape(record.benchmark)}</div>'
        f'<img class="chart-image" src="{_image_data_url(chart_path)}" alt="Track record chart"></figure>'
        if chart_path
        else '<div class="chart-empty">Not enough price history yet to draw the performance curve.</div>'
    )

    hit = record.hit_rate
    avg = record.average_return_pct
    excess = record.average_excess_pct
    body = f"""
<div class="shell">
<nav class="rail" aria-label="Sections">
  <div class="rail-label">Track Record</div>
  <a href="#summary" class="on">Summary</a><a href="#curve">Performance</a><a href="#picks">Every pick</a><a href="#method">Method</a>
  <div class="rail-tools"><button class="btn" onclick="window.print()">Print / save PDF</button></div>
</nav>
<main class="page">
<div class="mast"><div class="firm">Gottfried &amp; Somberg Wealth Management</div><div class="doctype">Track Record</div></div>
<div class="head"><div><h1>Buy-side pick performance</h1>
<div class="ticker-strip"><b>{len(record.scored)} scored picks</b><span class="dot"></span>{len(record.open)} open<span class="dot"></span>{len(record.closed)} closed<span class="dot"></span>{escape(as_of[:10])}</div></div></div>

<section id="summary">
  <div class="tr-stats">
    {_stat("Picks scored", str(len(record.scored)), f"{len(record.open)} still open")}
    {_stat("Went the right way", _pct(hit, signed=False), "share with a positive return")}
    {_stat("Average return", _pct(avg), "per pick, not annualised", _tone(avg))}
    {_stat(f"Average vs {record.benchmark}", _pct(excess), "excess over the same dates", _tone(excess))}
  </div>
</section>

<section id="curve"><div class="sec-head"><h2>Performance</h2><span class="verdict v-neu">Equal weighted</span></div>{chart}</section>

<section id="picks">
  <div class="sec-head"><h2>Every pick</h2></div>
  <table class="tr-table">
    <thead><tr><th>Called</th><th>Security</th><th>Rating</th><th>Status</th><th>Entry</th><th>Latest</th><th>Return</th><th>{escape(record.benchmark)}</th><th>Excess</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  {unscored_note}
</section>

<section id="method">
  <div class="sec-head"><h2>How this is measured</h2></div>
  <p class="tr-method">
    A pick opens when a finalised report rates a security Strong Buy, Buy or Add, at that report's price.
    It stays open until the same security is researched again and returns a rating that is not buy-side,
    closing at that later report's price. Re-confirming a buy-side view does not reset the entry, so the
    original call is what gets judged. Open picks are marked at the latest available price.
    Each pick is compared with {escape(record.benchmark)} over its own dates, so a rising market is not counted as skill.
    The curve equal-weights whichever picks were live on each date and holds cash when none were.
    Returns are price only: they exclude dividends, costs, taxes and slippage, and are not a client performance record.
  </p>
  <p class="disc">This material is informational and reflects conditions as of the stated time. Past performance is not a guide to
  future results. Sources are believed reliable but are not guaranteed. Investing involves risk, including possible loss of principal.
  Firm compliance review is required before client distribution.</p>
  <footer><span>Gottfried &amp; Somberg Wealth Management</span><span class="num">Prepared {escape(as_of[:10])}</span></footer>
</section>
</main></div>"""
    html = _document("Track Record — Researcheus Maximus", "general_research_base.html", body, "", extra_css=_EXTRA_CSS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
