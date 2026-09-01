# Technical Analyst Agent web server.
#
# The desktop app is not part of this image: PySide6 is a GUI toolkit with no
# role on a server, so only the research core, the backend and the frontend are
# installed. requirements-web.txt is requirements.txt minus the desktop-only
# packages for that reason.
FROM python:3.12-slim

# matplotlib renders the charts and needs no display; fonts keep chart text
# from falling back to boxes on a slim image.
ENV MPLBACKEND=Agg \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-web.txt backend/requirements.txt ./deps/
RUN pip install -r deps/requirements-web.txt -r deps/requirements.txt

COPY backend/ ./backend/
COPY core/ ./core/
COPY reports/ ./reports/
# The approved report stylesheets live here and are read at render time.
COPY resources/ ./resources/
COPY research/ ./research/
COPY security/ ./security/
COPY services/ ./services/
COPY web/ ./web/

# Reports are temporary by default and deleted when the server stops. A hosted
# deployment usually wants the opposite -- links that survive a redeploy -- so
# it points them at a mounted volume and opts into retention.
#
# There is deliberately no VOLUME instruction: Railway rejects the whole
# Dockerfile if it finds one ("docker VOLUME ... is not supported, use Railway
# Volumes"). Persistence is attached by the host instead, mounted over this
# path. Without such a mount the directory is ordinary container storage and
# reports last only as long as the container, which is the same disposable
# behaviour the app has by default.
#
# The path lives outside /app, and must keep doing so. A host volume mounts an
# EMPTY filesystem over its mount point, hiding whatever the image put there.
# Pointed at /app/reports it therefore erased the reports/ Python package, and
# the server died on startup with "No module named 'reports.call_log'". Any
# directory under /app that shares a name with a package here is the same trap.
ENV RESEARCHEUS_REPORTS_DIR=/data/reports \
    RESEARCHEUS_KEEP_REPORTS=1
RUN mkdir -p /data/reports

# Hosts that inject $PORT (Railway, Render, Fly) override this.
ENV PORT=8000
EXPOSE 8000

# 0.0.0.0 so the container is reachable from outside itself.
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
