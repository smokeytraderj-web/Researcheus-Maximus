# TV Remix MCP Research Resource

## Connection

- Server: `https://tvremix.xyz/api/mcp/v1`
- Transport: Streamable HTTP
- Project configuration: [`.mcp.json`](../.mcp.json)
- Authentication: OAuth 2.1 with Dynamic Client Registration. The first tool call opens the TV Remix authorization page. Sign in and approve access in the MCP host.
- Headless fallback: create a `tvr_...` API key in the TV Remix account page and store it only in the MCP client's protected configuration. Never commit it to this repository.
- Published rate limit: 60 requests per minute per account. Respect `Retry-After` after an HTTP 429 response.

The desktop application's current ReportLab/Qt runtime does not execute MCP calls itself. This resource makes TV Remix available to an MCP-capable research agent or host. A future native adapter can consume the same endpoint without changing the research rules below.

## Best uses in Researcheus

1. Resolve a bare company or ticker with `search_symbols`; use the returned `EXCHANGE:SYMBOL` identifier.
2. Retrieve price history with `get_ohlcv` and use at least 300 bars when analyzing swing structure.
3. Retrieve multi-timeframe indicators with `get_full_technicals` or `analyze_multi_timeframe`.
4. Retrieve structural levels with `analyze_swing_tool`; add `analyze_smc_tool` when order blocks, fair-value gaps, liquidity, or break-of-structure evidence matters.
5. Use `get_financials`, `get_forecasts`, `get_news`, and the earnings/economic calendars for supporting research.
6. Use batch tools for watchlists and comparisons instead of repeatedly calling one-symbol tools.
7. Re-render verified values in the Researcheus navy, gold, and white chart style. Attribute TV Remix when it supplied the underlying evidence.

## Stop-loss evidence workflow

- Establish the current trend and the nearest support, swing low, moving average, Fibonacci level, or volatility reference.
- Place a proposed stop beyond structural invalidation rather than choosing an arbitrary percentage.
- Compare the stop distance with ATR so ordinary volatility is less likely to trigger it.
- Identify a credible first target and require an acceptable reward/risk relationship before calling the setup actionable.
- State what confirms the trade, what invalidates it, and what evidence would change the technical assessment.
- Never invent a price level, signal, option premium, chart snapshot, or executed trade. If the MCP response is missing, truncated, or unsuccessful, disclose that internally and omit unsupported claims from the client report.

## Service boundaries

The MCP supplies quotes, OHLCV bars, technicals, swing/SMC analysis, fundamentals, forecasts, news, calendars, screeners, options data, comparisons, and correlations. It does not control authenticated TradingView drawings, alerts, watchlists, or paper trades. Those functions remain in the TV Remix browser extension.

## Official references

- [TV Remix prompt library](https://tvremix.xyz/mcp/prompts)
- [TV Remix MCP tool reference](https://github.com/tvremix/claude-plugin/blob/main/skills/mcp-tools.md)
- [Official MCP configuration](https://github.com/tvremix/claude-plugin/blob/main/.mcp.json)
