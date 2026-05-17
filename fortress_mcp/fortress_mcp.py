#!/usr/bin/env python3
"""
fortress_mcp.py — Fortress Dashboard MCP Server
Tier 1 (25 read-only tools) + Tier 2 (9 write tools, env-gated)

Transport: stdio (launched by Claude Desktop as a subprocess)
Auth:      Bearer token via FORTRESS_API_TOKEN env var
Writes:    Enabled only when FORTRESS_MCP_ALLOW_WRITES=1

QuantData live tools (Tier 1b — 6 tools):
  Requires QUANTDATA_AUTH_TOKEN + QUANTDATA_INSTANCE_ID env vars.
  These call the QuantData API directly for real-time market data.
  If not set, tools return a clear error message rather than failing silently.

Usage:
    export FORTRESS_API_URL=http://your-vps-ip:3000  # nginx port (proxies /api/* to FastAPI)
    export FORTRESS_API_TOKEN=your-64-char-token
    export QUANTDATA_AUTH_TOKEN=your-qd-jwt-token        # optional
    export QUANTDATA_INSTANCE_ID=your-qd-instance-id    # optional
    python3 fortress_mcp.py
"""

import os
import json
import time
import logging
from typing import Optional, Any
import httpx
import requests
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
API_URL   = os.environ.get("FORTRESS_API_URL", "http://76.13.138.194:3000").rstrip("/")
API_TOKEN = os.environ.get("FORTRESS_API_TOKEN", "")
ALLOW_WRITES = os.environ.get("FORTRESS_MCP_ALLOW_WRITES", "0") == "1"

# QuantData live API credentials (optional — only needed for Tier 1b tools)
QD_AUTH_TOKEN   = os.environ.get("QUANTDATA_AUTH_TOKEN", "")
QD_INSTANCE_ID  = os.environ.get("QUANTDATA_INSTANCE_ID", "")
QD_BASE_URL     = "https://core-lb-prod.quantdata.us/api"
QD_AVAILABLE    = bool(QD_AUTH_TOKEN and QD_INSTANCE_ID)

mcp = FastMCP(
    "fortress-dashboard",
    instructions=(
        "Fortress Dashboard MCP — Portfolio Strategy v3.7.2. "
        "All monetary values are USD. Delta target: 0.35 net long. "
        "Use get_briefing() first for any portfolio question. "
        "Never execute trades — this server is read-only unless FORTRESS_MCP_ALLOW_WRITES=1. "
        "Live QuantData tools (qd_*) require QUANTDATA_AUTH_TOKEN + QUANTDATA_INSTANCE_ID env vars."
    ),
)

# ─── QuantData HTTP client ────────────────────────────────────────────────────
def _qd_check() -> None:
    """Raise if QuantData credentials are not configured."""
    if not QD_AVAILABLE:
        raise ValueError(
            "QuantData credentials not configured. "
            "Set QUANTDATA_AUTH_TOKEN and QUANTDATA_INSTANCE_ID environment variables. "
            "See README for how to obtain these from your QuantData account."
        )

def _qd_get(endpoint: str, params: dict | None = None) -> Any:
    """GET request to QuantData API with retry-with-backoff."""
    _qd_check()
    url = f"{QD_BASE_URL}/{endpoint.lstrip('/')}"
    headers = {
        "accept": "application/json",
        "authorization": QD_AUTH_TOKEN,
        "x-instance-id": QD_INSTANCE_ID,
        "x-qd-version": "1",
        "origin": "https://v3.quantdata.us",
    }
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code == 401:
                raise ValueError("QuantData authentication failed — check QUANTDATA_AUTH_TOKEN and QUANTDATA_INSTANCE_ID.")
            if resp.status_code == 429:
                if attempt < 2:
                    time.sleep(1.0 * (2 ** attempt))
                    continue
                raise ValueError("QuantData rate limit exceeded. Try again in a few seconds.")
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise ValueError(f"QuantData API request failed after 3 attempts: {e}") from e
    raise ValueError("Unexpected error in QuantData request handling")

def _qd_set_filter(page_id: str, session_date: str, ticker: str) -> bool:
    """Set page-level ticker + date filter on QuantData before fetching data."""
    if not QD_AVAILABLE:
        return False
    url = f"{QD_BASE_URL}/page/{page_id}/filter"
    headers = {
        "accept": "application/json",
        "authorization": QD_AUTH_TOKEN,
        "x-instance-id": QD_INSTANCE_ID,
        "x-qd-version": "1",
        "origin": "https://v3.quantdata.us",
    }
    payload = {
        "sessionDate": {"filterOperationType": "EQUALS", "value": session_date},
        "ticker": {"filterOperationType": "EQUALS", "value": [ticker]},
    }
    try:
        resp = requests.put(url, headers=headers, json=payload, timeout=10)
        return resp.status_code < 300
    except Exception:
        return False

# ─── HTTP client ─────────────────────────────────────────────────────────────
def _client() -> httpx.Client:
    return httpx.Client(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=30,
        verify=False,  # self-signed cert on VPS
    )

def _get(path: str, params: dict | None = None) -> Any:
    with _client() as c:
        r = c.get(path, params=params)
        r.raise_for_status()
        return r.json()

def _post(path: str, body: dict | None = None, params: dict | None = None) -> Any:
    with _client() as c:
        r = c.post(path, json=body or {}, params=params)
        r.raise_for_status()
        return r.json()

def _put(path: str, body: dict) -> Any:
    with _client() as c:
        r = c.put(path, json=body)
        r.raise_for_status()
        return r.json()

def _patch(path: str, body: dict) -> Any:
    with _client() as c:
        r = c.patch(path, json=body)
        r.raise_for_status()
        return r.json()

def _delete(path: str) -> Any:
    with _client() as c:
        r = c.delete(path)
        r.raise_for_status()
        return r.json()

def _writes_check() -> None:
    if not ALLOW_WRITES:
        raise PermissionError(
            "Write tools are disabled. Set FORTRESS_MCP_ALLOW_WRITES=1 to enable."
        )

# ─── Tier 1 — Read-only tools (19) ───────────────────────────────────────────

@mcp.tool()
def get_briefing() -> dict:
    """
    Full portfolio briefing: account header (NetLiq, delta, pacing), today's
    required actions, market regime, concentration top-5, Portfolio Greeks
    (delta/theta/vega), FX rates, USD threshold check, and data staleness.
    Call this first for any portfolio question.
    """
    return _get("/api/briefing")


@mcp.tool()
def get_positions(aggregated: bool = True) -> dict:
    """
    Current option book. aggregated=True (default) returns one row per ticker
    with combined delta/theta/vega. aggregated=False returns one row per leg.
    Includes stop-loss status, DTE, and Greeks per position.
    """
    if aggregated:
        return _get("/api/manage/positions")
    return _get("/api/positions")


@mcp.tool()
def get_candidates() -> dict:
    """
    IV crush candidate scanner: tickers ranked by IVR and IV/HV spread,
    enriched with earnings blackout status, concentration check, exclusion
    flags, and a tradeable signal. Use before any new trade decision.
    """
    return _get("/api/candidates")


@mcp.tool()
def get_calendar(window_days: int = 14) -> dict:
    """
    Earnings calendar for the next window_days (default 14). Returns each
    ticker's next earnings date, days-to-earnings, and confirmation status.
    Critical for pre-trade gate §3.3 (no new positions within 7 days of earnings).
    """
    return _get("/api/calendar", params={"window_days": window_days})


@mcp.tool()
def get_universe() -> dict:
    """
    Full trading universe: tier1 (core watchlist), tier2 (secondary),
    macro (SPX/SPY/VIX), and excluded tickers with exclusion reasons.
    """
    return _get("/api/universe")


@mcp.tool()
def get_journal(limit: int = 30) -> dict:
    """
    Recent trade journal entries (default last 30). Each entry includes
    action type, ticker, reasoning, framework rules cited, and outcome
    metrics where available. Use for decision audit trail.
    """
    return _get("/api/journal", params={"limit": limit})


@mcp.tool()
def get_alerts() -> dict:
    """
    Active profit-take and stop-loss alerts. Each alert includes position ID,
    trigger type (delta/price/pnl), trigger value, direction, and action.
    """
    return _get("/api/alerts")


@mcp.tool()
def get_dp_floors_and_gex(ticker: str) -> dict:
    """
    DP floors and GEX walls for a ticker from the latest QuantData Daily Report.
    Returns key support/resistance levels used in stop-loss and roll decisions.
    ticker: uppercase ticker symbol, e.g. 'AAPL', 'SPY'
    """
    return _get(f"/api/chart/{ticker}/levels")



@mcp.tool()
def get_market_intelligence(ticker: str = "SPY") -> dict:
    """
    Full market intelligence synthesis for a ticker: regime score (-4 to +4),
    GEX gamma flip zone, dark pool floors, net drift, and specific trade setups.
    This is the most sophisticated output the Fortress system produces — use it
    every morning before placing trades and when evaluating directional bias.
    ticker: uppercase ticker symbol, e.g. 'SPY', 'QQQ', 'AAPL'. Defaults to 'SPY'.
    """
    return _get(f"/api/market-intelligence", params={"ticker": ticker})


@mcp.tool()
def get_chart_data(ticker: str, period: str = "3mo") -> dict:
    """
    OHLCV price candles plus overlay levels (DP floors, GEX walls, moving
    averages) for a ticker. period: '1mo', '3mo', '6mo', '1y'.
    ticker: uppercase ticker symbol, e.g. 'AAPL'
    """
    return _get(f"/api/chart/{ticker}", params={"period": period})


@mcp.tool()
def evaluate_stop_loss(
    ticker: str,
    fundamental_break: bool = False,
    peak_mv: Optional[float] = None,
) -> dict:
    """
    Multi-signal stop-loss verdict for a position per Strategy §6.
    Returns: hold / close / reduce recommendation with signal breakdown.
    ticker: uppercase ticker symbol
    fundamental_break: True if a thesis-invalidating event has occurred
    peak_mv: peak market value of the position if known (for drawdown calc)
    """
    params: dict = {"fundamental_break": str(fundamental_break).lower()}
    if peak_mv is not None:
        params["peak_mv"] = peak_mv
    return _get(f"/api/manage/stop_loss/{ticker}", params=params)


@mcp.tool()
def evaluate_roll(
    ticker: str,
    dte_low: int = 30,
    dte_high: int = 45,
    delta_low: float = 0.20,
    delta_high: float = 0.25,
) -> dict:
    """
    Roll evaluation for an expiring position per Strategy §5.
    Returns top-3 roll candidates with strike/expiry/credit and IBKR ticket text.
    ticker: uppercase ticker symbol
    dte_low/dte_high: target DTE window for the rolled position
    delta_low/delta_high: target delta range for the rolled strike
    """
    return _get(
        f"/api/manage/roll/{ticker}",
        params={
            "dte_low": dte_low,
            "dte_high": dte_high,
            "delta_low": delta_low,
            "delta_high": delta_high,
        },
    )


@mcp.tool()
def evaluate_post_earnings(
    ticker: str,
    gap_pct: float,
    iv_crush_pct: float,
    thesis: Optional[dict] = None,
) -> dict:
    """
    Post-earnings decision matrix per Strategy §10.
    Returns: hold / close / adjust verdict with reasoning.
    ticker: uppercase ticker symbol
    gap_pct: overnight gap as a percentage (negative = gap down), e.g. -4.5
    iv_crush_pct: IV crush magnitude as a percentage, e.g. 35.0
    thesis: optional dict with original trade thesis fields
    """
    body: dict = {"ticker": ticker, "gap_pct": gap_pct, "iv_crush_pct": iv_crush_pct}
    if thesis:
        body["thesis"] = thesis
    return _post("/api/playbook/post_earnings", body=body)


@mcp.tool()
def validate_jade_lizard(
    put_strike: float,
    call_short_strike: float,
    call_long_strike: float,
    put_credit: float,
    call_spread_credit: float,
) -> dict:
    """
    Validate a jade lizard structure per Strategy §2.E.
    Checks that total credit > width of call spread (no upside risk).
    Returns: valid/invalid with credit breakdown and risk assessment.
    All strikes and credits in USD.
    """
    return _post(
        "/api/manage/validate_jade_lizard",
        body={
            "put_strike": put_strike,
            "call_short_strike": call_short_strike,
            "call_long_strike": call_long_strike,
            "put_credit": put_credit,
            "call_spread_credit": call_spread_credit,
        },
    )


@mcp.tool()
def get_spy_hedge_coverage() -> dict:
    """
    SPY hedge coverage check per Strategy §2.D (USD-native in v3.6).
    Returns: current hedge notional, required coverage, gap, and verdict.
    """
    return _get("/api/manage/spy_hedge_coverage")


@mcp.tool()
def pretrade_check(ticker: str, strategy: str) -> dict:
    """
    Full pre-trade gate check per Strategy §3.3 → §4 → §7.
    Runs: exclusion check, earnings blackout (7-day window), concentration
    limit (Strategy §3.4), and VIX regime gate.
    ticker: uppercase ticker symbol, e.g. 'AAPL'
    strategy: strategy type, e.g. 'short_put', 'short_strangle', 'jade_lizard'
    Returns: go / no-go with per-gate breakdown.
    """
    return _get("/api/ibkr/preview", params={"ticker": ticker, "strategy": strategy})


@mcp.tool()
def get_capability(refresh: bool = False) -> dict:
    """
    Greeks backend capability probe: Web API (CP Gateway + OPRA) and legacy
    TWS gateway status. Use to answer 'Is live Greeks coverage active right now?'
    refresh=True forces a fresh probe (otherwise returns cached result, ~60s TTL).
    Returns: active_backend, session status, OPRA subscription, checked_at.
    """
    return _get("/api/ibkr/capability", params={"refresh": str(refresh).lower()})


@mcp.tool()
def get_ibkr_status() -> dict:
    """
    Legacy TWS gateway connection status (diagnostics only).
    For current Greeks backend health, prefer get_capability().
    """
    return _get("/api/ibkr/status")


@mcp.tool()
def get_settings() -> dict:
    """
    All current runtime configuration: strategy thresholds, alert thresholds,
    technical/infrastructure settings (Greeks backend, gateway URLs, API keys
    masked), and UI preferences.
    Returns: {config: {strategy: {...}, alerts: {...}, technical: {...}, ui: {...}}}
    """
    return _get("/api/settings")


@mcp.tool()
def get_quantdata_reports(report: str = "daily", date: str = "latest") -> dict:
    """
    Retrieve a QuantData report from the VPS filesystem.
    report: report type — 'daily', 'weekly', or 'options'
    date: 'latest' (default) or a date string 'YYYY-MM-DD'
    Returns the full report text and metadata.
    """
    return _get("/api/uploads", params={"report": report, "date": date})


# ─── Tier 2 — Write tools (env-gated, 9 tools) ───────────────────────────────

@mcp.tool()
def add_journal_entry(
    action: str,
    ticker: str,
    description: str,
    reasoning: str,
    framework_rules: list[str],
    outcome: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Append a new entry to the trade journal.
    action: e.g. 'open', 'close', 'roll', 'adjust', 'observe'
    ticker: uppercase ticker symbol
    description: one-sentence summary of the action taken
    reasoning: detailed reasoning referencing strategy framework
    framework_rules: list of strategy section references, e.g. ['§3.3', '§6.2']
    outcome: optional outcome description (for post-trade entries)
    tags: optional list of tags, e.g. ['earnings', 'roll', 'stop-loss']
    """
    _writes_check()
    body: dict = {
        "action": action,
        "ticker": ticker,
        "description": description,
        "reasoning": reasoning,
        "framework_rules": framework_rules,
    }
    if outcome:
        body["outcome"] = outcome
    if tags:
        body["tags"] = tags
    return _post("/api/journal", body=body)


@mcp.tool()
def add_alert(
    position_id: str,
    trigger_type: str,
    trigger_value: float,
    direction: str,
    action: str,
) -> dict:
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Add a new profit-take or stop-loss alert.
    position_id: position identifier from get_positions()
    trigger_type: 'delta', 'price', or 'pnl_pct'
    trigger_value: numeric threshold
    direction: 'above' or 'below'
    action: 'close', 'reduce_50', or 'notify'
    """
    _writes_check()
    return _post("/api/alerts", body={
        "position_id": position_id,
        "trigger_type": trigger_type,
        "trigger_value": trigger_value,
        "direction": direction,
        "action": action,
    })


@mcp.tool()
def update_alert(
    alert_id: str,
    trigger_value: Optional[float] = None,
    action: Optional[str] = None,
    active: Optional[bool] = None,
) -> dict:
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Update an existing alert's trigger value, action, or active status.
    alert_id: alert identifier from get_alerts()
    """
    _writes_check()
    body: dict = {}
    if trigger_value is not None:
        body["trigger_value"] = trigger_value
    if action is not None:
        body["action"] = action
    if active is not None:
        body["active"] = active
    return _patch(f"/api/alerts/{alert_id}", body=body)


@mcp.tool()
def delete_alert(alert_id: str) -> dict:
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Delete an alert by ID. Reversible from backups.
    alert_id: alert identifier from get_alerts()
    """
    _writes_check()
    return _delete(f"/api/alerts/{alert_id}")


@mcp.tool()
def update_calendar(
    ticker: str,
    next_earnings: str,
    confirmed: bool = False,
) -> dict:
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Update the earnings date for a ticker.
    ticker: uppercase ticker symbol
    next_earnings: date string 'YYYY-MM-DD'
    confirmed: True if date is confirmed (not estimated)
    Affects pre-trade earnings blackout gate (§3.3).
    """
    _writes_check()
    return _put(f"/api/calendar/{ticker}", body={
        "next_earnings": next_earnings,
        "confirmed": confirmed,
    })


@mcp.tool()
def add_excluded_ticker(ticker: str, reason: str) -> dict:
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Add a ticker to the exclusion list.
    ticker: uppercase ticker symbol
    reason: human-readable reason for exclusion
    """
    _writes_check()
    return _post("/api/universe/exclude", body={"ticker": ticker, "reason": reason})


@mcp.tool()
def add_universe_ticker(tier: str, ticker: str) -> dict:
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Add a ticker to the trading universe.
    tier: 'tier1', 'tier2', or 'macro'
    ticker: uppercase ticker symbol
    Note: tier composition changes require manual review per Strategy §3.4.4.
    """
    _writes_check()
    return _post("/api/universe/add", body={"tier": tier, "ticker": ticker})


@mcp.tool()
def update_settings_section(section: str, values: dict) -> dict:
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Update a settings section. Only use when explicitly approved by user in chat.
    section: 'strategy', 'alerts', 'technical', or 'ui'
    values: dict of key-value pairs to update, e.g. {"delta_target": 0.35}
    Use get_settings() first to see current values and valid keys.
    """
    _writes_check()
    return _put(f"/api/settings/{section}", body={"values": values})


@mcp.tool()
def trigger_ibkr_sync(backend: Optional[str] = None) -> dict:
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Trigger an IBKR positions and Greeks sync.
    backend: override backend — 'web_api', 'bs_yfinance', 'tws_ibkr', or None for auto.
    Atomic operation with backup. Use sparingly — sync runs automatically every 60s.
    """
    _writes_check()
    body: dict = {}
    if backend:
        body["backend"] = backend
    return _post("/api/ibkr/sync", body=body)


# ─── Tier 1b — QuantData live tools (6, read-only, requires QD credentials) ──

@mcp.tool()
def qd_get_dark_pool_levels(ticker: str, session_date: str | None = None) -> dict:
    """
    Live Dark Pool hard floor levels for a ticker from the QuantData API.
    Supersedes the static parsed-report version (get_dp_floors_and_gex) with
    real-time data. Use for stop-loss level confirmation and chart overlay.
    ticker: uppercase ticker symbol, e.g. 'MSFT', 'AAPL'
    session_date: YYYY-MM-DD (defaults to today)
    Returns: {"ticker", "dp_levels": [{"price", "notional_m", "type"}, ...]}
    """
    from datetime import date
    _qd_check()
    if not session_date:
        session_date = date.today().isoformat()
    data = _qd_get(f"tool/OPTIONS_DARK_POOL_LEVELS_TABLE",
                   params={"ticker": ticker, "sessionDate": session_date})
    response = data.get("response", data)
    rows = response.get("rows", response.get("data", []))
    levels = []
    for row in rows:
        price = row.get("price") or row.get("level") or row.get("strike")
        notional = row.get("notional") or row.get("notionalM") or row.get("volume")
        level_type = row.get("type", "floor")
        if price:
            levels.append({"price": price, "notional_m": notional, "type": level_type})
    return {"ticker": ticker, "session_date": session_date, "dp_levels": levels, "source": "quantdata_live_api"}


@mcp.tool()
def qd_get_order_flow(
    ticker: str,
    session_date: str | None = None,
    min_premium: float | None = None,
    is_sweep: bool | None = None,
    is_block: bool | None = None,
    side: str | None = None,
    limit: int = 50,
) -> dict:
    """
    Live options order flow for a ticker from the QuantData API.
    Use for pre-trade confirmation: look for large sweeps/blocks aligned with
    your directional thesis before entering a new position.
    ticker: uppercase ticker symbol
    session_date: YYYY-MM-DD (defaults to today)
    min_premium: minimum premium in USD (e.g. 50000 for $50K+ prints)
    is_sweep: True to filter sweeps only
    is_block: True to filter blocks only
    side: 'CALL' or 'PUT' to filter by side
    limit: max rows to return (default 50)
    Returns: {"ticker", "session_date", "flow": [{"time", "side", "strike", "expiry",
              "premium", "size", "is_sweep", "is_block", "sentiment"}, ...]}
    """
    from datetime import date
    _qd_check()
    if not session_date:
        session_date = date.today().isoformat()
    params: dict = {"ticker": ticker, "sessionDate": session_date, "limit": limit}
    if min_premium is not None:
        params["minPremium"] = min_premium
    if is_sweep is not None:
        params["isSweep"] = str(is_sweep).lower()
    if is_block is not None:
        params["isBlock"] = str(is_block).lower()
    if side:
        params["side"] = side.upper()
    data = _qd_get("tool/OPTIONS_ORDER_FLOW_CONSOLIDATED_TABLE", params=params)
    response = data.get("response", data)
    rows = response.get("rows", response.get("data", []))
    flow = []
    for row in rows:
        flow.append({
            "time":      row.get("time") or row.get("timestamp"),
            "side":      row.get("side") or row.get("callPut"),
            "strike":    row.get("strike"),
            "expiry":    row.get("expiry") or row.get("expirationDate"),
            "premium":   row.get("premium") or row.get("totalPremium"),
            "size":      row.get("size") or row.get("quantity"),
            "is_sweep":  row.get("isSweep", False),
            "is_block":  row.get("isBlock", False),
            "sentiment": row.get("sentiment") or row.get("aggressor"),
        })
    return {"ticker": ticker, "session_date": session_date, "flow": flow, "source": "quantdata_live_api"}


@mcp.tool()
def qd_get_net_drift(ticker: str, session_date: str | None = None) -> dict:
    """
    Cumulative call vs put premium flow (net drift) for a ticker.
    Positive net drift = call premium dominates = bullish smart money bias.
    Negative net drift = put premium dominates = bearish smart money bias.
    Use as a directional bias signal before entering directional spreads.
    ticker: uppercase ticker symbol
    session_date: YYYY-MM-DD (defaults to today)
    Returns: {"ticker", "session_date", "call_premium", "put_premium",
              "net_drift", "bias": 'bullish'|'bearish'|'neutral'}
    """
    from datetime import date
    _qd_check()
    if not session_date:
        session_date = date.today().isoformat()
    data = _qd_get("tool/OPTIONS_NET_DRIFT_CHART",
                   params={"ticker": ticker, "sessionDate": session_date})
    response = data.get("response", data)
    call_prem = response.get("callPremium") or response.get("totalCallPremium", 0)
    put_prem  = response.get("putPremium")  or response.get("totalPutPremium", 0)
    net = (call_prem or 0) - (put_prem or 0)
    bias = "bullish" if net > 0 else ("bearish" if net < 0 else "neutral")
    return {
        "ticker":        ticker,
        "session_date":  session_date,
        "call_premium":  call_prem,
        "put_premium":   put_prem,
        "net_drift":     net,
        "bias":          bias,
        "source":        "quantdata_live_api",
    }


@mcp.tool()
def qd_get_max_pain(ticker: str, session_date: str | None = None) -> dict:
    """
    Max pain strike and distance from current price for a ticker.
    Max pain = the price at which option sellers (market makers) have minimum
    aggregate payout. Use for strike selection on PCS/CSP entries — prefer
    strikes below max pain for put spreads.
    ticker: uppercase ticker symbol
    session_date: YYYY-MM-DD (defaults to today)
    Returns: {"ticker", "session_date", "max_pain_strike", "current_price",
              "distance_pct", "expirations": [{"date", "max_pain"}, ...]}
    """
    from datetime import date
    _qd_check()
    if not session_date:
        session_date = date.today().isoformat()
    data = _qd_get("tool/OPTIONS_MAX_PAIN_CHART",
                   params={"ticker": ticker, "sessionDate": session_date})
    response = data.get("response", data)
    max_pain = response.get("maxPain") or response.get("maxPainStrike")
    current  = response.get("currentPrice") or response.get("underlyingPrice")
    dist_pct = None
    if max_pain and current and current != 0:
        dist_pct = round((max_pain - current) / current * 100, 2)
    expirations = []
    for row in response.get("expirations", response.get("data", [])):
        expirations.append({
            "date":      row.get("expirationDate") or row.get("date"),
            "max_pain":  row.get("maxPain") or row.get("maxPainStrike"),
        })
    return {
        "ticker":          ticker,
        "session_date":    session_date,
        "max_pain_strike": max_pain,
        "current_price":   current,
        "distance_pct":    dist_pct,
        "expirations":     expirations,
        "source":          "quantdata_live_api",
    }


@mcp.tool()
def qd_get_iv_rank(ticker: str, session_date: str | None = None) -> dict:
    """
    IV Rank and IV Percentile for a ticker from QuantData.
    Richer than the IBKR snapshot IVR — includes configurable lookback,
    maturity-weighted IV, and call/put IV split.
    Use for IV crush candidate evaluation (Strategy §4.1 — IVR > 50 threshold).
    ticker: uppercase ticker symbol
    session_date: YYYY-MM-DD (defaults to today)
    Returns: {"ticker", "iv_rank", "iv_percentile", "current_iv",
              "iv_52w_high", "iv_52w_low", "call_iv", "put_iv"}
    """
    from datetime import date
    _qd_check()
    if not session_date:
        session_date = date.today().isoformat()
    data = _qd_get("tool/OPTIONS_IV_RANK_CHART",
                   params={"ticker": ticker, "sessionDate": session_date})
    response = data.get("response", data)
    return {
        "ticker":         ticker,
        "session_date":   session_date,
        "iv_rank":        response.get("ivRank") or response.get("rank"),
        "iv_percentile":  response.get("ivPercentile") or response.get("percentile"),
        "current_iv":     response.get("currentIv") or response.get("iv"),
        "iv_52w_high":    response.get("iv52wHigh") or response.get("high52w"),
        "iv_52w_low":     response.get("iv52wLow") or response.get("low52w"),
        "call_iv":        response.get("callIv"),
        "put_iv":         response.get("putIv"),
        "source":         "quantdata_live_api",
    }


@mcp.tool()
def qd_get_oi_change(ticker: str, session_date: str | None = None) -> dict:
    """
    Day-over-day open interest change for a ticker — identifies unusual OI
    build-up that may signal institutional positioning before earnings or
    major events. Use to flag unusual activity before entering new positions.
    ticker: uppercase ticker symbol
    session_date: YYYY-MM-DD (defaults to today)
    Returns: {"ticker", "session_date", "total_call_oi_change",
              "total_put_oi_change", "notable": [{"strike", "expiry",
              "side", "oi_change", "pct_change"}, ...]}
    """
    from datetime import date
    _qd_check()
    if not session_date:
        session_date = date.today().isoformat()
    data = _qd_get("tool/OPTIONS_OPEN_INTEREST_CHANGE_TABLE",
                   params={"ticker": ticker, "sessionDate": session_date})
    response = data.get("response", data)
    rows = response.get("rows", response.get("data", []))
    notable = []
    for row in rows:
        notable.append({
            "strike":     row.get("strike"),
            "expiry":     row.get("expirationDate") or row.get("expiry"),
            "side":       row.get("side") or row.get("callPut"),
            "oi_change":  row.get("oiChange") or row.get("change"),
            "pct_change": row.get("pctChange") or row.get("percentChange"),
        })
    return {
        "ticker":               ticker,
        "session_date":         session_date,
        "total_call_oi_change": response.get("totalCallOiChange"),
        "total_put_oi_change":  response.get("totalPutOiChange"),
        "notable":              notable,
        "source":               "quantdata_live_api",
    }


# ─── Entry point ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_pending_orders(status=None):
    """
    List orders in the approval queue submitted from Build Center.
    status filter: pending | submitted | declined | failed | None for all.
    Each order shows ticker, strategy, legs, PoP, max profit/loss, whatif result.
    """
    params = {"status": status} if status else None
    return _get("/api/orders/pending", params=params)


@mcp.tool()
def options_greeks(spot: float, strike: float, dte: int, iv: float, right: str, qty=None):
    """
    Black-Scholes Greeks for any option.
    spot: underlying price. strike: strike price. dte: days to expiry.
    iv: implied vol as decimal (0.30 = 30%). right: C or P.
    qty: optional contracts — adds pos_delta/pos_theta/pos_vega.
    Returns delta, theta, gamma, vega, PoP, intrinsic, extrinsic, itm.
    """
    body = {"spot": spot, "strike": strike, "dte": dte, "iv": iv, "right": right}
    if qty is not None:
        body["qty"] = qty
    return _post("/api/options/greeks", body=body)


@mcp.tool()
def preview_order(order_id: str):
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    IBKR whatif (margin/commission estimate) for a pending order — no submission.
    Returns equity impact, init margin, maintenance margin, commission estimate.
    """
    _writes_check()
    return _post(f"/api/orders/pending/{order_id}/preview")


@mcp.tool()
def approve_order(order_id: str):
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Approve a pending order: resolves IBKR conids, runs whatif, submits to IBKR.
    Returns submitted status and IBKR order ID on success.
    """
    _writes_check()
    return _post(f"/api/orders/pending/{order_id}/approve")


@mcp.tool()
def decline_order(order_id: str):
    """
    [WRITE — requires FORTRESS_MCP_ALLOW_WRITES=1]
    Decline a pending order. Sets status to declined.
    """
    _writes_check()
    return _delete(f"/api/orders/pending/{order_id}")


if __name__ == "__main__":
    if not API_TOKEN:
        import sys
        print(
            "ERROR: FORTRESS_API_TOKEN environment variable is not set.\n"
            "Set it to the 64-char token from the VPS systemd override.\n"
            "Example: export FORTRESS_API_TOKEN=07f03fb6...",
            file=sys.stderr,
        )
        sys.exit(1)

    tier2_status = "ENABLED" if ALLOW_WRITES else "DISABLED (set FORTRESS_MCP_ALLOW_WRITES=1 to enable)"
    qd_status = "ENABLED" if QD_AVAILABLE else "DISABLED (set QUANTDATA_AUTH_TOKEN + QUANTDATA_INSTANCE_ID to enable)"
    import sys
    print(f"[fortress-mcp] Connecting to {API_URL}", file=sys.stderr)
    print(f"[fortress-mcp] Tier 1 tools: 19 (read-only)", file=sys.stderr)
    print(f"[fortress-mcp] Tier 1b QuantData live tools: {qd_status}", file=sys.stderr)
    print(f"[fortress-mcp] Tier 2 write tools: {tier2_status}", file=sys.stderr)

    mcp.run(transport="stdio")
