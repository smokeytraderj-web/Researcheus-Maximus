# Portfolio research on the RM website

## Use the dashboard

1. Paste holdings or import a CSV/TSV with just a ticker and amount per row. Choose percentage weights, USD market values, shares, or explicit equal weighting.
2. Review the parsed tickers and amounts. Percentage weights must total 100%. Add `CASH` for cash when using weights or market values. Combine duplicate lots first.
3. Select **Full technical research** or **General research brief**, optionally add an investment question, and run the review.
4. Open finished holdings while the remaining research runs. The ticker pills switch every position panel together. The same holdings are available in an allocation table.
5. Explore **Overview**, **Charts**, **Key data & sources**, and **Full RM report**. Technical research retains RM's price structure, momentum, relative strength and Fibonacci charts when produced from usable evidence.
6. **Download portfolio** saves a ZIP containing an offline dashboard, charts and the original HTML notes. Extract it and open `Portfolio_RM.html`. To save a position as PDF, choose **Full RM report → Open / save PDF** and use the note's print control.

A percentage-weight input looks like:

```csv
Ticker,Weight
AAPL,25
MSFT,25
NVDA,20
SPY,25
CASH,5
```

CSV input supports quoted thousands separators. Tabs and whitespace-separated rows are supported. Equal weighting accepts ticker-only rows or a comma-separated ticker list. Inputs are long-only, up to 50 positions. USD-listed securities only; mixed-currency share values are not added without an FX conversion. Unknown, unavailable or mismatched tickers stay visible as failures.

## How the portfolio view works

The summary is a transparent roll-up of the existing RM opinions, with no change to the security-rating engine:

| RM rating | Summary score |
| --- | ---: |
| Strong Buy | +3 |
| Buy | +2 |
| Add | +1 |
| Hold | 0 |
| Reduce | −1 |
| Sell | −2 |
| Avoid | −3 |

The score is allocation-weighted across invested securities: **Constructive** at +1 or above, **Defensive** at −1 or below, and **Mixed** in between. Cash has no security rating and is shown separately. The dashboard reports the portions of the whole portfolio with constructive, neutral and negative opinions.

An overall view requires usable research for every security. A failed holding retains its allocation; the remaining positions are never silently reweighted. With shares, any missing price leaves all allocation weights pending. Concentration is flagged at 25% in one security or 60% in the largest three. These review thresholds are explicit, separate from the opinion score, and are not suitability limits. No correlation, diversification benefit, risk-adjusted forecast or expected portfolio return is inferred from individual ratings.

## Integration with Researcheus Maximus

Open `/portfolio` through **Evaluate portfolio** on the existing home page. The
**Single-stock research** button returns to `/`. Both pages use the same origin,
access cookie, server credentials, data providers and run capacity. No second
server, deployment, API key setup or login is needed.

Portfolio endpoints are under `/api/portfolio`. Reports and charts remain behind
the shared access gate and send `Cache-Control: no-store`. Working sessions are
cleaned up per holding; finished portfolio reports follow the existing RM
report-retention configuration. Cancellation finishes the current provider call,
skips the remaining holdings, and removes the cancelled run's files.

The preview's synthetic sample data is not shipped into this page. Live research
uses the existing RM provider configuration; demo data requires the existing
explicit `RESEARCHEUS_DEMO=1` setting. Desktop Excel YCharts remains unavailable
to the existing web provider. Sources and limitations remain visible per holding.

The original single-stock home page, desktop entry point, access settings,
report templates and Railway/Docker launch command remain in place.
