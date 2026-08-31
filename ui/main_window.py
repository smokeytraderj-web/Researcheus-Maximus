"""Runnable investment-research desktop flow."""

from __future__ import annotations

from dataclasses import replace
from html import escape
from pathlib import Path
import tempfile
import traceback

from PySide6.QtCore import QObject, QSettings, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCursor, QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
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
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from core.assessments import assessment_interpretation, fundamental_outlook, technical_setup
from core.models import Horizon, ResearchRequest
from core.research_prompt import (
    append_revision_instructions,
    classify_research_intent,
    is_historical_trade_request,
    parse_comparison_prompt,
    parse_custom_range,
    parse_deep_analysis_prompt,
    parse_horizon,
    parse_overview_chart_request,
    parse_portfolio_allocation,
    parse_research_prompt,
)
from research.demo_provider import DemoResearchProvider
from research.live_provider import LiveResearchProvider
from research.ycharts_excel import retrieve_ycharts_metrics
from security import secret_store
from services.research_runner import PreparedResearch, ResearchRunner
from services.technical_runner import PreparedTechnical, TechnicalRunner
from services.track_runner import TrackRecordRunner


_METRIC_EXPLANATIONS = {
    "price": "The latest available market price, or the final price in a historical custom range.",
    "market_cap": "Market capitalization is the company's share price multiplied by shares outstanding. It is a measure of company size, not whether the stock is cheap.",
    "growth": "Revenue growth shows sales change; earnings growth shows profit change. Positive sales growth with negative earnings growth means costs or margins weakened.",
    "target_upside": "The percentage difference between the current price and the available average analyst target. It is an opinion-based reference, not a guaranteed return.",
    "ycharts_target": "The analyst price target supplied through YCharts. Zero or invalid placeholder values are removed from the report.",
    "return": "The stock's percentage price change over the stated period. It does not include every possible tax, fee, or dividend adjustment.",
    "moving_average": "A moving average smooths daily prices. Trading above it generally signals a stronger trend; below it signals a weaker trend.",
    "rsi": "RSI measures recent momentum from 0 to 100. Above 70 can indicate an extended move; below 30 can indicate an oversold move. It is not a buy or sell signal by itself.",
    "atr": "ATR estimates the stock's typical daily price movement. A larger ATR means wider normal swings and usually requires wider risk limits.",
    "fibonacci": "Fibonacci retracement levels mark potential support or resistance within the selected price swing. They are decision zones, not precise predictions.",
    "valuation": "Valuation multiples compare price with earnings, sales, book value, or cash flow. Lower can be cheaper, but may also reflect weaker business quality or growth.",
    "margin": "Margins show how much revenue remains after costs. Higher or improving margins generally indicate stronger operating efficiency.",
    "leverage": "Debt-to-equity compares reported debt with shareholder equity. Higher values generally mean greater financial leverage and balance-sheet risk.",
    "beta": "Beta estimates how strongly a stock has moved relative to the broader market. Above 1 has historically meant larger market-related swings.",
    "technical": "The technical setup summarizes trend, momentum, volatility, volume, support, resistance, and Fibonacci evidence. It supports the Overall Rating but is not a second recommendation.",
    "benchmark": "Benchmark-relative performance shows how much the stock gained or lost beyond the selected sector or market ETF over the same dates.",
    "general": "This is one supporting data point. Read it together with the trend, fundamentals, valuation, risks, and the report's Overall Rating.",
}


def _horizon_from_text(brief: str) -> Horizon:
    """The horizon stated in the question, defaulting to All Horizons."""
    stated = parse_horizon(brief)
    for horizon in Horizon:
        if horizon.value == stated:
            return horizon
    return Horizon.ALL


def _metric_help_key(label: str) -> str:
    lowered = label.lower()
    rules = (
        (("current price", "range-end price"), "price"),
        (("market capitalization",), "market_cap"),
        (("revenue growth", "earnings growth"), "growth"),
        (("ycharts price target",), "ycharts_target"),
        (("target implied upside", "target upside"), "target_upside"),
        (("return vs.", "excess return", "benchmark"), "benchmark"),
        (("return",), "return"),
        (("moving average", "sma"), "moving_average"),
        (("rsi",), "rsi"),
        (("atr", "volatility"), "atr"),
        (("fibonacci",), "fibonacci"),
        (("p/e", "price / sales", "price / book", "enterprise value", "cash flow yield"), "valuation"),
        (("margin", "return on equity"), "margin"),
        (("debt", "leverage"), "leverage"),
        (("beta",), "beta"),
        (("technical setup",), "technical"),
    )
    for phrases, key in rules:
        if any(phrase in lowered for phrase in phrases):
            return key
    return "general"


def _metric_link(label: str) -> str:
    key = _metric_help_key(label)
    return f"<a href='metric://{key}' style='color:#14263D; text-decoration:none'>{escape(label)}</a>"


_BROWSER_STYLE = """
<style>
body{font-family:'Segoe UI',Arial,sans-serif;color:#3E4759;font-size:13px;line-height:1.6}
h2{font-family:Georgia,'Times New Roman',serif;color:#1B2A4A;font-size:22px;font-weight:700;margin:0 0 6px}
h3{font-family:Georgia,'Times New Roman',serif;color:#1B2A4A;font-size:14.5px;font-weight:700;
   margin:20px 0 8px;padding-top:14px;border-top:1px solid #DDE1E7}
hr{border:0;border-top:2px solid #1B2A4A;margin:16px 0}
b{color:#1B2A4A}
p{margin:0 0 10px}
ul{margin:4px 0 10px;padding-left:20px}
li{margin-bottom:5px}
a{color:#1B2A4A}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:6px 0 14px}
th{background:#1B2A4A;color:#FFFFFF;padding:7px 9px;text-align:left;font-size:10.5px;
   text-transform:uppercase;letter-spacing:.04em}
td{padding:7px 9px;border-bottom:1px solid #EDF0F3}
</style>
"""


def _branded_html(body: str) -> str:
    """Wrap raw QTextBrowser content in the app's navy/gold/serif visual system."""
    return _BROWSER_STYLE + body


class MetricBrowser(QTextBrowser):
    """Evidence browser with a minimal plain-English metric glossary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._handle_anchor)

    def _show_metric(self, key: str, position) -> None:
        QToolTip.showText(position, _METRIC_EXPLANATIONS.get(key, _METRIC_EXPLANATIONS["general"]), self)

    def _handle_anchor(self, url: QUrl) -> None:
        if url.scheme() == "metric":
            self._show_metric(url.host() or url.path().lstrip("/"), QCursor.pos())
        else:
            QDesktopServices.openUrl(url)

    def contextMenuEvent(self, event) -> None:
        anchor = self.anchorAt(event.pos())
        url = QUrl(anchor)
        if url.scheme() == "metric":
            self._show_metric(url.host() or url.path().lstrip("/"), event.globalPos())
            event.accept()
            return
        super().contextMenuEvent(event)


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


class TechnicalWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, runner: TechnicalRunner, query: str, parent=None):
        super().__init__(parent)
        self.runner = runner
        self.query = query

    def run(self) -> None:
        try:
            self.completed.emit(self.runner.prepare(self.query))
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc) or "Technical Analysis preparation failed.")


class TrackRecordWorker(QThread):
    completed = Signal(object, object)
    failed = Signal(str)

    def __init__(self, runner: TrackRecordRunner, log_directory: Path, parent=None):
        super().__init__(parent)
        self.runner = runner
        self.log_directory = log_directory

    def run(self) -> None:
        try:
            path, session, _record = self.runner.build(self.log_directory)
            self.completed.emit(path, session)
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc) or "The track record could not be built.")


class YChartsTestWorker(QThread):
    completed = Signal(bool, str)

    def run(self) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="researcheus-ycharts-test-") as folder:
                evidence = retrieve_ycharts_metrics("SPY", Path(folder), timeout=30)
            if evidence.values:
                self.completed.emit(True, f"Connected - {len(evidence.values)} YCharts metrics loaded for SPY.")
            else:
                message = evidence.errors[0] if evidence.errors else "No YCharts values were returned."
                self.completed.emit(False, message)
        except Exception as exc:
            self.completed.emit(False, str(exc) or "YCharts connection test failed.")


class _Bridge(QObject):
    """Exposes the actions the Tailwind-rendered pages can trigger in Qt.

    Shared across the home, Deep Technical Analysis, and Comparison pages --
    each has its own QWebChannel registering this same instance as "bridge".
    """

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._window = window

    @Slot(str)
    def submitQuery(self, text: str) -> None:
        self._window.query.setPlainText(text)
        self._window._start_research()

    @Slot(str)
    def submitDeepQuery(self, text: str) -> None:
        self._window.deep_query.setPlainText(text)
        self._window._start_research(deep=True)

    @Slot(str)
    def submitComparisonQuery(self, text: str) -> None:
        self._window.comparison_query.setPlainText(text)
        self._window._start_research(comparison=True)

    @Slot(str)
    def submitTechnicalQuery(self, text: str) -> None:
        self._window.technical_query.setPlainText(text)
        self._window._start_technical_research()

    @Slot()
    def openOverview(self) -> None:
        self._window.stack.setCurrentIndex(0)

    @Slot()
    def openDeepAnalysis(self) -> None:
        self._window.stack.setCurrentIndex(3)

    @Slot()
    def openComparison(self) -> None:
        self._window.stack.setCurrentIndex(4)

    @Slot()
    def openTechnicalAnalysis(self) -> None:
        self._window.stack.setCurrentIndex(5)

    @Slot()
    def openTrackRecord(self) -> None:
        self._window._open_track_record()

    @Slot()
    def openSettings(self) -> None:
        self._window.settings_dialog.open()


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Researcheus Maximus")
        self.resize(1320, 820)
        self.setMinimumSize(900, 640)
        self.runner = ResearchRunner()
        self.prepared: PreparedResearch | None = None
        self.worker: ResearchWorker | None = None
        self.technical_worker: TechnicalWorker | None = None
        self.track_worker: TrackRecordWorker | None = None
        self.ycharts_test_worker: YChartsTestWorker | None = None
        self.settings = QSettings("GottfriedSomberg", "ResearcheusMaximus")
        self._bridge = _Bridge(self)

        root = QWidget(objectName="AppRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.stack = QStackedWidget()
        self.intake_page = self._build_intake()
        self.review_page = self._build_review()
        self.preview_page = self._build_preview()
        self.deep_analysis_page = self._build_deep_analysis()
        self.comparison_page = self._build_comparison()
        self.technical_analysis_page = self._build_technical_analysis()
        self.stack.addWidget(self.intake_page)
        self.stack.addWidget(self.review_page)
        self.stack.addWidget(self.preview_page)
        self.stack.addWidget(self.deep_analysis_page)
        self.stack.addWidget(self.comparison_page)
        self.stack.addWidget(self.technical_analysis_page)
        self.topbar = self._topbar()
        layout.addWidget(self.topbar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        # The web-rendered pages (home, Deep Analysis, Comparison, Technical
        # Analysis) carry their own minimal branding and have no header by
        # design; the remaining native pages keep the shared app chrome.
        web_page_indices = {0, 3, 4, 5}
        self.stack.currentChanged.connect(lambda index: self.topbar.setVisible(index not in web_page_indices))
        self.topbar.setVisible(self.stack.currentIndex() not in web_page_indices)

    def _topbar(self) -> QFrame:
        frame = QFrame(objectName="TopBar")
        frame.setFixedHeight(56)
        row = QHBoxLayout(frame)
        row.setContentsMargins(32, 0, 32, 0)
        row.setSpacing(10)
        lockup = QHBoxLayout()
        lockup.setSpacing(10)
        lockup.addWidget(QLabel("RESEARCHEUS MAXIMUS", objectName="Brand"))
        divider = QFrame(objectName="BrandDivider")
        divider.setFixedSize(1, 14)
        lockup.addWidget(divider)
        lockup.addWidget(QLabel("GOTTFRIED & SOMBERG WEALTH MANAGEMENT", objectName="Firm"))
        row.addLayout(lockup)
        row.addStretch()
        settings_button = QPushButton("Settings", objectName="Settings")
        settings_button.clicked.connect(self.settings_dialog.open)
        row.addWidget(settings_button)
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
        self.research_mode = QComboBox()
        self.research_mode.addItems(["Live Market Research", "Demo / Offline Test"])
        self.synthesis_provider = QComboBox()
        self.synthesis_provider.addItems(["Automatic", "OpenAI", "Ollama", "Deterministic"])
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Optional; blank unless remembered below")
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("Optional model override")
        self.tvremix_api_key = QLineEdit()
        self.tvremix_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.tvremix_api_key.setPlaceholderText("Optional tvr_... key; blank unless remembered below")
        # Opt-in only, and the keys go to the OS credential store -- never into this
        # app's settings, logs, session files, or reports.
        self.remember_keys = QCheckBox("Remember API keys in this computer's secure keychain")
        self.remember_keys.setChecked(bool(secret_store.load_secret(secret_store.TVREMIX_KEY)))
        if not secret_store.available():
            self.remember_keys.setEnabled(False)
            self.remember_keys.setText("Remember API keys (no secure keychain available on this machine)")
        self.api_key.setText(secret_store.load_secret(secret_store.OPENAI_KEY))
        self.tvremix_api_key.setText(secret_store.load_secret(secret_store.TVREMIX_KEY))
        self.key_status = QLabel("", objectName="Subtitle")
        self.key_status.setWordWrap(True)
        self.remember_keys.toggled.connect(self._apply_remembered_keys)
        self.api_key.editingFinished.connect(self._apply_remembered_keys)
        self.tvremix_api_key.editingFinished.connect(self._apply_remembered_keys)
        self.use_tvremix = QCheckBox("Query TV Remix for supplemental swing-structure evidence")
        self.use_tvremix.setChecked(True)
        self.use_ycharts = QCheckBox("Query the installed YCharts Excel add-in")
        self.use_ycharts.setChecked(True)
        self.settings_dialog = self._build_settings_dialog()

        # _start_research reads the submitted question from here; the web-rendered
        # home page collects the text and hands it to us through the bridge below.
        self.query = QPlainTextEdit()
        self.query.hide()
        return self._build_web_page("home.html")

    def _build_web_page(self, filename: str) -> QWebEngineView:
        """A page rendered from resources/<filename>, wired to self._bridge via QWebChannel."""
        view = QWebEngineView()
        channel = QWebChannel(view)
        channel.registerObject("bridge", self._bridge)
        view.page().setWebChannel(channel)
        path = Path(__file__).resolve().parents[1] / "resources" / filename
        view.load(QUrl.fromLocalFile(str(path)))
        return view

    def _build_comparison(self) -> QWidget:
        # _start_research reads the submitted comparison text from here; the
        # web-rendered page collects it and hands it to us through the bridge.
        self.comparison_query = QPlainTextEdit()
        self.comparison_query.hide()
        return self._build_web_page("comparison.html")

    def _build_deep_analysis(self) -> QWidget:
        # _start_research reads the submitted analysis text from here; the
        # web-rendered page collects it and hands it to us through the bridge.
        self.deep_query = QPlainTextEdit()
        self.deep_query.hide()
        return self._build_web_page("deep_analysis.html")

    def _build_technical_analysis(self) -> QWidget:
        # _start_technical_research reads the submitted query from here; the
        # web-rendered page collects it and hands it to us through the bridge.
        self.technical_query = QPlainTextEdit()
        self.technical_query.hide()
        return self._build_web_page("technical_analysis_intake.html")

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
        form.addRow("TV Remix API key", self.tvremix_api_key)
        form.addRow("", self.remember_keys)
        form.addRow("", self.key_status)
        form.addRow("TV Remix", self.use_tvremix)
        form.addRow("YCharts", self.use_ycharts)
        outer.addLayout(form)
        ycharts_note = QLabel(
            "YCharts uses the signed-in desktop Excel add-in. Credentials are never stored in this app, workbook cells, or GitHub."
        )
        ycharts_note.setWordWrap(True)
        ycharts_note.setObjectName("Subtitle")
        outer.addWidget(ycharts_note)
        self.ycharts_test_status = QLabel("Not tested in this session.", objectName="Subtitle")
        self.ycharts_test_status.setWordWrap(True)
        ycharts_test = QPushButton("Test YCharts Connection", objectName="Secondary")
        ycharts_test.clicked.connect(lambda: self._test_ycharts_connection(ycharts_test))
        outer.addWidget(ycharts_test)
        outer.addWidget(self.ycharts_test_status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.close)
        outer.addWidget(buttons)
        # Whatever is in the fields when Settings closes is what gets remembered.
        # Field-level signals alone missed the common path of pasting a key and
        # closing the dialog straight away.
        dialog.finished.connect(lambda _result: self._apply_remembered_keys())
        return dialog

    def _apply_remembered_keys(self) -> None:
        """Mirror the key fields into the OS keychain, or clear them when opted out."""
        if self.remember_keys.isChecked():
            secret_store.save_secret(secret_store.TVREMIX_KEY, self.tvremix_api_key.text())
            secret_store.save_secret(secret_store.OPENAI_KEY, self.api_key.text())
            remembered = [
                name
                for name, key in (("TV Remix", secret_store.TVREMIX_KEY), ("OpenAI", secret_store.OPENAI_KEY))
                if secret_store.load_secret(key)
            ]
            self.key_status.setText(
                f"Remembered in the keychain: {', '.join(remembered)}."
                if remembered
                else "Nothing to remember yet — paste a key above."
            )
        else:
            secret_store.forget_secret(secret_store.TVREMIX_KEY)
            secret_store.forget_secret(secret_store.OPENAI_KEY)
            self.key_status.setText("Keys are not remembered; they clear when the app closes.")

    def _test_ycharts_connection(self, button: QPushButton) -> None:
        if self.ycharts_test_worker and self.ycharts_test_worker.isRunning():
            return
        button.setEnabled(False)
        self.ycharts_test_status.setText("Testing the signed-in Excel add-in with SPY…")
        self.ycharts_test_worker = YChartsTestWorker(self)

        def finished(success: bool, message: str) -> None:
            button.setEnabled(True)
            prefix = "YCharts ready" if success else "YCharts needs attention"
            self.ycharts_test_status.setText(f"{prefix}: {message}")

        self.ycharts_test_worker.completed.connect(finished)
        self.ycharts_test_worker.start()

    def _build_review(self) -> QWidget:
        page, outer = self._page_shell("Evidence Review", "Confirm the resolved security and preliminary analysis before building the client report.")
        self.review_browser = MetricBrowser()
        outer.addWidget(self.review_browser, 1)
        actions = QHBoxLayout()
        back = QPushButton("Back", objectName="Secondary")
        back.clicked.connect(self._back_to_request)
        approve = QPushButton("Approve & Build Client Report", objectName="Gold")
        approve.clicked.connect(self._approve)
        actions.addWidget(back)
        actions.addStretch()
        actions.addWidget(approve)
        outer.addLayout(actions)
        return page

    def _build_preview(self) -> QWidget:
        page, outer = self._page_shell(
            "Finalize Research",
            "Review the interactive client report, request final changes, or save the approved report.",
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
        open_report = QPushButton("Open Client Report")
        open_report.setObjectName("Gold")
        open_report.clicked.connect(self._open_interactive_report)
        apply_changes = QPushButton("Apply Changes & Regenerate", objectName="Secondary")
        apply_changes.clicked.connect(self._apply_modifications)
        finalize = QPushButton("Finalize Research", objectName="Gold")
        finalize.clicked.connect(self._finalize)
        actions.addWidget(restart)
        actions.addStretch()
        actions.addWidget(open_report)
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
                overview_chart=parse_overview_chart_request(brief),
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
                overview_chart=parse_overview_chart_request(brief),
            )
        security_query, research_brief = parse_research_prompt(self.query.toPlainText())
        custom_start, custom_end = parse_custom_range(research_brief)
        historical_trades = is_historical_trade_request(research_brief)
        # Honour a horizon the user actually stated ("for the long term", "next
        # few weeks"); All Horizons remains the default when they state none.
        stated_horizon = _horizon_from_text(research_brief)
        comparisons = ("SPY",) if historical_trades else ()
        requested_charts = (
            ("price_trend", "stop_loss", "momentum", "relative_performance", "historical_trades")
            if historical_trades
            else ()
        )
        return ResearchRequest(
            security_query,
            stated_horizon,
            question=research_brief,
            deep_analysis=historical_trades,
            comparison_symbols=comparisons,
            requested_charts=requested_charts,
            custom_start=custom_start,
            custom_end=custom_end,
            decision_intent=classify_research_intent(research_brief),
            portfolio_allocation=parse_portfolio_allocation(research_brief),
            historical_trade_examples=historical_trades,
            overview_chart=parse_overview_chart_request(research_brief),
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
                    self.tvremix_api_key.text().strip() if self.use_tvremix.isChecked() else "",
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

    def _start_technical_research(self) -> None:
        if self.technical_worker and self.technical_worker.isRunning():
            QMessageBox.information(self, "Research in progress", "Please wait for the current Technical Analysis run to finish.")
            return
        query_text = self.technical_query.toPlainText().strip()
        if not query_text:
            QMessageBox.warning(self, "Choose a stock", "Enter a company name or ticker.")
            return
        api_key = self.tvremix_api_key.text().strip()
        if not self.use_tvremix.isChecked() or not api_key:
            QMessageBox.information(
                self,
                "TV Remix not configured",
                "Add a TV Remix API key in Settings and enable TV Remix to use Technical Analysis.",
            )
            return
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setFormat("Reading TV Remix technical structure…")
        self.statusBar().addPermanentWidget(progress)
        self.technical_worker = TechnicalWorker(TechnicalRunner(api_key=api_key), query_text, self)
        self.technical_worker.completed.connect(lambda prepared: self._technical_ready(prepared, progress))
        self.technical_worker.failed.connect(lambda message: self._research_failed(message, progress, keep_preview=False))
        self.technical_worker.start()

    def _open_track_record(self) -> None:
        """Score the logged calls and open the track record."""
        if self.track_worker and self.track_worker.isRunning():
            QMessageBox.information(self, "Track record", "The track record is already being built.")
            return
        folder = self.settings.value("outputFolder", "")
        if not folder or not Path(folder).is_dir():
            folder = QFileDialog.getExistingDirectory(
                self, "Where are your finalized reports saved?", str(Path.home() / "Documents")
            )
            if not folder:
                return
            self.settings.setValue("outputFolder", folder)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setFormat("Scoring recorded calls…")
        self.statusBar().addPermanentWidget(progress)
        self.track_worker = TrackRecordWorker(TrackRecordRunner(), Path(folder), self)
        self.track_worker.completed.connect(lambda path, session: self._track_ready(path, session, progress))
        self.track_worker.failed.connect(lambda message: self._research_failed(message, progress, keep_preview=False))
        self.track_worker.start()

    def _track_ready(self, path: Path, session, progress: QProgressBar) -> None:
        self.statusBar().removeWidget(progress)
        progress.deleteLater()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        # Give the browser time to read the file before the temp session goes.
        QTimer.singleShot(3000, session.cleanup)

    def _technical_ready(self, prepared: PreparedTechnical, progress: QProgressBar) -> None:
        self.statusBar().removeWidget(progress)
        progress.deleteLater()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(prepared.interactive_path)))
        self.stack.setCurrentIndex(0)
        # No approval gate for this single-source view -- the report is opened
        # directly. Delay cleanup briefly so the system browser has time to
        # read the file before the temp session directory is removed.
        QTimer.singleShot(3000, prepared.session.cleanup)

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
        key_metric_rows = "".join(
            f"<tr><td>{_metric_link(label)}</td><td><b>{escape(value)}</b></td></tr>"
            for label, value in r.key_metrics
            if value and "unavailable" not in value.lower()
        )
        key_metrics = f"""
            <h3>Key metrics</h3>
            <p style='font-size:10px;color:#657386'>Right-click a metric name for a short explanation.</p>
            <table cellspacing='0' cellpadding='5' border='1'>{key_metric_rows}</table>
        """ if key_metric_rows else ""
        chartbook_items = "".join(
            f"<li><b>{escape(chart.title)}</b> - {escape(chart.insight)}</li>" for chart in r.chartbook
        )
        deep_analysis = ""
        if r.chartbook:
            analyzed_comparisons = tuple(
                label.split("vs. ", 1)[1]
                for label, _value in r.key_metrics
                if " return vs. " in label
            )
            comparisons = ", ".join(analyzed_comparisons or prepared.request.comparison_symbols)
            deep_analysis = f"""
                <h3>Deep technical chartbook</h3>
                <p><b>Comparisons:</b> {escape(comparisons)}<br>
                <b>Requested charts:</b> {escape(', '.join(prepared.request.requested_charts))}</p>
                <ul>{chartbook_items}</ul>
            """
        portfolio_fit = ""
        if r.portfolio_fit:
            fit = r.portfolio_fit
            evidence = "".join(f"<li>{escape(item)}</li>" for item in fit.evidence)
            watchouts = "".join(f"<li>{escape(item)}</li>" for item in fit.watchouts)
            portfolio_fit = f"""
                <h3>{fit.equity_target_pct}/{fit.fixed_income_target_pct} portfolio fit</h3>
                <p><b>{escape(fit.fit_label)}</b><br>{escape(fit.summary)}</p>
                <p><b>Proposed role:</b> {escape(fit.security_role)}</p>
                <ul>{evidence}</ul>
                <p><b>Confirm before use:</b></p><ul>{watchouts}</ul>
            """
        trade_case_review = ""
        if prepared.request.historical_trade_examples:
            rows = "".join(
                f"<tr><td>{escape(case.signal_date)}</td><td>{escape(case.entry_date)} at ${case.entry_price:,.2f}</td>"
                f"<td>${case.initial_stop:,.2f}</td><td>{escape(case.exit_date)} at ${case.exit_price:,.2f}</td>"
                f"<td><b>{case.return_pct:+.1%}</b></td></tr>"
                for case in r.historical_trade_cases
            )
            trade_case_review = f"""
                <h3>Historical trade case studies</h3>
                <p>Hypothetical rules-based examples using real market history; not executed trades.</p>
                {f"<table cellspacing='0' cellpadding='5' border='1'><tr><th>Signal</th><th>Entry</th><th>Initial stop</th><th>Exit</th><th>Return</th></tr>{rows}</table>" if rows else "<p>No trade met every rule in the selected range.</p>"}
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
                f"<tr><td>{_metric_link(label)}</td><td>{escape(primary)}</td><td>{escape(secondary)}</td><td><b>{escape(edge)}</b></td></tr>"
                for label, primary, secondary, edge in comparison.metrics
            )
            rationale = "".join(f"<li>{escape(item)}</li>" for item in comparison.rationale)
            primary_setup = technical_setup(r.technical.rating)
            secondary_setup = technical_setup(comparison.secondary_technical.rating)
            self.review_browser.setHtml(_branded_html(f"""
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
                <p style='font-size:10px;color:#657386'>Right-click a metric name for a short explanation.</p>
                <table cellspacing='0' cellpadding='6' border='1'>
                    <tr><th>Metric</th><th>{escape(r.identity.ticker)}</th><th>{escape(comparison.secondary_identity.ticker)}</th><th>Current edge</th></tr>
                    {metric_rows}
                </table>
                {ycharts_audit}
                <h3>Sources and direct review links</h3><ul>{source_links}</ul>
                <h3>Limitations and source gaps</h3><ul>{limitations or '<li>None reported.</li>'}</ul>
                {"<p style='color:#8A632B'><b>Demo mode:</b> Values are synthetic and are for workflow testing only.</p>" if r.demo_mode else ""}
            """))
            self.stack.setCurrentIndex(1)
            return
        self.review_browser.setHtml(_branded_html(f"""
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
            {portfolio_fit}
            {trade_case_review}
            {key_metrics}
            <h3>Fundamental signals</h3><ul>{fundamentals}</ul>
            <h3>Sentiment</h3><p>{r.sentiment}</p>
            <h3>Research provider</h3><p>{r.provider_label}</p>
            {ycharts_audit}
            <h3>Sources and direct review links</h3><ul>{source_links}</ul>
            <h3>Limitations and source gaps</h3><ul>{limitations or '<li>None reported.</li>'}</ul>
            {"<p style='color:#8A632B'><b>Blocking limitation:</b> Demo mode uses synthetic values and contains no live YCharts, TradingView, SEC, news, or social evidence.</p>" if r.demo_mode else ""}
        """))
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
        self.preview_browser.setHtml(_branded_html(f"<h2>Interactive client report ready</h2><p><b>{self.prepared.suggested_html_filename}</b></p><p>The approved Equity Note format was populated with this run's validated research data.</p>{mode_note}<p>The report includes <b>Print / save PDF</b>, which preserves this approved layout. The obsolete static PDF is no longer presented as the client report.</p>"))
        self.stack.setCurrentIndex(2)
        self._open_interactive_report()

    def _open_interactive_report(self) -> None:
        if self.prepared:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.prepared.interactive_path)))

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
            overview_chart=(
                parse_overview_chart_request(revised_question)
                or self.prepared.request.overview_chart
            ),
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
        QMessageBox.information(self, "Research finalized", f"Interactive client report saved and verified.\n\n{path}\n\nUse Print / save PDF inside the report when a PDF copy is needed.")
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
