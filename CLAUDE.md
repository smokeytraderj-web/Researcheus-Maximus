# Researcheus Maximus Project Instructions

## Product

**Researcheus Maximus** is a single-user Windows desktop application for producing client-ready, evidence-grounded research on one publicly traded stock at a time.

The user may enter either a ticker or a company name, such as `AAPL` or `Apple`. The application resolves the security, asks for an investment horizon, conducts automated technical, fundamental, news, analyst-commentary, and public social-sentiment research, and produces a concise branded interactive report.

The application is a new public GitHub project modeled on the architecture, interaction pattern, and visual system of `smokeytraderj-web/Reportus`. Reportus must remain unchanged.

The primary client artifact is the interactive HTML Equity Note defined by the approved resource templates. Its built-in **Print / save PDF** control is the supported PDF path so a saved PDF preserves the same approved layout. The obsolete standalone ReportLab layout must never be presented as the client report.

The displayed product name is **Researcheus Maximus**. The displayed firm name is **Gottfried & Somberg Wealth Management**. Do not append “LLC” or abbreviate the firm name unless an approved firm template requires it.

## Primary General Research Objective

The main General Research workflow exists first to answer the user's stated investment question. Security research, ratings, technical levels, charts, and strategy ideas are supporting evidence for that answer; they must never displace it with a generic stock report.

- Preserve the complete user question and make the direct answer the first substantive content in the client PDF.
- Incorporate stated portfolio allocation, concentration, existing-position, timing, and decision context when it materially changes the answer.
- If the question cannot be answered from the available evidence, say exactly what is missing instead of substituting a generic fundamental or technical summary.
- Default General Research output is a three-page client brief: direct answer and reasoning; action/risk plan with one large annotated chart; concise evidence, sources, and disclosure.
- General Research should use only the technical detail necessary to support the decision. Deep Technical Analysis remains the detailed technical workflow.
- Options strategies appear in General Research only when the user asks about options, calls, puts, or hedging, or when existing-position context makes a hedge directly relevant.

## Version-One Scope

Version one supports only **Single Stock Research**.

Do not expose unfinished portfolio functionality in the interface. Preserve extension points for a later Portfolio Review workflow that can accept Excel, CSV, PDF, screenshots, and pasted holdings, screen positions with lighter research, show one-word ratings and correlation risks, and launch a full stock-research session from any holding.

Version one must:

1. Accept a ticker or company name.
2. Resolve and confirm the exact listed security before research.
3. Ask the user to select Short Term, Medium Term, Long Term, or All Horizons.
4. Accept optional purchase price, quantity, position size, risk tolerance, and a custom question.
5. Research YCharts through the user's existing authenticated browser session.
6. Research public TradingView pages and charts without requiring a TradingView login where practical.
7. Research SEC filings, company investor-relations sources, financial news, analyst commentary, X, Reddit, and Stocktwits where accessible and permitted.
8. Run separate Technical Analyst and Fundamental Analyst workstreams.
9. Use a Lead Analyst to reconcile the complete evidence.
10. Present a pre-generation evidence review for user approval.
11. Generate a concise, client-ready interactive report with text, tables, annotated charts, and a print-safe PDF view.
12. Support revisions before finalization.
13. Delete temporary research data after successful export, cancellation, or crash recovery.

## Priorities

Apply these priorities in order:

1. Protect user, client, account, and authentication information.
2. Never fabricate, guess, or silently repair research data.
3. Preserve security identity, numerical accuracy, source provenance, and timestamps.
4. Distinguish observations, interpretations, scenarios, and recommendations.
5. Produce decision-useful insight with explicit uncertainty and risk controls.
6. Produce polished client-ready presentation quality.
7. Keep the interface minimal and easy to operate.
8. Complete a normal analysis within 20 minutes when sources are available.

Accuracy and evidence quality take priority over speed. If required information is uncertain or materially conflicting, stop and ask the user.

## Product Character

The product must feel minimal, sleek, professional, deliberate, and fast. Assume the user understands financial material. Use concise analyst language rather than educational filler.

Every output is assumed to be client-ready. There is no separate internal-report mode in version one.

Client-ready means polished and sourced; it does not mean overstating certainty. Ratings, price levels, targets, and strategies must be framed as evidence-based assessments and scenarios, never guarantees.

## Research Report Standards

The two HTML files in `Researcheus-Maximus/resources/` are authoritative product contracts, not loose mood boards:

- `general_research_base.html` defines the default General Research response.
- `technical_research_base.html` defines Deep Technical / Technical Research.

Both formats share one visual system: a white editorial page, narrow left navigation rail, Source Serif 4 display hierarchy, IBM Plex Sans body copy, IBM Plex Mono figures, navy text, restrained gold accents, light-gray analytical panels, and compact red/green signal colors. Preserve generous page margins, aligned content edges, consistent section rules, tabular-number alignment, and one dominant idea per module. Do not reintroduce oversized banners, dense dashboard grids, ornamental headers, obvious chart-commentary boxes, or mixed visual systems.

### General Research

- The main goal is to answer the user's exact question. Preserve the question verbatim and put a direct, decision-specific answer before the first chart.
- Use this order: security and answer; exact question and direct answer; concise reasoning; what the advisor would do; one decision-relevant chart; essential data; risks and decision triggers; sources and disclosure.
- Default to one chart. Select the chart that best supports the requested decision; use security-versus-SPY indexed total return when the user does not specify a chart.
- Keep the data set compact and relevant to the question. General Research must not become a technical-analysis dump or a shortened copy of the technical report.
- Add entry, stop, target, options, or other technical modules only when the user's request materially calls for them and the available evidence supports them.
- The default print/PDF form is a concise three-page client brief: answer and reasoning, evidence and essential data, then risks/sources/disclosure.

### Technical Research

- Preserve the information order: security and rating; the call; position and risk plan; technical evidence; fundamentals; organized data; sources and disclosure.
- Open with the call stated plainly: the final rating at display size, its confidence, the stance, and a single row carrying entry zone, stop, first target, and reward/risk. The reader must not have to hunt for the recommendation or the levels.
- Preserve the interactive `Action plan` / `Scenario tester` control. The scenario tester updates selected price, change from current price, change from entry, stop distance, illustrative position impact, and plain-English action zone without changing the evidence.
- Present the technical evidence as one tabbed `Charts` section. Lead with `Price structure`, then `Momentum`, `Relative strength`, and `Fibonacci`; additional validated views follow. The left rail navigates the report's pages, and the Charts page opens on the first tab.
- A chart tab appears only when its evidence was actually produced. Never publish an empty or placeholder panel to keep a fixed tab count — a security with no usable volume simply has no volume-by-price tab.
- `Volume by price` distributes each session's volume across the range it traded, and marks the point of control and the value area holding 70% of volume. State where the current price sits relative to that value area.
- The Fibonacci chart visibly renders the validated six-month close series, swing high and low, 38.2%, 50%, and 61.8% retracement levels, the current-price interaction, and one concise decision implication. Reserve enough plot margin that every annotation remains inside the chart at desktop, responsive, and print sizes.
- Charts that expose their plotted series carry a hover read-out giving the exact dated values behind the picture. The read-out is positioned from geometry published by the renderer, so it must stay aligned with the image at any width.
- Interactive controls are additive. Print/PDF output hides controls, exposes useful static conclusions, expands hidden report content where necessary, and remains complete without JavaScript interaction.
- Live embeds cannot render in print. Omit them from the printed report rather than reserving space that prints blank.
- Deep Technical may run longer than the General Research brief to keep charts legible, but no printed page may be blank or near-blank. Verify page count and per-page content on the rendered PDF, not on the HTML.

Both formats use the same production data bindings and validation rules as the approved research result. Seeded demonstration values in the reference files are layout fixtures only and must never be emitted into a client report.

## Inherited Reportus Framework

Reuse or adapt these proven Reportus patterns:

- PySide6 Windows desktop shell.
- Minimal navy, white, and restrained gold visual system.
- Large home-screen function card.
- Step-by-step intake pages.
- Skill-driven workflow definitions.
- Thin orchestration and typed subsystem boundaries.
- Local privacy inspection before external processing.
- Isolated disposable sessions.
- Clear progress stages using background workers.
- Embedded PDF preview.
- Slim revision panel.
- Explicit finalization.
- Windows-safe filename sanitization and automatic versioning.
- Provider-neutral structured AI interface.
- Deterministic parsing, calculations, validation, file handling, and QA.
- Rendered-output inspection before presentation.

Do not copy Reportus report generators merely because they exist. Reuse its shell, session lifecycle, provider abstraction, skill registry pattern, privacy rules, grounding concepts, QA approach, and visual behavior. Replace report-generation orchestration with research-specific components.

## Default User Workflow

1. Open Single Stock Research.
2. Enter a ticker or company name.
3. Resolve candidate securities and require confirmation of the exact exchange-listed instrument.
4. Ask for the analysis horizon: Short Term, Medium Term, Long Term, or All Horizons.
5. Offer optional position context: purchase price, quantity, position size or allocation, risk tolerance, and a custom question.
6. Show the planned source and research checklist.
7. Run local privacy and input validation.
8. Conduct source retrieval and specialist analysis.
9. Reconcile conflicting evidence and calculate deterministic metrics.
10. Show a compact Evidence Review containing security identity, current price, timestamps, sources, major signals, missing information, conflicts, and preliminary ratings.
11. Require approval or correction.
12. Generate the interactive Equity Note and open it in the user's browser for review.
13. Allow quick revisions or a custom revision.
14. Finalize only when the user presses **Finalize Research**.
15. Verify the exported HTML report and delete the temporary session; PDF copies are created from the report's Print / save PDF control.

## Security Resolution

The only required initial input is a ticker or company name.

- Accept common-name and ticker inputs, including `Apple`, `AAPL`, `Walmart`, and `WMT`.
- Resolve candidates using current, authoritative security metadata.
- Show company name, ticker, exchange, security type, and currency.
- Require confirmation before research if more than one plausible security exists.
- Never silently choose among multiple share classes, ADRs, foreign listings, funds, or similarly named issuers.
- Carry a stable security identity through every source request.

## Analysis Horizons

The selected horizon changes chart intervals, lookback periods, signal emphasis, strategy construction, and the Lead Analyst's evidence weighting.

### Short Term

Emphasize current price structure, momentum, volume, volatility, near-term support and resistance, event risk, and current sentiment. Fundamentals remain relevant but normally receive less influence unless a material catalyst dominates the setup.

### Medium Term

Balance technical structure, earnings trajectory, valuation, revisions, catalysts, and sentiment.

### Long Term

Emphasize business quality, financial performance, valuation, competitive position, long-duration risks, and thesis durability. Use technical analysis primarily for trend condition, risk management, and entry timing.

### All Horizons

Produce distinct conclusions and strategy implications for Short, Medium, and Long Term. Do not collapse conflicting horizon conclusions into one vague statement.

Do not implement the weighting as a hidden fixed formula. The Lead Analyst must make and explain a reasoned judgment, while deterministic scores may be used as transparent supporting evidence.

## Research-Agent Architecture

The application uses isolated specialist workstreams and a final synthesis step. Specialists must not see or imitate another specialist's rating before completing their own analysis.

### Research Orchestrator

The orchestrator resolves the security, builds the research plan, retrieves approved evidence, dispatches bounded tasks, tracks provenance, detects missing or conflicting inputs, and assembles the evidence review. Keep orchestration thin and explicit.

### Technical Analyst

Act as a professional technical analyst, not an indicator checklist.

Evaluate price, volume, momentum, volatility, market structure, relative strength, and risk in the context of the selected horizon. Use a multi-timeframe and multi-factor mosaic. Select relevant tools based on the security's liquidity, volatility, history, regime, and available evidence.

The baseline toolkit includes:

- Trend direction, structure, and strength.
- Swing highs, swing lows, higher-high/lower-low sequences, and trading ranges.
- Support, resistance, breakout, breakdown, retest, and gap behavior.
- Simple and exponential moving averages and their slope, ordering, distance, and crossovers.
- RSI and momentum divergence.
- MACD and momentum transitions.
- Volume confirmation, accumulation/distribution clues, unusual volume, and volume-by-price when available.
- Bollinger Bands or comparable volatility envelopes.
- ATR or comparable realized-volatility measures.
- Relative strength versus an appropriate benchmark and, when useful, sector peers.
- Chart patterns only when objectively supported.
- Market and sector context when it materially changes interpretation.
- Liquidity, event gaps, and unreliable-signal risks.
- Entry, add, target, stop, and invalidation zones when evidence supports defensible levels.

Rules:

- Start with raw price and volume structure before indicators.
- Use multiple timeframes appropriate to the chosen horizon.
- Do not count correlated indicators as independent confirmation.
- Explain which signals agree, conflict, or are inconclusive.
- Treat TradingView's aggregate Technical Rating as one input, never the final conclusion.
- Never infer an exact chart value from an unreadable image.
- Preserve chart timeframe, indicator settings, market session, currency, and retrieval time.
- Use technical analysis as a probabilistic decision and risk-management framework, not a prediction engine.

### Fundamental Analyst

Evaluate the issuer's business, financial condition, valuation, estimates, catalysts, and risks using authoritative and current evidence.

The baseline toolkit includes:

- Business model, segments, competitive position, and material dependencies.
- Revenue, margins, earnings, free cash flow, and balance-sheet trends.
- Capital allocation, dilution, debt, liquidity, and share-count changes.
- Management guidance and material changes in expectations.
- Valuation using appropriate multiples and context, not one universal metric.
- Historical valuation and peer comparison when definitions and periods align.
- Earnings estimates and revisions.
- Recent 10-K, 10-Q, 8-K, earnings release, and investor presentation.
- Upcoming earnings and identifiable catalysts.
- Material regulatory, litigation, customer-concentration, execution, and industry risks.
- Bull, base, and bear thesis elements.

Rules:

- Prioritize SEC filings and issuer investor-relations material for official disclosures.
- Use YCharts for normalized financials, valuation, estimates, ratings, and comparisons.
- Use reputable news and analyst commentary for current context.
- Match fiscal periods and metric definitions before comparing values.
- Never fill missing financial values with model guesses.
- Clearly distinguish reported results, consensus estimates, company guidance, and analyst interpretation.

### Sentiment and Narrative Research

Sentiment is a supporting capability used by the research process. It may examine public X posts and searches, Reddit, Stocktwits, current financial news, and analyst commentary.

The sentiment process must:

- Search using the confirmed ticker, cashtag, company name, major products, executives, earnings, and relevant current narratives.
- Separate company-specific sentiment from broad market or sector sentiment.
- Report bullish and bearish narratives, direction, intensity, recency, and meaningful change.
- Detect repeated content, likely spam, promotional campaigns, bots, engagement bait, and unverified rumors when possible.
- Prefer diverse original sources over repost volume.
- Avoid equating post count with investor conviction.
- Cite representative evidence without exposing unnecessary personal data.
- Label rumors and unverified claims clearly or omit them when they cannot be responsibly contextualized.
- Never use sentiment alone to justify an investment rating.

### Lead Analyst

The Lead Analyst receives the completed specialist findings, normalized evidence, conflicts, and uncertainty flags. It must reconcile rather than average.

The Lead Analyst must:

- Produce a final rating for the selected horizon.
- Preserve separate Technical and Fundamental ratings.
- Include a sentiment assessment.
- Explain agreement and disagreement among workstreams.
- Adapt evidence influence to the selected horizon.
- Identify what evidence is decisive and what is merely supportive.
- Assign High, Medium, or Low confidence with reasons.
- State what would change or invalidate the conclusion.
- Reject synthesis when critical evidence is missing, stale, or unresolved.

## Rating System

Use exactly these user-facing recommendation labels:

1. **Strong Buy**
2. **Buy**
3. **Add**
4. **Hold**
5. **Reduce**
6. **Sell**
7. **Avoid**

Every report shows:

- Technical Analyst rating.
- Fundamental Analyst rating.
- Sentiment assessment.
- Lead Analyst final rating.
- High, Medium, or Low confidence.
- A concise rationale.
- Material disagreement.
- Conditions that would change the rating.

Define rating semantics in a versioned policy file before implementation. Do not allow individual prompts to invent new meanings or labels.

## Conviction Checklist

General Research includes a five-point Conviction Checklist: deterministic, threshold-based checkboxes shown with a headline score (for example, 3/5). It is supplementary evidence, not a rating — it never renames, replaces, or overrides the seven-label Rating System above or the Lead Analyst's synthesis. No LLM-generated text is an input to it.

The five criteria (policy version 1.0, defined in `core/conviction_checklist.py`) are trend (price above both the 50-day and 200-day averages), momentum (MACD above its signal and RSI(14) between 40 and 75), relative strength (return over the lookback beats SPY), growth (revenue growth and earnings growth both positive), and street conviction (analyst mean target above the current price).

A criterion that cannot be evaluated from available evidence — a security too new to have a 200-day average, missing growth figures, no analyst target — is reported as not-confirmed with the reason stated, never guessed, and never silently counted toward or against the score. Changing a threshold, or adding or removing a criterion, is a policy change: bump the version and update the policy file's documentation in the same change.

## Potential Investment Strategies

Every report includes a dedicated **Potential Investment Strategies** page or section.

Use only strategies supported by the evidence. Potential strategies may include:

- New-position entry.
- Add on a pullback.
- Add after breakout confirmation.
- Hold and monitor.
- Reduce into strength.
- Profit-taking.
- Risk-control or exit.

For every included strategy, show:

- Intended horizon.
- Who or what position context it applies to.
- Relevant entry or action zone.
- Required confirmation signals.
- Upside objective or monitoring level when defensible.
- Stop, invalidation, or reassessment condition.
- Principal risks.
- Estimated risk/reward when inputs support a valid calculation.

Do not force precise price levels when the evidence does not support them. Label scenario levels as zones rather than false-precision point estimates when appropriate.

## Source Hierarchy

Use the most authoritative source suitable for each claim.

1. Exchange/security-master data for identity and listing details.
2. SEC filings and official company investor-relations material for company disclosures.
3. YCharts for licensed normalized market, financial, valuation, estimate, and rating data.
4. TradingView for public charts, technical indicators, and market context.
5. Established financial-news and analyst-research sources for current developments and commentary.
6. Public X, Reddit, and Stocktwits content for sentiment and narrative evidence only.

Source hierarchy does not justify silently overriding a conflict. When sources materially disagree on price, rating, financial data, dates, or definitions, show both sources and timestamps and ask the user to resolve or refresh the discrepancy.

## Browser and Authentication Rules

- Use the user's existing authenticated browser session for YCharts.
- Never store, request through custom UI, log, transmit to an AI model, or export usernames, passwords, session cookies, API tokens, or browser secrets.
- If YCharts authentication expires, pause and ask the user to sign in through the normal browser interface.
- Use public TradingView and public X research where practical.
- Respect access controls, rate limits, robots rules, licensing, terms, and permitted display/export behavior.
- Do not bypass paywalls, CAPTCHAs, access restrictions, or anti-automation controls.
- Do not claim data retrieval succeeded unless the required fields and provenance were actually captured.
- Provide a manual evidence-upload fallback for sources that cannot be safely or reliably automated, even though automated retrieval is the normal workflow.

## Evidence and Provenance Model

Every research fact must retain:

- Confirmed security identifier.
- Source name.
- Source URL or uploaded filename.
- Publication date when available.
- Retrieval timestamp and timezone.
- Page, section, table, chart, or row locator when applicable.
- Raw value and normalized value when transformation occurs.
- Unit, currency, fiscal period, market session, and calculation method as applicable.
- Responsible workstream.

Separate evidence into:

- Observed fact.
- Deterministic calculation.
- Analyst interpretation.
- Scenario or strategy.
- Unverified claim.

Never allow generated prose to become evidence for another agent.

## Data Conflict and Freshness Gates

- Use one explicit analysis timestamp in America/New_York and retain source-specific retrieval times.
- Compare prices only when market session, currency, adjustment method, and timing are compatible.
- Define freshness requirements by data class and horizon.
- Flag imminent earnings, halted securities, stale quotes, missing filings, illiquidity, unusual volatility, and incomplete chart history.
- Material conflicts are blocking. Ask the user; do not silently apply a hierarchy.
- If a required source is unavailable, disclose the gap and either request user approval to continue with reduced confidence or stop when the missing source is critical.

## Evidence Review Gate

Before PDF generation, show a compact approval screen containing:

- Company, ticker, exchange, security type, and currency.
- Selected horizon and optional position context.
- Current price, quote status, market session, and timestamp.
- Sources successfully used and sources unavailable.
- Major technical signals and preliminary Technical rating.
- Major fundamental signals and preliminary Fundamental rating.
- Sentiment summary.
- Conflicts, missing data, stale data, and uncertainty flags.
- Proposed final rating and confidence.
- Proposed report sections and strategies.

The user can approve, correct the security, remove a questionable source, refresh data, resolve a conflict, or request deeper research.

## PDF Structure

The normal General Research PDF is a concise, highly readable three-page client brief. Specialized comparison, historical-trade, and Deep Technical Analysis reports may expand when needed to preserve evidence and chart legibility. Do not compress material into unreadable text.

For General Research, use this fixed sequence:

1. The user's question, a direct answer, the final rating, and concise decision reasoning.
2. A restrained action/risk plan and one large annotated candlestick chart.
3. Supporting evidence, essential metrics, risks/triggers, sources, and disclosure.

Use a minimal **Researcheus Maximus** wordmark and white page surface. Do not use a large colored title banner. Do not add generic or obvious chart commentary beneath a chart; the chart itself should use short arrows and labels tied to actual dated price or indicator events.

For specialized reports, preserve the relevant parts of this logical structure:

1. Executive Summary and final rating.
2. Current Price and Key Metrics.
3. Technical Analysis with annotated charts.
4. Fundamental Analysis.
5. News, Analyst Commentary, and Social Sentiment.
6. Potential Investment Strategies.
7. Risks, Catalysts, and What Would Change the Rating.
8. Technical, Fundamental, Sentiment, and Lead conclusions with confidence and disagreement.
9. Sources and Disclosure.

The final **Sources** section lists source name, URL or document, publication/retrieval date, and the analysis area supported. Place a short source label directly under important charts.

## Presentation Standards

- Use the Gottfried & Somberg Wealth Management navy-and-gold visual system inherited from Reportus.
- Use annotated charts and concise summaries together.
- Annotate only defensible support, resistance, trend, entry, objective, stop, and invalidation zones.
- Preserve chart axes, timeframe, dates, ticker, exchange, currency, and source label.
- Prefer tables for exact comparisons.
- Keep the executive conclusion readable at a glance.
- Avoid dense walls of prose and unexplained jargon.
- Render and visually inspect every PDF before presenting it.
- Reject clipped text, overlap, illegible charts, incorrect pagination, stale timestamps, missing disclosures, broken links, inconsistent ratings, and missing sources.

## Revision Workflow

After first generation, offer quick actions for:

- Rewrite or shorten a section.
- Deepen the research.
- Change the analysis horizon.
- Rerun the Technical Analyst.
- Rerun the Fundamental Analyst.
- Refresh news or sentiment.
- Adjust chart annotations or strategy levels using refreshed evidence.
- Other / Custom Change.

Revisions that can change data, ratings, price levels, or conclusions must rerun the appropriate retrieval, grounding, conflict, and QA gates. Never implement a factual revision as a prose-only edit.

Do not retain revision-chat history after finalization or cancellation.

## Privacy and Session Lifecycle

- Run local privacy inspection before uploaded files or user-entered position details reach an AI provider or external service.
- Reject account numbers, account identifiers, Social Security or tax identifiers, dates of birth, addresses, phone numbers, email addresses, credentials, secrets, API keys, and bank-routing information.
- Allow company names, ticker symbols, purchase price, quantity, position size, allocation, horizon, and risk tolerance.
- Do not redact prohibited data and continue automatically; reject the affected session and request clean replacement input.
- Use an isolated temporary directory for each research session.
- Retain uploaded files, browser captures, extracted content, charts, agent notes, drafts, and revision context only during the active session.
- After finalization, verify the interactive report opens and passes QA, then delete all temporary session data.
- Delete the same data on cancellation or closing an unfinished session.
- On startup, purge abandoned sessions left by a crash.
- The finalized self-contained HTML report is the retained research artifact. A PDF copy may be printed from the same approved layout.
- Never log user position details, company research text, financial values, credentials, cookies, or source content.

## AI Providers

- Support a paid cloud AI provider for strongest production analysis.
- Preserve optional local Ollama support for development, testing, privacy, or offline use.
- Keep providers replaceable and business logic provider-neutral.
- Require structured outputs at subsystem boundaries.
- Use deterministic code for security resolution checks, privacy inspection, calculations, comparison normalization, source records, chart construction, file handling, and QA.
- Use AI for flexible research planning, visual interpretation, narrative analysis, and synthesis where it is genuinely necessary.
- Never send authentication secrets or browser session data to an AI provider.

## Disclosure

Until the firm supplies approved language, include a professionally written draft disclosure clearly identified in the codebase as compliance-review-required.

The disclosure should state, at minimum, that the material is informational; reflects information and market conditions as of the stated time; relies on sources believed reliable but not guaranteed; contains opinions and scenarios subject to change; is not a guarantee of performance; and involves investment risk, including possible loss of principal.

Do not claim that a generic disclosure makes the report compliant. Client distribution requires firm compliance review and approved wording.

## Desktop and Distribution

- Target standard Windows business laptops without requiring a dedicated GPU.
- Use PySide6 unless a verified constraint requires another framework.
- Keep long research stages off the UI thread.
- Display short, honest progress labels and elapsed time.
- Allow the user to cancel safely.
- Plan for a standard Windows installer with desktop shortcut and uninstaller.
- Keep implementation details out of user-facing screens.

## Engineering Architecture

Use testable packages with typed models at boundaries. A recommended top-level structure is:

```text
config/          product settings, workflow definitions, rating policy
core/            models, state, orchestration, sessions, provider contracts
research/        security resolution, research planning, retrieval
agents/          technical, fundamental, sentiment, lead analyst
sources/         YCharts, TradingView, SEC, IR, news, social adapters
analysis/        deterministic indicators, normalization, comparisons, scoring inputs
charts/          chart capture, reconstruction, annotation, rendering
quality/         grounding, consistency, freshness, citation, visual QA
security/        privacy inspection and safe logging
reports/         PDF content models and branded renderer
ui/              PySide6 windows, pages, widgets, theme
skills/          validated skill packages and their direct resources
tests/           unit, integration, browser-contract, and end-to-end tests
```

Keep source adapters separate from analyst reasoning. Browser navigation changes must not require rewriting analysis logic. Every adapter returns normalized typed evidence plus provenance or a structured failure.

## Skill System

Use skills as bounded, versioned behavior packages. Global rules in this file override every skill.

Initial version-one skills or capabilities should include:

- `single-stock-research` as the primary user-facing workflow.
- `technical-analyst` as a specialist analysis skill.
- `fundamental-analyst` as a specialist analysis skill.
- `sentiment-research` as a supporting capability.
- `lead-analyst` as the synthesis policy.
- `ycharts-research` and `tradingview-research` as source-specific capabilities.
- `client-research-pdf` as the branded output skill.

Load only the selected skill and directly required resources. Validate metadata, required sources, allowed inputs, output contract, privacy compatibility, disclosures, rating semantics, QA rules, and a representative test before enabling a skill.

The architecture must allow future third-party skills and reports without granting them automatic access to credentials, arbitrary browser state, all session data, or final rating authority.

## Testing and Acceptance

Add automated tests for:

- Company-name and ticker resolution, ambiguity, share classes, and invalid symbols.
- Privacy rejection and safe logging.
- Quote timestamp, session, currency, and source reconciliation.
- Source conflict blocking.
- Missing and stale evidence behavior.
- Deterministic indicator calculations against fixed fixtures.
- Multi-timeframe technical-analysis inputs.
- Fundamental-period and metric-definition alignment.
- Sentiment spam, duplication, rumor, and recency handling.
- Agent isolation and structured-output validation.
- Rating-label and horizon-policy consistency.
- Numeric and citation grounding.
- Strategy-level provenance and invalidation conditions.
- Revision-triggered refresh and revalidation.
- PDF pagination, chart legibility, branding, sources, and disclosure.
- Filename versioning.
- Cleanup after finalize, cancel, error, and crash recovery.
- Provider replacement and local fake-provider testing.

Do not claim version one is complete until representative end-to-end tests successfully:

1. Resolve a real public company from both ticker and company-name input.
2. Complete the selected source workflow without exposing credentials.
3. Produce independent Technical and Fundamental ratings.
4. Produce a grounded Lead rating and confidence explanation.
5. Show and approve the Evidence Review.
6. Render a visually verified client-ready PDF with annotated charts, strategies, sources, and disclosure.
7. Apply a revision that changes evidence and rerun the required gates.
8. Export a verified final PDF and prove temporary-session cleanup.

Use synthetic or non-client position data for all automated and representative tests.

## Deferred Work

The following are intentionally deferred beyond version one:

- Portfolio Review UI and generation.
- Persistent research history or saved dossiers.
- Multi-user accounts and collaboration.
- Centralized credential management.
- Automated brokerage connections.
- Unreviewed client distribution.
- Admin installation of arbitrary third-party skills.
- Mobile or macOS applications.

Do not let deferred features complicate or delay the validated Single Stock Research workflow. Preserve clean extension points and no more.

## Reference Basis

These sources inform the professional research principles in this specification:

- CMT Association, technical analysis as analysis of price, volume, momentum, market behavior, and risk: https://cmtassociation.org/
- TradingView, technical-analysis essentials and indicator documentation: https://www.tradingview.com/support/solutions/43000759577/
- TradingView, multi-indicator Technical Ratings methodology: https://www.tradingview.com/support/solutions/43000614331-technical-ratings/
- U.S. SEC, how to read Forms 10-K and 10-Q: https://www.sec.gov/fast-answers/answersreada10khtm.html
- U.S. SEC EDGAR filing search: https://www.sec.gov/edgar/search/
- FINRA, social-media-influenced investing and sentiment tools: https://www.finra.org/rules-guidance/key-topics/fintech/report/social-media-influenced-investing/tools
- FINRA and SEC investor bulletin on risks of social-sentiment tools: https://www.finra.org/investors/insights/social-sentiment-investing-tools
