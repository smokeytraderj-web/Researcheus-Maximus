"""Compact, chart-led PDF renderer for a validated research result."""

from __future__ import annotations

from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.models import ResearchRequest, ResearchResult

NAVY = colors.HexColor("#14263D")
GOLD = colors.HexColor("#B08D57")
INK = colors.HexColor("#263648")
MUTED = colors.HexColor("#657386")
PALE = colors.HexColor("#F3F5F7")
LINE = colors.HexColor("#D7DDE3")
FONT = "ResearcheusSans"
FONT_BOLD = "ResearcheusSans-Bold"


def _register_fonts() -> tuple[str, str]:
    """Embed a predictable TrueType font so PDF viewers render clean spacing."""
    try:
        import matplotlib

        font_root = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        if FONT not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(FONT, str(font_root / "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, str(font_root / "DejaVuSans-Bold.ttf")))
            pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD)
        return FONT, FONT_BOLD
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def _styles():
    regular, bold = _register_fonts()
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("Brand", parent=base["Normal"], fontName=bold, fontSize=7.2, textColor=GOLD, leading=9),
        "title": ParagraphStyle("Title", parent=base["Title"], fontName=bold, fontSize=20, leading=23, textColor=NAVY, alignment=TA_LEFT, spaceAfter=3),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontName=regular, fontSize=7.7, leading=10, textColor=MUTED),
        "section": ParagraphStyle("Section", parent=base["Heading2"], fontName=bold, fontSize=11, leading=13, textColor=NAVY, spaceBefore=7, spaceAfter=4),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName=regular, fontSize=7.8, leading=10.4, textColor=INK, spaceAfter=3),
        "compact": ParagraphStyle("Compact", parent=base["BodyText"], fontName=regular, fontSize=6.9, leading=9, textColor=INK),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontName=regular, fontSize=6.2, leading=7.7, textColor=MUTED),
        "tiny": ParagraphStyle("Tiny", parent=base["BodyText"], fontName=regular, fontSize=5.5, leading=6.8, textColor=MUTED),
        "rating": ParagraphStyle("Rating", parent=base["Normal"], fontName=bold, fontSize=13.5, leading=16, textColor=NAVY, alignment=TA_CENTER),
        "value": ParagraphStyle("Value", parent=base["Normal"], fontName=bold, fontSize=7.2, leading=9, textColor=NAVY, alignment=TA_RIGHT),
    }


def _footer(canvas, document) -> None:
    regular, _bold = _register_fonts()
    canvas.saveState()
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.6)
    canvas.line(0.62 * inch, 0.48 * inch, 7.88 * inch, 0.48 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont(regular, 6.2)
    canvas.drawString(0.62 * inch, 0.3 * inch, "Gottfried & Somberg Wealth Management")
    canvas.drawRightString(7.88 * inch, 0.3 * inch, f"Page {document.page}")
    canvas.restoreState()


def _safe(value: object) -> str:
    return escape(str(value), quote=True)


def _bullet_text(items: tuple[str, ...], style, limit: int | None = None) -> list[Paragraph]:
    selected = items if limit is None else items[:limit]
    return [Paragraph(f"- {_safe(item)}", style) for item in selected]


def _rating_box(result: ResearchResult, styles) -> Table:
    box = Table(
        [
            [
                Paragraph("LEAD", styles["small"]),
                Paragraph("TECHNICAL", styles["small"]),
                Paragraph("FUNDAMENTAL", styles["small"]),
                Paragraph("PRICE", styles["small"]),
            ],
            [
                Paragraph(_safe(result.lead_rating.value), styles["rating"]),
                Paragraph(_safe(result.technical.rating.value), styles["rating"]),
                Paragraph(_safe(result.fundamental.rating.value), styles["rating"]),
                Paragraph(f"${result.current_price:,.2f}", styles["rating"]),
            ],
        ],
        colWidths=[1.8125 * inch] * 4,
    )
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.8, NAVY),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
                ("TOPPADDING", (0, 1), (-1, 1), 7),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
            ]
        )
    )
    return box


_METRIC_PRIORITY = (
    "User purchase price",
    "Gain/loss from purchase price",
    "User quantity",
    "Illustrative current position value",
    "Market capitalization",
    "Trailing / forward P/E",
    "Revenue / earnings growth",
    "Analyst mean target",
    "Analyst target implied upside",
    "Street consensus (Yahoo)",
    "YCharts consensus rating",
    "YCharts price target",
    "YCharts price target upside",
    "20-day moving average",
    "50-day moving average",
    "200-day moving average",
    "RSI (14)",
    "MACD / signal",
    "ATR (14)",
    "Volume vs. 20-day avg.",
    "60-day support / resistance",
)


def _metric_grid(result: ResearchResult, styles) -> Table:
    def has_data(value: str) -> bool:
        remainder = value.lower().replace("unavailable", "").replace("/", "").strip()
        return bool(remainder)

    available = {label: value for label, value in result.key_metrics if has_data(value) and label != "Current price"}
    ordered = [(label, available[label]) for label in _METRIC_PRIORITY if label in available]
    included = {label for label, _value in ordered}
    ordered.extend((label, value) for label, value in available.items() if label not in included)
    ordered = ordered[:16]
    rows = []
    for index in range(0, len(ordered), 2):
        left = ordered[index]
        right = ordered[index + 1] if index + 1 < len(ordered) else ("", "")
        rows.append(
            [
                Paragraph(_safe(left[0]), styles["compact"]),
                Paragraph(_safe(left[1]), styles["value"]),
                Paragraph(_safe(right[0]), styles["compact"]),
                Paragraph(_safe(right[1]), styles["value"]),
            ]
        )
    table = Table(rows, colWidths=[2.05 * inch, 1.55 * inch, 2.05 * inch, 1.6 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ]
        )
    )
    return table


def _analysis_cards(result: ResearchResult, styles) -> Table:
    technical = [
        Paragraph(f"<b>Technical - {_safe(result.technical.rating.value)}</b>", styles["body"]),
        Paragraph(_safe(result.technical.summary), styles["compact"]),
        *_bullet_text(result.technical.signals, styles["compact"], 3),
    ]
    fundamental = [
        Paragraph(f"<b>Fundamental - {_safe(result.fundamental.rating.value)}</b>", styles["body"]),
        Paragraph(_safe(result.fundamental.summary), styles["compact"]),
        *_bullet_text(result.fundamental.signals, styles["compact"], 3),
    ]
    table = Table([[technical, fundamental]], colWidths=[3.575 * inch, 3.575 * inch], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _strategy_cards(result: ResearchResult, styles) -> Table | None:
    if not result.strategies:
        return None
    cells = []
    for strategy in result.strategies[:2]:
        cells.append(
            [
                Paragraph(f"<b>{_safe(strategy.name)}</b>", styles["body"]),
                Paragraph(f"<b>Action:</b> {_safe(strategy.action_zone)}", styles["compact"]),
                Paragraph(f"<b>Confirm:</b> {_safe(strategy.confirmation)}", styles["compact"]),
                Paragraph(f"<b>Invalidate:</b> {_safe(strategy.invalidation)}", styles["compact"]),
                Paragraph(f"<b>Risk:</b> {_safe(strategy.risk)}", styles["compact"]),
            ]
        )
    if len(cells) == 1:
        cells.append([])
    table = Table([cells], colWidths=[3.575 * inch, 3.575 * inch], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _research_watchlist(result: ResearchResult, styles) -> Table:
    columns = []
    for title, items in (
        ("Risks", result.risks),
        ("Catalysts", result.catalysts),
        ("Rating changes if", result.change_conditions),
    ):
        columns.append([Paragraph(f"<b>{title}</b>", styles["compact"]), *_bullet_text(items, styles["small"], 2)])
    table = Table([columns], colWidths=[2.383 * inch] * 3)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _source_table(result: ResearchResult, styles) -> Table:
    rows = []
    for source in result.sources[:8]:
        linked_name = f'<link href="{_safe(source.locator)}" color="#14263D"><u>{_safe(source.name)}</u></link>' if source.locator.startswith(("https://", "http://")) else _safe(source.name)
        rows.append([Paragraph(linked_name, styles["small"]), Paragraph(_safe(source.supports), styles["small"])])
    table = Table(rows, colWidths=[2.15 * inch, 5.0 * inch])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.2, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ]
        )
    )
    return table


def build_research_pdf(result: ResearchResult, request: ResearchRequest, destination: Path) -> Path:
    result.validate()
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(
        str(destination),
        pagesize=letter,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.48 * inch,
        bottomMargin=0.62 * inch,
        title=f"{result.identity.ticker} Research",
        author="Gottfried & Somberg Wealth Management",
        pageCompression=1,
    )
    as_of = result.as_of.replace("T", " ")
    story = [
        Paragraph("GOTTFRIED &amp; SOMBERG WEALTH MANAGEMENT", styles["brand"]),
        Spacer(1, 0.05 * inch),
        Paragraph(f"{_safe(result.identity.company_name)} ({_safe(result.identity.ticker)})", styles["title"]),
        Paragraph(
            f"{_safe(result.horizon.value)} research | {_safe(result.identity.exchange)} | {_safe(result.identity.currency)} | As of {_safe(as_of)} | Confidence: {_safe(result.confidence.value)}",
            styles["subtitle"],
        ),
        Spacer(1, 0.11 * inch),
    ]
    if result.demo_mode:
        warning = Table([[Paragraph("DEMO MODE - Synthetic values for workflow validation. Not live investment research.", styles["body"])]], colWidths=[7.25 * inch])
        warning.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF3D8")), ("BOX", (0, 0), (-1, -1), 0.7, GOLD), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story += [warning, Spacer(1, 0.08 * inch)]

    story += [_rating_box(result, styles), Paragraph("Investment View", styles["section"]), Paragraph(_safe(result.executive_summary), styles["body"])]
    if result.chart_path and Path(result.chart_path).is_file():
        story += [
            Spacer(1, 0.06 * inch),
            Image(result.chart_path, width=7.2 * inch, height=4.75 * inch),
            Paragraph("Source: attributed live price history; indicators and annotations calculated by Researcheus Maximus.", styles["small"]),
        ]
    story += [PageBreak(), Paragraph("Analysis and Decision Framework", styles["section"]), _analysis_cards(result, styles)]
    if result.sentiment:
        story.append(Paragraph(f"<b>Sentiment:</b> {_safe(result.sentiment)}", styles["small"]))
    story += [Paragraph("Key Metrics", styles["section"]), _metric_grid(result, styles), Paragraph("Potential Investment Strategies", styles["section"])]
    strategy_table = _strategy_cards(result, styles)
    if strategy_table is not None:
        story.append(strategy_table)
    story += [Paragraph("Research Watchlist", styles["section"]), _research_watchlist(result, styles), Paragraph("Sources", styles["section"]), _source_table(result, styles)]
    if result.limitations:
        limitations = " | ".join(result.limitations[:3])
        story.append(Paragraph(f"<b>Limitations:</b> {_safe(limitations)}", styles["tiny"]))
    story.append(
        Paragraph(
            "<b>Disclosure:</b> This material is informational and reflects conditions as of the stated time. Sources are believed reliable but are not guaranteed. Opinions and scenarios may change without notice. Investing involves risk, including possible loss of principal. Firm compliance review is required before client distribution.",
            styles["tiny"],
        )
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return destination
