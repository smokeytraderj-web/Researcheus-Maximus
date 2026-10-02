# Technical stock scorecard

Open **Portfolio → Rank Stocks**, or `/rank-stocks`. Paste 1–200 unique tickers
or upload CSV, TSV, or XLSX (tickers in the first column, optional Ticker header,
2 MB maximum). Ranking uses adjusted daily Yahoo Finance data and SPY as the
S&P 500 proxy. The dedicated ranking does not require an AI or TV Remix key.

Results sort highest first with alphabetical tie breaking. Each row contains
an independent 1.0–10.0 technical setup score for a 1–3 month horizon, a brief
reason, a data date, and expandable raw indicators and five component scores.
The expandable methodology describes every rule. Missing, stale, short-history,
zero-volume, or unaligned-benchmark data receives no score.

The score is `1 + 9 × weighted component total / 100`. Components (0–100) are
trend 30%, momentum 20%, SPY relative strength 20%, entry/risk 20%, volume 10%.
Scores are deterministic assessments, not calibrated forecasts or portfolio
recommendations. Fundamentals and earnings-event risk are outside this model.
The latest daily bar can be incomplete during trading hours.

The server processes stocks sequentially, shares the app's concurrency limit,
and permits one ranking job at a time. Progress is incremental; early ranks
are provisional. Results remain in process memory for one hour after completion,
with at most ten completed/recent jobs. Restart/sleep removes them. A device-local
job ID lets a browser restore a run while it exists; tickers/results are not
stored in browser storage. CSV exports contain all indicators, component scores,
source links, and model version. Print / PDF respects the current filter and
expanded rows. Reset the filter and expand rows to include more evidence.

## Deployment

Changes are on `main`. Render must rebuild the Docker image to install the new
`openpyxl` workbook dependency. Automatic deployment depends on the service's
Render settings; otherwise use **Manual Deploy → Deploy latest commit**.
Existing access-code protection covers the page and all ranking endpoints.

## Validation

Targeted synthetic tests cover 60-stock completion, independent scoring,
missing/stale history, benchmark failure, slot release, CSV/Excel input,
file limits, protected routes, and non-cached API responses. Existing portfolio
and backend regression checks are also run. Hosted performance and Yahoo
availability must be confirmed on the deployed Render service; tests do not
establish that a 200-stock live run fits every free-host resource limit.
