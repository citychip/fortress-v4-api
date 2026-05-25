"""
Dashboard settings — schema-driven, backed by app.services.config_store.

Endpoints:
  GET    /api/settings              → {config: {...}}
  GET    /api/settings/schema       → {schema: {section: [field, ...]}}
  GET    /api/settings/trader_presets → {presets: [{id, label, description, config}]}
  PUT    /api/settings/{section}    → body {values: {key: new_value, ...}}
  POST   /api/settings/reset        → reset to factory defaults
  POST   /api/settings/apply_preset → body {preset_id: str}
  GET    /api/settings/narrative    → plain-English strategy state description
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import config_store

router = APIRouter()


# ---------------------------------------------------------------------------
# Schema — describes the editable fields per section.
# ---------------------------------------------------------------------------
SCHEMA: dict[str, list[dict]] = {
    "trader_profile": [
        {
            "key": "trader_type",
            "label": "Trader type",
            "type": "select",
            "options": [
                "income_seeker",
                "speculator",
                "volatility_trader",
                "hedger",
                "custom",
            ],
            "description": (
                "Defines your primary trading persona. "
                "income_seeker = premium collection (Wheel, Covered Calls, PCS). "
                "speculator = directional leverage (Long Calls/Puts, Vertical Spreads). "
                "volatility_trader = non-directional vol plays (Straddle, Strangle, Iron Condor). "
                "hedger = portfolio protection (Collar, Protective Put, SPY Hedge). "
                "custom = manual configuration."
            ),
        },
        {
            "key": "active_strategies",
            "label": "Active strategies",
            "type": "multiselect",
            "options": [
                # Income / Premium collection
                "COVERED_CALL",
                "CASH_SECURED_PUT",
                "WHEEL",
                "PMCC",
                "JADE_LIZARD",
                "PCS",
                # Directional / Speculative
                "LONG_CALL",
                "LONG_PUT",
                "BULL_CALL_SPREAD",
                "BEAR_PUT_SPREAD",
                "BULL_PUT_SPREAD",
                "BEAR_CALL_SPREAD",
                # Volatility / Non-directional
                "LONG_STRADDLE",
                "SHORT_STRADDLE",
                "LONG_STRANGLE",
                "SHORT_STRANGLE",
                "IRON_CONDOR",
                "IRON_BUTTERFLY",
                "BUTTERFLY",
                # Hedging / Portfolio protection
                "COLLAR",
                "PROTECTIVE_PUT",
                "SPY_HEDGE",
                # LEAPS / Long-term
                "LEAPS",
                "DIAGONAL",
                # Stock
                "STOCK",
            ],
            "description": "Strategies you actively trade. Drives scanner signals, entry gates, and narrative.",
        },
        {
            "key": "risk_tolerance",
            "label": "Risk tolerance",
            "type": "select",
            "options": ["conservative", "moderate", "aggressive"],
            "description": "conservative = defined-risk only, tighter stops. aggressive = wider bands, naked short options allowed.",
        },
        {
            "key": "primary_objective",
            "label": "Primary objective",
            "type": "select",
            "options": ["income", "growth", "protection", "speculation"],
            "description": "Drives narrative framing and scanner priority ordering.",
        },
    ],
    "strategy": [
        # --- Portfolio-level rules ---
        {"key": "portfolio_netliq_usd", "label": "Portfolio NetLiq target", "type": "number", "unit": "USD", "min": 0, "step": 1000},
        {"key": "max_positions", "label": "Max open positions", "type": "number", "min": 1, "max": 200, "step": 1},
        {"key": "entries_per_week_max", "label": "Entries per week (pacing cap)", "type": "number", "min": 0, "max": 20, "step": 1, "description": "Rolls and hedges are excluded"},
        {"key": "max_concentration_pct", "label": "Single-ticker concentration cap", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 0.5},
        {"key": "high_conc_threshold_pct", "label": "High-concentration threshold", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 0.5, "description": "Triggers tightened entry band"},
        {"key": "high_conc_size_cap", "label": "High-concentration size cap", "type": "number", "unit": "contracts", "min": 1, "max": 10},
        {"key": "sector_concentration_max_pct", "label": "Sector concentration cap", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 0.5},
        # --- Delta / Greeks targets ---
        {"key": "target_delta_low", "label": "Target short delta (low)", "type": "number", "min": 0.0, "max": 1.0, "step": 0.01, "description": "Lower bound of acceptable short-leg delta at entry"},
        {"key": "target_delta_high", "label": "Target short delta (high)", "type": "number", "min": 0.0, "max": 1.0, "step": 0.01, "description": "Upper bound of acceptable short-leg delta at entry"},
        {"key": "delta_critical_threshold", "label": "Critical-gamma delta", "type": "number", "min": 0.0, "max": 1.0, "step": 0.01, "description": "Flag positions above this delta — roll required"},
        {"key": "delta_bias_long_threshold", "label": "Portfolio long-bias threshold", "type": "number", "step": 100, "description": "Net portfolio delta above this → 'long' bias"},
        {"key": "delta_bias_short_threshold", "label": "Portfolio short-bias threshold", "type": "number", "step": 100, "description": "Net portfolio delta below this → 'short' bias"},
        # --- DTE / Time management ---
        {"key": "target_dte_low", "label": "Target DTE (low)", "type": "number", "unit": "days", "min": 1, "max": 730},
        {"key": "target_dte_high", "label": "Target DTE (high)", "type": "number", "unit": "days", "min": 1, "max": 730},
        {"key": "dte_roll_threshold", "label": "DTE roll trigger", "type": "number", "unit": "days", "min": 1, "max": 60, "description": "Roll short leg when DTE falls below this"},
        {"key": "dte_exceptions", "label": "DTE exception list", "type": "list", "description": "Positions exempt from DTE roll alerts. One entry per line, format: TICKER:YYYY-MM-DD (e.g. MSFT:2026-12-18)"},
        {"key": "leap_earnings_blackout_days", "label": "LEAP earnings blackout", "type": "number", "unit": "days", "min": 0, "max": 60, "description": "Block new short-leg entries this many days before earnings when a LEAP/PMCC long call is open on the same ticker"},
        # --- Profit / Loss management ---
        {"key": "profit_target_pct", "label": "Profit-take target", "type": "number", "unit": "% of max profit", "min": 10, "max": 100, "step": 5, "description": "Close position when this % of max profit is reached"},
        {"key": "stop_loss_drawdown_pct", "label": "Stop-loss drawdown threshold", "type": "number", "unit": "%", "min": 0, "max": 200, "step": 1, "description": "Max MV loss before stop-loss fires"},
        {"key": "stop_loss_sma200_buffer", "label": "Stop-loss 200-SMA buffer", "type": "number", "min": 0, "max": 0.5, "step": 0.005, "description": "Fraction below 200-SMA that fires Signal 1"},
        # --- Hedge settings ---
        {"key": "spy_hedge_min_usd", "label": "SPY hedge MV target — min", "type": "number", "unit": "USD", "min": 0, "step": 100},
        {"key": "spy_hedge_max_usd", "label": "SPY hedge MV target — max", "type": "number", "unit": "USD", "min": 0, "step": 100},
        {"key": "spy_hedge_target_usd", "label": "SPY hedge MV target — mid", "type": "number", "unit": "USD", "min": 0, "step": 100},
        # --- Liquidity floors ---
        {"key": "available_funds_min_usd", "label": "Available Funds floor", "type": "number", "unit": "USD", "min": 0, "step": 500},
        {"key": "excess_liq_min_usd", "label": "Excess Liquidity floor", "type": "number", "unit": "USD", "min": 0, "step": 500},
        # --- IV / Entry filters ---
        {"key": "ivr_min_entry", "label": "Min IVR for entry", "type": "number", "min": 0, "max": 100, "step": 1, "description": "Do not enter new positions below this IVR"},
        {"key": "ivr_high_threshold", "label": "High IVR threshold", "type": "number", "min": 0, "max": 100, "step": 1},
        {"key": "iv_crush_floor_pct", "label": "Post-earnings IV crush floor", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 1},
        # --- Entry band ---
        {"key": "prime_entry_gap_low", "label": "Prime-entry gap low", "type": "number", "unit": "%", "step": 0.1},
        {"key": "prime_entry_gap_high", "label": "Prime-entry gap high", "type": "number", "unit": "%", "step": 0.1},
        {"key": "high_conc_prime_low", "label": "High-conc prime gap low", "type": "number", "unit": "%", "step": 0.1},
        {"key": "high_conc_prime_high", "label": "High-conc prime gap high", "type": "number", "unit": "%", "step": 0.1},
        # --- VIX regime thresholds ---
        {"key": "vix_low", "label": "VIX low regime", "type": "number", "min": 0, "max": 100, "step": 0.5},
        {"key": "vix_high", "label": "VIX high regime", "type": "number", "min": 0, "max": 100, "step": 0.5},
        {"key": "vix_extreme", "label": "VIX extreme regime", "type": "number", "min": 0, "max": 100, "step": 0.5},
        # --- Per-strategy credit minimums ---
        {"key": "min_credit_covered_call", "label": "Min Covered Call credit", "type": "number", "unit": "USD", "min": 0, "step": 0.05},
        {"key": "min_credit_csp", "label": "Min Cash-Secured Put credit", "type": "number", "unit": "USD", "min": 0, "step": 0.05},
        {"key": "min_credit_jade_lizard", "label": "Min Jade Lizard credit", "type": "number", "unit": "USD", "min": 0, "step": 0.05},
        {"key": "min_credit_pcs", "label": "Min PCS credit", "type": "number", "unit": "USD", "min": 0, "step": 0.05},
        {"key": "min_credit_pmcc", "label": "Min PMCC roll credit", "type": "number", "unit": "USD", "min": 0, "step": 0.05},
        {"key": "min_credit_iron_condor", "label": "Min Iron Condor credit", "type": "number", "unit": "USD", "min": 0, "step": 0.05},
        {"key": "min_credit_strangle", "label": "Min Strangle credit", "type": "number", "unit": "USD", "min": 0, "step": 0.05},
        # --- Speculative / Long options ---
        {"key": "max_long_option_pct_nlv", "label": "Max long option cost (% NLV)", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 0.5, "description": "Cap on debit paid for long calls/puts as % of NetLiq"},
        {"key": "long_call_delta_target", "label": "Long call target delta", "type": "number", "min": 0.0, "max": 1.0, "step": 0.01, "description": "Preferred delta for long call entries (e.g. 0.70 for ITM, 0.50 for ATM)"},
        {"key": "long_put_delta_target", "label": "Long put target delta", "type": "number", "min": 0.0, "max": 1.0, "step": 0.01},
        {"key": "vertical_spread_width", "label": "Vertical spread width", "type": "number", "unit": "strikes", "min": 1, "max": 50, "step": 1, "description": "Default strike width for Bull/Bear call and put spreads"},
        # --- Volatility strategies ---
        {"key": "straddle_dte_target", "label": "Straddle/Strangle DTE target", "type": "number", "unit": "days", "min": 1, "max": 90},
        {"key": "iron_condor_wing_width", "label": "Iron Condor wing width", "type": "number", "unit": "strikes", "min": 1, "max": 50, "step": 1},
        {"key": "iron_condor_short_delta", "label": "Iron Condor short delta", "type": "number", "min": 0.0, "max": 0.5, "step": 0.01, "description": "Delta of the short strikes (e.g. 0.16 = 1 SD)"},
        {"key": "butterfly_body_width", "label": "Butterfly body width", "type": "number", "unit": "strikes", "min": 1, "max": 50, "step": 1},
        # --- LEAPS ---
        {"key": "leaps_profit_take_pct", "label": "LEAPS profit-take", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 1},
        {"key": "leaps_scale_out_pct", "label": "LEAPS scale-out tranche", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 1},
        {"key": "leaps_min_dte", "label": "LEAPS minimum DTE at entry", "type": "number", "unit": "days", "min": 90, "max": 730},
        # --- Collar / Protective Put ---
        {"key": "collar_put_delta_target", "label": "Collar protective put delta", "type": "number", "min": 0.0, "max": 1.0, "step": 0.01, "description": "Delta of the long put leg in a collar (e.g. 0.25 = 25-delta put)"},
        {"key": "collar_call_delta_target", "label": "Collar short call delta", "type": "number", "min": 0.0, "max": 1.0, "step": 0.01},
        {"key": "protective_put_delta_target", "label": "Protective put delta", "type": "number", "min": 0.0, "max": 1.0, "step": 0.01},
    ],
    "alerts": [
        {"key": "delta_watch_threshold", "label": "Delta WATCH threshold", "type": "number", "min": 0, "max": 1, "step": 0.01},
        {"key": "delta_act_threshold", "label": "Delta ACT threshold", "type": "number", "min": 0, "max": 1, "step": 0.01},
        {"key": "mv_drawdown_warn_pct", "label": "MV drawdown WARN", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 1},
        {"key": "mv_drawdown_act_pct", "label": "MV drawdown ACT", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 1},
        {"key": "dte_urgent_days", "label": "DTE urgent threshold", "type": "number", "unit": "days", "min": 1, "max": 60},
        {"key": "dte_warning_days", "label": "DTE warning threshold", "type": "number", "unit": "days", "min": 1, "max": 60},
        {"key": "concentration_warn_pct", "label": "Concentration WARN", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 0.5},
        {"key": "concentration_act_pct", "label": "Concentration ACT", "type": "number", "unit": "%", "min": 0, "max": 100, "step": 0.5},
        {"key": "vix_warn_threshold", "label": "VIX WARN level", "type": "number", "min": 0, "max": 100, "step": 0.5, "description": "Alert when VIX crosses above this level"},
        {"key": "vix_act_threshold", "label": "VIX ACT level", "type": "number", "min": 0, "max": 100, "step": 0.5, "description": "Halt new entries when VIX crosses above this level"},
        {"key": "ivr_low_warn_threshold", "label": "IVR low WARN", "type": "number", "min": 0, "max": 100, "step": 1, "description": "Warn when IVR drops below this (premium too thin)"},
        {"key": "theta_decay_warn_pct", "label": "Theta decay WARN (% NLV/day)", "type": "number", "unit": "%", "min": 0, "max": 5, "step": 0.01, "description": "Alert when daily theta burn exceeds this % of NLV"},
    ],
    "security": [
        # --- Data source toggles ---
        {"key": "use_ibkr_web_api",   "label": "Enable IBKR Web API",  "type": "boolean",
         "description": "Connect to IB Gateway for live positions, Greeks, and account values. When disabled, Greeks are estimated via Black-Scholes (yfinance) and positions are read from the last saved snapshot. NetLiq and account values will be stale."},
        {"key": "use_quantdata",       "label": "Enable QuantData",      "type": "boolean",
         "description": "Power IV rank scanning, dark pool alerts, whale flow, macro regime, and DP/GEX chart overlays via QuantData.us. When disabled, workflow scripts are blocked, the candidate scanner is empty, macro regime shows as unknown, and the price chart shows plain candlesticks only."},
        # --- IBKR auto-sync ---
        {"key": "ibkr_auto_sync_enabled", "label": "Auto-sync IBKR", "type": "boolean",
         "description": "When enabled, the server automatically syncs positions from IBKR every N minutes regardless of browser activity. When disabled (default), sync is manual-only via the Sync button."},
        {"key": "ibkr_auto_sync_interval_min", "label": "Auto-sync interval", "type": "select",
         "options": [5, 15, 30, 60],
         "description": "How often to auto-sync IBKR positions (minutes). Only applies when Auto-sync IBKR is enabled."},
        # --- Credentials ---
        {"key": "ibkr_account_id",      "label": "IBKR Account ID",        "type": "password", "description": "Your IBKR account number (e.g. U1234567). Stored locally, never sent externally."},
        {"key": "quantdata_auth_token", "label": "QuantData Auth Token",   "type": "password", "description": "JWT auth token from QuantData.us (Authorization header value, starts with 'Bearer '). Obtain from browser DevTools → Network → any /api/ request."},
        {"key": "quantdata_instance_id","label": "QuantData Instance ID",  "type": "password", "description": "x-instance-id header value from QuantData.us requests."},
        {"key": "quantdata_api_key",   "label": "QuantData API key (legacy)", "type": "password", "description": "Legacy key — unused. Kept for backward compatibility."},
        {"key": "api_token_hint",      "label": "Dashboard API token",    "type": "text",     "description": "Read-only. Real token is set via FORTRESS_API_TOKEN env var on the server."},
        {"key": "cp_gateway_url",      "label": "CP Gateway URL",         "type": "text",     "description": "voyz/ibeam endpoint, e.g. https://localhost:5000"},
        {"key": "cp_gateway_verify_ssl","label": "Verify CP Gateway SSL",  "type": "boolean"},
        {"key": "cp_gateway_timeout_s", "label": "CP Gateway timeout",     "type": "number",   "unit": "s", "min": 5, "max": 120},
        {"key": "quantdata_api_base",   "label": "QuantData API base URL",  "type": "text"},
    ],
    "technical": [
        {"key": "greeks_backend", "label": "Greeks backend", "type": "select", "options": ["auto", "web_api", "bs_yfinance"], "description": "auto = pick best available; web_api uses CP Gateway + OPRA; bs_yfinance = Black-Scholes from yfinance"},
        {"key": "vps_ip", "label": "VPS IP", "type": "text"},
        {"key": "dashboard_port", "label": "Dashboard port", "type": "number", "min": 1, "max": 65535},
        {"key": "api_base_url", "label": "API base URL", "type": "text"},
        {"key": "ibkr_gateway_host",       "label": "IBKR Gateway host",           "type": "text"},
        {"key": "ibkr_gateway_port",       "label": "IBKR Gateway port",           "type": "number", "min": 1, "max": 65535},
        {"key": "ibkr_gateway_client_id",  "label": "IBKR client ID",              "type": "number", "min": 1, "max": 1000},
        {"key": "ibkr_gateway_timeout_s",  "label": "IBKR Gateway timeout",        "type": "number", "unit": "s", "min": 5, "max": 600},
        {"key": "ibkr_delta_timeout_s",    "label": "IBKR delta snapshot timeout",  "type": "number", "unit": "s", "min": 1, "max": 60},
        {"key": "data_dir", "label": "Data directory", "type": "text"},
        {"key": "reports_dir", "label": "Reports directory", "type": "text"},
        {"key": "uploads_dir", "label": "Uploads directory", "type": "text"},
        {"key": "base_currency", "label": "Base currency", "type": "select", "options": ["USD", "EUR", "GBP"]},
        {"key": "fx_refresh_interval_min", "label": "FX refresh interval", "type": "number", "unit": "min", "min": 1, "max": 1440},
        {"key": "service_name", "label": "systemd service name", "type": "text"},
    ],
    "ui": [
        {"key": "default_tab", "label": "Default tab", "type": "select", "options": ["dashboard", "positions", "manage", "trade", "data", "journal", "strategy", "settings"]},
        {"key": "refresh_interval_s", "label": "Auto-refresh interval", "type": "number", "unit": "s", "min": 0, "max": 3600, "description": "0 disables auto-refresh"},
        {"key": "theme", "label": "Theme", "type": "select", "options": ["dark", "light"]},
        {"key": "show_greeks", "label": "Show Portfolio Greeks card", "type": "boolean"},
        {"key": "show_pacing", "label": "Show pacing card", "type": "boolean"},
        {"key": "show_spy_hedge", "label": "Show SPY hedge card", "type": "boolean"},
        {"key": "currency_display", "label": "Currency display", "type": "select", "options": ["USD", "EUR", "BOTH"]},
        {"key": "date_format", "label": "Date format", "type": "select", "options": ["YYYY-MM-DD", "DD-MM-YYYY", "MM/DD/YYYY"]},
        {"key": "timezone", "label": "Timezone", "type": "text"},
    ],
}


# ---------------------------------------------------------------------------
# Trader presets — factory configurations for each persona
# ---------------------------------------------------------------------------
TRADER_PRESETS = {
    "income_seeker": {
        "label": "Income Seeker",
        "description": (
            "Conservative yield-focused trader. Generates steady premium income by selling "
            "options against owned stock or cash. Primary strategies: Covered Call, "
            "Cash-Secured Put, and the Wheel. Defined-risk only, low DTE, tight stops."
        ),
        "icon": "💰",
        "trader_profile": {
            "trader_type": "income_seeker",
            "active_strategies": ["COVERED_CALL", "CASH_SECURED_PUT", "WHEEL", "PCS", "SPY_HEDGE"],
            "risk_tolerance": "conservative",
            "primary_objective": "income",
        },
        "strategy": {
            "target_delta_low": 0.20,
            "target_delta_high": 0.30,
            "delta_critical_threshold": 0.40,
            "target_dte_low": 30,
            "target_dte_high": 45,
            "dte_roll_threshold": 21,
            "profit_target_pct": 50,
            "stop_loss_drawdown_pct": 50,
            "ivr_min_entry": 30,
            "ivr_high_threshold": 50,
            "min_credit_covered_call": 0.30,
            "min_credit_csp": 0.50,
            "max_positions": 15,
            "entries_per_week_max": 3,
            "max_concentration_pct": 15,
        },
        "alerts": {
            "delta_watch_threshold": 0.30,
            "delta_act_threshold": 0.40,
            "mv_drawdown_warn_pct": 30,
            "mv_drawdown_act_pct": 50,
            "dte_urgent_days": 14,
            "dte_warning_days": 21,
        },
    },
    "speculator": {
        "label": "Strategic Speculator",
        "description": (
            "Directional trader seeking leverage on price movement. Uses long calls/puts "
            "and vertical spreads to express a view with defined risk. Higher risk tolerance, "
            "wider position sizing, shorter holding periods."
        ),
        "icon": "📈",
        "trader_profile": {
            "trader_type": "speculator",
            "active_strategies": ["LONG_CALL", "LONG_PUT", "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"],
            "risk_tolerance": "aggressive",
            "primary_objective": "growth",
        },
        "strategy": {
            "target_delta_low": 0.40,
            "target_delta_high": 0.70,
            "delta_critical_threshold": 0.80,
            "target_dte_low": 14,
            "target_dte_high": 45,
            "dte_roll_threshold": 7,
            "profit_target_pct": 100,
            "stop_loss_drawdown_pct": 100,
            "ivr_min_entry": 20,
            "long_call_delta_target": 0.50,
            "long_put_delta_target": 0.50,
            "vertical_spread_width": 5,
            "max_long_option_pct_nlv": 5,
            "max_positions": 20,
            "entries_per_week_max": 5,
            "max_concentration_pct": 10,
        },
        "alerts": {
            "delta_watch_threshold": 0.60,
            "delta_act_threshold": 0.80,
            "mv_drawdown_warn_pct": 50,
            "mv_drawdown_act_pct": 100,
            "dte_urgent_days": 5,
            "dte_warning_days": 10,
        },
    },
    "volatility_trader": {
        "label": "Volatility Trader",
        "description": (
            "Non-directional trader who profits from volatility expansion or contraction. "
            "Trades Straddles, Strangles, Iron Condors, and Butterflies. Does not care about "
            "direction — only about how much the underlying moves."
        ),
        "icon": "⚡",
        "trader_profile": {
            "trader_type": "volatility_trader",
            "active_strategies": ["IRON_CONDOR", "SHORT_STRANGLE", "LONG_STRADDLE", "IRON_BUTTERFLY", "BUTTERFLY"],
            "risk_tolerance": "moderate",
            "primary_objective": "income",
        },
        "strategy": {
            "target_delta_low": 0.10,
            "target_delta_high": 0.20,
            "delta_critical_threshold": 0.30,
            "target_dte_low": 30,
            "target_dte_high": 60,
            "dte_roll_threshold": 21,
            "profit_target_pct": 50,
            "stop_loss_drawdown_pct": 200,
            "ivr_min_entry": 40,
            "ivr_high_threshold": 60,
            "iron_condor_short_delta": 0.16,
            "iron_condor_wing_width": 5,
            "straddle_dte_target": 30,
            "butterfly_body_width": 5,
            "min_credit_iron_condor": 1.00,
            "min_credit_strangle": 1.50,
            "max_positions": 10,
            "entries_per_week_max": 4,
            "max_concentration_pct": 20,
        },
        "alerts": {
            "delta_watch_threshold": 0.20,
            "delta_act_threshold": 0.30,
            "mv_drawdown_warn_pct": 100,
            "mv_drawdown_act_pct": 200,
            "dte_urgent_days": 14,
            "dte_warning_days": 21,
            "ivr_low_warn_threshold": 30,
        },
    },
    "hedger": {
        "label": "Portfolio Protector",
        "description": (
            "Risk manager who uses options as insurance for an existing stock portfolio. "
            "Trades Collars, Protective Puts, and SPY hedges. Willing to sacrifice some "
            "upside to protect against crashes."
        ),
        "icon": "🛡️",
        "trader_profile": {
            "trader_type": "hedger",
            "active_strategies": ["COLLAR", "PROTECTIVE_PUT", "SPY_HEDGE", "COVERED_CALL"],
            "risk_tolerance": "conservative",
            "primary_objective": "protection",
        },
        "strategy": {
            "target_delta_low": 0.20,
            "target_delta_high": 0.35,
            "delta_critical_threshold": 0.50,
            "target_dte_low": 30,
            "target_dte_high": 90,
            "dte_roll_threshold": 30,
            "profit_target_pct": 75,
            "stop_loss_drawdown_pct": 25,
            "ivr_min_entry": 20,
            "collar_put_delta_target": 0.25,
            "collar_call_delta_target": 0.25,
            "protective_put_delta_target": 0.30,
            "spy_hedge_min_usd": 20000,
            "spy_hedge_max_usd": 35000,
            "spy_hedge_target_usd": 27500,
            "max_positions": 20,
            "entries_per_week_max": 2,
            "max_concentration_pct": 25,
        },
        "alerts": {
            "delta_watch_threshold": 0.40,
            "delta_act_threshold": 0.50,
            "mv_drawdown_warn_pct": 15,
            "mv_drawdown_act_pct": 25,
            "dte_urgent_days": 21,
            "dte_warning_days": 30,
            "vix_warn_threshold": 20,
            "vix_act_threshold": 30,
        },
    },
    "pmcc_income": {
        "label": "PMCC Income (Current)",
        "description": (
            "Poor Man's Covered Call income strategy. Buys deep ITM LEAPS as a stock "
            "substitute and sells short-dated OTM calls against them. Combines income "
            "generation with leveraged long exposure. Current Fortress default."
        ),
        "icon": "🏰",
        "trader_profile": {
            "trader_type": "income_seeker",
            "active_strategies": ["PMCC", "JADE_LIZARD", "PCS", "SPY_HEDGE", "LEAPS"],
            "risk_tolerance": "moderate",
            "primary_objective": "income",
        },
        "strategy": {
            "target_delta_low": 0.20,
            "target_delta_high": 0.25,
            "delta_critical_threshold": 0.35,
            "target_dte_low": 30,
            "target_dte_high": 45,
            "dte_roll_threshold": 21,
            "profit_target_pct": 50,
            "stop_loss_drawdown_pct": 50,
            "stop_loss_sma200_buffer": 0.02,
            "ivr_min_entry": 30,
            "ivr_high_threshold": 50,
            "min_credit_jade_lizard": 1.0,
            "min_credit_pcs": 0.5,
            "min_credit_pmcc": 0.3,
            "leaps_profit_take_pct": 50,
            "leaps_scale_out_pct": 25,
            "leaps_min_dte": 365,
            "max_positions": 20,
            "entries_per_week_max": 4,
            "max_concentration_pct": 15,
            "spy_hedge_min_usd": 22000,
            "spy_hedge_max_usd": 33000,
            "spy_hedge_target_usd": 27500,
        },
        "alerts": {
            "delta_watch_threshold": 0.30,
            "delta_act_threshold": 0.35,
            "mv_drawdown_warn_pct": 30,
            "mv_drawdown_act_pct": 50,
            "dte_urgent_days": 14,
            "dte_warning_days": 21,
            "concentration_warn_pct": 12,
            "concentration_act_pct": 15,
        },
    },
}


class SectionUpdate(BaseModel):
    values: dict


class PresetApply(BaseModel):
    preset_id: str


@router.get("/settings")
def get_settings():
    """Return the entire current config under {config: {...}}."""
    return {"config": config_store.get_all()}


@router.get("/settings/schema")
def get_schema():
    """Return the schema describing each editable field per section."""
    return {"schema": SCHEMA}


@router.get("/settings/trader_presets")
def get_trader_presets():
    """Return all available trader presets with their metadata and config."""
    return {
        "presets": [
            {
                "id": pid,
                "label": p["label"],
                "description": p["description"],
                "icon": p.get("icon", ""),
                "strategies": p.get("trader_profile", {}).get("active_strategies", []),
                "risk_tolerance": p.get("trader_profile", {}).get("risk_tolerance", ""),
                "primary_objective": p.get("trader_profile", {}).get("primary_objective", ""),
            }
            for pid, p in TRADER_PRESETS.items()
        ]
    }


@router.post("/settings/apply_preset")
def apply_preset(body: PresetApply):
    """Apply a trader preset — overwrites trader_profile, strategy, and alerts sections."""
    pid = body.preset_id
    if pid not in TRADER_PRESETS:
        raise HTTPException(status_code=404, detail=f"Unknown preset: {pid!r}")
    preset = TRADER_PRESETS[pid]
    for section in ("trader_profile", "strategy", "alerts"):
        if section in preset:
            config_store.update_section(section, preset[section])
    return {
        "ok": True,
        "preset_id": pid,
        "label": preset["label"],
        "config": config_store.get_all(),
    }


@router.put("/settings/{section}")
def update_section(section: str, body: SectionUpdate):
    """Bulk-update a single section. body = {values: {key: new_value, ...}}."""
    if section not in SCHEMA:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")
    valid_keys = {f["key"] for f in SCHEMA[section]}
    bad = [k for k in body.values.keys() if k not in valid_keys]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown keys for section {section!r}: {bad}")
    config_store.update_section(section, body.values)
    # Mirror ibkr_account_id to dashboard_settings.json so the sync picks it up immediately
    if section == "security" and "ibkr_account_id" in body.values:
        _new_id = body.values["ibkr_account_id"]
        _PLACEHOLDER = "YOUR_IBKR_ACCOUNT_ID"
        if _new_id and _new_id != _PLACEHOLDER:
            try:
                from app.services import state as _state
                _state.save_dashboard_settings({"ibkr_account_id": _new_id})
            except Exception:
                pass
    return {
        "ok": True,
        "section": section,
        "updated_keys": list(body.values.keys()),
        "config": config_store.get_section(section),
    }


@router.get("/settings/narrative")
def get_narrative():
    """
    Return a structured plain-English narrative describing the current strategy state.
    Adapts language to the active trader_type and active_strategies.
    """
    import datetime
    from app.services import state, config_store

    cfg = config_store.get_all()
    s = cfg.get("strategy", {})
    a = cfg.get("alerts", {})
    tp = cfg.get("trader_profile", {})

    trader_type = tp.get("trader_type", "custom")
    active_strats = tp.get("active_strategies", s.get("active_strategies", []))
    risk_tol = tp.get("risk_tolerance", "moderate")

    try:
        briefing = state.get_briefing_data()
    except Exception:
        briefing = {}

    greeks      = briefing.get("greeks", {})
    pacing      = briefing.get("pacing", {})
    macro       = briefing.get("macro_regime", {})
    account     = briefing.get("account", {})
    conc        = briefing.get("concentration", {})
    actions     = briefing.get("actions", [])

    delta_target    = s.get("target_delta_high", 0.25)
    delta_band      = s.get("delta_bias_long_threshold", 700)
    pacing_max      = s.get("entries_per_week_max", 4)
    profit_target   = s.get("profit_target_pct", 50)
    dte_roll        = s.get("dte_roll_threshold", 21)
    max_conc        = s.get("max_concentration_pct", 15)
    spy_min         = s.get("spy_hedge_min_usd", 22000)
    spy_max         = s.get("spy_hedge_max_usd", 33000)
    stop_sma_pct    = s.get("stop_loss_sma200_buffer", 0.02)

    port_delta      = greeks.get("portfolio_delta")
    port_theta      = greeks.get("portfolio_theta")
    port_vega       = greeks.get("portfolio_vega")
    pos_with_greeks = greeks.get("positions_with_greeks", 0)
    pos_total       = greeks.get("positions_total", 0)

    pacing_used      = pacing.get("used", 0)
    pacing_remaining = pacing.get("remaining", pacing_max)

    regime      = (macro.get("regime") or "unknown").lower()
    vix         = macro.get("vix")
    vix_state   = (macro.get("vix_state") or "").lower()

    net_liq     = account.get("net_liq")
    avail_funds = account.get("available_funds")

    top_conc    = conc.get("top", {})
    top_ticker  = top_conc.get("ticker", "—")
    top_pct     = top_conc.get("pct")

    def fmt_usd(v):
        return "—" if v is None else f"${v:,.0f}"

    def fmt_delta(v):
        if v is None:
            return "—"
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:,.0f}"

    def fmt_pct(v):
        return "—" if v is None else f"{v:.1f}%"

    # Trader-type persona label
    persona_labels = {
        "income_seeker": "Income Seeker (premium collection)",
        "speculator": "Strategic Speculator (directional)",
        "volatility_trader": "Volatility Trader (non-directional)",
        "hedger": "Portfolio Protector (hedging)",
        "custom": "Custom",
    }
    persona = persona_labels.get(trader_type, trader_type)
    strats_str = ", ".join(active_strats) if active_strats else "none configured"

    regime_desc = {
        "bullish":  "bullish (VIX low, trend up — full entry budget available)",
        "neutral":  "neutral (VIX moderate — standard entry rules apply)",
        "bearish":  "bearish (VIX elevated — extra confirmation required for new entries)",
        "unknown":  "unknown (macro data not yet loaded)",
    }.get(regime, regime)

    delta_status = "within target band"
    delta_note = ""
    if port_delta is not None:
        if abs(port_delta) > delta_band:
            delta_status = "OUTSIDE target band — review required"
            delta_note = f" Your current delta of {fmt_delta(port_delta)} exceeds the ±{delta_band:,} band."
        elif abs(port_delta) > delta_band * 0.85:
            delta_status = "approaching band limit"
            delta_note = f" At {fmt_delta(port_delta)}, you are within 15% of the ±{delta_band:,} limit."

    if pacing_remaining == 0:
        pacing_desc = f"fully used ({pacing_used}/{pacing_max} entries this week — no new entries until next week)"
    elif pacing_remaining == pacing_max:
        pacing_desc = f"fully available ({pacing_used}/{pacing_max} entries used — {pacing_remaining} remaining)"
    else:
        pacing_desc = f"partially used ({pacing_used}/{pacing_max} entries used — {pacing_remaining} remaining)"

    conc_note = ""
    if top_pct is not None and top_pct > max_conc:
        conc_note = (
            f" ⚠️ {top_ticker} at {fmt_pct(top_pct)} of NLV exceeds your {fmt_pct(max_conc)} concentration limit."
        )

    try:
        spy_cov = state.get_spy_hedge_coverage()
        hedge_mv = spy_cov.get("current_market_value_usd", 0) or 0
        hedge_ok = spy_cov.get("coverage_ok", False)
    except Exception:
        hedge_mv = 0
        hedge_ok = False

    hedge_relevant = "SPY_HEDGE" in active_strats or "COLLAR" in active_strats or "PROTECTIVE_PUT" in active_strats
    if hedge_ok:
        hedge_desc = f"adequate ({fmt_usd(hedge_mv)} — within ${spy_min/1000:.0f}K–${spy_max/1000:.0f}K target)"
        hedge_flag = ""
    elif hedge_mv == 0:
        hedge_desc = f"MISSING — $0 vs ${spy_min/1000:.0f}K–${spy_max/1000:.0f}K target"
        hedge_flag = " ⚠️ This is the highest-priority structural gap in the portfolio." if hedge_relevant else ""
    else:
        hedge_desc = f"below target ({fmt_usd(hedge_mv)} vs ${spy_min/1000:.0f}K–${spy_max/1000:.0f}K target)"
        hedge_flag = " ⚠️ Consider adding protection." if hedge_relevant else ""

    greeks_coverage = f"{pos_with_greeks}/{pos_total} positions" if pos_total else "—"

    para1 = (
        f"You are configured as a **{persona}** trader with {risk_tol} risk tolerance. "
        f"Active strategies: **{strats_str}**. "
        f"The macro overlay is **{regime_desc}**. "
        f"Portfolio delta is **{fmt_delta(port_delta)}** ({delta_status}){delta_note}. "
        f"Daily theta is **{fmt_theta(port_theta)}** and vega is **{fmt_vega(port_vega)}**."
    )

    para2 = (
        f"Weekly entry pacing is **{pacing_desc}**. "
        f"Your profit-taking target is **{profit_target}% of max profit**, "
        f"and you roll short legs when DTE reaches **{dte_roll} days**. "
        f"Stop-loss triggers when price closes below the 200-SMA by more than **{stop_sma_pct*100:.1f}%** "
        f"(combined with a second confirming signal)."
    )

    if hedge_relevant:
        para3 = (
            f"Portfolio hedge coverage is **{hedge_desc}**.{hedge_flag} "
            f"Largest single-ticker concentration is **{top_ticker} at {fmt_pct(top_pct)}** of NLV "
            f"(limit: {fmt_pct(max_conc)}).{conc_note}"
        )
    else:
        para3 = (
            f"Largest single-ticker concentration is **{top_ticker} at {fmt_pct(top_pct)}** of NLV "
            f"(limit: {fmt_pct(max_conc)}).{conc_note} "
            f"No portfolio hedge is configured for this trader type."
        )

    para4 = (
        f"Net liquidation is **{fmt_usd(net_liq)}** with **{fmt_usd(avail_funds)}** available. "
        f"Greeks coverage: **{greeks_coverage}** with live data."
    )

    observations = []

    if regime == "bearish":
        observations.append({
            "level": "warn",
            "text": f"Bearish macro regime active (VIX {vix or '—'}, {vix_state}). Extra confirmation required for new entries."
        })

    if hedge_relevant and not hedge_ok:
        observations.append({
            "level": "critical" if hedge_mv == 0 else "warn",
            "text": f"Portfolio hedge {hedge_desc}. Target: ${spy_min/1000:.0f}K–${spy_max/1000:.0f}K notional."
        })

    if top_pct is not None and top_pct > max_conc:
        observations.append({
            "level": "warn",
            "text": f"{top_ticker} concentration at {fmt_pct(top_pct)} exceeds the {fmt_pct(max_conc)} limit. No new {top_ticker} entries."
        })

    if pacing_remaining == 0:
        observations.append({"level": "info", "text": "Weekly entry budget is fully used. No new entries until next Monday."})
    elif pacing_remaining > 0 and regime not in ("bearish",):
        observations.append({"level": "info", "text": f"{pacing_remaining} entry slot{'s' if pacing_remaining > 1 else ''} available this week."})

    for action in actions:
        observations.append({
            "level": "critical" if action.get("priority") == "HIGH" else "warn",
            "text": f"[{action.get('ticker', '')}] {action.get('title', '')}: {action.get('description', '')}"
        })

    if port_delta is not None and abs(port_delta) > delta_band * 0.85:
        observations.append({
            "level": "warn",
            "text": f"Portfolio delta {fmt_delta(port_delta)} approaching the ±{delta_band:,} band. Consider delta-reducing adjustments."
        })

    what_if = []
    if delta_target < 0.40 and trader_type in ("income_seeker", "pmcc_income"):
        what_if.append(
            f"Raising target_delta_high to 0.40 would place short calls closer to the money — "
            f"more premium collected but less cushion before stop-loss triggers."
        )
    if profit_target > 40:
        what_if.append(
            f"Lowering profit_target to 40% would close positions faster, "
            f"freeing capital sooner but capturing less premium per trade."
        )
    if hedge_relevant and not hedge_ok and net_liq and net_liq > 0:
        target_mid = (spy_min + spy_max) / 2
        what_if.append(
            f"Adding a ${target_mid/1000:.0f}K portfolio hedge would represent "
            f"{fmt_pct(target_mid / net_liq * 100)} of NLV — within normal protective sizing."
        )

    return {
        "as_of": datetime.datetime.utcnow().isoformat() + "Z",
        "trader_type": trader_type,
        "active_strategies": active_strats,
        "paragraphs": [para1, para2, para3, para4],
        "observations": observations,
        "what_if": what_if,
        "raw": {
            "regime": regime,
            "portfolio_delta": port_delta,
            "portfolio_theta": port_theta,
            "portfolio_vega": port_vega,
            "pacing_used": pacing_used,
            "pacing_max": pacing_max,
            "hedge_ok": hedge_ok,
            "hedge_mv_usd": hedge_mv,
            "top_concentration_ticker": top_ticker,
            "top_concentration_pct": top_pct,
            "net_liq": net_liq,
        }
    }


def fmt_theta(v):
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}${abs(v):.1f}/day"


def fmt_vega(v):
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}"


@router.post("/settings/reset")
def reset_settings():
    """Reset entire config to factory defaults."""
    config_store.reset_to_defaults()
    return {"ok": True, "config": config_store.get_all()}


# ---------------------------------------------------------------------------
# Backup / Restore
# ---------------------------------------------------------------------------

import zipfile, io, json as _json
from fastapi.responses import StreamingResponse
from fastapi import UploadFile, File


@router.get("/settings/backup")
def export_backup():
    """
    Download a ZIP archive containing:
      - fortress_config.json      (all settings)
      - ticker_universe.json      (watchlist)
      - alerts.json               (active alerts)
      - journal.json              (trade log)
      - chart_annotations.json   (chart notes)
    Excludes positions, uploads, and any file > 1 MB.
    """
    data_dir = config_store.get_section("technical").get("data_dir", "./quant")
    import os
    files_to_include = [
        ("fortress_config.json",     os.path.join(data_dir, "fortress_config.json")),
        ("ticker_universe.json",     os.path.join(data_dir, "ticker_universe.json")),
        ("alerts.json",              os.path.join(data_dir, "alerts.json")),
        ("journal.json",             os.path.join(data_dir, "journal.json")),
        ("chart_annotations.json",   os.path.join(data_dir, "chart_annotations.json")),
        ("earnings_blocklist.json",  os.path.join(data_dir, "earnings_blocklist.json")),
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = []
        for arc_name, path in files_to_include:
            if os.path.exists(path) and os.path.getsize(path) < 1_048_576:
                zf.write(path, arc_name)
                manifest.append(arc_name)
        # Write a manifest so the user knows what's inside
        zf.writestr("MANIFEST.txt", "\n".join(manifest) + "\n")
    buf.seek(0)
    import datetime as _dt
    ts = _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"fortress_backup_{ts}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/settings/restore")
async def import_backup(file: UploadFile = File(...)):
    """
    Upload a fortress_backup_*.zip to restore settings.
    Only fortress_config.json is applied to the live config.
    All other files are written to the data_dir.
    Returns a summary of what was restored.
    """
    import os
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip backup files are accepted.")
    content = await file.read()
    if len(content) > 5_242_880:  # 5 MB hard cap
        raise HTTPException(status_code=413, detail="Backup file too large (max 5 MB).")
    data_dir = config_store.get_section("technical").get("data_dir", "./quant")
    restored = []
    skipped = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = zf.namelist()
            for arc_name in names:
                if arc_name == "MANIFEST.txt":
                    continue
                if not arc_name.endswith(".json"):
                    skipped.append(arc_name)
                    continue
                raw = zf.read(arc_name)
                parsed = _json.loads(raw)
                dest = os.path.join(data_dir, arc_name)
                # For fortress_config.json, also apply to live config
                if arc_name == "fortress_config.json":
                    for section, values in parsed.items():
                        if isinstance(values, dict):
                            config_store.update_section(section, values)
                # Write the file to disk
                with open(dest, "w") as f:
                    _json.dump(parsed, f, indent=2)
                restored.append(arc_name)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid or corrupted ZIP file.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {e}")
    return {
        "ok": True,
        "restored": restored,
        "skipped": skipped,
        "config": config_store.get_all(),
    }


# ---------------------------------------------------------------------------
# QuantData connection test  (item J)
# ---------------------------------------------------------------------------

@router.post("/settings/test_quantdata")
def test_quantdata_connection():
    """
    Test the QuantData live API credentials.
    Reads credentials from ~/.quantdata-mcp/config.json (same source as quantdata_daily.py).
    Uses curl_cffi to impersonate Chrome (required by QuantData CDN protection).
    """
    import json as _json
    import pathlib as _pathlib
    from datetime import datetime as _datetime, timezone as _timezone

    # Read credentials from the MCP config file
    mcp_config_path = _pathlib.Path.home() / ".quantdata-mcp" / "config.json"
    if not mcp_config_path.exists():
        return {
            "ok": False,
            "error": "credentials_missing",
            "message": "QuantData MCP config not found at ~/.quantdata-mcp/config.json",
        }
    try:
        mcp_cfg = _json.loads(mcp_config_path.read_text())
    except Exception as e:
        return {
            "ok": False,
            "error": "credentials_missing",
            "message": f"Could not read QuantData MCP config: {e}",
        }

    token = mcp_cfg.get("auth_token", "")
    cookie = mcp_cfg.get("cookie", "")
    tools = mcp_cfg.get("tools", {})
    iv_rank_tool_id = tools.get("iv_rank", "")

    if not token or not iv_rank_tool_id:
        return {
            "ok": False,
            "error": "credentials_missing",
            "message": "QuantData auth_token or iv_rank tool ID missing from ~/.quantdata-mcp/config.json",
        }

    BASE_URL = "https://core-lb-prod.quantdata.us/api"
    headers = {
        "accept": "application/json",
        "authorization": token,
        "cookie": cookie,
        "origin": "https://v3.quantdata.us",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "content-type": "application/json",
    }

    try:
        from curl_cffi import requests as _cffi_req
        sess = _cffi_req.Session(impersonate="chrome110")
        sess.headers.update(headers)
        resp = sess.get(f"{BASE_URL}/options/iv-rank/{iv_rank_tool_id}", timeout=15)
    except ImportError:
        # Fallback to plain requests if curl_cffi not available
        import requests as _req
        resp = _req.get(
            f"{BASE_URL}/options/iv-rank/{iv_rank_tool_id}",
            headers=headers,
            timeout=15,
        )

    if resp.status_code == 200:
        data = resp.json().get("response", {})
        ivr_map = data.get("sessionDateToIVRankData", {})
        iv_rank = None
        ticker_in_tool = None

        # Get ticker from tool metadata
        tool_dto = data.get("toolDTO", {})
        if tool_dto:
            filt = tool_dto.get("metadata", {}).get("filter", {})
            ticker_in_tool = filt.get("ticker", {}).get("value", "?")

        if ivr_map:
            latest_date = sorted(ivr_map.keys())[-1]
            today_data = ivr_map.get(latest_date, {})
            ct_data = today_data.get("contractTypeToIVData", {})
            # Prefer CALL data; fall back to PUT
            iv_data = ct_data.get("CALL") or ct_data.get("PUT") or {}
            last_iv = iv_data.get("lastIV")
            min_iv = iv_data.get("windowMinIV")
            max_iv = iv_data.get("windowMaxIV")
            if last_iv is not None and min_iv is not None and max_iv is not None:
                iv_range = max_iv - min_iv
                if iv_range > 0:
                    iv_rank = round((last_iv - min_iv) / iv_range * 100, 1)
                else:
                    iv_rank = 0.0

        ticker_label = ticker_in_tool or "last-used ticker"
        return {
            "ok": True,
            "message": f"QuantData connection successful. {ticker_label} IV Rank: {iv_rank}",
            "iv_rank": iv_rank,
            "status_code": 200,
        }
    elif resp.status_code == 401:
        return {
            "ok": False,
            "error": "unauthorized",
            "message": "QuantData returned 401 — token or cookie expired. Re-run qd_setup.py to refresh credentials.",
            "status_code": 401,
        }
    elif resp.status_code == 429:
        return {
            "ok": False,
            "error": "rate_limited",
            "message": "QuantData returned 429 — rate limited. Wait 60 seconds and try again.",
            "status_code": 429,
        }
    else:
        return {
            "ok": False,
            "error": "api_error",
            "message": f"QuantData returned HTTP {resp.status_code}: {resp.text[:200]}",
            "status_code": resp.status_code,
        }


# ---------------------------------------------------------------------------
# QuantData Credentials Update  (Sprint v7.1)
# ---------------------------------------------------------------------------

class QuantDataCredentialsRequest(BaseModel):
    auth_token: str
    cookie: str


@router.post("/settings/quantdata_credentials")
def update_quantdata_credentials(body: QuantDataCredentialsRequest):
    """
    Update the QuantData auth_token and cookie in ~/.quantdata-mcp/config.json.
    Called from the Settings page when the user pastes fresh credentials from
    their browser DevTools after logging in to v3.quantdata.us.
    """
    import json as _json
    import pathlib as _pathlib

    if not body.auth_token.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="auth_token must not be empty")
    if not body.cookie.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="cookie must not be empty")

    mcp_config_path = _pathlib.Path.home() / ".quantdata-mcp" / "config.json"

    # Load existing config (preserve tool IDs and other fields)
    if mcp_config_path.exists():
        try:
            cfg = _json.loads(mcp_config_path.read_text())
        except Exception:
            cfg = {}
    else:
        cfg = {}

    # Update only the credentials fields
    cfg["auth_token"] = body.auth_token.strip()
    cfg["cookie"] = body.cookie.strip()

    # Write back
    try:
        mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_config_path.write_text(_json.dumps(cfg, indent=2))
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to write config: {e}")

    return {
        "ok": True,
        "message": "QuantData credentials updated. Run the IV Crush workflow to regenerate candidate data.",
    }


@router.get("/settings/quantdata_credentials_status")
def get_quantdata_credentials_status():
    """
    Returns the current QuantData credentials status: whether they exist,
    a masked preview of the token, and when they were last updated.
    """
    import json as _json
    import pathlib as _pathlib
    import os as _os

    mcp_config_path = _pathlib.Path.home() / ".quantdata-mcp" / "config.json"

    if not mcp_config_path.exists():
        return {"exists": False, "token_preview": None, "cookie_preview": None, "mtime": None}

    try:
        cfg = _json.loads(mcp_config_path.read_text())
        token = cfg.get("auth_token", "")
        cookie = cfg.get("cookie", "")
        mtime = _os.path.getmtime(str(mcp_config_path))
        from datetime import datetime as _dt, timezone as _tz
        mtime_iso = _dt.fromtimestamp(mtime, tz=_tz.utc).isoformat()
        return {
            "exists": True,
            "token_preview": token[:20] + "..." if len(token) > 20 else token,
            "cookie_preview": cookie[:40] + "..." if len(cookie) > 40 else cookie,
            "mtime": mtime_iso,
        }
    except Exception as e:
        return {"exists": False, "error": str(e), "token_preview": None, "cookie_preview": None, "mtime": None}


# QuantData Login-Based Credential Refresh  (Sprint v7.2)
# ---------------------------------------------------------------------------
# Accepts email + password, logs in to QuantData programmatically using
# curl_cffi Chrome impersonation (required to bypass Cloudflare), writes
# fresh auth_token + cookie to ~/.quantdata-mcp/config.json, then verifies
# the connection by fetching SPY IV Rank as live proof.
# ---------------------------------------------------------------------------

class QuantDataLoginRequest(BaseModel):
    email: str
    password: str

@router.post("/settings/quantdata_login_refresh")
def quantdata_login_refresh(body: QuantDataLoginRequest):
    """
    Log in to QuantData with email + password, retrieve a fresh JWT token
    and session cookie, persist them to ~/.quantdata-mcp/config.json, and
    verify the connection by fetching SPY IV Rank.

    Returns:
        ok: bool
        token_preview: first 20 chars of the new token
        iv_rank: float | null  (SPY IV Rank as proof of live connection)
        message: human-readable status
        error: str | null
    """
    import json as _json
    import pathlib as _pathlib
    import subprocess as _subprocess

    if not body.email.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="email must not be empty")
    if not body.password.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="password must not be empty")

    try:
        from curl_cffi import requests as _cffi_requests
    except ImportError:
        return {
            "ok": False,
            "token_preview": None,
            "iv_rank": None,
            "message": "curl_cffi is not installed on the server. Run: pip install curl_cffi",
            "error": "ImportError: curl_cffi",
        }

    QD_BASE = "https://core-lb-prod.quantdata.us"
    LOGIN_URL = f"{QD_BASE}/api/user/authentication/login"
    BROWSER_HEADERS = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://v3.quantdata.us",
        "referer": "https://v3.quantdata.us/",
        "sec-ch-ua": '"Chromium";v="110", "Not A(Brand";v="24", "Google Chrome";v="110"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    }

    # ── Step 1: warm up a browser session (sets Cloudflare cookies) ──────────
    try:
        session = _cffi_requests.Session(impersonate="chrome110")
        session.get("https://v3.quantdata.us/login", timeout=20, headers={
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "user-agent": BROWSER_HEADERS["user-agent"],
        })
    except Exception:
        pass  # warm-up failure is non-fatal

    # ── Step 2: POST login ────────────────────────────────────────────────────
    try:
        resp = session.post(
            LOGIN_URL,
            json={"usernameOrEmail": body.email.strip(), "password": body.password.strip()},
            headers=BROWSER_HEADERS,
            timeout=30,
        )
    except Exception as e:
        return {
            "ok": False,
            "token_preview": None,
            "iv_rank": None,
            "message": f"Network error during login: {e}",
            "error": str(e),
        }

    if resp.status_code == 401:
        return {
            "ok": False,
            "token_preview": None,
            "iv_rank": None,
            "message": "Login failed — incorrect email or password (HTTP 401).",
            "error": "HTTP 401 Unauthorized",
        }
    if resp.status_code == 429:
        return {
            "ok": False,
            "token_preview": None,
            "iv_rank": None,
            "message": "QuantData rate-limited the login attempt. Wait 60 seconds and try again.",
            "error": "HTTP 429 Too Many Requests",
        }
    if not resp.ok:
        return {
            "ok": False,
            "token_preview": None,
            "iv_rank": None,
            "message": f"Login returned HTTP {resp.status_code}: {resp.text[:200]}",
            "error": f"HTTP {resp.status_code}",
        }

    # ── Step 3: extract JWT token ─────────────────────────────────────────────
    try:
        data = resp.json()
    except Exception:
        return {
            "ok": False,
            "token_preview": None,
            "iv_rank": None,
            "message": "Login response was not valid JSON.",
            "error": "JSON parse error",
        }

    jwt_token = None
    # Try common response shapes
    for path in [
        lambda d: d.get("response", {}).get("userSessionDTO", {}).get("token"),
        lambda d: d.get("token"),
        lambda d: d.get("data", {}).get("token"),
        lambda d: d.get("accessToken"),
        lambda d: d.get("access_token"),
    ]:
        try:
            val = path(data)
            if val and isinstance(val, str) and len(val) > 20:
                jwt_token = val
                break
        except Exception:
            continue

    if not jwt_token:
        return {
            "ok": False,
            "token_preview": None,
            "iv_rank": None,
            "message": "Login succeeded but could not extract JWT token from response. Response keys: " + str(list(data.keys()))[:200],
            "error": "Token extraction failed",
        }

    # ── Step 4: build cookie string from response cookies + token cookie ──────
    cookie_parts = []
    for name, value in resp.cookies.items():
        cookie_parts.append(f"{name}={value}")
    # Also add session cookies from the warm-up
    for name, value in session.cookies.items():
        if name not in resp.cookies:
            cookie_parts.append(f"{name}={value}")
    cookie_parts.append(f"token={jwt_token}")
    cookie_str = "; ".join(cookie_parts)

    auth_token = f"Bearer {jwt_token}"

    # ── Step 5: persist to ~/.quantdata-mcp/config.json ──────────────────────
    mcp_config_path = _pathlib.Path.home() / ".quantdata-mcp" / "config.json"
    try:
        if mcp_config_path.exists():
            cfg = _json.loads(mcp_config_path.read_text())
        else:
            cfg = {}
        cfg["auth_token"] = auth_token
        cfg["cookie"] = cookie_str
        mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_config_path.write_text(_json.dumps(cfg, indent=2))
    except Exception as e:
        return {
            "ok": False,
            "token_preview": auth_token[:20] + "...",
            "iv_rank": None,
            "message": f"Login succeeded but failed to save credentials: {e}",
            "error": str(e),
        }

    # ── Step 6: verify by fetching SPY IV Rank ────────────────────────────────
    iv_rank = None
    verify_ok = False
    verify_msg = ""

    try:
        cfg = _json.loads(mcp_config_path.read_text())
        tools = cfg.get("tools", {})
        iv_rank_id = tools.get("iv_rank") or tools.get("iv_rank_tool_id")

        if iv_rank_id:
            verify_url = f"{QD_BASE}/api/options/iv-rank/{iv_rank_id}?ticker=SPY"
            verify_headers = {
                **BROWSER_HEADERS,
                "authorization": auth_token,
                "cookie": cookie_str,
            }
            vresp = session.get(verify_url, headers=verify_headers, timeout=20)
            if vresp.ok:
                vdata = vresp.json()
                # Parse IV rank from sessionDateToIVRankData structure
                try:
                    session_data = vdata.get("response", {}).get("sessionDateToIVRankData", {})
                    if session_data:
                        latest_date = sorted(session_data.keys())[-1]
                        call_data = session_data[latest_date].get("contractTypeToIVData", {}).get("CALL", {})
                        last_iv = call_data.get("lastIV", 0)
                        max_iv = call_data.get("windowMaxIV", 1)
                        min_iv = call_data.get("windowMinIV", 0)
                        if max_iv != min_iv:
                            iv_rank = round((last_iv - min_iv) / (max_iv - min_iv) * 100, 1)
                except Exception:
                    pass
                verify_ok = True
                verify_msg = f"SPY IV Rank: {iv_rank:.1f} (as of {latest_date})" if iv_rank is not None else "IV Rank endpoint returned 200 (value not parsed)"
            else:
                verify_msg = f"Verification call returned HTTP {vresp.status_code}"
        else:
            verify_msg = "Credentials saved. (IV Rank tool ID not configured — run qd_setup.py to enable full verification)"
            verify_ok = True
    except Exception as e:
        verify_msg = f"Credentials saved. Verification failed: {e}"
        verify_ok = True  # credentials were saved; verification is best-effort

    # ── Step 7: trigger background service restart ────────────────────────────
    try:
        _subprocess.Popen(
            ["systemctl", "restart", "fortress-dashboard"],
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass  # non-fatal

    return {
        "ok": verify_ok,
        "token_preview": auth_token[:24] + "...",
        "iv_rank": iv_rank,
        "message": f"Login successful. Credentials saved. {verify_msg}",
        "error": None,
    }
