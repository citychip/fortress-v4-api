"""
Synthetic sync — refresh derived state without hitting any broker.

Used when greeks_backend == "bs_yfinance" and no IBKR session is available.
Doesn't change positions; just refreshes deltas/IV via BS-from-yfinance,
recomputes spy_hedge_coverage, bumps the timestamps.

The user gets the latest BS-estimated Greeks against the most recent
known position book, which is the right behavior when the broker side
is offline or untrusted.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("fortress.ibkr_sync_synthetic")


def sync_synthetic(existing_positions: list[dict], settings: dict) -> dict:
    """No broker calls. Refresh BS deltas + spy_hedge_coverage + timestamps."""
    from app.services import state, bs_fallback

    cur = state.get_active_positions() or {}
    positions = list(existing_positions or cur.get("positions") or [])

    # Refresh BS deltas in place
    try:
        summary = bs_fallback.fill_missing_deltas(positions)
        logger.info("synthetic bs_fallback: %s", summary)
    except Exception as e:
        logger.warning("synthetic BS fallback failed: %s", e)

    # Recompute SPY hedge coverage
    net_liq = cur.get("net_liq")
    target_min, target_max = 20000, 30000
    spy_legs = [p for p in positions if (p.get("strategy") or "").upper() == "SPY_HEDGE"]
    hedge_mv = sum(p.get("market_value") or 0 for p in spy_legs)
    spy_coverage = {
        "hedge_market_value": round(hedge_mv, 2),
        "hedge_net_market_value": round(hedge_mv, 2),
        "hedge_pct_of_netliq": round(hedge_mv / net_liq * 100, 2) if net_liq else None,
        "target_min": target_min,
        "target_max": target_max,
        "coverage_ok": target_min <= hedge_mv <= target_max,
        "legs_count": len(spy_legs),
    }

    now = datetime.now(timezone.utc).isoformat()
    return {
        **{k: cur.get(k) for k in (
            "net_liq", "excess_liquidity", "available_funds", "buying_power",
            "daily_pnl", "unrealized_pnl",
        ) if cur.get(k) is not None},
        "_last_updated": now,
        # Keep ibkr_last_sync from previous successful sync, so staleness banner
        # reflects the last time we had ground-truth positions, not when we
        # last refreshed BS deltas
        "ibkr_last_sync": cur.get("ibkr_last_sync"),
        "spy_hedge_coverage": spy_coverage,
        "positions": positions,
    }
