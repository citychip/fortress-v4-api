"""
app/services/roll.py — Roll Candidate Evaluator (Strategy §5)

DTE and delta bands now read from config_store instead of hardcoded constants.
"""
from __future__ import annotations
from datetime import date
from typing import Optional
from app.services.config_store import cfg


def _dte(expiry_str: str) -> Optional[int]:
    """Calculate days to expiry from an ISO date string."""
    try:
        exp = date.fromisoformat(expiry_str)
        return max(0, (exp - date.today()).days)
    except (ValueError, TypeError):
        return None


def _label_candidate(delta: float, dte: int) -> str:
    """Label a roll candidate based on how it compares to the target bands."""
    low  = cfg("strategy.target_delta_low", 0.20)
    high = cfg("strategy.target_delta_high", 0.25)
    dte_low  = cfg("strategy.target_dte_low", 30)
    dte_high = cfg("strategy.target_dte_high", 45)

    in_delta_band = low <= delta <= high
    in_dte_band   = dte_low <= dte <= dte_high

    if in_delta_band and in_dte_band:
        return "IDEAL"
    if delta < low or dte > dte_high:
        return "CONSERVATIVE"
    return "AGGRESSIVE"


def _framework_score(delta: float, dte: int) -> float:
    """
    Score a candidate by proximity to the centre of the target bands.
    Lower score = closer to ideal. Used to rank candidates.
    """
    low  = cfg("strategy.target_delta_low", 0.20)
    high = cfg("strategy.target_delta_high", 0.25)
    dte_low  = cfg("strategy.target_dte_low", 30)
    dte_high = cfg("strategy.target_dte_high", 45)

    delta_center = (low + high) / 2
    dte_center   = (dte_low + dte_high) / 2

    delta_score = abs(delta - delta_center) / (high - low) if (high - low) else 0
    dte_score   = abs(dte - dte_center) / (dte_high - dte_low) if (dte_high - dte_low) else 0
    return round(delta_score + dte_score, 4)


def evaluate_roll(
    position: dict,
    chain: Optional[list[dict]] = None,
    target_dte: Optional[tuple[int, int]] = None,
    target_delta: Optional[tuple[float, float]] = None,
) -> dict:
    """
    Evaluate roll candidates for a position.

    Args:
        position: dict with ticker, short_strike, expiry, qty
        chain: optional pre-fetched option chain; if None, evaluation is
               based on position data only (no live chain candidates)
        target_dte: override (low, high) — defaults to config values
        target_delta: override (low, high) — defaults to config values

    Returns:
        dict with roll_needed, urgency, candidates, and thresholds_used
    """
    ticker  = (position.get("ticker") or "").upper()
    expiry  = position.get("expiry") or position.get("short_expiry")
    current_delta = position.get("current_delta")

    # Use overrides if provided, else read from config
    dte_low   = target_dte[0]   if target_dte   else cfg("strategy.target_dte_low", 30)
    dte_high  = target_dte[1]   if target_dte   else cfg("strategy.target_dte_high", 45)
    delta_low = target_delta[0] if target_delta else cfg("strategy.target_delta_low", 0.20)
    delta_high= target_delta[1] if target_delta else cfg("strategy.target_delta_high", 0.25)

    dte_urgent  = cfg("alerts.dte_urgent_days", 14)
    dte_warning = cfg("alerts.dte_warning_days", 21)

    current_dte = _dte(expiry) if expiry else None

    # ── DTE exception registry ────────────────────────────────────────────
    # Positions listed in strategy.dte_exceptions as "TICKER:YYYY-MM-DD" are
    # exempt from DTE-based roll alerts (e.g. intentional long-dated PMCC legs).
    dte_exceptions: list[str] = cfg("strategy.dte_exceptions") or []
    exception_key = f"{ticker}:{expiry}" if expiry else None
    dte_exempt = exception_key is not None and exception_key in dte_exceptions

    # ── Roll urgency ─────────────────────────────────────────────────────
    roll_needed = False
    urgency = "NONE"
    reasons: list[str] = []

    if current_dte is not None and not dte_exempt:
        if current_dte <= dte_urgent:
            roll_needed = True
            urgency = "URGENT"
            reasons.append(f"DTE {current_dte} ≤ urgent threshold {dte_urgent}")
        elif current_dte <= dte_warning:
            roll_needed = True
            urgency = "WARNING"
            reasons.append(f"DTE {current_dte} ≤ warning threshold {dte_warning}")
        elif current_dte <= dte_low:
            roll_needed = True
            urgency = "APPROACHING"
            reasons.append(f"DTE {current_dte} ≤ target DTE low {dte_low}")

    # Delta roll signals only apply to positions with an active short leg.
    # LEAPS (long call only) and STOCK positions have high delta by design.
    _strategy = (position.get("strategy") or "").upper()
    _skip_delta_roll = _strategy in ("LEAPS", "SPY_HEDGE", "STOCK")
    if current_delta is not None and not _skip_delta_roll:
        abs_d = abs(float(current_delta))
        if abs_d > cfg("strategy.delta_critical_threshold", 0.40):
            roll_needed = True
            urgency = "URGENT" if urgency != "URGENT" else urgency
            reasons.append(f"Delta {abs_d:.2f} above critical threshold")
        elif abs_d > delta_high:
            roll_needed = True
            urgency = urgency if urgency in ("URGENT",) else "WARNING"
            reasons.append(f"Delta {abs_d:.2f} above target band high {delta_high:.2f}")

    # ── Candidate scoring (if chain provided) ─────────────────────────────
    candidates: list[dict] = []
    if chain:
        for opt in chain:
            opt_delta = opt.get("delta")
            opt_expiry = opt.get("expiry")
            if opt_delta is None or opt_expiry is None:
                continue
            opt_dte = _dte(opt_expiry)
            if opt_dte is None:
                continue
            if not (dte_low <= opt_dte <= dte_high):
                continue
            if not (delta_low <= abs(float(opt_delta)) <= delta_high):
                continue
            candidates.append({
                "strike":  opt.get("strike"),
                "expiry":  opt_expiry,
                "dte":     opt_dte,
                "delta":   opt_delta,
                "bid":     opt.get("bid"),
                "ask":     opt.get("ask"),
                "mid":     opt.get("mid"),
                "label":   _label_candidate(abs(float(opt_delta)), opt_dte),
                "score":   _framework_score(abs(float(opt_delta)), opt_dte),
            })
        candidates.sort(key=lambda c: c["score"])

    return {
        "ticker":       ticker,
        "roll_needed":  roll_needed,
        "urgency":      urgency,
        "reasons":      reasons,
        "current_dte":  current_dte,
        "current_delta": current_delta,
        "dte_exempt":   dte_exempt,
        "candidates":   candidates[:10],  # top 10
        "thresholds_used": {
            "target_dte":       (dte_low, dte_high),
            "target_delta":     (delta_low, delta_high),
            "dte_urgent":       dte_urgent,
            "dte_warning":      dte_warning,
        },
    }
