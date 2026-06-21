"""
ibkr_marketdata.py — thin IBKR CP Gateway market-data helpers (Phases 1-3)
===========================================================================
Place at:  ~/fortress-v4-api/app/services/ibkr_marketdata.py

Built on the existing ibkr_chain.py plumbing (conid resolution + snapshot).
Every function returns None on ANY failure — callers fall back to yfinance
silently (same contract as ibkr_chain.get_ibkr_chain).

Consumers:
  - chain.get_spot()                 → ibkr_spot()         (Phase 1)
  - options_analytics check_liquidity → ibkr_quotes()      (Phase 2)
  - options_analytics get_iv_rank     → ibkr_atm_iv()      (Phase 3)
  - options_analytics get_vol_skew    → ibkr_quotes()      (Phase 3/4)

Field codes (CP Gateway /iserver/marketdata/snapshot):
  31 = last price · 84 = bid · 86 = ask · 7633 = option implied vol (strike)
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

logger = logging.getLogger("fortress.ibkr_marketdata")

# ── Module-level caches ───────────────────────────────────────────────────────
_SPOT_CACHE: dict = {}      # ticker → (ts, price)
_SPOT_TTL_S = 45            # live enough for trigger evaluation, kind to gateway

_QUOTES_CACHE: dict = {}    # (ticker, expiry, n) → (ts, quotes)
_QUOTES_TTL_S = 60


def _parse_price(v) -> Optional[float]:
    """
    CP snapshot price fields are strings and may carry prefixes:
    'C123.45' = prior close, 'H123.45' = halted. Strip and parse.
    """
    if v is None:
        return None
    try:
        s = re.sub(r"^[A-Za-z*]+", "", str(v)).replace(",", "")
        p = float(s)
        return p if p > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_trade_time(v) -> Optional[str]:
    """CP /iserver/account/trades `trade_time` arrives as 'YYYYMMDD-HH:MM:SS'
    (UTC). Normalize to ISO-8601 UTC. `trade_time_r` (epoch ms) is used as a
    fallback. Returns None if unparseable."""
    import datetime as _dt
    if v in (None, "", 0):
        return None
    s = str(v).strip()
    # Epoch milliseconds?
    if s.isdigit() and len(s) >= 12:
        try:
            return _dt.datetime.fromtimestamp(int(s) / 1000, _dt.timezone.utc).isoformat()
        except Exception:
            return None
    # 'YYYYMMDD-HH:MM:SS'
    try:
        d = _dt.datetime.strptime(s, "%Y%m%d-%H:%M:%S").replace(tzinfo=_dt.timezone.utc)
        return d.isoformat()
    except Exception:
        pass
    try:  # already ISO-ish
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).isoformat()
    except Exception:
        return None


# ── Sprint 16 keystone: recent executions (fills) reader ──────────────────────
# Self-contained GET against the CP Gateway (iBeam) /iserver/account/trades
# endpoint, which returns up to the last 7 days of executions. We hit the gateway
# directly (config strategy: cp_gateway_url) rather than the out-of-mount
# ibkr_web client, so this stays inspectable and dependency-free. Same failure
# contract as the rest of this module: returns None on ANY failure → callers
# degrade gracefully (pacing falls back to journal-only, entry-capture skips).

_FILLS_CACHE: dict = {}      # 'all' → (ts, fills)
_FILLS_TTL_S = 120


def _norm_side(v) -> Optional[str]:
    """Normalize IBKR side to 'BUY'|'SELL'. Accepts B/S, BOT/SLD, BUY/SELL."""
    if v is None:
        return None
    s = str(v).strip().upper()
    if s in ("B", "BOT", "BUY"):
        return "BUY"
    if s in ("S", "SLD", "SELL"):
        return "SELL"
    return None


def _parse_opt_from_desc(desc: str) -> dict:
    """Best-effort parse of strike/expiry/right from an IBKR option description
    like 'MSFT JAN16'26 490 CALL' or 'MSFT 26JAN26 490 C'. Returns {} if it
    can't — callers must tolerate missing fields."""
    out: dict = {}
    if not desc:
        return out
    s = str(desc).upper()
    m = re.search(r"\b(\d{2,5}(?:\.\d+)?)\s*(C|P|CALL|PUT)\b", s)
    if m:
        try:
            out["strike"] = float(m.group(1))
        except ValueError:
            pass
        out["right"] = "C" if m.group(2).startswith("C") else "P"
    return out


def ibkr_recent_fills(days_back: int = 7) -> Optional[list]:
    """
    Recent executions from CP Gateway /iserver/account/trades (last ≤7 days).
    Returns a list of normalized fills, newest-first:
        {execution_id, time (ISO UTC), ticker, sec_type, side (BUY|SELL),
         qty (float), price (float), strike, right, expiry, conid,
         description, position_after, liquidation, raw}
    or None on any failure. 120s cache.
    """
    now = time.time()
    hit = _FILLS_CACHE.get("all")
    if hit and now - hit[0] < _FILLS_TTL_S:
        return hit[1]
    try:
        import requests
        try:
            from app.services.config_store import cfg
            base = cfg("security.cp_gateway_url") or cfg("strategy.cp_gateway_url") \
                or "https://localhost:5000"
            verify = bool(cfg("security.cp_gateway_verify_ssl", False))
            timeout = int(cfg("security.cp_gateway_timeout_s", 15) or 15)
        except Exception:
            base, verify, timeout = "https://localhost:5000", False, 15
        base = base.rstrip("/")
        url = f"{base}/v1/api/iserver/account/trades"
        if not verify:
            try:
                import urllib3
                urllib3.disable_warnings()
            except Exception:
                pass
        resp = requests.get(url, params={"days": str(days_back)},
                            verify=verify, timeout=timeout)
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            return None

        fills = []
        for r in rows:
            side = _norm_side(r.get("side"))
            qty = r.get("size") if r.get("size") is not None else r.get("qty")
            try:
                qty = abs(float(qty)) if qty is not None else None
            except (ValueError, TypeError):
                qty = None
            price = _parse_price(r.get("price"))
            t = _parse_trade_time(r.get("trade_time") or r.get("trade_time_r"))
            desc = (r.get("order_description") or r.get("contract_description_1")
                    or r.get("description") or "")
            sec = (r.get("sec_type") or r.get("secType") or "").upper()
            opt = _parse_opt_from_desc(desc) if sec in ("OPT", "FOP") else {}
            fills.append({
                "execution_id": r.get("execution_id") or r.get("exec_id"),
                "time": t,
                "ticker": (r.get("symbol") or r.get("ticker") or "").upper(),
                "sec_type": sec,
                "side": side,
                "qty": qty,
                "price": price,
                "strike": opt.get("strike"),
                "right": opt.get("right"),
                "expiry": r.get("expiry") or r.get("expiration"),
                "conid": r.get("conid") or r.get("conidex"),
                "description": desc,
                "position_after": r.get("position"),
                "liquidation": bool(r.get("liquidation_trade")) if r.get("liquidation_trade") is not None else None,
                "raw": r,
            })
        # newest-first by time (None times sink to the bottom)
        fills.sort(key=lambda f: f["time"] or "", reverse=True)
        _FILLS_CACHE["all"] = (now, fills)
        return fills
    except Exception as e:
        logger.debug("ibkr_recent_fills failed: %s", e)
        return None


def _parse_iv_pct(v) -> Optional[float]:
    """
    IV fields (7633 / 7283) arrive as '23.4%', 23.4, or decimal 0.234.
    Normalize to percent in the sane band 1-500, else None.
    """
    if v in (None, "", "N/A"):
        return None
    try:
        x = float(str(v).replace("%", "").strip())
    except (ValueError, TypeError):
        return None
    if x <= 0:
        return None
    pct = round(x if x > 1 else x * 100, 3)
    return pct if 1.0 <= pct <= 500.0 else None


def _client():
    from app.services.ibkr_web import make_client
    return make_client()


# ── Phase 1: live spot ────────────────────────────────────────────────────────

def ibkr_spot(ticker: str) -> Optional[float]:
    """
    Live underlying spot via CP Gateway snapshot (field 31).
    45s cache. Returns None on any failure → caller falls back to yfinance.
    """
    ticker = ticker.upper()
    now = time.time()
    hit = _SPOT_CACHE.get(ticker)
    if hit and now - hit[0] < _SPOT_TTL_S:
        return hit[1]

    try:
        from app.services.ibkr_chain import _get_underlying_conid
        from app.services.ibkr_web import snapshot as snap_mod
        client = _client()
        conid = _get_underlying_conid(client, ticker)
        if not conid:
            return None
        rows = snap_mod.snapshot(client, [conid], fields=["31", "84", "86"])
        for row in rows:
            if int(row.get("conid", 0) or 0) != int(conid):
                continue
            last = _parse_price(row.get("31"))
            if last:
                _SPOT_CACHE[ticker] = (now, last)
                return last
            # last missing → try bid/ask mid
            bid, ask = _parse_price(row.get("84")), _parse_price(row.get("86"))
            if bid and ask:
                mid = (bid + ask) / 2
                _SPOT_CACHE[ticker] = (now, mid)
                return mid
        return None
    except Exception as e:
        logger.debug("ibkr_spot(%s) failed: %s", ticker, e)
        return None


# ── Phases 2-3: option quotes near spot, both rights ─────────────────────────

def ibkr_quotes(
    ticker: str,
    spot: float,
    expiry_iso: str,
    n_strikes: int = 12,
) -> Optional[dict]:
    """
    Live bid/ask/IV for the n_strikes strikes nearest spot, BOTH rights,
    for one expiry (YYYY-MM-DD — weeklies resolve too; if IBKR can't
    resolve the date, returns None and caller falls back).

    Returns {"quotes": {(strike, "call"|"put"): {bid, ask, mid, iv_pct}},
             "n_live": int} or None. iv_pct is in percent (26.5 = 26.5%)
    or None when the gateway didn't return 7633 for that contract.
    """
    ticker = ticker.upper()
    key = (ticker, expiry_iso, n_strikes)
    now = time.time()
    hit = _QUOTES_CACHE.get(key)
    if hit and now - hit[0] < _QUOTES_TTL_S:
        return hit[1]

    try:
        from app.services.ibkr_chain import (
            _get_underlying_conid, _get_strikes, _get_opt_conid,
            _snapshot_contracts,
        )
        client = _client()
        conid = _get_underlying_conid(client, ticker)
        if not conid:
            return None

        month = expiry_iso[:7].replace("-", "")          # YYYYMM
        expiry_ibkr = expiry_iso.replace("-", "")        # YYYYMMDD

        strikes = _get_strikes(client, conid, month, "C") or \
                  _get_strikes(client, conid, month, "P")
        if not strikes:
            return None
        nearest = sorted(strikes, key=lambda s: abs(s - spot))[:n_strikes]

        conid_map: dict = {}   # opt_conid → (strike, right)
        for s in nearest:
            for right_up, right in (("C", "call"), ("P", "put")):
                oc = _get_opt_conid(client, conid, expiry_ibkr, s, right_up)
                if oc:
                    conid_map[oc] = (s, right)

        if not conid_map:
            return None

        from app.services.ibkr_web import snapshot as snap_mod
        conids = list(conid_map.keys())
        # Request BOTH IV fields: 7633 (mark IV) is often slow/absent on
        # freshly-primed contracts; 7283 (option implied vol) frequently
        # arrives when 7633 doesn't. Note snapshot()'s internal backoff
        # returns as soon as ANY field has data (bid/ask are first), so we
        # poll here until an IV field actually populates.
        fields = ["84", "86", "31", "7633", "7283"]

        def _snap_quotes() -> tuple[dict, int]:
            rows = snap_mod.snapshot(client, conids, fields=fields)
            quotes: dict = {}
            n_live = 0
            for row in rows or []:
                try:
                    cid = int(row.get("conid") or 0)
                except (ValueError, TypeError):
                    continue
                if cid not in conid_map:
                    continue
                s, right = conid_map[cid]
                bid = _parse_price(row.get("84"))
                ask = _parse_price(row.get("86"))
                mark = _parse_price(row.get("31"))
                iv_pct = _parse_iv_pct(row.get("7633")) or _parse_iv_pct(row.get("7283"))
                mid = (bid + ask) / 2 if bid and ask else mark
                if bid and ask:
                    n_live += 1
                quotes[(s, right)] = {
                    "bid": bid, "ask": ask, "mid": mid, "iv_pct": iv_pct,
                }
            return quotes, n_live

        quotes, n_live = _snap_quotes()
        for _ in range(2):   # up to ~2 extra polls for computed IV fields
            if not quotes or any(v["iv_pct"] for v in quotes.values()):
                break
            time.sleep(1.5)
            q2, n2 = _snap_quotes()
            if q2:
                quotes, n_live = q2, n2

        if not quotes:
            return None
        result = {"quotes": quotes, "n_live": n_live}
        _QUOTES_CACHE[key] = (now, result)
        return result
    except Exception as e:
        logger.debug("ibkr_quotes(%s %s) failed: %s", ticker, expiry_iso, e)
        return None


# ── Phase 3: ATM IV straddle ─────────────────────────────────────────────────

def ibkr_atm_iv(ticker: str, spot: float, expiry_iso: str) -> Optional[dict]:
    """
    ATM IV from IBKR field 7633 — median over the ~3 strikes nearest spot,
    per side. Returns {"iv": blended_pct, "call_iv": pct|None,
    "put_iv": pct|None} or None.
    """
    data = ibkr_quotes(ticker, spot, expiry_iso, n_strikes=5)
    if not data:
        return None

    def _median_side(right: str) -> Optional[float]:
        ivs = sorted(
            v["iv_pct"] for (s, r), v in data["quotes"].items()
            if r == right and v["iv_pct"]
        )
        return ivs[len(ivs) // 2] if ivs else None

    call_iv, put_iv = _median_side("call"), _median_side("put")
    ivs = [v for v in (call_iv, put_iv) if v]
    if not ivs:
        return None
    # Wild disagreement between sides → take the lower (staleness inflates)
    blended = min(ivs) if (len(ivs) == 2 and max(ivs) > 2.5 * min(ivs)) else sum(ivs) / len(ivs)
    return {"iv": blended, "call_iv": call_iv, "put_iv": put_iv}


# ── Specific-contract quote (ANY strike — bypasses the near-spot band) ────────

def ibkr_contract_quote(
    ticker: str,
    expiry_iso: str,
    strike: float,
    right: str,
) -> Optional[dict]:
    """
    Live bid/ask/last/IV for ONE specific option contract at any strike — not
    limited to the near-spot band of ibkr_quotes(). This is what lets the
    backend price a far-OTM hedge/close leg directly.

    right: 'C'|'P' or 'call'|'put'. expiry_iso: 'YYYY-MM-DD' (weeklies resolve).
    Returns {bid, ask, mid, last, iv_pct} or None on any failure → caller falls
    back to yfinance.
    """
    ticker = ticker.upper()
    right_up = "C" if str(right).upper().startswith("C") else "P"
    try:
        from app.services.ibkr_chain import _get_underlying_conid, _get_opt_conid
        from app.services.ibkr_web import snapshot as snap_mod
        client = _client()
        conid = _get_underlying_conid(client, ticker)
        if not conid:
            return None
        expiry_ibkr = expiry_iso.replace("-", "")          # YYYYMMDD
        oc = _get_opt_conid(client, conid, expiry_ibkr, float(strike), right_up)
        if not oc:
            return None
        fields = ["84", "86", "31", "7633", "7283"]

        def _snap():
            for row in snap_mod.snapshot(client, [oc], fields=fields) or []:
                try:
                    if int(row.get("conid") or 0) != int(oc):
                        continue
                except (ValueError, TypeError):
                    continue
                bid = _parse_price(row.get("84"))
                ask = _parse_price(row.get("86"))
                last = _parse_price(row.get("31"))
                iv_pct = _parse_iv_pct(row.get("7633")) or _parse_iv_pct(row.get("7283"))
                mid = (bid + ask) / 2 if (bid and ask) else last
                if bid or ask or last:
                    return {"bid": bid, "ask": ask, "mid": mid, "last": last, "iv_pct": iv_pct}
            return None

        # IV fields (7633/7283) are often slow on a fresh single-contract snapshot;
        # re-poll up to 2x (same pattern as ibkr_quotes) so iv_pct populates.
        q = _snap()
        for _ in range(2):
            if not q or q.get("iv_pct"):
                break
            time.sleep(1.5)
            q2 = _snap()
            if q2:
                q = q2
        return q
    except Exception as e:
        logger.debug("ibkr_contract_quote(%s %s %s%s) failed: %s",
                     ticker, expiry_iso, strike, right_up, e)
        return None
