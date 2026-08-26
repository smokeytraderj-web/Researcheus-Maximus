"""Compact, chart-led PDF renderer for a validated research result."""

from __future__ import annotations

from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.assessments import fundamental_outlook, technical_setup
from core.models import ResearchRequest, ResearchResult

NAVY = colors.HexColor("#1B2A4A")
GOLD = colors.HexColor("#BFA054")
INK = colors.HexColor("#1B2A4A")
MUTED = colors.HexColor("#5E697A")
PALE = colors.HexColor("#F5F7FA")
WARM = colors.white
LINE = colors.HexColor("#D8DDE6")
FONT = "ResearcheusSans"
FONT_BOLD = "ResearcheusSans-Bold"
DISPLAY = "ResearcheusDisplay-Bold"


def _register_fonts() -> tuple[str, str, str]:
    """Embed a predictable TrueType font so PDF viewers render clean spacing."""
    try:
        import matplotlib

        font_root = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        if FONT not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(FONT, str(font_root / "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, str(font_root / "DejaVuSans-Bold.ttf")))
            pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD)
        if DISPLAY not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(DISPLAY, str(font_root / "DejaVuSerif-Bold.ttf")))
        return FONT, FONT_BOLD, DISPLAY
    except Exception:
        return "Helvetica", "Helvetica-Bold", "Times-Bold"


def _styles():
    regular, bold, display = _register_fonts()
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("Brand", parent=base["Normal"], fontName=bold, fontSize=7.2, textColor=GOLD, leading=9),
        "banner_title": ParagraphStyle("BannerTitle", parent=base["Title"], fontName=display, fontSize=20.5, leading=23.5, textColor=colors.white, alignment=TA_LEFT, spaceBefore=5, spaceAfter=3),
        "banner_subtitle": ParagraphStyle("BannerSubtitle", parent=base["Normal"], fontName=regular, fontSize=7.7, leading=10, textColor=colors.white),
        "request_label": ParagraphStyle("RequestLabel", parent=base["Normal"], fontName=bold, fontSize=7.0, textColor=GOLD, leading=9, spaceBefore=2, spaceAfter=2),
        "request_response": ParagraphStyle("RequestResponse", parent=base["BodyText"], fontName=regular, fontSize=9.2, leading=12.5, textColor=INK, spaceAfter=6),
        "title": ParagraphStyle("Title", parent=base["Title"], fontName=display, fontSize=20.5, leading=23.5, textColor=NAVY, alignment=TA_LEFT, spaceAfter=3),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontName=regular, fontSize=7.7, leading=10, textColor=MUTED),
        "page_title": ParagraphStyle("PageTitle", parent=base["Heading1"], fontName=display, fontSize=18.5, leading=22, textColor=NAVY),
        "page_meta": ParagraphStyle("PageMeta", parent=base["Normal"], fontName=regular, fontSize=7.3, leading=9, textColor=NAVY, alignment=TA_RIGHT),
        "section": ParagraphStyle("Section", parent=base["Heading2"], fontName=display, fontSize=13.5, leading=16.5, textColor=NAVY, spaceBefore=10, spaceAfter=6),
        "subsection": ParagraphStyle("Subsection", parent=base["Heading3"], fontName=bold, fontSize=8.2, leading=10, textColor=GOLD, spaceBefore=3, spaceAfter=3),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName=regular, fontSize=8.8, leading=12, textColor=INK, spaceAfter=4),
        "conclusion": ParagraphStyle("Conclusion", parent=base["BodyText"], fontName=regular, fontSize=10.1, leading=13.8, textColor=INK, spaceAfter=7),
        "compact": ParagraphStyle("Compact", parent=base["BodyText"], fontName=regular, fontSize=7.8, leading=10.5, textColor=INK),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontName=regular, fontSize=6.9, leading=8.8, textColor=MUTED),
        "table_header": ParagraphStyle("TableHeader", parent=base["BodyText"], fontName=bold, fontSize=7.0, leading=8.6, textColor=colors.white),
        "tiny": ParagraphStyle("Tiny", parent=base["BodyText"], fontName=regular, fontSize=6.1, leading=7.8, textColor=MUTED),
        "rating": ParagraphStyle("Rating", parent=base["Normal"], fontName=display, fontSize=15.5, leading=18, textColor=NAVY, alignment=TA_CENTER),
        "rating_primary_label": ParagraphStyle("RatingPrimaryLabel", parent=base["Normal"], fontName=bold, fontSize=7.0, leading=8.5, textColor=GOLD, alignment=TA_CENTER),
        "rating_primary": ParagraphStyle("RatingPrimary", parent=base["Normal"], fontName=display, fontSize=18.5, leading=21, textColor=colors.white, alignment=TA_CENTER),
        "rating_support_label": ParagraphStyle("RatingSupportLabel", parent=base["Normal"], fontName=bold, fontSize=6.8, leading=8.2, textColor=MUTED, alignment=TA_CENTER),
        "rating_support": ParagraphStyle("RatingSupport", parent=base["Normal"], fontName=display, fontSize=13.2, leading=16, textColor=NAVY, alignment=TA_CENTER),
        "question": ParagraphStyle("Question", parent=base["BodyText"], fontName=bold, fontSize=8.0, leading=10.5, textColor=NAVY, spaceAfter=3),
        "summary_answer": ParagraphStyle("SummaryAnswer", parent=base["BodyText"], fontName=regular, fontSize=9.0, leading=12.3, textColor=INK),
        "action_label": ParagraphStyle("ActionLabel", parent=base["Normal"], fontName=bold, fontSize=7.0, leading=8.5, textColor=GOLD),
        "action_big": ParagraphStyle("ActionBig", parent=base["Normal"], fontName=display, fontSize=13.5, leading=16, textColor=NAVY),
        "action_detail": ParagraphStyle("ActionDetail", parent=base["BodyText"], fontName=regular, fontSize=8.0, leading=10.8, textColor=INK),
        "action_value": ParagraphStyle("ActionValue", parent=base["Normal"], fontName=bold, fontSize=8.8, leading=10.5, textColor=NAVY, alignment=TA_LEFT),
        "value": ParagraphStyle("Value", parent=base["Normal"], fontName=bold, fontSize=8.0, leading=9.8, textColor=NAVY, alignment=TA_RIGHT),
        "metric_label": ParagraphStyle("MetricLabel", parent=base["BodyText"], fontName=regular, fontSize=7.5, leading=9.5, textColor=INK),
        "metric_value": ParagraphStyle("MetricValue", parent=base["BodyText"], fontName=bold, fontSize=7.9, leading=9.7, textColor=NAVY, alignment=TA_RIGHT),
        "chart_note": ParagraphStyle("ChartNote", parent=base["BodyText"], fontName=regular, fontSize=7.5, leading=10, textColor=MUTED, italic=True, spaceBefore=3, spaceAfter=4),
    }


def _footer(canvas, document) -> None:
    regular, _bold, _display = _register_fonts()
    canvas.saveState()
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.6)
    canvas.line(0.62 * inch, 0.48 * inch, 7.88 * inch, 0.48 * inch)
    canvas.setFillColor(NAVY)
    canvas.setFont(regular, 6.2)
    canvas.drawString(0.62 * inch, 0.3 * inch, "Gottfried & Somberg Wealth Management")
    canvas.drawRightString(7.88 * inch, 0.3 * inch, f"Page {document.page}")
    canvas.restoreState()


def _safe(value: object) -> str:
    return escape(str(value), quote=True)


def _as_of_label(result: ResearchResult) -> str:
    return f"As of {result.as_of[:10]}"


def _overall_conclusion_text(value: str) -> str:
    """Remove redundant machine-style prefixes beneath the report heading."""
    prefixes = (
        "Overall conclusion:",
        "Direct answer:",
        "Position answer:",
        "Portfolio-fit answer:",
        "Historical conclusion:",
        "Historical case-study answer:",
    )
    cleaned = value.strip()
    for prefix in prefixes:
        if cleaned.lower().startswith(prefix.lower()):
            return cleaned[len(prefix):].lstrip()
    return cleaned


def _first_sentence(value: str) -> str:
    protected = value.strip()
    abbreviations = ("Inc.", "Corp.", "Co.", "Ltd.", "L.P.", "S.A.", "U.S.")
    for abbreviation in abbreviations:
        protected = protected.replace(abbreviation, abbreviation.replace(".", "<DOT>"))
    parts = re.split(r"(?<=[.!?])\s+", protected, maxsplit=1)
    first = parts[0].replace("<DOT>", ".") if parts else protected.replace("<DOT>", ".")
    return first.strip()


def _report_banner(title: str, subtitle: str, styles) -> Table:
    content = [
        Paragraph("GOTTFRIED &amp; SOMBERG WEALTH MANAGEMENT", styles["brand"]),
        Paragraph(_safe(title), styles["banner_title"]),
        Paragraph(subtitle, styles["banner_subtitle"]),
    ]
    banner = Table([[content]], colWidths=[7.25 * inch], hAlign="LEFT")
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("LINEBELOW", (0, 0), (-1, -1), 1.5, GOLD),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return banner


def _content_header(title: str, meta: str, styles) -> list:
    header = Table(
        [[Paragraph(_safe(title), styles["page_title"]), Paragraph(_safe(meta), styles["page_meta"])]],
        colWidths=[5.3 * inch, 1.95 * inch],
        hAlign="LEFT",
    )
    header.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 1.4, GOLD),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [header, Spacer(1, 0.10 * inch)]


def _bullet_text(items: tuple[str, ...], style, limit: int | None = None) -> list[Paragraph]:
    selected = items if limit is None else items[:limit]
    return [Paragraph(f"- {_safe(item)}", style) for item in selected]


def _insight_bullets(insight: str) -> tuple[str, ...]:
    return tuple(
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", insight.strip())
        if sentence.strip()
    )


def _chart_note(items: tuple[str, ...], styles) -> Paragraph | None:
    clean = tuple(item.strip() for item in items if item and item.strip())
    if not clean:
        return None
    return Paragraph(f"<b>Decision note:</b> {_safe(clean[0])}", styles["chart_note"])


def _rating_box(result: ResearchResult, styles, *, price_label: str = "CURRENT PRICE") -> Table:
    box = Table(
        [
            [
                Paragraph("OVERALL RATING", styles["rating_primary_label"]),
                Paragraph("TECHNICAL SETUP", styles["rating_support_label"]),
                Paragraph("FUNDAMENTAL OUTLOOK", styles["rating_support_label"]),
                Paragraph(_safe(price_label), styles["rating_support_label"]),
            ],
            [
                Paragraph(_safe(result.lead_rating.value), styles["rating_primary"]),
                Paragraph(_safe(technical_setup(result.technical.rating)), styles["rating_support"]),
                Paragraph(_safe(fundamental_outlook(result.fundamental.rating)), styles["rating_support"]),
                Paragraph(f"${result.current_price:,.2f}", styles["rating_support"]),
            ],
        ],
        colWidths=[2.2 * inch, 1.68 * inch, 1.75 * inch, 1.62 * inch],
    )
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), NAVY),
                ("BACKGROUND", (1, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.55, LINE),
                ("LINEABOVE", (0, 0), (-1, 0), 2.0, GOLD),
                ("LINEBEFORE", (1, 0), (-1, -1), 0.25, LINE),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
                ("TOPPADDING", (0, 1), (-1, 1), 9),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
            ]
        )
    )
    return box


def _request_answer_card(result: ResearchResult, request: ResearchRequest, styles) -> Table | None:
    if not result.request_response:
        return None
    question = request.question.strip() or request.query.strip()
    content = [
        Paragraph("RESPONSE TO YOUR REQUEST", styles["request_label"]),
        Paragraph(f"<b>Your question:</b> {_safe(question)}", styles["question"]),
        Paragraph(_safe(result.request_response), styles["summary_answer"]),
    ]
    card = Table([[content]], colWidths=[7.25 * inch], hAlign="LEFT")
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("LINEBEFORE", (0, 0), (0, -1), 3.0, GOLD),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return card


def _comparison_preference_box(result: ResearchResult, styles, *, historical_range: bool = False) -> Table:
    comparison = result.comparison
    assert comparison is not None
    box = Table(
        [
            [
                Paragraph(
                    "RANGE-END EVIDENCE PREFERENCE" if historical_range else "CURRENT EVIDENCE PREFERENCE",
                    styles["small"],
                ),
                Paragraph(result.identity.ticker, styles["small"]),
                Paragraph(comparison.secondary_identity.ticker, styles["small"]),
            ],
            [
                Paragraph(_safe(comparison.preferred_ticker), styles["rating"]),
                Paragraph(f"${result.current_price:,.2f}", styles["rating"]),
                Paragraph(f"${comparison.secondary_price:,.2f}", styles["rating"]),
            ],
        ],
        colWidths=[3.65 * inch, 1.8 * inch, 1.8 * inch],
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


def _comparison_metric_table(result: ResearchResult, styles) -> Table:
    comparison = result.comparison
    assert comparison is not None
    rows = [[
        Paragraph("METRIC", styles["table_header"]),
        Paragraph(_safe(result.identity.ticker), styles["table_header"]),
        Paragraph(_safe(comparison.secondary_identity.ticker), styles["table_header"]),
        Paragraph("EVIDENCE EDGE", styles["table_header"]),
    ]]
    rows.extend(
        [
            Paragraph(_safe(label), styles["compact"]),
            Paragraph(_safe(primary), styles["value"]),
            Paragraph(_safe(secondary), styles["value"]),
            Paragraph(_safe(edge), styles["compact"]),
        ]
        for label, primary, secondary, edge in comparison.metrics
    )
    table = Table(rows, colWidths=[2.15 * inch, 1.65 * inch, 1.65 * inch, 1.8 * inch], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 4.2),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4.2),
            ]
        )
    )
    return table


def _comparison_performance_summary(result: ResearchResult, styles) -> Table | None:
    comparison = result.comparison
    assert comparison is not None
    if (
        not comparison.benchmark_ticker
        or comparison.benchmark_return is None
        or comparison.primary_chart_return is None
        or comparison.secondary_chart_return is None
    ):
        return None
    rows = [
        [
            Paragraph("VISIBLE CHART PERIOD", styles["table_header"]),
            Paragraph("TOTAL RETURN", styles["table_header"]),
            Paragraph(f"EXCESS VS. {comparison.benchmark_ticker}", styles["table_header"]),
        ],
        [
            Paragraph(_safe(result.identity.ticker), styles["body"]),
            Paragraph(f"{comparison.primary_chart_return:+.1%}", styles["value"]),
            Paragraph(f"{comparison.primary_chart_return - comparison.benchmark_return:+.1%}", styles["value"]),
        ],
        [
            Paragraph(_safe(comparison.secondary_identity.ticker), styles["body"]),
            Paragraph(f"{comparison.secondary_chart_return:+.1%}", styles["value"]),
            Paragraph(f"{comparison.secondary_chart_return - comparison.benchmark_return:+.1%}", styles["value"]),
        ],
        [
            Paragraph(_safe(comparison.benchmark_ticker), styles["body"]),
            Paragraph(f"{comparison.benchmark_return:+.1%}", styles["value"]),
            Paragraph("Benchmark", styles["value"]),
        ],
    ]
    table = Table(rows, colWidths=[2.7 * inch, 2.1 * inch, 2.45 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _comparison_chart_takeaways(result: ResearchResult) -> tuple[str, ...]:
    comparison = result.comparison
    assert comparison is not None
    bullets = list(comparison.rationale[:2])
    if (
        comparison.primary_chart_return is not None
        and comparison.secondary_chart_return is not None
    ):
        difference = comparison.primary_chart_return - comparison.secondary_chart_return
        leader = result.identity.ticker if difference >= 0 else comparison.secondary_identity.ticker
        bullets.insert(
            0,
            f"{leader} led the other security by {abs(difference):.1%} over the visible chart period.",
        )
    if comparison.benchmark_ticker and comparison.benchmark_return is not None:
        bullets.append(
            f"{comparison.benchmark_ticker} is the common benchmark; the table above shows each security's excess return over the same dates."
        )
    return tuple(bullets[:4])


def _comparison_technical_cards(result: ResearchResult, styles) -> Table:
    comparison = result.comparison
    assert comparison is not None
    cards = []
    for identity, finding in (
        (result.identity, result.technical),
        (comparison.secondary_identity, comparison.secondary_technical),
    ):
        cards.append(
            [
                Paragraph(
                    f"<b>{_safe(identity.ticker)} - {_safe(technical_setup(finding.rating))}</b>",
                    styles["body"],
                ),
                Paragraph(_safe(finding.summary), styles["compact"]),
                *_bullet_text(finding.signals, styles["small"], 3),
            ]
        )
    table = Table([cards], colWidths=[3.575 * inch, 3.575 * inch])
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
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _comparison_fundamental_cards(result: ResearchResult, styles) -> Table:
    comparison = result.comparison
    assert comparison is not None
    metrics = {label: (primary, secondary) for label, primary, secondary, _edge in comparison.metrics}

    def value(label: str, index: int) -> str:
        pair = metrics.get(label, ("Unavailable", "Unavailable"))
        return pair[index]

    cards = []
    for index, identity in enumerate((result.identity, comparison.secondary_identity)):
        cards.append(
            [
                Paragraph(f"<b>{_safe(identity.company_name)} ({_safe(identity.ticker)})</b>", styles["body"]),
                Paragraph(f"<b>Business:</b> {_safe(value('Sector / industry', index))}", styles["compact"]),
                Paragraph(
                    f"<b>Valuation:</b> Forward P/E {_safe(value('Forward P/E', index))}; price/sales {_safe(value('Price / sales', index))}",
                    styles["compact"],
                ),
                Paragraph(
                    f"<b>Growth:</b> Revenue {_safe(value('Revenue growth', index))}; earnings {_safe(value('Earnings growth', index))}",
                    styles["compact"],
                ),
                Paragraph(
                    f"<b>Profitability:</b> Operating margin {_safe(value('Operating margin', index))}; free-cash-flow yield {_safe(value('Free cash flow yield', index))}",
                    styles["compact"],
                ),
                Paragraph(
                    f"<b>Risk context:</b> Debt/equity {_safe(value('Debt / equity', index))}; beta {_safe(value('Beta', index))}",
                    styles["compact"],
                ),
            ]
        )
    table = Table([cards], colWidths=[3.575 * inch, 3.575 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


_METRIC_PRIORITY = (
    "User purchase price",
    "Gain/loss from purchase price",
    "User quantity",
    "Illustrative current position value",
    "Planned entry zone",
    "Technical stop / invalidation",
    "First / second target",
    "Estimated reward / risk",
    "Range-end price",
    "Security type",
    "Fund strategy",
    "Fund family",
    "Expense ratio",
    "Distribution yield",
    "Fund net assets",
    "Annual holdings turnover",
    "Reported asset allocation",
    "Fund duration",
    "Fund maturity",
    "Fund credit quality",
    "Market capitalization",
    "Trailing / forward P/E",
    "Revenue growth",
    "Earnings growth",
    "Analyst mean target",
    "Analyst target implied upside",
    "Street consensus (Yahoo)",
    "YCharts consensus rating",
    "YCharts price target",
    "YCharts price target upside",
    "Analysis-range return",
    "Three-month return",
    "20-day moving average",
    "50-day moving average",
    "200-day moving average",
    "RSI (14)",
    "MACD / signal",
    "ATR (14)",
    "Volume vs. 20-day avg.",
    "60-day support / resistance",
    "6-month Fibonacci swing range",
    "Fibonacci 38.2% / 50% / 61.8%",
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


_METRIC_GROUPS = (
    (
        "Position and Risk",
        (
            "User purchase price",
            "Gain/loss from purchase price",
            "User quantity",
            "Illustrative current position value",
            "Planned entry zone",
            "Technical stop / invalidation",
            "First / second target",
            "Estimated reward / risk",
        ),
    ),
    (
        "Trend and Momentum",
        (
            "Analysis-range return",
            "Three-month return",
            "20-day moving average",
            "50-day moving average",
            "200-day moving average",
            "RSI (14)",
            "MACD / signal",
            "ATR (14)",
            "Volume vs. 20-day avg.",
            "60-day support / resistance",
            "6-month Fibonacci swing range",
            "Fibonacci 38.2% / 50% / 61.8%",
        ),
    ),
    (
        "Company and Valuation",
        (
            "Current price",
            "Range-end price",
            "Security type",
            "Market capitalization",
            "Trailing / forward P/E",
            "Revenue growth",
            "Earnings growth",
            "Analyst mean target",
            "Analyst target implied upside",
            "Street consensus (Yahoo)",
            "YCharts consensus rating",
            "YCharts price target",
            "YCharts price target upside",
        ),
    ),
    (
        "Fund Profile",
        (
            "Fund strategy",
            "Fund family",
            "Expense ratio",
            "Distribution yield",
            "Fund net assets",
            "Annual holdings turnover",
            "Reported asset allocation",
            "Fund duration",
            "Fund maturity",
            "Fund credit quality",
        ),
    ),
)


def _metric_group_table(title: str, metrics: list[tuple[str, str]], styles) -> Table:
    rows: list[list] = [[Paragraph(_safe(title.upper()), styles["table_header"]), "", "", ""]]
    for index in range(0, len(metrics), 2):
        left = metrics[index]
        right = metrics[index + 1] if index + 1 < len(metrics) else ("", "")
        rows.append(
            [
                Paragraph(_safe(left[0]), styles["metric_label"]),
                Paragraph(_safe(left[1]), styles["metric_value"]),
                Paragraph(_safe(right[0]), styles["metric_label"]),
                Paragraph(_safe(right[1]), styles["metric_value"]),
            ]
        )
    table = Table(rows, colWidths=[2.0 * inch, 1.58 * inch, 2.0 * inch, 1.57 * inch], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (-1, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("LINEBELOW", (0, 1), (-1, -2), 0.25, LINE),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
            ]
        )
    )
    return table


def _organized_metric_story(result: ResearchResult, styles) -> list:
    def has_data(value: str) -> bool:
        remainder = value.lower().replace("unavailable", "").replace("/", "").strip()
        return bool(remainder)

    available = {label: value for label, value in result.key_metrics if has_data(value)}
    available.setdefault("Current price", f"${result.current_price:,.2f}")
    if result.technical_plan is not None:
        plan = result.technical_plan
        available.setdefault("Planned entry zone", f"${plan.entry_low:,.2f}-${plan.entry_high:,.2f}")
        available.setdefault(
            "Technical stop / invalidation",
            f"${plan.stop_level:,.2f} ({plan.stop_pct:.1%} below entry midpoint)",
        )
        available.setdefault(
            "First / second target",
            f"${plan.first_target:,.2f} / ${plan.second_target:,.2f}",
        )
        available.setdefault("Estimated reward / risk", f"{plan.reward_risk:.2f}x to first target")
    used: set[str] = set()
    story: list = []
    for title, labels in _METRIC_GROUPS:
        metrics = [(label, available[label]) for label in labels if label in available]
        if not metrics:
            continue
        used.update(label for label, _value in metrics)
        story += [_metric_group_table(title, metrics, styles), Spacer(1, 0.10 * inch)]
    extras = [(label, value) for label, value in available.items() if label not in used]
    if extras:
        story += [_metric_group_table("Additional Research Data", extras, styles), Spacer(1, 0.10 * inch)]
    return story


def _key_metric_note(result: ResearchResult, styles) -> Paragraph | None:
    metrics = dict(result.key_metrics)

    def percent(label: str) -> float | None:
        value = str(metrics.get(label, "")).replace("%", "").replace(",", "").strip()
        try:
            return float(value) / 100
        except ValueError:
            return None

    revenue_growth = percent("Revenue growth")
    earnings_growth = percent("Earnings growth")
    if revenue_growth is not None and earnings_growth is not None and revenue_growth > 0 > earnings_growth:
        return Paragraph(
            (
                f"<b>What this means:</b> Revenue grew {revenue_growth:.1%}, but earnings changed {earnings_growth:.1%}. "
                "Sales are expanding, but that growth has not yet translated into higher profit; margins, costs, and one-time items need closer review."
            ),
            styles["compact"],
        )
    return None


def _analysis_cards(result: ResearchResult, styles) -> Table:
    technical = [
        Paragraph("TECHNICAL SETUP", styles["subsection"]),
        Paragraph(_safe(technical_setup(result.technical.rating)), styles["action_big"]),
        Paragraph(_safe(result.technical.summary), styles["body"]),
        *_bullet_text(result.technical.signals, styles["compact"], 3),
    ]
    fundamental = [
        Paragraph("FUNDAMENTAL OUTLOOK", styles["subsection"]),
        Paragraph(_safe(fundamental_outlook(result.fundamental.rating)), styles["action_big"]),
        Paragraph(_safe(result.fundamental.summary), styles["body"]),
        *_bullet_text(result.fundamental.signals, styles["compact"], 3),
    ]
    table = Table([[technical], [fundamental]], colWidths=[7.15 * inch], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("LINEABOVE", (0, 0), (-1, 0), 1.7, GOLD),
                ("LINEABOVE", (0, 1), (-1, 1), 1.0, GOLD),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
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
                Paragraph(f"<b>Possible entry:</b> {_safe(strategy.action_zone)}", styles["compact"]),
                Paragraph(f"<b>What to wait for:</b> {_safe(strategy.confirmation)}", styles["compact"]),
                Paragraph(f"<b>When the idea fails:</b> {_safe(strategy.invalidation)}", styles["compact"]),
                Paragraph(f"<b>Main risk:</b> {_safe(strategy.risk)}", styles["compact"]),
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


def _technical_action_plan_story(result: ResearchResult, styles) -> list:
    plan = result.technical_plan
    if plan is None:
        return []

    entry_zone = f"${plan.entry_low:,.2f}-${plan.entry_high:,.2f}"
    stop = f"${plan.stop_level:,.2f}"
    targets = f"${plan.first_target:,.2f} / ${plan.second_target:,.2f}"
    position_card = Table(
        [[
            [
                Paragraph("POSITION IDEA", styles["action_label"]),
                Paragraph(_safe(plan.stance), styles["action_big"]),
                Paragraph(
                    f"<b>Order approach:</b> {_safe(plan.order_type)}<br/><b>Market condition:</b> {_safe(plan.market_condition)}",
                    styles["action_detail"],
                ),
            ],
            [
                Paragraph("PLANNED ENTRY", styles["action_label"]),
                Paragraph(_safe(entry_zone), styles["action_big"]),
                Paragraph("Use the range only if the confirmation condition is met.", styles["action_detail"]),
            ],
        ]],
        colWidths=[4.55 * inch, 2.6 * inch],
        hAlign="LEFT",
    )
    position_card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("LINEABOVE", (0, 0), (-1, 0), 2.0, GOLD),
                ("LINEBEFORE", (1, 0), (1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    risk_target_cards = Table(
        [[
            [
                Paragraph("STOP-LOSS IDEA", styles["action_label"]),
                Paragraph(_safe(stop), styles["action_big"]),
                Paragraph(
                    f"<b>Distance:</b> {plan.stop_pct:.1%} below entry midpoint<br/><b>Idea fails if:</b> {_safe(plan.invalidation)}",
                    styles["action_detail"],
                ),
            ],
            [
                Paragraph("TARGETS", styles["action_label"]),
                Paragraph(_safe(targets), styles["action_big"]),
                Paragraph(
                    f"<b>Reward/risk:</b> {plan.reward_risk:.2f}x to Target 1<br/><b>Confirm with:</b> {_safe(plan.confirmation)}",
                    styles["action_detail"],
                ),
            ],
        ]],
        colWidths=[3.575 * inch, 3.575 * inch],
        hAlign="LEFT",
    )
    risk_target_cards.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    rationale = [
        Paragraph("WHY THESE LEVELS", styles["action_label"]),
        *_bullet_text(plan.rationale[:3], styles["compact"]),
    ]
    rationale_card = Table([[rationale]], colWidths=[7.15 * inch], hAlign="LEFT")
    rationale_card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, GOLD),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story = [position_card, Spacer(1, 0.08 * inch), risk_target_cards, Spacer(1, 0.07 * inch), rationale_card]
    if plan.options_strategy:
        options = Table(
            [
                [
                    Paragraph("OPTIONS STRATEGY EXAMPLE", styles["table_header"]),
                    Paragraph(
                        f"<b>{_safe(plan.options_strategy)}</b><br/>{_safe(plan.options_structure)}"
                        f"<br/><b>Risk:</b> {_safe(plan.options_risk)}",
                        styles["body"],
                    )
                ]
            ],
            colWidths=[1.55 * inch, 5.6 * inch],
            hAlign="LEFT",
        )
        options.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), NAVY),
                    ("BACKGROUND", (1, 0), (1, 0), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story += [Spacer(1, 0.07 * inch), options]
    return story


def _research_watchlist(result: ResearchResult, styles) -> Table:
    columns = []
    for title, items in (
        ("Risks", result.risks),
        ("Catalysts", result.catalysts),
        ("Rating changes if", result.change_conditions),
    ):
        columns.append([Paragraph(title.upper(), styles["subsection"]), *_bullet_text(items, styles["compact"], 2)])
    table = Table([columns], colWidths=[2.383 * inch] * 3)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                ("LINEABOVE", (0, 0), (-1, 0), 1.4, GOLD),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
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


def _client_visible_limitations(result: ResearchResult) -> tuple[str, ...]:
    """Keep operational provider diagnostics in Evidence Review, not the client PDF."""
    hidden_fragments = (
        "no ai research provider was available",
        "automatic provider fallback",
        "ycharts",
        "excel returned",
        "excel automation",
        "addin",
        "add-in",
        "formula error",
        "#name?",
    )
    return tuple(
        item for item in result.limitations
        if not any(fragment in item.lower() for fragment in hidden_fragments)
    )


def _sources_and_disclosure_story(result: ResearchResult, styles, *, comparison: bool = False) -> list:
    visible_limitations = _client_visible_limitations(result)
    options_disclosure = (
        " Options involve leverage and are not suitable for every investor; an option buyer can lose the entire premium, and an option seller can be assigned. Any options scenario requires separate suitability, approval, and live-chain review."
        if result.technical_plan is not None and result.technical_plan.options_strategy
        else ""
    )
    comparison_note = (
        " The comparison is limited to like-for-like available evidence and may omit unavailable factors."
        if comparison
        else ""
    )
    story = [
        PageBreak(),
        *_content_header("Sources and Disclosure", _as_of_label(result), styles),
        Paragraph(
            "Source records below support the market history, security facts, benchmarks, and research evidence used throughout this report.",
            styles["body"],
        ),
        _source_table(result, styles),
    ]
    if visible_limitations:
        story += [
            Paragraph("Report Notes", styles["section"]),
            *_bullet_text(visible_limitations[:4], styles["small"]),
        ]
    story.append(
        Paragraph(
            "<b>Disclosure:</b> This material is informational and reflects conditions as of the stated time. Sources are believed reliable but are not guaranteed. Opinions and scenarios may change without notice. Investing involves risk, including possible loss of principal."
            + comparison_note
            + options_disclosure
            + " Firm compliance review is required before client distribution.",
            styles["tiny"],
        )
    )
    return story


def _chartbook_story(result: ResearchResult, styles) -> list:
    story = []
    for index, chart in enumerate(result.chartbook):
        if index % 2 == 0:
            story.append(PageBreak())
            heading = "Deep Technical Chartbook" if index == 0 else "Deep Technical Chartbook - Continued"
            story.extend(_content_header(heading, _as_of_label(result), styles))
        story.append(Paragraph(_safe(chart.title), styles["section"]))
        image = Image(chart.path)
        trailing_single = len(result.chartbook) % 2 == 1 and index == len(result.chartbook) - 1
        image._restrictSize(7.15 * inch, (2.35 if trailing_single else 2.95) * inch)
        story.append(image)
        note = _chart_note(
            chart.insights or _insight_bullets(chart.insight),
            styles,
        )
        if note is not None:
            story.append(note)
        story.append(Spacer(1, 0.05 * inch))
    return story


def _portfolio_fit_box(result: ResearchResult, styles) -> Table | None:
    fit = result.portfolio_fit
    if fit is None:
        return None
    evidence = "<br/>".join(f"- {_safe(item)}" for item in fit.evidence[:4])
    watchouts = "<br/>".join(f"- {_safe(item)}" for item in fit.watchouts[:3])
    table = Table(
        [
            [
                Paragraph(
                    f"<b>{fit.equity_target_pct}/{fit.fixed_income_target_pct} PORTFOLIO FIT</b><br/>"
                    f"<font size='10'><b>{_safe(fit.fit_label)}</b></font><br/>{_safe(fit.summary)}",
                    styles["body"],
                ),
                Paragraph(
                    f"<b>Role and evidence</b><br/>{evidence}<br/><br/><b>What to confirm</b><br/>{watchouts}",
                    styles["compact"],
                ),
            ]
        ],
        colWidths=[3.58 * inch, 3.57 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.6, NAVY),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _historical_trade_story(result: ResearchResult, styles) -> list:
    story = [PageBreak(), *_content_header("Historical Trade Case Studies", _as_of_label(result), styles)]
    story.append(
        Paragraph(
            "Hypothetical, rules-based examples using real daily market history. These are not executed trades, reconstructed TradingView orders, or proof that the same rule will work in the future. The signal is evaluated after the close and the entry is the next session, which prevents look-ahead bias.",
            styles["small"],
        )
    )
    if not result.historical_trade_cases:
        story.append(
            Paragraph(
                "No trade met every entry rule in the selected period. The report intentionally does not manufacture an example.",
                styles["body"],
            )
        )
        return story
    for index, case in enumerate(result.historical_trade_cases, start=1):
        if index > 1:
            story.append(PageBreak())
        story.append(Paragraph(f"Example {index} - Signal on {_safe(case.signal_date)}", styles["section"]))
        summary = Table(
            [
                [
                    Paragraph("ENTRY", styles["table_header"]),
                    Paragraph("INITIAL STOP", styles["table_header"]),
                    Paragraph("EXIT", styles["table_header"]),
                    Paragraph("OUTCOME", styles["table_header"]),
                ],
                [
                    Paragraph(f"{_safe(case.entry_date)}<br/><b>${case.entry_price:,.2f}</b>", styles["compact"]),
                    Paragraph(f"${case.initial_stop:,.2f}", styles["value"]),
                    Paragraph(f"{_safe(case.exit_date)}<br/><b>${case.exit_price:,.2f}</b>", styles["compact"]),
                    Paragraph(f"{_safe(case.outcome)}<br/><b>{case.return_pct:+.1%}</b>", styles["value"]),
                ],
            ],
            colWidths=[1.8 * inch, 1.75 * inch, 1.8 * inch, 1.8 * inch],
        )
        summary.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story += [summary, Spacer(1, 0.08 * inch)]
        if case.chart_path and Path(case.chart_path).is_file():
            image = Image(case.chart_path)
            image._restrictSize(7.15 * inch, 4.1 * inch)
            story.append(image)
        note = _chart_note(
            (
                f"Entry: {case.rationale}",
                f"Exit: {case.exit_reason}",
                f"Result: {case.return_pct:+.1%} from the hypothetical entry to exit.",
            ),
            styles,
        )
        if note is not None:
            story.append(note)
    return story


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
    page_meta = _as_of_label(result)
    custom_range = bool(request.custom_start and request.custom_end)
    historical_range = bool(custom_range and request.custom_end < result.as_of[:10])
    range_text = (
        f"Custom range {_safe(request.custom_start)} to {_safe(request.custom_end)}"
        if custom_range
        else ""
    )
    comparison = result.comparison
    report_title = (
        f"{result.identity.ticker} vs {comparison.secondary_identity.ticker}"
        if comparison
        else f"{result.identity.company_name} ({result.identity.ticker})"
    )
    report_subtitle = (
        f"Security Comparison | {range_text + ' | ' if range_text else ''}{_safe(result.identity.currency)} | Produced {_safe(as_of)}"
        if comparison
        else f"{_safe(result.analysis_mode if request.deep_analysis else result.horizon.value + ' research')} | {range_text + ' | ' if range_text else ''}{_safe(result.identity.exchange)} | {_safe(result.identity.currency)} | Produced {_safe(as_of)}"
    )
    story = [_report_banner(report_title, report_subtitle, styles), Spacer(1, 0.11 * inch)]
    if result.demo_mode:
        warning = Table([[Paragraph("DEMO MODE - Synthetic values for workflow validation. Not live investment research.", styles["body"])]], colWidths=[7.25 * inch])
        warning.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF3D8")), ("BOX", (0, 0), (-1, -1), 0.7, GOLD), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story += [warning, Spacer(1, 0.08 * inch)]

    if comparison:
        story += [
            _comparison_preference_box(result, styles, historical_range=historical_range),
            Paragraph("Comparison View", styles["section"]),
        ]
        if result.request_response:
            story += [
                Paragraph("RESPONSE TO YOUR REQUEST", styles["request_label"]),
                Paragraph(_safe(result.request_response), styles["request_response"]),
            ]
        story += [
            Paragraph(_safe(comparison.verdict), styles["body"]),
            *_bullet_text(comparison.rationale, styles["compact"]),
        ]
        performance_summary = _comparison_performance_summary(result, styles)
        if performance_summary is not None:
            story += [Paragraph("Performance Difference", styles["section"]), performance_summary]
        if result.chart_path and Path(result.chart_path).is_file():
            comparison_chart = Image(result.chart_path)
            comparison_chart._restrictSize(7.2 * inch, 4.35 * inch)
            story += [
                Spacer(1, 0.07 * inch),
                comparison_chart,
            ]
        story += [
            PageBreak(),
            *_content_header("Side-by-Side Evidence", page_meta, styles),
            _comparison_metric_table(result, styles),
            PageBreak(),
            *_content_header("Security Profiles", page_meta, styles),
            Paragraph("Technical Setups", styles["section"]),
            _comparison_technical_cards(result, styles),
            Paragraph("Company Snapshots", styles["section"]),
            _comparison_fundamental_cards(result, styles),
            Paragraph("How to Use This Preference", styles["section"]),
            Paragraph(
                "The highlighted preference is a comparison of the evidence available for both securities at the stated time. It is not an absolute recommendation. Portfolio role, concentration, taxes, liquidity needs, and risk capacity can change which security is more appropriate.",
                styles["body"],
            ),
        ]
        story += _sources_and_disclosure_story(result, styles, comparison=True)
        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return destination

    story += [_rating_box(result, styles, price_label="RANGE-END PRICE" if custom_range else "CURRENT PRICE")]
    story += [Paragraph("Investment Summary", styles["section"])]
    request_card = _request_answer_card(result, request, styles)
    if request_card is not None:
        story += [request_card, Spacer(1, 0.07 * inch)]
    story += [
        Paragraph(
            f"<b>Overall Conclusion:</b> {_safe(_first_sentence(_overall_conclusion_text(result.executive_summary)))}",
            styles["conclusion"],
        ),
    ]
    if result.overview_chart and Path(result.overview_chart.path).is_file():
        story += [Spacer(1, 0.04 * inch), Paragraph(_safe(result.overview_chart.title), styles["subsection"])]
        overview_image = Image(result.overview_chart.path)
        overview_image._restrictSize(7.25 * inch, 3.55 * inch)
        story.append(overview_image)
    story += [PageBreak(), *_content_header("Position and Risk Plan", page_meta, styles)]

    action_plan_story = _technical_action_plan_story(result, styles)
    if action_plan_story:
        story += [Paragraph("Technical Action Plan", styles["section"]), *action_plan_story]
    else:
        story += [
            Paragraph("Possible Investment Approaches", styles["section"]),
            Paragraph(
                "These are conditional ideas, not automatic instructions. Each approach states what price behavior to wait for and when the idea would no longer make sense.",
                styles["body"],
            ),
        ]
        strategy_table = _strategy_cards(result, styles)
        if strategy_table is not None:
            story.append(strategy_table)
    portfolio_fit_box = _portfolio_fit_box(result, styles)
    if portfolio_fit_box is not None:
        story += [Paragraph("Portfolio Role", styles["section"]), portfolio_fit_box]
    overview_uses_primary_chart = bool(
        result.overview_chart
        and result.chart_path
        and Path(result.overview_chart.path) == Path(result.chart_path)
    )
    if result.chart_path and Path(result.chart_path).is_file() and not overview_uses_primary_chart:
        story.append(Paragraph("Technical Price Structure", styles["section"]))
        primary_chart = Image(result.chart_path)
        primary_chart._restrictSize(7.15 * inch, 3.25 * inch)
        story.append(primary_chart)
    if request.deep_analysis and result.chartbook:
        story += _chartbook_story(result, styles)
    if request.historical_trade_examples:
        story += _historical_trade_story(result, styles)
    story += [PageBreak(), *_content_header("Research Evidence", page_meta, styles)]
    story.append(KeepTogether([Paragraph("Analysis and Decision Framework", styles["section"]), _analysis_cards(result, styles)]))
    if result.sentiment:
        story += [Paragraph("Sentiment and Narrative", styles["section"]), Paragraph(_safe(result.sentiment), styles["body"])]
    story += [Paragraph("Research Watchlist", styles["section"]), _research_watchlist(result, styles)]

    story += [PageBreak(), *_content_header("Key Data and Levels", page_meta, styles)]
    story.append(
        Paragraph(
            "The figures below are organized by decision use so entry levels, technical evidence, and company data can be reviewed independently.",
            styles["body"],
        )
    )
    story += _organized_metric_story(result, styles)
    metric_note = _key_metric_note(result, styles)
    if metric_note is not None:
        story.append(metric_note)
    story += _sources_and_disclosure_story(result, styles)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return destination
