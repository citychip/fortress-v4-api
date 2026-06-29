"""
APScheduler background scheduler for Fortress Dashboard V4.

Runs 8 workflow scripts on their defined ET schedules, stored as UTC.
All UTC times assume summer EDT (UTC-4). Winter EST note (Nov–Mar):
each hour value below increases by 1 (e.g. premarket 11→12 UTC).

Enable / disable via SCHEDULER_ENABLED env var (default: true).
Logs to {V4_ROOT}/logs/scheduler.log.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services import state

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCHEDULER_ENABLED: bool = os.environ.get("SCHEDULER_ENABLED", "true").lower() != "false"

_V4_ROOT = Path(__file__).resolve().parent.parent.parent   # .../Fortress_Dashboard_v4
LOG_DIR  = _V4_ROOT / "logs"
LOG_FILE = LOG_DIR  / "scheduler.log"

SCRIPT_TIMEOUT = 300   # seconds — kill a hung script after 5 min

# ---------------------------------------------------------------------------
# Script registry  (key → (filename_relative_to_state.BASE_DIR, label))
# ---------------------------------------------------------------------------

SCRIPTS: dict[str, tuple[str, str]] = {
    "premarket":        ("workflow_01_premarket_scanner.py", "Premarket Scanner"),
    "iv_crush":         ("workflow_05_iv_crush_report.py",   "IV Crush Monitor"),
    "position_monitor": ("workflow_03_position_monitor.py",  "Position Monitor"),
    "dark_pool_alert":  ("workflow_06_dark_pool_alert.py",   "Dark Pool Alert"),
    "eod_review":       ("workflow_04_eod_review.py",        "EOD Review"),
    "whale_flow":       ("workflow_07_whale_flow_report.py", "Whale Flow"),
    "max_pain":         ("workflow_08_max_pain_report.py",   "Max Pain"),
    "gex_oi":           ("gex_oi_report.py",                 "GEX/OI Update"),
    "qd_refresh":       ("qd_refresh_session.py",            "QuantData Session Refresh"),
}

# ---------------------------------------------------------------------------
# In-memory last-run status  (read by /api/scheduler/status)
# ---------------------------------------------------------------------------

_job_status: dict[str, dict] = {
    key: {"label": label, "status": "pending", "last_run": None}
    for key, (_, label) in SCRIPTS.items()
}

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

def _get_logger() -> logging.Logger:
    log = logging.getLogger("fortress.scheduler")
    if not log.handlers:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOG_FILE)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        log.addHandler(fh)
        log.setLevel(logging.INFO)
    return log


# ---------------------------------------------------------------------------
# Job runner — called by APScheduler in a background thread
# ---------------------------------------------------------------------------

def _run_script(script_key: str) -> None:
    script_filename, label = SCRIPTS[script_key]
    script_path = state.BASE_DIR / script_filename
    log = _get_logger()

    if not script_path.exists():
        log.warning("[%s] Script not found: %s — skipping.", script_key, script_path)
        _job_status[script_key].update(
            {"status": "missing", "last_run": datetime.now(timezone.utc).isoformat()}
        )
        return

    started = datetime.now(timezone.utc)
    _job_status[script_key].update({"status": "running", "last_run": started.isoformat()})
    log.info("[%s] ▶ Starting %s", script_key, label)

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT,
            cwd=str(state.BASE_DIR),
        )
        finished  = datetime.now(timezone.utc)
        duration  = round((finished - started).total_seconds(), 2)
        ok        = result.returncode == 0
        status    = "ok" if ok else "error"
        last_out  = "\n".join(result.stdout.splitlines()[-20:]) if result.stdout else ""
        last_err  = "\n".join(result.stderr.splitlines()[-10:]) if result.stderr else ""

        _job_status[script_key].update({
            "label":            label,
            "status":           status,
            "exit_code":        result.returncode,
            "last_run":         started.isoformat(),
            "finished_at":      finished.isoformat(),
            "duration_seconds": duration,
            "last_output":      last_out,
            "last_error":       last_err if not ok else "",
        })
        log.info(
            "[%s] %s — exit=%d  %.1fs",
            script_key, status.upper(), result.returncode, duration,
        )
        if last_err and not ok:
            log.warning("[%s] stderr: %s", script_key, last_err[:500])

    except subprocess.TimeoutExpired:
        finished = datetime.now(timezone.utc)
        _job_status[script_key].update(
            {"status": "timeout", "last_run": started.isoformat(),
             "finished_at": finished.isoformat()}
        )
        log.error("[%s] TIMEOUT after %ds", script_key, SCRIPT_TIMEOUT)

    except Exception as exc:
        _job_status[script_key].update(
            {"status": "error", "last_run": started.isoformat(), "error": str(exc)}
        )
        log.exception("[%s] Unexpected error: %s", script_key, exc)


# ---------------------------------------------------------------------------
# Scheduler build
# ---------------------------------------------------------------------------

_scheduler: BackgroundScheduler | None = None


def _job(key: str):
    """Zero-arg callable for APScheduler."""
    return partial(_run_script, key)


def build_scheduler() -> BackgroundScheduler:
    """
    Register all 8 script jobs with their UTC cron schedules.

    Schedule reference (summer EDT = UTC-4; add 1h for winter EST):
      qd_refresh      06:00 ET + 12:00 ET → 10:00 + 16:00 UTC  Mon-Fri
      premarket       07:00 ET → 11:00 UTC   Mon-Fri
      iv_crush        every 30 min during market hours (13:00-20:00 UTC Mon-Fri)
                      NOTE: spec requires earnings-aware 14-day window — deferred.
                      Current impl runs every 30 min during market hours as fallback.
      position_monitor every 5 min  13:35-19:55 ET → 13:00-20:00 UTC Mon-Fri
      dark_pool_alert  every 15 min 13:30-19:55 ET → 13:00-20:00 UTC Mon-Fri
      eod_review      16:05 ET → 20:05 UTC   Mon-Fri
      whale_flow      08:00 ET → 12:00 UTC   and  12:00 ET → 16:00 UTC  Mon-Fri
      max_pain        09:00 ET → 13:00 UTC   and  14:00 ET → 18:00 UTC  Mon-Fri
      gex_oi          09:05 ET → 13:05 UTC   and  13:00 ET → 17:00 UTC  Mon-Fri
    """
    sched = BackgroundScheduler(timezone="UTC")

    # 0a — QuantData Session Refresh: 06:00 ET → 10:00 UTC (runs before premarket)
    sched.add_job(
        _job("qd_refresh"),
        CronTrigger(hour=10, minute=0, day_of_week="mon-fri", timezone="UTC"),
        id="qd_refresh", name="QuantData Session Refresh", replace_existing=True,
    )

    # 0b — QuantData Midday Re-auth: 12:00 ET → 16:00 UTC (prevents intraday token expiry)
    sched.add_job(
        _job("qd_refresh"),
        CronTrigger(hour=16, minute=0, day_of_week="mon-fri", timezone="UTC"),
        id="qd_refresh_midday", name="QuantData Midday Re-auth", replace_existing=True,
    )

    # 1 — Premarket Scanner: 07:00 ET → 11:00 UTC
    sched.add_job(
        _job("premarket"),
        CronTrigger(hour=11, minute=0, day_of_week="mon-fri", timezone="UTC"),
        id="premarket", name="Premarket Scanner", replace_existing=True,
    )

    # 2 — IV Crush Monitor: every 30 min during market hours (13:00-20:00 UTC)
    sched.add_job(
        _job("iv_crush"),
        CronTrigger(minute="*/30", hour="13-20", day_of_week="mon-fri", timezone="UTC"),
        id="iv_crush", name="IV Crush Monitor", replace_existing=True,
    )

    # 3 — Position Monitor: every 5 min (13:00-19:55 UTC)
    sched.add_job(
        _job("position_monitor"),
        CronTrigger(minute="*/5", hour="13-19", day_of_week="mon-fri", timezone="UTC"),
        id="position_monitor", name="Position Monitor", replace_existing=True,
    )

    # 4 — Dark Pool Alert: every 15 min (13:00-19:55 UTC)
    sched.add_job(
        _job("dark_pool_alert"),
        CronTrigger(minute="*/15", hour="13-19", day_of_week="mon-fri", timezone="UTC"),
        id="dark_pool_alert", name="Dark Pool Alert", replace_existing=True,
    )

    # 5 — EOD Review: 16:05 ET → 20:05 UTC
    sched.add_job(
        _job("eod_review"),
        CronTrigger(hour=20, minute=5, day_of_week="mon-fri", timezone="UTC"),
        id="eod_review", name="EOD Review", replace_existing=True,
    )

    # 6 — Whale Flow: 08:00 ET → 12:00 UTC  AND  12:00 ET → 16:00 UTC
    sched.add_job(
        _job("whale_flow"),
        CronTrigger(hour="12,16", minute=0, day_of_week="mon-fri", timezone="UTC"),
        id="whale_flow", name="Whale Flow", replace_existing=True,
    )

    # 7 — Max Pain: 09:00 ET → 13:00 UTC  AND  14:00 ET → 18:00 UTC
    sched.add_job(
        _job("max_pain"),
        CronTrigger(hour="13,18", minute=0, day_of_week="mon-fri", timezone="UTC"),
        id="max_pain", name="Max Pain", replace_existing=True,
    )

    # 8 — GEX/OI Update: 09:05 ET → 13:05 UTC  (separate job for different minute)
    #                     13:00 ET → 17:00 UTC
    sched.add_job(
        _job("gex_oi"),
        CronTrigger(hour=13, minute=5, day_of_week="mon-fri", timezone="UTC"),
        id="gex_oi_am", name="GEX/OI Update (AM)", replace_existing=True,
    )
    sched.add_job(
        _job("gex_oi"),
        CronTrigger(hour=17, minute=0, day_of_week="mon-fri", timezone="UTC"),
        id="gex_oi_pm", name="GEX/OI Update (PM)", replace_existing=True,
    )

    # 9 — Conditional alert evaluation
    #   Market hours (13:30-20:00 UTC Mon-Fri): every 5 min
    sched.add_job(
        _evaluate_conditional_alerts,
        CronTrigger(minute="*/5", hour="13-19", day_of_week="mon-fri", timezone="UTC"),
        id="alert_eval_market", name="Alert Eval (market hours)", replace_existing=True,
    )
    #   Off-hours: every 30 min (for price-based alerts that fire on gaps/premarket)
    sched.add_job(
        _evaluate_conditional_alerts,
        CronTrigger(minute="*/30", hour="0-12,20-23", day_of_week="mon-fri", timezone="UTC"),
        id="alert_eval_offhours", name="Alert Eval (off-hours)", replace_existing=True,
    )
    sched.add_job(
        _evaluate_conditional_alerts,
        CronTrigger(minute="*/30", day_of_week="sat,sun", timezone="UTC"),
        id="alert_eval_weekend", name="Alert Eval (weekend)", replace_existing=True,
    )

    # 10 — Close-confirmed conditional alerts (Sprint 20.3): ONE daily EOD pass
    #   against the official DAILY CLOSE. Deliberately separate from the intraday
    #   alert_eval jobs above (which evaluate spot and false-fire on wicks) — the
    #   close pass evaluates only close_above / close_below.
    #   Default 21:15 UTC is post-close in BOTH EDT (17:15 ET) and EST (16:15 ET),
    #   so — unlike the EDT-anchored jobs above — it needs no seasonal edit.
    #   Time + enable are tunable via config (alerts.close_eval_*).
    try:
        from app.services.config_store import cfg
        _close_enabled = bool(cfg("alerts.close_eval_enabled", True))
        _close_hour    = int(cfg("alerts.close_eval_utc_hour", 21))
        _close_minute  = int(cfg("alerts.close_eval_utc_minute", 15))
    except Exception:
        _close_enabled, _close_hour, _close_minute = True, 21, 15
    if _close_enabled:
        sched.add_job(
            _evaluate_close_alerts,
            CronTrigger(hour=_close_hour, minute=_close_minute,
                        day_of_week="mon-fri", timezone="UTC"),
            id="close_alert_eval", name="Close Alert Eval (EOD)", replace_existing=True,
        )

    return sched


# ---------------------------------------------------------------------------
# Direct in-process job — alert evaluation (no subprocess)
# ---------------------------------------------------------------------------

def _evaluate_conditional_alerts() -> None:
    """Evaluate all active conditional alerts against live data. In-process.

    Intraday/spot pass — price/pnl/dte/delta. close_above/close_below are skipped
    here (the route excludes them) and handled by _evaluate_close_alerts instead.
    """
    log = _get_logger()
    try:
        from app.routes.conditional_alerts import evaluate_conditional_alerts
        result = evaluate_conditional_alerts()
        fired = result.get("count", 0)
        if fired:
            log.info("[alert_eval] %d alert(s) triggered", fired)
    except Exception as exc:
        log.warning("[alert_eval] Evaluation error: %s", exc)


def _evaluate_close_alerts() -> None:
    """EOD pass — evaluate close_above/close_below vs the official daily close.

    In-process; runs once after the cash close (Sprint 20.3). Kept separate from
    the intraday spot eval so wicks can never fire a close-confirmed rule.
    """
    log = _get_logger()
    try:
        from app.routes.conditional_alerts import evaluate_close_alerts
        result = evaluate_close_alerts()
        fired = result.get("count", 0)
        if fired:
            log.info("[close_alert_eval] %d close alert(s) triggered", fired)
        else:
            log.info("[close_alert_eval] EOD close pass ran — no close alerts triggered")
    except Exception as exc:
        log.warning("[close_alert_eval] Evaluation error: %s", exc)


# ---------------------------------------------------------------------------
# Public API — called from main.py lifespan
# ---------------------------------------------------------------------------

def start() -> None:
    """Start APScheduler. Call from FastAPI lifespan startup."""
    global _scheduler
    if not SCHEDULER_ENABLED:
        logging.getLogger("fortress").info(
            "APScheduler disabled (SCHEDULER_ENABLED=false)."
        )
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _scheduler = build_scheduler()
    _scheduler.start()
    logging.getLogger("fortress").info(
        "APScheduler started — %d jobs registered. Log → %s",
        len(_scheduler.get_jobs()), LOG_FILE,
    )


def shutdown() -> None:
    """Stop APScheduler. Call from FastAPI lifespan shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logging.getLogger("fortress").info("APScheduler stopped.")
    _scheduler = None


def get_status() -> dict:
    """Return job status dict for /api/scheduler/status."""
    # Synthetic entries for direct-function jobs (not in SCRIPTS registry)
    _direct_jobs = {
        "alert_eval": {"label": "Conditional Alert Evaluation", "status": "pending", "last_run": None},
        "close_alert_eval": {"label": "Close Alert Eval (EOD)", "status": "pending", "last_run": None},
    }
    out = {}
    for key, info in {**_job_status, **_direct_jobs}.items():
        next_run = None
        if _scheduler and _scheduler.running:
            # gex_oi has two APScheduler job IDs; report the earlier next_run
            for jid in (key, f"{key}_am", f"{key}_pm", f"{key}_market", f"{key}_offhours", f"{key}_weekend"):
                job = _scheduler.get_job(jid)
                if job and job.next_run_time:
                    candidate = job.next_run_time.isoformat()
                    if next_run is None or candidate < next_run:
                        next_run = candidate
        out[key] = {**info, "next_run": next_run}
    return out
