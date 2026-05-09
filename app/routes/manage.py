"""
Manage endpoints — Phase 4 §8.1, §8.2, plus Strategy v3.5 §2.D / §2.E.

Updated to use state.aggregate_positions_by_ticker() so the per-leg IBKR
sync still gives Phase 4 a sensible "one row per underlying" view.
"""

from __future__ import annotations

import glob
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator as _model_validator

from app.services import state, chain as chain_svc
from app.services import config_store
from app.services.roll import evaluate_roll
from app.services.stop_loss import evaluate_stop_loss, parse_dp_floors_from_daily_report

router = APIRouter()


def _synthesize_id(pos: dict) -> str:
    """e.g. UNH_jun18_390c — uses short_expiry/short_strike when available, else long."""
    ticker = (pos.get("ticker") or "").lower()
    expiry = pos.get("short_expiry") or pos.get("long_expiry") or pos.get("expiry") or ""
    strike = pos.get("short_strike") or pos.get("long_strike")
    try:
        d = datetime.strptime(expiry[:10], "%Y-%m-%d")
        exp_short = d.strftime("%b%d").lower()
    except (ValueError, TypeError):
        exp_short = "unkn"
    strike_part = f"{int(strike)}c" if strike else "?c"
    return f"{ticker}_{exp_short}_{strike_part}"


def _aggregated() -> list[dict]:
    """Aggregated view of active_positions.json — one record per ticker."""
    data = state.get_active_positions()
    return state.aggregate_positions_by_ticker(data)


def _find_position(position_id: str) -> Optional[dict]:
    """Resolve a combined position by ticker or synthesized id."""
    pid = position_id.strip()
    rows = _aggregated()

    for p in rows:
        if _synthesize_id(p).lower() == pid.lower():
            return p

    matches = [p for p in rows if (p.get("ticker") or "").upper() == pid.upper()]
    if len(matches) == 1:
        return matches[0]
    return None


def _get_latest_daily_report() -> Optional[Path]:
    matches = sorted(glob.glob(str(state.BASE_DIR / "QuantData Daily Report*.md")))
    return Path(matches[-1]) if matches else None


# ---------------------------------------------------------------------------
# Stop-loss aggregator (Strategy §6)
# ---------------------------------------------------------------------------

@router.get("/manage/stop_loss/{position_id}")
def stop_loss(
    position_id: str,
    fundamental_break: bool = Query(False),
    peak_mv: Optional[float] = Query(None),
    current_mv: Optional[float] = Query(None),
):
    pos = _find_position(position_id)
    if not pos:
        raise HTTPException(
            status_code=404,
            detail=f"Position '{position_id}' not found. Try the ticker (e.g., 'MSFT')."
        )

    ticker = (pos.get("ticker") or "").upper()
    latest_price = chain_svc.get_spot(ticker)
    sma_200 = chain_svc.get_sma(ticker, 200)

    dp_floors: list[float] = []
    # Only load DP floors when QuantData is enabled (Settings > Security)
    if config_store.cfg("security.use_quantdata", True):
        daily_path = _get_latest_daily_report()
        if daily_path:
            try:
                with daily_path.open("r", encoding="utf-8") as f:
                    content = f.read()
                floors_map = parse_dp_floors_from_daily_report(content)
                dp_floors = floors_map.get(ticker, [])
            except OSError:
                pass
    else:
        daily_path = None  # QuantData disabled — DP floor signal suppressed

    # If current_mv not provided, use the aggregated net_market_value
    if current_mv is None and pos.get("net_market_value") is not None:
        current_mv = pos.get("net_market_value")

    result = evaluate_stop_loss(
        position=pos,
        latest_price=latest_price,
        sma_200=sma_200,
        dp_floors=dp_floors,
        peak_mv=peak_mv,
        current_mv=current_mv,
        fundamental_break=fundamental_break,
    )
    result["position"] = {
        "ticker": ticker,
        "strategy": pos.get("strategy"),
        "expiry": pos.get("expiry"),
        "short_strike": pos.get("short_strike"),
        "long_strike": pos.get("long_strike"),
        "leg_count": pos.get("leg_count"),
        "synthesized_id": _synthesize_id(pos),
    }
    result["sources"] = {
        "spot": "yfinance",
        "sma_200": "yfinance (200d daily close)",
        "dp_floors": (
            "disabled (QuantData off in Settings > Security)"
            if not config_store.cfg("security.use_quantdata", True)
            else (str(daily_path) if daily_path else None)
        ),
    }
    return result


# ---------------------------------------------------------------------------
# Roll candidate evaluator (Strategy §5)
# ---------------------------------------------------------------------------

@router.get("/manage/roll/{position_id}")
def roll(
    position_id: str,
    target_dte_low: int = Query(30, ge=1, le=180),
    target_dte_high: int = Query(45, ge=1, le=365),
    target_delta_low: float = Query(0.20, ge=0.05, le=0.50),
    target_delta_high: float = Query(0.25, ge=0.05, le=0.60),
):
    pos = _find_position(position_id)
    if not pos:
        raise HTTPException(status_code=404, detail=f"Position '{position_id}' not found.")
    if (pos.get("strategy") or "").upper() == "SPY_HEDGE":
        raise HTTPException(status_code=400,
            detail="SPY hedge positions are not roll candidates per Strategy §2.D.")
    if pos.get("short_strike") is None:
        raise HTTPException(status_code=400,
            detail="Position has no short_strike — no short call leg to roll.")

    # evaluate_roll expects a dict with ticker, short_strike, expiry, qty
    # The aggregated record has all of these (expiry = short_expiry)
    roll_input = {
        "ticker": pos.get("ticker"),
        "short_strike": pos.get("short_strike"),
        "expiry": pos.get("short_expiry") or pos.get("expiry"),
        "qty": pos.get("qty") or 1,
    }
    result = evaluate_roll(
        position=roll_input,
        target_dte=(target_dte_low, target_dte_high),
        target_delta=(target_delta_low, target_delta_high),
    )
    result["position"] = {
        "ticker": pos.get("ticker"),
        "strategy": pos.get("strategy"),
        "expiry": pos.get("expiry"),
        "short_strike": pos.get("short_strike"),
        "long_strike": pos.get("long_strike"),
        "leg_count": pos.get("leg_count"),
        "synthesized_id": _synthesize_id(pos),
    }
    return result


# ---------------------------------------------------------------------------
# Aggregated position list — for UI pickers
# ---------------------------------------------------------------------------

@router.get("/manage/positions")
def list_manageable_positions():
    rows = _aggregated()
    out = []
    for p in rows:
        out.append({
            "ticker": p.get("ticker"),
            "strategy": p.get("strategy"),
            "expiry": p.get("expiry"),
            "short_strike": p.get("short_strike"),
            "long_strike": p.get("long_strike"),
            "leg_count": p.get("leg_count"),
            "current_delta": p.get("current_delta"),
            "alert_state": p.get("alert_state"),
            "delta_state": p.get("delta_state"),
            "net_liq_pct": p.get("net_liq_pct"),
            "id": _synthesize_id(p),
        })
    return {"positions": out}



# ---------------------------------------------------------------------------
# Build Spec §8.0 — Pre-trade gate (composite, four checks)
# ---------------------------------------------------------------------------
@router.get("/manage/pre_trade_check")
def pre_trade_check(ticker: str):
    """
    Composite pre-trade gate per Build Spec §8.0 and Strategy §15.1.
    Four hard checks — any failure requires explicit acknowledgment before entry.

    Gates:
      1. §3.3 Hard exclusion  — ticker in excluded list
      2. §4   Earnings blackout — days_to_earnings <= 10
      3. §7   Concentration    — existing position >= 50% NLV
      4. §7   VIX state        — VIX > strategy.vix_high threshold
    """
    ticker = ticker.upper().strip()

    # Load required state
    try:
        positions_data = state.get_active_positions()
        calendar = state.get_earnings_blocklist()
        universe = state.get_ticker_universe()
        iv_report = state.get_iv_crush_report()
        settings = state.get_dashboard_settings()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    macro = iv_report.get("macro_regime", {}) or {}
    strategy_cfg_raw = settings.get("config", {}).get("strategy", {})

    # Concentration map
    concentration = state.compute_concentration(positions_data)
    conc_pct = concentration.get(ticker, 0.0)

    # Gate 1: Hard exclusion
    excluded_map = {
        e["ticker"].upper(): e
        for e in (universe.get("excluded") or [])
        if isinstance(e, dict) and e.get("ticker")
    }
    excluded_entry = excluded_map.get(ticker)
    gate_exclusion = {
        "name": "hard_exclusion",
        "rule": "Strategy §3.3 — ticker must not be on the excluded list",
        "passed": excluded_entry is None,
        "detail": excluded_entry.get("reason") if excluded_entry else "Not excluded",
    }

    # Gate 2: Earnings blackout
    days_to_earnings = state.days_to_earnings(ticker, calendar)
    if days_to_earnings is not None and 0 <= days_to_earnings <= 10:
        earnings_state = "blackout"
        earnings_passed = False
    elif days_to_earnings is not None and 0 <= days_to_earnings <= 30:
        earnings_state = "approaching"
        earnings_passed = True  # warn but not a hard block
    else:
        earnings_state = "clear"
        earnings_passed = True
    gate_earnings = {
        "name": "earnings_blackout",
        "rule": "Strategy §4 — no entry within 10 days of earnings",
        "passed": earnings_passed,
        "detail": (
            f"Earnings in {days_to_earnings}d — {earnings_state}"
            if days_to_earnings is not None
            else "No earnings date found — treat as clear"
        ),
        "days_to_earnings": days_to_earnings,
        "earnings_state": earnings_state,
    }

    # Gate 3: Concentration
    strategy_cfg = strategy_cfg_raw
    conc_limit = float(strategy_cfg.get("concentration_limit_pct", 50))
    gate_concentration = {
        "name": "concentration",
        "rule": f"Strategy §7 — existing position must be < {conc_limit:.0f}% NLV",
        "passed": conc_pct < conc_limit,
        "detail": f"Current exposure: {conc_pct:.1f}% NLV (limit: {conc_limit:.0f}%)",
        "concentration_pct": round(conc_pct, 2),
        "limit_pct": conc_limit,
    }

    # Gate 4: VIX state
    vix_high = float(strategy_cfg.get("vix_high", 35))
    vix = macro.get("vix") or 0.0
    vix_state = macro.get("vix_state", "normal")
    gate_vix = {
        "name": "vix_state",
        "rule": f"Strategy §7 — VIX must be < {vix_high:.0f} for new entries",
        "passed": vix < vix_high,
        "detail": f"VIX: {vix:.1f} ({vix_state}) — threshold: {vix_high:.0f}",
        "vix": vix,
        "vix_state": vix_state,
        "vix_threshold": vix_high,
    }

    gates = [gate_exclusion, gate_earnings, gate_concentration, gate_vix]
    hard_failures = [g for g in gates if not g["passed"]]
    all_passed = len(hard_failures) == 0

    # Overall verdict
    if all_passed:
        verdict = "PROCEED"
        verdict_reason = "All four pre-trade gates passed."
    else:
        verdict = "BLOCKED"
        verdict_reason = f"{len(hard_failures)} gate(s) failed: {', '.join(g['name'] for g in hard_failures)}. Requires explicit acknowledgment per Strategy §15.1."

    return {
        "ticker": ticker,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "all_passed": all_passed,
        "gates": {g["name"]: g for g in gates},
        "hard_failures": [g["name"] for g in hard_failures],
        "acknowledgment_required": not all_passed,
    }

# ---------------------------------------------------------------------------
# Strategy v3.5 §2.D — SPY hedge coverage
# ---------------------------------------------------------------------------

@router.get("/manage/spy_hedge_coverage")
def spy_hedge_coverage():
    """Reports current SPY hedge MV against the €20–30K target band.

    Source: Top-level 'spy_hedge_coverage' field written by ibkr_sync.py,
    or computed on the fly from positions if not present.
    """
    data = state.get_active_positions()

    # Prefer the field written by the IBKR sync
    cached = data.get("spy_hedge_coverage")
    if cached:
        return {**cached, "source": "ibkr_sync_cached"}

    # Otherwise compute from legs
    target_min = 20000
    target_max = 30000
    hedge_mv = 0.0
    legs = 0
    for p in data.get("positions", []):
        if (p.get("strategy") or "").upper() == "SPY_HEDGE":
            hedge_mv += (p.get("market_value") or 0)
            legs += 1
    net_liq = data.get("net_liq") or 0

    return {
        "hedge_market_value": round(hedge_mv, 2),
        "hedge_net_market_value": round(hedge_mv, 2),
        "hedge_pct_of_netliq": round(hedge_mv / net_liq * 100, 2) if net_liq else None,
        "target_min": target_min,
        "target_max": target_max,
        "coverage_ok": target_min <= hedge_mv <= target_max,
        "legs_count": legs,
        "source": "computed",
    }


# ---------------------------------------------------------------------------
# Strategy §2.E — Jade Lizard credit validation (preserved from prior commit)
# ---------------------------------------------------------------------------

class JadeLizardValidationRequest(BaseModel):
    put_strike: float = Field(..., gt=0)
    call_short_strike: float = Field(..., gt=0)
    call_long_strike: float = Field(..., gt=0)
    put_credit: float = Field(..., gt=0)
    call_spread_credit: float = Field(...)

    @_model_validator(mode="after")
    def validate_strikes(self):
        if self.call_long_strike <= self.call_short_strike:
            raise ValueError(
                "call_long_strike must be greater than call_short_strike"
            )
        return self


@router.post("/manage/validate_jade_lizard")
def validate_jade_lizard(body: JadeLizardValidationRequest):
    """Strategy §2.E — total credit must exceed call spread width."""
    call_spread_width = round(body.call_long_strike - body.call_short_strike, 4)
    total_credit = round(body.put_credit + body.call_spread_credit, 4)
    credit_exceeds_width = total_credit > call_spread_width
    margin = round(total_credit - call_spread_width, 4)

    return {
        "verdict": "PASS" if credit_exceeds_width else "FAIL",
        "rule": "Strategy §2.E — Total credit must exceed call spread width",
        "credit_exceeds_width": credit_exceeds_width,
        "inputs": {
            "put_strike": body.put_strike,
            "call_short_strike": body.call_short_strike,
            "call_long_strike": body.call_long_strike,
            "put_credit": body.put_credit,
            "call_spread_credit": body.call_spread_credit,
        },
        "computed": {
            "call_spread_width": call_spread_width,
            "total_credit": total_credit,
            "margin": margin,
        },
        "message": (
            f"Total credit ${total_credit:.2f} exceeds call spread width ${call_spread_width:.2f} by ${margin:.2f}."
            if credit_exceeds_width
            else f"FAIL: total credit ${total_credit:.2f} is ${abs(margin):.2f} below the call spread width ${call_spread_width:.2f}. Strategy §2.E requires credit > width."
        ),
    }
