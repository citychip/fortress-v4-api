"""
app/routes/trpc.py
Minimal tRPC-compatible HTTP endpoint for browser preference sync.

Implements the tRPC HTTP Link batch protocol used by the v4 frontend:
  GET  /api/trpc/prefs.get   — load saved prefs
  POST /api/trpc/prefs.save  — persist prefs
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("fortress.trpc")
router = APIRouter()

PREFS_FILE = Path("/home/ubuntu/Fortress_Dashboard_v4/quant/user_prefs.json")


def _load_prefs() -> dict:
    try:
        if PREFS_FILE.exists():
            return json.loads(PREFS_FILE.read_text())
    except Exception as e:
        logger.warning("Failed to load prefs: %s", e)
    return {}


def _save_prefs(prefs: dict) -> None:
    try:
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREFS_FILE.write_text(json.dumps(prefs, indent=2))
    except Exception as e:
        logger.warning("Failed to save prefs: %s", e)


def _trpc_ok(data: dict) -> JSONResponse:
    """Wrap response in tRPC batch format: [{"result":{"data":{"json":{...}}}}]"""
    return JSONResponse([{"result": {"data": {"json": data}}}])


@router.get("/trpc/prefs.get")
async def trpc_prefs_get():
    prefs = _load_prefs()
    return _trpc_ok({"prefs": prefs})


@router.post("/trpc/prefs.save")
async def trpc_prefs_save(request: Request):
    try:
        body = await request.json()
        # tRPC batch body: {"0": {"json": {"prefs": {...}}}}
        prefs = body.get("0", {}).get("json", {}).get("prefs", {})
        if prefs:
            # Never persist the API token server-side
            prefs.pop("apiToken", None)
            _save_prefs(prefs)
            logger.info("Prefs saved (%d keys)", len(prefs))
    except Exception as e:
        logger.warning("prefs.save error: %s", e)
    return _trpc_ok({"ok": True})
