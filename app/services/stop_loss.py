"""
app/services/stop_loss.py — Stop-Loss Aggregator (Strategy §6)

All thresholds now read from config_store instead of being hardcoded.
"""
from __future__ import annotations
import re
from typing import Optional
from app.services.config_store import cfg


def parse_dp_floors_from_daily_report(content: str) -> dict[str, list[float]]:
    """
    Parse '### {TICKER} Execution Profile' sections from QuantData Daily Report.
    Each section has a 'Dark Pool Hard Floors:' line with $-prefixed prices.
    Returns {ticker: [floor1, floor2, ...]} sorted descending.
    """
    result: dict[str, list[float]] = {}
    header_re = re.compile(r"^###\s+([A-Z]{1,5})\s+Execution Profile", re.MULTILINE)
    for m in header_re.finditer(content):
        ticker = m.group(1)
        start = m.end()
        next_match = header_re.search(content, start)
        end = next_match.start() if next_match else len(content)
        section = content[start:end]
        dp_match = re.search(r"Dark Pool Hard Floors:\s*([^\n]+)", section)
        if dp_match:
            floor_text = dp_match.group(1)
            floors = re.findall(r"\$?(\d+\.\d{2})", floor_text)
            if floors:
                vals = sorted({float(f) for f in floors}, reverse=True)
                result[ticker] = vals
    return result


def evaluate_stop_loss(
    position: dict,
    latest_price: Optional[float],
    sma_200: Optional[float],
    dp_floors: list[float],
    peak_mv: Optional[float] = None,
    current_mv: Optional[float] = None,
    fundamental_break: bool = False,
) -> dict:
    """
    Evaluate stop-loss conditions for a position.
    Returns a verdict dict with signal, reasons, and recommended action.
    """
    ticker = (position.get("ticker") or "").upper()
    strategy = (position.get("strategy") or "").upper()
    current_delta = position.get("current_delta")

    # Load thresholds from config
    drawdown_pct    = cfg("strategy.stop_loss_drawdown_pct", 50.0) / 100.0
    sma_buffer      = cfg("strategy.stop_loss_sma200_buffer", 0.02)
    delta_critical  = cfg("strategy.delta_critical_threshold", 0.40)
    delta_act       = cfg("alerts.delta_act_threshold", 0.35)
    delta_watch     = cfg("alerts.delta_watch_threshold", 0.30)

    signals: list[str] = []
    reasons: list[str] = []
    score = 0  # 0=safe, 1=watch, 2=act, 3=act_immediately

    # ── Signal 1: Delta breach ────────────────────────────────────────────
    # Delta signals only apply to positions with an active SHORT leg that can
    # drift against us.  Long-only positions (LEAPS, standalone long calls) and
    # covered calls (CC) have high delta by design — never flag them.
    _delta_eligible_strategies = {"PCS", "PMCC", "DIAGONAL", "JADE_LIZARD", "MIXED", "CC"}
    # For CC we DO want to monitor the short call delta, but the position dict
    # will have a real short call so current_delta will be the short call's delta.
    # For LEAPS there is no short leg — skip entirely.
    _skip_delta = strategy in ("LEAPS", "SPY_HEDGE", "STOCK")
    if current_delta is not None and not _skip_delta:
        abs_delta = abs(float(current_delta))
        if abs_delta >= delta_critical:
            signals.append("delta_critical")
            reasons.append(f"Delta {abs_delta:.2f} ≥ critical threshold {delta_critical:.2f}")
            score = max(score, 3)
        elif abs_delta >= delta_act:
            signals.append("delta_act")
            reasons.append(f"Delta {abs_delta:.2f} ≥ act threshold {delta_act:.2f}")
            score = max(score, 2)
        elif abs_delta >= delta_watch:
            signals.append("delta_watch")
            reasons.append(f"Delta {abs_delta:.2f} ≥ watch threshold {delta_watch:.2f}")
            score = max(score, 1)

    # ── Signal 2: MV drawdown from peak ──────────────────────────────────
    if peak_mv is not None and current_mv is not None and peak_mv != 0:
        drawdown = (peak_mv - current_mv) / abs(peak_mv)
        mv_act_pct = cfg("alerts.mv_drawdown_act_pct", 50.0) / 100.0
        mv_warn_pct = cfg("alerts.mv_drawdown_warn_pct", 30.0) / 100.0
        if drawdown >= mv_act_pct:
            signals.append("mv_drawdown_act")
            reasons.append(f"MV drawdown {drawdown:.0%} ≥ act threshold {mv_act_pct:.0%}")
            score = max(score, 2)
        elif drawdown >= mv_warn_pct:
            signals.append("mv_drawdown_warn")
            reasons.append(f"MV drawdown {drawdown:.0%} ≥ warning threshold {mv_warn_pct:.0%}")
            score = max(score, 1)

    # ── Signal 3: Price below 200-SMA ────────────────────────────────────
    if latest_price is not None and sma_200 is not None:
        sma_floor = sma_200 * (1 - sma_buffer)
        if latest_price < sma_floor:
            signals.append("below_sma200")
            reasons.append(
                f"Price ${latest_price:.2f} below 200-SMA floor "
                f"${sma_floor:.2f} (SMA ${sma_200:.2f} × {1-sma_buffer:.3f})"
            )
            score = max(score, 2)

    # ── Signal 4: DP floor breach ─────────────────────────────────────────
    if latest_price is not None and dp_floors:
        breached = [f for f in dp_floors if latest_price < f]
        if breached:
            signals.append("dp_floor_breach")
            reasons.append(
                f"Price ${latest_price:.2f} below DP floor(s): "
                + ", ".join(f"${f:.2f}" for f in sorted(breached, reverse=True)[:3])
            )
            score = max(score, 1)

    # ── Signal 5: Fundamental break ───────────────────────────────────────
    if fundamental_break:
        signals.append("fundamental_break")
        reasons.append("Fundamental thesis break flagged by user")
        score = max(score, 2)

    # ── Verdict mapping ───────────────────────────────────────────────────
    verdict_map = {0: "SAFE", 1: "WATCH", 2: "ACT", 3: "ACT_IMMEDIATELY"}
    action_map = {
        0: "Hold — no stop-loss signals triggered.",
        1: "Monitor closely — one or more watch-level signals active.",
        2: "Consider closing or rolling — act-level signals active.",
        3: "Close immediately — critical delta breach.",
    }

    return {
        "ticker": ticker,
        "strategy": strategy,
        "verdict": verdict_map[score],
        "recommended_action": action_map[score],
        "signals": signals,
        "reasons": reasons,
        "inputs": {
            "current_delta": current_delta,
            "latest_price": latest_price,
            "sma_200": sma_200,
            "dp_floors": dp_floors,
            "peak_mv": peak_mv,
            "current_mv": current_mv,
            "fundamental_break": fundamental_break,
        },
        "thresholds_used": {
            "drawdown_pct":   cfg("strategy.stop_loss_drawdown_pct", 50.0),
            "sma_buffer":     cfg("strategy.stop_loss_sma200_buffer", 0.02),
            "delta_critical": delta_critical,
            "delta_act":      delta_act,
            "delta_watch":    delta_watch,
        },
    }
