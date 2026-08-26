# Researcheus Maximus

A Windows desktop application for client-ready, evidence-grounded single-stock research.

This first runnable vertical slice includes:

- company/ticker intake and horizon selection;
- optional position context;
- typed Technical, Fundamental, Sentiment, and Lead Analyst results;
- a required evidence-review checkpoint;
- Gottfried & Somberg Wealth Management branded PDF generation;
- embedded PDF preview, versioned export, and temporary-session cleanup;
- a deterministic demo provider for safe end-to-end testing.

Live YCharts, TradingView, SEC, news, and public-social adapters are the next integration stage. Demo mode is labeled throughout the UI and PDF and never claims that live research occurred.

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

