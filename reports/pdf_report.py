"""Branded PDF renderer for a validated research result."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.models import ResearchRequest, ResearchResult

NAVY = colors.HexColor("#14263D")
GOLD = colors.HexColor("#B08D57")
INK = colors.HexColor("#263648")
MUTED = colors.HexColor("#657386")
PALE = colors.HexColor("#F3F5F7")


def _styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("Brand", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8, textColor=GOLD, leading=10),
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=NAVY, alignment=TA_LEFT, spaceAfter=4),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontSize=9, leading=12, textColor=MUTED),
        "section": ParagraphStyle("Section", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=NAVY, spaceBefore=11, spaceAfter=6),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontSize=9, leading=13, textColor=INK, spaceAfter=5),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontSize=7.5, leading=10, textColor=MUTED),
        "rating": ParagraphStyle("Rating", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=18, leading=20, textColor=NAVY, alignment=TA_CENTER),
    }


def _footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.6)
    canvas.line(0.62 * inch, 0.48 * inch, 7.88 * inch, 0.48 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(0.62 * inch, 0.3 * inch, "Gottfried & Somberg Wealth Management")
    canvas.drawRightString(7.88 * inch, 0.3 * inch, f"Page {document.page}")
    canvas.restoreState()


def _bullets(items: tuple[str, ...], style) -> list[Paragraph]:
    return [Paragraph(f"• {item}", style) for item in items]


def build_research_pdf(result: ResearchResult, request: ResearchRequest, destination: Path) -> Path:
    result.validate()
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(
        str(destination),
        pagesize=letter,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.62 * inch,
        title=f"{result.identity.ticker} Research",
        author="Gottfried & Somberg Wealth Management",
    )
    story = [
        Paragraph("GOTTFRIED &amp; SOMBERG WEALTH MANAGEMENT", styles["brand"]),
        Spacer(1, 0.08 * inch),
        Paragraph(f"{result.identity.company_name} ({result.identity.ticker})", styles["title"]),
        Paragraph(
            f"{result.horizon.value} research • {result.identity.exchange} • {result.identity.currency} • As of {result.as_of}",
            styles["subtitle"],
        ),
        Spacer(1, 0.15 * inch),
    ]
    if result.demo_mode:
        warning = Table([[Paragraph("DEMO MODE — Synthetic values for workflow validation. Not live investment research.", styles["body"])]], colWidths=[7.25 * inch])
        warning.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF3D8")), ("BOX", (0, 0), (-1, -1), 0.8, GOLD), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        story += [warning, Spacer(1, 0.12 * inch)]

    rating_box = Table(
        [
            [Paragraph("LEAD RATING", styles["small"]), Paragraph("CONFIDENCE", styles["small"]), Paragraph("CURRENT PRICE", styles["small"])],
            [Paragraph(result.lead_rating.value, styles["rating"]), Paragraph(result.confidence.value, styles["rating"]), Paragraph(f"${result.current_price:,.2f}", styles["rating"])],
        ],
        colWidths=[2.42 * inch] * 3,
    )
    rating_box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), 0.8, NAVY), ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD2D9")), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [rating_box, Paragraph("Executive Summary", styles["section"]), Paragraph(result.executive_summary, styles["body"])]

    metrics = [[Paragraph("Metric", styles["small"]), Paragraph("Value", styles["small"])]] + [[Paragraph(a, styles["body"]), Paragraph(b, styles["body"])] for a, b in result.key_metrics]
    metric_table = Table(metrics, colWidths=[3.6 * inch, 3.65 * inch], repeatRows=1)
    metric_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7DDE3")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [Paragraph("Current Price and Key Metrics", styles["section"]), metric_table]

    for heading, finding in (("Technical Analysis", result.technical), ("Fundamental Analysis", result.fundamental)):
        block = [Paragraph(f"{heading} — {finding.rating.value}", styles["section"]), Paragraph(finding.summary, styles["body"])] + _bullets(finding.signals, styles["body"])
        story.append(KeepTogether(block))

    story += [Paragraph("News, Analyst Commentary, and Sentiment", styles["section"]), Paragraph(result.sentiment, styles["body"]), PageBreak(), Paragraph("Potential Investment Strategies", styles["section"])]
    for strategy in result.strategies:
        rows = [
            [Paragraph(strategy.name, styles["body"]), Paragraph(strategy.action_zone, styles["body"])],
            [Paragraph("Confirmation", styles["small"]), Paragraph(strategy.confirmation, styles["body"])],
            [Paragraph("Invalidation", styles["small"]), Paragraph(strategy.invalidation, styles["body"])],
            [Paragraph("Principal risk", styles["small"]), Paragraph(strategy.risk, styles["body"])],
        ]
        table = Table(rows, colWidths=[1.45 * inch, 5.8 * inch])
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), PALE), ("BOX", (0, 0), (-1, -1), 0.55, colors.HexColor("#BFC7D0")), ("INNERGRID", (0, 1), (-1, -1), 0.3, colors.HexColor("#D7DDE3")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story += [table, Spacer(1, 0.1 * inch)]

    story += [Paragraph("Risks", styles["section"])] + _bullets(result.risks, styles["body"])
    story += [Paragraph("Catalysts", styles["section"])] + _bullets(result.catalysts, styles["body"])
    story += [Paragraph("What Would Change the Rating", styles["section"])] + _bullets(result.change_conditions, styles["body"])
    story += [Paragraph("Sources", styles["section"])]
    for source in result.sources:
        story.append(Paragraph(f"{source.name} — {source.locator} — Retrieved {source.retrieved_at} — Supports: {source.supports}", styles["small"]))
    story += [
        Paragraph("Disclosure", styles["section"]),
        Paragraph(
            "This material is for informational purposes and reflects information and market conditions as of the stated time. Sources are believed reliable but are not guaranteed. Opinions and scenarios may change without notice. This report is not a guarantee of future performance. Investing involves risk, including possible loss of principal. Draft disclosure—firm compliance review is required before client distribution.",
            styles["small"],
        ),
    ]
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return destination

