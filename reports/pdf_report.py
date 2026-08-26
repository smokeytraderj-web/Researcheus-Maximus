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
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.assessments import assessment_interpretation, fundamental_outlook, technical_setup
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
        "table_header": ParagraphStyle("TableHeader", parent=base["BodyText"], fontName=bold, fontSize=6.2, leading=7.7, textColor=colors.white),
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


def _rating_box(result: ResearchResult, styles, *, price_label: str = "CURRENT PRICE") -> Table:
    box = Table(
        [
            [
                Paragraph("OVERALL RATING", styles["small"]),
                Paragraph("TECHNICAL SETUP", styles["small"]),
                Paragraph("FUNDAMENTAL OUTLOOK", styles["small"]),
                Paragraph(_safe(price_label), styles["small"]),
            ],
            [
                Paragraph(_safe(result.lead_rating.value), styles["rating"]),
                Paragraph(_safe(technical_setup(result.technical.rating)), styles["rating"]),
                Paragraph(_safe(fundamental_outlook(result.fundamental.rating)), styles["rating"]),
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
            Paragraph("Benchmark", styles["compact"]),
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
    "Range-end price",
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
            styles["small"],
        )
    return None


def _analysis_cards(result: ResearchResult, styles) -> Table:
    technical = [
        Paragraph(f"<b>Technical Setup - {_safe(technical_setup(result.technical.rating))}</b>", styles["body"]),
        Paragraph(_safe(result.technical.summary), styles["compact"]),
        *_bullet_text(result.technical.signals, styles["compact"], 3),
    ]
    fundamental = [
        Paragraph(f"<b>Fundamental Outlook - {_safe(fundamental_outlook(result.fundamental.rating))}</b>", styles["body"]),
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


def _chartbook_story(result: ResearchResult, styles) -> list:
    story = []
    for index, chart in enumerate(result.chartbook):
        if index % 2 == 0:
            story.append(PageBreak())
            heading = "Deep Technical Chartbook" if index == 0 else "Deep Technical Chartbook - Continued"
            story.append(Paragraph(heading, styles["section"]))
        story.append(Paragraph(_safe(chart.title), styles["section"]))
        image = Image(chart.path)
        trailing_single = len(result.chartbook) % 2 == 1 and index == len(result.chartbook) - 1
        image._restrictSize(7.15 * inch, (2.35 if trailing_single else 2.95) * inch)
        story.append(image)
        story.append(Paragraph(f"<b>Decision insight:</b> {_safe(chart.insight)}", styles["compact"]))
        story.append(
            Paragraph(
                "Source: attributed live price histories; calculations and chart construction by Researcheus Maximus.",
                styles["small"],
            )
        )
        story.append(Spacer(1, 0.05 * inch))
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
        f"Security Comparison | {range_text + ' | ' if range_text else ''}{_safe(result.identity.currency)} | Produced {_safe(as_of)} | Confidence: {_safe(result.confidence.value)}"
        if comparison
        else f"{_safe(result.analysis_mode if request.deep_analysis else result.horizon.value + ' research')} | {range_text + ' | ' if range_text else ''}{_safe(result.identity.exchange)} | {_safe(result.identity.currency)} | Produced {_safe(as_of)} | Confidence: {_safe(result.confidence.value)}"
    )
    story = [
        Paragraph("GOTTFRIED &amp; SOMBERG WEALTH MANAGEMENT", styles["brand"]),
        Spacer(1, 0.05 * inch),
        Paragraph(_safe(report_title), styles["title"]),
        Paragraph(report_subtitle, styles["subtitle"]),
        Spacer(1, 0.11 * inch),
    ]
    if result.demo_mode:
        warning = Table([[Paragraph("DEMO MODE - Synthetic values for workflow validation. Not live investment research.", styles["body"])]], colWidths=[7.25 * inch])
        warning.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF3D8")), ("BOX", (0, 0), (-1, -1), 0.7, GOLD), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story += [warning, Spacer(1, 0.08 * inch)]

    if comparison:
        story += [
            _comparison_preference_box(result, styles, historical_range=historical_range),
            Paragraph("Comparison View", styles["section"]),
            Paragraph(_safe(comparison.verdict), styles["body"]),
            *_bullet_text(comparison.rationale, styles["compact"]),
        ]
        if request.question:
            story.append(Paragraph(f"<b>Research question:</b> {_safe(request.question)}", styles["small"]))
        performance_summary = _comparison_performance_summary(result, styles)
        if performance_summary is not None:
            story += [Paragraph("Performance Difference", styles["section"]), performance_summary]
        if result.chart_path and Path(result.chart_path).is_file():
            comparison_chart = Image(result.chart_path)
            comparison_chart._restrictSize(7.2 * inch, 4.35 * inch)
            story += [
                Spacer(1, 0.07 * inch),
                comparison_chart,
                Paragraph(
                    (
                        "Source: attributed live price histories; series normalized to 100 on their first common trading date. "
                        + (
                            f"Sector benchmark: {_safe(comparison.benchmark_label)} ({_safe(comparison.benchmark_ticker)})."
                            if comparison.benchmark_ticker
                            else ""
                        )
                    ),
                    styles["small"],
                ),
            ]
        story += [
            PageBreak(),
            Paragraph("Side-by-Side Evidence", styles["section"]),
            _comparison_metric_table(result, styles),
            PageBreak(),
            Paragraph("Technical Setups", styles["section"]),
            _comparison_technical_cards(result, styles),
            Paragraph("Company Snapshots", styles["section"]),
            _comparison_fundamental_cards(result, styles),
            Paragraph("How to Use This Preference", styles["section"]),
            Paragraph(
                "The highlighted preference is a comparison of the evidence available for both securities at the stated time. It is not an absolute recommendation. Portfolio role, concentration, taxes, liquidity needs, and risk capacity can change which security is more appropriate.",
                styles["body"],
            ),
            Paragraph("Sources", styles["section"]),
            _source_table(result, styles),
        ]
        visible_limitations = _client_visible_limitations(result)
        if visible_limitations:
            story.append(Paragraph(f"<b>Limitations:</b> {_safe(' | '.join(visible_limitations[:4]))}", styles["tiny"]))
        story.append(
            Paragraph(
                "<b>Disclosure:</b> This material is informational and reflects conditions as of the stated time. Sources are believed reliable but are not guaranteed. The comparison is limited to like-for-like available evidence and may omit unavailable factors. Investing involves risk, including possible loss of principal. Firm compliance review is required before client distribution.",
                styles["tiny"],
            )
        )
        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return destination

    interpretation = assessment_interpretation(result.technical.rating, result.fundamental.rating)
    story += [
        _rating_box(result, styles, price_label="RANGE-END PRICE" if custom_range else "CURRENT PRICE"),
        Paragraph("Investment View", styles["section"]),
        Paragraph(f"<b>Interpretation:</b> {_safe(interpretation)}", styles["body"]),
        Paragraph(_safe(result.executive_summary), styles["body"]),
    ]
    if result.chart_path and Path(result.chart_path).is_file():
        story += [
            Spacer(1, 0.06 * inch),
            Image(result.chart_path, width=7.2 * inch, height=4.75 * inch),
            Paragraph("Source: attributed live price history; indicators and annotations calculated by Researcheus Maximus.", styles["small"]),
        ]
    if request.deep_analysis and result.chartbook:
        story += _chartbook_story(result, styles)
        if len(result.chartbook) % 2 == 0:
            story.append(PageBreak())
    else:
        story.append(PageBreak())
    story.append(
        KeepTogether(
            [
                Paragraph("Analysis and Decision Framework", styles["section"]),
                _analysis_cards(result, styles),
            ]
        )
    )
    if result.sentiment:
        story.append(Paragraph(f"<b>Sentiment:</b> {_safe(result.sentiment)}", styles["small"]))
    story += [Paragraph("Key Metrics", styles["section"]), _metric_grid(result, styles)]
    metric_note = _key_metric_note(result, styles)
    if metric_note is not None:
        story.append(metric_note)
    story += [
        Paragraph("Possible Investment Approaches", styles["section"]),
        Paragraph(
            "These are conditional ideas, not automatic instructions. Each approach states what price behavior to wait for and when the idea would no longer make sense.",
            styles["small"],
        ),
    ]
    strategy_table = _strategy_cards(result, styles)
    if strategy_table is not None:
        story.append(strategy_table)
    story += [Paragraph("Research Watchlist", styles["section"]), _research_watchlist(result, styles), Paragraph("Sources", styles["section"]), _source_table(result, styles)]
    visible_limitations = _client_visible_limitations(result)
    if visible_limitations:
        limitations = " | ".join(visible_limitations[:3])
        story.append(Paragraph(f"<b>Limitations:</b> {_safe(limitations)}", styles["tiny"]))
    story.append(
        Paragraph(
            "<b>Disclosure:</b> This material is informational and reflects conditions as of the stated time. Sources are believed reliable but are not guaranteed. Opinions and scenarios may change without notice. Investing involves risk, including possible loss of principal. Firm compliance review is required before client distribution.",
            styles["tiny"],
        )
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return destination
