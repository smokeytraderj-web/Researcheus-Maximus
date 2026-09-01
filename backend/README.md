# Researcheus Maximus — web

**This is the primary way to run Researcheus Maximus.** The PySide6 desktop app
still works unchanged (`python3 app.py`) and remains the only route to
YCharts-backed runs and the Track Record log, but the web app is the everyday
vehicle.

Both surfaces share one code path:

```
prompt text
   -> core.request_builder.build_request()   (shared parsing + validation)
   -> services.ResearchRunner / TechnicalRunner
   -> reports.html_report / reports.tvremix_report
```

A question typed into the desktop window and the same question posted to the
API therefore produce the same request and the same report.

## Run

```bash
pip install -r backend/requirements.txt
scripts/run_web.sh                 # http://localhost:8000
```

## Credentials

Keys are resolved server-side, in this order:

1. An **environment variable**, if set.
2. Otherwise the **OS keychain** — the same store the desktop app writes to
   when you tick "remember" in Settings. Running the server on your own machine
   therefore picks up keys you have already saved, instead of silently falling
   back to demo output.

An environment variable always wins, so a real deployment (no user keychain) is
configured purely through the environment.

| Variable | Purpose |
| --- | --- |
| `RESEARCHEUS_API_KEY` | Synthesis provider key. Live research is off without it. |
| `RESEARCHEUS_SYNTHESIS_PROVIDER` | Provider name (default `OpenAI`). |
| `RESEARCHEUS_MODEL` | Optional model override. |
| `RESEARCHEUS_TVREMIX_KEY` | TV Remix key; required for Technical Quick Report. |
| `RESEARCHEUS_DEMO` | Set to `1` to force synthetic output. |
| `RESEARCHEUS_REPORTS_DIR` | Where reports are written (default: system temp). |
| `RESEARCHEUS_KEEP_REPORTS` | Set to `1` to keep reports instead of deleting them. |
| `RESEARCHEUS_REPORT_TTL_HOURS` | Report lifetime, default 6. |

The browser never sends a key and the API never accepts one — credentials must
not cross this boundary. `/api/health` reports only *whether* each key was
found and from where, never a value.

The home page states plainly when it is in demo mode and which key is missing.

YCharts is unavailable on the web (it needs desktop Excel); use the desktop app
for YCharts-backed runs.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/research` | Start a run. Body: `{"prompt": "...", "mode": "general\|deep\|comparison\|technical"}`. Returns a job id. |
| `GET` | `/api/research/{id}` | Poll status: `running` / `ready` / `failed`. |
| `GET` | `/r/{id}` | The finished report — this is the shareable link. |
| `GET` | `/api/reports` | Finished reports, newest first. |
| `POST` | `/api/feedback` | Record a reader's feedback on a report. |
| `GET` | `/api/feedback` | Read recorded feedback, newest first, with counts. |
| `GET` | `/api/health` | Liveness, and which workflows are configured. |

Research takes minutes, so runs happen in a worker thread and the client polls.
At most `RESEARCHEUS_MAX_CONCURRENT_RUNS` (default 3) run at once; beyond that
the API returns 503 with a clear message rather than queueing invisibly or
exhausting the machine.

## Sessions and retention

**Reports are temporary.** They are written to the system temp directory --
never into the project -- expire after `RESEARCHEUS_REPORT_TTL_HOURS` (default
6), and the whole directory is deleted when the server stops. Nothing
accumulates, matching the desktop app's disposable-session rule.

The trade-off is deliberate: **a shared link is good for the life of the server,
not forever.** For durable links, set `RESEARCHEUS_KEEP_REPORTS=1` and point
`RESEARCHEUS_REPORTS_DIR` at a mounted volume (the Docker image does both).

Within that, two lifetimes are kept apart:

* **Job records** are in-memory progress state, only so the browser can poll a
  run it just started. They expire after six hours.
* **Report files** outlive the job record, so `/r/{id}` still resolves after the
  run has been forgotten -- until the report expires or the server stops.

Temporary session data (working files, chart intermediates) is deleted as soon
as a run ends, including on failure. The desktop app's exported HTML remains the
record copy, and the Track Record log is still written by the desktop app only.

## Deploying

```bash
docker build -t researcheus .
docker run -p 8000:8000 -v researcheus-reports:/app/reports \
  -e RESEARCHEUS_API_KEY=... -e RESEARCHEUS_TVREMIX_KEY=... researcheus
```

The image installs `requirements-web.txt` (the desktop requirements without
PySide6 and pywin32 — neither is imported outside `ui/`) plus the backend's
own dependencies. Verified: the whole stack runs with no GUI toolkit and no
keyring installed.

**Mount a volume at `/app/reports`.** The image opts into report retention so
hosted links survive a redeploy; without a volume, each redeploy still wipes
them.

Hosts that inject `$PORT` (Railway, Render, Fly) are handled. Set credentials
as environment variables — a deployed server has no user keychain.

## Feedback

Readers can mark a report useful or not and leave a comment; entries are stored
with the report's ticker and mode as JSON lines beside the reports, and are
readable at `GET /api/feedback`.

Feedback **never alters a rating or an analysis on its own.** A research tool
that silently rewired its conclusions from unvetted public input would be easy
to poison and impossible to audit, and it would break the evidence rules the
rest of the app rests on. Improvement happens by a person reading the feedback
and changing the code or the rating policy — a reviewable change with a version
behind it.

Feedback follows the same retention rule as reports: temporary unless
`RESEARCHEUS_KEEP_REPORTS=1`.

## Not yet built

Login and per-user history. Report URLs are unguessable but **unauthenticated** —
anyone with the link can read the report until it expires. Treat that as public
sharing, and don't put client-identifying material into a prompt.
