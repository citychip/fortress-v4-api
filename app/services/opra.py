"""
app/services/opra.py
OPRA option symbol utilities — Sprint v8.6 (K-01 Fix)

OPRA 21-character format:
  SSSSSS YYMMDD C/P KKKKKKKK
  ^^^^^^                       6-char ticker (left-justified, space-padded)
         ^^^^^^                expiry YYMMDD
               ^               right: C or P
                ^^^^^^^^       strike × 1000, zero-padded to 8 digits
  e.g. "AAPL  260117C00170000"
"""

from __future__ import annotations

import re
from typing import Optional

# Regex for an already-formed but possibly un-padded OPRA symbol
_OPRA_RE = re.compile(
    r"^([A-Z]{1,6})\s*(\d{6})([CP])(\d{8})$"
)

# Bracket pattern inside IBKR contractDesc, e.g.
# "NVDA   JUL2026 260 C [NVDA  260717C00260000 100]"
_CONTRACT_DESC_RE = re.compile(
    r"\[([A-Z]{1,6}\s*\d{6}[CP]\d{8})\s+\d+\]"
)


def normalise_opra(symbol: str) -> Optional[str]:
    """
    Accept a symbol that may be missing the ticker padding and return the
    canonical 21-character OPRA string, or None if it cannot be parsed.

    Examples:
        normalise_opra("AAPL260117C00170000")   -> "AAPL  260117C00170000"
        normalise_opra("AAPL  260117C00170000") -> "AAPL  260117C00170000"
        normalise_opra("NVDA  260717C00260000") -> "NVDA  260717C00260000"
    """
    if not symbol:
        return None
    s = symbol.strip()
    # Already the right length — validate structure then return
    if len(s) == 21:
        m = re.match(r"^([A-Z ]{6})(\d{6})([CP])(\d{8})$", s)
        if m:
            return s
    # Try to parse variable-length form
    m = _OPRA_RE.match(s)
    if not m:
        return None
    ticker, yymmdd, right, strike_str = m.groups()
    return f"{ticker.upper().ljust(6)}{yymmdd}{right}{strike_str}"


def build_opra(
    ticker: str,
    expiry: str,          # "YYYY-MM-DD" or "YYMMDD"
    right: str,           # "C" or "P"  (or "CALL"/"PUT")
    strike: float,
) -> Optional[str]:
    """
    Construct a 21-character OPRA symbol from position fields.

    Args:
        ticker:  Underlying ticker symbol (1-6 chars)
        expiry:  "YYYY-MM-DD" or "YYMMDD"
        right:   "C", "P", "CALL", or "PUT"
        strike:  Numeric strike price (e.g. 170.0)

    Returns:
        21-char OPRA string, or None on invalid input.

    Example:
        build_opra("AAPL", "2026-01-17", "C", 170.0)
        -> "AAPL  260117C00170000"
    """
    try:
        t = ticker.strip().upper()
        if not (1 <= len(t) <= 6):
            return None

        # Normalise right
        r = right.strip().upper()
        if r in ("CALL", "C"):
            r = "C"
        elif r in ("PUT", "P"):
            r = "P"
        else:
            return None

        # Normalise expiry
        exp = expiry.strip().replace("-", "")
        if len(exp) == 8:          # YYYYMMDD
            exp = exp[2:]          # -> YYMMDD
        if len(exp) != 6 or not exp.isdigit():
            return None

        # Strike: multiply by 1000, round to int, zero-pad to 8 digits
        strike_int = round(float(strike) * 1000)
        if strike_int < 0 or strike_int > 99_999_999:
            return None
        strike_str = f"{strike_int:08d}"

        return f"{t.ljust(6)}{exp}{r}{strike_str}"
    except Exception:
        return None


def extract_opra_from_contract_desc(desc: str) -> Optional[str]:
    """
    Extract and normalise the OPRA symbol embedded in an IBKR contractDesc
    bracket, e.g.
        "NVDA   JUL2026 260 C [NVDA  260717C00260000 100]"
        -> "NVDA  260717C00260000"

    Returns None if no bracket pattern found.
    """
    if not desc:
        return None
    m = _CONTRACT_DESC_RE.search(desc)
    if not m:
        return None
    return normalise_opra(m.group(1))
