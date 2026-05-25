"""
State service for Fortress Dashboard.

All routes use this module to access the data layer. State files live
in BASE_DIR (the Fortress_Dashboard directory by default; override via
FORTRESS_DATA_DIR env var).

Provides:
- Atomic writes with backup-before-write
- Staleness checks (hours since _last_updated)
- Earnings blackout helpers
- IV Crush report parsing (markdown → structured rows)
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(os.environ.get(
    "FORTRESS_DATA_DIR",
    Path(__file__).resolve().parent.parent.parent
)).resolve()

BACKUP_DIR = BASE_DIR / "backups"


class StateError(Exception):
    """Raised when a state file is missing, malformed, or cannot be written."""


# ---------------------------------------------------------------------------
# JSON file IO with atomic writes
# ---------------------------------------------------------------------------

def read_json(filename: str, default: Any = None) -> dict[str, Any]:
    """Read a JSON file from BASE_DIR. Returns default if missing."""
    path = BASE_DIR / filename
    if not path.exists():
        if default is not None:
            return default
        raise StateError(f"State file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise StateError(f"Malformed JSON in {filename}: {e}") from e


def write_json(filename: str, data: dict[str, Any]) -> None:
    """
    Write JSON file with backup-before-write and atomic replace.

    Backups are kept in BACKUP_DIR with timestamp in filename.
    Last 50 backups per file retained.
    """
    path = BASE_DIR / filename
    BACKUP_DIR.mkdir(exist_ok=True)

    # Backup current file if it exists
    if path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = BACKUP_DIR / f"{path.stem}.{ts}{path.suffix}"
        shutil.copy2(path, backup)

        # Prune old backups (keep last 50 per stem)
        siblings = sorted(BACKUP_DIR.glob(f"{path.stem}.*{path.suffix}"))
        for old in siblings[:-50]:
            old.unlink(missing_ok=True)

    # Atomic write
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Convenience accessors per file
# ---------------------------------------------------------------------------

DEFAULT_POSITIONS = {"_last_updated": None, "positions": []}
DEFAULT_ALERTS = {"_last_updated": None, "alerts": []}
DEFAULT_JOURNAL = {"_last_updated": None, "entries": []}
DEFAULT_CHARTS = {"_last_updated": None, "annotations": []}
DEFAULT_UPLOADS = {"_last_updated": None, "uploads": []}
DEFAULT_UNIVERSE = {"tier1": [], "tier2": [], "macro": []}
DEFAULT_CALENDAR = {"_last_updated": None, "tickers": {}}


def get_active_positions():
    return read_json("active_positions.json", DEFAULT_POSITIONS)


def get_alerts():
    return read_json("alerts.json", DEFAULT_ALERTS)


def get_journal():
    return read_json("journal.json", DEFAULT_JOURNAL)


def get_chart_annotations():
    return read_json("chart_annotations.json", DEFAULT_CHARTS)


def get_ibkr_uploads():
    return read_json("ibkr_uploads.json", DEFAULT_UPLOADS)


def get_ticker_universe():
    return read_json("ticker_universe.json", DEFAULT_UNIVERSE)


def get_earnings_blocklist():
    return read_json("earnings_blocklist.json", DEFAULT_CALENDAR)


def save_positions(data):
    write_json("active_positions.json", data)


def save_alerts(data):
    write_json("alerts.json", data)


def save_journal(data):
    write_json("journal.json", data)


def save_chart_annotations(data):
    write_json("chart_annotations.json", data)


def save_ibkr_uploads(data):
    write_json("ibkr_uploads.json", data)


def save_universe(data):
    write_json("ticker_universe.json", data)


def save_earnings_blocklist(data):
    write_json("earnings_blocklist.json", data)


# ---------------------------------------------------------------------------
# Staleness helpers
# ---------------------------------------------------------------------------

def staleness_hours(filename: str, key: str = "_last_updated") -> float | None:
    """Return how many hours old the file's _last_updated timestamp is."""
    try:
        data = read_json(filename, {})
    except StateError:
        return None
    ts = data.get(key)
    if not ts:
        return None
    try:
        if "T" in ts:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(ts + "T00:00:00+00:00")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 3600
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Earnings helpers
# ---------------------------------------------------------------------------

def days_to_earnings(ticker: str, calendar: dict[str, Any]) -> int | None:
    """Days from today to ticker's next earnings date. None if unknown."""
    entry = calendar.get("tickers", {}).get(ticker, {})
    date_str = entry.get("next_earnings")
    if not date_str:
        return None
    try:
        earnings_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        return (earnings_date - today).days
    except ValueError:
        return None


def is_earnings_blackout(ticker: str, calendar: dict[str, Any], window: int = 10) -> bool:
    """True if ticker is within the blackout window before earnings (Strategy §4)."""
    days = days_to_earnings(ticker, calendar)
    if days is None:
        return False
    return 0 <= days <= window


# ---------------------------------------------------------------------------
# IV Crush report parsing (markdown fallback)
# ---------------------------------------------------------------------------

def get_latest_crush_report_path() -> Path | None:
    """Find the latest Workflow_05_IV_Crush_*.md report in BASE_DIR."""
    matches = sorted(glob.glob(str(BASE_DIR / "Workflow_05_IV_Crush_*.md")))
    return Path(matches[-1]) if matches else None


def parse_crush_report_markdown(content: str) -> list[dict]:
    """
    Parse the markdown table from workflow_05_iv_crush_report.py output.

    Expected format: a markdown table with columns:
    Ticker | Price | IVR | IV | HV-20 | Spread (pp) | Days to Earn | Signal

    Returns list of dicts matching the canonical row schema.
    """
    rows = []
    in_table = False
    for line in content.splitlines():
        line = line.strip()
        # Skip until we find a header row
        if line.startswith("|") and "Ticker" in line and "Signal" in line:
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 8:
                continue
            try:
                # cols: ticker, price, ivr, current_iv, hv20, spread_pp, days_to_earnings, signal
                ticker = cols[0].strip()
                price = float(re.sub(r"[^0-9.\-]", "", cols[1]))
                ivr = float(re.sub(r"[^0-9.\-]", "", cols[2]))
                current_iv = float(re.sub(r"[^0-9.\-]", "", cols[3]))
                hv20 = float(re.sub(r"[^0-9.\-]", "", cols[4]))
                spread_pp = float(re.sub(r"[^0-9.\-]", "", cols[5]))
                days_str = re.sub(r"[^0-9\-]", "", cols[6])
                days = int(days_str) if days_str else None
                signal = cols[7].strip().upper().replace(" ", "_")
                rows.append({
                    "ticker": ticker,
                    "price": price,
                    "ivr": ivr,
                    "current_iv": current_iv,
                    "hv20": hv20,
                    "spread_pp": spread_pp,
                    "days_to_earnings": days,
                    "signal": signal,
                })
            except (ValueError, IndexError):
                continue
        elif in_table and not line.startswith("|"):
            # End of table
            in_table = False
    return rows


def get_iv_crush_report() -> dict:
    """
    Return latest IV Crush report data.

    Tries iv_crush_report.json first; falls back to parsing latest markdown.
    """
    # Prefer JSON if present
    json_path = BASE_DIR / "iv_crush_report.json"
    if json_path.exists():
        return read_json("iv_crush_report.json", {"rows": [], "macro_regime": {}})

    # Fallback: parse latest markdown
    md_path = get_latest_crush_report_path()
    if not md_path:
        return {"rows": [], "macro_regime": {}, "_source": None}

    with md_path.open("r", encoding="utf-8") as f:
        content = f.read()

    rows = parse_crush_report_markdown(content)

    # Pull macro regime from the daily report markdown if available
    macro = {}
    daily_matches = sorted(glob.glob(str(BASE_DIR / "QuantData Daily Report*.md")))
    if daily_matches:
        with open(daily_matches[-1], "r", encoding="utf-8") as f:
            daily_content = f.read()
        macro = _parse_macro_regime(daily_content)

    return {
        "_source": str(md_path),
        "_last_updated": datetime.fromtimestamp(md_path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "rows": rows,
        "macro_regime": macro,
    }


def _fetch_live_vix() -> float | None:
    """Fetch live VIX from yfinance as fallback when no daily report exists."""
    try:
        import yfinance as yf
        hist = yf.Ticker("^VIX").history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return None


def _parse_macro_regime(daily_md: str) -> dict:
    """Best-effort extraction of macro regime fields from daily report markdown."""
    # Default fallback
    out = {"regime": "neutral", "vix": None, "vix_state": "normal"}
    vix_match = re.search(r"VIX[:\s]+([0-9.]+)", daily_md)
    if vix_match:
        try:
            out["vix"] = float(vix_match.group(1))
            if out["vix"] > 35:
                out["vix_state"] = "stress"
            elif out["vix"] > 25:
                out["vix_state"] = "elevated"
        except ValueError:
            pass

    # Regime keywords
    if re.search(r"\bbearish\b", daily_md, re.IGNORECASE):
        out["regime"] = "bearish"
    elif re.search(r"\bbullish\b", daily_md, re.IGNORECASE):
        out["regime"] = "bullish"
    return out


# ---------------------------------------------------------------------------
# Beta-weighted Greeks helpers
# ---------------------------------------------------------------------------

def _get_beta_for_ticker(ticker: str, betas: dict[str, dict[str, Any]], fallback: float = 1.0) -> float:
    """Get beta for a ticker from the betas dict. Returns fallback if missing."""
    t = ticker.upper()
    entry = betas.get(t)
    if entry:
        return float(entry["beta"])
    return fallback


def compute_beta_weighted_delta(positions_data: dict, betas: dict[str, dict[str, Any]] | None = None) -> float:
    """Compute SPY-equivalent beta-weighted portfolio delta.

    For each leg:
        share_delta   = qty × option_delta × multiplier
        dollar_delta  = share_delta × stock_price
        spy_equiv_$   = dollar_delta × stock_beta
    Sum all spy_equiv_$ → divide by SPY price → SPY-equivalent shares.

    If betas/prices not provided, returns raw unweighted delta (shares sum).
    """
    if not betas:
        return positions_data.get("portfolio_delta") or 0

    positions = positions_data.get("positions", []) or []
    spy_price = betas.get("SPY", {}).get("price") or 545.0  # fallback if SPY missing
    total_spy_dollar = 0.0

    for p in positions:
        ticker = p.get("ticker", "").upper()
        sec_type = p.get("sec_type", "OPT")
        qty = p.get("qty") or 0
        try:
            multiplier = int(p.get("multiplier") or 100)
        except (ValueError, TypeError):
            multiplier = 100

        if sec_type == "STK":
            # Stock: delta = 1 per share, multiplier irrelevant
            stock_price = betas.get(ticker, {}).get("price") or 1.0
            beta = _get_beta_for_ticker(ticker, betas, fallback=1.0)
            dollar_delta = qty * 1.0 * stock_price
        else:
            option_delta = p.get("current_delta")
            if option_delta is None:
                continue
            stock_price = betas.get(ticker, {}).get("price") or 1.0
            beta = _get_beta_for_ticker(ticker, betas, fallback=1.0)
            share_delta = qty * option_delta * multiplier
            dollar_delta = share_delta * stock_price

        total_spy_dollar += dollar_delta * beta

    if spy_price == 0:
        return 0.0
    return total_spy_dollar / spy_price


# --- Phase 3 IBKR sync support (May 4 2026) ---

def _leg_strike(leg: dict) -> Optional[float]:
    """IBKR sync writes per-leg strike into 'short_strike' regardless of long/short.
    Treat 'short_strike' or 'long_strike' as 'this leg's strike'."""
    return leg.get("short_strike") or leg.get("long_strike")


def _normalize_alert_state(raw: Optional[str], delta: Optional[float]) -> str:
    """Normalize IBKR-sync alert states to the frontend stateMap vocabulary."""
    if not raw:
        return "unknown" if delta is None else "safe"
    raw_l = str(raw).lower()
    mapping = {
        "ok": "safe",
        "safe": "safe",
        "watch": "watch",
        "approaching": "approaching",
        "breaking": "breaking",
        "broken": "broken",
        "critical_gamma": "critical_gamma",
        "hedge": "hedge",
        "unknown": "unknown",
    }
    return mapping.get(raw_l, raw_l)


def _normalize_delta_state(delta: Optional[float], strategy: Optional[str], leg_role: Optional[str]) -> str:
    """Compute delta_state per Build Spec v1.2 §5.5.3.

    Thresholds come from config_store (strategy.delta_critical_threshold,
    alerts.delta_watch_threshold) so the user can tune them via Settings.
    Defaults match Strategy v3.5 §5 + alerts intent (0.35 / 0.30).
    """
    if delta is None:
        return "unknown"
    s = (strategy or "").upper()
    if s == "SPY_HEDGE" or leg_role == "LONG_CALL":
        return "normal"
    if s == "PCS" and leg_role == "PUT_SPREAD":
        return "normal"
    try:
        from app.services.config_store import cfg as _cfg
        crit = float(_cfg("strategy.delta_critical_threshold") or 0.35)
        watch = float(_cfg("alerts.delta_watch_threshold") or 0.30)
    except Exception:
        crit, watch = 0.35, 0.30
    abs_d = abs(float(delta))
    if abs_d > crit:
        return "critical"
    if abs_d >= watch:
        return "watch"
    return "normal"


def aggregate_positions_by_ticker(positions_data: dict) -> list[dict]:
    """Combine per-leg IBKR records into one row per ticker.

    Returns a list of dicts shaped for Phase 4 lookups:
      {
        ticker, strategy, leg_count, net_market_value, net_liq_pct,
        short_strike, short_expiry,   # primary short call (nearest expiry, qty<0, right=C)
        long_strike, long_expiry,     # primary long call (longest expiry, qty>0, right=C)
        expiry,                       # alias of short_expiry, fallback long_expiry
        current_delta, delta_state, alert_state, notes, qty,
        legs                          # list of compact per-leg summaries
      }
    """
    positions = positions_data.get("positions", []) or []
    net_liq = positions_data.get("net_liq") or 0

    by_ticker: dict[str, list[dict]] = {}
    for p in positions:
        t = p.get("ticker")
        if t:
            by_ticker.setdefault(t, []).append(p)

    out: list[dict] = []
    for ticker, legs in by_ticker.items():
        net_mv = sum((leg.get("market_value") or 0) for leg in legs)
        net_liq_pct = (net_mv / net_liq * 100) if net_liq else None

        # Primary strategy: most common non-None, with fallback inference from leg structure
        strats = [leg.get("strategy") for leg in legs if leg.get("strategy")]
        strategy = max(set(strats), key=strats.count) if strats else None

        if not strategy:
            # Infer strategy from leg structure when not stored in the data
            has_short_call = any(l.get("right") == "C" and (l.get("qty") or 0) < 0 for l in legs)
            has_long_call  = any(l.get("right") == "C" and (l.get("qty") or 0) > 0 for l in legs)
            has_short_put  = any(l.get("right") == "P" and (l.get("qty") or 0) < 0 for l in legs)
            has_long_put   = any(l.get("right") == "P" and (l.get("qty") or 0) > 0 for l in legs)
            has_stock      = any((l.get("right") or "") == "" or l.get("right") is None for l in legs)
            # Expiry diversity: PMCC requires short call expiry < long call expiry
            short_call_expiries = sorted(set(l.get("expiry") for l in legs if l.get("right") == "C" and (l.get("qty") or 0) < 0 and l.get("expiry")))
            long_call_expiries  = sorted(set(l.get("expiry") for l in legs if l.get("right") == "C" and (l.get("qty") or 0) > 0 and l.get("expiry")))
            pmcc_structure = (has_short_call and has_long_call
                              and short_call_expiries and long_call_expiries
                              and short_call_expiries[-1] < long_call_expiries[0])
            if ticker.upper() == "SPY" and has_short_put and has_long_put:
                strategy = "SPY_HEDGE"
            elif pmcc_structure:
                strategy = "PMCC"
            elif has_short_put and has_long_put and not has_short_call:
                strategy = "PCS"
            elif has_short_call and has_long_put and not has_long_call:
                strategy = "JADE_LIZARD"
            elif has_long_call and not has_short_call and not has_short_put and not has_long_put:
                # Long call only — standalone LEAP or PMCC anchor without a short overlay yet
                strategy = "LEAPS"
            elif has_short_call and not has_long_call and not has_short_put and not has_long_put:
                # Short call only — covered call (CC) or naked call
                strategy = "CC"
            elif has_stock and not has_short_call and not has_long_call:
                strategy = "STOCK"
            else:
                strategy = "MIXED"

        # Primary short call: right=C, qty<0, nearest expiry
        short_calls = sorted(
            [l for l in legs if l.get("right") == "C" and (l.get("qty") or 0) < 0 and l.get("expiry")],
            key=lambda l: l["expiry"],
        )
        primary_short = short_calls[0] if short_calls else None

        # Primary short put: right=P, qty<0, nearest expiry (used for PCS delta monitoring)
        short_puts = sorted(
            [l for l in legs if l.get("right") == "P" and (l.get("qty") or 0) < 0 and l.get("expiry")],
            key=lambda l: l["expiry"],
        )
        primary_short_put = short_puts[0] if short_puts else None

        # Primary long call: right=C, qty>0, longest expiry
        long_calls = sorted(
            [l for l in legs if l.get("right") == "C" and (l.get("qty") or 0) > 0 and l.get("expiry")],
            key=lambda l: l["expiry"],
            reverse=True,
        )
        primary_long = long_calls[0] if long_calls else None

        # Delta source priority:
        #  1. Short call delta (PMCC, CC, JADE_LIZARD — gamma drift monitoring)
        #  2. Short put delta (PCS — delta breach monitoring on the short put)
        #  3. Long call delta ONLY for display when there is no short leg at all (LEAPS)
        #     — in that case gamma alert is suppressed below.
        # NEVER use a long call's delta to trigger a stop-loss or roll alert.
        current_delta = (primary_short or {}).get("current_delta")
        _has_short_call_leg = primary_short is not None
        if current_delta is None and primary_short_put is not None:
            # PCS or PCS+LEAP combo: use the short put's delta for monitoring
            current_delta = primary_short_put.get("current_delta")
        _has_short_leg = _has_short_call_leg or (primary_short_put is not None)
        if current_delta is None and primary_long and not _has_short_leg:
            # Standalone LEAP with no short overlay — store for display only;
            # gamma alert will be suppressed below.
            current_delta = primary_long.get("current_delta")

        # Notes: take first non-empty
        notes = ""
        for leg in legs:
            n = leg.get("notes")
            if n:
                notes = n
                break

        # alert_state: take from the primary short leg (call or put) if available, else first leg
        _primary_short_any = primary_short or primary_short_put
        raw_alert = (_primary_short_any or legs[0]).get("alert_state")
        alert_state = _normalize_alert_state(raw_alert, current_delta)
        # Promote critical_gamma from delta ONLY when there is an active short call leg.
        # A LEAP long call (qty > 0, right == 'C') with delta ~0.80 is by design —
        # never flag it as gamma risk.
        _strat_upper = (strategy or "").upper()
        _long_only_strategies = {"SPY_HEDGE", "STOCK"}
        # _has_short_leg is True only if there is a leg with qty < 0 and right == 'C'
        _real_short_call = any(
            l.get("right", "") == "C" and (l.get("qty") or 0) < 0
            for l in legs
        )
        _gamma_check_eligible = (
            _real_short_call
            and _strat_upper not in _long_only_strategies
        )
        try:
            from app.services.config_store import cfg as _cfg2
            _crit = float(_cfg2("strategy.delta_critical_threshold") or 0.35)
        except Exception:
            _crit = 0.35
        if (_gamma_check_eligible
                and current_delta is not None
                and abs(current_delta) > _crit
                and alert_state in ("safe", "watch", "unknown")):
            alert_state = "critical_gamma"

        delta_state = _normalize_delta_state(current_delta, strategy, "MIXED")

        # Resolve display short leg once before building the record dict
        _display_short = primary_short or primary_short_put

        rec = {
            "ticker": ticker,
            "strategy": strategy,
            "leg_count": len(legs),
            "net_market_value": round(net_mv, 2),
            "net_liq_pct": round(net_liq_pct, 2) if net_liq_pct is not None else None,
            "short_strike": _leg_strike(_display_short) if _display_short else None,
            "short_expiry": _display_short.get("expiry") if _display_short else None,
            "long_strike": _leg_strike(primary_long) if primary_long else None,
            "long_expiry": primary_long.get("expiry") if primary_long else None,
            "expiry": (
                (_display_short.get("expiry") if _display_short else None)
                or (primary_long.get("expiry") if primary_long else None)
            ),
            "current_delta": current_delta,
            "delta_state": delta_state,
            "alert_state": alert_state,
            "notes": notes,
            "qty": abs(int((_primary_short_any or {}).get("qty") or 1)),
            "legs": [
                {
                    "strike": _leg_strike(l),
                    "right": l.get("right"),
                    "qty": l.get("qty"),
                    "expiry": l.get("expiry"),
                    "market_value": l.get("market_value"),
                    "local_symbol": l.get("local_symbol"),
                }
                for l in legs
            ],
        }
        out.append(rec)

    return out


def compute_concentration(positions_data: dict) -> dict[str, float]:
    """Concentration per ticker as % of NetLiq.

    Preferred: sum of net market_value / NetLiq * 100 (correct for per-leg IBKR sync).
    Fallback: sum of per-leg net_liq_pct (the OCR-era behavior).
    """
    existing = positions_data.get("concentration")
    if existing:
        return existing

    net_liq = positions_data.get("net_liq")
    if net_liq:
        by_ticker: dict[str, float] = {}
        for pos in positions_data.get("positions", []):
            t = pos.get("ticker")
            mv = pos.get("market_value") or 0
            if t:
                by_ticker[t] = by_ticker.get(t, 0) + mv
        return {t: round(mv / net_liq * 100, 1) for t, mv in by_ticker.items()}

    # Fallback (old behavior)
    by_ticker = {}
    for pos in positions_data.get("positions", []):
        t = pos.get("ticker")
        pct = pos.get("net_liq_pct") or 0
        if t:
            by_ticker[t] = by_ticker.get(t, 0) + pct
    return {t: round(p, 1) for t, p in by_ticker.items()}


# --- Dashboard runtime settings (May 4 2026) ---

DEFAULT_SETTINGS = {
    "_last_updated": None,
    "greeks_backend": "auto",  # auto | web_api | bs_yfinance
    "ibkr_account_id": "",  # Populated at runtime from config_store security section
    "ibkr_web_api": {
        "cp_gateway_url": "https://localhost:5000",
        "verify_ssl": False,
        "tickle_interval_s": 60,
        "request_timeout_s": 15,
    },
    "fx": {
        "default_pair": "EURUSD",
        "cache_ttl_s": 3600,
    },
    "ui": {
        "show_eur_equivalent": True,
        "default_position_view": "aggregated",
    },
}

VALID_GREEKS_BACKENDS = {"auto", "web_api", "bs_yfinance"}


def get_dashboard_settings() -> dict:
    """Return current settings, falling back to defaults for missing keys.

    ibkr_account_id is resolved in priority order:
      1. dashboard_settings.json (if not empty / not placeholder)
      2. config_store security.ibkr_account_id
      3. empty string (user must configure)
    """
    data = read_json("dashboard_settings.json", {})
    # Deep-merge with defaults so missing keys get default values
    out = _deep_merge(DEFAULT_SETTINGS, data)
    # Resolve ibkr_account_id — fall back to config_store if file has placeholder
    _PLACEHOLDER = "YOUR_IBKR_ACCOUNT_ID"
    file_account_id = out.get("ibkr_account_id", "")
    if not file_account_id or file_account_id == _PLACEHOLDER:
        try:
            from app.services.config_store import cfg as _cfg
            cfg_account_id = _cfg("security.ibkr_account_id", "")
            if cfg_account_id and cfg_account_id != _PLACEHOLDER:
                out["ibkr_account_id"] = cfg_account_id
        except Exception:
            pass
    return out


def save_dashboard_settings(updates: dict) -> dict:
    """Merge `updates` into current settings. Returns the merged result.

    Validates greeks_backend if present.
    """
    if "greeks_backend" in updates:
        v = updates["greeks_backend"]
        if v not in VALID_GREEKS_BACKENDS:
            raise StateError(f"Invalid greeks_backend: {v!r}. Must be one of {sorted(VALID_GREEKS_BACKENDS)}.")

    current = get_dashboard_settings()
    merged = _deep_merge(current, updates)
    from datetime import datetime, timezone
    merged["_last_updated"] = datetime.now(timezone.utc).isoformat()
    write_json("dashboard_settings.json", merged)
    return merged


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Merge overlay onto base. Nested dicts are merged; other values overwrite."""
    out = dict(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def resolve_greeks_backend(settings: dict, capability: dict) -> str:
    """Pick the active backend.

    Reads `greeks_backend` from (in priority):
      1. config_store cfg("technical.greeks_backend") — the canonical source
      2. settings dict's greeks_backend key (legacy)
      3. "auto" default
    """
    try:
        from app.services.config_store import cfg as _cfg
        requested = _cfg("technical.greeks_backend") or settings.get("greeks_backend") or "auto"
    except Exception:
        requested = settings.get("greeks_backend", "auto")

    web = (capability or {}).get("web_api", {}) or {}
    web_session = web.get("session_status", {}) or {}
    web_ok = bool(web.get("opra_subscribed")) and bool(web_session.get("established"))


    if requested == "auto":
        if web_ok:
            return "web_api"
        return "bs_yfinance"
    if requested == "web_api":
        return "web_api" if web_ok else "bs_yfinance"
    return requested

# ---------------------------------------------------------------------------
# Pending Orders (approval queue — v3.7.2)
# ---------------------------------------------------------------------------

DEFAULT_PENDING_ORDERS = {'_last_updated': None, 'orders': []}


def get_pending_orders() -> dict:
    return read_json('pending_orders.json', DEFAULT_PENDING_ORDERS)


def save_pending_orders(data: dict) -> None:
    write_json('pending_orders.json', data)
