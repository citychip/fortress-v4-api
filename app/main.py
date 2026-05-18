"""
Fortress Dashboard — FastAPI entry point.

Phase 1: read-only views (briefing, positions, candidates, calendar, universe, journal)
Phase 2: write capability (alerts, journal, calendar, universe edits — endpoints exist, UI partial)
Phase 3: upload pipeline (IBKR OCR + chart annotation)
Phase 4: strategy logic engines (stop-loss aggregator, roll evaluator, post-earnings playbook)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.middleware import bearer_token_middleware
from app.services import config_store

from app.routes import (
    pnl,
    options,
    orders,
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
    market_intelligence,
    playbook,
    positions,
    run,
    universe,
    uploads,
)


logger = logging.getLogger("fortress")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---------------------------------------------------------------------------
# IBKR auto-sync background task  (item A)
# ---------------------------------------------------------------------------
_auto_sync_task: asyncio.Task | None = None


async def _ibkr_auto_sync_loop() -> None:
    """Background task: sync IBKR every N minutes when auto-sync is enabled."""
    while True:
        interval_min = config_store.cfg("security.ibkr_auto_sync_interval_min", 15)
        await asyncio.sleep(interval_min * 60)
        if not config_store.cfg("security.ibkr_auto_sync_enabled", False):
            continue  # feature toggled off — keep looping but skip sync
        try:
            from app.routes.ibkr import trigger_sync
            logger.info("Auto-sync IBKR: firing scheduled sync (interval=%dm)", interval_min)
            await trigger_sync()
        except Exception as exc:
            logger.warning("Auto-sync IBKR: sync failed — %s", exc)


@asynccontextmanager
async def lifespan(app_: FastAPI):
    global _auto_sync_task
    config_store.load()
    _auto_sync_task = asyncio.create_task(_ibkr_auto_sync_loop())
    logger.info("IBKR auto-sync background task started.")
    yield
    if _auto_sync_task:
        _auto_sync_task.cancel()


app = FastAPI(
    title="Fortress Dashboard",
    description="Trading dashboard per Build Spec v1.2 — the trader's portfolio strategy v3.4",
    version="1.2.0",
    lifespan=lifespan,
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
app.include_router(market_intelligence.router, prefix="/api")
app.include_router(options.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(pnl.router, prefix="/api")



@app.get("/api/token")
def get_token():
    """Return the API token for the browser dashboard. Exempt from bearer auth."""
    import os
    token = os.environ.get("FORTRESS_API_TOKEN", "")
    return {"token": token}

@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


# Frontend is served by nginx from /var/www/fortress-v2/ (port 3000).
# FastAPI only handles /api/* routes.
