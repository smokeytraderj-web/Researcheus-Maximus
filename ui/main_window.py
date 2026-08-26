"""Runnable investment-research desktop flow."""

from __future__ import annotations

from dataclasses import replace
from html import escape
from pathlib import Path
import traceback

from PySide6.QtCore import QSettings, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.assessments import assessment_interpretation, fundamental_outlook, technical_setup
from core.models import Horizon, ResearchRequest
from core.research_prompt import (
    append_revision_instructions,
    classify_research_intent,
    parse_comparison_prompt,
    parse_custom_range,
    parse_deep_analysis_prompt,
    parse_research_prompt,
)
from research.demo_provider import DemoResearchProvider
from research.live_provider import LiveResearchProvider
from services.research_runner import PreparedResearch, ResearchRunner


class ResearchWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, runner: ResearchRunner, request: ResearchRequest, parent=None):
        super().__init__(parent)
        self.runner = runner
        self.request = request

    def run(self) -> None:
        try:
            self.completed.emit(self.runner.prepare(self.request))
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc) or "Research preparation failed.")


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Researcheus Maximus")
        self.resize(1120, 760)
        self.setMinimumSize(900, 640)
        self.runner = ResearchRunner()
        self.prepared: PreparedResearch | None = None
        self.worker: ResearchWorker | None = None
        self.settings = QSettings("GottfriedSomberg", "ResearcheusMaximus")

        root = QWidget(objectName="AppRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._topbar())
        self.stack = QStackedWidget()
        self.intake_page = self._build_intake()
        self.review_page = self._build_review()
        self.preview_page = self._build_preview()
        self.deep_analysis_page = self._build_deep_analysis()
        self.comparison_page = self._build_comparison()
        self.stack.addWidget(self.intake_page)
        self.stack.addWidget(self.review_page)
        self.stack.addWidget(self.preview_page)
        self.stack.addWidget(self.deep_analysis_page)
        self.stack.addWidget(self.comparison_page)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

    def _topbar(self) -> QFrame:
        frame = QFrame(objectName="TopBar")
        frame.setFixedHeight(56)
        row = QHBoxLayout(frame)
        row.setContentsMargins(28, 8, 28, 8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(QLabel("RESEARCHEUS", objectName="Brand"))
        titles.addWidget(QLabel("GOTTFRIED & SOMBERG WEALTH MANAGEMENT", objectName="Firm"))
        row.addLayout(titles)
        row.addStretch()
        row.addWidget(QLabel("INVESTMENT RESEARCH", objectName="Workspace"))
        return frame

    def _page_shell(self, title: str, subtitle: str):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(10)
        outer.addWidget(QLabel(title, objectName="Title"))
        outer.addWidget(QLabel(subtitle, objectName="Subtitle"))
        return page, outer

    def _build_intake(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(32, 24, 32, 22)
        outer.setSpacing(0)

        self.research_mode = QComboBox()
        self.research_mode.addItems(["Live Market Research", "Demo / Offline Test"])
        self.synthesis_provider = QComboBox()
        self.synthesis_provider.addItems(["Automatic", "OpenAI", "Ollama", "Deterministic"])
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Optional; used in memory only and never saved")
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("Optional model override")
        self.use_ycharts = QCheckBox("Query the installed YCharts Excel add-in")
        self.use_ycharts.setChecked(True)
        self.settings_dialog = self._build_settings_dialog()

        content = QWidget()
        content.setMinimumWidth(700)
        content.setMaximumWidth(880)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        heading_row = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addWidget(QLabel("Research Workspace", objectName="Title"))
        heading.addWidget(QLabel("Research one security, build a chart study, or compare two opportunities.", objectName="Subtitle"))
        heading_row.addLayout(heading)
        heading_row.addStretch()
        settings_button = QPushButton("Settings", objectName="Settings")
        settings_button.clicked.connect(self.settings_dialog.open)
        heading_row.addWidget(settings_button)
        content_layout.addLayout(heading_row)

        card = QFrame(objectName="PrimaryPanel")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 18, 22, 18)
        card_layout.setSpacing(9)
        card_layout.addWidget(QLabel("QUICK RESEARCH", objectName="Eyebrow"))
        prompt = QLabel("What would you like to know?", objectName="PrimaryTitle")
        helper = QLabel(
            "Ask a natural-language question about any stock or fund.",
            objectName="FieldHelp",
        )
        helper.setWordWrap(True)
        self.query = QPlainTextEdit()
        self.query.setPlaceholderText(
            "Example: Full analysis of TSLA — is it a good opportunity to buy?"
        )
        self.query.setObjectName("ResearchQuery")
        self.query.setMinimumHeight(72)
        begin = QPushButton("Generate Research", objectName="Gold")
        begin.setMinimumHeight(40)
        begin.setFixedWidth(176)
        begin.clicked.connect(lambda: self._start_research())
        card_layout.addWidget(prompt)
        card_layout.addWidget(helper)
        card_layout.addWidget(self.query)
        overview_actions = QHBoxLayout()
        overview_hint = QLabel("Buy · Sell · Hold · Position review · Full analysis", objectName="FieldHelp")
        overview_actions.addWidget(overview_hint)
        overview_actions.addStretch()
        overview_actions.addWidget(begin)
        card_layout.addLayout(overview_actions)
        content_layout.addWidget(card)

        tools_heading = QHBoxLayout()
        tools_heading.addWidget(QLabel("Advanced tools", objectName="Section"))
        tools_heading.addStretch()
        tools_heading.addWidget(QLabel("For focused technical or side-by-side work", objectName="FieldHelp"))
        content_layout.addLayout(tools_heading)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)
        deep_panel = QFrame(objectName="ToolPanel")
        deep_layout = QVBoxLayout(deep_panel)
        deep_layout.setContentsMargins(20, 17, 20, 17)
        deep_layout.setSpacing(6)
        deep_layout.addWidget(QLabel("TECHNICAL", objectName="Eyebrow"))
        deep_title = QLabel("Deep Technical Analysis", objectName="Section")
        deep_title.setWordWrap(True)
        deep_description = QLabel(
            "Charts, custom ranges, Fibonacci, momentum, risk, and benchmarks.",
            objectName="Subtitle",
        )
        deep_description.setWordWrap(True)
        deep_button = QPushButton("Open Technical Analysis", objectName="ToolAction")
        deep_button.setMinimumHeight(38)
        deep_button.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        deep_layout.addWidget(deep_title)
        deep_layout.addWidget(deep_description)
        deep_layout.addStretch()
        deep_layout.addWidget(deep_button)

        compare_panel = QFrame(objectName="ToolPanel")
        compare_layout = QVBoxLayout(compare_panel)
        compare_layout.setContentsMargins(20, 17, 20, 17)
        compare_layout.setSpacing(6)
        compare_layout.addWidget(QLabel("COMPARISON", objectName="Eyebrow"))
        compare_title = QLabel("Compare Securities", objectName="Section")
        compare_title.setWordWrap(True)
        compare_description = QLabel(
            "Compare two stocks or funds across value, growth, technical setup, and risk.",
            objectName="Subtitle",
        )
        compare_description.setWordWrap(True)
        compare_button = QPushButton("Open Comparison", objectName="ToolAction")
        compare_button.setMinimumHeight(38)
        compare_button.clicked.connect(lambda: self.stack.setCurrentIndex(4))
        compare_layout.addWidget(compare_title)
        compare_layout.addWidget(compare_description)
        compare_layout.addStretch()
        compare_layout.addWidget(compare_button)

        mode_row.addWidget(deep_panel, 1)
        mode_row.addWidget(compare_panel, 1)
        content_layout.addLayout(mode_row)

        centered = QHBoxLayout()
        centered.addStretch()
        centered.addWidget(content)
        centered.addStretch()
        outer.addStretch(1)
        outer.addLayout(centered)
        outer.addStretch(2)
        return page

    def _build_comparison(self) -> QWidget:
        page, outer = self._page_shell(
            "Compare Securities",
            "Compare two stocks or funds with one transparent, side-by-side decision framework.",
        )
        outer.addStretch(1)
        card = QFrame(objectName="Card")
        card.setMaximumWidth(880)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 28, 34, 28)
        card_layout.setSpacing(12)
        card_layout.addWidget(QLabel("What would you like to compare?", objectName="Section"))
        self.comparison_query = QPlainTextEdit()
        self.comparison_query.setObjectName("ComparisonQuery")
        self.comparison_query.setMinimumHeight(168)
        self.comparison_query.setPlaceholderText(
            "Name two securities, then add the decision you are considering.\n\n"
            "Example: AVGO vs NVDA - Which currently offers better value and risk-adjusted opportunity from January 2024 to today?"
        )
        explanation = QLabel(
            "The report compares only like-for-like available evidence, including Fibonacci-based technical setup, relative performance, valuation, growth, margins, analyst-target upside, and fund costs when applicable.",
            objectName="Subtitle",
        )
        explanation.setWordWrap(True)
        card_layout.addWidget(self.comparison_query)
        card_layout.addWidget(explanation)
        actions = QHBoxLayout()
        back = QPushButton("Back to Overview", objectName="Secondary")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        run = QPushButton("Run Comparison", objectName="Gold")
        run.clicked.connect(lambda: self._start_research(comparison=True))
        actions.addWidget(back)
        actions.addStretch()
        actions.addWidget(run)
        card_layout.addLayout(actions)
        centered = QHBoxLayout()
        centered.addStretch()
        centered.addWidget(card)
        centered.addStretch()
        outer.addLayout(centered)
        outer.addStretch(2)
        return page

    def _build_deep_analysis(self) -> QWidget:
        page, outer = self._page_shell(
            "Deep Technical Analysis",
            "Request specific real-market charts, compare a stock with peers or benchmarks, and build a chart-led decision report.",
        )
        outer.addStretch(1)
        card = QFrame(objectName="Card")
        card.setMaximumWidth(880)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 28, 34, 28)
        card_layout.setSpacing(12)
        card_layout.addWidget(QLabel("What would you like to analyze?", objectName="Section"))
        self.deep_query = QPlainTextEdit()
        self.deep_query.setObjectName("DeepResearchQuery")
        self.deep_query.setMinimumHeight(168)
        self.deep_query.setPlaceholderText(
            "Start with the primary ticker, then describe the analysis and comparison symbols.\n\n"
            "Example: AVGO - Compare with NVDA and SPY from 2024-01-01 to 2026-08-26. Analyze Fibonacci, trend, RSI, MACD, relative performance, drawdown, and volatility."
        )
        supported = QLabel(
            "Use phrases such as “from 2024-01-01 to 2025-12-31,” “from January 2024 to June 2025,” or “since March 2024.” Fibonacci automatically uses the selected range. SPY is used when no benchmark is named.",
            objectName="Subtitle",
        )
        supported.setWordWrap(True)
        card_layout.addWidget(self.deep_query)
        card_layout.addWidget(supported)
        actions = QHBoxLayout()
        back = QPushButton("Back to Overview", objectName="Secondary")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        run = QPushButton("Run Deep Analysis", objectName="Gold")
        run.clicked.connect(lambda: self._start_research(deep=True))
        actions.addWidget(back)
        actions.addStretch()
        actions.addWidget(run)
        card_layout.addLayout(actions)
        centered = QHBoxLayout()
        centered.addStretch()
        centered.addWidget(card)
        centered.addStretch()
        outer.addLayout(centered)
        outer.addStretch(2)
        return page

    def _build_settings_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setWindowTitle("Research Settings")
        dialog.setMinimumWidth(560)
        outer = QVBoxLayout(dialog)
        title = QLabel("Research Settings", objectName="Section")
        description = QLabel("These defaults apply automatically to each research session. API keys are used in memory only and are never saved.")
        description.setWordWrap(True)
        description.setObjectName("Subtitle")
        outer.addWidget(title)
        outer.addWidget(description)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Research mode", self.research_mode)
        form.addRow("Synthesis provider", self.synthesis_provider)
        form.addRow("OpenAI API key", self.api_key)
        form.addRow("Model override", self.model_name)
        form.addRow("YCharts", self.use_ycharts)
        outer.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.close)
        outer.addWidget(buttons)
        return dialog

    def _build_review(self) -> QWidget:
        page, outer = self._page_shell("Evidence Review", "Confirm the resolved security and preliminary analysis before creating the PDF.")
        self.review_browser = QTextBrowser()
        self.review_browser.setOpenExternalLinks(True)
        outer.addWidget(self.review_browser, 1)
        actions = QHBoxLayout()
        back = QPushButton("Back", objectName="Secondary")
        back.clicked.connect(self._back_to_request)
        approve = QPushButton("Approve & Generate PDF", objectName="Gold")
        approve.clicked.connect(self._approve)
        actions.addWidget(back)
        actions.addStretch()
        actions.addWidget(approve)
        outer.addLayout(actions)
        return page

    def _build_preview(self) -> QWidget:
        page, outer = self._page_shell(
            "Finalize Research",
            "Open the completed PDF, request any final changes, or save the approved report.",
        )
        self.preview_browser = QTextBrowser()
        self.preview_browser.setOpenExternalLinks(True)
        outer.addWidget(self.preview_browser, 1)
        revision_label = QLabel("Requested Modifications", objectName="Section")
        revision_help = QLabel(
            "Optional — describe the exact changes you want, then regenerate the report.",
            objectName="Subtitle",
        )
        self.modification_request = QPlainTextEdit()
        self.modification_request.setObjectName("ModificationRequest")
        self.modification_request.setPlaceholderText(
            "Example: Emphasize downside risks, make the investment view more concise, and use a more conservative entry strategy."
        )
        self.modification_request.setMaximumHeight(92)
        outer.addWidget(revision_label)
        outer.addWidget(revision_help)
        outer.addWidget(self.modification_request)
        actions = QHBoxLayout()
        restart = QPushButton("Cancel & Start Over", objectName="Secondary")
        restart.clicked.connect(self._cancel)
        open_pdf = QPushButton("Open PDF")
        open_pdf.clicked.connect(self._open_pdf)
        apply_changes = QPushButton("Apply Changes & Regenerate", objectName="Secondary")
        apply_changes.clicked.connect(self._apply_modifications)
        finalize = QPushButton("Finalize Research", objectName="Gold")
        finalize.clicked.connect(self._finalize)
        actions.addWidget(restart)
        actions.addStretch()
        actions.addWidget(open_pdf)
        actions.addWidget(apply_changes)
        actions.addWidget(finalize)
        outer.addLayout(actions)
        return page

    def _request(self, *, deep: bool = False, comparison: bool = False) -> ResearchRequest:
        if comparison:
            primary, secondary, brief = parse_comparison_prompt(self.comparison_query.toPlainText())
            custom_start, custom_end = parse_custom_range(brief)
            return ResearchRequest(
                primary,
                Horizon.ALL,
                question=brief,
                comparison_analysis=True,
                comparison_query=secondary,
                custom_start=custom_start,
                custom_end=custom_end,
                decision_intent=classify_research_intent(brief),
            )
        if deep:
            security_query, brief, comparisons, charts = parse_deep_analysis_prompt(self.deep_query.toPlainText())
            custom_start, custom_end = parse_custom_range(brief)
            return ResearchRequest(
                security_query,
                Horizon.ALL,
                question=brief,
                deep_analysis=True,
                comparison_symbols=comparisons,
                requested_charts=charts,
                custom_start=custom_start,
                custom_end=custom_end,
                decision_intent=classify_research_intent(brief),
            )
        security_query, research_brief = parse_research_prompt(self.query.toPlainText())
        custom_start, custom_end = parse_custom_range(research_brief)
        return ResearchRequest(
            security_query,
            Horizon.ALL,
            question=research_brief,
            custom_start=custom_start,
            custom_end=custom_end,
            decision_intent=classify_research_intent(research_brief),
        )

    def _start_research(self, *, deep: bool = False, comparison: bool = False) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Research in progress", "Please wait for the current research run to finish.")
            return
        active_query = self.comparison_query if comparison else self.deep_query if deep else self.query
        if not active_query.toPlainText().strip():
            QMessageBox.warning(self, "Choose a stock", "Enter a company name or ticker.")
            return
        try:
            request = self._request(deep=deep, comparison=comparison)
            request.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Check input", str(exc))
            return
        if self.research_mode.currentText().startswith("Live"):
            self.runner = ResearchRunner(
                provider=LiveResearchProvider(
                    self.synthesis_provider.currentText(),
                    self.api_key.text().strip(),
                    self.model_name.text().strip(),
                    self.use_ycharts.isChecked(),
                )
            )
        else:
            self.runner = ResearchRunner(provider=DemoResearchProvider())
        self._run_request(request, replacing=self.prepared)

    def _run_request(self, request: ResearchRequest, *, replacing: PreparedResearch | None = None) -> None:
        progress = QProgressBar()
        progress.setRange(0, 0)
        if replacing:
            progress.setFormat("Applying requested changes…")
        elif request.comparison_analysis:
            progress.setFormat("Comparing securities…")
        elif request.deep_analysis:
            progress.setFormat("Building technical chartbook…")
        else:
            progress.setFormat("Preparing evidence…")
        self.statusBar().addPermanentWidget(progress)
        self.worker = ResearchWorker(self.runner, request, self)
        self.worker.completed.connect(
            lambda prepared: self._research_ready(prepared, progress, replacing=replacing)
        )
        self.worker.failed.connect(
            lambda message: self._research_failed(message, progress, keep_preview=bool(replacing))
        )
        self.worker.start()

    def _back_to_request(self) -> None:
        if self.prepared and self.prepared.request.comparison_analysis:
            self.stack.setCurrentIndex(4)
        elif self.prepared and self.prepared.request.deep_analysis:
            self.stack.setCurrentIndex(3)
        else:
            self.stack.setCurrentIndex(0)

    def _research_ready(
        self,
        prepared: PreparedResearch,
        progress: QProgressBar,
        *,
        replacing: PreparedResearch | None = None,
    ) -> None:
        self.statusBar().removeWidget(progress)
        progress.deleteLater()
        if replacing:
            self.runner.cancel(replacing)
            self.modification_request.clear()
        self.prepared = prepared
        r = prepared.result
        ycharts_alert = ""
        if r.ycharts_status and not r.ycharts_status.startswith("YCharts connected") and not r.demo_mode:
            ycharts_alert = f"""
                <div style='background:#FFF4D6; border:1px solid #D7A84B; padding:10px; margin-bottom:10px;'>
                    <b>YCharts data alert</b><br>{escape(r.ycharts_status)}
                    <br><span style='font-size:10px'>Open desktop Excel, confirm both YCharts add-ins are active and signed in, then retry if these fields are important to the decision.</span>
                </div>
            """
        interpretation = assessment_interpretation(r.technical.rating, r.fundamental.rating)
        signals = "".join(f"<li>{item}</li>" for item in r.technical.signals)
        fundamentals = "".join(f"<li>{item}</li>" for item in r.fundamental.signals)
        operational_ycharts_terms = ("ycharts", "excel returned", "excel automation", "add-in", "addin", "#name?")
        display_limitations = tuple(
            item for item in r.limitations
            if not any(term in item.lower() for term in operational_ycharts_terms)
        )
        limitations = "".join(f"<li>{escape(item)}</li>" for item in display_limitations)
        source_links = "".join(f"<li><a href='{item.locator}'>{item.name}</a> — {item.supports}</li>" for item in r.sources if item.locator.startswith(("https://", "http://")))
        loaded_ycharts_audit = tuple(
            row for row in r.ycharts_audit if row[2].startswith("Loaded")
        )
        ycharts_rows = "".join(
            f"<tr><td><b>{escape(cell)}</b></td><td><code>{escape(formula)}</code></td><td>{escape(status)}</td></tr>"
            for cell, formula, status in loaded_ycharts_audit
        )
        ycharts_audit = ""
        if ycharts_rows:
            ycharts_audit = f"""
                <h3>YCharts Excel Formula Audit</h3>
                <p>The temporary workbook uses columns A:G; calculated results are in F2:F9. These are the rows that loaded and entered the analysis.</p>
                <table cellspacing='0' cellpadding='6' border='1'>
                    <tr><th>Result cell</th><th>Exact formula</th><th>Status</th></tr>{ycharts_rows}
                </table>
            """
        chartbook_items = "".join(
            f"<li><b>{escape(chart.title)}</b> - {escape(chart.insight)}</li>" for chart in r.chartbook
        )
        deep_analysis = ""
        if r.chartbook:
            comparisons = ", ".join(prepared.request.comparison_symbols)
            deep_analysis = f"""
                <h3>Deep technical chartbook</h3>
                <p><b>Comparisons:</b> {escape(comparisons)}<br>
                <b>Requested charts:</b> {escape(', '.join(prepared.request.requested_charts))}</p>
                <ul>{chartbook_items}</ul>
            """
        if r.comparison:
            comparison = r.comparison
            custom_range = bool(prepared.request.custom_start and prepared.request.custom_end)
            range_line = (
                f"<b>Analysis range:</b> {escape(prepared.request.custom_start)} to {escape(prepared.request.custom_end)}<br>"
                if custom_range
                else ""
            )
            preference_label = "Range-end evidence preference" if custom_range else "Current evidence preference"
            metric_rows = "".join(
                f"<tr><td>{escape(label)}</td><td>{escape(primary)}</td><td>{escape(secondary)}</td><td><b>{escape(edge)}</b></td></tr>"
                for label, primary, secondary, edge in comparison.metrics
            )
            rationale = "".join(f"<li>{escape(item)}</li>" for item in comparison.rationale)
            primary_setup = technical_setup(r.technical.rating)
            secondary_setup = technical_setup(comparison.secondary_technical.rating)
            self.review_browser.setHtml(f"""
                {ycharts_alert}
                <h2>{escape(r.identity.ticker)} vs {escape(comparison.secondary_identity.ticker)}</h2>
                <p><b>{escape(r.identity.company_name)}</b> compared with <b>{escape(comparison.secondary_identity.company_name)}</b><br>
                {range_line}<b>Produced:</b> {escape(r.as_of)} &nbsp; <b>Mode:</b> Security Comparison</p>
                <hr><h3>{preference_label}</h3>
                <p style='font-size:18px'><b>{escape(comparison.preferred_ticker)}</b></p>
                <p>{escape(comparison.verdict)}</p><ul>{rationale}</ul>
                <p><b>Technical setup:</b> {escape(r.identity.ticker)} - {escape(primary_setup)} &nbsp; | &nbsp;
                {escape(comparison.secondary_identity.ticker)} - {escape(secondary_setup)}</p>
                <h3>Side-by-side evidence</h3>
                <table cellspacing='0' cellpadding='6' border='1'>
                    <tr><th>Metric</th><th>{escape(r.identity.ticker)}</th><th>{escape(comparison.secondary_identity.ticker)}</th><th>Current edge</th></tr>
                    {metric_rows}
                </table>
                {ycharts_audit}
                <h3>Sources and direct review links</h3><ul>{source_links}</ul>
                <h3>Limitations and source gaps</h3><ul>{limitations or '<li>None reported.</li>'}</ul>
                {"<p style='color:#8A632B'><b>Demo mode:</b> Values are synthetic and are for workflow testing only.</p>" if r.demo_mode else ""}
            """)
            self.stack.setCurrentIndex(1)
            return
        self.review_browser.setHtml(f"""
            {ycharts_alert}
            <h2>{r.identity.company_name} ({r.identity.ticker})</h2>
            <p><b>Exchange:</b> {r.identity.exchange} &nbsp; <b>Currency:</b> {r.identity.currency}<br>
            <b>Horizon:</b> {r.horizon.value} &nbsp; <b>As of:</b> {r.as_of}<br>
            <b>Mode:</b> {r.analysis_mode}<br>
            {f'<b>Analysis range:</b> {escape(prepared.request.custom_start)} to {escape(prepared.request.custom_end)}<br>' if prepared.request.custom_start else ''}
            <b>{'Range-end price' if prepared.request.custom_start else 'Current price'}:</b> ${r.current_price:,.2f}</p>
            <hr><h3>Preliminary recommendation</h3>
            <p><b>Overall rating:</b> {r.lead_rating.value} ({r.confidence.value} confidence)<br>
            <b>Technical setup:</b> {technical_setup(r.technical.rating)}<br>
            <b>Fundamental outlook:</b> {fundamental_outlook(r.fundamental.rating)}</p>
            <p><b>Interpretation:</b> {interpretation}</p>
            <h3>Technical signals</h3><ul>{signals}</ul>
            {deep_analysis}
            <h3>Fundamental signals</h3><ul>{fundamentals}</ul>
            <h3>Sentiment</h3><p>{r.sentiment}</p>
            <h3>Research provider</h3><p>{r.provider_label}</p>
            {ycharts_audit}
            <h3>Sources and direct review links</h3><ul>{source_links}</ul>
            <h3>Limitations and source gaps</h3><ul>{limitations or '<li>None reported.</li>'}</ul>
            {"<p style='color:#8A632B'><b>Blocking limitation:</b> Demo mode uses synthetic values and contains no live YCharts, TradingView, SEC, news, or social evidence.</p>" if r.demo_mode else ""}
        """)
        self.stack.setCurrentIndex(1)

    def _research_failed(self, message: str, progress: QProgressBar, *, keep_preview: bool = False) -> None:
        self.statusBar().removeWidget(progress)
        progress.deleteLater()
        QMessageBox.critical(self, "Research failed", message)
        if keep_preview:
            self.stack.setCurrentIndex(2)

    def _approve(self) -> None:
        if not self.prepared:
            return
        path = self.prepared.preview_path
        mode_note = "<p style='color:#8A632B'><b>Demo mode:</b> The report is for application testing only.</p>" if self.prepared.result.demo_mode else "<p><b>Live research:</b> Review every source, limitation, and rating before finalization.</p>"
        if self.prepared.request.deep_analysis:
            mode_note += f"<p><b>Deep chartbook:</b> {len(self.prepared.result.chartbook) + 1} analyzed charts, including the primary price/trend chart.</p>"
        if self.prepared.request.comparison_analysis and self.prepared.result.comparison:
            mode_note += f"<p><b>Security comparison:</b> {escape(self.prepared.result.identity.ticker)} vs {escape(self.prepared.result.comparison.secondary_identity.ticker)}, with a transparent metric-by-metric evidence table.</p>"
        self.preview_browser.setHtml(f"<h2>PDF ready for review</h2><p><b>{self.prepared.suggested_filename}</b></p><p>The branded report passed structural PDF validation.</p>{mode_note}<p>Use <b>Open PDF</b> for the complete rendered preview, then finalize it to a folder you select.</p>")
        self.stack.setCurrentIndex(2)

    def _open_pdf(self) -> None:
        if self.prepared:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.prepared.preview_path)))

    def _apply_modifications(self) -> None:
        if not self.prepared:
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Research in progress", "Please wait for the current revision to finish.")
            return
        revision = self.modification_request.toPlainText().strip()
        if not revision:
            QMessageBox.information(
                self,
                "Describe the changes",
                "Enter the report changes you want before regenerating.",
            )
            self.modification_request.setFocus()
            return
        revised_question = append_revision_instructions(self.prepared.request.question, revision)
        custom_start, custom_end = parse_custom_range(revised_question)
        revised_request = replace(
            self.prepared.request,
            question=revised_question,
            custom_start=custom_start or self.prepared.request.custom_start,
            custom_end=custom_end or self.prepared.request.custom_end,
            decision_intent=classify_research_intent(revised_question),
        )
        if revised_request.deep_analysis:
            _query, _brief, comparisons, charts = parse_deep_analysis_prompt(revised_question)
            revised_request = replace(
                revised_request,
                comparison_symbols=comparisons,
                requested_charts=charts,
            )
        elif revised_request.comparison_analysis:
            primary, secondary, _brief = parse_comparison_prompt(revised_question)
            if primary and secondary:
                revised_request = replace(
                    revised_request,
                    query=primary,
                    comparison_query=secondary,
                )
        self._run_request(revised_request, replacing=self.prepared)

    def _finalize(self) -> None:
        if not self.prepared:
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Research in progress", "Please wait for the revised report to finish.")
            return
        default = self.settings.value("outputFolder", str(Path.home() / "Documents"))
        directory = QFileDialog.getExistingDirectory(self, "Choose output folder", str(default))
        if not directory:
            return
        try:
            path = self.runner.finalize(self.prepared, Path(directory))
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.settings.setValue("outputFolder", directory)
        self.prepared = None
        QMessageBox.information(self, "Research finalized", f"Saved and verified:\n{path}")
        self.stack.setCurrentIndex(0)

    def _cancel(self) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Research in progress", "Please wait for the current research run to finish.")
            return
        if self.prepared:
            self.runner.cancel(self.prepared)
            self.prepared = None
        self.stack.setCurrentIndex(0)

    def closeEvent(self, event) -> None:
        if self.prepared:
            self.runner.cancel(self.prepared)
            self.prepared = None
        event.accept()
