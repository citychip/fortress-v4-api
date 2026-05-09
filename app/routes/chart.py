"""
Fortress Dashboard — Chart data route.
Serves OHLCV candlestick data and Dark Pool / GEX overlay levels for a given ticker.
Used by the TradingView Lightweight Charts component in the Manage tab.
"""
from __future__ import annotations
import re
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
import yfinance as yf
from app.services import config_store

logger = logging.getLogger("fortress.chart")
router = APIRouter(tags=["chart"])

# ── helpers ──────────────────────────────────────────────────────────────────

def _get_data_dir() -> Path:
    import os
    return Path(os.environ.get("FORTRESS_DATA_DIR", Path.home() / ".quantdata-mcp"))


def _parse_dp_levels(ticker: str) -> dict:
    """
    Parse Dark Pool floors and GEX walls for a ticker from the latest QuantData daily report.
    Returns: {"dp_floors": [float, ...], "gex_calls": [float, ...], "gex_puts": [float, ...]}
    """
    data_dir = _get_data_dir()
    # Find the most recent daily report
    reports = sorted(data_dir.glob("QuantData Daily Report*.md"), reverse=True)
    if not reports:
        return {"dp_floors": [], "gex_calls": [], "gex_puts": []}

    text = reports[0].read_text(encoding="utf-8", errors="ignore")

    # Find the section for this ticker
    # Pattern: "### MSFT Execution Profile\n- **Dark Pool Hard Floors:** $389.00 (982.6M), ..."
    section_pattern = rf"### {re.escape(ticker)} Execution Profile(.*?)(?=### \w+ Execution Profile|---|\Z)"
    section_match = re.search(section_pattern, text, re.DOTALL)
    if not section_match:
        return {"dp_floors": [], "gex_calls": [], "gex_puts": []}

    section = section_match.group(1)

    # Extract DP floors: "$389.00 (982.6M), $384.47 (260.5M), ..."
    dp_match = re.search(r"Dark Pool Hard Floors:\*\*\s*(.*)", section)
    dp_floors = []
    if dp_match:
        raw = dp_match.group(1)
        dp_floors = [float(m) for m in re.findall(r"\$(\d+(?:\.\d+)?)", raw)]

    # Extract GEX walls: "Calls at $390, $400, $395 | Puts at $320, $325, $300"
    gex_match = re.search(r"GEX Walls:\*\*\s*Calls at\s*(.*?)\s*\|\s*Puts at\s*(.*?)(?:\n|$)", section)
    gex_calls, gex_puts = [], []
    if gex_match:
        gex_calls = [float(m) for m in re.findall(r"\$(\d+(?:\.\d+)?)", gex_match.group(1))]
        gex_puts  = [float(m) for m in re.findall(r"\$(\d+(?:\.\d+)?)", gex_match.group(2))]

    return {"dp_floors": dp_floors, "gex_calls": gex_calls, "gex_puts": gex_puts}


def _fetch_ohlcv(ticker: str, period: str = "3mo", interval: str = "1d") -> list[dict]:
    """
    Fetch OHLCV data from yfinance and return as a list of dicts
    compatible with TradingView Lightweight Charts CandlestickSeries.
    yfinance >= 0.2 returns a MultiIndex DataFrame with (column, ticker) tuples;
    we flatten it to a simple single-level column frame before iterating.
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
            # TradingView expects Unix timestamp (seconds) or ISO date string
            time_val = int(ts.timestamp()) if hasattr(ts, "timestamp") else str(ts)[:10]
            candles.append({
                "time": time_val,
                "open":  round(float(row["Open"]),  2),
                "high":  round(float(row["High"]),  2),
                "low":   round(float(row["Low"]),   2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if "Volume" in row else 0,
            })
        return candles
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", ticker, exc)
        return []


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/chart/{ticker}")
def get_chart_data(
    ticker: str,
    period: str = Query(default="3mo", description="yfinance period: 1mo, 3mo, 6mo, 1y"),
    interval: str = Query(default="1d", description="yfinance interval: 1d, 1h"),
):
    """
    Return OHLCV candles + Dark Pool floors + GEX walls for a ticker.
    Used by the TradingView Lightweight Charts component.
    """
    ticker = ticker.upper()
    candles = _fetch_ohlcv(ticker, period=period, interval=interval)
    # Only fetch DP/GEX overlays when QuantData is enabled (Settings > Security)
    if config_store.cfg("security.use_quantdata", True):
        levels = _parse_dp_levels(ticker)
    else:
        levels = {"dp_floors": [], "gex_calls": [], "gex_puts": []}

    if not candles:
        raise HTTPException(status_code=404, detail=f"No price data found for {ticker}")

    return {
        "ticker":   ticker,
        "period":   period,
        "interval": interval,
        "candles":  candles,
        "levels": {
            "dp_floors":  levels["dp_floors"],
            "gex_calls":  levels["gex_calls"],
            "gex_puts":   levels["gex_puts"],
        },
    }


@router.get("/chart/{ticker}/levels")
def get_chart_levels(ticker: str):
    """
    Return only the Dark Pool and GEX levels for a ticker (no OHLCV).
    Fast endpoint for refreshing overlays without re-fetching candles.
    """
    ticker = ticker.upper()
    # Only fetch DP/GEX overlays when QuantData is enabled (Settings > Security)
    if config_store.cfg("security.use_quantdata", True):
        levels = _parse_dp_levels(ticker)
    else:
        levels = {"dp_floors": [], "gex_calls": [], "gex_puts": []}
    return {"ticker": ticker, **levels}
