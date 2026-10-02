# Technical stock scorecard

Open **Portfolio → Rank Stocks**, or `/rank-stocks`. Paste 1–200 unique tickers
or upload CSV, TSV, or XLSX (tickers in the first column, optional Ticker header,
2 MB maximum). Ranking prefers adjusted daily Yahoo Finance data, with direct chart access
through two Yahoo hosts, a verified yfinance session, and a Nasdaq history
fallback. SPY is the
S&P 500 proxy. The dedicated ranking does not require an AI or TV Remix key.

Results sort highest first with alphabetical tie breaking. Each row contains
an independent 1.0–10.0 technical setup score for a 1–3 month horizon, a brief
reason, a data date, and expandable raw indicators, five component scores, and a
concise two-sentence technical interpretation derived from those indicators.
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
source links, adjustment basis, actual data providers, and model version.
Stock and SPY always use the same price basis; Nasdaq fallback is unadjusted
and clearly labeled. Large discontinuities in raw Nasdaq prices are rejected. Download PDF creates a branded landscape scorecard with summary, three scatter
plots, correlation-group findings, the full ranked table, per-ticker interpretation,
and methodology. The PDF includes every ranked stock; graph scope and market
adjustment follow the comparison controls. Export is generated in memory and
not saved on the server.

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

## Correlation graphs

The scorecard has a dedicated Graphs & analysis tab with three full-width scatter plots: trailing 12-month return versus
technical score, and 100-trading-day return (X) versus 200-trading-day return (Y), plus technical score versus correlation to a chosen reference stock. A window selector also compares recent versus preceding non-overlapping 100-day returns.
Top 20 is default; Top 10 and Top 50 are available. Return windows are measured
as latest close / close N sessions earlier - 1, multiplied by 100. Both new
windows are available with the minimum 220-session scoring history. Values are
also included in ticker details and CSV exports.

Colors identify complete-link daily-return correlation groups (every pair >=
0.75), rather than sectors or visual proximity. Click a point/group to inspect
membership, average correlation, and the lowest member-pair correlation. Nearby
points in the new scatter have similar performance across the two windows;
the 100-day window is contained in the 200-day window, so overlap can strengthen
the relationship between the axes without proving stocks move together daily.

Up to 252 overlapping daily percentage returns are used for group membership,
with 126 required. The Remove market effect toggle fits stock returns on an
intercept and SPY, then correlates residuals. Constant residual series are
excluded. Stocks with an incompatible adjustment basis are excluded and listed.
The two performance plots keep actual stock returns in both modes. The reference scatter uses the selected correlation mode. Correlation
analysis reuses already-fetched history; no extra requests are made. Raw
histories remain private to the temporary job. The correlation map and heatmap
are no longer shown in the page or PDF.

Shared `workspace-theme.css` applies the landing-page typography, blue actions,
white cards and cool background across the workspace, help and access pages.
The offline portfolio bundle inlines this stylesheet. Rank Stocks is linked
from both the landing page and the portfolio header.

### Readability

Charts occupy separate full-width panels. Ticker labels use leader lines without
moving the underlying points; the top 20 labels are shown, or the top 10 for
larger comparisons. Selecting a group labels its members. Hover/focus details
identify each stock and its 100-day, 200-day, and 12-month returns, plus correlation to the selected reference where applicable. The PDF gives
each scatter its own landscape page, a reading guide, and research references and lists qualifying groups separately.
The home page uses keyboard-accessible Rating / Technical tabs in one intake
card, with stacked actions on small screens.

Graphs use rounded axis domains and readable 1/2/5 percentage increments instead
of arbitrary equal subdivisions. Score axes label every integer from 1 to 10.
The PDF retains the reference-stock and window selections. The full watchlist
still exports even if the chart scope is Top 10/20/50. See chart-research.md for
research decisions, source links, and limits of interpretation.
