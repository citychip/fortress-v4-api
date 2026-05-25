"""
app/routes/ibkr.py
Fortress Dashboard — IB Gateway API Routes
Phase 3: Direct IBKR sync endpoints replacing OCR-based upload.

Endpoints:
  GET  /api/ibkr/status     — Check if the IB Gateway container is reachable
  POST /api/ibkr/sync       — Trigger a full sync from IB Gateway
  GET  /api/ibkr/preview    — Fetch live data without writing to disk (dry run)

Design note: ib_async uses its own asyncio event loop. FastAPI/uvicorn also
runs an event loop. To avoid "this event loop is already running", the sync
service runs ib_async in a dedicated background thread (via threading.Thread
with its own loop). The FastAPI route uses asyncio.get_event_loop().run_in_executor
to call the synchronous wrapper without blocking the uvicorn event loop.
"""
from __future__ import annotations

import asyncio
import logging
from fastapi import APIRouter, HTTPException
from app.services import state, config_store

logger = logging.getLogger("fortress.ibkr")
router = APIRouter(tags=["ibkr"])


@router.get("/ibkr/status")
async def get_gateway_status():
    """
    Check whether the IB Gateway Docker container is reachable and connected.
    Returns connection status, account ID, and any error message.
    """
    try:
        loop = asyncio.get_event_loop()
        status = await loop.run_in_executor(None, gateway_status)
        return status
    except Exception as e:
        logger.error("Gateway status check failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ibkr/sync")
async def trigger_sync(backend: str | None = None):
    """Trigger a full sync. Dispatches to the appropriate backend.

    Resolution order:
      1. ?backend= query param (web_api / bs_yfinance) — one-shot override
      2. settings.greeks_backend == "auto": web_api > bs_yfinance per capability
      3. settings.greeks_backend explicit: respected (graceful fallback for web_api → bs_yfinance)
    """
    from app.services.ibkr_web import capability as cap_mod

    if backend and backend not in {"web_api", "bs_yfinance"}:
        raise HTTPException(status_code=400,
            detail=f"backend must be web_api / bs_yfinance; got {backend!r}")

    try:
        existing_data = state.get_active_positions()
        existing_positions = (
            existing_data.get("positions", []) if isinstance(existing_data, dict) else []
        )

        settings = state.get_dashboard_settings()
        # Security toggle: when IBKR Web API is disabled, force synthetic backend
        ibkr_enabled = config_store.cfg("security.use_ibkr_web_api", True)
        if not ibkr_enabled:
            chosen = "bs_yfinance"
            logger.info("Sync dispatcher: IBKR Web API disabled in Settings — forcing bs_yfinance")
        elif backend:
            chosen = backend
        else:
            cap = cap_mod.get_capability()
            chosen = state.resolve_greeks_backend(settings, cap)
        logger.info("Sync dispatcher: chosen backend = %s", chosen)

        if chosen == "web_api":
            from app.services import ibkr_sync_web
            synced = await asyncio.get_event_loop().run_in_executor(
                None, ibkr_sync_web.sync_via_web_api, existing_positions, settings
            )
        else:  # bs_yfinance
            from app.services import ibkr_sync_synthetic
            synced = await asyncio.get_event_loop().run_in_executor(
                None, ibkr_sync_synthetic.sync_synthetic, existing_positions, settings
            )

        synced["greeks_backend_used"] = chosen
        positions = synced.pop("positions", [])
        
        # --- Enrich with beta data (IBKR primary, yFinance fallback) ---
        ticker_set = set()
        for p in positions:
            t = p.get("ticker")
            if t:
                ticker_set.add(t)
        
        betas = {}
        if ticker_set:
            try:
                from app.services import beta_weights
                tickers = sorted(ticker_set)
                betas = beta_weights.fetch_betas_for_portfolio(tickers, {"positions": positions})
            except Exception as e:
                logger.warning("Beta-weight fetch failed (non-fatal): %s", e)
        
        # Add betas to positions data for downstream use
        new_data = {**synced, "positions": positions, "_betas": betas}
        state.save_positions(new_data)
        cap_mod.invalidate()  # capability may have changed (e.g. session refreshed)

        return {
            "status": "ok",
            "synced_at": synced.get("ibkr_last_sync") or synced.get("_last_updated"),
            "positions_count": len(positions),
            "backend": chosen,
            "ibkr_web_api_enabled": ibkr_enabled,
            "net_liq": synced.get("net_liq"),
            "excess_liquidity": synced.get("excess_liquidity"),
            "available_funds": synced.get("available_funds"),
        }

    except TimeoutError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "gateway_unreachable",
                "message": str(e),
                "hint": "Check CP Gateway: docker ps | grep ibeam",
            },
        )
    except Exception as e:
        err_str = str(e)
        logger.error("IBKR sync failed: %s", e, exc_info=True)
        # Detect IBKR Web API session expiry and return a structured 401 with re-auth hint
        if "auth_failed" in err_str or "401" in err_str or "403" in err_str:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "session_expired",
                    "message": err_str,
                    "hint": "Your IBKR Web API session has expired. Open the CP Gateway URL in your browser to re-authenticate, then sync again. Alternatively, switch to the yfinance fallback in Settings → Security.",
                    "reauth_url": config_store.cfg("security.cp_gateway_url", "https://localhost:5000"),
                    "fallback_available": True,
                },
            )
        raise HTTPException(status_code=500, detail=err_str)



# ---------------------------------------------------------------------------
# Capability check (May 4 2026) — Web API + TWS Gateway availability
# ---------------------------------------------------------------------------
@router.get("/ibkr/capability")
async def get_capability_endpoint(refresh: bool = False):
    """Return current backend capability snapshot. Cached 60s; pass ?refresh=1 to bust."""
    from app.services.ibkr_web import capability as cap_mod
    from app.services import state as _state
    try:
        cap = cap_mod.get_capability(force_refresh=bool(refresh))
    except Exception as e:
        logger.error("capability check failed: %s", e)
        raise HTTPException(status_code=500, detail=f"capability_check_failed: {e}")
    settings = _state.get_dashboard_settings()
    active = _state.resolve_greeks_backend(settings, cap)
    return {
        **cap,
        "settings_value": settings.get("greeks_backend"),
        "active_backend": active,
        "fallback_backend": "bs_yfinance",
    }


@router.get("/ibkr/preview")
async def preview_sync():
    """Dry-run sync — fetch live positions and account data from IBKR without
    writing anything to disk. Returns a summary of what a real sync would produce.
    """
    from app.services.ibkr_web import capability as cap_mod
    from app.services import ibkr_sync_web

    try:
        settings = state.get_dashboard_settings()
        cap = cap_mod.get_capability()
        active = state.resolve_greeks_backend(settings, cap)

        if active != "web_api":
            return {
                "backend": active,
                "note": "Web API not active — preview uses yfinance data only.",
                "positions_count": len((state.get_active_positions() or {}).get("positions", [])),
                "net_liq": None,
            }

        pos_data = state.get_active_positions() or {}
        existing_positions = pos_data.get("positions", []) if isinstance(pos_data, dict) else []

        loop = asyncio.get_event_loop()
        synced = await loop.run_in_executor(
            None, ibkr_sync_web.sync_via_web_api, existing_positions, settings
        )

        # synced is a dict with positions list and account fields
        if isinstance(synced, dict):
            positions = synced.get("positions", [])
            net_liq = synced.get("net_liq")
            excess_liq = synced.get("excess_liquidity")
            avail_funds = synced.get("available_funds")
            daily_pnl = synced.get("daily_pnl")
            unrealized_pnl = synced.get("unrealized_pnl")
        else:
            positions = list(synced) if synced else []
            net_liq = excess_liq = avail_funds = daily_pnl = unrealized_pnl = None

        # Summarise by strategy without saving
        # aggregate_positions_by_ticker expects the full positions dict, not a bare list
        from app.services.state import aggregate_positions_by_ticker
        aggregated = aggregate_positions_by_ticker({"positions": positions})

        return {
            "backend": "web_api",
            "dry_run": True,
            "positions_count": len(positions),
            "aggregated_count": len(aggregated),
            "net_liq": net_liq,
            "excess_liquidity": excess_liq,
            "available_funds": avail_funds,
            "daily_pnl": daily_pnl,
            "unrealized_pnl": unrealized_pnl,
            "positions_preview": [
                {
                    "ticker": p.get("ticker"),
                    "strategy": p.get("strategy"),
                    "qty": p.get("qty"),
                    "expiry": p.get("expiry"),
                    "strike": p.get("strike") or p.get("short_strike"),
                    "right": p.get("right"),
                    "current_delta": p.get("current_delta"),
                    "market_value": p.get("market_value"),
                }
                for p in positions[:30]  # cap at 30 rows for display
            ],
        }

    except Exception as e:
        err_str = str(e)
        logger.error("IBKR preview failed: %s", e, exc_info=True)
        if "auth_failed" in err_str or "401" in err_str:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "session_expired",
                    "message": err_str,
                    "hint": "IBKR session expired. Re-authenticate in CP Gateway.",
                },
            )
        raise HTTPException(status_code=500, detail=err_str)
