"""
app/middleware.py
Fortress Dashboard — Bearer token authentication middleware.

Accepts two valid tokens:
  FORTRESS_API_TOKEN  — browser/frontend token (set in the main service file)
  FORTRESS_MCP_TOKEN  — Claude MCP token (set in systemd override.conf)

Either token grants full access.  This allows the browser and Claude MCP
to use different tokens without interfering with each other.

Token is read from environment variables at startup.
If neither env var is set, all requests are rejected with 401 (fail-secure).
"""
import os
import logging
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger('fortress.auth')

_API_TOKEN = os.environ.get('FORTRESS_API_TOKEN', '')
_MCP_TOKEN = os.environ.get('FORTRESS_MCP_TOKEN', '')
VALID_TOKENS = {t for t in [_API_TOKEN, _MCP_TOKEN] if t}

EXEMPT_PATHS = {'/api/health', '/api/token', '/api/manage/hydrate-asset', '/api/manage/hydrated-assets', '/api/stream', '/api/stream/'}


async def bearer_token_middleware(request: Request, call_next):
    path = request.url.path

    # Always public: static, root, health, stream
    if (path == '/' or path.startswith('/static') or
            path in EXEMPT_PATHS or path.startswith('/api/trpc')):
        return await call_next(request)

    if path.startswith('/api'):
        if not VALID_TOKENS:
            logger.warning('No auth tokens configured — rejecting %s', path)
            return JSONResponse(
                status_code=401,
                content={'detail': 'server_misconfigured', 'hint': 'FORTRESS_API_TOKEN env var not set'},
            )
        auth = request.headers.get('authorization', '')
        token = auth[7:] if auth.startswith('Bearer ') else ''
        if token not in VALID_TOKENS:
            logger.warning('Invalid or missing Bearer token for %s', path)
            return JSONResponse(status_code=401, content={'detail': 'invalid_token'})

    return await call_next(request)
