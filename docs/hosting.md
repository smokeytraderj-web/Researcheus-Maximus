# Hosting migration: Railway to Render Free

This repo contains the full Python research backend and its web interface.
`render.yaml` deploys the existing Docker image to Render's Free web-service
plan; it does not replace the research engine with a static demo.

## Create the replacement service

1. Sign in to https://dashboard.render.com with GitHub.
2. Choose **New → Blueprint**, select `smokeytraderj-web/Researcheus-Maximus`
   on `main`, and use the root `render.yaml`.
3. Confirm the service plan is **Free**. Supply `RESEARCHEUS_ACCESS_CODE`
   and `RESEARCHEUS_TVREMIX_KEY` in Render's secret fields. Never commit keys.
   The TV Remix key is needed for the dedicated technical workflow.
4. Deploy. Render generates the cookie signing secret automatically.
5. Optional: add `RESEARCHEUS_API_KEY` to the service's environment for AI
   synthesis, plus the existing provider/model settings if used. Live general
   research can use deterministic synthesis without this key. API usage is
   separate from hosting and may incur charges.
6. Open the actual URL assigned by Render. Check `/api/health`, unlock the app,
   complete a technical report, and download it. Also check a general report
   and a small portfolio before switching DNS.

The configuration limits single-stock runs to one at a time and numerical
library threads to one to reduce memory pressure. Portfolio research must also
be checked against the Free service's 512 MB limit. A local configuration check
is not proof that a hosted research run fits those resources.

## Reconnect the domain

The extension currently recognizes `gswmai.online` and `www.gswmai.online`.
Confirm that this is still the intended domain before changing DNS.

1. In the new service, open **Settings → Custom Domains** and add the intended
   hostname. Follow Render's instructions for the apex and `www` arrangement.
2. At the domain's DNS provider, replace only the old Railway web-hosting
   records with the exact records Render displays. Preserve email and other
   unrelated records. Do not guess the destination from the service name.
3. Verify the domain in Render and wait for HTTPS to become ready.
4. Test research and downloads through the custom domain.
5. Once verified, remove the old custom-domain attachment and stop/delete the
   old Railway service if that account remains accessible. Repo edits do not
   cancel a Railway subscription or delete its resources.

No domain is attached by this Blueprint, so creating the replacement does not
reroute the existing domain prematurely.

## Free plan behavior and temporary data

Render Free sleeps after 15 minutes without inbound traffic and typically
needs about a minute to wake. Its filesystem is ephemeral; data disappears on
restart, redeploy, or sleep. Reports already expire within an hour and are
removed on shutdown/startup. Download finished reports promptly.

House views and local feedback are also lost without external persistence.
If feedback must survive, configure the existing external feedback webhook.
Do not attach a disk or database expecting it to be free.

The full app cannot be published unchanged on Sites: its Python dependencies,
long-running threaded jobs, and local report generation require a Python
server. A Sites migration would be a separate backend rewrite.

References:
- https://render.com/docs/blueprint-spec
- https://render.com/docs/free
- https://render.com/docs/custom-domains
