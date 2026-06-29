"""
Conditional Alerts — Phase 7.

Trigger types:
  price_above       — spot >= threshold (e.g. "MSFT hits $450")
  price_below       — spot <= threshold (e.g. "MSFT pulls back to $400 → entry")
  close_above       — DAILY CLOSE >= threshold (EOD-confirmed; immune to wicks)
  close_below       — DAILY CLOSE <= threshold (EOD-confirmed; immune to wicks)
  pnl_pct           — position unrealized P&L% >= threshold (e.g. 50% profit → close)
  dte_lte           — short leg DTE <= threshold (e.g. 21d → review roll)
  delta_gte         — short leg abs(delta) >= threshold (e.g. 0.35 → roll)
  conditional_entry — same as price_below but tagged as 🔵 entry signal

  NOTE (Sprint 20.3): close_above / close_below are evaluated ONLY by the EOD
  close pass (POST /api/conditional-alerts/evaluate-close), against the official
  daily close — never on intraday spot. The intraday /evaluate pass skips them.
  This removes the manual "confirm on the daily close" step that price_* rules
  required (they false-fire on intraday wicks).

GET  /api/conditional-alerts                  — list all (optionally filter by ticker)
POST /api/conditional-alerts                  — create
DELETE /api/conditional-alerts/{id}           — delete
PATCH  /api/conditional-alerts/{id}           — snooze / unsnooze / update threshold
POST /api/conditional-alerts/evaluate         — intraday pass: spot/pnl/dte/delta (skips close_*)
POST /api/conditional-alerts/evaluate-close   — EOD pass: close_above/close_below vs daily close
GET  /api/action-queue/summary                — lightweight cached count for sidebar badge
"""
from __future__ import annotations

import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import state

router = APIRouter()
_log = logging.getLogger("fortress.conditional_alerts")

AlertType = Literal[
    "price_above", "price_below",
    "close_above", "close_below",   # Sprint 20.3 — EOD-confirmed (daily close)
    "pnl_pct", "dte_lte", "delta_gte",
    "conditional_entry",
]
UrgencyLevel = Literal["critical", "watch", "profit", "entry"]

# ── badge cache ───────────────────────────────────────────────────────────────
_summary_cache: dict = {"ts": 0.0, "data": {"count": 0, "breakdown": {}}}
_CACHE_TTL = 60  # seconds


# ── Pydantic models ───────────────────────────────────────────────────────────

class ConditionalAlertCreate(BaseModel):
    ticker:      str        = Field(..., min_length=1, max_length=10)
    alert_type:  AlertType
    threshold:   float      = Field(..., description="Trigger value (price, %, DTE, delta)")
    message:     str        = Field(..., min_length=1, max_length=300)
    urgency:     UrgencyLevel = "watch"
    position_id: Optional[str] = None  # linked position synthetic ID
    action_mode: Optional[str] = "new"  # 'new'|'roll'|'close'|'add'


class ConditionalAlertUpdate(BaseModel):
    snoozed:    Optional[bool]  = None
    threshold:  Optional[float] = None
    message:    Optional[str]   = None


# ── State helpers ─────────────────────────────────────────────────────────────

_DEFAULT_CA = {"alerts": [], "_last_updated": None}

def _load() -> dict:
    return state.read_json("conditional_alerts.json", _DEFAULT_CA)

def _save(data: dict) -> None:
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()
    state.write_json("conditional_alerts.json", data)

def _find(alerts: list, alert_id: str):
    for i, a in enumerate(alerts):
        if a.get("id") == alert_id:
            return i, a
    raise HTTPException(404, detail=f"Alert '{alert_id}' not found")


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/conditional-alerts")
def list_conditional_alerts(ticker: Optional[str] = Query(None)):
    data = _load()
    alerts = data.get("alerts", [])
    if ticker:
        alerts = [a for a in alerts if a.get("ticker", "").upper() == ticker.upper()]
    return {"alerts": alerts, "count": len(alerts)}


@router.post("/conditional-alerts", status_code=201)
def create_conditional_alert(body: ConditionalAlertCreate):
    data = _load()
    alerts = data.get("alerts", [])
    new_alert = {
        "id":          str(uuid.uuid4())[:8],
        "ticker":      body.ticker.upper(),
        "alert_type":  body.alert_type,
        "threshold":   body.threshold,
        "message":     body.message,
        "urgency":     body.urgency,
        "position_id": body.position_id,
        "action_mode": body.action_mode or "new",
        "triggered":   False,
        "triggered_at": None,
        "snoozed":     False,
        "snoozed_at":  None,
        "created_at":  datetime.now(timezone.utc).isoformat(),
    }
    alerts.append(new_alert)
    data["alerts"] = alerts
    _save(data)
    _invalidate_cache()
    return new_alert


@router.patch("/conditional-alerts/{alert_id}")
def update_conditional_alert(alert_id: str, body: ConditionalAlertUpdate):
    data = _load()
    alerts = data.get("alerts", [])
    idx, alert = _find(alerts, alert_id)
    if body.snoozed is not None:
        alert["snoozed"] = body.snoozed
        alert["snoozed_at"] = datetime.now(timezone.utc).isoformat() if body.snoozed else None
    if body.threshold is not None:
        alert["threshold"] = body.threshold
        alert["triggered"] = False  # re-arm on threshold change
        alert["triggered_at"] = None
    if body.message is not None:
        alert["message"] = body.message
    alert["updated_at"] = datetime.now(timezone.utc).isoformat()
    alerts[idx] = alert
    data["alerts"] = alerts
    _save(data)
    _invalidate_cache()
    return alert


@router.delete("/conditional-alerts/{alert_id}", status_code=204)
def delete_conditional_alert(alert_id: str):
    data = _load()
    alerts = data.get("alerts", [])
    idx, _ = _find(alerts, alert_id)
    alerts.pop(idx)
    data["alerts"] = alerts
    _save(data)
    _invalidate_cache()


# ── Evaluate ──────────────────────────────────────────────────────────────────

@router.post("/conditional-alerts/evaluate")
def evaluate_conditional_alerts():
    """
    Check every active (non-triggered, non-snoozed) alert against live data.
    Returns the list of newly triggered alerts.
    """
    data = _load()
    alerts = data.get("alerts", [])
    newly_triggered = []

    # Pull positions once
    try:
        pos_data = state.get_positions()
        positions = pos_data.get("positions", [])
    except Exception:
        positions = []

    from app.services import chain as chain_svc

    for alert in alerts:
        if alert.get("triggered") or alert.get("snoozed"):
            continue

        # Sprint 20.3 — close-confirmed alerts are evaluated ONLY by the EOD
        # close pass (evaluate_close_alerts), against the official daily close.
        # Skip them here so intraday spot (wick-prone) can never fire them.
        if alert.get("alert_type") in ("close_above", "close_below"):
            continue

        ticker     = alert["ticker"]
        alert_type = alert["alert_type"]
        threshold  = alert["threshold"]
        fired      = False

        try:
            if alert_type in ("price_above", "price_below", "conditional_entry"):
                spot = chain_svc.get_spot(ticker) or 0
                if alert_type == "price_above" and spot >= threshold:
                    fired = True
                elif alert_type in ("price_below", "conditional_entry") and 0 < spot <= threshold:
                    fired = True

            elif alert_type == "pnl_pct":
                # Find position unrealized P&L %
                legs = [p for p in positions if p.get("ticker") == ticker]
                for leg in legs:
                    pnl_pct = leg.get("unrealized_pnl_pct") or leg.get("pnl_pct") or 0
                    if pnl_pct >= threshold:
                        fired = True
                        break

            elif alert_type == "dte_lte":
                # Find shortest DTE among short legs for this ticker
                from datetime import date as _date_cls
                today = datetime.now(timezone.utc).date()
                short_legs = [p for p in positions if p.get("ticker") == ticker
                              and p.get("leg_direction") == "short" and p.get("expiry")]
                for leg in short_legs:
                    try:
                        exp = datetime.strptime(leg["expiry"][:10], "%Y-%m-%d").date()
                        dte = (exp - today).days
                        if dte <= threshold:
                            fired = True
                            break
                    except Exception:
                        pass

            elif alert_type == "delta_gte":
                # Find max abs(delta) among short legs for this ticker
                short_legs = [p for p in positions if p.get("ticker") == ticker
                              and p.get("leg_direction") == "short"]
                for leg in short_legs:
                    delta = abs(leg.get("current_delta") or 0)
                    if delta >= threshold:
                        fired = True
                        break

        except Exception as e:
            _log.warning("evaluate error for alert %s (%s %s): %s", alert["id"], ticker, alert_type, e)

        if fired:
            alert["triggered"]    = True
            alert["triggered_at"] = datetime.now(timezone.utc).isoformat()
            newly_triggered.append(alert)
            _log.info("Alert triggered: %s %s %s>=%.2f", alert["id"], ticker, alert_type, threshold)

    data["alerts"] = alerts
    _save(data)
    _invalidate_cache()
    return {"triggered": newly_triggered, "count": len(newly_triggered)}


# ── EOD close-confirmation pass (Sprint 20.3) ─────────────────────────────────

def _daily_close(ticker: str):
    """
    Return (close_price, bar_date_iso) for the most recent SETTLED daily bar
    from yfinance, or (None, None) on failure.

    Used ONLY by the EOD close pass — deliberately NOT chain.get_spot(), which
    is the live/intraday price (wick-prone). The official daily close is the
    settled regular-session close; the EOD scheduler job runs after the cash
    close so the latest bar is final.
    """
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="5d", auto_adjust=False)
        if hist is None or hist.empty:
            return None, None
        close = float(hist["Close"].iloc[-1])
        if close <= 0:
            return None, None
        bar_date = hist.index[-1].date().isoformat()
        return close, bar_date
    except Exception as e:
        _log.warning("_daily_close(%s) failed: %s", ticker, e)
        return None, None


@router.post("/conditional-alerts/evaluate-close")
def evaluate_close_alerts():
    """
    EOD pass — evaluate ONLY close_above / close_below alerts against the
    official DAILY CLOSE (not intraday spot). Run once after the cash close by
    the scheduler's close_alert_eval job; also callable on demand to confirm a
    close rule. Records last_close / last_close_date on every close alert for
    audit, and triggered_close / triggered_close_date when it fires.
    Returns the list of newly triggered alerts.
    """
    data = _load()
    alerts = data.get("alerts", [])
    newly_triggered = []
    close_cache: dict = {}   # ticker → (close, bar_date), fetched once per ticker

    for alert in alerts:
        if alert.get("alert_type") not in ("close_above", "close_below"):
            continue
        if alert.get("triggered") or alert.get("snoozed"):
            continue

        ticker     = alert["ticker"]
        alert_type = alert["alert_type"]
        threshold  = alert["threshold"]

        if ticker not in close_cache:
            close_cache[ticker] = _daily_close(ticker)
        close, bar_date = close_cache[ticker]

        if close is None:
            _log.warning("evaluate-close: no daily close for %s — skipping %s",
                         ticker, alert.get("id"))
            continue

        # Stamp the evaluated close on the alert for audit (even when it doesn't fire)
        alert["last_close"] = round(close, 4)
        alert["last_close_date"] = bar_date

        fired = (
            (alert_type == "close_above" and close >= threshold) or
            (alert_type == "close_below" and close <= threshold)
        )

        if fired:
            now_iso = datetime.now(timezone.utc).isoformat()
            alert["triggered"]            = True
            alert["triggered_at"]         = now_iso
            alert["triggered_close"]      = round(close, 4)
            alert["triggered_close_date"] = bar_date
            newly_triggered.append(alert)
            _log.info("Close alert triggered: %s %s %s @ close %.2f (%s) vs %.2f",
                      alert.get("id"), ticker, alert_type, close, bar_date, threshold)

    data["alerts"] = alerts
    _save(data)
    _invalidate_cache()
    return {
        "triggered":    newly_triggered,
        "count":        len(newly_triggered),
        "pass":         "eod_close",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Action Queue Summary ──────────────────────────────────────────────────────

def _invalidate_cache():
    _summary_cache["ts"] = 0.0


@router.get("/action-queue/summary")
def action_queue_summary():
    """
    Lightweight cached integer count for sidebar badge.
    Combines: roll_needed + stop_loss ACT + triggered conditional alerts.
    Cache TTL: 60 seconds.
    """
    now = time.time()
    if now - _summary_cache["ts"] < _CACHE_TTL:
        return _summary_cache["data"]

    roll_count = 0
    stop_count = 0
    alert_count = 0

    try:
        from app.routes.manage import roll_all as _roll_all, stop_loss_all as _stop_loss_all  # type: ignore
        roll_data = _roll_all()
        roll_count = sum(1 for p in (roll_data.get("positions") or []) if p.get("roll_needed"))
        stop_data = _stop_loss_all()
        stop_count = sum(1 for p in (stop_data.get("positions") or []) if p.get("verdict") == "ACT")
    except Exception:
        pass

    try:
        ca_data = _load()
        alert_count = sum(
            1 for a in ca_data.get("alerts", [])
            if a.get("triggered") and not a.get("snoozed")
        )
    except Exception:
        pass

    result = {
        "count": roll_count + stop_count + alert_count,
        "breakdown": {
            "roll":   roll_count,
            "stop":   stop_count,
            "alerts": alert_count,
        },
    }
    _summary_cache["ts"]   = now
    _summary_cache["data"] = result
    return result
