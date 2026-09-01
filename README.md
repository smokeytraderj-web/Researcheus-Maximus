# Technical Analyst Agent

A Windows desktop application for client-ready, evidence-grounded investment research.

**Primary General Research objective:** answer the user's exact question clearly and directly. Security data, ratings, charts, and technical plans must support that answer; they must never replace it with a generic stock report.

The runnable application includes:

- one conversational company/ticker research prompt with an automatic all-horizons framework;
- portfolio-role questions such as whether a fund fits a 70/30 allocation;
- historical, rules-based trade case studies with real market charts and explicit entry, initial-stop, and exit markers;
- a separate Deep Technical Analysis workspace for chart-specific research and benchmark/peer comparisons;
- a two-security comparison workspace for stocks or funds, with one evidence preference, sector-benchmark performance, and a side-by-side report;
- optional position context;
- one prominent Overall View inside a client question-and-answer brief, with technical and fundamental evidence organized later in the report;
- a dedicated Position and Risk Plan that converts the chart evidence into a stance, market condition, preferred order type, entry zone, technical stop and stop distance, two targets, and estimated reward/risk;
- an options-planning scenario only when the user asks about options or hedging, with explicit expiration, premium, assignment, suitability, and live-chain verification warnings;
- a first-page **Direct Answer** that preserves and answers the complete user question before any chart or technical plan; fund-summary prompts lead with a concise provider-grounded description, strategy/category, family, and available fee/asset facts;
- a required evidence-review checkpoint;
- Gottfried & Somberg Wealth Management branded interactive HTML reports;
- approved General Research and Technical Research Equity Note layouts with browser-native Print / save PDF;
- requested-modification regeneration, versioned export, and temporary-session cleanup;
- live security resolution, market history, fundamentals, news metadata, and deterministic technical indicators;
- cleanly separated price-trend and Fibonacci charts so technical evidence remains readable;
- a large annotated candlestick chart on page two by default, with short arrows anchored to actual dated price, moving-average-cross, and support events; explicit stop-loss-evidence, Fibonacci, momentum, or relative-performance chart requests are still honored;
- chart-led pages without redundant “what this chart shows” or generic takeaway boxes;
- a fixed three-page General Research brief: client Q&A and reasoning; position/risk plan with one large chart; concise evidence, essential facts, sources, and disclosure;
- a client-facing first page built around the exact question, a direct answer, one Overall View, and labeled reasons before the first chart—without the legacy four-column rating strip;
- a spacious second-page action plan that separates position, order style, market condition, entry, structural stop, targets/payoff, confirmation, and invalidation; an options or hedge example appears only when requested;
- an editorial third page with two-column supporting evidence, one formal facts table, and sources/disclosure confined to the final page;
- navy-and-gold GSWM presentation with clean white pages, a minimal first-page Technical Analyst Agent wordmark, thin gold rules, serif display headings, and readable sans-serif body copy;
- a full-width editorial landing page in the same visual system: a navy research hero, white canvas, serif headings, restrained gold rules, three numbered research paths, and a Tailwind-inspired spacing/card system implemented natively in Qt;
- an optional multi-page technical chartbook with dedicated structural stop-loss evidence, RSI/MACD, normalized relative performance, and requested drawdown/volatility analysis;
- plain-English decision insights beneath every deep-analysis chart, connecting the observed signal to the next confirmation level, downside level, and rating effect;
- fund-profile enrichment for strategy, family, fees, assets, turnover, allocation, and fixed-income characteristics when the provider exposes them;
- volume-aware fund charts that omit the volume panel and metric when daily fund volume is not reported;
- an Evidence Review audit showing the exact YCharts Excel result cells and formulas;
- a minimal Evidence Review glossary: click or right-click a metric name for a plain-English explanation;
- secure Windows certificate-store support for live market connections;
- configurable OpenAI web research, local Ollama synthesis, deterministic fallback, and explicit demo mode.

Live mode links directly to YCharts, TradingView, SEC EDGAR, and the underlying market-data page. Authenticated YCharts values are never guessed when an account session cannot be read. Demo mode remains labeled throughout the UI and PDF and never claims that live research occurred.

On Windows, live mode queries the installed YCharts Excel Add-In through a temporary workbook. Keep desktop Excel open and signed in to YCharts so the app can reuse the active authenticated session. The bridge checks and activates both the YCharts Excel Add-In and YCharts COM Add-In. Excel/YCharts credentials remain inside Excel. Use **Settings > Test YCharts Connection** to run a harmless SPY formula check before research. Do not paste a YCharts credential or access code into a workbook cell or the public repository; authentication must remain in the YCharts Excel ribbon.

The YCharts workbook uses columns A:G and calculates live results in F2:F9. Excel formula errors such as `#NAME?` are rejected and can never be formatted as market values or ratings. A zero YCharts price target or zero price-target-upside result is also treated as an unresolved add-in placeholder and omitted; a separately available Yahoo analyst target remains visible. When YCharts is unavailable, Evidence Review shows one concise amber data alert and keeps raw setup errors out of the client PDF.

## Ask a research question

The main workspace accepts natural-language decision questions and gives the direct, conditional conclusion first. Examples:

```text
Full analysis of TSLA - is it a good opportunity to buy?
Should I sell my AVGO position?
What about my WMT position?
Is BDMIX good for a 70/30 portfolio?
Show QQQ trade entries with stop-loss examples and real chart snapshots from the past year.
```

The answer distinguishes the one Overall Rating from supporting technical and fundamental assessments, cites the evidence behind the conclusion, and states what would change it. In the main all-horizons report, the rating weights technical evidence 70% and fundamental evidence 30% so the displayed decision follows the current setup while retaining business-quality context.

The next page turns that rating into a conditional Position and Risk Plan. Four spacious modules separate the position idea, entry, stop/invalidation, and targets/payoff, followed by one large annotated candlestick chart. The plan distinguishes a controlled pullback, patient limit order, confirmed breakout, or wait-for-reclaim setup; calculates an entry zone from support, moving averages, and Fibonacci structure; and places the technical stop beyond invalidation with an ATR volatility buffer. The displayed stop percentage is therefore derived from the actual chart rather than fixed at 7%. Targets use nearby resistance and Fibonacci levels, and the first target must offer at least 1.5x estimated reward/risk before the setup is treated as actionable. When the evidence does not support an attractive or sufficiently tight setup, the plan says to wait instead of manufacturing a trade.

When the user explicitly asks about options or hedging, an eligible stock or ETF report may also show a defined-risk call spread, cash-secured put, or existing-position protective hedge as a research scenario. It never invents a live premium or executable strike: the user must verify the current option chain, liquidity, expiration, assignment exposure, and maximum loss before acting. A portfolio-context question instead quantifies the stated allocation and concentration before discussing the security-specific setup.

Historical trade prompts automatically open the deep-analysis workflow and interpret “past year” as an exact one-year date range. A case qualifies only after price reclaims its 20-day average while the 50-day trend is rising, MACD is improving, RSI is 45-72, and volume is at least 0.8x its 20-day average. The hypothetical entry occurs the next session. Each chart marks the entry, initial protective stop, and exit, and the report states the outcome and exit rule. These are reproducible case studies using attributed market history, not executed trades or fabricated TradingView screenshots; the report includes a direct TradingView link for independent review.

## Provider setup

- **OpenAI:** paste an API key into Research Settings for the current session, or set `OPENAI_API_KEY`. The key is never saved by the app. OpenAI synthesis uses the Responses API with web search and Structured Outputs. The external synthesis context includes the security, market evidence, and research question; optional purchase price, quantity, and risk-tolerance fields remain local and are not included in that payload.
- **Ollama:** start Ollama locally and install a model. The default is `gpt-oss:20b`; override it in Research Settings or with `RESEARCHEUS_OLLAMA_MODEL`.
- **Automatic:** tries OpenAI, then Ollama, then a clearly disclosed deterministic fallback.
- **Deterministic:** uses live market/provider fields without language-model synthesis.

### TV Remix MCP research resource

The repository includes a credential-free [`.mcp.json`](.mcp.json) connection for `https://tvremix.xyz/api/mcp/v1` and a [TV Remix research guide](resources/tvremix-mcp.md). In an MCP-capable host, the first tool call starts TV Remix OAuth; no token or API key belongs in this repository. Use the resource for verified OHLCV, multi-timeframe technicals, swing/SMC structure, forecasts, news, options, screening, comparisons, and correlation research. The current Qt desktop runtime does not call MCP directly; it continues to use its internal providers unless a native MCP adapter is added later.

Natural-language report modifications are applied by OpenAI or Ollama. Deterministic fallback still refreshes market evidence, but cannot reliably interpret arbitrary editorial instructions.

## Deep Technical Analysis

The landing page presents three numbered choices: **Research Overview**, **Deep Technical Analysis**, and **Security Comparison**. Choose **Start analysis**, begin the prompt with the primary company or ticker, then name up to three comparison symbols and the technical work you want. For example:

```text
AVGO - Compare against NVDA, SOXX, and SPY. Analyze trend, RSI, MACD,
relative performance, drawdown, volatility, support, and resistance.
```

Every technical workflow includes Fibonacci analysis. By default it uses a six-month swing range; when the prompt includes a custom range, Fibonacci, return, relative performance, and chart evidence use that selected range. The 38.2%, 50%, and 61.8% retracement levels are included in the technical score, written signals, strategy context, key metrics, and a dedicated Fibonacci chart. Every deep report also includes a **Stop-Loss Evidence** chart, RSI/MACD, and normalized relative performance. The stop chart shows the planned entry zone, the nearest usable structural reference, the stop beyond that reference, the ATR volatility comparison, Target 1, and estimated reward/risk. Chart labels are kept short and point to the actual dated evidence rather than repeating obvious visual commentary. SPY is the default comparison when none is named. Asking for drawdown, volatility, or a risk chart adds a drawdown and realized-volatility study. Deep Analysis weights technical evidence 70% and fundamental evidence 30%. Relative strength is disclosed in the metrics and may move the technical assessment by one rating step; the report states when that adjustment occurs. Unavailable comparison data is disclosed and never fabricated.

The technical presentation order and risk logic are informed by the public [TV Remix MCP prompt library](https://tvremix.xyz/mcp/prompts): lead with the verdict, establish trend and structural levels, place stops beyond structural invalidation rather than at an arbitrary percentage, compare stop distance with ATR, and require a credible target/payoff relationship. Researcheus calculates and renders those values from its own retrieved price history; it does not copy unverified levels or claim that the TV Remix MCP supplied data when it was not connected.

Custom date ranges can be written directly in Overview, Deep Analysis, or Comparison prompts:

```text
Analyze TSLA from 2024-01-01 to 2025-12-31. Was that a good entry setup?
AVGO vs NVDA from January 2024 to June 2025 - which performed better technically?
```

## Compare Securities

Choose **Start comparison** and name two stocks or funds in one prompt. Company names and tickers are both supported. For example:

```text
AVGO vs NVDA - Which currently offers better value and risk-adjusted opportunity?
```

The comparison retrieves both securities and automatically selects a relevant benchmark. Semiconductor pairs use SOXX; same-sector pairs use the appropriate Select Sector SPDR ETF; cross-sector or unsupported pairs use SPY. The report charts both securities and the benchmark over identical common dates, states each total return and excess return, and analyzes technical setup, Fibonacci position, volatility, valuation, growth, margins, cash-flow yield, leverage, beta, analyst-target upside, and fund fields when available for both. Current price is context, not a measure of cheapness. The four-page report separates the performance decision, full scorecard, company snapshots, and sources/disclosure so every page remains readable.

Deep Analysis also honors prompts such as `Compare AXON to SPY and its respective sector and benchmarks`: it keeps SPY, automatically adds the relevant sector ETF, analyzes both relative-performance series, and includes them in the chartbook. The primary technical chart now focuses on price and moving averages; Fibonacci structure is shown in a separate chart.

Possible investment approaches use plain-language labels: **Possible entry**, **What to wait for**, **When the idea fails**, and **Main risk**. Invalid zero YCharts targets and target-upside placeholders are rejected rather than displayed as real evidence. Revenue and earnings growth are shown separately, with a short explanation when sales grow while earnings decline.

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
