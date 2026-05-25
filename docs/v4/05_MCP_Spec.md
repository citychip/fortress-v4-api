# Fortress V4 — MCP Specification
## Claude Tool Catalogue: All 61 Tools

**Version:** 4.0.0  
**Status:** Authoritative — Phase 2 deliverable  
**MCP Server Version:** `4.0.0` (returned by `get_capability`)  
**Write Guard:** Tier 2 tools require `FORTRESS_MCP_ALLOW_WRITES=1` environment variable

---

## Overview

The Fortress MCP server exposes **61 tools** to Claude:

| Tier | Count | Description |
|---|---|---|
| **Tier 1** | 47 | Read-only — safe at all times |
| **Tier 2** | 10 | Write operations — require `FORTRESS_MCP_ALLOW_WRITES=1` |
| **Tier 1.5** | 4 | New V4 analytics — read-only, derived calculations |
| **Total** | **61** | |

All tools communicate with the Fortress API over `http://localhost:8080/api/*` using bearer token authentication. The MCP server reads `FORTRESS_API_TOKEN` from the environment and injects it into every request.

---

## Environment Variables

```env
FORTRESS_API_URL=http://localhost:8080
FORTRESS_API_TOKEN=<bearer token>
FORTRESS_MCP_ALLOW_WRITES=0          # Set to 1 to enable Tier 2 tools
FORTRESS_MCP_VERSION=4.0.0
```

---

## Tier 1 — Read-Only Tools (47)

### Portfolio & Positions

#### `get_positions`
Returns all open positions with full leg detail.

**Request:** `GET /api/positions`  
**Response:**
```json
{
  "positions": [
    {
      "id": "uuid",
      "ticker": "AAPL",
      "strategy": "PMCC",
      "legs": [
        {
          "type": "call",
          "expiry": "2026-06-20",
          "strike": 175.0,
          "quantity": 1,
          "delta": 0.72,
          "theta": -0.08,
          "vega": 0.22,
          "current_price": 8.40,
          "cost_basis": 7.20
        }
      ],
      "net_delta": 0.35,
      "net_theta": -0.05,
      "unrealised_pnl": 120.0,
      "opened_at": "2026-05-01T09:35:00Z"
    }
  ],
  "total_positions": 4,
  "net_portfolio_delta": 1.42
}
```

---

#### `get_position_limits`
Returns current position counts vs configured limits.

**Request:** `GET /api/positions/limits`  
**Response:**
```json
{
  "pcs_count": 3,
  "pcs_max": 5,
  "put_notional": 18500.0,
  "put_notional_max": 25000.0,
  "trades_this_week": 1,
  "trades_per_week_max": 2
}
```

---

#### `get_pnl`
Returns P&L summary for specified period.

**Parameters:** `period` (string): `day` | `week` | `month` | `ytd` | `all`  
**Request:** `GET /api/pnl?period={period}`  
**Response:**
```json
{
  "period": "month",
  "realised_pnl": 2340.50,
  "unrealised_pnl": 890.00,
  "total_pnl": 3230.50,
  "win_rate": 0.72,
  "avg_win": 340.0,
  "avg_loss": -180.0,
  "trades_count": 18
}
```

---

#### `get_forward_pnl`
Projects P&L scenarios at different price levels for active positions.

**Parameters:** `ticker` (string), `price_range_pct` (float, default 0.10)  
**Request:** `GET /api/positions/forward-pnl?ticker={ticker}&range={range}`

---

#### `get_spy_hedge_coverage`
Returns current SPY hedge coverage ratio vs portfolio delta.

**Request:** `GET /api/positions/hedge-coverage`  
**Response:**
```json
{
  "portfolio_delta_dollars": 12400.0,
  "hedge_delta_dollars": -4200.0,
  "coverage_ratio": 0.339,
  "coverage_target": 0.25,
  "status": "adequate"
}
```

---

#### `get_hydrated_assets`
Returns all positions enriched with current market data (IV, greeks, bid/ask).

**Request:** `GET /api/positions/hydrated`

---

### Market Intelligence

#### `get_market_intelligence`
Returns comprehensive market snapshot including SPY, VIX, and macro signals.

**Request:** `GET /api/market/intelligence`  
**Response:**
```json
{
  "spy_price": 542.30,
  "spy_change_pct": 0.42,
  "vix": 18.4,
  "vix_regime": "normal",
  "market_session": "regular",
  "session_start": "2026-05-23T13:30:00Z",
  "session_end": "2026-05-23T20:00:00Z"
}
```

---

#### `get_vol_analytics`
Returns volatility analytics for a given ticker.

**Parameters:** `ticker` (string)  
**Request:** `GET /api/market/vol?ticker={ticker}`  
**Response:**
```json
{
  "ticker": "AAPL",
  "iv_rank": 42.0,
  "iv_percentile": 38.0,
  "hv_30": 0.22,
  "iv_30": 0.28,
  "iv_skew": -0.04,
  "term_structure": {
    "7d": 0.26,
    "30d": 0.28,
    "60d": 0.30,
    "90d": 0.32
  }
}
```

---

#### `get_order_flow_chart`
Returns aggregated options order flow data.

**Parameters:** `ticker` (string), `period` (string): `1d` | `5d` | `1w`  
**Request:** `GET /api/market/order-flow?ticker={ticker}&period={period}`

---

#### `get_dp_floors_and_gex`
Returns dark pool price levels and gamma exposure data.

**Parameters:** `ticker` (string)  
**Request:** `GET /api/market/dp-gex?ticker={ticker}`

---

### Alerts

#### `get_alerts`
Returns all active alerts.

**Request:** `GET /api/alerts`  
**Response:**
```json
{
  "alerts": [
    {
      "id": "uuid",
      "ticker": "AAPL",
      "type": "price_target",
      "threshold": 170.0,
      "condition": "below",
      "message": "AAPL approaching put spread lower bound",
      "created_at": "2026-05-22T10:00:00Z",
      "triggered": false
    }
  ]
}
```

---

#### `evaluate_stop_loss`
Evaluates whether a stop-loss condition has been met for a position.

**Parameters:** `position_id` (string)  
**Request:** `GET /api/positions/{id}/stop-loss-eval`

---

#### `evaluate_roll`
Evaluates roll candidates for a position nearing expiry or under pressure.

**Parameters:** `position_id` (string)  
**Request:** `GET /api/positions/{id}/roll-eval`

---

#### `evaluate_post_earnings`
Evaluates recommended action after earnings for a position.

**Parameters:** `position_id` (string)  
**Request:** `GET /api/positions/{id}/post-earnings`

---

### Trade & Pre-Trade

#### `get_pending_orders`
Returns all pending orders awaiting approval.

**Request:** `GET /api/orders/pending`

---

#### `pretrade_check`
Runs the full pre-trade gate validation for a proposed order.

**Parameters:** `ticker`, `strategy`, `legs` (array), `quantity`  
**Request:** `POST /api/trade/pretrade` (read-only validation — does not place order)  
**Response:**
```json
{
  "passed": false,
  "checks": [
    { "rule": "pcs_cap", "passed": true, "detail": "3/5 PCS positions active" },
    { "rule": "put_notional", "passed": true, "detail": "$18,500 / $25,000 utilised" },
    { "rule": "earnings_blackout", "passed": false, "detail": "AAPL earnings in 8 days (PCS blackout: 10 days)" },
    { "rule": "leap_blackout", "passed": true, "detail": "No LEAP entry" },
    { "rule": "ivr_gate", "passed": true, "detail": "IVR 42 ≥ 25" },
    { "rule": "vix_regime", "passed": true, "detail": "VIX 18.4 < 35" },
    { "rule": "weekly_pacing", "passed": true, "detail": "1 trade this week / max 2" }
  ],
  "blocking_failures": ["earnings_blackout"]
}
```

---

#### `get_pretrade_all`
Runs pre-trade checks against all current open positions (portfolio-level scan).

**Request:** `GET /api/trade/pretrade-all`

---

#### `preview_order`
Generates an IBKR order preview without submitting.

**Parameters:** `ticker`, `action` (BUY/SELL), `legs`, `quantity`  
**Request:** `POST /api/ibkr/preview`

---

#### `get_ibkr_preview`
Returns the last generated IBKR order preview.

**Request:** `GET /api/ibkr/preview`

---

#### `get_ibkr_status`
Returns current IBKR CP Gateway connection status.

**Request:** `GET /api/ibkr/status`  
**Response:**
```json
{
  "connected": true,
  "session_age_minutes": 42,
  "authenticated": true,
  "competing_sessions": false
}
```

---

#### `validate_jade_lizard`
Validates that a proposed Jade Lizard structure is properly set up (no upside risk).

**Parameters:** `short_call_strike`, `short_put_strike`, `long_put_strike`, `net_credit`  
**Request:** `POST /api/trade/validate-jade-lizard` (validation only, no write)

---

### Analytics

#### `options_greeks`
Returns current greeks for a specific options contract.

**Parameters:** `ticker`, `expiry`, `strike`, `option_type` (call/put)  
**Request:** `GET /api/market/greeks?ticker={ticker}&expiry={expiry}&strike={strike}&type={type}`

---

#### `get_earnings_history`
Returns historical earnings reaction data for a ticker.

**Parameters:** `ticker` (string), `lookback` (int, number of events, default 8)  
**Request:** `GET /api/earnings/history?ticker={ticker}&lookback={lookback}`

---

#### `get_calendar`
Returns the earnings and events calendar.

**Parameters:** `days_ahead` (int, default 14)  
**Request:** `GET /api/calendar?days={days}`

---

#### `get_candidates`
Returns trade candidates from the configured universe that meet entry criteria.

**Request:** `GET /api/candidates`  
**Response:**
```json
{
  "candidates": [
    {
      "ticker": "NVDA",
      "strategy_fit": ["PCS", "JL"],
      "ivr": 58.0,
      "iv_30": 0.62,
      "next_earnings_days": 45,
      "score": 0.84
    }
  ]
}
```

---

#### `get_roll_all`
Returns roll recommendations for all positions.

**Request:** `GET /api/positions/roll-all`

---

#### `get_stop_loss_all`
Returns stop-loss status for all positions.

**Request:** `GET /api/positions/stop-loss-all`

---

#### `get_chart_data`
Returns OHLCV chart data for a ticker.

**Parameters:** `ticker`, `period` (1d/5d/1m/3m/1y), `interval` (1m/5m/15m/1h/1d)  
**Request:** `GET /api/market/chart?ticker={ticker}&period={period}&interval={interval}`

---

### Configuration & Universe

#### `get_settings`
Returns all configuration settings.

**Request:** `GET /api/config`

---

#### `get_settings_narrative`
Returns configuration settings as a human-readable narrative summary.

**Request:** `GET /api/config/narrative`

---

#### `get_universe`
Returns the configured trading universe (tickers approved for trading).

**Request:** `GET /api/universe`

---

#### `get_capability`
Returns the MCP server version and capability manifest.

**Request:** `GET /api/capability`  
**Response:**
```json
{
  "version": "4.0.0",
  "tier1_tools": 47,
  "tier1_5_tools": 4,
  "tier2_tools": 10,
  "writes_enabled": false,
  "strategy_version": "3.7"
}
```

---

### Journal

#### `get_journal`
Returns journal entries.

**Parameters:** `limit` (int, default 20), `strategy` (optional filter), `closed_only` (bool)  
**Request:** `GET /api/journal?limit={limit}&strategy={strategy}`

---

#### `get_journal_suggestion`
Returns an AI-generated journal suggestion for a completed trade.

**Parameters:** `position_id` (string)  
**Request:** `GET /api/journal/suggest?position_id={id}`

---

### Reporting & Scheduler

#### `get_trade_report`
Returns a trade report for a specified period.

**Parameters:** `period` (day/week/month/ytd)  
**Request:** `GET /api/reports/trades?period={period}`

---

#### `get_briefing`
Returns the daily morning briefing. **Use this first for any portfolio question.**

**Request:** `GET /api/briefing`  
**Response:**
```json
{
  "generated_at": "2026-05-23T07:00:00Z",
  "portfolio_delta": 1.42,
  "delta_status": "within_target",
  "open_positions": 4,
  "unrealised_pnl": 890.0,
  "today_earnings": ["NVDA"],
  "alerts_active": 1,
  "vix": 18.4,
  "vix_regime": "normal",
  "recommended_actions": [
    "Review NVDA position — earnings today"
  ]
}
```

---

#### `list_scripts`
Returns the list of available APScheduler scripts.

**Request:** `GET /api/scheduler/scripts`

---

#### `get_time_of_day`
Returns current market session state.

**Request:** `GET /api/market/session`  
**Response:**
```json
{
  "session": "regular",
  "time_utc": "2026-05-23T15:42:00Z",
  "minutes_to_close": 198,
  "premarket": false,
  "afterhours": false
}
```

---

### QuantData Integration (Live Data)

#### `qd_get_dark_pool_levels`
Returns dark pool price levels from QuantData.

**Parameters:** `ticker` (string)

---

#### `qd_get_iv_rank`
Returns IVR and IV percentile from QuantData.

**Parameters:** `ticker` (string)

---

#### `qd_get_max_pain`
Returns max pain strike for the current or specified expiry.

**Parameters:** `ticker`, `expiry` (optional)

---

#### `qd_get_net_drift`
Returns cumulative options premium drift (call vs put bias).

**Parameters:** `ticker`, `period`

---

#### `qd_get_oi_change`
Returns open interest change by strike.

**Parameters:** `ticker`, `expiry`

---

#### `qd_get_order_flow`
Returns live or historical order flow data.

**Parameters:** `ticker`, `period`

---

#### `get_quantdata_reports`
Returns a composite QuantData report for all universe tickers.

**Request:** `GET /api/quantdata/report`

---

*That completes the 47 Tier 1 tools.*

---

## Tier 1.5 — New V4 Analytics Tools (4)

> These tools are new in Fortress V4. They call the four new Tier 1.5 API endpoints added to support Portfolio Strategy v3.7 requirements.

### `get_portfolio_beta`
Returns the portfolio's beta-weighted delta versus SPY.

**Endpoint:** `GET /api/portfolio/beta`  
**Response:**
```json
{
  "portfolio_beta_vs_spy": 0.62,
  "beta_weighted_delta": 0.39,
  "delta_target": 0.35,
  "delta_variance": "+0.04",
  "positions_by_beta": [
    { "ticker": "AAPL", "beta": 1.18, "position_delta": 0.35, "beta_adj_delta": 0.41 },
    { "ticker": "NVDA", "beta": 1.68, "position_delta": 0.28, "beta_adj_delta": 0.47 }
  ]
}
```

**Usage:** After `get_briefing`, call this to assess whether portfolio delta is within the 0.35 net-long target (§5 of strategy).

---

### `get_sector_exposure`
Returns portfolio exposure broken down by GICS sector.

**Endpoint:** `GET /api/portfolio/sector-exposure`  
**Response:**
```json
{
  "sectors": [
    { "sector": "Information Technology", "notional": 24500.0, "pct_of_portfolio": 0.54 },
    { "sector": "Consumer Discretionary", "notional": 8200.0, "pct_of_portfolio": 0.18 },
    { "sector": "Financials", "notional": 6100.0, "pct_of_portfolio": 0.13 }
  ],
  "concentration_warning": true,
  "max_sector": "Information Technology",
  "max_sector_pct": 0.54
}
```

**Usage:** Identify sector concentration before entering a new position. Flag if any sector > 40% of portfolio.

---

### `get_capital_efficiency`
Returns the capital efficiency ratio: credit received vs capital at risk per strategy type.

**Endpoint:** `GET /api/portfolio/capital-efficiency`  
**Response:**
```json
{
  "overall_efficiency": 0.148,
  "by_strategy": [
    { "strategy": "PMCC", "capital_at_risk": 8200.0, "credit_received": 1240.0, "efficiency": 0.151 },
    { "strategy": "PCS", "capital_at_risk": 6000.0, "credit_received": 880.0, "efficiency": 0.147 },
    { "strategy": "JL", "capital_at_risk": 4500.0, "credit_received": 680.0, "efficiency": 0.151 }
  ],
  "target_efficiency": 0.12,
  "status": "above_target"
}
```

**Usage:** Monthly performance review. Target is > 12% capital efficiency; below 8% triggers strategy review.

---

### `get_earnings_volatility`
Returns pre- and post-earnings implied volatility data for a ticker.

**Endpoint:** `GET /api/market/earnings-volatility?ticker={ticker}`  
**Response:**
```json
{
  "ticker": "AAPL",
  "next_earnings": "2026-07-31",
  "days_to_earnings": 69,
  "iv_current": 0.28,
  "iv_pre_earnings_historical_avg": 0.38,
  "iv_post_earnings_historical_avg": 0.22,
  "expected_iv_crush_pct": 0.42,
  "implied_move_pct": 0.048,
  "historical_moves": [0.032, 0.071, 0.028, 0.052, 0.041, 0.038, 0.044, 0.029]
}
```

**Usage:** Before entering any position on an earnings-adjacent ticker. Used by the IV crush workflow (APScheduler script 2).

---

## Tier 2 — Write Tools (10)

> **These tools require `FORTRESS_MCP_ALLOW_WRITES=1`**. When the environment variable is absent or `0`, all Tier 2 tools return:
> ```json
> { "error": "writes_disabled", "message": "Set FORTRESS_MCP_ALLOW_WRITES=1 to enable write operations" }
> ```

### `add_alert`
Creates a new alert.

**Endpoint:** `POST /api/alerts`  
**Body:**
```json
{
  "ticker": "AAPL",
  "type": "price_target",
  "threshold": 168.0,
  "condition": "below",
  "message": "AAPL approaching put spread lower bound"
}
```

---

### `update_alert`
Updates an existing alert.

**Endpoint:** `PATCH /api/alerts/{id}`  
**Body:** partial alert fields

---

### `delete_alert`
Deletes an alert.

**Endpoint:** `DELETE /api/alerts/{id}`

---

### `add_journal_entry`
Creates a new journal entry.

**Endpoint:** `POST /api/journal`  
**Body:**
```json
{
  "ticker": "AAPL",
  "strategy": "PMCC",
  "action": "OPEN",
  "notes": "Entered PMCC on AAPL, IVR 42, 45 DTE",
  "position_id": "uuid",
  "close_id": null
}
```

---

### `add_universe_ticker`
Adds a ticker to the trading universe.

**Endpoint:** `POST /api/universe`  
**Body:** `{ "ticker": "MSFT" }`

---

### `add_excluded_ticker`
Adds a ticker to the exclusion list (blacklist).

**Endpoint:** `POST /api/universe/excluded`  
**Body:** `{ "ticker": "GME", "reason": "meme stock" }`

---

### `approve_order`
Approves a pending order for IBKR submission.

**Endpoint:** `POST /api/orders/{id}/approve`  
**⚠️ Note:** This triggers IBKR order submission. Only call after full pre-trade validation and user confirmation.

---

### `decline_order`
Declines a pending order.

**Endpoint:** `POST /api/orders/{id}/decline`  
**Body:** `{ "reason": "string" }`

---

### `update_calendar`
Updates an event or earnings date in the calendar.

**Endpoint:** `PATCH /api/calendar/{id}`  
**Body:** partial calendar fields

---

### `update_settings_section`
Updates a section of the configuration.

**Endpoint:** `PATCH /api/config`  
**Body:**
```json
{
  "section": "strategy_params",
  "values": {
    "vix_max": 32,
    "ivr_min": 25
  }
}
```
**⚠️ Note:** Config is validated before write. Invalid values are rejected with `422`. Config is auto-backed up before each write (K-02 fix).

---

### `run_script`
Triggers an APScheduler script to run immediately.

**Endpoint:** `POST /api/scheduler/run`  
**Body:** `{ "script_name": "premarket_scanner" }`  
**Available scripts:** `premarket_scanner`, `iv_crush`, `position_monitor`, `dark_pool_alert`, `eod_review`, `whale_flow`, `max_pain`, `gex_oi`

---

### `trigger_ibkr_sync`
Triggers an immediate IBKR position sync.

**Endpoint:** `POST /api/ibkr/sync`

---

## Daily Workflow Prompts (19 Prompts — V4)

### Morning Session

**1. Full Morning Briefing**
```
Use get_briefing first, then get_portfolio_beta, then get_alerts.
Summarise: portfolio health, delta vs target (0.35), active alerts, today's earnings.
Flag any required actions before market open.
```

**2. Pre-Market Scanner**
```
Run the premarket_scanner script via run_script.
Review output: which candidates score above 0.75? Any universe additions to consider?
```

**3. IV Environment Check**
```
Use get_market_intelligence for VIX regime.
If VIX > 25: flag — no new PCS entries. If VIX > 35: flag — all new entries blocked.
Use get_vol_analytics for SPY and any positions under pressure.
```

**4. Sector Exposure Review**
```
Use get_sector_exposure.
Flag if any sector > 40% of portfolio.
Suggest offsetting positions if concentration excessive.
```

### Position Management

**5. Portfolio Delta Check**
```
Use get_portfolio_beta.
Current target: net delta 0.35 long (§5 of strategy v3.7).
If delta > 0.55: suggest hedge additions. If delta < 0.20: suggest trimming hedges.
```

**6. Position Health Scan**
```
Use get_roll_all and get_stop_loss_all.
List positions requiring attention: approaching stop-loss levels or roll criteria.
Prioritise by urgency (days to expiry, P&L drawdown).
```

**7. Stop-Loss Evaluation — Specific Position**
```
Use evaluate_stop_loss for position {position_id}.
Assess current P&L vs 4-level stop-loss thresholds (§6 of strategy v3.7).
Recommend: hold / adjust / close.
```

**8. Roll Evaluation — Specific Position**
```
Use evaluate_roll for position {position_id}.
Assess: DTE remaining, credit received vs current value, roll-out viability.
Recommend: roll / hold / close.
```

**9. SPY Hedge Coverage Check**
```
Use get_spy_hedge_coverage.
Target: hedge covers ≥ 25% of portfolio delta.
If coverage < 20%: recommend adding hedge. If > 50%: check if over-hedged.
```

### Trade Evaluation

**10. Pre-Trade Validation**
```
Use pretrade_check for proposed trade: {ticker} {strategy} {legs}.
Review all 12 gate checks. If any blocking failure: do not proceed.
Summarise: passed checks, failed checks, blocking issues.
```

**11. Position Limit Check Before Entry**
```
Use get_position_limits.
Confirm: PCS count < 5, put notional < €25K, trades this week < 2.
If any limit at capacity: block new entry, flag to user.
```

**12. Earnings Volatility Pre-Trade**
```
Use get_earnings_volatility for {ticker}.
If earnings < 10 days: PCS blackout. If earnings < 14 days: LEAP blackout.
Check historical implied move vs proposed spread width.
```

**13. Capital Efficiency Check**
```
Use get_capital_efficiency.
Is overall efficiency above 12%? Does proposed trade improve or dilute efficiency?
```

**14. Jade Lizard Validation**
```
Use validate_jade_lizard for proposed structure.
Confirm: total credit > width of put spread (no upside risk).
```

### Evening & Weekly Review

**15. End-of-Day Review**
```
Use get_pnl for period=day.
Run eod_review script via run_script.
Summarise: today's P&L, any positions that triggered alerts, upcoming earnings next 5 days.
```

**16. Weekly Performance Review**
```
Use get_pnl for period=week.
Use get_trade_report for period=week.
Review: win rate, avg win/loss, capital efficiency this week.
```

**17. IV Crush Check (Post-Earnings)**
```
Use evaluate_post_earnings for position {position_id}.
Compare IV crush actual vs expected from earnings_volatility.
Recommend: harvest theta / close / hold.
```

**18. Journal Closed-Loop Review**
```
Use get_journal for closed_only=true, limit=10.
For each closed trade without a journal entry: use get_journal_suggestion for position_id.
Prompt user to review and save suggested entries.
```

**19. Monthly Universe Review**
```
Use get_candidates with default parameters.
Use get_universe to see current universe.
Are any candidates consistently scoring > 0.80? Recommend universe additions.
Any universe tickers consistently scoring < 0.40? Recommend review.
```

---

## MCP Server Error Codes

| Code | Meaning |
|---|---|
| `writes_disabled` | Tier 2 tool called without `FORTRESS_MCP_ALLOW_WRITES=1` |
| `ibkr_disconnected` | IBKR CP Gateway not reachable; trades and syncs unavailable |
| `strategy_override` | Action blocked by strategy v3.7 rule; detail field explains which rule |
| `auth_failed` | Bearer token rejected by API |
| `rate_limited` | QuantData API rate limit hit; retry after 30s |
| `market_closed` | Action requires open market session |

---

*Fortress V4 MCP Spec — 61 tools total. Tier 1.5 tools are the primary V4 addition. Strategy v3.7 is the governing document for all thresholds.*
