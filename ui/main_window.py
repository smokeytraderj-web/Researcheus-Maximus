"""Runnable single-stock research desktop flow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models import Horizon, ResearchRequest
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
        self.stack.addWidget(self.intake_page)
        self.stack.addWidget(self.review_page)
        self.stack.addWidget(self.preview_page)
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
        demo = QLabel("LIVE RESEARCH • LOCAL ANALYSIS")
        demo.setStyleSheet("color: #F0D49A; font-weight: 700;")
        row.addWidget(demo)
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
        page, outer = self._page_shell("Single Stock Research", "Resolve a security, select a horizon, and prepare client-ready research.")
        card = QFrame(objectName="Card")
        form = QFormLayout(card)
        form.setContentsMargins(26, 24, 26, 24)
        form.setVerticalSpacing(16)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Company or ticker — e.g., Axon or AXON")
        self.horizon = QComboBox()
        self.horizon.addItems([item.value for item in Horizon])
        self.purchase = QDoubleSpinBox()
        self.purchase.setRange(0, 1_000_000)
        self.purchase.setDecimals(2)
        self.purchase.setSpecialValueText("Not provided")
        self.quantity = QDoubleSpinBox()
        self.quantity.setRange(0, 1_000_000_000)
        self.quantity.setDecimals(4)
        self.quantity.setSpecialValueText("Not provided")
        self.risk = QComboBox()
        self.risk.addItems(["Not provided", "Conservative", "Moderate", "Aggressive"])
        self.question = QTextEdit()
        self.question.setPlaceholderText("Optional question or research emphasis")
        self.question.setMaximumHeight(90)
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
        form.addRow("Company or ticker *", self.query)
        form.addRow("Investment horizon *", self.horizon)
        form.addRow("Purchase price", self.purchase)
        form.addRow("Quantity", self.quantity)
        form.addRow("Risk tolerance", self.risk)
        form.addRow("Custom question", self.question)
        form.addRow("Research mode", self.research_mode)
        form.addRow("Synthesis provider", self.synthesis_provider)
        form.addRow("OpenAI API key", self.api_key)
        form.addRow("Model override", self.model_name)
        form.addRow("YCharts", self.use_ycharts)
        outer.addWidget(card)
        note = QLabel("Live mode retrieves market history and fundamentals, calculates indicators locally, builds an annotated chart, and uses OpenAI web research or local Ollama when configured. YCharts and TradingView links remain visible for source review.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #8A632B; padding: 4px;")
        outer.addWidget(note)
        outer.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        run = QPushButton("Prepare Evidence Review")
        run.clicked.connect(self._start_research)
        actions.addWidget(run)
        outer.addLayout(actions)
        return page

    def _build_review(self) -> QWidget:
        page, outer = self._page_shell("Evidence Review", "Confirm the resolved security and preliminary analysis before creating the PDF.")
        self.review_browser = QTextBrowser()
        self.review_browser.setOpenExternalLinks(True)
        outer.addWidget(self.review_browser, 1)
        actions = QHBoxLayout()
        back = QPushButton("Back", objectName="Secondary")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        approve = QPushButton("Approve & Generate PDF", objectName="Gold")
        approve.clicked.connect(self._approve)
        actions.addWidget(back)
        actions.addStretch()
        actions.addWidget(approve)
        outer.addLayout(actions)
        return page

    def _build_preview(self) -> QWidget:
        page, outer = self._page_shell("Research Preview", "Review the completed PDF before finalizing it.")
        self.preview_browser = QTextBrowser()
        self.preview_browser.setOpenExternalLinks(True)
        outer.addWidget(self.preview_browser, 1)
        actions = QHBoxLayout()
        restart = QPushButton("Cancel & Start Over", objectName="Secondary")
        restart.clicked.connect(self._cancel)
        revise = QPushButton("Revise Research", objectName="Secondary")
        revise.clicked.connect(self._revise)
        open_pdf = QPushButton("Open PDF")
        open_pdf.clicked.connect(self._open_pdf)
        finalize = QPushButton("Finalize Research", objectName="Gold")
        finalize.clicked.connect(self._finalize)
        actions.addWidget(restart)
        actions.addWidget(revise)
        actions.addStretch()
        actions.addWidget(open_pdf)
        actions.addWidget(finalize)
        outer.addLayout(actions)
        return page

    def _request(self) -> ResearchRequest:
        purchase = self.purchase.value() or None
        quantity = self.quantity.value() or None
        risk = "" if self.risk.currentIndex() == 0 else self.risk.currentText()
        return ResearchRequest(self.query.text(), Horizon(self.horizon.currentText()), purchase, quantity, risk, self.question.toPlainText().strip())

    def _start_research(self) -> None:
        try:
            request = self._request()
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
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setFormat("Preparing evidence…")
        self.statusBar().addPermanentWidget(progress)
        self.worker = ResearchWorker(self.runner, request, self)
        self.worker.completed.connect(lambda prepared: self._research_ready(prepared, progress))
        self.worker.failed.connect(lambda message: self._research_failed(message, progress))
        self.worker.start()

    def _research_ready(self, prepared: PreparedResearch, progress: QProgressBar) -> None:
        self.statusBar().removeWidget(progress)
        progress.deleteLater()
        self.prepared = prepared
        r = prepared.result
        signals = "".join(f"<li>{item}</li>" for item in r.technical.signals)
        fundamentals = "".join(f"<li>{item}</li>" for item in r.fundamental.signals)
        limitations = "".join(f"<li>{item}</li>" for item in r.limitations)
        source_links = "".join(f"<li><a href='{item.locator}'>{item.name}</a> — {item.supports}</li>" for item in r.sources if item.locator.startswith(("https://", "http://")))
        self.review_browser.setHtml(f"""
            <h2>{r.identity.company_name} ({r.identity.ticker})</h2>
            <p><b>Exchange:</b> {r.identity.exchange} &nbsp; <b>Currency:</b> {r.identity.currency}<br>
            <b>Horizon:</b> {r.horizon.value} &nbsp; <b>As of:</b> {r.as_of}<br>
            <b>Illustrative current price:</b> ${r.current_price:,.2f}</p>
            <hr><h3>Preliminary ratings</h3>
            <p><b>Technical:</b> {r.technical.rating.value}<br>
            <b>Fundamental:</b> {r.fundamental.rating.value}<br>
            <b>Lead:</b> {r.lead_rating.value} ({r.confidence.value} confidence)</p>
            <h3>Technical signals</h3><ul>{signals}</ul>
            <h3>Fundamental signals</h3><ul>{fundamentals}</ul>
            <h3>Sentiment</h3><p>{r.sentiment}</p>
            <h3>Research provider</h3><p>{r.provider_label}</p>
            <h3>Sources and direct review links</h3><ul>{source_links}</ul>
            <h3>Limitations and source gaps</h3><ul>{limitations or '<li>None reported.</li>'}</ul>
            {"<p style='color:#8A632B'><b>Blocking limitation:</b> Demo mode uses synthetic values and contains no live YCharts, TradingView, SEC, news, or social evidence.</p>" if r.demo_mode else ""}
        """)
        self.stack.setCurrentIndex(1)

    def _research_failed(self, message: str, progress: QProgressBar) -> None:
        self.statusBar().removeWidget(progress)
        progress.deleteLater()
        QMessageBox.critical(self, "Research failed", message)

    def _approve(self) -> None:
        if not self.prepared:
            return
        path = self.prepared.preview_path
        mode_note = "<p style='color:#8A632B'><b>Demo mode:</b> The report is for application testing only.</p>" if self.prepared.result.demo_mode else "<p><b>Live research:</b> Review every source, limitation, and rating before finalization.</p>"
        self.preview_browser.setHtml(f"<h2>PDF ready for review</h2><p><b>{self.prepared.suggested_filename}</b></p><p>The branded report passed structural PDF validation.</p>{mode_note}<p>Use <b>Open PDF</b> for the complete rendered preview, then finalize it to a folder you select.</p>")
        self.stack.setCurrentIndex(2)

    def _open_pdf(self) -> None:
        if self.prepared:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.prepared.preview_path)))

    def _finalize(self) -> None:
        if not self.prepared:
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
        if self.prepared:
            self.runner.cancel(self.prepared)
            self.prepared = None
        self.stack.setCurrentIndex(0)

    def _revise(self) -> None:
        if self.prepared:
            self.runner.cancel(self.prepared)
            self.prepared = None
        self.stack.setCurrentIndex(0)

    def closeEvent(self, event) -> None:
        if self.prepared:
            self.runner.cancel(self.prepared)
            self.prepared = None
        event.accept()
