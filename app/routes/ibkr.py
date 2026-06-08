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
    Check IBKR connection status. Supports both ibeam and OAuth auth modes.
    """
    try:
        from app.services import config_store
        from app.services.ibkr_web import get_session_status, make_client
        from app.services.ibkr_web import portfolio as web_portfolio

        cfg = config_store.cfg
        mode = cfg("security.ibkr_auth_mode") or "ibeam"
        summary = get_session_status(cfg)

        account = None
        if summary.get("authenticated") and summary.get("established"):
            try:
                client = make_client(cfg)
                accounts = web_portfolio.list_accounts(client)
                account = accounts[0].get("accountId") if accounts else None
                client.close()
            except Exception:
                pass

        return {
            "host": cfg("security.cp_gateway_url") if mode == "ibeam" else "https://api.ibkr.com",
            "auth_mode": mode,
            "reachable": summary.get("reachable", False),
            "connected": summary.get("connected", False),
            "authenticated": summary.get("authenticated", False),
            "established": summary.get("established", False),
            "competing": summary.get("competing", False),
            "account": account,
            "backend": "web_api",
            "error": summary.get("error"),
        }
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
        # --- Sprint v8.9: record sync attempt in Redis for retry ---
        import time as _t
        _store_sync_result({
            "status": "ok",
            "backend": chosen,
            "synced_at": synced.get("ibkr_last_sync") or synced.get("_last_updated"),
            "is_retry": False,
            "recorded_at": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
        })
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
        # --- Sprint v8.9: record failure in Redis for retry ---
        import time as _t2
        _store_sync_result({
            "status": "error",
            "error": err_str[:500],
            "backend": chosen if 'chosen' in dir() else None,
            "is_retry": False,
            "recorded_at": _t2.strftime("%Y-%m-%dT%H:%M:%SZ", _t2.gmtime()),
        })
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


# ---------------------------------------------------------------------------
# Sprint v8.9 — IBKR Upload Retry (K-03)
# ---------------------------------------------------------------------------

import json as _json
import os as _os
import time as _time

_REDIS_URL = _os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_REDIS_KEY = "fortress:ibkr:last_sync_attempt"
_REDIS_TTL = 86400  # 24 hours


def _get_redis():
    import redis as _redis
    return _redis.Redis.from_url(_REDIS_URL, decode_responses=True)


def _store_sync_result(result: dict):
    """Persist last sync attempt to Redis (best-effort; never raises)."""
    try:
        r = _get_redis()
        r.set(_REDIS_KEY, _json.dumps(result), ex=_REDIS_TTL)
    except Exception as _e:
        logger.warning("Redis store failed (non-fatal): %s", _e)


def _load_sync_result() -> dict | None:
    """Read last sync attempt from Redis. Returns None if missing or Redis down."""
    try:
        r = _get_redis()
        raw = r.get(_REDIS_KEY)
        return _json.loads(raw) if raw else None
    except Exception as _e:
        logger.warning("Redis read failed: %s", _e)
        return None


@router.get("/ibkr/last-sync")
async def get_last_sync():
    """Return metadata about the most recent sync attempt (from Redis)."""
    record = _load_sync_result()
    if not record:
        return {"status": "no_record", "message": "No sync attempt recorded yet."}
    return record


@router.post("/ibkr/upload/retry")
async def retry_last_upload():
    """
    Re-trigger the last IBKR sync attempt (K-03 fix).

    Reads the last sync context from Redis (backend, settings snapshot) and
    re-runs the same sync pipeline. Returns the new result alongside the
    previous attempt's outcome so the caller can compare.

    If no prior attempt is found, falls back to a fresh sync using current settings.
    """
    prior = _load_sync_result()
    prior_status = prior.get("status") if prior else None
    prior_backend = prior.get("backend") if prior else None

    logger.info(
        "Retry requested — prior attempt: status=%s backend=%s",
        prior_status, prior_backend
    )

    # Re-use the same backend as the last attempt when known; otherwise auto-resolve
    retry_backend = prior_backend if prior_backend in ("web_api", "bs_yfinance") else None

    from app.services.ibkr_web import capability as cap_mod

    try:
        existing_data = state.get_active_positions()
        existing_positions = (
            existing_data.get("positions", []) if isinstance(existing_data, dict) else []
        )
        settings = state.get_dashboard_settings()
        ibkr_enabled = config_store.cfg("security.use_ibkr_web_api", True)

        if not ibkr_enabled:
            chosen = "bs_yfinance"
        elif retry_backend:
            chosen = retry_backend
        else:
            cap = cap_mod.get_capability()
            chosen = state.resolve_greeks_backend(settings, cap)

        started_at = _time.time()

        if chosen == "web_api":
            from app.services import ibkr_sync_web
            synced = await asyncio.get_event_loop().run_in_executor(
                None, ibkr_sync_web.sync_via_web_api, existing_positions, settings
            )
        else:
            from app.services import ibkr_sync_synthetic
            synced = await asyncio.get_event_loop().run_in_executor(
                None, ibkr_sync_synthetic.sync_synthetic, existing_positions, settings
            )

        positions = synced.pop("positions", [])
        synced["greeks_backend_used"] = chosen
        new_data = {**synced, "positions": positions}
        state.save_positions(new_data)
        cap_mod.invalidate()

        elapsed = round(_time.time() - started_at, 2)

        result_record = {
            "status": "ok",
            "backend": chosen,
            "positions_count": len(positions),
            "synced_at": synced.get("ibkr_last_sync") or synced.get("_last_updated"),
            "elapsed_s": elapsed,
            "is_retry": True,
            "recorded_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        }
        _store_sync_result(result_record)

        return {
            **result_record,
            "prior_attempt": {
                "status": prior_status,
                "backend": prior_backend,
                "recorded_at": prior.get("recorded_at") if prior else None,
                "error": prior.get("error") if prior else None,
            },
        }

    except Exception as e:
        err_str = str(e)
        logger.error("IBKR retry sync failed: %s", e, exc_info=True)

        fail_record = {
            "status": "error",
            "error": err_str,
            "backend": retry_backend,
            "is_retry": True,
            "recorded_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        }
        _store_sync_result(fail_record)

        if "auth_failed" in err_str or "401" in err_str or "403" in err_str:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "session_expired",
                    "message": err_str,
                    "hint": "IBKR session expired. Re-authenticate in CP Gateway then retry.",
                    "reauth_url": config_store.cfg(
                        "security.cp_gateway_url", "https://localhost:5000"
                    ),
                },
            )
        raise HTTPException(status_code=500, detail=err_str)

@router.post("/ibkr/gateway/{action}")
async def gateway_control(action: str):
    """
    Control the cp-gateway Docker container.
    action: start | stop | restart
    """
    if action not in ("start", "stop", "restart"):
        raise HTTPException(status_code=400, detail=f"Invalid action '{action}'. Use start, stop, or restart.")
    import subprocess
    try:
        result = subprocess.run(
            ["docker", action, "cp-gateway"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or f"docker {action} failed")
        logger.info("Gateway %s: %s", action, result.stdout.strip())
        return {"action": action, "status": "ok", "output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"docker {action} timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="docker not found in PATH")


# ── Reconnect ─────────────────────────────────────────────────────────────────

import subprocess as _subprocess

@router.post("/ibkr/reconnect")
async def reconnect_gateway():
    """
    Restart cp-gateway (iBeam) and wait up to 60s for re-authentication.
    Frontend polls /api/ibkr/capability independently — this just fires the restart.
    """
    try:
        _subprocess.run(
            ["docker", "restart", "cp-gateway"],
            check=True, capture_output=True, timeout=15
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"docker restart failed: {e}")

    # Poll until iBeam authenticates or timeout
    from app.services.ibkr_web import get_session_status
    from app.services import config_store
    cfg = config_store.cfg
    for _ in range(20):          # 20 × 3s = 60s
        await asyncio.sleep(3)
        try:
            status = get_session_status(cfg)
            if status.get("authenticated"):
                return {"ok": True, "message": "iBeam authenticated"}
        except Exception:
            pass
    return {"ok": False, "message": "Timed out waiting for iBeam — frontend will keep polling"}
