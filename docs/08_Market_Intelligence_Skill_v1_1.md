# Market Intelligence Skill

**Version:** 1.1 | **Updated:** May 18, 2026

The Market Intelligence Skill is an agentic workflow that synthesises live options order flow data (Gamma Exposure, Dark Pools, Net Drift) with active portfolio constraints from the Fortress Dashboard. It produces actionable, high-probability trading decisions that respect the rules of Strategy v3.7.

**v1.1 changes from v1.0:** Sprint v7.1 UI enhancements documented — sort dropdown, per-card refresh button, and metric tooltips. QuantData API now uses widget-UUID REST endpoints (deprecated `tool/OPTIONS_*` calls removed from `chart.py`). QuantData credential refresh via Settings UI documented.

---

## 1. Core Concepts

Before executing trades, the skill evaluates three primary flow indicators from QuantData to determine the market regime and key structural levels.

### Gamma Exposure (GEX) Walls

GEX measures the net gamma exposure of options dealers at specific strike prices. Because dealers delta-hedge their books, their hedging activity suppresses or amplifies volatility.

- **Call Walls (Positive GEX):** Strikes where dealers are net long gamma. As price approaches these strikes, dealers sell the underlying to hedge, creating **resistance** and suppressing volatility.
- **Put Walls (Negative GEX):** Strikes where dealers are net short gamma. As price drops toward these strikes, dealers sell the underlying to hedge, creating **support** (but amplifying volatility if broken).
- **Flip Zone (Zero Gamma):** The price level where net gamma transitions from positive to negative.
  - **Above the Flip Zone:** Positive gamma regime. Market is stable, mean-reverting, and dips are bought.
  - **Below the Flip Zone:** Negative gamma regime. Market is volatile, trend-following, and selling accelerates.

### Dark Pool Floors

Dark pools represent off-exchange block trades by institutions. Large notional prints ($1B+) at specific price levels indicate significant institutional accumulation or distribution.

- These levels act as magnetic **floors (support)** or **ceilings (resistance)**.
- When price approaches a heavy dark pool level, it often stalls or reverses as institutions defend their cost basis.

### Net Drift

Net Drift aggregates real-time options order flow (calls vs. puts) into a cumulative dollar value over the trading session.

- **Positive Net Drift:** Bullish flow (calls being bought at the ask, puts being sold at the bid).
- **Negative Net Drift:** Bearish flow (puts being bought at the ask, calls being sold at the bid).
- **Divergence:** If the underlying price is rising but Net Drift is sharply negative, the rally is unsupported by options flow and likely to fail.

---

## 2. Dashboard UI (Sprint v7.1)

The Market Intelligence page at `/market-intel` was significantly enhanced in Sprint v7.1.

### Sort Dropdown

A page-level sort control allows ordering all ticker cards by:

| Option | Description |
|---|---|
| **Score ↓** | Most bullish first (highest regime score at top) |
| **Score ↑** | Most bearish first (lowest regime score at top) |
| **Bias** | Grouped: bullish → neutral → bearish |
| **Alphabetical** | A–Z by ticker |

### Per-Card Refresh

Each ticker card has a `↺` button in the header row. Clicking it re-fetches only that ticker's live data without reloading the full page. The button spins while the request is in flight.

### Metric Tooltips

Every metric box on each card has a `?` badge. Hovering reveals a plain-English explanation:

| Metric | Tooltip explains |
|---|---|
| GEX Call Wall | Resistance level where dealer hedging suppresses upside |
| GEX Put Wall | Support level where dealer hedging amplifies downside if broken |
| DP Floor | Dark pool institutional accumulation level — acts as magnetic support |
| DP Ceiling | Dark pool institutional distribution level — acts as resistance |
| Net Drift | Cumulative options order flow bias for the session |
| GEX Flip Zone | Price level where gamma transitions from positive to negative |
| Regime Score | Composite score −4 (strongly bearish) to +4 (strongly bullish) |

---

## 3. Using the Skill via MCP

The skill is exposed to Claude Desktop (or any MCP-compatible agent) via the `get_market_intelligence` tool in the `fortress-mcp` server.

### Triggering the Skill

You can trigger the full analysis with a simple natural language prompt:
> *"What is the market doing today? Are there any actionable trade setups on SPY?"*

Claude will call `get_market_intelligence(ticker="SPY")`, which orchestrates the entire workflow in a single backend request.

### The Agentic Workflow

When Claude receives the data from the endpoint, it follows a strict workflow defined in its `SKILL.md` instructions:

1. **Evaluate the Regime:** It checks the overall score (e.g., `mildly_bullish`), the gamma regime (positive/negative), and the proximity to the flip zone.
2. **Identify Key Levels:** It maps the top GEX call walls (resistance) and put walls (support), alongside the heaviest Dark Pool floors.
3. **Check Portfolio Constraints:** Before recommending any trades, it reviews the `portfolio_context` and `risk_checks` blocks. If the dashboard flags a concentration warning (e.g., MSFT > 50%), the agent will strictly advise against adding correlated exposure.
4. **Present Trade Setups:** It filters the generated setups (Gamma Pin, Floor Bounce, Flip Zone Breakdown) based on the current regime and portfolio constraints, presenting only those that are safe to execute.

---

## 4. The Backend Engine (`/api/market-intelligence`)

The MCP tool is powered by a dedicated endpoint on the Fortress Dashboard. This endpoint performs heavy lifting so the AI agent doesn't have to make multiple API calls.

### Data Sources

- **Live QuantData API:** Fetches GEX by strike, Dark Pool levels, and Net Drift directly from QuantData using widget-UUID REST endpoints. Credentials stored in `/home/ubuntu/.quantdata-mcp/config.json` and refreshable via **Settings → QuantData Credentials**.
- **Fortress Dashboard:** Fetches current positions, macro regime, pacing limits, and concentration metrics from the local state.

### QuantData API Endpoints Used

| Data | Endpoint Pattern |
|---|---|
| GEX by strike (call/put walls) | `GET /api/options/exposure/strike/{widget_uuid}?ticker={ticker}` |
| Dark Pool levels | `GET /api/equities/dark-pool/levels/{widget_uuid}?ticker={ticker}` |
| Net Drift | `GET /api/options/net-drift/{widget_uuid}?ticker={ticker}` |
| Order flow | `GET /api/options/order-flow/consolidated?ticker={ticker}` |

> **Note:** The deprecated `tool/OPTIONS_GEX_WALLS_TABLE`, `tool/OPTIONS_DARK_POOL_LEVELS_TABLE`, and `tool/OPTIONS_ORDER_FLOW_CONSOLIDATED_TABLE` endpoints were removed in Sprint v7.1. Do not use them — they return 400 errors and caused account revocation.

### Regime Synthesis Scoring

The endpoint calculates an `overall` regime score from -4 (strongly bearish) to +4 (strongly bullish) based on:

| Signal | Bullish | Bearish |
|---|---|---|
| Gamma Regime | +2 (above flip zone) | -2 (below flip zone) |
| Dark Pool Proximity | +1 (bouncing off heavy floor) | -1 (broken below floor) |
| Net Drift Bias | +1 (cumulative flow bullish) | -1 (cumulative flow bearish) |
| Macro Regime | +1 (dashboard macro bullish) | -1 (dashboard macro bearish) |
| Divergence Penalty | — | -1 (positive gamma but bearish drift) |

### Trade Setup Generation

The endpoint automatically generates specific trade setups when conditions align:

| Setup Name | Conditions Required | Recommended Execution |
|---|---|---|
| **Gamma Pin** | Positive gamma regime; price pinned between tight call and put walls. | Sell Iron Condor with short strikes at the walls. |
| **Floor Bounce** | Price drops near a massive Dark Pool floor (> $500M notional). | Sell Put Credit Spread just below the floor. |
| **Flip Zone Breakdown** | Negative gamma regime; price breaks below the flip zone. | Buy Bear Put Spread targeting the next Dark Pool floor. |

---

## 5. Credential Management

The Market Intelligence endpoint requires valid QuantData credentials. When credentials expire, all QuantData-dependent data (GEX walls, DP floors, Net Drift, IV Rank) will return empty or null values.

**To refresh credentials:**

1. Open the Fortress Dashboard → **Settings** → scroll to **QuantData Credentials**.
2. Follow the on-screen instructions to extract `auth_token` and `cookie` from a fresh QuantData browser session.
3. Paste both values and click **Save Credentials**.
4. Re-run the IV Crush workflow if needed: `python3 quant/workflow_05_iv_crush_report.py`.

See `operations/04_Incident_Recovery_Playbook.md` §5 for the full step-by-step procedure.

---

## 6. Execution Checklist

To trade successfully using this skill, incorporate it into your daily routine:

1. **Pre-Market (09:00 ET):** Check the Dashboard for Macro Regime, Concentration warnings, and Pacing limits.
2. **Open (09:30 - 10:00 ET):** Let overnight orders clear. Do not trade the first 30 minutes. Monitor Net Drift to establish the opening flow bias.
3. **Intraday (10:00 - 15:30 ET):** Ask Claude *"What is the market doing?"* to run the Market Intelligence skill. Execute the suggested setups only when Price, GEX, and Net Drift align.
4. **Close (15:30 - 16:00 ET):** Review active positions against the Fortress `stop_loss_scan.py` output. Roll any positions where DTE ≤ 7 or Delta ≥ 0.80.

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 1.1 | 2026-05-18 | Sprint v7.1 UI enhancements: sort dropdown, per-card refresh, metric tooltips. QuantData widget-UUID endpoint table. Deprecated tool IDs warning. Credential refresh via Settings UI. |
| 1.0 | 2026-05-13 | Initial release. |

*For detailed technical implementation, see `app/routes/market_intelligence.py` and the `fortress-mcp` repository.*
