"""
IBKR option chain via CP Gateway — roll candidates engine.

Fetches live bid/ask/IV directly from IBKR instead of yfinance.
Falls back silently to yfinance on any error (gateway offline, auth failure, etc.).

Chain:
  1. POST /iserver/secdef/search           → underlying conid (cached 1h)
  2. GET  /iserver/secdef/strikes          → strike list per month (cached 5min)
  3. GET  /iserver/secdef/info (per strike) → option conid (cached 5min)
  4. snapshot()                            → live bid/ask/IV (NOT cached — always live)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("fortress.ibkr_chain")

# ── Module-level caches ────────────────────────────────────────────────────────
_CONID_CACHE:    dict = {}   # ticker → (ts, conid)
_STRIKES_CACHE:  dict = {}   # (conid, month) → (ts, {"call": [...], "put": [...]})
_OPTCONID_CACHE: dict = {}   # (conid, month, strike, right) → (ts, opt_conid)

_TTL_CONID   = 3600   # 1h — underlying conids rarely change
_TTL_STRIKES = 300    # 5min
_TTL_OPTCONID = 300   # 5min


def _cache_get(cache, key, ttl):
    entry = cache.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None


def _cache_set(cache, key, val):
    cache[key] = (time.time(), val)


# ── Step 1: underlying conid ───────────────────────────────────────────────────

def _get_underlying_conid(client, ticker: str) -> Optional[int]:
    key = ticker.upper()
    cached = _cache_get(_CONID_CACHE, key, _TTL_CONID)
    if cached:
        return cached

    try:
        results = client.post("/iserver/secdef/search", json={
            "symbol": ticker.upper(),
            "name": False,
            "secType": "STK",
        })
        logger.info("[ibkr_chain] secdef/search result for %s: %s", ticker, str(results)[:200])
        if not results or not isinstance(results, list):
            return None
        # Pick first STK result on a major exchange
        for r in results:
            # secType may be top-level or nested inside 'sections'
            sections = r.get("sections") or []
            has_stk = (r.get("secType") == "STK" or
                       any(s.get("secType") == "STK" for s in sections))
            if has_stk:
                conid = r.get("conid")
                if conid:
                    _cache_set(_CONID_CACHE, key, int(conid))
                    logger.debug("Resolved %s → conid %s", ticker, conid)
                    return int(conid)
    except Exception as e:
        logger.warning("conid lookup failed for %s: %s", ticker, e)
    return None


# ── Step 2: strikes for a month ────────────────────────────────────────────────

def _get_strikes(client, conid: int, month: str, right: str) -> list[float]:
    """month: 'MMMYY' e.g. 'JUN26'. right: 'C' or 'P'."""
    key = (conid, month)
    cached = _cache_get(_STRIKES_CACHE, key, _TTL_STRIKES)
    if cached is not None:
        return cached.get("call" if right == "C" else "put", [])

    try:
        data = client.get("/iserver/secdef/strikes", params={
            "conid": str(conid),
            "sectype": "OPT",
            "month": month,
            "exchange": "SMART",
        })
        logger.info("[ibkr_chain] secdef/strikes conid=%s month=%s → %s", conid, month, str(data)[:200])
        if isinstance(data, dict):
            _cache_set(_STRIKES_CACHE, key, data)
            return data.get("call" if right == "C" else "put", [])
    except Exception as e:
        logger.warning("strikes fetch failed conid=%s month=%s: %s", conid, month, e)
    return []


# ── Step 3: option conid for a specific contract ───────────────────────────────

def _get_opt_conid(client, conid: int, expiry: str, strike: float, right: str) -> Optional[int]:
    """expiry: 'YYYYMMDD'. Returns option conid."""
    key = (conid, expiry, strike, right)
    cached = _cache_get(_OPTCONID_CACHE, key, _TTL_OPTCONID)
    if cached:
        return cached

    try:
        # month must be MMMYY format (e.g. JUN26)
        from datetime import datetime as _dt2
        month_str = _dt2.strptime(expiry[:8], "%Y%m%d").strftime("%b%y").upper()
        results = client.get("/iserver/secdef/info", params={
            "conid": str(conid),
            "sectype": "OPT",
            "month": month_str,
            "expiry": expiry,
            "strike": str(strike),
            "right": right,
        })
        if isinstance(results, list) and results:
            opt_conid = results[0].get("conid")
            if opt_conid:
                _cache_set(_OPTCONID_CACHE, key, int(opt_conid))
                return int(opt_conid)
    except Exception as e:
        logger.info("[ibkr_chain] opt conid lookup failed conid=%s expiry=%s strike=%s right=%s: %s", conid, expiry, strike, right, e)
    return None


# ── Step 4: snapshot bid/ask/IV ────────────────────────────────────────────────

def _snapshot_contracts(client, opt_conids: list[int]) -> dict[int, dict]:
    """Returns {opt_conid: {bid, ask, mid, iv}} for each conid."""
    if not opt_conids:
        return {}
    try:
        from app.services.ibkr_web import snapshot as snap_mod
        fields = ["84", "86", "7633", "31"]   # bid, ask, iv_strike, mark
        rows = snap_mod.snapshot(client, opt_conids, fields=fields)
        result = {}
        for row in rows:
            cid = row.get("conid")
            if not cid:
                continue
            bid  = _safe_float(row.get("84"))
            ask  = _safe_float(row.get("86"))
            iv   = _safe_float(row.get("7633"))
            mark = _safe_float(row.get("31"))
            mid  = (bid + ask) / 2 if bid and ask and bid > 0 and ask > 0 else (mark or None)
            result[int(cid)] = {"bid": bid, "ask": ask, "mid": mid, "iv_raw": iv}
        return result
    except Exception as e:
        logger.warning("snapshot failed: %s", e)
        return {}


def _safe_float(v) -> Optional[float]:
    try:
        x = float(str(v).replace(",", ""))
        return x if x == x else None  # NaN guard
    except (TypeError, ValueError):
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def get_ibkr_chain(
    ticker: str,
    right: str = "C",
    spot: float = 0,
    target_dte: int = 45,
    max_expiries: int = 3,
) -> Optional[dict]:
    """
    Fetch live option chain from IBKR CP Gateway.

    Returns a dict compatible with chain.get_chain():
        {"ticker": ..., "spot": ..., "expirations": {date_str: {"calls": [...], "puts": [...]}}}

    Returns None if IBKR is unavailable.
    """
    try:
        from app.services.ibkr_web import make_client
        from app.services import chain as chain_svc
        client = make_client()
    except Exception as e:
        logger.warning("Could not create IBKR client: %s", e)
        return None

    try:
        # Resolve underlying conid
        logger.info("[ibkr_chain] Resolving conid for %s", ticker)
        conid = _get_underlying_conid(client, ticker)
        if not conid:
            logger.warning("[ibkr_chain] Could not resolve conid for %s — secdef/search returned nothing", ticker)
            return None
        logger.info("[ibkr_chain] conid=%s for %s", conid, ticker)

        # Determine target months
        today = datetime.now(timezone.utc)
        months = []
        for delta_months in range(0, max_expiries + 2):
            m = today + timedelta(days=delta_months * 30)
            months.append(m.strftime("%Y%m"))
        months = list(dict.fromkeys(months))[:max_expiries + 1]

        # Get strikes + filter to OTM near target
        right_up = right.upper()
        out_expirations: dict = {}

        for month in months:
            all_strikes = _get_strikes(client, conid, month, right_up)
            if not all_strikes:
                continue

            # Filter: OTM only, within ±20% of spot, pick ~8 nearest
            if right_up == "C":
                otm = [s for s in all_strikes if s > spot * 0.98]
            else:
                otm = [s for s in all_strikes if s < spot * 1.02]

            if not otm:
                continue

            # Take up to 20 OTM strikes — enough to cover current_strike when rolling up
            otm_sorted = sorted(otm) if right_up == "C" else sorted(otm, reverse=True)
            target_strikes = otm_sorted[:20]

            # Convert month YYYYMM to expiry candidates: 3rd Friday
            year, mon = int(month[:4]), int(month[4:])
            from calendar import monthcalendar
            cal = monthcalendar(year, mon)
            fridays = [week[4] for week in cal if week[4] > 0]
            if len(fridays) < 3:
                continue
            third_fri = fridays[2]
            expiry_dt = datetime(year, mon, third_fri, tzinfo=timezone.utc)
            dte = (expiry_dt.date() - today.date()).days
            if dte < 14 or dte > target_dte + 60:
                continue
            expiry_str = expiry_dt.strftime("%Y-%m-%d")
            expiry_ibkr = expiry_dt.strftime("%Y%m%d")

            # Resolve option conids for these strikes
            strike_to_conid: dict[float, int] = {}
            for s in target_strikes:
                oc = _get_opt_conid(client, conid, expiry_ibkr, s, right_up)
                if oc:
                    strike_to_conid[s] = oc

            if not strike_to_conid:
                logger.info("[ibkr_chain] no opt conids resolved for %s %s %s — skipping", ticker, expiry_str, right_up)
                continue

            # Snapshot live data
            live = _snapshot_contracts(client, list(strike_to_conid.values()))

            # Build rows
            rows = []
            for s, oc in strike_to_conid.items():
                snap = live.get(oc, {})
                bid    = snap.get("bid")
                ask    = snap.get("ask")
                iv_raw = snap.get("iv_raw")
                iv     = (iv_raw / 100.0) if iv_raw and iv_raw > 1 else (iv_raw or 0)
                mid    = snap.get("mid")

                # After-hours / closed market: quotes are zero — fall back to BS estimate
                if not mid or mid <= 0:
                    try:
                        from app.services.bs_fallback import _bs_d1d2, _norm_cdf, _RISK_FREE
                        import math as _math
                        _iv = iv if iv > 0.01 else 0.30
                        _t  = max(dte, 1) / 365.0
                        d1, d2 = _bs_d1d2(spot, s, _t, _iv, _RISK_FREE)
                        if d1 is not None:
                            disc = _math.exp(-_RISK_FREE * _t)
                            if right_up == "C":
                                mid = spot * _norm_cdf(d1) - s * disc * _norm_cdf(d2)
                            else:
                                mid = s * disc * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
                            mid = max(round(mid, 4), 0.01)
                    except Exception:
                        pass

                rows.append({
                    "strike":         s,
                    "bid":            bid or 0,
                    "ask":            ask or 0,
                    "mid":            mid,
                    "iv":             iv or 0,
                    "open_interest":  100,   # placeholder — OI not in snapshot
                    "volume":         0,
                    "source":         "ibkr_live" if (bid and bid > 0) else "ibkr_bs_fallback",
                })

            logger.info("[ibkr_chain] %s %s %s: %d rows built, sample mid=%s iv=%s",
                    ticker, expiry_str, right_up,
                    len(rows),
                    rows[0].get("mid") if rows else None,
                    rows[0].get("iv") if rows else None)
        if rows:
                key = "calls" if right_up == "C" else "puts"
                out_expirations[expiry_str] = {key: rows}

        if not out_expirations:
            return None

        logger.info("IBKR chain fetched for %s: %d expiries", ticker, len(out_expirations))
        return {
            "ticker":      ticker.upper(),
            "spot":        spot,
            "source":      "ibkr_live",
            "expirations": out_expirations,
        }

    except Exception as e:
        logger.warning("[ibkr_chain] Chain fetch FAILED for %s: %s", ticker, e, exc_info=True)
        return None
    finally:
        try:
            client.close()
        except Exception:
            pass
