"""
Run endpoint: manually trigger workflow scripts.

Security note: only scripts in WORKFLOW_SCRIPTS whitelist can be invoked.
Manus's prototype accepted any filename — this version refuses anything not
explicitly in the whitelist. This prevents path traversal and arbitrary
code execution via the API.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services import state, config_store

router = APIRouter()

# Scripts that require QuantData to be enabled (Settings > Security > Enable QuantData).
# workflow_03 (position_monitor) is exempt — it only uses yfinance/IBKR.
QUANTDATA_REQUIRED_SCRIPTS = {
    "premarket",
    "daily",
    "iv_crush",
    "whale_flow",
    "dark_pool_alert",
    "eod_review",
    "max_pain",
    "entry_scoring",
    "gex_oi",
}

# Whitelist of scripts that can be invoked via the dashboard.
# Anything not on this list returns 403.
WORKFLOW_SCRIPTS = {
    "premarket": "workflow_01_premarket_scanner.py",
    "daily": "quantdata_daily.py",
    "iv_crush": "workflow_05_iv_crush_report.py",
    "whale_flow": "workflow_07_whale_flow_report.py",
    "position_monitor": "workflow_03_position_monitor.py",
    "dark_pool_alert": "workflow_06_dark_pool_alert.py",
    "eod_review": "workflow_04_eod_review.py",
    "max_pain": "workflow_08_max_pain_report.py",
    "entry_scoring": "workflow_02_entry_scoring.py",
    "gex_oi": "gex_oi_report.py",
}

# Safety: limit subprocess execution time
SCRIPT_TIMEOUT_SECONDS = 120


@router.get("/run/scripts")
def list_scripts():
    """List the whitelisted scripts that can be run."""
    return {
        "scripts": [
            {"key": key, "filename": filename}
            for key, filename in WORKFLOW_SCRIPTS.items()
        ]
    }


@router.post("/run/{script_key}")
def run_script(script_key: str):
    """
    Trigger a whitelisted script. Returns last 100 lines of output.

    Returns 403 if script_key is not in the whitelist (security: prevents
    arbitrary file execution via the API).
    """
    if script_key not in WORKFLOW_SCRIPTS:
        raise HTTPException(
            status_code=403,
            detail=f"Script '{script_key}' is not whitelisted. Available: {list(WORKFLOW_SCRIPTS.keys())}"
        )

    # Guard: QuantData-dependent scripts are blocked when the toggle is off
    if script_key in QUANTDATA_REQUIRED_SCRIPTS and not config_store.cfg("security.use_quantdata", True):
        raise HTTPException(
            status_code=503,
            detail=(
                f"Script '{script_key}' requires QuantData, which is currently disabled. "
                "Enable it in Settings → Security → Enable QuantData."
            ),
        )

    script_path = state.BASE_DIR / WORKFLOW_SCRIPTS[script_key]
    if not script_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Script file not found: {script_path}"
        )

    started = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT_SECONDS,
            cwd=state.BASE_DIR,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail=f"Script {script_key} timed out after {SCRIPT_TIMEOUT_SECONDS}s"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {e}")

    finished = datetime.now(timezone.utc)
    duration = (finished - started).total_seconds()

    # Truncate output to last ~100 lines or 4KB
    stdout_lines = result.stdout.splitlines()
    stderr_lines = result.stderr.splitlines()

    return {
        "script": script_key,
        "filename": WORKFLOW_SCRIPTS[script_key],
        "exit_code": result.returncode,
        "duration_seconds": round(duration, 2),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "stdout": "\n".join(stdout_lines[-100:]),
        "stderr": "\n".join(stderr_lines[-50:]) if stderr_lines else "",
    }
