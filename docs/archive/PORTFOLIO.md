# Fortress — Portfolio Reference
**v4.1 · Updated 2026-06-15 (live, post-MSFT/AAPL rotation + AMD/META spreads)**

> Data per the ⭐ procedure in `HANDOFF.md`: account/positions from fortress `get_briefing`/`get_positions` (IBKR web_api), IV rank from fortress `get_iv_rank` (NOT qd), GEX/skew from fortress `get_gex`/`get_vol_skew`. Verify `active_backend: web_api` before trusting any number.

---

## Current Account (2026-06-15 ~16:03 UTC)

| Metric | Value |
|---|---|
| Net Liq | ~$74,404 (€64,099) |
| Available | ~$36,020 |
| Excess Liq | ~$39,446 |
| Portfolio Δ | +524 raw / **+308 beta-weighted** (target ~320) |
| Portfolio Θ | +$53/day |
| Vega | ~528 |
| VIX | 16.3 |
| Regime | Bearish |
| Pacing | 0/5 logged ⚠ (manual IBKR fills not counted — 4 trades done today) |

**MSFT concentration: 41.9% of NLV — now BELOW the 50% cap, warning cleared.** (Was 59% this morning; cut by selling 1× Jan28 310C.)

---

## Open Positions (2026-06-15)

| Ticker | Strategy | Structure | Expiry | %NLV | Notes |
|---|---|---|---|---|---|
| **MSFT** | LEAPs + short calls | Long Jan28 310C×1 + 340C×2; short Sep18 490C×2, Dec18 510C×3; long Aug21 465C×1 | mixed | 41.9 | Sold 1× 310C today (de-risk). Short legs deep OTM, safe |
| **MSFT** | BPS (expiring) | Jun18 380P/370P ×1 | Jun18 | ~0 | Worthless — let expire Thu Jun 18 |
| **AAPL** | LEAPs | Jan28 290C×1 + **240C×1** | Jan28 | 19.0 | 240C added today (Δ0.79). Combined Δ ~145 |
| **GOOGL** | PMCC | Jan28 310C LEAP + Aug21 420C short | Aug21 | 14.1 | Δ0.26, safe |
| **AMZN** | PMCC | Jan28 200C LEAP + Jul17 285C short | Jul17 | 10.5 | Δ0.08, safe |
| **NVDA** | PMCC | Jan28 170C LEAP + Aug21 250C short | Aug21 | 9.4 | Δ0.21 — roll only if >0.35 |
| **META** | PCS (NEW) | **Jul31 545/525** put credit | Jul31 | credit | ⚠ earnings Jul 29 INSIDE — close before. Alert `320fc5ae` set |
| **AMD** | PCS ×2 | Jun26 380/375 (expiring) + **Jul31 450/430** (NEW) | mixed | credit | Jun26 far OTM, let expire. Jul31 = today's good-POP sell |
| **V** | PCS | Jul17 300P/295P ×4 | Jul17 | credit | Δ-0.12, safe (borderline vs 200-SMA) |
| **OST** | Stock | 44 shares | — | 0.1 | Ignored entirely (§3.3) |

---

## Pending Actions / Watch

1. **META Jul31 PCS — CLOSE before Jul 29 earnings.** Spread expires Jul 31, two days after the print. Conditional alert `320fc5ae` fires at DTE≤8 (~Jul 23). Take profit at 50% or close to avoid gap risk.
2. **MSFT Jun18 BPS** — let expire Thu Jun 18. No action.
3. **AMD Jun26 PCS** — let expire Jun 26. No action.
4. **MSFT 385 / 412 alerts** — the 385 conditional alert is still flagged `triggered` from a Jun 11 intraday wick (MSFT never *closed* <385); the 412 "sell into strength" alert is missing. Re-arm 385 (close-based framing) and recreate 412 if continuing the staged exit.
5. **MSFT de-risking** — primary target (<50% NLV) ACHIEVED at 41.9%. Tranche 2 of the staged exit (sell another 310C + cover) optional, on the same <$385 / >$412 triggers, post-FOMC. No tax friction (Dutch Box 3).
6. **NVDA roll** — Aug21 250C Δ0.21, safe. Re-stage only if Δ > 0.35.
7. **OAuth Stage 2** — still pending IBKR (Priority 7). Reminder set for Jun 22. Live data unaffected (runs on web_api).

## Stop-Loss Watch (ACT = below 200-SMA; no mechanical trigger)

| Ticker | Price | 200-SMA Floor | Verdict | Notes |
|---|---|---|---|---|
| MSFT | $398.59 | $442.32 | ACT | Short calls deep OTM — no required action; ties to de-risk thesis |
| V | $325.43 | $328.23 | SAFE | Borderline (~$3 below SMA); PCS short 300, cushioned |
| All others | — | — | SAFE | No signals |

---

## Strategy Quick Reference (v3.9.0)

All thresholds advisory — signals for review, not automatic triggers.

### Entry Gates (all must pass)
- IVR ≥ 25 minimum, ≥ 50 prime — source: fortress **`get_iv_rank(ticker)`** (NOT qd_get_iv_rank — broken)
- Execute after **10:00 AM ET only**
- Max **5 new positions per week** (track manually — counter misses manual fills)
- No earnings within **10 days** (PCS) / **14 days** (LEAP) — and don't let the expiry span an earnings date
- Regime gate: bearish → IC / far-OTM CSP / defined-risk PCS preferred

### Delta Rules
- Entry short leg: **0.25–0.30 Δ** (PMCC) or **0.15–0.20 Δ** (put credit spreads, 80–85% PoP)
- Watch: **> 0.35 Δ** · Roll: **> 0.40 Δ**
- Portfolio β-weighted Δ target: **~320**

### Strike Selection
1. GEX call wall — fortress **`get_gex(ticker)`** (NOT qd_get_exposure_by_strike — broken in RTH)
2. Delta filter · 3. Chart confirmation · 4. Earnings vol check
5. Price spreads at the **mid**; confirm credit/POP with `get_iv_rank` + live chain (`qd_get_contract_price`/massive) — `strategy_metrics` uses placeholder vol, ranking only

### PMCC / PCS Structure
- LEAP: Jan 2028, Δ 0.78–0.85, strict 1:1 coverage (never leave a LEAP uncovered)
- Short: 30–45 DTE · PCS width $5–$20 anchored below DP floor / GEX put wall

### MSFT De-risking
- Target <50% NLV — **achieved (41.9%)**. Continue opportunistically on IV spikes; no new MSFT PMCC legs. No tax friction (Dutch Box 3).

---

## Approved Universe (as of 2026-06-09)

**Tier 1 (23):** MSFT, AVGO, NFLX, VST, GOOGL, AMZN, AMD, MSTR, UNH, APP, LLY, TSM, V, MU, GEV, META, AAPL, ELV, GE, PNC, CSX, MAR, NVDA

**Tier 2:** (none)

**Index / hedge:** SPX, SPY, VIX

**Excluded:** COIN, HOOD, SMCI (regulatory, until cleared) · OST (ignored entirely — display only, never recommend)

---

## OAuth 1.0a Status

Consumer key **SHARMILAH**. Stage 1 (LST) ✅ 2026-06-04. Stage 2 (brokerage session) ❌ — re-tested 2026-06-15 via `test_ibkr_oauth.py`, still 401 "Invalid signature" at `ssodh/init`. Pending IBKR activation (Priority 7).
- ⚠ Do NOT trust `get_ibkr_status.oauth` — it reports `authenticated:true` while the handshake fails. Only the script confirms Stage 2.
- Test: `python3 /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/test_ibkr_oauth.py` · Keys: `/home/ubuntu/ibkr-oauth/`
- Active backend: `web_api` (iBeam headless) — unaffected by OAuth status.
