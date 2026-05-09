"""
/portfolio/* endpoint wrappers.

Per docs: /portfolio/accounts MUST be called before any other /portfolio/*
endpoint, and ideally cached for the session.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.services.ibkr_web.client import WebApiClient

logger = logging.getLogger("fortress.ibkr_web.portfolio")


def list_accounts(client: WebApiClient) -> list[dict]:
    """GET /portfolio/accounts. MUST be called before any other /portfolio/* call."""
    return client.get("/portfolio/accounts")


def list_subaccounts(client: WebApiClient) -> list[dict]:
    """GET /portfolio/subaccounts. For FA / multi-account structures."""
    return client.get("/portfolio/subaccounts")


def account_summary(client: WebApiClient, account_id: str) -> dict:
    """GET /portfolio/{accountId}/summary. NetLiq, ExcessLiq, AvailableFunds, etc."""
    return client.get(f"/portfolio/{account_id}/summary")


def account_ledger(client: WebApiClient, account_id: str) -> dict:
    """GET /portfolio/{accountId}/ledger. Cash balances by currency."""
    return client.get(f"/portfolio/{account_id}/ledger")


def positions(client: WebApiClient, account_id: str, page_id: int = 0) -> list[dict]:
    """GET /portfolio/{accountId}/positions/{pageId}.

    Returns up to 100 positions per page; iterate for accounts with more.
    """
    return client.get(f"/portfolio/{account_id}/positions/{page_id}")


def all_positions(client: WebApiClient, account_id: str, max_pages: int = 10) -> list[dict]:
    """Walk the paginated positions endpoint until we get an empty page."""
    out: list[dict] = []
    for page in range(max_pages):
        rows = positions(client, account_id, page)
        if not rows:
            break
        out.extend(rows)
        if len(rows) < 100:
            break
    return out


def extract_summary_field(summary: dict, key: str) -> Optional[float]:
    """Pull a numeric value from /portfolio/.../summary.

    Summary keys map to objects shaped like:
      {"amount": 0.0, "currency": "USD", "value": "85629.83", "timestamp": ...}

    We return float(value) when present; None otherwise.
    """
    entry = summary.get(key)
    if not isinstance(entry, dict):
        return None
    raw = entry.get("amount", entry.get("value"))
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
