"""
Scheduler status route.

GET /api/scheduler/status — returns last-run time and result for each of the
8 scheduled workflow scripts, plus the scheduler's running state.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.scheduler import runner as scheduler_runner

router = APIRouter()


@router.get("/scheduler/status")
def scheduler_status():
    """
    Return APScheduler job status for all 8 workflow scripts.

    Response shape:
      {
        "enabled": true,
        "running": true,
        "jobs": {
          "premarket": {
            "label": "Premarket Scanner",
            "status": "ok" | "error" | "running" | "timeout" | "missing" | "pending",
            "last_run": "2026-05-26T11:00:00+00:00",
            "finished_at": "...",
            "duration_seconds": 12.4,
            "exit_code": 0,
            "next_run": "2026-05-27T11:00:00+00:00"
          },
          ...
        }
      }
    """
    return {
        "enabled": scheduler_runner.SCHEDULER_ENABLED,
        "running": bool(
            scheduler_runner._scheduler
            and scheduler_runner._scheduler.running
        ),
        "jobs": scheduler_runner.get_status(),
    }
