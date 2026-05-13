"""
Fortress Dashboard — Chart data route.
Serves OHLCV candlestick data and Dark Pool / GEX overlay levels for a given ticker.
Used by the TradingView Lightweight Charts component in the Trade tab.

Overlay data source priority (when use_quantdata = true in Settings > Security):
  1. QuantData live API  — real-time DP floors + GEX walls via JWT credentials
  2. Parsed report file  — fallback: latest QuantData Daily Report .md in DATA_DIR
  3. Empty arrays        — if both sources fail or use_quantdata = false
"""
from __future__ import annotations
import re
import time
import logging
from datetime import date
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
import yfinance as yf
import requests as req_lib
from app.services import config_store

logger = logging.getLogger("fortress.chart")
router = APIRouter(tags=["chart"])

# ── QuantData live API client ─────────────────────────────────────────────────

_QD_BASE = "https://core-lb-prod.quantdata.us/api"


def _qd_headers() -> dict:
    """Build QuantData request headers from config."""
    auth  = config_store.cfg("security.quantdata_auth_token", "")
    inst  = config_store.cfg("security.quantdata_instance_id", "")
    return {
        "accept":        "application/json",
        "authorization": auth,
        "x-instance-id": inst,
        "x-qd-version":  "1",
        "origin":        "https://v3.quantdata.us",
    }


def _qd_available() -> bool:
    """Return True if QuantData credentials are configured."""
    auth = config_store.cfg("security.quantdata_auth_token", "")
    inst = config_store.cfg("security.quantdata_instance_id", "")
    return bool(auth and inst)


def _qd_get(endpoint: str, params: dict | None = None) -> dict | None:
    """
    GET from QuantData API with 2-attempt retry.
    Returns parsed JSON dict on success, None on any failure (caller falls back).
    """
    url = f"{_QD_BASE}/{endpoint.lstrip('/')}"
    headers = _qd_headers()
    for attempt in range(2):
        try:
            resp = req_lib.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code in (401, 403):
                logger.warning("QuantData auth failed (%s) — check credentials in Settings > Security", resp.status_code)
                return None
            if resp.status_code == 429:
                if attempt == 0:
                    time.sleep(1.0)
                    continue
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("QuantData request attempt %d failed: %s", attempt + 1, exc)
            if attempt == 0:
                time.sleep(0.5)
    return None


def _fetch_dp_levels_live(ticker: str) -> dict | None:
    """
    Fetch Dark Pool floors and GEX walls from the live QuantData API.
    Returns {"dp_floors": [...], "gex_calls": [...], "gex_puts": [...], "source": "live"}
    or None if the API call fails.
    """
    session_date = date.today().isoformat()

    # DP levels
    dp_data = _qd_get(
        "tool/OPTIONS_DARK_POOL_LEVELS_TABLE",
        params={"ticker": ticker, "sessionDate": session_date},
    )
    # GEX walls
    gex_data = _qd_get(
        "tool/OPTIONS_GEX_WALLS_TABLE",
        params={"ticker": ticker, "sessionDate": session_date},
    )

    if dp_data is None and gex_data is None:
        return None

    # Parse DP floors
    dp_floors: list[float] = []
    if dp_data:
        response = dp_data.get("response", dp_data)
        rows = response.get("rows", response.get("data", []))
        for row in rows:
            price = row.get("price") or row.get("level") or row.get("strike")
            if price:
                try:
                    dp_floors.append(round(float(price), 2))
                except (TypeError, ValueError):
                    pass

    # Parse GEX walls
    gex_calls: list[float] = []
    gex_puts:  list[float] = []
    if gex_data:
        response = gex_data.get("response", gex_data)
        rows = response.get("rows", response.get("data", []))
        for row in rows:
            side  = (row.get("side") or row.get("callPut") or "").upper()
            price = row.get("price") or row.get("strike") or row.get("level")
            if price:
                try:
                    val = round(float(price), 2)
                    if side in ("CALL", "C"):
                        gex_calls.append(val)
                    elif side in ("PUT", "P"):
                        gex_puts.append(val)
                except (TypeError, ValueError):
                    pass

    logger.debug(
        "QuantData live: %s — %d DP floors, %d GEX calls, %d GEX puts",
        ticker, len(dp_floors), len(gex_calls), len(gex_puts),
    )
    return {"dp_floors": dp_floors, "gex_calls": gex_calls, "gex_puts": gex_puts, "source": "live"}


# ── Static report file parser (fallback) ─────────────────────────────────────

def _get_data_dir() -> Path:
    import os
    return Path(os.environ.get("FORTRESS_DATA_DIR", Path.home() / ".quantdata-mcp"))


def _parse_dp_levels(ticker: str) -> dict:
    """
    Parse Dark Pool floors and GEX walls for a ticker from the latest QuantData daily report.
    Fallback when the live API is unavailable or credentials are not configured.
    Returns: {"dp_floors": [...], "gex_calls": [...], "gex_puts": [...], "source": "report_file"}
    """
    data_dir = _get_data_dir()
    reports = sorted(data_dir.glob("QuantData Daily Report*.md"), reverse=True)
    if not reports:
        return {"dp_floors": [], "gex_calls": [], "gex_puts": [], "source": "none"}

    text = reports[0].read_text(encoding="utf-8", errors="ignore")

    section_pattern = rf"### {re.escape(ticker)} Execution Profile(.*?)(?=### \w+ Execution Profile|---|\Z)"
    section_match = re.search(section_pattern, text, re.DOTALL)
    if not section_match:
        return {"dp_floors": [], "gex_calls": [], "gex_puts": [], "source": "report_file_no_ticker"}

    section = section_match.group(1)

    dp_match = re.search(r"Dark Pool Hard Floors:\*\*\s*(.*)", section)
    dp_floors = []
    if dp_match:
        raw = dp_match.group(1)
        dp_floors = [float(m) for m in re.findall(r"\$(\d+(?:\.\d+)?)", raw)]

    gex_match = re.search(r"GEX Walls:\*\*\s*Calls at\s*(.*?)\s*\|\s*Puts at\s*(.*?)(?:\n|$)", section)
    gex_calls, gex_puts = [], []
    if gex_match:
        gex_calls = [float(m) for m in re.findall(r"\$(\d+(?:\.\d+)?)", gex_match.group(1))]
        gex_puts  = [float(m) for m in re.findall(r"\$(\d+(?:\.\d+)?)", gex_match.group(2))]

    return {"dp_floors": dp_floors, "gex_calls": gex_calls, "gex_puts": gex_puts, "source": "report_file"}


def _get_levels(ticker: str) -> dict:
    """
    Get DP/GEX levels using priority: live API → report file → empty.
    Only called when use_quantdata = true.
    """
    if _qd_available():
        live = _fetch_dp_levels_live(ticker)
        if live is not None:
            return live
        logger.info("QuantData live API unavailable for %s — falling back to report file", ticker)

    return _parse_dp_levels(ticker)


# ── OHLCV fetcher ─────────────────────────────────────────────────────────────

def _fetch_ohlcv(ticker: str, period: str = "3mo", interval: str = "1d") -> list[dict]:
    """
    Fetch OHLCV data from yfinance and return as a list of dicts
    compatible with TradingView Lightweight Charts CandlestickSeries.
    """
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return []
        # Flatten MultiIndex columns: ('Open', 'MSFT') -> 'Open'
        if hasattr(df.columns, "levels"):
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        candles = []
        for ts, row in df.iterrows():
            time_val = int(ts.timestamp()) if hasattr(ts, "timestamp") else str(ts)[:10]
            candles.append({
                "time":   time_val,
                "open":   round(float(row["Open"]),  2),
                "high":   round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if "Volume" in row else 0,
            })
        return candles
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", ticker, exc)
        return []


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/chart/{ticker}")
def get_chart_data(
    ticker: str,
    period: str = Query(default="3mo", description="yfinance period: 1mo, 3mo, 6mo, 1y"),
    interval: str = Query(default="1d", description="yfinance interval: 1d, 1h"),
):
    """
    Return OHLCV candles + Dark Pool floors + GEX walls for a ticker.
    Overlay data comes from the live QuantData API when credentials are configured,
    falling back to the latest uploaded daily report file.
    """
    ticker = ticker.upper()
    candles = _fetch_ohlcv(ticker, period=period, interval=interval)

    if config_store.cfg("security.use_quantdata", True):
        levels = _get_levels(ticker)
    else:
        levels = {"dp_floors": [], "gex_calls": [], "gex_puts": [], "source": "disabled"}

    if not candles:
        raise HTTPException(status_code=404, detail=f"No price data found for {ticker}")

    return {
        "ticker":        ticker,
        "period":        period,
        "interval":      interval,
        "candles":       candles,
        "levels_source": levels.get("source", "unknown"),
        "levels": {
            "dp_floors": levels["dp_floors"],
            "gex_calls": levels["gex_calls"],
            "gex_puts":  levels["gex_puts"],
        },
    }


@router.get("/chart/{ticker}/levels")
def get_chart_levels(ticker: str):
    """
    Return only the Dark Pool and GEX levels for a ticker (no OHLCV).
    Fast endpoint for refreshing overlays without re-fetching candles.
    """
    ticker = ticker.upper()
    if config_store.cfg("security.use_quantdata", True):
        levels = _get_levels(ticker)
    else:
        levels = {"dp_floors": [], "gex_calls": [], "gex_puts": [], "source": "disabled"}
    return {
        "ticker":        ticker,
        "levels_source": levels.get("source", "unknown"),
        "dp_floors":     levels["dp_floors"],
        "gex_calls":     levels["gex_calls"],
        "gex_puts":      levels["gex_puts"],
    }


@router.get("/chart/{ticker}/order_flow")
def get_order_flow(
    ticker: str,
    min_premium: float = Query(default=25000, description="Minimum premium in USD"),
    side: str = Query(default="", description="CALL or PUT (empty = both)"),
    limit: int = Query(default=25, description="Max rows to return"),
):
    """
    Return live options order flow for a ticker from the QuantData API.
    Used by the Trade tab order flow card.
    Requires QuantData credentials in Settings > Security.
    """
    ticker = ticker.upper()

    if not config_store.cfg("security.use_quantdata", True):
        return {"ticker": ticker, "enabled": False, "flow": [], "message": "QuantData disabled in Settings > Security"}

    if not _qd_available():
        return {
            "ticker":  ticker,
            "enabled": True,
            "flow":    [],
            "message": "QuantData credentials not configured — add quantdata_auth_token and quantdata_instance_id in Settings > Security",
        }

    session_date = date.today().isoformat()
    params: dict = {"ticker": ticker, "sessionDate": session_date, "limit": limit}
    if min_premium:
        params["minPremium"] = min_premium
    if side:
        params["side"] = side.upper()

    data = _qd_get("tool/OPTIONS_ORDER_FLOW_CONSOLIDATED_TABLE", params=params)
    if data is None:
        return {"ticker": ticker, "enabled": True, "flow": [], "message": "QuantData API unavailable — try again shortly"}

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

    return {
        "ticker":       ticker,
        "enabled":      True,
        "session_date": session_date,
        "flow":         flow,
        "source":       "quantdata_live_api",
    }
