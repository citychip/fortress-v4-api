"""
Fortress Dashboard — FastAPI entry point.

Phase 1: read-only views (briefing, positions, candidates, calendar, universe, journal)
Phase 2: write capability (alerts, journal, calendar, universe edits — endpoints exist, UI partial)
Phase 3: upload pipeline (IBKR OCR + chart annotation)
Phase 4: strategy logic engines (stop-loss aggregator, roll evaluator, post-earnings playbook)
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.middleware import bearer_token_middleware

from app.routes import (
    settings,
    earnings_fetch,
    ibkr,
    alerts,
    briefing,
    calendar,
    candidates,
    chart,
    journal,
    manage,
    playbook,
    positions,
    run,
    universe,
    uploads,
)


logger = logging.getLogger("fortress")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


app = FastAPI(
    title="Fortress Dashboard",
    description="Trading dashboard per Build Spec v1.2 — the trader's portfolio strategy v3.4",
    version="1.2.0",
)

# CORS — open for local network use. Lock down before exposing publicly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bearer token authentication — must come after CORS
app.add_middleware(BaseHTTPMiddleware, dispatch=bearer_token_middleware)

# Mount routes under /api
app.include_router(briefing.router, prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(candidates.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(universe.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(journal.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(run.router, prefix="/api")
app.include_router(manage.router, prefix="/api")
app.include_router(ibkr.router, prefix="/api")
app.include_router(playbook.router, prefix="/api")
app.include_router(chart.router, prefix="/api")
app.include_router(earnings_fetch.router, prefix="/api")
app.include_router(settings.router, prefix="/api")



@app.get("/api/token")
def get_token():
    """Return the API token for the browser dashboard. Exempt from bearer auth."""
    import os
    token = os.environ.get("FORTRESS_API_TOKEN", "")
    return {"token": token}

@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


# Static files — the dashboard frontend lives in app/static/
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    """Serve the dashboard at root."""
    return FileResponse(STATIC_DIR / "index.html")
