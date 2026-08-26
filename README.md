# Researcheus Maximus

A Windows desktop application for client-ready, evidence-grounded single-stock research.

The runnable application includes:

- company/ticker intake and horizon selection;
- optional position context;
- typed Technical, Fundamental, Sentiment, and Lead Analyst results;
- a required evidence-review checkpoint;
- Gottfried & Somberg Wealth Management branded PDF generation;
- embedded PDF preview, versioned export, and temporary-session cleanup;
- live security resolution, market history, fundamentals, news metadata, and deterministic technical indicators;
- annotated technical charts with trend, support, resistance, and volume;
- configurable OpenAI web research, local Ollama synthesis, deterministic fallback, and explicit demo mode.

Live mode links directly to YCharts, TradingView, SEC EDGAR, and the underlying market-data page. Authenticated YCharts values are never guessed when an account session cannot be read. Demo mode remains labeled throughout the UI and PDF and never claims that live research occurred.

On Windows, live mode also attempts to query the installed YCharts Excel Add-In through a temporary workbook. Excel/YCharts credentials remain inside the existing add-in session. Unavailable formulas or add-in failures are disclosed in the Evidence Review and final report rather than silently replaced.

## Provider setup

- **OpenAI:** paste an API key into the intake screen for the current session, or set `OPENAI_API_KEY`. The key is never saved by the app. OpenAI synthesis uses the Responses API with web search and Structured Outputs.
- **Ollama:** start Ollama locally and install a model. The default is `gpt-oss:20b`; override it in the intake screen or with `RESEARCHEUS_OLLAMA_MODEL`.
- **Automatic:** tries OpenAI, then Ollama, then a clearly disclosed deterministic fallback.
- **Deterministic:** uses live market/provider fields without language-model synthesis.

## Run on Windows

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Test

```powershell
python -m unittest discover -s tests -v
```

See `CLAUDE.md` for the complete product and engineering specification.
