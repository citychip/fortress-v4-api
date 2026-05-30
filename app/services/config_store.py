"""
app/services/config_store.py — Fortress Dashboard Central Config Store

Single source of truth for ALL technical and strategy variables.
Replaces every hardcoded constant across the codebase.

Storage: JSON file at DATA_DIR/fortress_config.json
  - Loaded once at startup into an in-memory dict
  - Written atomically (write-to-temp, rename) on every save
  - Thread-safe via a RLock

Usage anywhere in the codebase:
    from app.services.config_store import cfg
    max_conc = cfg("strategy.max_concentration_pct")   # → 15.0
    host     = cfg("technical.ibkr_gateway_host")      # → "127.0.0.1"

The cfg() function always returns the current live value — no restart needed
after a settings change via the UI.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger("fortress.config")

# ---------------------------------------------------------------------------
# Storage location — same DATA_DIR convention used by state.py
# ---------------------------------------------------------------------------
_DATA_DIR = Path(os.environ.get("FORTRESS_DATA_DIR", "./quant"))
_CONFIG_FILE = _DATA_DIR / "fortress_config.json"

# ---------------------------------------------------------------------------
# Default configuration — every variable with its default value
# Grouped into sections that map to Settings tab panels.
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, Any] = {

    # ── TRADER PROFILE ───────────────────────────────────────────────────────
    "trader_profile": {
        "trader_type":          "income_seeker",   # income_seeker | speculator | volatility_trader | hedger | custom
        "active_strategies":    ["PMCC", "JADE_LIZARD", "PCS", "SPY_HEDGE", "LEAPS"],
        "risk_tolerance":       "moderate",        # conservative | moderate | aggressive
        "primary_objective":    "income",          # income | growth | protection | speculation
    },

    # ── SECURITY ─────────────────────────────────────────────────────────────
    "security": {
        # IBKR account — stored locally, never transmitted externally
        "ibkr_account_id":          "",          # set to your IBKR account number, e.g. U1234567

        # QuantData live API — JWT credentials from browser DevTools (see docs/07_MCP_Workflow)
        # Obtain: open v3.quantdata.us → DevTools → Network → any /api/ request → Request Headers
        "quantdata_auth_token":     "",   # Authorization header value (JWT, starts with 'Bearer ')
        "quantdata_instance_id":    "",   # x-instance-id header value
        "quantdata_api_base":       "https://core-lb-prod.quantdata.us/api",
        # Legacy API key (unused — kept for backward compat)
        "quantdata_api_key":        "",

        # IBKR auto-sync — when enabled, the server triggers a sync every N minutes
        # independently of browser activity. Default: off (manual-only).
        "ibkr_auto_sync_enabled":   False,
        "ibkr_auto_sync_interval_min": 15,

        # Dashboard Bearer token — display hint only; real value lives in FORTRESS_API_TOKEN env var
        "api_token_hint":           "(set via FORTRESS_API_TOKEN env var)",

        # IBKR auth mode: "ibeam" (CP Gateway) or "oauth" (OAuth 1.0a)
        "ibkr_auth_mode":           "ibeam",

        # CP Gateway (voyz/ibeam) — used when ibkr_auth_mode == "ibeam"
        "cp_gateway_url":           "https://localhost:5000",
        "cp_gateway_verify_ssl":    False,
        "cp_gateway_timeout_s":     15,

        # OAuth 1.0a — used when ibkr_auth_mode == "oauth"
        "oauth_consumer_key":       "SHARMILAH",
        "oauth_keys_dir":           "/home/ubuntu/ibkr-oauth",
    },

    # ── TECHNICAL ────────────────────────────────────────────────────────────
    "technical": {

        # Network
        "vps_ip":                   "YOUR_VPS_IP",
        "dashboard_port":           8080,
        "api_base_url":             "http://YOUR_VPS_IP:8080",

        # IBKR Gateway (gnzsnz/ib-gateway Docker container)
        "ibkr_gateway_host":        "127.0.0.1",
        "ibkr_gateway_port":        4001,
        "ibkr_gateway_client_id":   10,
        "ibkr_gateway_timeout_s":   90,
        "ibkr_delta_timeout_s":     8,

        # Greeks backend selection: auto | web_api | bs_yfinance
        "greeks_backend":           "auto",

        # Data paths
        "data_dir":                 "./quant",
        "reports_dir":              "./quant/reports",
        "uploads_dir":              "./quant/uploads",

        # FX
        "base_currency":            "USD",
        "fx_refresh_interval_min":  60,

        # Systemd service name
        "service_name":             "fortress-dashboard",
    },

    # ── STRATEGY ─────────────────────────────────────────────────────────────
    "strategy": {

        # Portfolio sizing
        "portfolio_netliq_usd":     500000.0,   # target net liquidation value
        "max_positions":            20,          # hard cap on open positions
        "entries_per_week_max":     2,           # pacing cap (rolls/hedges excluded)

        # Concentration limits (Strategy §7)
        "max_concentration_pct":    15.0,        # single ticker hard cap % of NetLiq
        "high_conc_threshold_pct":  50.0,        # triggers tightened entry band
        "high_conc_size_cap":       1,           # max contracts when >50% conc
        "sector_concentration_max_pct": 40.0,   # sector-level cap (Tier 1.5)

        # Delta targets (Strategy §4 / §5)
        "target_delta_low":         0.20,        # short call target delta lower bound
        "target_delta_high":        0.25,        # short call target delta upper bound
        "delta_critical_threshold": 0.35,        # triggers critical_gamma alert (was 0.40 per Strategy §5; user override 2026-05-05)
        "delta_bias_long_threshold":  5000.0,    # portfolio delta > this → "long"
        "delta_bias_short_threshold": -5000.0,   # portfolio delta < this → "short"

        # DTE targets (Strategy §5)
        "target_dte_low":           30,          # roll target DTE lower bound
        "target_dte_high":          45,          # roll target DTE upper bound

        # SPY Hedge (Strategy §2.D)
        "spy_hedge_min_usd":        22000.0,     # minimum hedge market value USD
        "spy_hedge_max_usd":        33000.0,     # maximum hedge market value USD
        "spy_hedge_target_usd":     27500.0,     # midpoint target

        # Account-level USD floors (Strategy §7 — currency normalised to USD per user pref)
        "available_funds_min_usd":  17000.0,
        "excess_liq_min_usd":       25000.0,

        # Stop-loss (Strategy §6)
        "stop_loss_drawdown_pct":   50.0,        # max drawdown from peak MV %
        "stop_loss_sma200_buffer":  0.02,        # 2% buffer below 200-SMA

        # Post-earnings playbook (Strategy §10)
        "iv_crush_floor_pct":       15.0,        # minimum IV crush to consider entry
        "prime_entry_gap_low":      -8.0,        # prime entry band lower bound %
        "prime_entry_gap_high":     -3.0,        # prime entry band upper bound %
        "high_conc_prime_low":      -8.0,        # tightened prime band lower (high-conc)
        "high_conc_prime_high":     -5.0,        # tightened prime band upper (high-conc)

        # LEAP earnings blackout — days before earnings to block new short-leg entries
        # when a LEAP / long-dated long call (DTE > 90) is open on the same ticker.
        "leap_earnings_blackout_days": 21,

        # DTE exception registry — positions exempt from DTE roll alerts.
        # Each entry is a string in the form "TICKER:YYYY-MM-DD" matching the
        # short-leg expiry. Example: ["MSFT:2026-12-18", "VST:2026-09-19"]
        "dte_exceptions":           [],

         # DTE roll trigger
        "dte_roll_threshold":       21,          # roll short leg when DTE < this
        # Profit / loss management
        "profit_target_pct":        50,          # close at this % of max profit
        # Credit / premium minimums
        "min_credit_covered_call":  0.30,        # minimum net credit for Covered Call
        "min_credit_csp":           0.50,        # minimum net credit for Cash-Secured Put
        "min_credit_jade_lizard":   1.00,        # minimum net credit for Jade Lizard
        "min_credit_pcs":           0.50,        # minimum net credit for PCS
        "min_credit_pmcc":          0.30,        # minimum net credit for PMCC roll
        "min_credit_iron_condor":   1.00,        # minimum net credit for Iron Condor
        "min_credit_strangle":      1.50,        # minimum net credit for Short Strangle
        # Speculative / Long options
        "max_long_option_pct_nlv":  5.0,         # max debit paid for long options as % of NLV
        "long_call_delta_target":   0.50,        # preferred delta for long call entries
        "long_put_delta_target":    0.50,        # preferred delta for long put entries
        "vertical_spread_width":    5,           # default strike width for vertical spreads
        # Volatility strategies
        "straddle_dte_target":      30,          # target DTE for straddle/strangle entries
        "iron_condor_wing_width":   5,           # Iron Condor wing width (strikes)
        "iron_condor_short_delta":  0.16,        # Iron Condor short strike delta (1 SD)
        "butterfly_body_width":     5,           # Butterfly body width (strikes)
        # LEAPS profit-taking (Strategy §6)
        "leaps_profit_take_pct":    50.0,        # close LEAPS at this % of max profit
        "leaps_scale_out_pct":      25.0,        # scale-out tranche size %
        "leaps_min_dte":            365,         # minimum DTE at LEAPS entry
        # Collar / Protective Put
        "collar_put_delta_target":  0.25,        # delta of long put leg in collar
        "collar_call_delta_target": 0.25,        # delta of short call leg in collar
        "protective_put_delta_target": 0.30,     # delta of standalone protective put
        # IVR thresholds
        "ivr_min_entry":            30,          # minimum IVR to consider new entry
        "ivr_high_threshold":       50,          # IVR above this = elevated IV environment
        # VIX regime thresholds
        "vix_low":                  15.0,        # VIX < this = low vol regime
        "vix_high":                 25.0,        # VIX > this = high vol regime
        "vix_extreme":              35.0,        # VIX > this = extreme vol / no new entries
    },

    # ── ALERTS ───────────────────────────────────────────────────────────────
    "alerts": {
        "delta_watch_threshold":    0.30,        # delta > this → WATCH alert
        "delta_act_threshold":      0.35,        # delta > this → ACT_IMMEDIATELY
        "mv_drawdown_warn_pct":     30.0,        # MV drawdown % → warning
        "mv_drawdown_act_pct":      50.0,        # MV drawdown % → act
        "dte_urgent_days":          14,          # DTE < this → urgent roll alert
        "dte_warning_days":         21,          # DTE < this → warning
        "concentration_warn_pct":   12.0,        # concentration → warning
        "concentration_act_pct":    15.0,        # concentration → act
        "vix_warn_threshold":       25.0,        # VIX above this → WARN
        "vix_act_threshold":        35.0,        # VIX above this → halt new entries
        "ivr_low_warn_threshold":   20,          # IVR below this → premium too thin
        "theta_decay_warn_pct":     0.10,        # daily theta burn > this % of NLV → warn
    },

    # ── UI / DISPLAY ──────────────────────────────────────────────────────────
    "ui": {
        "default_tab":              "briefing",
        "refresh_interval_s":       300,         # auto-refresh interval (0 = off)
        "theme":                    "dark",      # "dark" or "light"
        "show_greeks":              True,
        "show_pacing":              True,
        "show_spy_hedge":           True,
        "currency_display":         "USD",
        "date_format":              "YYYY-MM-DD",
        "timezone":                 "America/New_York",
    },
}

# ---------------------------------------------------------------------------
# In-memory store + lock
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_config: dict[str, Any] = {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result


def load() -> None:
    """
    Load config from disk, merging with defaults.
    Called once at application startup from main.py.
    Missing keys are filled from DEFAULTS — safe for upgrades.
    """
    global _config
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _CONFIG_FILE.exists():
        try:
            with _CONFIG_FILE.open("r", encoding="utf-8") as f:
                on_disk = json.load(f)
            merged = _deep_merge(DEFAULTS, on_disk)
            logger.info("Config loaded from %s", _CONFIG_FILE)
        except Exception as exc:
            logger.warning("Could not read config file (%s) — using defaults.", exc)
            merged = deepcopy(DEFAULTS)
    else:
        merged = deepcopy(DEFAULTS)
        logger.info("No config file found — using defaults. Will create on first save.")
    with _lock:
        _config = merged


def save() -> None:
    """
    Persist the current in-memory config to disk atomically.
    Uses write-to-temp + rename to avoid partial writes.
    Keeps a rolling backup of the previous version at fortress_config.bak.json.
    """
    tmp = _CONFIG_FILE.with_suffix(".tmp")
    with _lock:
        snapshot = deepcopy(_config)
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    # Rotate: current → .bak before replacing
    bak = _CONFIG_FILE.with_name(_CONFIG_FILE.stem + ".bak.json")
    if _CONFIG_FILE.exists():
        try:
            _CONFIG_FILE.replace(bak)
        except Exception as exc:
            logger.warning("Could not rotate config backup: %s", exc)
    tmp.replace(_CONFIG_FILE)
    logger.info("Config saved to %s (backup: %s)", _CONFIG_FILE, bak)


def cfg(key: str, default: Any = None) -> Any:
    """
    Read a config value using dot-notation.

    Examples:
        cfg("strategy.target_delta_low")      → 0.20
        cfg("technical.ibkr_gateway_port")    → 4001
        cfg("alerts.delta_act_threshold")     → 0.35

    Returns `default` if the key path does not exist.
    """
    with _lock:
        parts = key.split(".")
        node: Any = _config
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node


def set_value(key: str, value: Any) -> None:
    """
    Set a single config value using dot-notation and persist to disk.
    Creates intermediate dicts if needed.
    """
    with _lock:
        parts = key.split(".")
        node = _config
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    save()


def update_section(section: str, values: dict) -> None:
    """
    Bulk-update an entire section dict and persist to disk.
    Merges values into the existing section (does not replace the whole section).
    """
    with _lock:
        if section not in _config:
            _config[section] = {}
        _config[section].update(values)
    save()


def get_all() -> dict:
    """Return a deep copy of the entire config (safe for JSON serialisation)."""
    with _lock:
        return deepcopy(_config)


def get_section(section: str) -> dict:
    """Return a deep copy of a single section."""
    with _lock:
        return deepcopy(_config.get(section, {}))


def reset_to_defaults() -> None:
    """Reset the entire config to factory defaults and persist."""
    global _config
    with _lock:
        _config = deepcopy(DEFAULTS)
    save()
    logger.info("Config reset to defaults.")


# ---------------------------------------------------------------------------
# Auto-load on import (so any module can just `from app.services.config_store import cfg`)
# ---------------------------------------------------------------------------
load()
