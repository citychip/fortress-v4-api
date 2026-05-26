# Market Intelligence Skill

**Version:** 1.0 | **Updated:** May 13, 2026

The Market Intelligence Skill is an agentic workflow that synthesises live options order flow data (Gamma Exposure, Dark Pools, Net Drift) with active portfolio constraints from the Fortress Dashboard. It produces actionable, high-probability trading decisions that respect the rules of Strategy v3.6.

This document explains how the skill works, how to use it via the MCP server, and how the underlying dashboard endpoint (`/api/market-intelligence`) generates its recommendations.

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

## 2. Using the Skill via MCP

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

## 3. The Backend Engine (`/api/market-intelligence`)

The MCP tool is powered by a dedicated endpoint on the Fortress Dashboard. This endpoint performs heavy lifting so the AI agent doesn't have to make multiple API calls.

### Data Sources
- **Live QuantData API:** Fetches GEX by strike, Dark Pool levels, and Net Drift directly from QuantData using the credentials stored in the VPS environment (`QUANTDATA_AUTH_TOKEN`, `QUANTDATA_USER_ID`).
- **Fortress Dashboard:** Fetches current positions, macro regime, pacing limits, and concentration metrics from the local state.

### Regime Synthesis Scoring
The endpoint calculates an `overall` regime score from -4 (strongly bearish) to +4 (strongly bullish) based on:
- **Gamma Regime:** +2 if positive (above flip zone), -2 if negative.
- **Dark Pool Proximity:** +1 if price is bouncing off a heavy floor, -1 if price has broken below a floor.
- **Net Drift Bias:** +1 if cumulative flow is bullish, -1 if bearish.
- **Macro Regime:** +1 if the dashboard's daily macro regime is bullish, -1 if bearish.
- **Divergence Penalty:** -1 if price is in positive gamma but net drift is bearish.

### Trade Setup Generation
The endpoint automatically generates specific trade setups when conditions align:

| Setup Name | Conditions Required | Recommended Execution |
|---|---|---|
| **Gamma Pin** | Positive gamma regime; price pinned between tight call and put walls. | Sell Iron Condor with short strikes at the walls. |
| **Floor Bounce** | Price drops near a massive Dark Pool floor (> $500M notional). | Sell Put Credit Spread just below the floor. |
| **Flip Zone Breakdown** | Negative gamma regime; price breaks below the flip zone. | Buy Bear Put Spread targeting the next Dark Pool floor. |

---

## 4. Execution Checklist

To trade successfully using this skill, incorporate it into your daily routine:

1. **Pre-Market (09:00 ET):** Check the Dashboard for Macro Regime, Concentration warnings, and Pacing limits.
2. **Open (09:30 - 10:00 ET):** Let overnight orders clear. Do not trade the first 30 minutes. Monitor Net Drift to establish the opening flow bias.
3. **Intraday (10:00 - 15:30 ET):** Ask Claude *"What is the market doing?"* to run the Market Intelligence skill. Execute the suggested setups only when Price, GEX, and Net Drift align.
4. **Close (15:30 - 16:00 ET):** Review active positions against the Fortress `stop_loss_scan.py` output. Roll any positions where DTE $\le 7$ or Delta $\ge 0.80$.

---

*For detailed technical implementation, see `app/routes/market_intelligence.py` and the `fortress-mcp` repository.*
