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
        _strat = (pos.get("strategy") or "").upper()
        # LEAPS are intentional long-dated long calls — never stop-loss scan them.
        # STOCK positions are evaluated on price/SMA only (no delta signal).
        # SPY_HEDGE is a protective position — never close it on stop-loss signals.
        if _strat in ("SPY_HEDGE",):
            continue
        try:
            latest_price = chain_svc.get_spot(ticker)
            sma_200 = chain_svc.get_sma(ticker, 200)
        except Exception:
            latest_price = None
            sma_200 = None

        dp_floors = dp_floors_map.get(ticker, [])
        current_mv = pos.get("net_market_value")
        vert_exempt = bool(pos.get("vertical_exempt"))

        if vert_exempt:
            # Doctrine v2 (v3.11): expiry-matched verticals are defined-risk
            # packages — leg-level stop signals are suppressed; the package is
            # managed by the weekly-close de-risk rules, not per-leg stops.
            ev = {
                "verdict": "SAFE",
                "recommended_action": "Expiry-matched vertical (doctrine v2) — manage as package; no leg-level stop action.",
                "signals": ["vertical_exempt"],
                "reasons": ["Short call is fully covered by a same-expiry long call (defined-risk vertical) — stop flags suppressed per Strategy v3.11 doctrine v2."],
            }
        else:
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
            "vertical_exempt": vert_exempt,
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
            "vertical_exempt": sum(1 for r in results if r.get("vertical_exempt")),
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
        if strategy in ("SPY_HEDGE", "STOCK"):
            continue  # not roll candidates
        if strategy == "LEAPS":
            continue  # LEAP long calls are intentionally long-dated; never roll-scan them

        roll_input = {
            "ticker": ticker,
            "strategy": strategy,
            "short_strike": pos.get("short_strike"),
            "expiry": pos.get("short_expiry") or pos.get("expiry"),
            "qty": pos.get("qty") or 1,
            "current_delta": pos.get("current_delta"),
        }
        vert_exempt = bool(pos.get("vertical_exempt"))

        if vert_exempt:
            # Doctrine v2 (v3.11): expiry-matched verticals are never leg-rolled —
            # delta on the short leg WILL run high by design; the package resolves
            # at expiry or via the weekly-close de-risk rules.
            ev = {
                "urgency": "NONE",
                "roll_needed": False,
                "current_dte": _dte_days(roll_input["expiry"]),
                "reasons": ["Expiry-matched vertical — roll flags suppressed per Strategy v3.11 doctrine v2 (manage as package)."],
            }
        else:
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
            "vertical_exempt": vert_exempt,
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
            "vertical_exempt": sum(1 for r in results if r.get("vertical_exempt")),
        },
    }


@router.get("/manage/leap_roll_all")
def leap_roll_all():
    """
    Sprint 25.11 (backlog 19.4b) — LEAP-roll signals.

    The aggregated short-leg roll scan (roll_all) intentionally SKIPS LEAPs. This
    scans the PER-LEG book for long-dated long CALL legs (the LEAP cores) and flags
    any whose long delta has decayed to ≤ `strategy.leap_roll_delta` (0.70) or whose
    DTE has fallen to ≤ `strategy.leap_roll_dte` (120) — the §5 / v3.10 §4b trigger
    to roll the LEAP into a fresh 12–18-month contract before decay/assignment risk
    bites. Uses the per-leg greeks the aggregated rows don't expose.
    """
    from ..services.config_store import cfg
    roll_delta = float(cfg("strategy.leap_roll_delta", 0.70))
    roll_dte = int(cfg("strategy.leap_roll_dte", 120))
    leap_min_dte = 90  # a long call with DTE > this is treated as a LEAP core

    try:
        data = state.get_active_positions()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    out = []
    for p in (data.get("positions") or []):
        if (str(p.get("sec_type") or "OPT").upper() != "OPT"):
            continue
        if str(p.get("leg_direction", "")).lower() != "long":
            continue
        if str(p.get("right", "")).upper() != "C":
            continue
        dte = _dte_days(p.get("expiry")) or 0
        if dte <= leap_min_dte:
            continue  # short-dated long calls aren't LEAP cores
        delta = p.get("current_delta")
        reasons = []
        if delta is not None and float(delta) <= roll_delta:
            reasons.append(f"long delta {float(delta):.2f} ≤ {roll_delta:.2f}")
        if dte <= roll_dte:
            reasons.append(f"DTE {dte} ≤ {roll_dte}")
        if reasons:
            out.append({
                "ticker": (p.get("ticker") or "").upper(),
                "strike": p.get("strike"),
                "expiry": p.get("expiry"),
                "dte": dte,
                "current_delta": delta,
                "roll_needed": True,
                "urgency": "URGENT" if (delta is not None and float(delta) <= roll_delta - 0.05) or dte <= 60 else "WARNING",
                "reasons": reasons,
            })
    out.sort(key=lambda r: (0 if r["urgency"] == "URGENT" else 1, r.get("dte") or 9999))
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "leap_roll_delta": roll_delta,
        "leap_roll_dte": roll_dte,
        "count": len(out),
        "positions": out,
    }


def _collar_protective_put(spot: float | None, iv_dec: float | None,
                           dte_days: int, target_delta: float) -> tuple[float | None, float | None]:
    """
    Sprint 26.2 — DTE-matched protective put for a collar. Finds the OTM put
    strike whose |delta| ≈ target_delta (bisection) and returns (strike, debit)
    where debit is the per-contract Black-Scholes price in USD. The DTE is passed
    in by the caller so it MATCHES the short call exactly (no premium-decay drag
    from a longer-dated put — Technical Decision "DTE-Matched Protective Puts").
    Returns (None, None) on unusable inputs. Advisory math only.
    """
    import math as _m
    from app.services.bs_fallback import _norm_cdf, _RISK_FREE
    if not spot or spot <= 0 or not iv_dec or iv_dec <= 0 or dte_days <= 0:
        return None, None
    t = dte_days / 365.0
    lo, hi = spot * 0.5, spot            # protective put sits below spot
    strike = spot * 0.9
    for _ in range(60):
        strike = (lo + hi) / 2
        d1 = (_m.log(spot / strike) + (_RISK_FREE + 0.5 * iv_dec ** 2) * t) / (iv_dec * _m.sqrt(t))
        adelta = abs(_norm_cdf(d1) - 1.0)   # |put delta| — rises as strike → ATM
        if adelta > target_delta:
            hi = strike
        else:
            lo = strike
    d1 = (_m.log(spot / strike) + (_RISK_FREE + 0.5 * iv_dec ** 2) * t) / (iv_dec * _m.sqrt(t))
    d2 = d1 - iv_dec * _m.sqrt(t)
    put = strike * _m.exp(-_RISK_FREE * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
    return round(strike, 0), round(max(put, 0.0) * 100, 2)


@router.get("/manage/covered_call_candidates")
def covered_call_candidates():
    """
    Sprint 25.9 / 23.3 — auto-surface a covered-call candidate for each
    UNDER-WRITTEN LEAP core. Sprint 26.2 adds the FULL COLLAR (a DTE-matched
    protective put funded by the covered call) per Decision D-03.

    A long-dated long CALL (a LEAP core) ties up capital while earning nothing
    if it isn't written against — the MONETIZE case the capital-efficiency page
    flags (e.g. AMZN 0.15× / GOOGL 0.25×). This scans the PER-LEG book for LEAP
    cores (long call, DTE > `strategy.leap_core_min_dte`) whose contracts are NOT
    fully covered by an open short call on the same underlying, and for each
    surfaces the adaptive ~0.30Δ / 30–45 DTE covered call the 21.1b engine would
    write — sourced straight from `get_strategy_metrics` (the PMCC short leg) so
    the strike / credit / yield math is the exact tested path the Strategy
    Selector uses (no re-implemented Black-Scholes).

    "Under-written" here is structural: contracts held minus short calls open.
    ADVISORY ONLY — never stages or places an order.
    """
    from ..services.config_store import cfg
    leap_min_dte = int(cfg("strategy.leap_core_min_dte", 90))
    target_dte   = int(cfg("strategy.covered_call_target_dte", 45))
    put_delta    = float(cfg("strategy.collar_put_delta_target", 0.25))

    try:
        data = state.get_active_positions()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    legs = [p for p in (data.get("positions") or [])
            if str(p.get("sec_type") or "OPT").upper() == "OPT"]

    def _qty(p) -> int:
        try:
            return int(p.get("qty") or 0)
        except (TypeError, ValueError):
            return 0

    # Open short-call contracts per ticker (qty < 0, right C) = already written.
    written_by_ticker: dict[str, int] = {}
    for p in legs:
        if str(p.get("right", "")).upper() == "C" and _qty(p) < 0:
            t = (p.get("ticker") or "").upper()
            written_by_ticker[t] = written_by_ticker.get(t, 0) + abs(_qty(p))

    # LEAP cores: long call (qty > 0), long-dated. Sum contracts per ticker,
    # remember the nearest-dated core (the one to write against first).
    cores: dict[str, dict] = {}
    for p in legs:
        if not (str(p.get("right", "")).upper() == "C" and _qty(p) > 0):
            continue
        dte = _dte_days(p.get("expiry")) or 0
        if dte <= leap_min_dte:
            continue  # short-dated long calls aren't LEAP cores
        t = (p.get("ticker") or "").upper()
        core = cores.setdefault(t, {
            "ticker": t, "contracts": 0,
            "nearest_expiry": p.get("expiry"), "nearest_dte": dte,
        })
        core["contracts"] += abs(_qty(p))
        if dte < (core["nearest_dte"] or 10**9):
            core["nearest_dte"], core["nearest_expiry"] = dte, p.get("expiry")

    out = []
    for t, core in cores.items():
        written = written_by_ticker.get(t, 0)
        unwritten = core["contracts"] - written
        if unwritten <= 0:
            continue  # fully covered — nothing to monetize

        rec, note = None, None
        try:
            from app.routes.options import get_strategy_metrics
            sm = get_strategy_metrics(ticker=t, mode="new", target_dte=target_dte)
            pmcc = next((s for s in sm.get("strategies", []) if s.get("id") == "pmcc"), None)
            if pmcc and (pmcc.get("estimated_credit") or 0) > 0:
                rec = {
                    "short_strike":     pmcc.get("short_strike"),
                    "target_delta":     pmcc.get("target_delta"),
                    "target_dte":       target_dte,
                    "estimated_credit": pmcc.get("estimated_credit"),
                    "annualized_yield": pmcc.get("annualized_yield"),
                    "pop":              pmcc.get("pop"),
                    "earnings_safe":    pmcc.get("earnings_safe"),
                    "delta_rationale":  pmcc.get("delta_rationale"),
                    "spot":             sm.get("spot"),
                    "ivr":              sm.get("ivr"),
                    "vol_source":       sm.get("vol_source"),
                }
                # 26.2 — fund a DTE-matched protective put to close the collar.
                iv_dec = (sm.get("iv") or 0) / 100.0   # sm.iv is a percentage
                put_strike, put_debit = _collar_protective_put(
                    sm.get("spot"), iv_dec, target_dte, put_delta)
                if put_strike is not None:
                    net = round((rec["estimated_credit"] or 0) - (put_debit or 0), 2)
                    rec["protective_put"] = {
                        "strike":        put_strike,
                        "debit":         put_debit,
                        "target_delta":  put_delta,
                        "dte":           target_dte,   # matched to the short call
                    }
                    rec["collar_net"] = net            # >0 = net credit, <0 = net debit to establish
                    rec["collar_note"] = (
                        f"collar: sell {rec['short_strike']:.0f}C / buy {put_strike:.0f}P · "
                        f"{'net credit' if net >= 0 else 'net debit'} ${abs(net):.0f} · "
                        f"caps downside below {put_strike:.0f}"
                    )
                if not pmcc.get("earnings_safe"):
                    note = "inside earnings window — defer or size down per Strategy §4"
            else:
                note = "no positive-credit short call (thin premium / degraded chain)"
        except HTTPException as e:
            note = f"strategy_metrics unavailable: {e.detail}"
        except Exception as e:  # never let one bad ticker sink the scan
            note = f"strategy_metrics error: {e}"

        out.append({
            "ticker":              t,
            "leap_contracts":      core["contracts"],
            "short_calls_open":    written,
            "unwritten":           unwritten,
            "nearest_leap_expiry": core["nearest_expiry"],
            "nearest_leap_dte":    core["nearest_dte"],
            "recommended_call":    rec,
            "note":                note,
        })

    # Actionable (has a recommendation) first, then biggest un-monetized core.
    out.sort(key=lambda r: (r.get("recommended_call") is None, -(r.get("unwritten") or 0)))
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "target_dte": target_dte,
        "leap_core_min_dte": leap_min_dte,
        "count": len(out),
        "candidates": out,
    }


@router.post("/manage/cluster_history")
def record_cluster_history(payload: dict | None = None):
    """
    Sprint 25.6 follow-on — persist a daily Mag-7 cluster-% point so the Recovery
    page can draw the concentration *glide line* (not just current-vs-target).

    Upsert-by-date: at most one point per calendar day. A same-day re-post only
    rewrites if the value moved > 0.05pp, so the atomic-write backups stay at
    ~1/day even though the page posts on every load. Body: {"pct": <float>};
    returns {"target", "points":[{date, pct}]}.
    """
    from ..services.config_store import cfg
    target = float(cfg("strategy.cluster_concentration_warn_pct", 60.0))
    try:
        pct = float((payload or {}).get("pct"))
    except (TypeError, ValueError):
        pct = None

    hist = state.read_json("cluster_history.json", {"points": []})
    points = hist.get("points") or []
    if pct is not None:
        today = datetime.now(timezone.utc).date().isoformat()
        last = points[-1] if points else None
        if last and last.get("date") == today:
            if abs(float(last.get("pct", 0)) - pct) > 0.05:
                last["pct"] = round(pct, 1)
                state.write_json("cluster_history.json", {"points": points})
        else:
            points.append({"date": today, "pct": round(pct, 1)})
            points = points[-400:]  # keep ~13 months
            state.write_json("cluster_history.json", {"points": points})
    return {"target": target, "points": points}


@router.get("/manage/cluster_history")
def get_cluster_history():
    """Sprint 25.6 — the stored Mag-7 cluster-% glide series (read-only, no write)."""
    from ..services.config_store import cfg
    target = float(cfg("strategy.cluster_concentration_warn_pct", 60.0))
    hist = state.read_json("cluster_history.json", {"points": []})
    return {"target": target, "points": hist.get("points") or []}


@router.get("/manage/profit_targets")
def profit_targets():
    """
    Sprint 26.3 — manage-at-50% + 21-DTE scan (Decision D-05 + time-discipline).

    Scans OPEN SHORT option legs (the premium-selling / defined-risk sleeve; LEAP
    long-call cores are excluded) and flags any that have (a) captured ≥
    `strategy.profit_target_pct` of the premium received, or (b) decayed to ≤
    `strategy.dte_roll_threshold` DTE — the two systematic close/roll triggers that
    lift capital turnover and cut late-cycle gamma risk. Profit capture uses the
    IBKR entry basis (`avg_cost`) vs current `market_value`; when the entry basis
    isn't synced the row still carries its reliable DTE flag. ADVISORY ONLY.
    """
    from ..services.config_store import cfg
    profit_pct = float(cfg("strategy.profit_target_pct", 50))
    dte_manage = int(cfg("strategy.dte_roll_threshold", 21))

    try:
        data = state.get_active_positions()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    out = []
    for p in (data.get("positions") or []):
        if str(p.get("sec_type") or "OPT").upper() != "OPT":
            continue
        try:
            qty = int(p.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty >= 0:
            continue  # only SHORT premium legs; long/LEAP cores are not profit-managed

        # Fail-safe (2026-07-08): right after a relaunch/pre-sync the position
        # payload can lack option metadata (expiry None, strike unset, right
        # "NONE"). `_dte_days(None) or 0` then read as DTE 0 and false-flagged
        # EVERY short leg "DTE 0 ≤ 21". Missing metadata → SKIP the leg (an
        # advisory scan must under-report, never fabricate an exit signal).
        dte = _dte_days(p.get("expiry"))
        strike = p.get("strike") or state._leg_strike(p)
        right = str(p.get("right") or "").upper()
        if dte is None or strike is None or right not in ("C", "P"):
            continue

        avg_cost = p.get("avg_cost")
        mv = p.get("market_value")
        credit = abs(float(avg_cost)) * abs(qty) if avg_cost not in (None, 0) else None
        capture_pct = None
        if credit and mv is not None:
            try:  # short: received `credit`, pays abs(mv) to close → profit / credit
                capture_pct = round((credit - abs(float(mv))) / credit * 100, 1)
            except (TypeError, ValueError, ZeroDivisionError):
                capture_pct = None

        reasons = []
        if capture_pct is not None and capture_pct >= profit_pct:
            reasons.append(f"{capture_pct:.0f}% of max profit ≥ {profit_pct:.0f}% → close/roll")
        if 0 <= dte <= dte_manage:
            reasons.append(f"DTE {dte} ≤ {dte_manage} → time-manage (gamma)")
        if not reasons:
            continue
        out.append({
            "ticker":     (p.get("ticker") or "").upper(),
            "right":      right,
            "strike":     strike,
            "expiry":     p.get("expiry"),
            "dte":        dte,
            "qty":        qty,
            "capture_pct": capture_pct,
            "action":     "MANAGE",
            "reasons":    reasons,
        })
    out.sort(key=lambda r: (r.get("dte") if r.get("dte") is not None else 9999,
                            -(r.get("capture_pct") or 0)))
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "profit_target_pct": profit_pct,
        "dte_roll_threshold": dte_manage,
        "count": len(out),
        "positions": out,
    }


@router.get("/manage/risk_limits")
def risk_limits():
    """
    Sprint 26.1 (Health Manager) — margin-debt & liquidity risk monitor.

    Surfaces the two hard account risk limits — the USD-cash margin-debt floor
    and the Excess-Liquidity floor (Decision D-06) — with breach flags, plus a
    stale-data check (sync age vs the configured budget). Read by the
    `margin-debt-alert` scheduled task and the dashboard. Fail-safe: a missing
    value reads as unknown, never as "within limits". ADVISORY / read-only.
    """
    from ..services.config_store import cfg
    cash_floor   = float(cfg("strategy.margin_debt_limit_usd", -15000.0))
    excess_floor = float(cfg("strategy.excess_liq_min_usd", 25000.0))
    stale_min    = int(cfg("strategy.data_stale_minutes", 30))

    try:
        data = state.get_active_positions()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))
    pos = data if isinstance(data, dict) else {}

    def _first(*keys):
        for k in keys:
            v = pos.get(k)
            if v is not None:
                return v
        return None

    # The IBKR sync writer is out-of-mount and field names vary by sync path
    # (ledger vs position-only vs bs fallback), so probe the known aliases. Cash
    # typically only populates under an authenticated ledger sync — when it's
    # absent the monitor fail-safes to unknown (never "within limits").
    base_cash  = _first("base_cash", "cash", "cashbalance", "total_cash",
                        "usd_cash", "settled_cash", "totalcashvalue")
    excess_liq = _first("excess_liq", "excess_liquidity")

    synced = _first("synced_at", "_ibkr_sync_time", "ocr_last_sync", "last_sync", "updated_at")
    age_min = None
    stale = None
    if synced:
        try:
            ts = datetime.fromisoformat(str(synced).replace("Z", "+00:00"))
            age_min = round((datetime.now(timezone.utc) - ts).total_seconds() / 60.0, 1)
            stale = age_min > stale_min
        except (ValueError, TypeError):
            pass

    cash_breach = base_cash is not None and float(base_cash) < cash_floor
    liq_breach  = excess_liq is not None and float(excess_liq) < excess_floor
    return {
        "as_of":             datetime.now(timezone.utc).isoformat(),
        "net_liq":           pos.get("net_liq"),
        "usd_cash":          base_cash,
        "cash_floor":        cash_floor,
        "cash_breach":       cash_breach,
        "excess_liq":        excess_liq,
        "excess_floor":      excess_floor,
        "excess_liq_breach": liq_breach,
        "data_age_min":      age_min,
        "stale_data":        stale,
        "any_breach":        bool(cash_breach or liq_breach),
        "status":            "🔴 BREACH" if (cash_breach or liq_breach) else "🟢 within limits",
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
# Sprint 16.1 — Consolidated advisory layer (macro-defer + VIX-term + ex-div)
# ---------------------------------------------------------------------------
# These are ADVISORY sub-flags, deliberately kept separate from the five hard
# gates: they never change the PROCEED/BLOCKED verdict, they only raise an amber
# `caution` so Candidates/Triage can surface a "heads-up" chip. Each source is
# soft-failed independently — a dead route degrades that one flag to `unknown`,
# never the whole gate. macro_defer and vix_term are market-wide; ex_div is
# filtered to the requested ticker's short-call legs.

def _market_advisories() -> dict:
    """Fetch the market-wide advisory inputs ONCE (so the batch endpoint doesn't
    re-hit them per ticker). Returns the macro_defer + vix_term advisory dicts and
    an ex-div-risk map keyed by ticker. Each source soft-fails to `unknown`."""
    # ── Macro binary-event defer ──────────────────────────────────────────────
    try:
        from ..routes.options_analytics import get_macro_events
        m = get_macro_events()
        if m.get("error"):
            macro_adv = {"name": "macro_defer", "level": "unknown", "detail": "macro events unavailable"}
        else:
            defer = bool(m.get("defer_advisory"))
            macro_adv = {
                "name": "macro_defer",
                "level": "amber" if defer else "ok",
                "detail": m.get("defer_reason") or "No high-impact macro event in the defer window",
                "nearest_high_impact": m.get("nearest_high_impact"),
            }
    except Exception as e:
        macro_adv = {"name": "macro_defer", "level": "unknown", "detail": str(e)}

    # ── VIX term-structure ────────────────────────────────────────────────────
    try:
        from ..routes.options_analytics import get_vix_term
        v = get_vix_term()
        if v.get("error"):
            vix_adv = {"name": "vix_term", "level": "unknown", "detail": "VIX term unavailable"}
        else:
            st = v.get("state")
            vix_adv = {
                "name": "vix_term",
                "level": "amber" if st == "backwardation" else "ok",
                "detail": v.get("signal") or f"VIX term: {st}",
                "state": st, "ratio": v.get("ratio"),
            }
    except Exception as e:
        vix_adv = {"name": "vix_term", "level": "unknown", "detail": str(e)}

    # ── Ex-div assignment risk (all tickers in one call) ─────────────────────
    exdiv_by_ticker: dict[str, list] = {}
    exdiv_ok = True
    try:
        from ..routes.options_analytics import get_ex_div
        x = get_ex_div()
        if x.get("error"):
            exdiv_ok = False
        else:
            for r in x.get("assignment_risks", []):
                exdiv_by_ticker.setdefault(str(r.get("ticker", "")).upper(), []).append(r)
    except Exception:
        exdiv_ok = False

    # ── VRP (variance risk premium = IV − HV20) per ticker, from the IV-crush scan ─
    # Sprint 19.3: a high IVR with thin/negative IV−HV means little real edge
    # (Strategy v3.10 §3). Reuses the scanner's spread_pp (real since Sprint 18).
    vrp_by_ticker: dict[str, float] = {}
    vrp_min = 3.0
    try:
        from ..services.config_store import cfg
        vrp_min = float(cfg("strategy.vrp_min_entry_pp", 3.0))
    except Exception:
        pass
    try:
        rep = state.get_iv_crush_report()
        for r in rep.get("rows", []):
            tk = str(r.get("ticker", "")).upper()
            sp = r.get("spread_pp")
            if tk and sp is not None:
                vrp_by_ticker[tk] = float(sp)
    except Exception:
        pass

    # ── Concentration (Sprint 21.5) — single-name + Mag-7 cluster, warn-mode ──
    # Canonical MV/NLV basis (Sprint 20.4). Computed ONCE here so the per-ticker
    # advisory is a cheap dict lookup in the batch endpoint.
    conc_map: dict[str, float] = {}
    cluster_pct: float | None = None
    single_cap, cluster_cap, conc_mode = 20.0, 60.0, "warn"
    cluster_names: list[str] = []
    try:
        from ..services.config_store import cfg
        single_cap = float(cfg("strategy.single_name_cap_pct", 20.0))
        cluster_cap = float(cfg("strategy.cluster_cap_pct", 60.0))
        conc_mode = cfg("strategy.concentration_gate_mode", "warn") or "warn"
        cluster_names = [str(t).upper() for t in (cfg("strategy.mag7_cluster", []) or [])]
    except Exception:
        pass
    try:
        _pd = state.get_active_positions()
        conc_map = {str(k).upper(): float(v) for k, v in (state.compute_concentration(_pd) or {}).items()}
        if cluster_names:
            cluster_pct = round(sum(conc_map.get(n, 0.0) for n in cluster_names), 1)
    except Exception:
        pass

    return {"macro": macro_adv, "vix": vix_adv,
            "exdiv_by_ticker": exdiv_by_ticker, "exdiv_ok": exdiv_ok,
            "vrp_by_ticker": vrp_by_ticker, "vrp_min": vrp_min,
            "conc_map": conc_map, "cluster_pct": cluster_pct,
            "single_name_cap": single_cap, "cluster_cap": cluster_cap,
            "conc_mode": conc_mode, "cluster_names": cluster_names}


def _exdiv_advisory(ticker: str, market: dict) -> dict:
    """Build the ticker-specific ex-div advisory from prefetched market data."""
    if not market.get("exdiv_ok"):
        return {"name": "ex_div", "level": "unknown", "detail": "ex-div store unavailable"}
    mine = market["exdiv_by_ticker"].get(ticker.upper(), [])
    if mine:
        worst = "high" if any(r.get("severity") == "high" for r in mine) else "watch"
        return {"name": "ex_div", "level": "amber",
                "detail": mine[0].get("note") or f"{len(mine)} ex-div assignment risk(s) on {ticker}",
                "severity": worst, "risks": mine}
    return {"name": "ex_div", "level": "ok",
            "detail": f"No ex-div assignment risk on {ticker} short calls"}


def _vrp_advisory(ticker: str, market: dict) -> dict:
    """Variance-risk-premium (IV − HV20) edge advisory (Strategy v3.10 §3).
    Thin/negative VRP means selling premium here has little real edge even when
    IVR looks high. Advisory only — never blocks."""
    vrp = market.get("vrp_by_ticker", {}).get(ticker.upper())
    vrp_min = market.get("vrp_min", 3.0)
    if vrp is None:
        return {"name": "vrp", "level": "unknown",
                "detail": "no IV−HV data for this ticker (run refresh_iv_data)"}
    if vrp < vrp_min:
        return {"name": "vrp", "level": "amber",
                "detail": f"IV−HV20 {vrp:+.1f}pp < {vrp_min:.0f}pp floor — thin variance-risk premium; the IVR edge may be illusory",
                "spread_pp": vrp, "min_pp": vrp_min}
    return {"name": "vrp", "level": "ok",
            "detail": f"IV−HV20 {vrp:+.1f}pp ≥ {vrp_min:.0f}pp — real premium-selling edge",
            "spread_pp": vrp, "min_pp": vrp_min}


def _concentration_advisory(ticker: str, market: dict) -> dict:
    """Single-name + Mag-7 cluster concentration advisory (Sprint 21.5).

    Warn-mode by default (never blocks unless `strategy.concentration_gate_mode`
    is set to 'block'). Uses the canonical MV/NLV basis (Sprint 20.4). Flags amber
    when the name is already at/over the single-name cap, or when the name is a
    cluster member and the Mag-7 cluster is already at/over its cap — in both cases
    a new entry only worsens an over-concentrated book (the recovery-plan risk the
    briefing reports but the pre-trade gate didn't catch)."""
    cap = market.get("single_name_cap", 20.0)
    ccap = market.get("cluster_cap", 60.0)
    name_pct = market.get("conc_map", {}).get(ticker.upper(), 0.0)
    cluster_pct = market.get("cluster_pct")
    in_cluster = ticker.upper() in market.get("cluster_names", [])
    reasons = []
    if name_pct >= cap:
        reasons.append(f"{ticker} {name_pct:.0f}% ≥ {cap:.0f}% single-name cap")
    if in_cluster and cluster_pct is not None and cluster_pct >= ccap:
        reasons.append(f"Mag-7 cluster {cluster_pct:.0f}% ≥ {ccap:.0f}% cap")
    if reasons:
        return {"name": "concentration", "level": "amber",
                "detail": "; ".join(reasons) + " — a new position adds to an over-concentrated book",
                "name_pct": round(name_pct, 1), "cluster_pct": cluster_pct,
                "single_name_cap": cap, "cluster_cap": ccap,
                "in_cluster": in_cluster, "mode": market.get("conc_mode", "warn")}
    return {"name": "concentration", "level": "ok",
            "detail": (f"{ticker} {name_pct:.0f}% (cap {cap:.0f}%)"
                       + (f", cluster {cluster_pct:.0f}% (cap {ccap:.0f}%)" if cluster_pct is not None else "")),
            "name_pct": round(name_pct, 1), "cluster_pct": cluster_pct,
            "single_name_cap": cap, "cluster_cap": ccap, "in_cluster": in_cluster}


def _trend_advisory(ticker: str) -> dict:
    """Weekly-200-SMA 'Thesis Stop' entry advisory (Sprint 21.4, warn-mode).

    Amber when spot is below the weekly 200-SMA — the structural downtrend where
    premium-selling win-rate collapses (the 25% cohort). Insufficient weekly
    history → soft-fails to `unknown` (never a breach). Ticker-specific; the
    weekly read is TTL-cached in options_analytics."""
    try:
        from ..routes.options_analytics import weekly_trend_state
        w = weekly_trend_state(ticker)
    except Exception as e:
        return {"name": "trend", "level": "unknown", "detail": f"weekly trend unavailable: {e}"}
    if w.get("above_200w") is None:
        return {"name": "trend", "level": "unknown",
                "detail": w.get("error") or "insufficient weekly history"}
    pct = w.get("pct_from_sma")
    pct_s = f"{pct:+.0f}%" if pct is not None else "n/a"
    if not w["above_200w"]:
        return {"name": "trend", "level": "amber",
                "detail": f"{ticker} ${w['spot']} below weekly 200-SMA ${w['sma_200w']} ({pct_s}) — Thesis Stop; premium-selling win-rate is poor below the weekly 200",
                "spot": w["spot"], "sma_200w": w["sma_200w"], "above_200w": False, "pct_from_sma": pct}
    return {"name": "trend", "level": "ok",
            "detail": f"{ticker} ${w['spot']} above weekly 200-SMA ${w['sma_200w']} ({pct_s})",
            "spot": w["spot"], "sma_200w": w["sma_200w"], "above_200w": True, "pct_from_sma": pct}


def _pretrade_advisories(ticker: str, market: dict | None = None) -> dict:
    """Return {advisories:{name:..}, caution:bool, caution_flags:[]} for a ticker.

    level ∈ {ok, amber, unknown}. caution = any amber. Pass `market` (from
    _market_advisories) to reuse one fetch across many tickers; omit for a single
    lookup. macro_defer/vix_term/concentration are market-wide; ex_div/trend are
    ticker-specific.
    """
    ticker = (ticker or "").upper().strip()
    if market is None:
        market = _market_advisories()
    items = [market["macro"], market["vix"], _exdiv_advisory(ticker, market),
             _vrp_advisory(ticker, market), _concentration_advisory(ticker, market),
             _trend_advisory(ticker)]
    return {
        "advisories": {a["name"]: a for a in items},
        "caution": any(a["level"] == "amber" for a in items),
        "caution_flags": [a["name"] for a in items if a["level"] == "amber"],
    }


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
    earnings_state = state.earnings_state_from_days(days_to_earnings)
    earnings_passed = earnings_state != "blackout"
    gate_earnings = {
        "name": "earnings_blackout",
        "rule": "Strategy §4 — no entry within 10 days of earnings",
        "passed": earnings_passed,
        "detail": (
            f"Earnings in {days_to_earnings}d — {earnings_state}"
            if days_to_earnings is not None
            else "⚠ No earnings date found — UNVERIFIED, confirm via get_earnings_history before sizing (scanner-null fix)"
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

    adv = _pretrade_advisories(ticker)

    return {
        "ticker": ticker,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "all_passed": all_passed,
        "gates": {g["name"]: g for g in gates},
        "hard_failures": [g["name"] for g in hard_failures],
        "acknowledgment_required": not all_passed,
        # Sprint 16.1 — advisory sub-flags (non-blocking; amber = heads-up)
        "advisories": adv["advisories"],
        "caution": adv["caution"],
        "caution_flags": adv["caution_flags"],
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

    # Sprint 16.1 — fetch market-wide advisories once, reuse per ticker
    market_adv = _market_advisories()

    results = []
    for ticker in tickers:
        conc_pct = concentration.get(ticker, 0.0)
        days_to_earnings = state.days_to_earnings(ticker, calendar)
        earnings_state = state.earnings_state_from_days(days_to_earnings)

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

        adv = _pretrade_advisories(ticker, market_adv)
        # Scanner-null fix: unknown earnings date = advisory caution, never a block.
        caution_flags = list(adv["caution_flags"])
        if earnings_state == "unverified":
            caution_flags.append("earnings_unverified")

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
            # Sprint 16.1 — advisory caution (non-blocking)
            "caution": bool(adv["caution"]) or earnings_state == "unverified",
            "caution_flags": caution_flags,
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
            "caution": sum(1 for r in results if r.get("caution")),
            "vix": round(vix, 1),
            "vix_regime": macro.get("vix_state", "unknown"),
        },
        # Sprint 16.1 — market-wide advisories (apply to all tickers)
        "market_advisories": {"macro_defer": market_adv["macro"], "vix_term": market_adv["vix"]},
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
        earnings_state = state.earnings_state_from_days(days_to_earnings)

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
    # OR were dismissed within the last 4 hours (cooldown to prevent re-fire spam).
    _now = datetime.now(timezone.utc)
    _cooldown_hours = 4
    alerted_tickers = set()
    for a in existing_alerts:
        if a.get("source") != "position_monitor":
            continue
        ticker_key = (a.get("ticker") or "").upper()
        if not ticker_key:
            continue
        # Always suppress if currently active
        if not a.get("snoozed", False):
            alerted_tickers.add(ticker_key)
            continue
        # Suppress recently-dismissed alerts within cooldown window
        dismissed_at_str = a.get("snoozed_at") or a.get("created_at") or ""
        if dismissed_at_str:
            try:
                dismissed_at = datetime.fromisoformat(dismissed_at_str.replace("Z", "+00:00"))
                if dismissed_at.tzinfo is None:
                    dismissed_at = dismissed_at.replace(tzinfo=timezone.utc)
                hours_ago = (_now - dismissed_at).total_seconds() / 3600
                if hours_ago < _cooldown_hours:
                    alerted_tickers.add(ticker_key)
            except Exception:
                pass

    new_alerts = []

    for pos in aggregated:
        ticker = (pos.get("ticker") or "").upper()
        if not ticker or ticker in alerted_tickers:
            continue

        _strat = (pos.get("strategy") or "").upper()
        # LEAPS, SPY_HEDGE, and STOCK are never stop-loss or roll candidates
        # from the position monitor — they are intentional long-dated / protective positions.
        if _strat in ("LEAPS", "SPY_HEDGE", "STOCK"):
            continue
        # For PMCC and DIAGONAL, only fire alerts when there is an active short call leg.
        _legs = pos.get("legs") or []
        _has_real_short_call = any(
            (l.get("right") or "") == "C" and (l.get("qty") or 0) < 0
            for l in _legs
        )
        # For positions stored without legs (single-leg rows), fall back to qty sign
        if not _legs:
            _pos_qty = pos.get("qty") or 0
            _pos_right = (pos.get("right") or "").upper()
            _has_real_short_call = _pos_qty < 0 and _pos_right == "C"
        # PMCC/DIAGONAL without a short call overlay — skip entirely
        if _strat in ("PMCC", "DIAGONAL") and not _has_real_short_call:
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
    if cached and cached.get("legs_count", 0) > 0:
        return {**cached, "source": "ibkr_sync_cached"}

    target_min = 20000
    target_max = 30000
    hedge_mv = 0.0
    legs = 0
    for p in data.get("positions", []):
        _strat  = (p.get("strategy") or "").upper()
        _ticker = (p.get("ticker") or "").upper()
        _right  = (p.get("right") or "").upper()
        # Classify as hedge if explicitly tagged OR is an untagged SPY put
        # (covers bear-put-spread legs that arrive without a strategy tag)
        _is_hedge = (_strat == "SPY_HEDGE") or (_ticker == "SPY" and _right == "P")
        if _is_hedge:
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


# ─── Dashboard hydration cache (written by Python scripts post-execution) ────

from typing import Dict, Any
import threading

_hydration_cache: Dict[str, Dict[str, Any]] = {}
_hydration_lock = threading.Lock()


class HydrateAssetRequest(BaseModel):
    ticker: str
    gex_call_wall: Optional[float] = None
    gex_put_wall: Optional[float] = None
    dp_floor: Optional[float] = None
    net_drift: Optional[float] = None
    gamma_flip: Optional[float] = None
    timestamp: Optional[str] = None


@router.post("/manage/hydrate-asset")
def hydrate_asset(payload: HydrateAssetRequest):
    """
    Called by Python scripts (max_pain.py, whale_flow.py) after execution.
    Stores GEX/DP/drift values in an in-memory cache so the frontend can
    overlay them when live QuantData fields are blank.
    No auth required — only callable from localhost (middleware exempted).
    """
    from datetime import datetime, timezone
    ticker = payload.ticker.upper()
    entry = {
        "ticker": ticker,
        "gex_call_wall": payload.gex_call_wall,
        "gex_put_wall": payload.gex_put_wall,
        "dp_floor": payload.dp_floor,
        "net_drift": payload.net_drift,
        "gamma_flip": payload.gamma_flip,
        "timestamp": payload.timestamp or datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    with _hydration_lock:
        _hydration_cache[ticker] = entry
    return {"success": True, "message": f"Cache hydrated for {ticker}"}


@router.get("/manage/hydrated-assets")
def get_hydrated_assets():
    """
    Returns all currently cached hydrated asset entries.
    Frontend polls this to overlay cached values when QuantData fields are blank.
    No auth required — served via nginx proxy to the browser.
    """
    with _hydration_lock:
        assets = list(_hydration_cache.values())
    return {"assets": assets}


# ---------------------------------------------------------------------------
# Bearer Token Rotation
# ---------------------------------------------------------------------------
import uuid
import subprocess
import re

TOKEN_FILE = '/home/ubuntu/.fortress_api_token'
OVERRIDE_FILE = '/etc/systemd/system/fortress-dashboard.service.d/override.conf'

@router.post('/manage/rotate-token')
def rotate_token():
    """
    Generates a new 48-char hex bearer token.
    1. Writes the new token to /home/ubuntu/.fortress_api_token (ubuntu-owned).
    2. Updates the systemd override via 'sudo tee' (ubuntu has NOPASSWD:ALL).
    3. Runs 'sudo systemctl daemon-reload && sudo systemctl restart fortress-dashboard'.
    Returns the new token so the browser can save it immediately.
    """
    new_token = uuid.uuid4().hex + uuid.uuid4().hex[:16]
    try:
        # Step 1: write token file (ubuntu-owned, no sudo needed)
        with open(TOKEN_FILE, 'w') as f:
            f.write(new_token)

        # Step 2: update systemd override using sudo tee
        with open(OVERRIDE_FILE, 'r') as f:
            content = f.read()
        new_content = re.sub(
            r'(Environment="FORTRESS_API_TOKEN=)[^"]*(")' ,
            rf'\g<1>{new_token}\g<2>',
            content,
        )
        if new_content == content:
            new_content += f'\nEnvironment="FORTRESS_API_TOKEN={new_token}"\n'
        result = subprocess.run(
            ['sudo', 'tee', OVERRIDE_FILE],
            input=new_content.encode(),
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f'sudo tee failed: {result.stderr.decode()}')

        # Step 3: reload systemd and restart service
        subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
        # Fire-and-forget restart: the service kills itself (SIGTERM) so we can't use check=True
        subprocess.Popen(['sudo', 'systemctl', 'restart', 'fortress-dashboard'])

        return {
            'ok': True,
            'new_token': new_token,
            'message': 'Token rotated. Service restarting — reconnect with the new token.',
        }
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f'Token rotation failed: {e}')
