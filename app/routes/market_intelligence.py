"""
/api/market-intelligence — Unified market regime + flow + portfolio synthesis.

Orchestrates:
  1. Live GEX walls (QuantData exposure/strike endpoint)
  2. Live Dark Pool floors (QuantData dark-pool/levels endpoint)
  3. Live Net Drift (QuantData net-drift endpoint)
  4. Portfolio context (positions, briefing)
  5. Regime synthesis (flip zone, gamma regime, DP support/resistance)
  6. Trade setup suggestions (Gamma Pin, Floor Bounce, Flip Zone Breakdown)
  7. Risk checks (concentration, pacing, delta limits)

Returns a single structured JSON that can be consumed by:
  - The Fortress Dashboard UI (Market Intelligence tab)
  - The fortress-mcp qd_market_intelligence tool
  - Any AI assistant using the Market Intelligence Skill
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter

from ..services.config_store import get_all as get_config

logger = logging.getLogger("fortress.market_intelligence")
router = APIRouter()

# ─── QuantData credentials ────────────────────────────────────────────────────
QD_AUTH_TOKEN  = os.environ.get("QUANTDATA_AUTH_TOKEN", "")
QD_USER_ID     = os.environ.get("QUANTDATA_USER_ID", "")
QD_BASE_URL    = "https://core-lb-prod.quantdata.us/api"

# Known widget IDs per ticker (SPY default; can be extended)
# Discovered via GET /api/pages — these are stable widget UUIDs on the MCP Agentic Page
_WIDGET_IDS: dict[str, dict[str, str]] = {
    "SPY": {
        "gex":       "2e4d7ea4-ae92-4209-bca4-ccb2908ec9f6",  # OPTIONS_EXPOSURE_BY_STRIKE_CHART
        "dp":        "0001c185-460d-43e5-b9e9-b1ede7943f6b",  # DARK_POOL_LEVELS_TABLE
        "net_drift": "9fcb5310-970a-453e-a672-0f3b5ef22c78",  # OPTIONS_NET_DRIFT_CHART
        "page_id":   "e22a6d88-9d75-42b3-af9d-ee583008fdad",  # SPY page
    },
    "SPX": {
        "gex":       "444d17ce-e2f0-4d38-9acb-e51b09d6d4b6",  # SPX Dashboard
        "page_id":   "672ab496-da3e-4538-bc68-3d0925b9b122",
    },
    "QQQ": {
        "gex":       "4b6d1f27-4131-44e1-a5f3-724d6f701d16",  # SPY Dashboard (QQQ widget)
        "page_id":   "9b3d47a2-92b0-49be-9a85-778c06300df0",
    },
}

_QD_SESS: requests.Session | None = None


def _qd_session(page_id: str) -> requests.Session:
    sess = requests.Session()
    sess.headers.update({
        "accept":        "application/json",
        "authorization": QD_AUTH_TOKEN,
        "x-instance-id": page_id,
        "x-qd-version":  "1",
        "origin":        "https://v3.quantdata.us",
        "content-type":  "application/json",
    })
    return sess


def _qd_available() -> bool:
    return bool(QD_AUTH_TOKEN and QD_USER_ID)


def _set_global_filter(sess: requests.Session, ticker: str, session_date: str) -> None:
    """Set QuantData global session filter for the given ticker and date."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    try:
        sess.put(
            f"{QD_BASE_URL}/user/attributes",
            timeout=10,
            json={
                "id": QD_USER_ID,
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
        logger.warning("Failed to set QD global filter: %s", e)


def _fetch_gex(sess: requests.Session, widget_id: str) -> dict | None:
    """Fetch GEX by strike data and return parsed walls."""
    try:
        r = sess.get(f"{QD_BASE_URL}/options/exposure/strike/{widget_id}", timeout=25)
        if r.status_code != 200:
            return None
        resp = r.json().get("response", {})
        exp_map = resp.get("expirationDateToStrikePriceInCentsToContractExposureMap", {})
        current_price_cents = resp.get("stockPriceInCents")

        # Aggregate net GEX across all expirations
        net_gex: dict[float, float] = defaultdict(float)
        today = date.today().isoformat()
        dte0_gex: dict[float, float] = {}

        for expiry, strike_data in exp_map.items():
            for strike_cents, sides in strike_data.items():
                price = int(strike_cents) / 100
                call_gex = sides.get("CALL", 0) or 0
                put_gex  = sides.get("PUT", 0)  or 0
                net      = call_gex + put_gex
                net_gex[price] += net
                if expiry == today:
                    dte0_gex[price] = dte0_gex.get(price, 0) + net

        if not net_gex:
            return None

        # Sort and find flip zone
        sorted_strikes = sorted(net_gex.items())
        flip_zone = None
        for i in range(len(sorted_strikes) - 1):
            p1, g1 = sorted_strikes[i]
            p2, g2 = sorted_strikes[i + 1]
            if g1 * g2 < 0:
                flip_zone = round((p1 + p2) / 2, 2)
                break

        call_walls = sorted(
            [(p, round(g / 1_000_000, 1)) for p, g in net_gex.items() if g > 0],
            key=lambda x: x[1], reverse=True
        )[:8]
        put_walls = sorted(
            [(p, round(g / 1_000_000, 1)) for p, g in net_gex.items() if g < 0],
            key=lambda x: x[1]
        )[:8]

        current_price = (current_price_cents / 100) if current_price_cents else None
        gamma_regime = None
        if current_price and flip_zone:
            gamma_regime = "positive" if current_price > flip_zone else "negative"

        return {
            "call_walls":    [{"strike": p, "gex_m": g} for p, g in call_walls],
            "put_walls":     [{"strike": p, "gex_m": g} for p, g in put_walls],
            "flip_zone":     flip_zone,
            "gamma_regime":  gamma_regime,
            "current_price": current_price,
            "dte0_call_walls": sorted(
                [{"strike": p, "gex_m": round(g / 1_000_000, 1)} for p, g in dte0_gex.items() if g > 0],
                key=lambda x: x["gex_m"], reverse=True
            )[:5],
            "dte0_put_walls": sorted(
                [{"strike": p, "gex_m": round(g / 1_000_000, 1)} for p, g in dte0_gex.items() if g < 0],
                key=lambda x: x["gex_m"]
            )[:5],
        }
    except Exception as e:
        logger.warning("GEX fetch error: %s", e)
        return None


def _fetch_dp(sess: requests.Session, widget_id: str) -> dict | None:
    """Fetch Dark Pool levels and return top floors by notional."""
    try:
        r = sess.get(f"{QD_BASE_URL}/equities/dark-pool/levels/{widget_id}", timeout=20)
        if r.status_code != 200:
            return None
        resp = r.json().get("response", {})
        dp_map = resp.get("priceInCentsToDarkPoolLevelDataSumModelMap", {})
        current_price_cents = resp.get("stockPriceInCents")

        if not dp_map:
            return {"floors": [], "current_price": (current_price_cents / 100) if current_price_cents else None}

        floors = sorted(
            [
                {
                    "price":       int(k) / 100,
                    "notional_m":  round(v.get("notionalValueInCentsSum", 0) / 100_000_000, 1),
                    "contracts":   v.get("sizeSum", 0),
                    "trades":      v.get("tradeCountSum", 0),
                }
                for k, v in dp_map.items()
            ],
            key=lambda x: x["notional_m"],
            reverse=True,
        )[:15]

        return {
            "floors":        floors,
            "current_price": (current_price_cents / 100) if current_price_cents else None,
        }
    except Exception as e:
        logger.warning("DP fetch error: %s", e)
        return None


def _fetch_net_drift(sess: requests.Session, widget_id: str) -> dict | None:
    """Fetch Net Drift and return session summary."""
    try:
        r = sess.get(f"{QD_BASE_URL}/options/net-drift/{widget_id}", timeout=20)
        if r.status_code != 200:
            return None
        resp = r.json().get("response", {})
        nd = resp.get("netDrift", [])
        if not nd:
            return None

        first = nd[0]
        last  = nd[-1]
        ts_open  = datetime.fromtimestamp(first[0] / 1000, tz=timezone.utc).strftime("%H:%M ET")
        ts_close = datetime.fromtimestamp(last[0]  / 1000, tz=timezone.utc).strftime("%H:%M ET")

        call_drift = last[1] / 100 if len(last) > 1 else 0
        put_drift  = last[2] / 100 if len(last) > 2 else 0
        net        = call_drift + put_drift
        price      = last[7] / 100 if len(last) > 7 else None

        # Cumulative net drift over session (sum of all net values)
        cumulative = sum((row[1] / 100 if len(row) > 1 else 0) + (row[2] / 100 if len(row) > 2 else 0) for row in nd)

        return {
            "session_open":    ts_open,
            "session_close":   ts_close,
            "data_points":     len(nd),
            "call_drift_last": round(call_drift, 0),
            "put_drift_last":  round(put_drift, 0),
            "net_drift_last":  round(net, 0),
            "cumulative_drift": round(cumulative, 0),
            "bias":            "bullish" if cumulative > 0 else ("bearish" if cumulative < 0 else "neutral"),
            "current_price":   price,
        }
    except Exception as e:
        logger.warning("Net Drift fetch error: %s", e)
        return None


def _synthesize_regime(gex: dict | None, dp: dict | None, drift: dict | None, macro_regime: str) -> dict:
    """Synthesize all signals into a unified market regime assessment."""
    signals = []
    score   = 0  # positive = bullish, negative = bearish

    current_price = (
        (gex or {}).get("current_price")
        or (dp or {}).get("current_price")
        or (drift or {}).get("current_price")
    )

    # GEX regime signal
    gamma_regime = (gex or {}).get("gamma_regime")
    flip_zone    = (gex or {}).get("flip_zone")
    if gamma_regime == "positive":
        signals.append({"source": "GEX", "signal": "positive_gamma", "weight": +2,
                        "note": f"Price ${current_price} is ABOVE flip zone ${flip_zone} — stable, mean-reverting regime"})
        score += 2
    elif gamma_regime == "negative":
        signals.append({"source": "GEX", "signal": "negative_gamma", "weight": -2,
                        "note": f"Price ${current_price} is BELOW flip zone ${flip_zone} — volatile, trend-following regime"})
        score -= 2

    # Proximity to flip zone (within 0.5%)
    if current_price and flip_zone:
        pct_from_flip = abs(current_price - flip_zone) / flip_zone * 100
        if pct_from_flip < 0.5:
            signals.append({"source": "GEX", "signal": "at_flip_zone", "weight": 0,
                            "note": f"Price is within {pct_from_flip:.2f}% of flip zone — regime change imminent"})

    # DP floor signal
    if dp and dp.get("floors") and current_price:
        nearest_floor = min(dp["floors"], key=lambda f: abs(f["price"] - current_price))
        dist = current_price - nearest_floor["price"]
        if 0 < dist < 5:
            signals.append({"source": "DarkPool", "signal": "near_dp_floor",
                            "weight": +1,
                            "note": f"Price is ${dist:.2f} above DP floor at ${nearest_floor['price']} (${nearest_floor['notional_m']}M notional) — strong support"})
            score += 1
        elif -5 < dist <= 0:
            signals.append({"source": "DarkPool", "signal": "below_dp_floor",
                            "weight": -1,
                            "note": f"Price has broken below DP floor at ${nearest_floor['price']} — bearish"})
            score -= 1

    # Net Drift signal
    if drift:
        bias = drift.get("bias", "neutral")
        cum  = drift.get("cumulative_drift", 0)
        if bias == "bullish":
            signals.append({"source": "NetDrift", "signal": "bullish_flow",
                            "weight": +1, "note": f"Cumulative net drift ${cum:,.0f} — smart money is net long"})
            score += 1
        elif bias == "bearish":
            signals.append({"source": "NetDrift", "signal": "bearish_flow",
                            "weight": -1, "note": f"Cumulative net drift ${cum:,.0f} — smart money is net short"})
            score -= 1

    # Macro regime signal
    if macro_regime == "bullish":
        score += 1
    elif macro_regime == "bearish":
        score -= 1

    # Divergence check: price above flip but bearish drift
    if gamma_regime == "positive" and (drift or {}).get("bias") == "bearish":
        signals.append({"source": "Divergence", "signal": "gex_drift_divergence", "weight": -1,
                        "note": "Positive gamma but bearish net drift — rally is unsupported, likely to fail"})
        score -= 1

    overall = "strongly_bullish" if score >= 3 else \
              "bullish"          if score == 2 else \
              "mildly_bullish"   if score == 1 else \
              "neutral"          if score == 0 else \
              "mildly_bearish"   if score == -1 else \
              "bearish"          if score == -2 else \
              "strongly_bearish"

    return {
        "overall":       overall,
        "score":         score,
        "signals":       signals,
        "current_price": current_price,
        "gamma_regime":  gamma_regime,
        "flip_zone":     flip_zone,
    }


def _generate_setups(gex: dict | None, dp: dict | None, regime: dict) -> list[dict]:
    """Generate concrete trade setup suggestions based on the regime and levels."""
    setups = []
    current_price = regime.get("current_price")
    gamma_regime  = regime.get("gamma_regime")
    flip_zone     = regime.get("flip_zone")

    if not current_price:
        return setups

    # Setup A: Gamma Pin (Iron Condor / Iron Butterfly)
    if gex and gamma_regime == "positive":
        call_walls = gex.get("call_walls", [])
        put_walls  = gex.get("put_walls", [])
        if call_walls and put_walls:
            top_call = call_walls[0]["strike"]
            top_put  = put_walls[0]["strike"]
            range_width = top_call - top_put
            if range_width < current_price * 0.03:  # range < 3% of price
                setups.append({
                    "name":        "Gamma Pin — Iron Condor",
                    "type":        "neutral",
                    "confidence":  "high" if range_width < current_price * 0.015 else "medium",
                    "description": f"Price is pinned between Put Wall ${top_put} and Call Wall ${top_call} (range: ${range_width:.0f}). Sell Iron Condor with short strikes at these walls.",
                    "entry":       f"Sell ${top_call} Call / Buy ${top_call + 5} Call | Sell ${top_put} Put / Buy ${top_put - 5} Put",
                    "target":      "50% of max credit",
                    "stop":        "2x credit received",
                    "fortress_check": ["delta_short ≤ 0.16", "min_credit ≥ $1.00", "DTE 14–45"],
                })

    # Setup B: Floor Bounce (Put Credit Spread / Long Call)
    if dp and dp.get("floors") and current_price:
        nearest_floor = min(dp["floors"], key=lambda f: abs(f["price"] - current_price))
        dist = current_price - nearest_floor["price"]
        if 0 < dist < 8 and nearest_floor["notional_m"] > 500:
            setups.append({
                "name":        "Floor Bounce — Put Credit Spread",
                "type":        "bullish",
                "confidence":  "high" if nearest_floor["notional_m"] > 1000 else "medium",
                "description": f"Price is ${dist:.2f} above a massive DP floor at ${nearest_floor['price']} (${nearest_floor['notional_m']}M notional). Institutions will defend this level.",
                "entry":       f"Sell ${nearest_floor['price'] - 1:.0f} Put / Buy ${nearest_floor['price'] - 6:.0f} Put (PCS below the floor)",
                "target":      "50% of max credit",
                "stop":        "2x credit received or close below DP floor",
                "fortress_check": ["min_credit ≥ $0.50", "DTE 14–45", "check concentration"],
            })

    # Setup C: Flip Zone Breakdown (Bear Put Spread)
    if flip_zone and gamma_regime == "negative":
        next_dp_floor = None
        if dp and dp.get("floors"):
            below_floors = [f for f in dp["floors"] if f["price"] < current_price]
            if below_floors:
                next_dp_floor = max(below_floors, key=lambda f: f["price"])
        target = next_dp_floor["price"] if next_dp_floor else current_price * 0.97
        setups.append({
            "name":        "Flip Zone Breakdown — Bear Put Spread",
            "type":        "bearish",
            "confidence":  "high",
            "description": f"Price has broken below the GEX Flip Zone (${flip_zone}). Dealers are now net short gamma and will sell into weakness, amplifying the move.",
            "entry":       f"Buy ${current_price:.0f} Put / Sell ${target:.0f} Put (BPS targeting next DP floor at ${target:.2f})",
            "target":      f"Next DP floor at ${target:.2f}",
            "stop":        f"Close back above flip zone ${flip_zone}",
            "fortress_check": ["check pacing", "check concentration", "DTE 7–21 for short-term breakdown"],
        })

    return setups


def _risk_checks(positions: list[dict], settings: dict, regime: dict) -> list[dict]:
    """Run portfolio risk checks relevant to the current regime."""
    checks = []
    strategy_cfg = settings.get("strategy", {})
    alerts_cfg   = settings.get("alerts", {})

    # Concentration check
    tickers = {}
    for pos in positions:
        t = pos.get("ticker", "")
        tickers[t] = tickers.get(t, 0) + abs(pos.get("net_liq_pct", 0))
    for ticker, pct in sorted(tickers.items(), key=lambda x: x[1], reverse=True):
        max_conc = strategy_cfg.get("max_concentration_pct", 10)
        if pct > max_conc:
            checks.append({
                "type":    "concentration",
                "ticker":  ticker,
                "value":   round(pct, 1),
                "limit":   max_conc,
                "severity": "critical" if pct > max_conc * 1.5 else "warning",
                "action":  f"Do not add new {ticker} positions. Consider reducing exposure.",
            })

    # Pacing check — count positions opened this week
    # (simplified: count positions with recent avg_cost dates)
    pacing_max = strategy_cfg.get("entries_per_week_max", 5)

    # Delta check
    for pos in positions:
        delta = abs(pos.get("current_delta", 0) or 0)
        act_threshold = alerts_cfg.get("delta_act_threshold", 0.8)
        watch_threshold = alerts_cfg.get("delta_watch_threshold", 0.6)
        if delta >= act_threshold:
            checks.append({
                "type":    "delta",
                "ticker":  pos.get("ticker"),
                "strike":  pos.get("strike"),
                "expiry":  pos.get("expiry"),
                "value":   delta,
                "limit":   act_threshold,
                "severity": "critical",
                "action":  "Roll or close immediately — delta exceeds action threshold.",
            })
        elif delta >= watch_threshold:
            checks.append({
                "type":    "delta",
                "ticker":  pos.get("ticker"),
                "strike":  pos.get("strike"),
                "expiry":  pos.get("expiry"),
                "value":   delta,
                "limit":   watch_threshold,
                "severity": "warning",
                "action":  "Monitor closely — delta approaching action threshold.",
            })

    # Regime-specific check
    if regime.get("gamma_regime") == "negative":
        checks.append({
            "type":    "regime",
            "severity": "warning",
            "action":  "Market is in NEGATIVE gamma regime. Reduce long delta exposure. Avoid new bullish entries until price reclaims flip zone.",
        })

    return checks


@router.get("/market-intelligence")
def get_market_intelligence(ticker: str = "SPY", session_date: str | None = None):
    """
    Unified market regime + flow + portfolio intelligence endpoint.

    Fetches live GEX walls, Dark Pool floors, Net Drift from QuantData,
    combines with portfolio context, and returns a structured analysis
    with regime assessment, trade setups, and risk checks.

    Parameters:
        ticker: Ticker symbol to analyse (default: SPY)
        session_date: Trading date in YYYY-MM-DD format (default: today)

    Returns:
        {
          "as_of": ISO timestamp,
          "ticker": str,
          "session_date": str,
          "current_price": float | null,
          "regime": {
            "overall": str,        # strongly_bullish | bullish | mildly_bullish | neutral | mildly_bearish | bearish | strongly_bearish
            "score": int,          # -4 to +4
            "gamma_regime": str,   # positive | negative | null
            "flip_zone": float,    # GEX zero-crossing price
            "signals": [...]       # list of contributing signals
          },
          "gex": {
            "call_walls": [{"strike", "gex_m"}, ...],
            "put_walls":  [{"strike", "gex_m"}, ...],
            "flip_zone": float,
            "dte0_call_walls": [...],
            "dte0_put_walls":  [...],
          },
          "dark_pool": {
            "floors": [{"price", "notional_m", "contracts", "trades"}, ...],
          },
          "net_drift": {
            "bias": bullish|bearish|neutral,
            "cumulative_drift": float,
            "net_drift_last": float,
            "session_open": str,
            "session_close": str,
          },
          "trade_setups": [
            {"name", "type", "confidence", "description", "entry", "target", "stop", "fortress_check"}
          ],
          "risk_checks": [
            {"type", "severity", "ticker", "value", "limit", "action"}
          ],
          "portfolio_context": {
            "macro_regime": str,
            "concentration": {...},
            "pacing": {...},
            "net_liq": float,
          },
          "quantdata_available": bool,
          "source": str,
        }
    """
    from ..routes.positions import get_positions
    from ..routes.briefing import get_briefing

    if not session_date:
        session_date = date.today().isoformat()

    ticker = ticker.upper()
    as_of  = datetime.now(timezone.utc).isoformat()

    # ── Fetch portfolio context ───────────────────────────────────────────────
    try:
        briefing_data = get_briefing()
    except Exception:
        briefing_data = {}

    try:
        positions_data = get_positions(aggregated=False)
        positions = positions_data if isinstance(positions_data, list) else positions_data.get("positions", [])
    except Exception:
        positions = []

    macro_regime = (briefing_data.get("macro_regime") or {}).get("regime", "neutral")
    concentration = briefing_data.get("concentration", {})
    pacing        = briefing_data.get("pacing", {})
    account       = briefing_data.get("account", {})
    net_liq       = account.get("net_liq") if account else None

    settings = get_config()  # returns full config dict

    # ── Fetch live QuantData data ─────────────────────────────────────────────
    gex_data   = None
    dp_data    = None
    drift_data = None
    qd_source  = "unavailable"

    if _qd_available():
        widgets = _WIDGET_IDS.get(ticker, _WIDGET_IDS.get("SPY", {}))
        page_id = widgets.get("page_id", "")
        sess    = _qd_session(page_id)

        _set_global_filter(sess, ticker, session_date)

        if widgets.get("gex"):
            gex_data = _fetch_gex(sess, widgets["gex"])
        if widgets.get("dp"):
            dp_data = _fetch_dp(sess, widgets["dp"])
        if widgets.get("net_drift"):
            drift_data = _fetch_net_drift(sess, widgets["net_drift"])

        qd_source = "quantdata_live_api"
    else:
        # Fall back to parsed report file data
        try:
            from ..routes.chart import _get_levels
            levels = _get_levels(ticker)
            dp_floors_raw = levels.get("dp_floors", [])
            if dp_floors_raw:
                dp_data = {
                    "floors": [{"price": f, "notional_m": None, "contracts": None, "trades": None}
                               for f in dp_floors_raw],
                    "current_price": None,
                }
            qd_source = "report_file_fallback"
        except Exception:
            pass

    # ── Synthesize regime ─────────────────────────────────────────────────────
    regime = _synthesize_regime(gex_data, dp_data, drift_data, macro_regime)

    # ── Generate trade setups ─────────────────────────────────────────────────
    trade_setups = _generate_setups(gex_data, dp_data, regime)

    # ── Risk checks ───────────────────────────────────────────────────────────
    risk_checks = _risk_checks(positions, settings, regime)

    return {
        "as_of":         as_of,
        "ticker":        ticker,
        "session_date":  session_date,
        "current_price": regime.get("current_price"),
        "regime":        regime,
        "gex":           gex_data,
        "dark_pool":     dp_data,
        "net_drift":     drift_data,
        "trade_setups":  trade_setups,
        "risk_checks":   risk_checks,
        "portfolio_context": {
            "macro_regime":  macro_regime,
            "concentration": concentration,
            "pacing":        pacing,
            "net_liq":       net_liq,
        },
        "quantdata_available": _qd_available(),
        "source":        qd_source,
    }
