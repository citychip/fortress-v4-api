"""
Uploads endpoint (Phase 3).

Two upload paths:
- POST /uploads/ibkr: IBKR positions screenshot, runs OCR, returns parsed for confirmation
- POST /uploads/chart: TradingView chart for a ticker, stores file with metadata

Adopted from Manus's prototype with cross-platform OCR and validation.
"""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services import ocr, state

router = APIRouter()

# Uploads directory adjacent to state files
UPLOAD_DIR = state.BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# File size cap: 10 MB per Build Spec §7.1
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg"}


def _safe_filename(filename: str) -> str:
    """Strip path components and sanitize filename to alphanumerics + ._-"""
    name = Path(filename).name
    return "".join(c for c in name if c.isalnum() or c in "._-")[:120]


async def _save_upload(file: UploadFile, prefix: str) -> Path:
    """Save uploaded file to UPLOAD_DIR with size + type checks."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Use PNG or JPEG."
        )

    safe = _safe_filename(file.filename or "upload")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    filename = f"{prefix}_{timestamp}_{safe}"
    file_path = UPLOAD_DIR / filename

    bytes_written = 0
    with file_path.open("wb") as buffer:
        while chunk := await file.read(64 * 1024):
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_BYTES:
                buffer.close()
                file_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024*1024)}MB limit"
                )
            buffer.write(chunk)

    return file_path


# ---------------------------------------------------------------------------
# IBKR screenshot upload + OCR
# ---------------------------------------------------------------------------

@router.post("/uploads/ibkr")
async def upload_ibkr(file: UploadFile = File(...)):
    """Upload IBKR positions screenshot. Runs OCR. Returns parsed positions."""
    file_path = await _save_upload(file, "ibkr")

    if not ocr.is_available():
        # Save the upload but skip OCR
        record = {
            "id": f"upload_{int(time.time())}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "image_path": str(file_path),
            "ocr_status": "unavailable",
            "ocr_results": [],
            "applied_to_positions": False,
            "note": "OCR backend not configured. Install tesseract-ocr + pytesseract."
        }
    else:
        ocr_result = ocr.process_ibkr_screenshot(str(file_path))
        record = {
            "id": f"upload_{int(time.time())}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "image_path": str(file_path),
            "ocr_status": "ok" if ocr_result["success"] else "failed",
            "ocr_results": ocr_result["results"],
            "ocr_error": ocr_result.get("error"),
            "applied_to_positions": False,
        }

    # Audit trail
    uploads_data = state.get_ibkr_uploads()
    uploads_data.setdefault("uploads", []).append(record)
    uploads_data["_last_updated"] = datetime.now(timezone.utc).isoformat()
    state.save_ibkr_uploads(uploads_data)

    return record


@router.post("/uploads/ibkr/{upload_id}/confirm")
async def confirm_ibkr_upload(upload_id: str, payload: dict):
    """
    Apply OCR results to active_positions.json.
    Phase 3: full IBKR sync. For now, accepts confirmed positions list and writes.
    """
    confirmed = payload.get("positions", [])
    if not confirmed:
        raise HTTPException(status_code=400, detail="No positions to confirm")

    positions_data = state.get_active_positions()
    positions_data["positions"] = confirmed
    positions_data["_last_updated"] = datetime.now(timezone.utc).isoformat()
    positions_data["ocr_last_sync"] = datetime.now(timezone.utc).isoformat()
    state.save_positions(positions_data)

    # Update audit trail
    uploads_data = state.get_ibkr_uploads()
    for u in uploads_data.get("uploads", []):
        if u.get("id") == upload_id:
            u["applied_to_positions"] = True
            u["applied_at"] = datetime.now(timezone.utc).isoformat()
    state.save_ibkr_uploads(uploads_data)

    return {"status": "applied", "positions_count": len(confirmed)}


# ---------------------------------------------------------------------------
# Chart annotation upload
# ---------------------------------------------------------------------------

VALID_CONTEXTS = {
    "pre_trade_chart_confirmation",
    "post_earnings_playbook",
    "roll_candidate_evaluation",
    "position_monitoring",
    "stop_loss_signal_check",
}


@router.post("/uploads/chart")
async def upload_chart(
    ticker: str = Form(...),
    context: str = Form(...),
    file: UploadFile = File(...)
):
    """Upload TradingView chart with ticker and context."""
    ticker = ticker.upper().strip()
    if not ticker.isalpha() or len(ticker) > 5:
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")

    if context not in VALID_CONTEXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid context. Must be one of: {sorted(VALID_CONTEXTS)}"
        )

    file_path = await _save_upload(file, f"chart_{ticker}")

    record = {
        "id": f"chart_{ticker}_{int(time.time())}",
        "ticker": ticker,
        "context": context,
        "image_path": str(file_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "levels": {
            "resistance": [],
            "support": [],
            "sma200": None,
            "sma50": None,
        },
        "read": "",
        "used_in_decisions": [],
    }

    annotations = state.get_chart_annotations()
    annotations.setdefault("annotations", []).append(record)
    annotations["_last_updated"] = datetime.now(timezone.utc).isoformat()
    state.save_chart_annotations(annotations)

    return record


@router.post("/uploads/chart/{chart_id}/annotate")
async def annotate_chart(chart_id: str, payload: dict):
    """Update annotation data for an uploaded chart."""
    annotations = state.get_chart_annotations()
    found = False
    for entry in annotations.get("annotations", []):
        if entry.get("id") == chart_id:
            entry["levels"] = payload.get("levels", entry.get("levels", {}))
            entry["read"] = payload.get("read", entry.get("read", ""))
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Chart {chart_id} not found")

    annotations["_last_updated"] = datetime.now(timezone.utc).isoformat()
    state.save_chart_annotations(annotations)
    return {"status": "annotated"}


@router.get("/uploads")
def list_uploads():
    """List all uploads (IBKR + charts) with metadata."""
    ibkr = state.get_ibkr_uploads().get("uploads", [])
    charts = state.get_chart_annotations().get("annotations", [])
    return {
        "ibkr_uploads": ibkr,
        "chart_annotations": charts,
    }
