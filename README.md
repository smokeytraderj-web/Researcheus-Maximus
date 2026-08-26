# Researcheus Maximus

A Windows desktop application for client-ready, evidence-grounded investment research.

The runnable application includes:

- one conversational company/ticker research prompt with an automatic all-horizons framework;
- a separate Deep Technical Analysis workspace for chart-specific research and benchmark/peer comparisons;
- a two-security comparison workspace for stocks or funds, with one current evidence preference and a side-by-side report;
- optional position context;
- one Overall Rating supported by a Technical Setup, Fundamental Outlook, and plain-language interpretation;
- a required evidence-review checkpoint;
- Gottfried & Somberg Wealth Management branded PDF generation;
- embedded PDF preview, requested-modification regeneration, versioned export, and temporary-session cleanup;
- live security resolution, market history, fundamentals, news metadata, and deterministic technical indicators;
- a compact, chart-led report with trend, support, resistance, volume, and Fibonacci levels;
- an optional multi-page technical chartbook with RSI/MACD, normalized relative performance, and requested drawdown/volatility analysis;
- an Evidence Review audit showing the exact YCharts Excel result cells and formulas;
- secure Windows certificate-store support for live market connections;
- configurable OpenAI web research, local Ollama synthesis, deterministic fallback, and explicit demo mode.

Live mode links directly to YCharts, TradingView, SEC EDGAR, and the underlying market-data page. Authenticated YCharts values are never guessed when an account session cannot be read. Demo mode remains labeled throughout the UI and PDF and never claims that live research occurred.

On Windows, live mode queries the installed YCharts Excel Add-In through a temporary workbook. Keep desktop Excel open and signed in to YCharts so the app can reuse the active authenticated session. The bridge checks and activates both the YCharts Excel Add-In and YCharts COM Add-In. Excel/YCharts credentials remain inside Excel.

The YCharts workbook uses columns A:G and calculates live results in F2:F9. Excel formula errors such as `#NAME?` are rejected and can never be formatted as market values or ratings. When YCharts is unavailable, Evidence Review shows one concise amber data alert and keeps raw setup errors out of the client PDF.

## Ask a research question

The main workspace accepts natural-language decision questions and gives the direct, conditional conclusion first. Examples:

```text
Full analysis of TSLA - is it a good opportunity to buy?
Should I sell my AVGO position?
What about my WMT position?
```

The answer distinguishes the one Overall Rating from supporting technical and fundamental assessments, cites the evidence behind the conclusion, and states what would change it.

## Provider setup

- **OpenAI:** paste an API key into Research Settings for the current session, or set `OPENAI_API_KEY`. The key is never saved by the app. OpenAI synthesis uses the Responses API with web search and Structured Outputs.
- **Ollama:** start Ollama locally and install a model. The default is `gpt-oss:20b`; override it in Research Settings or with `RESEARCHEUS_OLLAMA_MODEL`.
- **Automatic:** tries OpenAI, then Ollama, then a clearly disclosed deterministic fallback.
- **Deterministic:** uses live market/provider fields without language-model synthesis.

Natural-language report modifications are applied by OpenAI or Ollama. Deterministic fallback still refreshes market evidence, but cannot reliably interpret arbitrary editorial instructions.

## Deep Technical Analysis

The landing page presents three clear choices: **Research Overview**, **Deep Analysis**, and **Compare Securities**. Choose **Open Deep Analysis**, start the prompt with the primary company or ticker, then name up to three comparison symbols and the technical work you want. For example:

```text
AVGO - Compare against NVDA, SOXX, and SPY. Analyze trend, RSI, MACD,
relative performance, drawdown, volatility, support, and resistance.
```

Every technical workflow includes Fibonacci analysis. By default it uses a six-month swing range; when the prompt includes a custom range, Fibonacci, return, relative performance, and chart evidence use that selected range. The 38.2%, 50%, and 61.8% retracement levels are included in the technical score, written signals, strategy context, key metrics, and primary price chart. Every deep report also includes RSI/MACD and normalized relative performance. SPY is the default comparison when none is named. Asking for drawdown, volatility, or a risk chart adds a drawdown and realized-volatility study. Deep Analysis weights technical evidence 70% and fundamental evidence 30%. Relative strength is disclosed in the metrics and may move the technical assessment by one rating step; the report states when that adjustment occurs. Unavailable comparison data is disclosed and never fabricated.

Custom date ranges can be written directly in Overview, Deep Analysis, or Comparison prompts:

```text
Analyze TSLA from 2024-01-01 to 2025-12-31. Was that a good entry setup?
AVGO vs NVDA from January 2024 to June 2025 - which performed better technically?
```

## Compare Securities

Choose **Compare Securities** and name two stocks or funds in one prompt. Company names and tickers are both supported. For example:

```text
AVGO vs NVDA - Which currently offers better value and risk-adjusted opportunity?
```

The comparison retrieves both securities and analyzes their technical setups, Fibonacci position, normalized relative performance, valuation, growth, margins, analyst-target upside, and fund expense ratios or three-year returns when those fields are available for both. Current price is shown as context, not treated as a measure of cheapness. The report identifies one **current evidence preference**, explains every metric edge, and states when no clear winner exists. It does not convert missing data into an estimate or claim that the preferred security is universally appropriate; portfolio role, concentration, tax, liquidity, and risk considerations remain part of the decision.

## Run on Windows

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

If dependencies were previously installed, run the `pip install` command again before testing this version. Live mode keeps SSL verification enabled and augments the public certificate bundle with certificates already trusted by Windows, which supports managed networks that inspect HTTPS traffic.

## Test

```powershell
python -m unittest discover -s tests -v
```

See `CLAUDE.md` for the complete product and engineering specification.
