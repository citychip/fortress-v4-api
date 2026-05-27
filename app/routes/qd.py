"""
qd.py — QuantData proxy routes for Fortress V4 API
Reads tool IDs dynamically from the QD config file (no hardcoding).
Re-discovers IDs automatically when config changes (TTL: 60s).

All routes require Bearer auth (same middleware as the rest of the API).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["quantdata"])

# ── Config paths ──────────────────────────────────────────────────────────────
_CONFIG_PATHS = [
    Path("/home/ubuntu/.quantdata-mcp/config.json"),
    Path("/root/.quantdata-mcp/config.json"),
]
_QD_BASE = "https://core-lb-prod.quantdata.us/api"

# ── Tool name → QD slug mapping ───────────────────────────────────────────────
# These are the "tool_name" values found in the QD config file.
# The proxy tries each name in order until it finds one with a valid ID.
_TOOL_NAMES: dict[str, list[str]] = {
    "iv_rank":   ["INTRADAY_IV_RANK", "IV_RANK"],
    "net_drift": ["OPTIONS_NET_DRIFT_TABLE", "NET_DRIFT", "OPTIONS_NET_DRIFT"],
    "max_pain":  ["OPTIONS_MAX_PAIN", "MAX_PAIN", "OPTIONS_MAX_PAIN_TABLE"],
    "order_flow":["OPTIONS_ORDER_FLOW_CONSOLIDATED_TABLE",
                  "OPTIONS_ORDER_FLOW_CONSOLIDATED",
                  "OPTIONS_ORDER_FLOW"],
    "dark_pool": ["DARK_POOL_LEVELS_TABLE", "DARK_POOL_LEVELS", "DARK_POOL"],
    "oi_change": ["OPTIONS_OPEN_INTEREST_CHANGE_TABLE",
                  "OPTIONS_OPEN_INTEREST_CHANGE",
                  "OPTIONS_OI_CHANGE"],
}

# ── Config cache (TTL = 60s) ──────────────────────────────────────────────────
_cache: dict[str, Any] = {}
_cache_at: float = 0.0
_CACHE_TTL = 60.0


def _load_config() -> dict:
    """Load and merge QD config from all known paths. Ubuntu overrides root."""
    global _cache, _cache_at
    now = time.monotonic()
    if _cache and (now - _cache_at) < _CACHE_TTL:
        return _cache

    merged: dict[str, Any] = {}
    for path in reversed(_CONFIG_PATHS):   # root first, ubuntu overrides
        if path.exists():
            try:
                data = json.loads(path.read_text())
                merged.update(data)
            except Exception as exc:
                logger.warning("Could not read QD config %s: %s", path, exc)

    _cache = merged
    _cache_at = now
    return merged


def _get_auth() -> tuple[str, str]:
    """Return (auth_token, instance_id) from config, raise 503 if missing."""
    cfg = _load_config()
    token = cfg.get("authToken") or cfg.get("auth_token") or cfg.get("token", "")
    inst  = cfg.get("instanceId") or cfg.get("instance_id") or cfg.get("userId", "")
    if not token or not inst:
        raise HTTPException(503, "QuantData credentials not configured — re-login via Settings.")
    return token, inst


def _get_tool_id(key: str) -> str:
    """Look up tool ID for key. Searches config tools list by name."""
    cfg = _load_config()
    tools: list[dict] = cfg.get("tools", [])

    # Build name→id map from config
    name_to_id: dict[str, str] = {}
    for t in tools:
        name = (t.get("toolName") or t.get("name") or t.get("tool_name") or "").upper()
        tid  = (t.get("toolId")   or t.get("id")   or t.get("tool_id")   or "")
        if name and tid:
            name_to_id[name] = tid

    # Also check top-level shorthand keys (legacy format)
    shorthand = {
        "iv_rank":   cfg.get("iv_rank_tool_id"),
        "net_drift": cfg.get("net_drift_tool_id"),
        "max_pain":  cfg.get("max_pain_tool_id"),
        "order_flow":cfg.get("order_flow_tool_id"),
        "dark_pool": cfg.get("dark_pool_tool_id"),
        "oi_change": cfg.get("oi_change_tool_id"),
    }
    if shorthand.get(key):
        return shorthand[key]

    # Search by canonical names
    for name in _TOOL_NAMES.get(key, []):
        if name in name_to_id:
            return name_to_id[name]

    raise HTTPException(
        404,
        f"QuantData tool endpoint not found for '{key}'. "
        "Re-login via Settings → QuantData Auto-Login to refresh tool IDs."
    )


def _qd_get(tool_key: str, ticker: str, session_date: Optional[str], extra_params: Optional[dict] = None) -> Any:
    """Call QD API for a given tool key and ticker."""
    token, inst = _get_auth()
    tool_id = _get_tool_id(tool_key)
    slug = _TOOL_NAMES[tool_key][0]   # use first name as URL slug

    params: dict = {"sessionDate": session_date or _today(), "ticker": ticker.upper()}
    if extra_params:
        params.update(extra_params)

    headers = {
        "accept": "application/json",
        "authorization": token,
        "x-qd-version": "1",
        "origin": "https://v3.quantdata.us",
    }

    url = f"{_QD_BASE}/options/{slug}/{tool_id}"
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
    except requests.exceptions.RequestException as exc:
        raise HTTPException(502, f"QuantData request failed: {exc}") from exc

    if resp.status_code == 401:
        raise HTTPException(401, "QuantData auth expired — re-login via Settings → QuantData Auto-Login.")
    if resp.status_code == 404:
        raise HTTPException(404, f"QuantData tool endpoint not found. Tool may need reconfiguration.")
    if resp.status_code == 429:
        raise HTTPException(429, "QuantData rate limit — try again in a few seconds.")
    if resp.status_code == 503:
        raise HTTPException(503, "QuantData service unavailable — try again shortly.")
    if not resp.ok:
        raise HTTPException(resp.status_code, f"QuantData error {resp.status_code}")

    if not resp.content:
        raise HTTPException(204, "QuantData returned empty response.")

    try:
        return resp.json()
    except Exception:
        raise HTTPException(502, "QuantData returned non-JSON response.")


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/qd/iv-rank/{ticker}")
def qd_iv_rank(ticker: str, session_date: Optional[str] = Query(default=None)):
    data = _qd_get("iv_rank", ticker, session_date)
    return {
        "ticker": ticker.upper(),
        "session_date": session_date or _today(),
        "iv_rank":       _extract(data, ["ivRank", "iv_rank", "IVRank"]),
        "iv_percentile": _extract(data, ["ivPercentile", "iv_percentile"]),
        "current_iv":    _extract(data, ["currentIV", "current_iv", "iv"]),
        "iv_52w_high":   _extract(data, ["iv52wHigh", "iv_52w_high"]),
        "iv_52w_low":    _extract(data, ["iv52wLow",  "iv_52w_low"]),
        "call_iv":       _extract(data, ["callIV", "call_iv"]),
        "put_iv":        _extract(data, ["putIV",  "put_iv"]),
    }


@router.get("/qd/net-drift/{ticker}")
def qd_net_drift(ticker: str, session_date: Optional[str] = Query(default=None)):
    data = _qd_get("net_drift", ticker, session_date)
    call_p = _extract(data, ["callPremium", "call_premium"], 0)
    put_p  = _extract(data, ["putPremium",  "put_premium"],  0)
    net    = _extract(data, ["netDrift", "net_drift"], (call_p or 0) - (put_p or 0))
    points = _extract(data, ["dataPoints", "data_points", "count"], 0)
    bias   = "bullish" if (net or 0) > 0 else ("bearish" if (net or 0) < 0 else "neutral")
    return {
        "ticker":        ticker.upper(),
        "session_date":  session_date or _today(),
        "call_premium":  call_p,
        "put_premium":   put_p,
        "net_drift":     net,
        "bias":          bias,
        "data_points":   points,
    }


@router.get("/qd/max-pain/{ticker}")
def qd_max_pain(ticker: str, session_date: Optional[str] = Query(default=None)):
    data = _qd_get("max_pain", ticker, session_date)
    return {
        "ticker":          ticker.upper(),
        "session_date":    session_date or _today(),
        "max_pain_strike": _extract(data, ["maxPain", "max_pain", "maxPainStrike"]),
        "current_price":   _extract(data, ["currentPrice", "current_price", "price"]),
        "distance_pct":    _extract(data, ["distancePct", "distance_pct"]),
        "expirations":     _extract(data, ["expirations", "expiries"], []),
        "raw":             data,
    }


@router.get("/qd/order-flow/{ticker}")
def qd_order_flow(
    ticker: str,
    session_date: Optional[str] = Query(default=None),
    min_premium:  Optional[float] = Query(default=None),
    side:         str   | None = Query(default=None),
    limit:        int          = Query(default=50),
):
    data = _qd_get("order_flow", ticker, session_date)
    flow = _extract(data, ["flow", "orders", "data", "rows"], [])
    if side and isinstance(flow, list):
        flow = [r for r in flow if str(r.get("side", "")).upper() == side.upper()]
    if min_premium is not None and isinstance(flow, list):
        flow = [r for r in flow if (r.get("premium") or 0) >= min_premium]
    if isinstance(flow, list):
        flow = flow[:limit]
    return {
        "ticker":       ticker.upper(),
        "session_date": session_date or _today(),
        "flow":         flow,
    }


@router.get("/qd/dark-pool/{ticker}")
def qd_dark_pool(ticker: str, session_date: Optional[str] = Query(default=None)):
    data = _qd_get("dark_pool", ticker, session_date)
    levels = _extract(data, ["levels", "dpLevels", "dp_levels", "data", "rows"], [])
    return {
        "ticker":    ticker.upper(),
        "dp_levels": levels,
        "raw":       data,
    }


@router.get("/qd/oi-change/{ticker}")
def qd_oi_change(ticker: str, session_date: Optional[str] = Query(default=None)):
    data = _qd_get("oi_change", ticker, session_date)
    return {
        "ticker":              ticker.upper(),
        "session_date":        session_date or _today(),
        "total_call_oi_change": _extract(data, ["totalCallOiChange", "call_oi_change"], 0),
        "total_put_oi_change":  _extract(data, ["totalPutOiChange",  "put_oi_change"],  0),
        "notable":              _extract(data, ["notable", "rows", "data"], []),
        "raw":                  data,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract(data: Any, keys: list[str], default: Any = None) -> Any:
    """Extract first matching key from a dict or nested result."""
    if isinstance(data, dict):
        # Direct key match
        for k in keys:
            if k in data:
                return data[k]
        # Try nested under 'result', 'data', 'payload'
        for wrapper in ("result", "data", "payload"):
            if wrapper in data and isinstance(data[wrapper], dict):
                for k in keys:
                    if k in data[wrapper]:
                        return data[wrapper][k]
    return default


@router.get("/qd/tools")
def qd_tools_diagnostic():
    """Diagnostic: list all tool names and IDs found in the QD config."""
    cfg = _load_config()
    tools: list[dict] = cfg.get("tools", [])
    available = []
    for t in tools:
        name = (t.get("toolName") or t.get("name") or t.get("tool_name") or "").upper()
        tid  = (t.get("toolId")   or t.get("id")   or t.get("tool_id")   or "")
        if name:
            available.append({"name": name, "id": tid or "(no id)"})
    # Also show which of our proxy keys resolved
    resolved = {}
    for key, slugs in _TOOL_NAMES.items():
        try:
            tid = _get_tool_id(key)
            resolved[key] = {"status": "ok", "tool_id": tid}
        except HTTPException as e:
            resolved[key] = {"status": "missing", "detail": e.detail}
    return {
        "config_paths_checked": [str(p) for p in _CONFIG_PATHS],
        "config_tool_count": len(available),
        "all_tools_in_config": available,
        "proxy_key_resolution": resolved,
    }
