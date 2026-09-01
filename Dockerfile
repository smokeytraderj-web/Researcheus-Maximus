# Researcheus Maximus web server.
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
ENV RESEARCHEUS_REPORTS_DIR=/app/reports \
    RESEARCHEUS_KEEP_REPORTS=1
RUN mkdir -p /app/reports
VOLUME ["/app/reports"]

# Hosts that inject $PORT (Railway, Render, Fly) override this.
ENV PORT=8000
EXPOSE 8000

# 0.0.0.0 so the container is reachable from outside itself.
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
