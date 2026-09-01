# Researcheus Maximus — web backend

Serves the same research workflows as the PySide6 desktop app over HTTP, so a
report can be opened and shared as a URL. **The desktop app is unchanged** and
still runs standalone with `python3 app.py`.

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

Demo mode is the default (synthetic evidence, no credentials, no network).
For live research, set these in the **server** environment before starting:

| Variable | Purpose |
| --- | --- |
| `RESEARCHEUS_API_KEY` | Synthesis provider key. Live research is off without it. |
| `RESEARCHEUS_SYNTHESIS_PROVIDER` | Provider name (default `OpenAI`). |
| `RESEARCHEUS_MODEL` | Optional model override. |
| `RESEARCHEUS_TVREMIX_KEY` | TV Remix key; required for Technical Quick Report. |

Keys are read from the server environment only. The browser never sends a key
and the API never accepts one — credentials must not cross this boundary.

YCharts is unavailable on the web (it needs desktop Excel); use the desktop app
for YCharts-backed runs.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/research` | Start a run. Body: `{"prompt": "...", "mode": "general\|deep\|comparison\|technical"}`. Returns a job id. |
| `GET` | `/api/research/{id}` | Poll status: `running` / `ready` / `failed`. |
| `GET` | `/r/{id}` | The finished report — this is the shareable link. |
| `GET` | `/api/health` | Liveness, and whether live research is configured. |

Research takes minutes, so runs happen in a worker thread and the client polls.

## Sessions and retention

Two lifetimes are kept deliberately apart:

* **Job records** are in-memory progress state, only so the browser can poll a
  run it just started. They expire after six hours.
* **Reports** are files under `output/web-sessions/<id>/`. A shared link must
  keep working, so `/r/{id}` resolves the report from disk and never consults
  the job registry -- links survive job expiry and server restarts. Startup
  purges only *unfinished* directories (crash leftovers), never finished
  reports.

Temporary session data (working files, chart intermediates) still follows the
desktop app's disposable-session rule and is deleted as soon as a run ends,
including on failure. The desktop app's exported HTML remains the record copy,
and the Track Record log is still written by the desktop app only.

Reports accumulate on disk. Delete `output/web-sessions/` to clear them; doing
so breaks any link already shared.

## Not yet built

Login and per-user history. Report URLs are unguessable but **unauthenticated** —
anyone with the link can read the report until it expires. Treat that as public
sharing, and don't put client-identifying material into a prompt.
