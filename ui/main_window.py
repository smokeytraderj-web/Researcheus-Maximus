"""Runnable single-stock research desktop flow."""

from __future__ import annotations

from dataclasses import replace
from html import escape
from pathlib import Path
import traceback

from PySide6.QtCore import QSettings, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
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
    parse_comparison_prompt,
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
        frame.setFixedHeight(76)
        row = QHBoxLayout(frame)
        row.setContentsMargins(28, 12, 28, 12)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(QLabel("RESEARCHEUS MAXIMUS", objectName="Brand"))
        titles.addWidget(QLabel("GOTTFRIED & SOMBERG WEALTH MANAGEMENT", objectName="Firm"))
        row.addLayout(titles)
        row.addStretch()
        row.addWidget(QLabel("EQUITY RESEARCH WORKSPACE", objectName="Workspace"))
        return frame

    def _page_shell(self, title: str, subtitle: str):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(42, 32, 42, 32)
        outer.setSpacing(10)
        outer.addWidget(QLabel(title, objectName="Title"))
        outer.addWidget(QLabel(subtitle, objectName="Subtitle"))
        return page, outer

    def _build_intake(self) -> QWidget:
        page, outer = self._page_shell(
            "Single Stock Research",
            "Choose the research format that fits the decision in front of you.",
        )
        outer.addSpacing(4)
        card = QFrame(objectName="Card")
        card.setMaximumWidth(940)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(20, 38, 61, 34))
        card.setGraphicsEffect(shadow)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 26, 34, 26)
        card_layout.setSpacing(10)
        standard = QVBoxLayout()
        standard.setSpacing(9)
        standard.addWidget(QLabel("RESEARCH OVERVIEW", objectName="Eyebrow"))
        prompt = QLabel("What would you like to research?", objectName="Section")
        helper = QLabel("Enter a company or ticker and optionally add the decision you are considering.", objectName="FieldHelp")
        helper.setWordWrap(True)
        self.query = QPlainTextEdit()
        self.query.setPlaceholderText(
            "Example: WMT - Is this an attractive entry after the recent pullback?"
        )
        self.query.setObjectName("ResearchQuery")
        self.query.setMinimumHeight(104)
        begin = QPushButton("Generate Research", objectName="Gold")
        begin.setMinimumHeight(44)
        begin.clicked.connect(lambda: self._start_research())
        standard.addWidget(prompt)
        standard.addWidget(helper)
        standard.addWidget(self.query)
        standard.addWidget(begin, 0)
        card_layout.addLayout(standard)
        centered = QHBoxLayout()
        centered.addStretch()
        centered.addWidget(card)
        centered.addStretch()
        outer.addLayout(centered)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(16)
        deep_panel = QFrame(objectName="DeepPanel")
        deep_layout = QVBoxLayout(deep_panel)
        deep_layout.setContentsMargins(24, 20, 24, 20)
        deep_layout.setSpacing(8)
        deep_layout.addWidget(QLabel("DEEP ANALYSIS", objectName="Eyebrow"))
        deep_title = QLabel("Build a technical chartbook", objectName="Section")
        deep_title.setWordWrap(True)
        deep_description = QLabel(
            "Go beyond the overview with real charts and evidence tied directly to the decision.",
            objectName="Subtitle",
        )
        deep_description.setWordWrap(True)
        deep_features = QLabel(
            "Fibonacci  |  momentum  |  benchmark context  |  technical evidence",
            objectName="DeepFeatures",
        )
        deep_features.setWordWrap(True)
        deep_button = QPushButton("Open Deep Analysis", objectName="DeepAction")
        deep_button.setMinimumHeight(42)
        deep_button.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        deep_layout.addWidget(deep_title)
        deep_layout.addWidget(deep_description)
        deep_layout.addWidget(deep_features)
        deep_layout.addStretch()
        deep_layout.addWidget(deep_button)

        compare_panel = QFrame(objectName="ComparePanel")
        compare_layout = QVBoxLayout(compare_panel)
        compare_layout.setContentsMargins(24, 20, 24, 20)
        compare_layout.setSpacing(8)
        compare_layout.addWidget(QLabel("SECURITY COMPARISON", objectName="Eyebrow"))
        compare_title = QLabel("Which opportunity looks better?", objectName="Section")
        compare_title.setWordWrap(True)
        compare_description = QLabel(
            "Compare two stocks or funds across valuation, growth, technical setup, and relative performance.",
            objectName="Subtitle",
        )
        compare_description.setWordWrap(True)
        compare_features = QLabel(
            "Side-by-side metrics  |  current evidence edge  |  decision context",
            objectName="DeepFeatures",
        )
        compare_features.setWordWrap(True)
        compare_button = QPushButton("Compare Securities", objectName="CompareAction")
        compare_button.setMinimumHeight(42)
        compare_button.clicked.connect(lambda: self.stack.setCurrentIndex(4))
        compare_layout.addWidget(compare_title)
        compare_layout.addWidget(compare_description)
        compare_layout.addWidget(compare_features)
        compare_layout.addStretch()
        compare_layout.addWidget(compare_button)

        mode_row.addWidget(deep_panel, 1)
        mode_row.addWidget(compare_panel, 1)
        modes_centered = QHBoxLayout()
        modes_centered.addStretch()
        modes = QWidget()
        modes.setMaximumWidth(940)
        modes.setLayout(mode_row)
        modes_centered.addWidget(modes)
        modes_centered.addStretch()
        outer.addLayout(modes_centered)

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
        outer.addStretch(1)
        actions = QHBoxLayout()
        settings_button = QPushButton("Research Settings", objectName="Settings")
        settings_button.clicked.connect(self.settings_dialog.open)
        actions.addStretch()
        actions.addWidget(settings_button)
        outer.addLayout(actions)
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
            "Example: AVGO vs NVDA - Which currently offers better value and risk-adjusted opportunity?"
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
            "Example: AVGO - Compare against NVDA, SOXX, and SPY. Analyze trend, RSI, MACD, relative performance, drawdown, volatility, support and resistance."
        )
        supported = QLabel(
            "Every technical review includes a six-month Fibonacci swing with 38.2%, 50%, and 61.8% levels. The standard chartbook also includes price/trend, RSI/MACD, and normalized relative performance. Ask for drawdown or volatility to add a risk chart. SPY is used when no benchmark is named.",
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
            return ResearchRequest(
                primary,
                Horizon.ALL,
                question=brief,
                comparison_analysis=True,
                comparison_query=secondary,
            )
        if deep:
            security_query, brief, comparisons, charts = parse_deep_analysis_prompt(self.deep_query.toPlainText())
            return ResearchRequest(
                security_query,
                Horizon.ALL,
                question=brief,
                deep_analysis=True,
                comparison_symbols=comparisons,
                requested_charts=charts,
            )
        security_query, research_brief = parse_research_prompt(self.query.toPlainText())
        return ResearchRequest(security_query, Horizon.ALL, question=research_brief)

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
        interpretation = assessment_interpretation(r.technical.rating, r.fundamental.rating)
        signals = "".join(f"<li>{item}</li>" for item in r.technical.signals)
        fundamentals = "".join(f"<li>{item}</li>" for item in r.fundamental.signals)
        limitations = "".join(f"<li>{item}</li>" for item in r.limitations)
        source_links = "".join(f"<li><a href='{item.locator}'>{item.name}</a> — {item.supports}</li>" for item in r.sources if item.locator.startswith(("https://", "http://")))
        ycharts_rows = "".join(
            f"<tr><td><b>{escape(cell)}</b></td><td><code>{escape(formula)}</code></td><td>{escape(status)}</td></tr>"
            for cell, formula, status in r.ycharts_audit
        )
        ycharts_audit = ""
        if ycharts_rows:
            ycharts_audit = f"""
                <h3>YCharts Excel Formula Audit</h3>
                <p>The temporary workbook uses columns A:G; calculated results are in F2:F9. Only rows marked <b>Loaded</b> enter the report.</p>
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
            metric_rows = "".join(
                f"<tr><td>{escape(label)}</td><td>{escape(primary)}</td><td>{escape(secondary)}</td><td><b>{escape(edge)}</b></td></tr>"
                for label, primary, secondary, edge in comparison.metrics
            )
            rationale = "".join(f"<li>{escape(item)}</li>" for item in comparison.rationale)
            primary_setup = technical_setup(r.technical.rating)
            secondary_setup = technical_setup(comparison.secondary_technical.rating)
            self.review_browser.setHtml(f"""
                <h2>{escape(r.identity.ticker)} vs {escape(comparison.secondary_identity.ticker)}</h2>
                <p><b>{escape(r.identity.company_name)}</b> compared with <b>{escape(comparison.secondary_identity.company_name)}</b><br>
                <b>As of:</b> {escape(r.as_of)} &nbsp; <b>Mode:</b> Security Comparison</p>
                <hr><h3>Current evidence preference</h3>
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
            <h2>{r.identity.company_name} ({r.identity.ticker})</h2>
            <p><b>Exchange:</b> {r.identity.exchange} &nbsp; <b>Currency:</b> {r.identity.currency}<br>
            <b>Horizon:</b> {r.horizon.value} &nbsp; <b>As of:</b> {r.as_of}<br>
            <b>Mode:</b> {r.analysis_mode}<br>
            <b>Illustrative current price:</b> ${r.current_price:,.2f}</p>
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
        revised_request = replace(self.prepared.request, question=revised_question)
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
