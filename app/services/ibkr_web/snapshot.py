"""
/iserver/marketdata/snapshot — two-step pattern per IBKR docs.

The first request "primes" IServer to begin streaming the requested
contracts; it returns the conids but no data values. Subsequent
requests return data.

We retry with exponential backoff instead of a fixed sleep so that
fast-responding sessions don't wait unnecessarily and slow sessions
don't time out prematurely.

We also cache primed conids per-process so we only preflight once
per (conid, fields) tuple.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from app.services.ibkr_web import SNAPSHOT_FIELDS
from app.services.ibkr_web.client import WebApiClient

logger = logging.getLogger("fortress.ibkr_web.snapshot")

# Conids that have been primed in this process. Cleared on process restart.
_PRIMED: set[int] = set()

# Retry delays (seconds) after the prime request.
# Three attempts at 0.5 s, 1.0 s, 2.0 s → max 3.5 s total wait vs 1.5 s fixed.
_RETRY_DELAYS_S = (0.5, 1.0, 2.0)


def _has_data(rows: list[dict], fields: list[str]) -> bool:
    """Return True if at least one row has a non-null value for any requested field."""
    for row in rows:
        for f in fields:
            v = row.get(f)
            if v not in (None, "", "N/A"):
                return True
    return False


def snapshot(
    client: WebApiClient,
    conids: list[int],
    fields: Optional[list[str]] = None,
    force_prime: bool = False,
) -> list[dict]:
    """Return per-conid data dicts. Performs preflight if any conid is unprimed.

    Uses retry-with-backoff after the prime request instead of a fixed sleep,
    returning as soon as data is available.

    Args:
        conids: list of IBKR contract IDs (ints).
        fields: numeric field tags as strings. Defaults to SNAPSHOT_FIELDS.
        force_prime: if True, always preflight even if conids are primed.

    Returns:
        list[dict] — each dict has keys "conid", "conidEx", and the requested
        field tags as string keys (matching IBKR's response shape).
    """
    if not conids:
        return []
    fields = fields or SNAPSHOT_FIELDS
    params = {
        "conids": ",".join(str(c) for c in conids),
        "fields": ",".join(fields),
    }

    needs_prime = force_prime or any(c not in _PRIMED for c in conids)
    if needs_prime:
        logger.debug("Preflighting %d conids", len(conids))
        client.get("/iserver/marketdata/snapshot", params=params)
        for c in conids:
            _PRIMED.add(c)

        # Retry with backoff until data arrives or retries exhausted
        rows: list[dict] = []
        for attempt, delay in enumerate(_RETRY_DELAYS_S, start=1):
            time.sleep(delay)
            rows = client.get("/iserver/marketdata/snapshot", params=params) or []
            if _has_data(rows, fields):
                logger.debug(
                    "Snapshot data ready after attempt %d (%.1fs delay)", attempt, delay
                )
                return rows
            logger.debug("Snapshot attempt %d: no data yet, retrying", attempt)

        logger.warning(
            "Snapshot returned no data after %d retries for conids %s",
            len(_RETRY_DELAYS_S),
            conids,
        )
        return rows

    rows = client.get("/iserver/marketdata/snapshot", params=params)
    return rows or []


def reset_prime_cache():
    """Clear primed-conid cache. Call on session loss / re-auth."""
    _PRIMED.clear()
