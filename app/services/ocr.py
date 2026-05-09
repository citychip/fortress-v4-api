"""
OCR service for IBKR screenshot uploads.

Phase 3 backend. Uses Tesseract via pytesseract by default. Cross-platform:
- Linux/macOS: relies on system PATH (tesseract-ocr package)
- Windows: looks for pytesseract.pytesseract.tesseract_cmd env var

If TESSERACT_CMD env var is set, that path is used.
If pytesseract is not installed, returns a graceful error.

To install on Ubuntu VPS:
    sudo apt update && sudo apt install -y tesseract-ocr
    pip install pytesseract pillow

Future: swap for AWS Textract or Google Vision per Build Spec §10.1.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


# Lazy imports — only load if tesseract is configured
_pytesseract = None
_PIL_Image = None


def _ensure_imports() -> tuple[bool, str | None]:
    """Try to import pytesseract and PIL. Returns (success, error_message)."""
    global _pytesseract, _PIL_Image
    if _pytesseract is not None:
        return True, None
    try:
        import pytesseract
        from PIL import Image
        _pytesseract = pytesseract
        _PIL_Image = Image
    except ImportError as e:
        return False, f"OCR dependencies not installed: {e}. Run: pip install pytesseract pillow"

    # Override tesseract path from env if specified
    custom_path = os.environ.get("TESSERACT_CMD")
    if custom_path and Path(custom_path).exists():
        _pytesseract.pytesseract.tesseract_cmd = custom_path

    return True, None


def process_ibkr_screenshot(file_path: str) -> dict[str, Any]:
    """
    Run OCR on an IBKR positions screenshot and return parsed positions.

    Returns:
        {
            "success": bool,
            "results": [{"raw": str, "parsed": str, "status": "ok"|"unmatched"|"warning"}],
            "raw_text": str,
            "error": str | None
        }
    """
    ok, err = _ensure_imports()
    if not ok:
        return {"success": False, "error": err, "results": [], "raw_text": ""}

    try:
        img = _PIL_Image.open(file_path)
        text = _pytesseract.image_to_string(img)
    except Exception as e:
        return {
            "success": False,
            "error": f"OCR failed: {e}",
            "results": [],
            "raw_text": ""
        }

    # Parse lines that look like IBKR positions
    # Heuristic: starts with uppercase ticker (1-5 chars), contains expiry-ish pattern
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        parsed = _parse_ibkr_line(line)
        if parsed:
            results.append(parsed)

    return {
        "success": True,
        "results": results,
        "raw_text": text,
        "error": None
    }


def _parse_ibkr_line(line: str) -> dict | None:
    """
    Parse a single IBKR line. Returns dict with raw/parsed/status if it
    looks like a position; None otherwise.

    Expected pattern variations seen in IBKR screenshots:
    - MSFT JAN 28 2028 310 CALL +5
    - MSFT 21JAN28 310 C 5
    - MSFT Jan'28 $310C +5
    """
    parts = line.split()
    if len(parts) < 3:
        return None

    ticker_match = re.match(r"^([A-Z]{1,5})$", parts[0])
    if not ticker_match:
        return None

    ticker = ticker_match.group(1)

    # Look for strike (number near the end before C/P)
    strike = None
    side = None
    for i, part in enumerate(parts):
        # CALL/PUT or C/P
        if part.upper() in ("CALL", "C"):
            side = "C"
            # strike is usually the previous numeric token
            if i > 0:
                m = re.match(r"^\$?([0-9]+(?:\.[0-9]+)?)$", parts[i - 1])
                if m:
                    strike = float(m.group(1))
        elif part.upper() in ("PUT", "P"):
            side = "P"
            if i > 0:
                m = re.match(r"^\$?([0-9]+(?:\.[0-9]+)?)$", parts[i - 1])
                if m:
                    strike = float(m.group(1))

    # Quantity: look for +N or -N at end
    qty = None
    for part in reversed(parts):
        m = re.match(r"^([+\-]?[0-9]+)$", part)
        if m:
            try:
                qty = int(m.group(1))
                break
            except ValueError:
                pass

    if not (strike and side):
        return {
            "raw": line,
            "parsed": ticker.lower() + "_unparsed",
            "qty": qty,
            "status": "warning"
        }

    parsed_id = f"{ticker.lower()}_{int(strike)}{side.lower()}"
    return {
        "raw": line,
        "parsed": parsed_id,
        "ticker": ticker,
        "strike": strike,
        "side": side,
        "qty": qty,
        "status": "ok"
    }


def is_available() -> bool:
    """Check if OCR is configured and ready."""
    ok, _ = _ensure_imports()
    return ok
