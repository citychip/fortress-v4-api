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
            if resp.status_code in (400, 401, 403):
                logger.warning("QuantData returned %s — invalid endpoint or expired credentials", resp.status_code)
                return None  # do NOT retry on 4xx
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


# Widget UUIDs for chart overlay data — same as market_intelligence.py
# These are the correct REST endpoints. The deprecated /api/tool/* path causes 400 errors.
_CHART_WIDGETS: dict[str, dict] = {
    "SPY": {
        "dp":      "0001c185-460d-43e5-b9e9-b1ede7943f6b",
        "gex":     "2e4d7ea4-ae92-4209-bca4-ccb2908ec9f6",
        "page_id": "e22a6d88-9d75-42b3-af9d-ee583008fdad",
    },
    "NVDA": {
        "dp":      "7b2707f2-527b-484b-ab45-b6aa4df9dbc8",
        "gex":     "0dda93ba-d196-48bc-bacc-4b788f23369e",
        "page_id": "52ca72cb-7456-4d64-8cc4-7c25265b0bb9",
    },
    "_SYSTEM": {
        "dp":         "a2c2f3f9-0c34-486d-a25a-9b98b82b49c9",
        "gex":        "465c0bd0-149a-4fb9-8274-9f429ccecb29",
        "page_id":    "e07c6cba-335b-42dc-942b-0f90a5144b4a",
        "dp_page_id": "12f5f34d-6968-4eca-a687-d14566d2235f",
    },
}

def _chart_session(page_id: str) -> req_lib.Session:
    """Build a QuantData requests.Session for chart overlay fetches."""
    auth = config_store.cfg("security.quantdata_auth_token", "")
    inst = config_store.cfg("security.quantdata_instance_id", "")
    sess = req_lib.Session()
    sess.headers.update({
        "accept":        "application/json",
        "authorization": auth,
        "x-instance-id": page_id,
        "x-qd-version":  "1",
        "origin":        "https://v3.quantdata.us",
    })
    return sess

def _chart_set_filter(sess: req_lib.Session, ticker: str, session_date: str) -> None:
    """Set QuantData global filter for the given ticker and date."""
    user_id = config_store.cfg("security.quantdata_instance_id", "")
    if not user_id:
        return
    now_ms = int(time.time() * 1000)
    try:
        sess.put(
            f"{_QD_BASE}/user/attributes",
            timeout=8,
            json={
                "id": user_id,
                "fontSizePercentage": 100,
                "globalFilter": {
                    "expirationDate": {"filterOperationType": "EQUALS", "value": session_date},
                    "sessionDate":    {"filterOperationType": "EQUALS", "value": session_date},
                    "ticker":         {"filterOperationType": "EQUALS", "value": [ticker]},
                },
                "globalTickerConfiguration": {"defaultTicker": ticker, "favoriteTickers": []},
                "globalToolConfiguration": {
                    "hideAxisTitles": False, "hideCrosshairs": False,
                    "hideDataZoomSliders": False, "hideLegends": False,
                    "hideStatusIndicators": False, "hideTimeSliders": False,
                    "hideTitles": False, "hideTooltips": False,
                },
                "notificationConfiguration": {"positionType": "BOTTOM_LEFT", "stacked": False},
                "timeZoneType": "AMERICA_NEW_YORK",
                "createdTime": now_ms, "lastUpdatedTime": now_ms,
            },
        )
    except Exception as e:
        logger.debug("chart: failed to set QD global filter: %s", e)

def _fetch_dp_levels_live(ticker: str) -> dict | None:
    """
    Fetch Dark Pool floors and GEX walls from the live QuantData API.
    Uses the correct widget-UUID REST endpoints — NOT the deprecated /api/tool/* path.
    Returns {"dp_floors": [...], "gex_calls": [...], "gex_puts": [...], "source": "live"}
    or None if the API call fails.
    """
    session_date = date.today().isoformat()
    widgets  = _CHART_WIDGETS.get(ticker, _CHART_WIDGETS["_SYSTEM"])
    is_sys   = ticker not in _CHART_WIDGETS
    page_id  = widgets["page_id"]
    sess     = _chart_session(page_id)

    if is_sys:
        _chart_set_filter(sess, ticker, session_date)

    dp_floors: list[float] = []
    gex_calls: list[float] = []
    gex_puts:  list[float] = []

    # ── Dark Pool levels ──────────────────────────────────────────────────────
    dp_widget = widgets.get("dp")
    if dp_widget:
        dp_page = widgets.get("dp_page_id", page_id)
        dp_sess = _chart_session(dp_page) if dp_page != page_id else sess
        if dp_page != page_id and is_sys:
            _chart_set_filter(dp_sess, ticker, session_date)
        try:
            r = dp_sess.get(f"{_QD_BASE}/equities/dark-pool/levels/{dp_widget}", timeout=15)
            if r.status_code in (400, 401, 403):
                logger.warning("QuantData DP levels returned %s for %s — credentials may be expired", r.status_code, ticker)
                return None
            if r.status_code == 200:
                resp    = r.json().get("response", {})
                dp_map  = resp.get("priceInCentsToDarkPoolLevelDataSumModelMap", {})
                for k, v in dp_map.items():
                    notional = v.get("notionalValueInCentsSum", 0) / 100_000_000
                    if notional >= 50:
                        try:
                            dp_floors.append(round(int(k) / 100, 2))
                        except (TypeError, ValueError):
                            pass
        except Exception as e:
            logger.debug("chart: DP levels fetch failed for %s: %s", ticker, e)

    # ── GEX walls ─────────────────────────────────────────────────────────────
    gex_widget = widgets.get("gex")
    if gex_widget:
        try:
            r = sess.get(f"{_QD_BASE}/options/exposure/strike/{gex_widget}", timeout=20)
            if r.status_code in (400, 401, 403):
                logger.warning("QuantData GEX returned %s for %s — credentials may be expired", r.status_code, ticker)
                return None
            if r.status_code == 200:
                resp    = r.json().get("response", {})
                exp_map = resp.get("expirationDateToStrikePriceInCentsToContractExposureMap", {})
                net_gex: dict[float, float] = {}
                for expiry, strike_data in exp_map.items():
                    for strike_cents, sides in strike_data.items():
                        price    = int(strike_cents) / 100
                        call_gex = sides.get("CALL", 0) or 0
                        put_gex  = sides.get("PUT", 0)  or 0
                        net_gex[price] = net_gex.get(price, 0) + call_gex + put_gex
                gex_calls = sorted(
                    [round(p, 2) for p, g in net_gex.items() if g > 0],
                    key=lambda p: net_gex[p], reverse=True
                )[:5]
                gex_puts = sorted(
                    [round(p, 2) for p, g in net_gex.items() if g < 0],
                    key=lambda p: net_gex[p]
                )[:5]
        except Exception as e:
            logger.debug("chart: GEX fetch failed for %s: %s", ticker, e)

    if not dp_floors and not gex_calls and not gex_puts:
        return None

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

# yfinance-native intervals we can pass straight through
_YF_NATIVE_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m",
                        "1h", "1d", "5d", "1wk", "1mo", "3mo"}
# intraday intervals — yfinance caps their lookback (~730d for 1h)
_INTRADAY = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}


def _fetch_ohlcv(ticker: str, period: str = "3mo", interval: str = "1d") -> list[dict]:
    """
    Fetch OHLCV data from yfinance and return as a list of dicts
    compatible with TradingView Lightweight Charts CandlestickSeries.

    Sprint 22.5 — multi-timeframe support:
      • ``1mo`` (monthly) is a native yfinance interval — passed straight through.
      • ``4h`` is NOT a native yfinance interval, so it is fetched as ``1h`` and
        resampled to 4-hour bars (OHLC = first/max/min/last, volume summed).
      • Intraday intervals have their lookback clamped so a long ``period`` (1y+)
        doesn't blow past yfinance's ~730d intraday cap and return empty.
    Unknown intervals fall back to daily rather than erroring.
    """
    try:
        base_interval = interval
        resample_rule = None
        if interval in ("4h", "240m"):
            base_interval, resample_rule = "1h", "4h"
        elif interval not in _YF_NATIVE_INTERVALS:
            base_interval = {"1hr": "1h", "60min": "60m"}.get(interval, "1d")

        # yfinance rejects >~730d of intraday data — clamp the lookback.
        if base_interval in _INTRADAY and period in ("1y", "2y", "5y", "10y", "ytd", "max"):
            period = "180d"

        df = yf.download(ticker, period=period, interval=base_interval,
                         progress=False, auto_adjust=True)
        if df.empty:
            return []
        # Flatten MultiIndex columns: ('Open', 'MSFT') -> 'Open'
        if hasattr(df.columns, "levels"):
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

        # Resample 1h → 4h when requested.
        if resample_rule:
            agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
            if "Volume" in df.columns:
                agg["Volume"] = "sum"
            df = df.resample(resample_rule).agg(agg).dropna(subset=["Open", "High", "Low", "Close"])

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
    period: str = Query(default="3mo", description="yfinance period: 1mo, 3mo, 6mo, 1y, 2y, 5y, max"),
    interval: str = Query(default="1d", description="interval: 4h, 1h, 1d, 1wk, 1mo (Sprint 22.5 — 4h is resampled from 1h; intraday lookback is clamped)"),
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

    # Use the correct QuantData order flow REST endpoint
    # The /api/tool/* path is deprecated and causes 400 errors
    try:
        _qd_base_url = "https://core-lb-prod.quantdata.us/api"
        _auth  = config_store.cfg("security.quantdata_auth_token", "")
        _inst  = config_store.cfg("security.quantdata_instance_id", "")
        _hdrs  = {
            "accept": "application/json",
            "authorization": _auth,
            "x-instance-id": _inst,
            "x-qd-version": "1",
            "origin": "https://v3.quantdata.us",
        }
        _r = req_lib.get(
            f"{_qd_base_url}/options/order-flow/consolidated",
            headers=_hdrs,
            params=params,
            timeout=15,
        )
        if _r.status_code in (400, 401, 403):
            logger.warning("QuantData order flow returned %s for %s — credentials may be expired", _r.status_code, ticker)
            return {"ticker": ticker, "enabled": True, "flow": [], "message": f"QuantData returned {_r.status_code} — credentials may be expired"}
        _r.raise_for_status()
        data = _r.json()
    except Exception as _exc:
        logger.debug("Order flow fetch failed for %s: %s", ticker, _exc)
        data = None
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
