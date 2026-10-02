# Technical Analyst Agent — web

**This is the primary way to run Technical Analyst Agent.** The PySide6 desktop app
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
| `RESEARCHEUS_REPORTS_DIR` | Where reports are briefly held before delivery (default: system temp). Reports are never kept; see below. |

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
| `GET` | `/r/{id}` | The finished report, for the browser that ran it. Add `?download=1` to save it. Deleted within the hour. |
| `POST` | `/api/feedback` | Record a reader's feedback on a report. |
| `GET` | `/api/feedback` | Read recorded feedback, newest first, with counts. |
| `GET` | `/api/health` | Liveness, and which workflows are configured. |

Research takes minutes, so runs happen in a worker thread and the client polls.
At most `RESEARCHEUS_MAX_CONCURRENT_RUNS` (default 3) run at once; beyond that
the API returns 503 with a clear message rather than queueing invisibly or
exhausting the machine.

## Sessions and retention

**Reports are never kept.** A finished report is held only long enough to reach
the browser that ran it: it is deleted an hour after it is made, and every report
is deleted when the server starts or stops. This is fixed in code; there is no
setting to keep reports and no shareable link. To keep a report, the reader
downloads it, prints it to PDF, or exports slides from inside it. A portfolio is
kept with **Download portfolio**.

There used to be a `RESEARCHEUS_KEEP_REPORTS` switch. The Docker image turned it
on, the kept reports filled the deployment's volume, and every run then failed
with "No space left on device" as it saved its report. The variable is now
ignored.

Within that, two lifetimes are kept apart:

* **Job records** are in-memory progress state, only so the browser can poll a
  run it just started. They expire after six hours.
* **Report files** can briefly outlive the job record, so `/r/{id}` still opens
  a ready report after the record has gone -- until it is deleted.

Temporary session data (working files, chart intermediates) is deleted as soon
as a run ends, including on failure. The desktop app's exported HTML remains the
record copy, and the Track Record log is still written by the desktop app only.

## Deploying

For free hosted deployment and domain migration, follow
[Hosting migration](../docs/hosting.md). The root `render.yaml` defines a
Render Free Docker service with the existing access gate and research engine.

```bash
docker build -t researcheus .
docker run -p 8000:8000 \
  -e RESEARCHEUS_API_KEY=... -e RESEARCHEUS_TVREMIX_KEY=... researcheus
```

The image installs server dependencies without the desktop GUI toolkit.
Hosts that inject `$PORT` are handled. Set credentials as environment
variables; a deployed server has no user keychain.

Reports are temporary and removed within an hour and on restart. Do not mount
anything at `/app/reports`: that would hide the Python report package. Any
optional persistence must use a separate path outside `/app`, such as `/data`.
Render Free has no persistent disk; see the migration guide for feedback and
house-view limitations.

## Running fully offline

Tailwind and all 27 font files are vendored under `web/vendor/`, so the app
itself makes no external requests — it runs with no network at all. Research
naturally still needs the internet to reach Yahoo Finance and TV Remix; only
the interface is self-contained.

Generated reports deliberately keep their remote font link. A report is a
single self-contained file meant to be opened anywhere, so a relative path to
this project's fonts would break it; offline it falls back to the system serif
and sans stacks, which is the intended degradation.

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

Feedback is not a report and is kept. See below for making it survive a deploy.

## Not yet built

Per-user login. Reports sit behind the shared access code and are deleted within
the hour. Still, don't put client-identifying material into a prompt.

## Logging feedback to a Google Doc

Reader feedback is always written to `<reports dir>/_feedback/feedback.jsonl`
and is readable at `GET /api/feedback`. That file is exempt from the report
retention purge, but the reports directory defaults to the system temp
directory — so on a host that redeploys by replacing the container, it does not survive a deploy. Set `RESEARCHEUS_FEEDBACK_DIR` to a mounted
volume, mirror to a Google Doc, or both.

The mirror uses an Apps Script web app rather than the Google Docs API on
purpose: it is authorised by its URL, so this application holds no Google
credentials and cannot act as you.

1. Create the Google Doc that will hold the log.
2. In that doc: **Extensions → Apps Script**, and replace the contents with:

```javascript
function doPost(e) {
  var entry = JSON.parse(e.postData.contents);
  var body = DocumentApp.getActiveDocument().getBody();
  var verdict = entry.helpful === true ? 'Helpful'
              : entry.helpful === false ? 'Not helpful' : 'No rating';
  body.appendParagraph(
    entry.at + '  ·  ' + (entry.ticker || '—') + '  ·  ' +
    (entry.mode || '—') + '  ·  ' + verdict
  ).setHeading(DocumentApp.ParagraphHeading.HEADING3);
  if (entry.message) { body.appendParagraph(entry.message); }
  if (entry.job_id) {
    body.appendParagraph('Report: ' + entry.job_id).setItalic(true);
  }
  return ContentService.createTextOutput('ok');
}
```

3. **Deploy → New deployment → Web app**. Execute as *me*; who has access,
   *Anyone*. Copy the `/exec` URL.
4. Set `RESEARCHEUS_FEEDBACK_WEBHOOK` to that URL on the server and redeploy.

Treat the URL as a secret: anyone holding it can append to the doc. It is only
ever read from the environment — never logged, never sent to a model, never
returned by the API.

Delivery is best-effort and off the request path. The local file is the record
of truth: an entry that cannot be delivered stays pending and is retried on the
next submission and at startup, so nothing is lost while the script is down.
`GET /api/feedback` reports `awaiting_delivery` so a backlog is visible.
