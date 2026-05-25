"""
app/middleware.py
Fortress Dashboard — Bearer token authentication middleware.

Validates Authorization: Bearer <token> on all /api/* routes except /api/health.
Static files and the root index are always public.

Token is read from FORTRESS_API_TOKEN environment variable.
If the env var is not set, all requests are rejected with 401 (fail-secure).

Per MCP Proposal §4 (Build Spec v1.8).
"""
import os
import logging
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("fortress.auth")

EXPECTED_TOKEN = os.environ.get("FORTRESS_API_TOKEN", "")

EXEMPT_PREFIXES = ("/static", "/api/health", "/", "/api/manage/hydrate-asset", "/api/manage/hydrated-assets")


async def bearer_token_middleware(request: Request, call_next):
    """FastAPI middleware: enforce Bearer token on /api/* (except /api/health)."""
    path = request.url.path

    # Exempt: static files, health check, and root index
    if path == "/" or path.startswith("/static") or path in ("/api/health", "/api/token", "/api/manage/hydrate-asset", "/api/manage/hydrated-assets") or path in ("/api/stream", "/api/stream/") or path.startswith("/api/trpc"):
        return await call_next(request)

    # All other /api/* routes require a valid token
    if path.startswith("/api"):
        if not EXPECTED_TOKEN:
            logger.warning("FORTRESS_API_TOKEN not set — rejecting request to %s", path)
            return JSONResponse(
                status_code=401,
                content={"detail": "server_misconfigured", "hint": "FORTRESS_API_TOKEN env var not set"},
            )
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != EXPECTED_TOKEN:
            logger.warning("Invalid or missing Bearer token for %s", path)
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid_token"},
            )

    return await call_next(request)
