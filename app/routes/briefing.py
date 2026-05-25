"""
Briefing endpoint: aggregates the morning briefing view.

Returns: account header + today's actions + macro regime + pacing + concentration
       + portfolio greeks + visual indicator state (VIX, staleness, delta states).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from app.services import state
from app.services import fx
from app.services.config_store import cfg

router = APIRouter()


# ---------------------------------------------------------------------------
# Portfolio Greeks aggregation
# ---------------------------------------------------------------------------

def compute_portfolio_greeks(data: dict) -> dict:
    """
    Aggregate signed portfolio delta (and theta/vega when available) across
    all positions.

    Delta convention used throughout:
      - qty is signed: long = positive, short = negative
      - current_delta is the per-share delta (0 to 1 for calls, -1 to 0 for puts)
      - position_delta = qty * multiplier * current_delta

    For PMCC long LEAP calls (qty > 0, delta ~0.80) this adds positive delta.
    For short calls (qty < 0, delta ~0.30) this subtracts delta.
    Net result is the true directional exposure in dollar-delta terms.
    """
    total_delta = 0.0
    total_theta = 0.0
    total_vega = 0.0
    positions_with_greeks = 0
    positions_total = 0
    pcs_count = 0
    pcs_put_notional = 0.0  # sum of (short_strike * |qty| * multiplier) for PCS short-put legs

    for pos in data.get("positions", []):
        positions_total += 1
        mult_raw = pos.get("multiplier", 100)
        try:
            mult = int(mult_raw) if mult_raw not in ("", None) else 1
        except (ValueError, TypeError):
            mult = 1
        qty = float(pos.get("qty", 0))
        delta = pos.get("current_delta")
        theta = pos.get("current_theta")
        vega = pos.get("current_vega")

        if delta is not None:
            positions_with_greeks += 1
            total_delta += float(delta) * qty * mult

        if theta is not None:
            total_theta += float(theta) * qty * mult

        if vega is not None:
            total_vega += float(vega) * qty * mult

        # PCS exposure — count short-put legs and accumulate notional
        strategy = str(pos.get("strategy") or "").upper()
        if strategy == "PCS":
            leg_role = str(pos.get("leg_role") or pos.get("leg") or "").lower()
            right = str(pos.get("right") or "").upper()
            # Count the short put leg only (avoid double-counting the long put)
            is_short_put = (
                leg_role in ("short", "short_put")
                or (right == "P" and qty < 0)
                or (leg_role == "" and qty < 0)
            )
            if is_short_put:
                pcs_count += 1
                short_strike = pos.get("short_strike") or pos.get("strike")
                if short_strike is not None:
                    try:
                        pcs_put_notional += float(short_strike) * abs(qty) * mult
                    except (ValueError, TypeError):
                        pass

    # Classify net delta exposure
    _long_thresh  = cfg("strategy.delta_bias_long_threshold", 5000.0)
    _short_thresh = cfg("strategy.delta_bias_short_threshold", -5000.0)
    if total_delta > _long_thresh:
        delta_bias = "long"
    elif total_delta < _short_thresh:
        delta_bias = "short"
    else:
        delta_bias = "neutral"

    return {
        "portfolio_delta": round(total_delta, 0),
        "portfolio_theta": round(total_theta, 2),
        "portfolio_vega": round(total_vega, 2),
        "delta_bias": delta_bias,
        "positions_with_greeks": positions_with_greeks,
        "positions_total": positions_total,
        "pcs_count": pcs_count,
        "pcs_put_notional_usd": round(pcs_put_notional, 0),
    }


# ── Beta cache: refresh at most once per hour to avoid fd exhaustion ─────────
import time as _time
_beta_cache: dict = {}          # {ticker -> {beta, price, source}}
_beta_cache_tickers: set = set()
_beta_cache_ts: float = 0.0
_BETA_CACHE_TTL: float = 3600.0  # seconds


def _fetch_betas_and_prices(tickers: list[str]) -> dict:
    """Fetch beta (vs SPY, 1y weekly) and last price from yfinance.
    Results are cached for _BETA_CACHE_TTL seconds to prevent fd exhaustion
    when called repeatedly from the SSE stream.
    """
    global _beta_cache, _beta_cache_tickers, _beta_cache_ts

    now = _time.monotonic()
    ticker_set = set(tickers)
    cache_valid = (
        (now - _beta_cache_ts) < _BETA_CACHE_TTL
        and ticker_set <= _beta_cache_tickers
        and _beta_cache
    )
    if cache_valid:
        return _beta_cache

    result = {}
    fetch_list = list(ticker_set | {"SPY"})
    try:
        import yfinance as yf
        import numpy as np
        raw = yf.download(
            fetch_list,
            period="1y",
            interval="1wk",
            auto_adjust=True,
            progress=False,
        )
        closes = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw
        spy_ret = closes["SPY"].pct_change().dropna() if "SPY" in closes.columns else None

        for t in fetch_list:
            try:
                col = closes[t] if t in closes.columns else None
                if col is None or col.dropna().empty:
                    continue
                price = float(col.dropna().iloc[-1])
                if spy_ret is not None and len(spy_ret) > 10:
                    stock_ret = col.pct_change().dropna()
                    s_r, m_r = stock_ret.align(spy_ret, join="inner")
                    if len(s_r) > 10:
                        cov = float(np.cov(s_r, m_r)[0][1])
                        var = float(np.var(m_r))
                        beta = round(cov / var, 3) if var > 0 else 1.0
                    else:
                        beta = 1.0
                else:
                    beta = 1.0
                result[t] = {"beta": beta, "price": price, "source": "yfinance"}
            except Exception:
                continue
    except Exception:
        pass

    if result:
        _beta_cache = result
        _beta_cache_tickers = set(result.keys())
        _beta_cache_ts = now

    return result


def compute_portfolio_greeks_with_beta(data: dict) -> dict:
    """
    Compute portfolio Greeks with SPY-equivalent beta-weighted delta.
    Betas are cached for 1 hour — safe to call from SSE stream.
    """
    greeks = compute_portfolio_greeks(data)

    try:
        positions = data.get("positions", []) or []
        tickers = list({p.get("ticker", "").upper() for p in positions if p.get("ticker")})
        if tickers:
            betas = _fetch_betas_and_prices(tickers)
            if betas:
                weighted_delta = state.compute_beta_weighted_delta(data, betas)
                greeks["beta_weighted_delta"] = round(weighted_delta, 1)
                greeks["beta_sources"] = "yfinance"
            else:
                greeks["beta_weighted_delta"] = None
                greeks["beta_sources"] = "unavailable"
    except Exception as e:
        import logging
        logging.getLogger("fortress.briefing").warning(f"Beta-weighted delta failed: {e}")
        greeks["beta_weighted_delta"] = None
        greeks["beta_sources"] = "error"

    return greeks


# ---------------------------------------------------------------------------
# Pacing computation
# ---------------------------------------------------------------------------

def compute_pacing(journal: dict) -> dict:
    """Count OPEN actions in the current calendar week (Mon-Sun)."""
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    entries = journal.get("entries", [])
    opens_this_week = []
    for e in entries:
        if e.get("action") != "OPEN":
            continue
        ts = e.get("timestamp", "")
        try:
            entry_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            # Per Strategy §7: rolls and hedges don't count toward pacing
            rules = e.get("framework_rules", [])
            is_roll = any("roll" in r.lower() for r in rules)
            is_hedge = any("hedge" in r.lower() for r in rules)
            if entry_dt >= monday and not (is_roll or is_hedge):
                opens_this_week.append({
                    "ticker": e.get("ticker"),
                    "description": e.get("description")
                })
        except ValueError:
            continue
    _max = cfg("strategy.entries_per_week_max", 2)
    return {
        "max_per_week": _max,
        "used": len(opens_this_week),
        "remaining": max(0, _max - len(opens_this_week)),
        "entries_this_week": opens_this_week,
    }


# ---------------------------------------------------------------------------
# Actions priority computation per Build Spec §5.2
# ---------------------------------------------------------------------------

def compute_actions(positions: dict, alerts: dict, candidates: dict, calendar: dict) -> list[dict]:
    """Build today's actions list with priority assignment."""
    actions = []

    # Position alert states (HIGH for active alert states).
    aggregated_positions = state.aggregate_positions_by_ticker(positions) \
        if hasattr(state, 'aggregate_positions_by_ticker') else positions.get("positions", [])
    for pos in aggregated_positions:
        state_ = pos.get("alert_state", "safe")
        ticker = pos.get("ticker", "")

        if state_ in ("approaching", "breaking", "broken"):
            actions.append({
                "priority": "HIGH",
                "title": f"{ticker} alert: {state_}",
                "description": pos.get("notes", "") or f"{ticker} requires defensive review",
                "ticker": ticker,
                "cta": "Investigate"
            })
        elif state_ == "critical_gamma":
            # Only fire if there is an active short leg — LEAP long calls are high-delta by design.
            _strat_b = (pos.get("strategy") or "").upper()
            _has_short_b = pos.get("short_strike") is not None
            if _strat_b in ("PMCC", "DIAGONAL", "LEAPS") and not _has_short_b:
                pass  # Long LEAP, no short overlay yet — not a risk
            else:
                actions.append({
                    "priority": "HIGH",
                    "title": f"{ticker} Short-leg Gamma Risk",
                    "description": (
                        f"Short call delta > 0.40 (currently {pos.get('current_delta', '?')}). "
                        f"Roll short leg within trading week per §5."
                    ),
                    "ticker": ticker,
                    "cta": "Roll"
                })

    # Held tickers entering earnings window
    held_tickers = {p.get("ticker") for p in positions.get("positions", []) if p.get("ticker")}
    for ticker in held_tickers:
        days = state.days_to_earnings(ticker, calendar)
        if days is not None and 0 <= days <= 5:
            actions.append({
                "priority": "MED",
                "title": f"{ticker} earnings in {days} day{'s' if days != 1 else ''}",
                "description": "Existing position event risk. Hold through per PMCC design.",
                "ticker": ticker,
                "cta": "Review"
            })

    # Candidate scanner top signals
    for row in candidates.get("rows", []):
        ticker = row.get("ticker", "")
        days = row.get("days_to_earnings")
        signal = row.get("signal", "").upper()
        # Skip if blocked by earnings
        if days is not None and 0 <= days <= 10:
            continue

        if signal == "PRIME_CRUSH":
            actions.append({
                "priority": "MED",
                "title": f"{ticker} PRIME CRUSH candidate",
                "description": f"IVR {row.get('ivr', '?')}, IV/HV +{row.get('spread_pp', '?')}pp",
                "ticker": ticker,
                "cta": "Trade"
            })
        elif signal == "GOOD_SPREAD":
            actions.append({
                "priority": "LOW",
                "title": f"{ticker} GOOD SPREAD candidate",
                "description": f"IVR {row.get('ivr', '?')}, IV/HV +{row.get('spread_pp', '?')}pp",
                "ticker": ticker,
                "cta": "Trade"
            })

    # Stale data warning
    staleness = state.staleness_hours("active_positions.json")
    if staleness and staleness > 24:
        actions.insert(0, {
            "priority": "HIGH",
            "title": "Position state is stale",
            "description": f"active_positions.json is {staleness:.0f}h old. Sync from IBKR before trading.",
            "ticker": None,
            "cta": "Sync IBKR"
        })

    # Sort: HIGH > MED > LOW
    priority_order = {"HIGH": 0, "MED": 1, "LOW": 2}
    actions.sort(key=lambda a: priority_order.get(a["priority"], 3))
    return actions[:8]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/briefing")
def get_briefing():
    """Aggregate the briefing view per Build Spec §5.2."""
    try:
        positions = state.get_active_positions()
        alerts = state.get_alerts()
        candidates = state.get_iv_crush_report()
        calendar = state.get_earnings_blocklist()
        journal = state.get_journal()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Account header — graceful: only show fields that exist in positions file.
    # IBKR sync writes 'excess_liquidity'; older OCR-style files may have used 'excess_liq'.
    excess_liq_value = positions.get("excess_liq")
    if excess_liq_value is None:
        excess_liq_value = positions.get("excess_liquidity")

    account_usd = {
        "net_liq": positions.get("net_liq"),
        "excess_liq": excess_liq_value,
        "available_funds": positions.get("available_funds"),
        "base_cash": positions.get("base_cash"),
        "daily_pnl": positions.get("daily_pnl"),
        "unrealized_pnl": positions.get("unrealized_pnl"),
    }
    has_account_data = any(v is not None for v in account_usd.values())

    # FX conversion — Strategy v3.4 §7 thresholds are in EUR; IBKR returns USD
    fx_rate = fx.get_eur_usd_rate()
    def _to_eur(usd):
        if usd is None or not fx_rate:
            return None
        return round(usd / fx_rate, 2)
    account_eur = {k: _to_eur(v) for k, v in account_usd.items()}

    # USD-native thresholds (configurable via Settings → strategy.{available_funds_min_usd, excess_liq_min_usd})
    try:
        from app.services.config_store import cfg as _cfg
        avail_floor = float(_cfg("strategy.available_funds_min_usd") or 17000)
        excess_floor = float(_cfg("strategy.excess_liq_min_usd") or 25000)
    except Exception:
        avail_floor, excess_floor = 17000, 25000

    account = {
        **account_usd,
        "currency": "USD",
        "fx_rate_eur_usd": round(fx_rate, 4) if fx_rate else None,
        "eur_equivalent": account_eur,
        # Strategy §7 thresholds — USD-native per user preference (was EUR pre-2026-05-05)
        "thresholds": {
            "available_funds_floor_usd": avail_floor,
            "excess_liq_floor_usd": excess_floor,
            "available_funds_ok": (
                account_usd.get("available_funds") is not None
                and account_usd["available_funds"] > avail_floor
            ),
            "excess_liq_ok": (
                account_usd.get("excess_liq") is not None
                and account_usd["excess_liq"] > excess_floor
            ),
        },
    }

    # Macro regime + VIX state for Build Spec §5.5.1
    macro = candidates.get("macro_regime", {}) or {}

    # Live VIX fallback: fetch from yfinance when no daily report has populated it
    if not macro.get("vix"):
        try:
            import yfinance as _yf
            _hist = _yf.Ticker("^VIX").history(period="1d")
            if not _hist.empty:
                macro["vix"] = round(float(_hist["Close"].iloc[-1]), 2)
        except Exception:
            pass
    vix = macro.get("vix", 0) or 0
    if vix > 35:
        vix_state = "stress"
    elif vix > 25:
        vix_state = "elevated"
    else:
        vix_state = "normal"
    macro["vix_state"] = vix_state

    # Data staleness per Build Spec §5.5.2
    staleness = state.staleness_hours("active_positions.json")
    if staleness is None:
        staleness_state = "unknown"
    elif staleness > 24:
        staleness_state = "stale"
    elif staleness > 2:
        staleness_state = "aging"
    else:
        staleness_state = "fresh"

    # Concentration (use stored or compute)
    conc_dict = state.compute_concentration(positions)
    top_concentration = sorted(
        [{"ticker": t, "pct": p} for t, p in conc_dict.items()],
        key=lambda x: x["pct"],
        reverse=True
    )[:5]
    msft_warning = conc_dict.get("MSFT", 0) >= 50

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "has_account_data": has_account_data,
        "macro_regime": macro,
        "staleness": {
            "hours": round(staleness, 1) if staleness is not None else None,
            "state": staleness_state,
            "ocr_last_sync": positions.get("ocr_last_sync"),
        },
        "pacing": compute_pacing(journal),
        "concentration": {
            "top": top_concentration,
            "all": conc_dict,
            "msft_warning": msft_warning,
        },
        "greeks": compute_portfolio_greeks_with_beta(positions),
        "actions": compute_actions(positions, alerts, candidates, calendar),
    }
