# Researcheus Maximus

A Windows desktop application for client-ready, evidence-grounded single-stock research.

The runnable application includes:

- one conversational company/ticker research prompt with an automatic all-horizons framework;
- optional position context;
- typed Technical, Fundamental, Sentiment, and Lead Analyst results;
- a required evidence-review checkpoint;
- Gottfried & Somberg Wealth Management branded PDF generation;
- embedded PDF preview, requested-modification regeneration, versioned export, and temporary-session cleanup;
- live security resolution, market history, fundamentals, news metadata, and deterministic technical indicators;
- a compact two-page, chart-led report with trend, support, resistance, and volume;
- an Evidence Review audit showing the exact YCharts Excel result cells and formulas;
- secure Windows certificate-store support for live market connections;
- configurable OpenAI web research, local Ollama synthesis, deterministic fallback, and explicit demo mode.

Live mode links directly to YCharts, TradingView, SEC EDGAR, and the underlying market-data page. Authenticated YCharts values are never guessed when an account session cannot be read. Demo mode remains labeled throughout the UI and PDF and never claims that live research occurred.

On Windows, live mode also attempts to query the installed YCharts Excel Add-In through a temporary workbook. Excel/YCharts credentials remain inside the existing add-in session. Unavailable formulas or add-in failures are disclosed in the Evidence Review and final report rather than silently replaced.

The YCharts workbook uses columns A:G and calculates live results in F2:F9. Excel formula errors such as `#NAME?` are rejected and disclosed; they can never be formatted as market values or ratings.

## Provider setup

- **OpenAI:** paste an API key into Research Settings for the current session, or set `OPENAI_API_KEY`. The key is never saved by the app. OpenAI synthesis uses the Responses API with web search and Structured Outputs.
- **Ollama:** start Ollama locally and install a model. The default is `gpt-oss:20b`; override it in Research Settings or with `RESEARCHEUS_OLLAMA_MODEL`.
- **Automatic:** tries OpenAI, then Ollama, then a clearly disclosed deterministic fallback.
- **Deterministic:** uses live market/provider fields without language-model synthesis.

Natural-language report modifications are applied by OpenAI or Ollama. Deterministic fallback still refreshes market evidence, but cannot reliably interpret arbitrary editorial instructions.

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
