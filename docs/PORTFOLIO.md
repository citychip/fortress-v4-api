# Fortress — Portfolio Reference
**v3.9 · Updated 2026-06-04**

---

## Current Account (2026-06-04 ~17:30 ET)

| Metric | Value |
|---|---|
| Net Liq | ~$83,722 |
| Available | ~$28,329 |
| Excess Liq | ~$33,360 |
| Portfolio Δ | ~+436 raw / +285.5 beta-weighted |
| Portfolio Θ | ~+$78/day |
| Vega | ~341 |
| VIX | 15.54 |
| Regime | Bearish |
| Pacing | 0/5 this week |

**MSFT concentration: ~93.2% of NLV — new entries LOCKED.**

---

## Open Positions (2026-06-04, post-roll)

| Ticker | Strategy | Structure | Expiry | Δ | Notes |
|---|---|---|---|---|---|
| **MSFT** | PMCC | Jan28 310C×4 + Jan28 340C×2 (LEAPs) | — | 0.86 / 0.81 | Long legs only |
| **MSFT** | PMCC short | Aug21 465C ×1 | Aug21 | 0.340 | Inside band |
| **MSFT** | PMCC short | Sep18 490C ×2 | Sep18 | 0.261 | Rolled this session (was 450C) |
| **MSFT** | PMCC short | Dec18 510C ×3 | Dec18 | 0.290 | Rolled this session (was 480C) |
| **MSFT** | BPS | Jun18 380P/370P ×1 | Jun18 | ~-0.04 | 14 DTE, nearly worthless — let expire |
| **GOOGL** | PMCC | Jan28 310C LEAP → Aug21 420C short | Aug21 | 0.285 | Rolled this session (was Jul17 390C) |
| **AMZN** | PMCC | Jan28 200C LEAP → Jul17 285C short | Jul17 | 0.174 | Safe |
| **NVDA** | PMCC | Jan28 170C LEAP → Aug21 250C short | Aug21 | 0.292 | Safe. Roll to Sep 265C still unfilled |
| **META** | IC | Jul17 535P/550P + 695C/710C | Jul17 | 0.233 | Safe |
| **V** | PCS | Jul17 300P/295P ×4 | Jul17 | -0.194 | ACT: barely below 200-SMA ($321 vs floor $322) |
| **AMD** | PCS | Jun26 380P/375P ×1 | Jun26 | -0.04 | 22 DTE, far OTM — let expire |
| **OST** | Stock | 44 shares | — | — | Delisted, ignore |

---

## Pending Actions

1. **MSFT Jun18 BPS** — nearly worthless, let expire Jun18
2. **AMD Jun26 PCS** — far OTM, let expire Jun26
3. **NVDA roll** — Aug21 250C → Sep19 265C still unfilled (order `2572e40c` from Jun2). Re-stage if delta rises above 0.35 (currently 0.292, safe)
4. **AAPL LEAP** — WAIT. WWDC June 8 may create dip to $300-305. Default entry June 10. Strike: Jan28 250C (~$86/contract)
5. **MSFT de-risking** — no action this session; concentration at 93.2%. Ongoing strategic goal: below 50% by Dec 2026. Method: roll short calls aggressively on IV spikes, no new PMCC legs
6. **2 unhedged MSFT LEAPs** — Jan28 310C×4 partially uncovered. Add covered call legs when conditions allow

---

## Strategy Quick Reference (v3.8.0)

All thresholds are advisory — signals for review, not automatic triggers.

### Entry Gates (all must pass)
- IVR > 25 — minimum; dual-confirm: `get_candidates()` + `qd_get_iv_rank(ticker)`
- IVR > 50 — prime entry zone
- Execute after **10:00 AM ET only**
- Max **5 new positions per week** (pacing gate)
- No earnings within **10 days** (PCS) or **14 days** (LEAP)
- MSFT: **no new entries** (concentration lock)

### Delta Rules
- Entry: **0.25–0.30 Δ** on short leg
- Watch: **> 0.35 Δ** — review
- Roll trigger: **> 0.40 Δ** — act

### Strike Selection
1. GEX call wall (QuantData `qd_get_exposure_by_strike`)
2. Delta 0.25–0.30 filter
3. Chart confirmation (resistance, SMA)
4. Earnings vol check

### PMCC Structure
- LEAP: Jan 2028 cycle, 25–30% ITM, Δ 0.78–0.85
- Short: 30–45 DTE, 7–10% OTM, Δ 0.25–0.30
- Ratio: strict 1:1, never leave a LEAP uncovered

### Put Credit Spreads
- Short strike: Δ 0.15–0.20 (80–85% PoP)
- Width: $5–$10, anchored below DP floor / GEX put wall
- DTE: 30–45 at entry

### MSFT De-risking Target
- Goal: below 50% NLV by December 2026
- Method: roll short calls aggressively on IV spikes; do not add new PMCC legs

---

## Approved Universe

**Tier 1 (primary):** MSFT, AVGO, NFLX, VST, GOOGL, AMZN, AMD, MSTR, UNH, APP, LLY, TSM, V, MU, GEV

**Tier 2 (secondary):** META, AAPL, NVDA

**Index / hedge:** SPX, SPY

**Excluded:** COIN, HOOD, SMCI (regulatory risk) · OST (ignore) · NVDIA (typo alias for NVDA)

---

## LEAP Watch List (2026-06-04)

| Ticker | Price | IV | IVR | Status | Trigger |
|---|---|---|---|---|---|
| **AAPL** | $311 | ~24% | 75.4 | WAIT | WWDC June 8 dip to $300-305; default entry June 10. Strike: Jan28 250C (~$86) |
| **META** | $630 | ~35% | 49.0 | WAIT | IV > 30-32% target; needs compression |
| **NVDA** | $218 | ~39% | 62.9 | WAIT | IV > 38% threshold; watch post-Computex vol crush |
| **MSFT** | $428 | ~30% | 53.7 | BLOCKED | Concentration locked (93.2% NLV) |

---

## OAuth 1.0a Status

Implementation complete. Consumer key: **SHARMILAH**.
- Stage 1 (LST generation): ✅ confirmed working 2026-06-04
- Stage 2 (brokerage session): ❌ pending IBKR weekend activation — test Monday
- Test script: `python3 /mnt/c/.../2606Fortress/test_ibkr_oauth.py`
- Key files: `/home/ubuntu/ibkr-oauth/`
- Toggle: Parapet → System → Settings → Connections → switch backend to OAuth
