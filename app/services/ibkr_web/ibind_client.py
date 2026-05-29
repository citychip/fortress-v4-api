"""
ibind IbkrClient singleton for Fortress V4.
Replaces direct HTTP calls to CP Gateway with OAuth 1.0a via ibind.

All credentials are read from env vars in the systemd override.conf:
  IBIND_USE_OAUTH, IBIND_OAUTH1A_CONSUMER_KEY, IBIND_OAUTH1A_ACCESS_TOKEN,
  IBIND_OAUTH1A_ACCESS_TOKEN_SECRET, IBIND_OAUTH1A_DH_PRIME,
  IBIND_OAUTH1A_ENCRYPTION_KEY_FP, IBIND_OAUTH1A_SIGNATURE_KEY_FP,
  IBIND_ACCOUNT_ID
"""
import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client: Optional[Any] = None
_init_error: Optional[str] = None
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ibind")


def is_ibkr_enabled() -> bool:
    """Check the use_ibkr_web_api toggle from settings."""
    try:
        from app.services.settings_service import get_settings
        s = get_settings()
        return bool(s.get("security", {}).get("use_ibkr_web_api", True))
    except Exception:
        return True


def get_client():
    """Get or initialize the ibind IbkrClient singleton (thread-safe first call)."""
    global _client, _init_error

    if _client is not None:
        return _client

    if not is_ibkr_enabled():
        raise RuntimeError("IBKR integration is disabled (use_ibkr_web_api=false in settings)")

    try:
        from ibind import IbkrClient
        account_id = os.environ.get("IBIND_ACCOUNT_ID", "U7453366")
        _client = IbkrClient(account_id=account_id)
        _init_error = None
        logger.info(f"ibind IbkrClient ready (account={account_id})")
        return _client
    except Exception as exc:
        _init_error = str(exc)
        logger.error(f"ibind IbkrClient init failed: {exc}")
        raise


def reset_client():
    """Tear down and reset — next get_client() call re-initialises OAuth."""
    global _client, _init_error
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None
    _init_error = None
    logger.info("ibind IbkrClient reset — will re-initialise on next call")


# ── Async helpers (ibind is synchronous; run in thread pool) ─────────────────

async def _run(fn, *args, **kwargs):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, partial(fn, *args, **kwargs))
    return result.data if hasattr(result, "data") else result


async def get(path: str, params: dict = None) -> Any:
    c = get_client()
    return await _run(c.get, path, params=params)


async def post(path: str, data: dict = None) -> Any:
    c = get_client()
    return await _run(c.post, path, json=data or {})


async def call(method_name: str, *args, **kwargs) -> Any:
    """Call any named ibind method, e.g. await call('portfolio_accounts')."""
    c = get_client()
    return await _run(getattr(c, method_name), *args, **kwargs)
