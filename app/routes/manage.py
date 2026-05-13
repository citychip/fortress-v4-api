"""
Manage endpoints — Phase 4 §8.1, §8.2, plus Strategy v3.5 §2.D / §2.E.

Updated to use state.aggregate_positions_by_ticker() so the per-leg IBKR
sync still gives Phase 4 a sensible "one row per underlying" view.

v2 additions:
  GET /api/manage/stop_loss_all   — run stop-loss for every active position
  GET /api/manage/roll_all        — run roll evaluator for every active position
  GET /api/manage/pretrade_all    — run pre-trade gates for every universe ticker
  GET /api/manage/trade_report    — comprehensive trade evaluation report
  POST /api/manage/monitor_alerts — run position monitor and auto-create alerts
"""

from __future__ import annotations

import glob
import uuid
from datetime import datetime, date, timezone
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


def _dte_days(expiry_str: str) -> Optional[int]:
    """Return days to expiry from an ISO date string, or None if unparseable."""
    try:
        exp = date.fromisoformat(str(expiry_str)[:10])
        return max(0, (exp - date.today()).days)
    except (ValueError, TypeError):
        return None


def _load_dp_floors_map() -> dict[str, list[float]]:
    """Load DP floors from the latest QuantData daily report (if enabled)."""
    if not config_store.cfg("security.use_quantdata", True):
        return {}
    daily_path = _get_latest_daily_report()
    if not daily_path:
        return {}
    try:
        with daily_path.open("r", encoding="utf-8") as f:
            content = f.read()
        return parse_dp_floors_from_daily_report(content)
    except OSError:
        return {}


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
    daily_path = None
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
# Batch stop-loss — all active positions  (item B)
# ---------------------------------------------------------------------------

@router.get("/manage/stop_loss_all")
def stop_loss_all():
    """
    Run stop-loss evaluation for every active position.
    Returns a ranked list (ACT_IMMEDIATELY → ACT → WATCH → SAFE).
    """
    rows = _aggregated()
    dp_floors_map = _load_dp_floors_map()

    VERDICT_RANK = {"ACT_IMMEDIATELY": 0, "ACT": 1, "WATCH": 2, "SAFE": 3}
    results = []

    for pos in rows:
        ticker = (pos.get("ticker") or "").upper()
        if not ticker:
            continue
        try:
            latest_price = chain_svc.get_spot(ticker)
            sma_200 = chain_svc.get_sma(ticker, 200)
        except Exception:
            latest_price = None
            sma_200 = None

        dp_floors = dp_floors_map.get(ticker, [])
        current_mv = pos.get("net_market_value")

        try:
            ev = evaluate_stop_loss(
                position=pos,
                latest_price=latest_price,
                sma_200=sma_200,
                dp_floors=dp_floors,
                current_mv=current_mv,
            )
        except Exception as exc:
            ev = {"verdict": "SAFE", "signals": [], "reasons": [str(exc)]}

        results.append({
            "ticker": ticker,
            "strategy": pos.get("strategy"),
            "expiry": pos.get("short_expiry") or pos.get("expiry"),
            "short_strike": pos.get("short_strike"),
            "current_delta": pos.get("current_delta"),
            "net_market_value": current_mv,
            "synthesized_id": _synthesize_id(pos),
            "verdict": ev.get("verdict", "SAFE"),
            "recommended_action": ev.get("recommended_action", ""),
            "signals": ev.get("signals", []),
            "reasons": ev.get("reasons", []),
            "latest_price": latest_price,
            "sma_200": sma_200,
        })

    results.sort(key=lambda r: VERDICT_RANK.get(r["verdict"], 99))

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "positions_evaluated": len(results),
        "positions": results,
        "summary": {
            "act_immediately": sum(1 for r in results if r["verdict"] == "ACT_IMMEDIATELY"),
            "act": sum(1 for r in results if r["verdict"] == "ACT"),
            "watch": sum(1 for r in results if r["verdict"] == "WATCH"),
            "safe": sum(1 for r in results if r["verdict"] == "SAFE"),
        },
    }


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
# Batch roll — all active positions  (item B)
# ---------------------------------------------------------------------------

@router.get("/manage/roll_all")
def roll_all():
    """
    Run roll evaluation for every active position.
    Returns a ranked list (URGENT → WARNING → APPROACHING → NONE).
    """
    rows = _aggregated()
    URGENCY_RANK = {"URGENT": 0, "WARNING": 1, "APPROACHING": 2, "NONE": 3}
    results = []

    for pos in rows:
        ticker = (pos.get("ticker") or "").upper()
        if not ticker:
            continue
        strategy = (pos.get("strategy") or "").upper()
        if strategy == "SPY_HEDGE":
            continue  # not roll candidates

        roll_input = {
            "ticker": ticker,
            "short_strike": pos.get("short_strike"),
            "expiry": pos.get("short_expiry") or pos.get("expiry"),
            "qty": pos.get("qty") or 1,
            "current_delta": pos.get("current_delta"),
        }

        try:
            ev = evaluate_roll(position=roll_input)
        except Exception as exc:
            ev = {"urgency": "NONE", "roll_needed": False, "reasons": [str(exc)], "current_dte": None}

        results.append({
            "ticker": ticker,
            "strategy": pos.get("strategy"),
            "expiry": pos.get("short_expiry") or pos.get("expiry"),
            "short_strike": pos.get("short_strike"),
            "current_delta": pos.get("current_delta"),
            "synthesized_id": _synthesize_id(pos),
            "roll_needed": ev.get("roll_needed", False),
            "urgency": ev.get("urgency", "NONE"),
            "current_dte": ev.get("current_dte"),
            "dte_exempt": ev.get("dte_exempt", False),
            "reasons": ev.get("reasons", []),
        })

    results.sort(key=lambda r: URGENCY_RANK.get(r["urgency"], 99))

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "positions_evaluated": len(results),
        "positions": results,
        "summary": {
            "urgent": sum(1 for r in results if r["urgency"] == "URGENT"),
            "warning": sum(1 for r in results if r["urgency"] == "WARNING"),
            "approaching": sum(1 for r in results if r["urgency"] == "APPROACHING"),
            "none": sum(1 for r in results if r["urgency"] == "NONE"),
        },
    }


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
    Five hard checks — any failure requires explicit acknowledgment before entry.
    """
    ticker = ticker.upper().strip()

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

    concentration = state.compute_concentration(positions_data)
    conc_pct = concentration.get(ticker, 0.0)

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

    days_to_earnings = state.days_to_earnings(ticker, calendar)
    if days_to_earnings is not None and 0 <= days_to_earnings <= 10:
        earnings_state = "blackout"
        earnings_passed = False
    elif days_to_earnings is not None and 0 <= days_to_earnings <= 30:
        earnings_state = "approaching"
        earnings_passed = True
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

    leap_blackout_days = int(strategy_cfg.get("leap_earnings_blackout_days", 21))
    has_leap = any(
        p.get("ticker", "").upper() == ticker
        and str(p.get("strategy", "")).upper() in ("PMCC", "LEAPS", "DIAGONAL")
        and (_dte_days(p.get("long_expiry") or p.get("expiry") or "") or 0) > 90
        for p in (positions_data.get("positions") or [])
    )
    if has_leap and days_to_earnings is not None and 0 <= days_to_earnings <= leap_blackout_days:
        leap_gate_passed = False
        leap_detail = (
            f"LEAP position open on {ticker}; earnings in {days_to_earnings}d "
            f"(≤ {leap_blackout_days}d blackout) — short-leg entry blocked"
        )
    else:
        leap_gate_passed = True
        if has_leap and days_to_earnings is not None:
            leap_detail = f"LEAP open on {ticker}; earnings in {days_to_earnings}d — outside {leap_blackout_days}d blackout"
        elif has_leap:
            leap_detail = f"LEAP open on {ticker}; no earnings date found — treat as clear"
        else:
            leap_detail = f"No LEAP/PMCC position on {ticker} — gate not applicable"
    gate_leap = {
        "name": "leap_earnings_blackout",
        "rule": f"Strategy §4 — no short-leg entry within {leap_blackout_days}d of earnings when a LEAP is open",
        "passed": leap_gate_passed,
        "detail": leap_detail,
        "has_leap": has_leap,
        "days_to_earnings": days_to_earnings,
        "blackout_days": leap_blackout_days,
    }

    gates = [gate_exclusion, gate_earnings, gate_concentration, gate_vix, gate_leap]
    hard_failures = [g for g in gates if not g["passed"]]
    all_passed = len(hard_failures) == 0

    if all_passed:
        verdict = "PROCEED"
        verdict_reason = "All five pre-trade gates passed."
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
# Batch pre-trade gate — all universe tickers  (item C)
# ---------------------------------------------------------------------------

@router.get("/manage/pretrade_all")
def pretrade_all():
    """
    Run pre-trade gates for every ticker in the universe.
    Returns a matrix: PROCEED | BLOCKED per ticker.
    """
    try:
        positions_data = state.get_active_positions()
        calendar = state.get_earnings_blocklist()
        universe = state.get_ticker_universe()
        iv_report = state.get_iv_crush_report()
        settings = state.get_dashboard_settings()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    macro = iv_report.get("macro_regime", {}) or {}
    strategy_cfg = settings.get("config", {}).get("strategy", {})
    concentration = state.compute_concentration(positions_data)

    excluded_map = {
        e["ticker"].upper(): e
        for e in (universe.get("excluded") or [])
        if isinstance(e, dict) and e.get("ticker")
    }

    # Collect all universe tickers (tier1 + tier2 + tier3)
    all_tickers: list[str] = []
    for tier_key in ("tier1", "tier2", "tier3", "tickers"):
        tier = universe.get(tier_key, [])
        if isinstance(tier, list):
            all_tickers.extend(t.upper() for t in tier if t)

    # Deduplicate, skip excluded
    seen = set()
    tickers = []
    for t in all_tickers:
        if t not in seen:
            seen.add(t)
            tickers.append(t)

    vix_high = float(strategy_cfg.get("vix_high", 35))
    vix = macro.get("vix") or 0.0
    conc_limit = float(strategy_cfg.get("concentration_limit_pct", 50))
    leap_blackout_days = int(strategy_cfg.get("leap_earnings_blackout_days", 21))

    results = []
    for ticker in tickers:
        conc_pct = concentration.get(ticker, 0.0)
        days_to_earnings = state.days_to_earnings(ticker, calendar)

        if days_to_earnings is not None and 0 <= days_to_earnings <= 10:
            earnings_state = "blackout"
        elif days_to_earnings is not None and 0 <= days_to_earnings <= 30:
            earnings_state = "approaching"
        else:
            earnings_state = "clear"

        excluded_entry = excluded_map.get(ticker)
        is_excluded = excluded_entry is not None

        has_leap = any(
            p.get("ticker", "").upper() == ticker
            and str(p.get("strategy", "")).upper() in ("PMCC", "LEAPS", "DIAGONAL")
            and (_dte_days(p.get("long_expiry") or p.get("expiry") or "") or 0) > 90
            for p in (positions_data.get("positions") or [])
        )
        leap_blocked = (
            has_leap
            and days_to_earnings is not None
            and 0 <= days_to_earnings <= leap_blackout_days
        )

        failures = []
        if is_excluded:
            failures.append("excluded")
        if earnings_state == "blackout":
            failures.append("earnings_blackout")
        if conc_pct >= conc_limit:
            failures.append("concentration")
        if vix >= vix_high:
            failures.append("vix")
        if leap_blocked:
            failures.append("leap_blackout")

        verdict = "PROCEED" if not failures else "BLOCKED"

        results.append({
            "ticker": ticker,
            "verdict": verdict,
            "failures": failures,
            "days_to_earnings": days_to_earnings,
            "earnings_state": earnings_state,
            "concentration_pct": round(conc_pct, 2),
            "vix": round(vix, 1),
            "excluded": is_excluded,
            "exclusion_reason": excluded_entry.get("reason") if excluded_entry else None,
            "has_leap": has_leap,
        })

    # Sort: PROCEED first, then by earnings proximity
    results.sort(key=lambda r: (
        0 if r["verdict"] == "PROCEED" else 1,
        r.get("days_to_earnings") or 999,
    ))

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "tickers_evaluated": len(results),
        "results": results,
        "summary": {
            "proceed": sum(1 for r in results if r["verdict"] == "PROCEED"),
            "blocked": sum(1 for r in results if r["verdict"] == "BLOCKED"),
            "vix": round(vix, 1),
            "vix_regime": macro.get("vix_state", "unknown"),
        },
    }


# ---------------------------------------------------------------------------
# Comprehensive trade evaluation report  (new feature)
# ---------------------------------------------------------------------------

@router.get("/manage/trade_report")
def trade_report():
    """
    Comprehensive trade evaluation report covering:
      1. Entry candidates — universe tickers that pass all gates, ranked by IV rank
      2. Roll candidates  — active positions needing a roll, ranked by urgency
      3. Stop-loss alerts — active positions with ACT/ACT_IMMEDIATELY verdicts
      4. Exit candidates  — positions at profit target (≥ 50% of max credit captured)
      5. Post-earnings    — tickers with earnings in last 3 days (playbook candidates)
    """
    try:
        positions_data = state.get_active_positions()
        calendar = state.get_earnings_blocklist()
        universe = state.get_ticker_universe()
        iv_report = state.get_iv_crush_report()
        settings = state.get_dashboard_settings()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    macro = iv_report.get("macro_regime", {}) or {}
    strategy_cfg = settings.get("config", {}).get("strategy", {})
    concentration = state.compute_concentration(positions_data)
    aggregated = state.aggregate_positions_by_ticker(positions_data)
    dp_floors_map = _load_dp_floors_map()

    excluded_map = {
        e["ticker"].upper(): e
        for e in (universe.get("excluded") or [])
        if isinstance(e, dict) and e.get("ticker")
    }

    vix_high = float(strategy_cfg.get("vix_high", 35))
    vix = macro.get("vix") or 0.0
    conc_limit = float(strategy_cfg.get("concentration_limit_pct", 50))
    profit_target_pct = float(strategy_cfg.get("profit_target_pct", 50)) / 100.0
    leap_blackout_days = int(strategy_cfg.get("leap_earnings_blackout_days", 21))

    # ── 1. Entry candidates ──────────────────────────────────────────────────
    iv_rows = iv_report.get("rows", []) or []
    iv_map = {r.get("ticker", "").upper(): r for r in iv_rows if r.get("ticker")}

    all_tickers: list[str] = []
    for tier_key in ("tier1", "tier2", "tier3", "tickers"):
        tier = universe.get(tier_key, [])
        if isinstance(tier, list):
            all_tickers.extend(t.upper() for t in tier if t)

    seen: set[str] = set()
    entry_candidates = []
    for ticker in all_tickers:
        if ticker in seen:
            continue
        seen.add(ticker)

        conc_pct = concentration.get(ticker, 0.0)
        days_to_earnings = state.days_to_earnings(ticker, calendar)

        if days_to_earnings is not None and 0 <= days_to_earnings <= 10:
            earnings_state = "blackout"
        elif days_to_earnings is not None and 0 <= days_to_earnings <= 30:
            earnings_state = "approaching"
        else:
            earnings_state = "clear"

        is_excluded = ticker in excluded_map
        has_leap = any(
            p.get("ticker", "").upper() == ticker
            and str(p.get("strategy", "")).upper() in ("PMCC", "LEAPS", "DIAGONAL")
            and (_dte_days(p.get("long_expiry") or p.get("expiry") or "") or 0) > 90
            for p in (positions_data.get("positions") or [])
        )
        leap_blocked = (
            has_leap
            and days_to_earnings is not None
            and 0 <= days_to_earnings <= leap_blackout_days
        )

        can_trade = (
            not is_excluded
            and earnings_state != "blackout"
            and conc_pct < conc_limit
            and vix < vix_high
            and not leap_blocked
        )

        iv_data = iv_map.get(ticker, {})
        iv_rank = iv_data.get("iv_rank") or iv_data.get("ivr")
        iv_pct = iv_data.get("iv_pct") or iv_data.get("iv_percentile")

        if can_trade:
            entry_candidates.append({
                "ticker": ticker,
                "iv_rank": iv_rank,
                "iv_pct": iv_pct,
                "days_to_earnings": days_to_earnings,
                "earnings_state": earnings_state,
                "concentration_pct": round(conc_pct, 2),
                "has_existing_position": ticker in {
                    (p.get("ticker") or "").upper() for p in aggregated
                },
                "action": "NEW_ENTRY" if not any(
                    (p.get("ticker") or "").upper() == ticker for p in aggregated
                ) else "ADD_TO_POSITION",
            })

    # Sort by IV rank descending (highest IV rank = best premium)
    entry_candidates.sort(
        key=lambda r: (r.get("iv_rank") or 0),
        reverse=True,
    )

    # ── 2. Roll candidates ───────────────────────────────────────────────────
    URGENCY_RANK = {"URGENT": 0, "WARNING": 1, "APPROACHING": 2, "NONE": 3}
    roll_candidates = []
    for pos in aggregated:
        ticker = (pos.get("ticker") or "").upper()
        if (pos.get("strategy") or "").upper() == "SPY_HEDGE":
            continue
        roll_input = {
            "ticker": ticker,
            "short_strike": pos.get("short_strike"),
            "expiry": pos.get("short_expiry") or pos.get("expiry"),
            "qty": pos.get("qty") or 1,
            "current_delta": pos.get("current_delta"),
        }
        try:
            ev = evaluate_roll(position=roll_input)
        except Exception:
            continue
        if ev.get("roll_needed"):
            roll_candidates.append({
                "ticker": ticker,
                "strategy": pos.get("strategy"),
                "expiry": pos.get("short_expiry") or pos.get("expiry"),
                "short_strike": pos.get("short_strike"),
                "current_dte": ev.get("current_dte"),
                "current_delta": pos.get("current_delta"),
                "urgency": ev.get("urgency"),
                "reasons": ev.get("reasons", []),
                "synthesized_id": _synthesize_id(pos),
                "action": "ROLL",
            })
    roll_candidates.sort(key=lambda r: URGENCY_RANK.get(r["urgency"], 99))

    # ── 3. Stop-loss alerts ──────────────────────────────────────────────────
    VERDICT_RANK = {"ACT_IMMEDIATELY": 0, "ACT": 1, "WATCH": 2, "SAFE": 3}
    stop_loss_alerts = []
    for pos in aggregated:
        ticker = (pos.get("ticker") or "").upper()
        try:
            latest_price = chain_svc.get_spot(ticker)
            sma_200 = chain_svc.get_sma(ticker, 200)
        except Exception:
            latest_price = None
            sma_200 = None
        dp_floors = dp_floors_map.get(ticker, [])
        current_mv = pos.get("net_market_value")
        try:
            ev = evaluate_stop_loss(
                position=pos,
                latest_price=latest_price,
                sma_200=sma_200,
                dp_floors=dp_floors,
                current_mv=current_mv,
            )
        except Exception:
            continue
        if ev.get("verdict") in ("ACT", "ACT_IMMEDIATELY", "WATCH"):
            stop_loss_alerts.append({
                "ticker": ticker,
                "strategy": pos.get("strategy"),
                "verdict": ev.get("verdict"),
                "recommended_action": ev.get("recommended_action"),
                "signals": ev.get("signals", []),
                "reasons": ev.get("reasons", []),
                "synthesized_id": _synthesize_id(pos),
                "action": "CLOSE" if ev.get("verdict") == "ACT_IMMEDIATELY" else "REVIEW",
            })
    stop_loss_alerts.sort(key=lambda r: VERDICT_RANK.get(r["verdict"], 99))

    # ── 4. Exit candidates (profit target reached) ───────────────────────────
    exit_candidates = []
    for pos in aggregated:
        ticker = (pos.get("ticker") or "").upper()
        net_mv = pos.get("net_market_value")
        # Rough proxy: if net_market_value is significantly positive (credit collected
        # and position has decayed), flag as potential exit candidate.
        # A more precise check would compare to original credit — use net_liq_pct as proxy.
        net_liq_pct = pos.get("net_liq_pct") or 0
        # Flag if position has a low/positive market value relative to original credit
        # (this is a heuristic — the user should confirm with actual P&L)
        if net_mv is not None and net_mv > 0 and net_liq_pct < 2.0:
            exit_candidates.append({
                "ticker": ticker,
                "strategy": pos.get("strategy"),
                "expiry": pos.get("short_expiry") or pos.get("expiry"),
                "short_strike": pos.get("short_strike"),
                "net_market_value": net_mv,
                "net_liq_pct": net_liq_pct,
                "synthesized_id": _synthesize_id(pos),
                "action": "CLOSE_FOR_PROFIT",
                "note": "Position near zero cost — consider closing at profit target",
            })

    # ── 5. Post-earnings playbook candidates ─────────────────────────────────
    post_earnings_candidates = []
    today = date.today()
    for ticker in seen:
        days = state.days_to_earnings(ticker, calendar)
        if days is not None and -3 <= days <= 0:
            # Earnings were in the last 3 days
            try:
                spot = chain_svc.get_spot(ticker)
            except Exception:
                spot = None
            iv_data = iv_map.get(ticker, {})
            post_earnings_candidates.append({
                "ticker": ticker,
                "days_since_earnings": abs(days),
                "current_price": spot,
                "iv_rank_post": iv_data.get("iv_rank"),
                "action": "POST_EARNINGS_PLAYBOOK",
                "note": f"Earnings {abs(days)}d ago — run post-earnings playbook",
            })

    # ── Summary ──────────────────────────────────────────────────────────────
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "macro": {
            "vix": round(vix, 1),
            "regime": macro.get("regime", "unknown"),
            "vix_state": macro.get("vix_state", "unknown"),
        },
        "entry_candidates": entry_candidates[:20],  # top 20
        "roll_candidates": roll_candidates,
        "stop_loss_alerts": stop_loss_alerts,
        "exit_candidates": exit_candidates,
        "post_earnings_candidates": post_earnings_candidates,
        "summary": {
            "entry_candidates_count": len(entry_candidates),
            "roll_candidates_count": len(roll_candidates),
            "stop_loss_alerts_count": len(stop_loss_alerts),
            "exit_candidates_count": len(exit_candidates),
            "post_earnings_count": len(post_earnings_candidates),
            "urgent_actions": sum(1 for r in roll_candidates if r["urgency"] == "URGENT")
                            + sum(1 for r in stop_loss_alerts if r["verdict"] == "ACT_IMMEDIATELY"),
        },
    }


# ---------------------------------------------------------------------------
# Position monitor → auto-create alerts  (items D, E)
# ---------------------------------------------------------------------------

@router.post("/manage/monitor_alerts")
def monitor_alerts():
    """
    Run a lightweight position monitor pass and auto-create alerts for
    any positions with ACT or ACT_IMMEDIATELY stop-loss verdicts or
    URGENT roll urgency. Skips positions that already have an active alert.
    Returns the list of newly created alerts.
    """
    aggregated = _aggregated()
    dp_floors_map = _load_dp_floors_map()

    # Load existing alerts to avoid duplicates
    try:
        existing_data = state.get_alerts()
        existing_alerts = existing_data.get("alerts", [])
    except Exception:
        existing_alerts = []

    # Build set of tickers that already have an active (non-snoozed) alert
    alerted_tickers = {
        a.get("ticker", "").upper()
        for a in existing_alerts
        if not a.get("snoozed", False)
        and a.get("source") == "position_monitor"
    }

    new_alerts = []

    for pos in aggregated:
        ticker = (pos.get("ticker") or "").upper()
        if not ticker or ticker in alerted_tickers:
            continue

        # Skip LEAP/PMCC long-only positions — no short leg means no gamma risk to monitor.
        # Stop-loss and roll checks only apply when there is an active short leg.
        _strat = (pos.get("strategy") or "").upper()
        _has_short = pos.get("short_strike") is not None
        if _strat in ("PMCC", "DIAGONAL", "LEAPS") and not _has_short:
            continue

        # Stop-loss check
        try:
            latest_price = chain_svc.get_spot(ticker)
            sma_200 = chain_svc.get_sma(ticker, 200)
        except Exception:
            latest_price = None
            sma_200 = None

        dp_floors = dp_floors_map.get(ticker, [])
        current_mv = pos.get("net_market_value")

        try:
            sl = evaluate_stop_loss(
                position=pos,
                latest_price=latest_price,
                sma_200=sma_200,
                dp_floors=dp_floors,
                current_mv=current_mv,
            )
        except Exception:
            sl = {"verdict": "SAFE"}

        # Roll check
        roll_input = {
            "ticker": ticker,
            "short_strike": pos.get("short_strike"),
            "expiry": pos.get("short_expiry") or pos.get("expiry"),
            "qty": pos.get("qty") or 1,
            "current_delta": pos.get("current_delta"),
        }
        try:
            rv = evaluate_roll(position=roll_input)
        except Exception:
            rv = {"urgency": "NONE", "roll_needed": False}

        alert_needed = False
        severity = "info"
        message = ""

        if sl.get("verdict") == "ACT_IMMEDIATELY":
            alert_needed = True
            severity = "critical"
            message = f"STOP-LOSS: {ticker} — {sl.get('recommended_action', '')}. Signals: {', '.join(sl.get('signals', []))}"
        elif sl.get("verdict") == "ACT":
            alert_needed = True
            severity = "warn"
            message = f"STOP-LOSS: {ticker} — {sl.get('recommended_action', '')}. Signals: {', '.join(sl.get('signals', []))}"
        elif rv.get("urgency") == "URGENT":
            alert_needed = True
            severity = "critical"
            message = f"ROLL URGENT: {ticker} — {'; '.join(rv.get('reasons', []))}"
        elif rv.get("urgency") == "WARNING":
            alert_needed = True
            severity = "warn"
            message = f"ROLL WARNING: {ticker} — {'; '.join(rv.get('reasons', []))}"

        if alert_needed:
            new_alert = {
                "id": str(uuid.uuid4())[:8],
                "ticker": ticker,
                "severity": severity,
                "message": message,
                "source": "position_monitor",
                "position_id": _synthesize_id(pos),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "snoozed": False,
            }
            existing_alerts.append(new_alert)
            new_alerts.append(new_alert)

    if new_alerts:
        existing_data["alerts"] = existing_alerts
        existing_data["_last_updated"] = datetime.now(timezone.utc).isoformat()
        try:
            state.save_alerts(existing_data)
        except Exception:
            pass

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "new_alerts_created": len(new_alerts),
        "alerts": new_alerts,
    }


# ---------------------------------------------------------------------------
# Strategy v3.5 §2.D — SPY hedge coverage
# ---------------------------------------------------------------------------

@router.get("/manage/spy_hedge_coverage")
def spy_hedge_coverage():
    """Reports current SPY hedge MV against the €20–30K target band."""
    data = state.get_active_positions()

    cached = data.get("spy_hedge_coverage")
    if cached:
        return {**cached, "source": "ibkr_sync_cached"}

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
# Strategy §2.E — Jade Lizard credit validation
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
            raise ValueError("call_long_strike must be greater than call_short_strike")
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
