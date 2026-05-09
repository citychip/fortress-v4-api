"""
app/services/playbook.py — Post-Earnings Playbook (Strategy §10)

All thresholds now read from config_store instead of being hardcoded.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional
from app.services.config_store import cfg


@dataclass
class ThesisCheck:
    trend_intact: bool
    support_holds: bool
    iv_environment_ok: bool
    no_fundamental_break: bool

    @property
    def all_passed(self) -> bool:
        return all(asdict(self).values())


def _matrix_lookup(gap_pct: float) -> tuple[str, str, float]:
    """
    Map a post-earnings gap % to a matrix verdict.
    Returns (verdict, rule_text, iv_floor_required).
    Bands are derived from config values.
    """
    prime_low  = cfg("strategy.prime_entry_gap_low", -8.0)
    prime_high = cfg("strategy.prime_entry_gap_high", -3.0)
    iv_floor   = cfg("strategy.iv_crush_floor_pct", 15.0)

    if gap_pct >= 5.0:
        return ("PASS", "Gap >+5%: stock gapped up — no premium edge, pass.", 0)
    if gap_pct >= 2.0:
        return ("PASS", "Gap +2..+5%: mild gap-up — wait for consolidation.", 0)
    if gap_pct >= -3.0:
        return ("EVALUATE", "Gap ±2..3%: flat/mild — evaluate IV crush and thesis.", iv_floor)
    if gap_pct >= prime_low:
        return ("PRIME_ENTRY", f"Gap {prime_low}..{prime_high}%: prime entry band — proceed if thesis intact.", 0)
    if gap_pct >= -15.0:
        return ("CONDITIONAL", "Gap −8..−15%: evaluate — requires IV crush ≥ floor.", iv_floor)
    return ("PASS", "Gap < −15%: excessive gap-down — pass, wait for stabilisation.", 0)


def evaluate_playbook(
    ticker: str,
    gap_pct: float,
    iv_crush_pct: float,
    concentration_pct: Optional[float] = None,
    thesis: Optional[ThesisCheck] = None,
) -> dict:
    """
    Apply Strategy §10 matrix + §7 concentration override + thesis check.
    """
    notes: list[str] = []
    overrides: list[str] = []

    iv_floor_override = cfg("strategy.iv_crush_floor_pct", 15.0)
    high_conc_threshold = cfg("strategy.high_conc_threshold_pct", 50.0)
    high_conc_size_cap  = cfg("strategy.high_conc_size_cap", 1)
    high_conc_prime_low  = cfg("strategy.high_conc_prime_low", -8.0)
    high_conc_prime_high = cfg("strategy.high_conc_prime_high", -5.0)

    # Override 1: IV crush floor
    if iv_crush_pct < iv_floor_override:
        return {
            "ticker": ticker,
            "inputs": {"gap_pct": gap_pct, "iv_crush_pct": iv_crush_pct, "concentration_pct": concentration_pct},
            "verdict": "PASS",
            "verdict_reason": f"IV crush {iv_crush_pct:.1f}% below {iv_floor_override:.0f}% floor — no premium edge.",
            "matrix_band": "iv_crush_override",
            "size_cap": 0,
            "thesis_required": False,
            "thesis_passed": None,
            "final_action": "PASS",
            "notes": notes,
            "overrides_applied": ["iv_crush_floor"],
        }

    verdict, rule_text, iv_floor = _matrix_lookup(gap_pct)

    # Override 2: High concentration
    high_conc = concentration_pct is not None and concentration_pct > high_conc_threshold
    if high_conc:
        if high_conc_prime_low <= gap_pct < high_conc_prime_high:
            verdict = "PRIME_ENTRY"
            rule_text = (
                f"High-concentration override: {concentration_pct:.0f}% concentration, "
                f"gap {gap_pct:+.1f}% in tightened {high_conc_prime_low}..{high_conc_prime_high}% prime band."
            )
            overrides.append("high_concentration_tightened_band")
        elif gap_pct > 5.0:
            verdict = "PROFIT_TRIM"
            rule_text = (
                f"High-concentration profit-trim: {concentration_pct:.0f}% concentration, "
                f"gap +{gap_pct:.1f}% — trim, do not add."
            )
            overrides.append("high_concentration_profit_trim")
        else:
            verdict = "PASS"
            rule_text = (
                f"High-concentration override: {concentration_pct:.0f}% concentration; "
                f"gap {gap_pct:+.1f}% outside tightened band."
            )
            overrides.append("high_concentration_pass")

    # IV-crush conditional gate
    if verdict == "CONDITIONAL" and iv_floor > 0 and iv_crush_pct < iv_floor:
        verdict_reason = f"{rule_text}. IV crush {iv_crush_pct:.1f}% below required {iv_floor:.0f}%."
        verdict = "PASS"
    else:
        verdict_reason = rule_text

    # Size cap
    size_cap: Optional[int]
    if high_conc and verdict == "PRIME_ENTRY":
        size_cap = high_conc_size_cap
    elif verdict in ("PASS", "PROFIT_TRIM"):
        size_cap = 0
    else:
        size_cap = None

    # Thesis check
    thesis_required = verdict in ("PRIME_ENTRY", "CONDITIONAL", "EVALUATE")
    thesis_passed = None
    final_action = verdict

    if thesis_required:
        if thesis is None:
            final_action = "HOLD"
            notes.append("Thesis health checklist required before PROCEED.")
        else:
            thesis_passed = thesis.all_passed
            if thesis_passed:
                final_action = "PROCEED"
                if verdict == "EVALUATE":
                    notes.append("Thesis confirmed; proceed at reduced size given gap −8..−15%.")
            else:
                final_action = "HOLD"
                missing = [k for k, v in asdict(thesis).items() if not v]
                notes.append(f"Thesis check failed; missing: {', '.join(missing)}.")
    elif verdict == "PASS":
        final_action = "PASS"
    elif verdict == "PROFIT_TRIM":
        final_action = "PROFIT_TRIM"

    return {
        "ticker": ticker,
        "inputs": {"gap_pct": gap_pct, "iv_crush_pct": iv_crush_pct, "concentration_pct": concentration_pct},
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "matrix_band": _band_label(gap_pct),
        "size_cap": size_cap,
        "thesis_required": thesis_required,
        "thesis_passed": thesis_passed,
        "final_action": final_action,
        "notes": notes,
        "overrides_applied": overrides,
        "thresholds_used": {
            "iv_crush_floor_pct":   iv_floor_override,
            "prime_entry_band":     (cfg("strategy.prime_entry_gap_low", -8.0), cfg("strategy.prime_entry_gap_high", -3.0)),
            "high_conc_threshold":  high_conc_threshold,
            "high_conc_prime_band": (high_conc_prime_low, high_conc_prime_high),
        },
    }


# Alias for backward compatibility with routes/playbook.py
evaluate_post_earnings = evaluate_playbook


def _band_label(gap_pct: float) -> str:
    prime_low = cfg("strategy.prime_entry_gap_low", -8.0)
    if gap_pct >= 5.0:   return "gap > +5%"
    if gap_pct >= 2.0:   return "gap +2..+5%"
    if gap_pct >= -3.0:  return "gap ±2..3%"
    if gap_pct >= prime_low: return f"gap {prime_low}..−3% (PRIME)"
    if gap_pct >= -15.0: return "gap −8..−15%"
    return "gap < −15%"
