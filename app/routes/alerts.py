"""
Alerts endpoints — Phase 2 CRUD.
GET  /api/alerts           — list all active alerts
POST /api/alerts           — create a new alert
PATCH /api/alerts/{id}     — update an alert (e.g. snooze, change severity)
DELETE /api/alerts/{id}    — dismiss/delete an alert
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import state

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AlertCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    severity: str = Field("info", pattern="^(info|warn|critical)$")
    message: str = Field(..., min_length=1, max_length=500)
    source: str = Field("manual", description="Who created this alert")
    position_id: Optional[str] = Field(None, description="Linked position synthesized ID")


class AlertUpdate(BaseModel):
    severity: Optional[str] = Field(None, pattern="^(info|warn|critical)$")
    message: Optional[str] = Field(None, min_length=1, max_length=500)
    snoozed: Optional[bool] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_alert(alerts: list[dict], alert_id: str) -> tuple[int, dict]:
    for i, a in enumerate(alerts):
        if a.get("id") == alert_id:
            return i, a
    raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/alerts")
def get_alerts():
    try:
        return state.get_alerts()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts", status_code=201)
def create_alert(body: AlertCreate):
    try:
        data = state.get_alerts()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    alerts = data.get("alerts", [])
    new_alert = {
        "id": str(uuid.uuid4())[:8],
        "ticker": body.ticker.upper(),
        "severity": body.severity,
        "message": body.message,
        "source": body.source,
        "position_id": body.position_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snoozed": False,
    }
    alerts.append(new_alert)
    data["alerts"] = alerts
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()

    try:
        state.save_alerts(data)
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return new_alert


@router.patch("/alerts/{alert_id}")
def update_alert(alert_id: str, body: AlertUpdate):
    try:
        data = state.get_alerts()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    alerts = data.get("alerts", [])
    idx, alert = _find_alert(alerts, alert_id)

    if body.severity is not None:
        alert["severity"] = body.severity
    if body.message is not None:
        alert["message"] = body.message
    if body.snoozed is not None:
        alert["snoozed"] = body.snoozed

    alert["updated_at"] = datetime.now(timezone.utc).isoformat()
    alerts[idx] = alert
    data["alerts"] = alerts
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()

    try:
        state.save_alerts(data)
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return alert


@router.delete("/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: str):
    try:
        data = state.get_alerts()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    alerts = data.get("alerts", [])
    idx, _ = _find_alert(alerts, alert_id)

    alerts.pop(idx)
    data["alerts"] = alerts
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()

    try:
        state.save_alerts(data)
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))
