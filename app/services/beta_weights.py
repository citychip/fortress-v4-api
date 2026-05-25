"""
Beta Weighting Service — Fetch IBKR betas for portfolio tickers.

Primary source: IBKR CP Gateway (/v1/api/fundamentals/{conid})
Fallback: yFinance (delayed, but reliable)

Usage:
    from app.services.beta_weights import fetch_betas_for_portfolio
    betas = fetch_betas_for_portfolio(["MSFT", "AAPL", "SPY"], positions_data)
    # → {"MSFT": {"beta": 1.15, "source": "ibkr"}, ...}
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("fortress.beta_weights")

# In-memory cache: ticker → {beta: float, source: str, ts: float}
_beta_cache: dict[str, dict[str, Any]] = {}
CACHE_TTL_SECONDS = 86400  # 24 hours — betas rarely change


def _get_conid_for_ticker(ticker: str, positions_data: dict) -> int | None:
    """Extract IBKR contract ID (conid) from positions data for a ticker."""
    positions = positions_data.get("positions", []) or []
    for p in positions:
        if p.get("ticker", "").upper() == ticker.upper():
            conid = p.get("conid") or p.get("contract_id")
            if conid:
                return int(conid)
    return None


def _fetch_beta_ibkr(ticker: str, conid: int) -> float | None:
    """Fetch Beta from IBKR CP Gateway."""
    try:
        from app.services.ibkr_web.client import WebApiClient
        from app.services.config_store import cfg

        client = WebApiClient(
            gateway_url=cfg("technical.cp_gateway_url") or "https://localhost:5000",
            verify_ssl=cfg("technical.cp_gateway_verify_ssl") or False,
        )

        response = client.get(f"/fundamentals/{conid}")

        # IBKR returns fundamentals with beta nested in financial data
        beta = None
        if isinstance(response, dict):
            # Try common beta locations in fundamentals response
            beta = (
                response.get("beta")
                or response.get("mktCap", {}).get("beta")
                or response.get("fundamental", {}).get("beta")
                or response.get("financials", {}).get("beta")
            )

        client.close()

        if beta is not None:
            beta = float(beta)
            logger.info(f"Beta for {ticker} from IBKR: {beta}")
            return beta

    except Exception as e:
        logger.warning(f"Failed to fetch beta for {ticker} from IBKR: {e}")

    return None


def _fetch_beta_yfinance(ticker: str) -> float:
    """Fallback: fetch Beta from yFinance (5-year beta vs S&P 500)."""
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info
        beta = info.get("beta")
        if beta is not None:
            beta = float(beta)
            logger.info(f"Beta for {ticker} from yFinance: {beta}")
            return beta
    except Exception as e:
        logger.warning(f"Failed to fetch beta for {ticker} from yFinance: {e}")

    # Default fallback: SPY proxy = 1.0
    return 1.0


def fetch_betas_for_portfolio(
    tickers: list[str],
    positions_data: dict,
) -> dict[str, dict[str, Any]]:
    """
    Fetch betas for all tickers in the portfolio.
    
    Strategy:
    1. Check cache (24h TTL)
    2. Try IBKR CP Gateway (primary)
    3. Fall back to yFinance (delayed but generic)
    
    Returns:
        {
            "MSFT": {"beta": 1.15, "source": "ibkr"},
            "AAPL": {"beta": 1.25, "source": "yfinance"},
            "SPY": {"beta": 1.0, "source": "cache"},
        }
    """
    now = time.time()
    result: dict[str, dict[str, Any]] = {}

    for ticker in tickers:
        t = ticker.upper()

        # Check cache first
        cached = _beta_cache.get(t)
        if cached and (now - cached["ts"]) < CACHE_TTL_SECONDS:
            result[t] = {"beta": cached["beta"], "source": "cache"}
            continue

        # Try IBKR
        conid = _get_conid_for_ticker(ticker, positions_data)
        if conid:
            beta = _fetch_beta_ibkr(ticker, conid)
            if beta is not None:
                _beta_cache[t] = {"beta": beta, "source": "ibkr", "ts": now}
                result[t] = {"beta": beta, "source": "ibkr"}
                continue

        # Fallback to yFinance
        beta = _fetch_beta_yfinance(ticker)
        _beta_cache[t] = {"beta": beta, "source": "yfinance", "ts": now}
        result[t] = {"beta": beta, "source": "yfinance"}

    return result


def clear_beta_cache():
    """Clear the beta cache (useful for testing or manual refresh)."""
    global _beta_cache
    _beta_cache = {}
