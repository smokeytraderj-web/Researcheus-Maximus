# Stock scorecard chart research

Reviewed 2026-10-02. These are interface and analytical-method decisions, not
claims that the ranking model predicts investment returns.

## Three separate questions

1. Where do current strong setups sit relative to past gains?
2. Which stocks show similar performance in recent and longer windows?
3. Which strong setups have historically moved together day to day?

The first two plots describe performance and technical characteristics. The
third directly uses estimated pairwise daily-return correlation. Keeping these
questions distinct avoids treating proximity in a return/return scatter as
proof of stock-to-stock co-movement.

## Evidence and design decisions

NIST's scatter-plot guidance describes relationships, nonlinear patterns and
outliers, while distinguishing association from causation. This supports clear
axis labels and explanatory notes. It does not validate any trading strategy.
https://www.itl.nist.gov/div898/handbook/eda/section3/scatterp.htm

MathWorks demonstrates comparing stock-return vectors with scatter plots and
inspecting observations using data tips. RM uses matched daily percentage
returns to calculate the correlation coefficient. The overview then places one
stock per dot, with correlation to a selected reference on X and score on Y.
That overview layout is our design choice, rather than a standardized indicator
from the source. A daily-return scatter would instead have one day per dot.
https://www.mathworks.com/videos/plotting-financial-data-1603366137074.html

Plerou et al. study stock-return correlation matrices and distinguish a market
influence common to stocks, group structure, and noise. RM therefore offers
both overall-return correlation and correlation of residuals after separate
stock-on-SPY regressions. This simple SPY adjustment is not the paper's random
matrix denoising procedure, nor a full sector/factor model.
https://arxiv.org/abs/cond-mat/0108023

CFA Institute's published daily/monthly comparison shows that sampling
frequency and historical window affect estimated relationships. RM makes the
common date range and sample count visible and consistently uses daily data.
The result is a description of that window, not a permanent stock property.
https://rpc.cfainstitute.org/blogs/enterprising-investor/2023/equity-and-bond-correlations-higher-than-assumed

CFA Institute's backtesting reading describes walk-forward signal calibration,
subsequent performance tracking, look-ahead bias and structural breaks. A plot
of today's technical score against past returns cannot establish predictive
value. RM's score already uses trend and momentum, so some association with
past returns is mechanical. Testing predictive usefulness would require scores
formed at past dates without future information, followed by subsequent returns.
https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation

## Window arithmetic

Recent 100-session return = latest close / close 100 sessions earlier - 1.
Trailing 200-session return = latest close / close 200 sessions earlier - 1.
The first period is contained in the second. Their shared observations can
mechanically strengthen the relationship between plot axes. This conclusion
comes from the window definitions, not from a backtest.

Preceding 100-session return = close 100 sessions earlier / close 200 sessions
earlier - 1. This option compares two adjacent periods without overlapping
return intervals. Upper-right indicates gains in both; lower-right indicates
a recent gain following a prior loss. Those patterns do not establish trading
signals. All chart returns are percentages over observed trading sessions,
not calendar days, and retain the input adjustment basis.

## Correlation and group rules

Pearson correlation compares matched daily percentage returns across up to 252
observations, with at least 126 required. Constant series are excluded. Common
observations are aligned before calculation; missing returns are not zero-filled.
Mixed price bases are excluded rather than compared as though equivalent.

Reference correlation does not imply all-pairs group membership. Two stocks can
both correlate highly with a third while their mutual correlation falls below
the chosen threshold. RM uses complete-link groups in which every member pair
meets 0.75. The threshold and score >=8 highlight are application screening
rules, not significance tests or academically calibrated trading cutoffs.

The SPY toggle correlates residuals after each stock's daily return is regressed
on an intercept and the contemporaneous SPY return. It does not remove all
possible common factors. Performance windows remain actual stock returns in
both modes. Raw fallback prices can be affected by corporate actions.

## Layout and explanations

Graphs have their own tab and wider workspace. Each chart has a full-width
panel, stable point coordinates, collision-aware ticker labels with leader
lines, local point details, a result-derived summary, and a collapsible guide.
The third graph lists the five closest reference relationships with exact
three-decimal coefficients. Changing the reference excludes its own 1.0
self-correlation. API correlation values retain full precision for threshold comparisons; only displayed coefficients are rounded. Percentage axes use round increments; scores label 1-10.
The PDF keeps selected controls and provides chart-reading and source pages.

## Alternatives considered

A 50-stock scatter matrix would require 2,500 panels and is unsuitable for this
minimal interface. The prior 2D correlation projection and heatmap were removed
following user feedback. Rolling correlation is a useful potential drilldown for
stability over time, but a fixed overview coefficient alone cannot show that
stability. Do not describe the present implementation as a rolling analysis.
The 100/200 view remains available as requested, with an adjacent-window option
for a less mechanically coupled performance comparison.
