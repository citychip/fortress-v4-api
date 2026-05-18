"""
SSE stream endpoint — pushes briefing/positions/alerts diffs to connected clients.

Design:
- Single persistent GET /api/stream connection per browser tab
- Pushes data every POLL_INTERVAL seconds if a hash change is detected
- Each event is a JSON object: { "type": "briefing"|"positions"|"alerts", "data": {...} }
- Client uses EventSource; on message, calls queryClient.setQueryData() for the matching key
- Falls back gracefully: if the client disconnects, the generator exits cleanly
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.routes.briefing import get_briefing
from app.services import state

logger = logging.getLogger("fortress.stream")
router = APIRouter()

POLL_INTERVAL = 5  # seconds between data checks
KEEPALIVE_INTERVAL = 20  # seconds between keepalive pings


def _hash(obj: object) -> str:
    """Stable hash of a JSON-serialisable object."""
    return hashlib.md5(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


async def _event_generator(request: Request) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted strings until the client disconnects."""
    last_hashes: dict[str, str] = {}
    ticks_since_keepalive = 0

    while True:
        # Check if client has disconnected
        if await request.is_disconnected():
            logger.info("SSE client disconnected")
            break

        events_sent = 0

        # ── briefing ──────────────────────────────────────────────────────
        try:
            briefing = get_briefing()
            h = _hash(briefing)
            if last_hashes.get("briefing") != h:
                last_hashes["briefing"] = h
                yield f"event: briefing\ndata: {json.dumps(briefing, default=str)}\n\n"
                events_sent += 1
        except Exception as exc:
            logger.warning("SSE briefing error: %s", exc)

        # ── positions ─────────────────────────────────────────────────────
        try:
            positions = state.get_active_positions()
            h = _hash(positions)
            if last_hashes.get("positions") != h:
                last_hashes["positions"] = h
                yield f"event: positions\ndata: {json.dumps(positions, default=str)}\n\n"
                events_sent += 1
        except Exception as exc:
            logger.warning("SSE positions error: %s", exc)

        # ── alerts ────────────────────────────────────────────────────────
        try:
            alerts = state.get_alerts()
            h = _hash(alerts)
            if last_hashes.get("alerts") != h:
                last_hashes["alerts"] = h
                yield f"event: alerts\ndata: {json.dumps(alerts, default=str)}\n\n"
                events_sent += 1
        except Exception as exc:
            logger.warning("SSE alerts error: %s", exc)

        # ── keepalive comment (prevents proxy timeouts) ───────────────────
        ticks_since_keepalive += 1
        if ticks_since_keepalive >= (KEEPALIVE_INTERVAL // POLL_INTERVAL):
            yield ": keepalive\n\n"
            ticks_since_keepalive = 0

        await asyncio.sleep(POLL_INTERVAL)


@router.get("/stream")
async def sse_stream(request: Request):
    """
    Server-Sent Events stream for real-time dashboard updates.

    Pushes briefing, positions, and alerts as named events whenever their
    content changes. The client subscribes once and receives diffs only.

    This endpoint is exempt from bearer token auth (handled in middleware.py).
    Authentication is enforced by requiring the token as a query parameter:
    GET /api/stream?token=<bearer_token>
    """
    # Validate token from query param (since EventSource cannot set headers)
    import os
    token_param = request.query_params.get("token", "")
    expected = os.environ.get("FORTRESS_API_TOKEN", "")
    if not expected or token_param != expected:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")

    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
