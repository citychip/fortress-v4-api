## AI Summary

- Macro regime for SPX is bearish with net drift showing $319M more premium on puts vs calls; however, the premium bias remains call-heavy, indicating possible mixed sentiment or short-term call buying.
- SPX and SPY IV ranks are below 25, so no new put spreads on index; eligible tickers for new put credit spreads include MSFT, AVGO, VST, GOOGL, AMD, MSTR, META, AAPL, and NVDA, with AMD and NVDA flagged as "CRUSH" for high IV rank.
- Significant GEX call walls cluster around $7,000-$7,030 on SPX indicating strong gamma barriers on the upside; put GEX walls near $5,200-$5,400 effectively neutral with negligible gamma.
- Dark pool hard floors and GEX walls for top Tier 1 assets (MSFT, AVGO) identified for precise entry zones, supporting use of these levels for put spread strikes and risk management.
- No fresh net flow bias detected today; maintain focus on tickers with IVR > 25 and confirmed whale flow for new entries in put credit spreads or diagonals.

---

# QuantData Daily Report — 2026-05-01
*Generated: 2026-05-01 12:59 ET | Portfolio Strategy v3.2*

---

## 1. Macro Regime — SPX

**Current Price:** $6,890.07  |  **GEX Flip Zone:** $5,230

### GEX Walls (Gamma Exposure)

| Side | Strike | Net GEX ($M) |
|------|--------|--------------|
| Call Wall | $6,900 | +1004.2 |
| Call Wall | $7,010 | +917.2 |
| Call Wall | $7,000 | +759.5 |
| Call Wall | $7,030 | +623.7 |
| Call Wall | $7,020 | +457.5 |
| Put Wall  | $5,210 | -0.0 |
| Put Wall  | $5,430 | -0.0 |
| Put Wall  | $5,320 | -0.0 |
| Put Wall  | $5,275 | -0.0 |
| Put Wall  | $5,150 | -0.0 |

### Open Interest Walls

| Side | Strike | OI Contracts |
|------|--------|--------------|
| Call OI | $7,000 | 13,910 |
| Call OI | $7,030 | 12,622 |
| Call OI | $7,010 | 12,603 |
| Put OI  | $5,825 | 44,107 |
| Put OI  | $5,725 | 43,946 |
| Put OI  | $4,800 | 23,910 |

### Net Drift (Cumulative Premium Flow)

**Direction:** 🔴 BEARISH
- Call Premium: $459.0M
- Put Premium: $778.1M
- Net: $-319.1M
- Data points: 405

### Net Flow

**Bias:** 🔴 N/A
- Call Flow: $0.0M
- Put Flow: $0.0M
- Call/Put Ratio: 0.00x

### Order Flow Statistics

**Premium Bias:** 🟢 CALL-HEAVY
- Total Call Premium: $872.97M
- Total Put Premium: $425.82M
- Aggressive Call Buys (AA): $18.34M
- Aggressive Put Sells (BB): $18.98M

---

## 2. IV Rank — Entry Eligibility (§4 Quality Filter)

> **Rule:** IVR > 25 required before entering new put credit spreads or Jade Lizards.

| Ticker | Tier | Price | Call IV | Put IV | Avg IVR | Put Spread Eligible |
|--------|------|-------|---------|--------|---------|---------------------|
| SPX | Macro | $7,245.14 | 12.6% | 14.6% | 22.4 | ❌ NO | - |
| SPY | Macro | $722.18 | 13.7% | 14.5% | 22.2 | ❌ NO | - |
| MSFT | Tier 1 | $413.69 | 25.2% | 28.2% | 43.6 | ✅ YES | - |
| AVGO | Tier 1 | $420.23 | 41.8% | 42.7% | 25.6 | ✅ YES | - |
| NFLX | Tier 1 | $93.08 | 28.3% | 28.9% | 18.6 | ❌ NO | - |
| VST | Tier 1 | $157.88 | 57.9% | 0.0% | 31.7 | ✅ YES | - |
| GOOGL | Tier 1 | $385.17 | 29.7% | 30.3% | 27.0 | ✅ YES | - |
| AMZN | Tier 1 | $268.76 | 27.4% | 28.5% | 17.2 | ❌ NO | - |
| AMD | Tier 1 | $358.45 | 66.9% | 68.1% | 82.5 | ✅ YES | 🔥 CRUSH |
| MSTR | Tier 1 | $177.13 | 71.4% | 69.9% | 32.2 | ✅ YES | - |
| META | Tier 2 | $612.71 | 30.2% | 30.9% | 27.1 | ✅ YES | - |
| AAPL | Tier 2 | $283.48 | 21.5% | 23.3% | 29.6 | ✅ YES | - |
| NVDA | Tier 2 | $199.20 | 43.5% | 44.3% | 53.6 | ✅ YES | 🔥 CRUSH |

---

## 3. Tier 1 & 2 Execution Engines (GEX, Dark Pools, Whale Flow)

> **Workflow:** Cross-reference GEX/OI walls with Clean Decision Chart technicals. Watch Dark Pool levels as Hard Floors. Confirm Whale Flow bias before entry.

### MSFT Execution Profile
- **Dark Pool Hard Floors:** $389.00 (982.6M), $384.47 (260.5M), $386.49 (28.9M)
- **GEX Walls:** Calls at $390, $400, $395 | Puts at $320, $325, $300

### AVGO Execution Profile
- **Dark Pool Hard Floors:** $325.49 (1381.4M), $330.34 (114.7M), $324.08 (24.7M)
- **GEX Walls:** Calls at $350, $340, $345 | Puts at $505, $500, $210

### NFLX Execution Profile
- **Dark Pool Hard Floors:** $78.04 (86.5M), $77.27 (20.9M), $77.26 (18.3M)
- **GEX Walls:** Calls at $80, $81, $79 | Puts at $66, $60, $67

### VST Execution Profile
- **Dark Pool Hard Floors:** $171.62 (11.2M), $170.31 (3.8M), $170.59 (3.8M)
- **GEX Walls:** Calls at $175, $185, $188 | Puts at $133, $132, $137

### GOOGL Execution Profile
- **Dark Pool Hard Floors:** $310.89 (893.7M), $311.27 (134.8M), $310.81 (60.7M)
- **GEX Walls:** Calls at $318, $315, $320 | Puts at $230, $215, $268

### AMZN Execution Profile
- **Dark Pool Hard Floors:** $208.56 (508.7M), $208.42 (29.0M), $209.08 (28.6M)
- **GEX Walls:** Calls at $215, $210, $212 | Puts at $135, $145, $140

### AMD Execution Profile
- **Dark Pool Hard Floors:** $213.84 (239.5M), $216.00 (42.2M), $214.00 (35.8M)
- **GEX Walls:** Calls at $215, $210, $205 | Puts at $105, $340, $110

### MSTR Execution Profile
- **Dark Pool Hard Floors:** $124.61 (32.3M), $124.75 (9.7M), $124.31 (7.9M)
- **GEX Walls:** Calls at $137, $130, $135 | Puts at $30, $50, $55

### META Execution Profile
- **Dark Pool Hard Floors:** $639.29 (326.9M), $637.25 (19.4M), $639.16 (14.8M)
- **GEX Walls:** Calls at $660, $665, $680 | Puts at $370, $330, $350

### AAPL Execution Profile
- **Dark Pool Hard Floors:** $272.14 (1558.8M), $272.27 (43.2M), $272.33 (35.4M)
- **GEX Walls:** Calls at $280, $275, $270 | Puts at $370, $185, $135

### NVDA Execution Profile
- **Dark Pool Hard Floors:** $192.85 (2740.5M), $192.63 (110.6M), $192.90 (104.8M)
- **GEX Walls:** Calls at $195, $200, $202 | Puts at $50, $115, $90


### SPY Execution Profile
- **Dark Pool Hard Floors:** $682.16 (2013.6M), $687.37 (1631.3M), $687.35 (1587.2M)
- **GEX Walls:** Calls at $697, $700, $696 | Puts at $780, $485, $475
### SPX Execution Profile
- **Dark Pool Hard Floors:** *No Dark Pool data available (index)*
- **GEX Walls:** Calls at $6900, $7010, $7000 | Puts at $5210, $5430, $5320
### UNH Execution Profile
- **Dark Pool Hard Floors:** *No Dark Pool data available*
- **GEX Walls:** Calls at $370, $368, $375 | Puts at $220, $262, $272
### UNH Execution Profile
- **Dark Pool Hard Floors:** *No Dark Pool data available*
- **GEX Walls:** Calls at $370, $368, $375 | Puts at $220, $262, $272
---

## 3. Strategy Flags

**Put Spread / Jade Lizard Eligible (IVR ≥ 25):** MSFT, AVGO, VST, GOOGL, AMD, MSTR, META, AAPL, NVDA
**Below IVR Threshold (IVR < 25):** SPX, SPY, NFLX, AMZN

### Macro Regime Summary

| Signal | Value |
|--------|-------|
| Net Drift | 🔴 BEARISH |
| Net Flow | 🔴 N/A |
| Order Flow | 🟢 CALL-HEAVY |
| **Overall Regime** | **🔴 BEARISH** |

> **1/3 bullish signals** — Caution: bearish regime. Pause new entries unless VIX confirms.

---

*End of QuantData Daily Report — 2026-05-01*