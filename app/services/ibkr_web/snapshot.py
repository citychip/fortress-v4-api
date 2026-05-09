"""
/iserver/marketdata/snapshot — two-step pattern per IBKR docs.

The first request "primes" IServer to begin streaming the requested
contracts; it returns the conids but no data values. Subsequent
requests return data. We sleep between them.

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

PRIME_WAIT_S = 1.5  # Sleep between preflight and read; docs say "may take a few moments"


def snapshot(
    client: WebApiClient,
    conids: list[int],
    fields: Optional[list[str]] = None,
    force_prime: bool = False,
) -> list[dict]:
    """Return per-conid data dicts. Performs preflight if any conid is unprimed.

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

    needs_prime = force_prime or any(c not in _PRIMED for c in conids)
    if needs_prime:
        logger.debug("Preflighting %d conids", len(conids))
        client.get("/iserver/marketdata/snapshot", params={
            "conids": ",".join(str(c) for c in conids),
            "fields": ",".join(fields),
        })
        for c in conids:
            _PRIMED.add(c)
        time.sleep(PRIME_WAIT_S)

    rows = client.get("/iserver/marketdata/snapshot", params={
        "conids": ",".join(str(c) for c in conids),
        "fields": ",".join(fields),
    })
    return rows or []


def reset_prime_cache():
    """Clear primed-conid cache. Call on session loss / re-auth."""
    _PRIMED.clear()
