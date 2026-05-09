## AI Summary

AI summary unavailable: The api_key client option must be set either by passing api_key to the client or by setting the OPENAI_API_KEY environment variable

---

# QuantData Daily Report — 2026-05-05
*Generated: 2026-05-05 16:47 ET | Portfolio Strategy v3.2*

---

## 1. Macro Regime — SPX

**Current Price:** $7,229.32  |  **GEX Flip Zone:** $6,610

### GEX Walls (Gamma Exposure)

| Side | Strike | Net GEX ($M) |
|------|--------|--------------|
| Call Wall | $7,280 | +1623.5 |
| Call Wall | $7,260 | +1438.0 |
| Call Wall | $7,250 | +1388.0 |
| Call Wall | $7,255 | +1302.9 |
| Call Wall | $7,275 | +1267.9 |
| Put Wall  | $7,415 | -0.0 |
| Put Wall  | $3,800 | -0.0 |
| Put Wall  | $9,200 | -0.0 |
| Put Wall  | $5,675 | -0.0 |
| Put Wall  | $6,480 | -0.0 |

### Open Interest Walls

| Side | Strike | OI Contracts |
|------|--------|--------------|
| Call OI | $7,340 | 30,715 |
| Call OI | $7,280 | 19,205 |
| Call OI | $7,200 | 14,136 |
| Put OI  | $5,300 | 47,359 |
| Put OI  | $5,200 | 45,971 |
| Put OI  | $5,750 | 21,551 |

### Net Drift (Cumulative Premium Flow)

**Direction:** 🔴 BEARISH
- Call Premium: $-764.1M
- Put Premium: $3353.2M
- Net: $-4117.3M
- Data points: 405

### Net Flow

**Bias:** 🔴 N/A
- Call Flow: $0.0M
- Put Flow: $0.0M
- Call/Put Ratio: 0.00x

### Order Flow Statistics

**Premium Bias:** 🟢 CALL-HEAVY
- Total Call Premium: $1643.45M
- Total Put Premium: $374.63M
- Aggressive Call Buys (AA): $74.05M
- Aggressive Put Sells (BB): $46.25M

---

## 2. IV Rank — Entry Eligibility (§4 Quality Filter)

> **Rule:** IVR > 25 required before entering new put credit spreads or Jade Lizards.

| Ticker | Tier | Price | Call IV | Put IV | Avg IVR | Put Spread Eligible |
|--------|------|-------|---------|--------|---------|---------------------|
| SPX | Macro | $7,260.26 | 13.6% | 15.1% | 26.6 | ✅ YES | - |
| SPY | Macro | $724.04 | 14.4% | 15.1% | 26.4 | ✅ YES | - |
| MSFT | Tier 1 | $411.33 | 25.6% | 28.6% | 45.2 | ✅ YES | - |
| AVGO | Tier 1 | $427.50 | 55.5% | 53.8% | 63.9 | ✅ YES | 🔥 CRUSH |
| NFLX | Tier 1 | $87.90 | 30.8% | 30.9% | 27.6 | ✅ YES | - |
| VST | Tier 1 | $160.38 | 58.9% | 61.2% | 70.5 | ✅ YES | 🔥 CRUSH |
| GOOGL | Tier 1 | $388.47 | 30.3% | 31.0% | 30.4 | ✅ YES | - |
| AMZN | Tier 1 | $273.51 | 28.3% | 28.0% | 17.9 | ❌ NO | - |
| AMD | Tier 1 | $355.26 | 66.9% | 68.0% | 82.3 | ✅ YES | 🔥 CRUSH |
| MSTR | Tier 1 | $186.74 | 71.1% | 74.3% | 34.5 | ✅ YES | - |
| META | Tier 2 | $604.94 | 30.2% | 30.6% | 26.5 | ✅ YES | - |
| AAPL | Tier 2 | $284.18 | 22.8% | 24.5% | 36.9 | ✅ YES | - |
| NVDA | Tier 2 | $196.49 | 43.6% | 44.2% | 53.6 | ✅ YES | 🔥 CRUSH |

---

## 3. Tier 1 & 2 Execution Engines (GEX, Dark Pools, Whale Flow)

> **Workflow:** Cross-reference GEX/OI walls with Clean Decision Chart technicals. Watch Dark Pool levels as Hard Floors. Confirm Whale Flow bias before entry.

### MSFT Execution Profile
- **GEX Walls:** Calls at $415, $418, $412 | Puts at $280, $290, $385

### AVGO Execution Profile
- **GEX Walls:** Calls at $420, $422, $428 | Puts at $190, $195, $205

### NFLX Execution Profile
- **GEX Walls:** Calls at $92, $93, $95 | Puts at None

### VST Execution Profile
- **GEX Walls:** Calls at $158, $165, $180 | Puts at $95, $90, $115

### GOOGL Execution Profile
- **GEX Walls:** Calls at $388, $390, $365 | Puts at $135, $120, $255

### AMZN Execution Profile
- **GEX Walls:** Calls at $270, $268, $272 | Puts at $185, $170, $160

### AMD Execution Profile
- **GEX Walls:** Calls at $362, $358, $365 | Puts at $145, $165, $160

### MSTR Execution Profile
- **GEX Walls:** Calls at $178, $182, $180 | Puts at $106, $118, $104

### META Execution Profile
- **GEX Walls:** Calls at $615, $612, $618 | Puts at $200, $220, $230

### AAPL Execution Profile
- **GEX Walls:** Calls at $280, $282, $285 | Puts at $360, $185, $205

### NVDA Execution Profile
- **GEX Walls:** Calls at $202, $205, $208 | Puts at $50, $105, $115


### UNH Execution Profile
- **Dark Pool Hard Floors:** *No data*
- **GEX Walls:** Calls at $370, $368, $375 | Puts at $220, $262, $272
### SPY Execution Profile
- **Dark Pool Hard Floors:** $682.16 (2013.6M), $687.37 (1631.3M), $687.35 (1587.2M)
- **GEX Walls:** Calls at $724, $723, $725 | Puts at $630, $570, $525
### SPX Execution Profile
- **Dark Pool Hard Floors:** *No Dark Pool data available (index)*
- **GEX Walls:** Calls at $7280, $7260, $7250 | Puts at $7415, $3800, $9200
### UNH Execution Profile
- **Dark Pool Hard Floors:** *No Dark Pool data available*
- **GEX Walls:** Calls at $370, $368, $375 | Puts at $220, $262, $272
### SPY Execution Profile
- **Dark Pool Hard Floors:** $682.16 (2013.6M), $687.37 (1631.3M), $687.35 (1587.2M)
- **GEX Walls:** Calls at $724, $723, $725 | Puts at $630, $570, $525
### SPX Execution Profile
- **Dark Pool Hard Floors:** *No Dark Pool data available (index)*
- **GEX Walls:** Calls at $7280, $7260, $7250 | Puts at $7415, $3800, $9200
### UNH Execution Profile
- **Dark Pool Hard Floors:** *No Dark Pool data available*
- **GEX Walls:** Calls at $370, $368, $375 | Puts at $220, $262, $272
---

## 3. Strategy Flags

**Put Spread / Jade Lizard Eligible (IVR ≥ 25):** SPX, SPY, MSFT, AVGO, NFLX, VST, GOOGL, AMD, MSTR, META, AAPL, NVDA
**Below IVR Threshold (IVR < 25):** AMZN

### Macro Regime Summary

| Signal | Value |
|--------|-------|
| Net Drift | 🔴 BEARISH |
| Net Flow | 🔴 N/A |
| Order Flow | 🟢 CALL-HEAVY |
| **Overall Regime** | **🔴 BEARISH** |

> **1/3 bullish signals** — Caution: bearish regime. Pause new entries unless VIX confirms.

---

*End of QuantData Daily Report — 2026-05-05*