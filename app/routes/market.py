"""
Market analytics endpoints.

GET /api/market/earnings-volatility/{ticker}
    — Implied earnings move vs historical realized moves.
      Useful for deciding whether to enter/exit before earnings.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.services import state

router = APIRouter()
logger = logging.getLogger("fortress.market")


# ---------------------------------------------------------------------------
# /api/market/earnings-volatility/{ticker}
# ---------------------------------------------------------------------------

@router.get("/market/earnings-volatility/{ticker}")
def get_earnings_volatility(ticker: str):
    """
    Implied earnings move vs historical realized moves.

    implied_move_pct  — ATM straddle value / stock price at nearest post-earnings expiry.
                        Uses yfinance option chain; falls back to None if chain unavailable.
    historical_moves  — Last 8 earnings realized absolute % moves from yfinance earnings_dates.
    avg_historical_pct — Mean of historical_moves.
    implied_vs_historical_ratio — implied / avg_historical (>1 = market pricing more vol than history).

    Args:
        ticker: Stock ticker e.g. MSFT
    """
    ticker = ticker.upper()

    try:
        import yfinance as yf
    except ImportError:
        raise HTTPException(status_code=503, detail="yfinance not installed")

    try:
        yf_ticker = yf.Ticker(ticker)

        # ── Stock price ───────────────────────────────────────────────────
        info = yf_ticker.fast_info
        stock_price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
        if stock_price is None:
            hist = yf_ticker.history(period="2d")
            stock_price = float(hist["Close"].iloc[-1]) if not hist.empty else None

        # ── Next earnings date from calendar state ────────────────────────
        next_earnings_date: Optional[str] = None
        straddle_expiry: Optional[str] = None
        implied_move_pct: Optional[float] = None

        try:
            calendar_data = state.get_earnings_blocklist()
            ticker_entry = calendar_data.get("tickers", {}).get(ticker, {})
            next_earnings_date = ticker_entry.get("next_earnings")
        except Exception:
            pass

        if not next_earnings_date:
            try:
                cal = yf_ticker.calendar
                if cal is not None and not cal.empty:
                    earn_date = cal.iloc[0].get("Earnings Date")
                    if earn_date:
                        next_earnings_date = str(earn_date)[:10]
            except Exception:
                pass

        # ── ATM straddle from option chain ────────────────────────────────
        if stock_price:
            try:
                expiries = yf_ticker.options
                if expiries and next_earnings_date:
                    # Pick the first expiry after earnings date
                    post_earn_expiries = [e for e in expiries if e >= next_earnings_date]
                    target_expiry = post_earn_expiries[0] if post_earn_expiries else expiries[-1]
                elif expiries:
                    target_expiry = expiries[0]
                else:
                    target_expiry = None

                if target_expiry:
                    straddle_expiry = target_expiry
                    chain = yf_ticker.option_chain(target_expiry)
                    calls = chain.calls
                    puts = chain.puts

                    # ATM = closest strike to current price
                    atm_call = calls.iloc[(calls["strike"] - stock_price).abs().argsort()[:1]]
                    atm_put = puts.iloc[(puts["strike"] - stock_price).abs().argsort()[:1]]

                    call_mid = (atm_call["bid"].values[0] + atm_call["ask"].values[0]) / 2
                    put_mid = (atm_put["bid"].values[0] + atm_put["ask"].values[0]) / 2
                    straddle_val = call_mid + put_mid

                    if straddle_val > 0 and stock_price > 0:
                        implied_move_pct = round(straddle_val / stock_price * 100, 2)
            except Exception as e:
                logger.debug("Straddle calc failed for %s: %s", ticker, e)

        # ── Historical earnings moves from yfinance ───────────────────────
        historical_moves = []
        try:
            earn_df = yf_ticker.earnings_dates
            if earn_df is not None and not earn_df.empty:
                hist_prices = yf_ticker.history(period="2y", interval="1d")

                for earn_dt_idx in earn_df.index[:8]:
                    earn_date_str = str(earn_dt_idx)[:10]
                    try:
                        earn_date = datetime.strptime(earn_date_str, "%Y-%m-%d").date()
                        # Skip future earnings
                        if earn_date >= datetime.now(timezone.utc).date():
                            continue

                        # Find price 1 day before and 1 day after
                        prices_before = hist_prices[hist_prices.index.date < earn_date]  # type: ignore[attr-defined]
                        prices_after = hist_prices[hist_prices.index.date >= earn_date]  # type: ignore[attr-defined]

                        if prices_before.empty or prices_after.empty:
                            continue

                        pre_close = float(prices_before["Close"].iloc[-1])
                        post_open = float(prices_after["Close"].iloc[0])

                        if pre_close > 0:
                            move_pct = (post_open - pre_close) / pre_close * 100
                            historical_moves.append(
                                {
                                    "date": earn_date_str,
                                    "move_pct": round(abs(move_pct), 2),
                                    "direction_pct": round(move_pct, 2),
                                }
                            )
                    except Exception:
                        continue
        except Exception as e:
            logger.debug("Historical moves calc failed for %s: %s", ticker, e)

        avg_historical_pct = (
            round(sum(m["move_pct"] for m in historical_moves) / len(historical_moves), 2)
            if historical_moves
            else None
        )

        implied_vs_historical_ratio: Optional[float] = None
        if implied_move_pct and avg_historical_pct and avg_historical_pct > 0:
            implied_vs_historical_ratio = round(implied_move_pct / avg_historical_pct, 2)

        return {
            "ticker": ticker,
            "implied_move_pct": implied_move_pct,
            "straddle_expiry": straddle_expiry,
            "stock_price": round(float(stock_price), 2) if stock_price else None,
            "next_earnings_date": next_earnings_date,
            "historical_moves": historical_moves,
            "avg_historical_pct": avg_historical_pct,
            "implied_vs_historical_ratio": implied_vs_historical_ratio,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("earnings_volatility failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=f"earnings volatility calculation failed: {e}")
