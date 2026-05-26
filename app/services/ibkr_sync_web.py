"""
IBKR Web API sync — replaces the legacy TWS path.
Same output schema as ibkr_sync.py.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.ibkr_web import FIELD_TAGS, SNAPSHOT_FIELDS
from app.services.ibkr_web.client import WebApiClient, GatewayUnreachable, WebApiError
from app.services.ibkr_web import session as web_session
from app.services.opra import build_opra
from app.services.ibkr_web import portfolio as web_portfolio
from app.services.ibkr_web import snapshot as web_snapshot

logger = logging.getLogger("fortress.ibkr_sync_web")


def sync_via_web_api(existing_positions: list, settings: dict) -> dict:
    web_cfg = (settings.get("ibkr_web_api") or {})
    gateway_url = web_cfg.get("cp_gateway_url") or "https://localhost:5000"
    account_id = settings.get("ibkr_account_id")

    client = WebApiClient(
        gateway_url=gateway_url,
        verify_ssl=bool(web_cfg.get("verify_ssl", False)),
        request_timeout_s=int(web_cfg.get("request_timeout_s", 15)),
    )
    try:
        return _do_sync(client, account_id, existing_positions)
    finally:
        client.close()


def _do_sync(client, account_id, existing_positions):
    sess = web_session.session_summary(client)
    if not sess.get("established"):
        raise GatewayUnreachable(
            "Web API session not established: " + str(sess.get("error") or sess)
        )

    accounts = web_portfolio.list_accounts(client)
    resolved_account = account_id or (accounts[0].get("accountId") if accounts else None)
    if not resolved_account:
        raise WebApiError("No account available from /portfolio/accounts")
    # If account_id was a placeholder or empty, persist the discovered ID so future syncs work
    if not account_id or account_id in ("YOUR_IBKR_ACCOUNT_ID", ""):
        try:
            from app.services import state as _state
            _state.save_dashboard_settings({"ibkr_account_id": resolved_account})
            logger.info("Auto-saved discovered IBKR account ID: %s", resolved_account)
        except Exception as _e:
            logger.warning("Could not auto-save account ID: %s", _e)

    summary = web_portfolio.account_summary(client, resolved_account)

    def _f(key):
        return web_portfolio.extract_summary_field(summary, key)

    account_fields = {
        "net_liq":           _f("netliquidation"),
        "excess_liquidity":  _f("excessliquidity"),
        "available_funds":   _f("availablefunds"),
        "buying_power":      _f("buyingpower"),
        "daily_pnl":         _f("dailypnl"),
        "unrealized_pnl":    _f("unrealizedpnl"),
    }

    raw_positions = web_portfolio.all_positions(client, resolved_account)
    positions_data = [_map_position(p, existing_positions) for p in raw_positions]
    positions_data = [p for p in positions_data if (p.get("qty") or 0) != 0]

    net_liq = account_fields.get("net_liq")
    if net_liq and net_liq > 0:
        for rec in positions_data:
            mv = rec.get("market_value")
            if mv is not None:
                rec["net_liq_pct"] = round(abs(mv) / net_liq * 100, 2)

    # Snapshot Greeks
    option_legs = [p for p in positions_data if (p.get("sec_type") or "").upper() == "OPT"]
    conid_to_leg = {p["conid"]: p for p in option_legs if isinstance(p.get("conid"), int)}
    if conid_to_leg:
        try:
            rows = web_snapshot.snapshot(client, list(conid_to_leg.keys()))
            for r in rows:
                cid = r.get("conid")
                leg = conid_to_leg.get(cid)
                if not leg:
                    continue
                d = _safe_float(r.get(FIELD_TAGS["delta"]))
                leg["_ibkr_delta_raw"] = d
                if d is not None:
                    leg["current_delta"] = d
                    leg["current_delta_source"] = "web_api"
                gamma = _safe_float(r.get(FIELD_TAGS["gamma"]))
                theta = _safe_float(r.get(FIELD_TAGS["theta"]))
                vega  = _safe_float(r.get(FIELD_TAGS["vega"]))
                iv    = _safe_float_strip_pct(r.get(FIELD_TAGS["iv_strike"]))
                mark  = _safe_float(r.get(FIELD_TAGS["mark"]))
                if gamma is not None: leg["current_gamma"] = gamma
                if theta is not None: leg["current_theta"] = theta
                if vega  is not None: leg["current_vega"]  = vega
                if iv    is not None: leg["current_iv"]    = iv
                if mark  is not None: leg["current_mark"]  = mark
        except (GatewayUnreachable, WebApiError) as e:
            logger.warning("Web API snapshot failed: %s — relying on BS fallback", e)

    # BS fallback for any leg without a Web API delta
    try:
        from app.services import bs_fallback
        bs_summary = bs_fallback.fill_missing_deltas(positions_data)
        logger.info("bs_fallback after web_api: %s", bs_summary)
    except Exception as e:
        logger.warning("BS fallback failed: %s", e)

    spy_hedge_coverage = _compute_spy_hedge_coverage(positions_data, net_liq)

    # Sprint v8.7: persist to MySQL (non-blocking — failures don't abort sync)
    try:
        from app.services.db_v4 import upsert_positions, upsert_greeks
        n_pos = upsert_positions(positions_data, resolved_account)
        n_gk = upsert_greeks(positions_data, resolved_account)
        logger.info("MySQL write: %d positions, %d greeks rows", n_pos, n_gk)
    except Exception as _mysql_err:
        logger.warning("MySQL write step failed (sync still OK): %s", _mysql_err)

    now = datetime.now(timezone.utc).isoformat()
    return {
        **account_fields,
        "_last_updated": now,
        "ibkr_last_sync": now,
        "spy_hedge_coverage": spy_hedge_coverage,
        "positions": positions_data,
    }


def _safe_float(v):
    if v in (None, "", "N/A"):
        return None
    try:
        f = float(v)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_float_strip_pct(v):
    """IBKR sometimes returns IV as a string with % suffix, e.g. '29.2%'."""
    if v is None:
        return None
    if isinstance(v, str) and v.endswith("%"):
        v = v[:-1]
    return _safe_float(v)


def _map_position(p, existing):
    """Map IBKR /portfolio/.../positions row to our schema.

    IBKR Web API field names (verified May 5, 2026):
      ticker, conid, contractDesc, position, avgCost, mktValue,
      expiry (YYYYMMDD), strike (string), putOrCall (C/P),
      multiplier, currency, assetClass (OPT/STK/...)
    """
    asset = (p.get("assetClass") or "").upper()
    sec_type = "OPT" if asset == "OPT" else ("STK" if asset == "STK" else asset)
    conid = p.get("conid")
    ticker = (p.get("ticker") or p.get("undSym") or "").upper()
    if not ticker:
        cd = (p.get("contractDesc") or "").split()
        ticker = (cd[0] if cd else "").upper()

    strike = _safe_float(p.get("strike"))
    expiry = p.get("expiry")
    if expiry and len(expiry) == 8:
        expiry = expiry[:4] + "-" + expiry[4:6] + "-" + expiry[6:8]
    right = (p.get("putOrCall") or p.get("right") or "").upper() or None
    qty = _safe_float(p.get("position"))
    avg_cost = _safe_float(p.get("avgCost"))
    market_value = _safe_float(p.get("mktValue"))
    multiplier = str(p.get("multiplier") or "100")
    if multiplier.endswith(".0"):
        multiplier = multiplier[:-2]

    matched = _find_existing_match(existing, conid, ticker, expiry, strike, right)
    notes = matched.get("notes") if matched else ""
    strategy = matched.get("strategy") if matched else None
    alert_state = matched.get("alert_state") if matched else None

    # Determine leg direction from qty sign so downstream code never has to
    # guess from field names.  qty < 0 → short (sold), qty > 0 → long (bought).
    leg_direction = None
    if qty is not None:
        leg_direction = "short" if qty < 0 else "long"

    return {
        "ticker": ticker,
        "sec_type": sec_type,
        "currency": p.get("currency") or "USD",
        "qty": qty,
        "avg_cost": avg_cost,
        "expiry": expiry,
        # Canonical strike — same value regardless of leg direction.
        # 'short_strike' kept as alias for backward compat with downstream code
        # that has not yet been migrated to use 'strike'.
        "strike": strike,
        "short_strike": strike,
        "long_strike": None,
        "leg_direction": leg_direction,
        "right": right,
        "multiplier": multiplier,
        "local_symbol": p.get("contractDesc"),
        "conid": conid,
        "current_delta": None,
        "current_delta_source": None,
        "_ibkr_delta_raw": None,
        "delta_state": None,
        "alert_state": alert_state or "ok",
        "net_liq_pct": None,
        "dp_floor": None,
        "strategy": strategy,
        "notes": notes,
        "_ibkr_synced": True,
        "opra_symbol": build_opra(ticker, expiry, right, strike) if sec_type == "OPT" else None,
        "_ibkr_sync_time": datetime.now(timezone.utc).isoformat(),
        "market_value": market_value,
    }


def _find_existing_match(existing, conid, ticker, expiry, strike, right):
    for ex in existing or []:
        if conid and ex.get("conid") == conid:
            return ex
        if (
            ex.get("ticker") == ticker
            and ex.get("expiry") == expiry
            and (ex.get("short_strike") == strike or ex.get("long_strike") == strike)
            and ex.get("right") == right
        ):
            return ex
    return None


def _compute_spy_hedge_coverage(positions, net_liq):
    target_min, target_max = 20000, 30000
    spy_legs = [p for p in positions if (p.get("strategy") or "").upper() == "SPY_HEDGE"]
    hedge_mv = sum(p.get("market_value") or 0 for p in spy_legs)
    return {
        "hedge_market_value": round(hedge_mv, 2),
        "hedge_net_market_value": round(hedge_mv, 2),
        "hedge_pct_of_netliq": round(hedge_mv / net_liq * 100, 2) if net_liq else None,
        "target_min": target_min,
        "target_max": target_max,
        "coverage_ok": target_min <= hedge_mv <= target_max,
        "legs_count": len(spy_legs),
    }
