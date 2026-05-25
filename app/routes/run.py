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

# Time-of-day script groups for auto-run (item F)
# Keys map to WORKFLOW_SCRIPTS above
TIME_OF_DAY_SCRIPTS = {
    "pre_market":    ["premarket", "entry_scoring"],
    "market_hours":  ["position_monitor", "dark_pool_alert"],
    "post_market":   ["eod_review", "max_pain"],
    "any_time":      ["iv_crush", "whale_flow"],
}


@router.get("/run/scripts")
def list_scripts():
    """List the whitelisted scripts that can be run."""
    return {
        "scripts": [
            {"key": key, "filename": filename}
            for key, filename in WORKFLOW_SCRIPTS.items()
        ]
    }



@router.get("/run/results")
def get_script_results():
    """Return cached last-run results for all scripts from script_results.json."""
    try:
        data = state.read_json("script_results.json", default={})
        # Strip the internal _last_updated key from per-script results
        last_updated = data.get("_last_updated")
        results = {k: v for k, v in data.items() if not k.startswith("_")}
        return {
            "results": results,
            "last_updated": last_updated,
        }
    except Exception as e:
        return {"results": {}, "last_updated": None, "error": str(e)}

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

    run_result = {
        "script": script_key,
        "filename": WORKFLOW_SCRIPTS[script_key],
        "exit_code": result.returncode,
        "duration_seconds": round(duration, 2),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "stdout": "\n".join(stdout_lines[-100:]),
        "stderr": "\n".join(stderr_lines[-50:]) if stderr_lines else "",
    }
    # Cache-write hook: persist last run result so dashboard panels hydrate immediately
    try:
        existing = state.read_json("script_results.json", default={})
        existing[script_key] = run_result
        existing["_last_updated"] = finished.isoformat()
        state.write_json("script_results.json", existing)
    except Exception:
        pass  # Non-fatal: dashboard will fall back to live API
    return run_result

# ---------------------------------------------------------------------------
# Time-of-day auto-run endpoint  (item F)
# ---------------------------------------------------------------------------

@router.get("/run/time_of_day")
def get_time_of_day_group():
    """
    Return the appropriate script group for the current time of day (ET).
    Used by the Strategy tab to auto-run the right scripts on activation.
    """
    import pytz
    from datetime import time as _time

    try:
        et = pytz.timezone("America/New_York")
        now_et = datetime.now(et).time()
    except Exception:
        now_et = datetime.utcnow().time()

    pre_market_start  = _time(4, 0)
    market_open       = _time(9, 30)
    market_close      = _time(16, 0)
    post_market_end   = _time(20, 0)

    if pre_market_start <= now_et < market_open:
        group = "pre_market"
    elif market_open <= now_et < market_close:
        group = "market_hours"
    elif market_close <= now_et < post_market_end:
        group = "post_market"
    else:
        group = "any_time"

    scripts = TIME_OF_DAY_SCRIPTS[group]
    # Filter to only scripts that exist and pass QuantData guard
    available = []
    for key in scripts:
        if key not in WORKFLOW_SCRIPTS:
            continue
        if key in QUANTDATA_REQUIRED_SCRIPTS and not config_store.cfg("security.use_quantdata", True):
            available.append({"key": key, "blocked": True, "reason": "QuantData disabled"})
        else:
            script_path = state.BASE_DIR / WORKFLOW_SCRIPTS[key]
            available.append({
                "key": key,
                "filename": WORKFLOW_SCRIPTS[key],
                "blocked": not script_path.exists(),
                "reason": "script file not found" if not script_path.exists() else None,
            })

    return {
        "group": group,
        "scripts": available,
        "all_groups": TIME_OF_DAY_SCRIPTS,
    }


@router.post("/run/group/{group_name}")
def run_group(group_name: str):
    """
    Run all scripts in a time-of-day group sequentially.
    Returns results for each script.
    """
    if group_name not in TIME_OF_DAY_SCRIPTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown group '{group_name}'. Available: {list(TIME_OF_DAY_SCRIPTS.keys())}"
        )

    scripts = TIME_OF_DAY_SCRIPTS[group_name]
    results = []

    for script_key in scripts:
        if script_key not in WORKFLOW_SCRIPTS:
            results.append({"script": script_key, "status": "skipped", "reason": "not in whitelist"})
            continue

        if script_key in QUANTDATA_REQUIRED_SCRIPTS and not config_store.cfg("security.use_quantdata", True):
            results.append({"script": script_key, "status": "skipped", "reason": "QuantData disabled"})
            continue

        script_path = state.BASE_DIR / WORKFLOW_SCRIPTS[script_key]
        if not script_path.exists():
            results.append({"script": script_key, "status": "skipped", "reason": "file not found"})
            continue

        started = datetime.now(timezone.utc)
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=SCRIPT_TIMEOUT_SECONDS,
                cwd=state.BASE_DIR,
            )
            finished = datetime.now(timezone.utc)
            stdout_lines = result.stdout.splitlines()
            results.append({
                "script": script_key,
                "status": "ok" if result.returncode == 0 else "error",
                "exit_code": result.returncode,
                "duration_seconds": round((finished - started).total_seconds(), 2),
                "stdout": "\n".join(stdout_lines[-50:]),
            })
        except subprocess.TimeoutExpired:
            results.append({"script": script_key, "status": "timeout"})
        except Exception as e:
            results.append({"script": script_key, "status": "error", "reason": str(e)})

    return {
        "group": group_name,
        "scripts_run": len([r for r in results if r.get("status") not in ("skipped",)]),
        "results": results,
    }
