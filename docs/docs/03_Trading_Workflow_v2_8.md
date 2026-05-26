# Trading Workflow

**Version 2.9.0 — May 13, 2026**
**Strategy:** Portfolio Strategy v3.6

End-to-end automated trading workflow integrating QuantData market data, the Fortress Dashboard, and the IBKR Web API (CP Gateway) with Portfolio Strategy v3.6. Eight Python scripts run on schedule; the dashboard surfaces the outputs; the Phase 4 engines code-enforce the strategy's complex decision rules; live-tunable settings via Settings tab.

v2.9.0 adds: Full integration of the 13 UX/Automation improvements (A-M) and the new Trade Reports tab, allowing batch execution of workflow checks directly from the dashboard UI.

Governing principle from Strategy §15.1:

> "Reports are inputs, not triggers. Every trade goes through the framework's pre-trade checklist. No report fires a trade. Tools warn; humans decide."

---

## 1. Overview

This document is the operational manual. Companions:

- **Strategy v3.6** (`01_Portfolio_Strategy_v3_6.md`) — the decision rules.
- **Build Spec v1.8** (`02_Trading_Dashboard_Build_Spec_v1_8.md`) — what the dashboard does.
- **VPS Guide v1.5** (`04_VPS_Implementation_Guide_v1_5.md`) — deployment.
- **Implementation Status** (`05_Implementation_Status.md`) — current reality and known issues.

If anything in this doc conflicts with Strategy v3.6, Strategy v3.6 wins.

---

## 2. Script Inventory

All scripts in `/home/ubuntu/Fortress_Dashboard/quant/`. Triggered by `fortress_orchestrator.service` on schedule, or manually via `POST /api/run/{script_key}`.

| # | Script | Status | Schedule |
|---|---|---|---|
| 1 | `quantdata_daily.py` | Built & scheduled | Weekdays 09:35 ET |
| 2 | `workflow_01_premarket_scanner.py` | Built & tested | Weekdays 09:00 ET |
| 3 | `workflow_02_entry_scoring.py` | On-demand | per-ticker |
| 4 | `workflow_03_position_monitor.py` | Built & tested | Weekdays 12:00 + 15:45 ET |
| 5 | `workflow_04_eod_review.py` | Built & tested | Weekdays 16:15 ET |
| 6 | `workflow_05_iv_crush_report.py` | Built & tested | Weekdays 09:35 ET |
| 7 | `workflow_06_dark_pool_alert.py` | Built & tested | Weekdays 12:00 + 15:45 ET |
| 8 | `workflow_07_whale_flow_report.py` | Built & tested | Weekdays 09:35 ET |
| 9 | `workflow_08_max_pain_report.py` | Built & tested | Weekly Friday + on-demand at 14 DTE |
| 10 | `gex_oi_report.py` | Built & tested | On-demand |

---

## 3. Daily Workflow Schedule

### Phase 1 — Pre-Market (09:00–09:35 ET)

**Step 1.1: Pre-Market Scanner.** `workflow_01_premarket_scanner.py`. Filters Tier 1 + Tier 2 for IVR ≥ 25.

**Step 1.2: Trigger fresh IBKR sync.** `POST /api/ibkr/sync`. **The dispatcher picks the active backend per `cfg("technical.greeks_backend")`** — usually `auto` → web_api. Refreshes positions, account, Greeks (delta/theta/vega/IV/mark when OPRA active), SPY hedge coverage. The Briefing tab's stale-data banner clears once complete.

**Step 1.3: Capability check.** Dashboard header shows the Greeks-backend badge. Confirm it's green ("Δ: Web API+OPRA"). If amber ("Δ: BS yfinance"), check the Settings tab → Technical → Greeks backend, or `/api/ibkr/capability?refresh=1` in the browser to see why (likely the daily 2FA push wasn't approved — see §6.2).

**Step 1.4: Briefing pre-market read.** Open dashboard Briefing tab. Confirm:
- Account thresholds (USD primary + EUR equivalent + ok/breach flag).
- Pacing budget remaining for the week.
- Concentration top-3.
- Portfolio Greeks bias (`long`/`short`/`neutral`) — all four Greeks populated when web_api backend.
- VIX state border (none / amber / red).
- Today's Actions list — any HIGH-priority items.

### Phase 2 — Market Open (09:35–10:00 ET)

**Step 2.1: Daily QuantData Summary.** `quantdata_daily.py` (auto-scheduled). Same as v2.7.

**Step 2.2: IV Crush Opportunity Report.** `workflow_05_iv_crush_report.py`. Same as v2.7.

**Step 2.3: Whale Flow Report.** `workflow_07_whale_flow_report.py`. Same as v2.7.

### Phase 3 — Trade Entry Window (10:00–11:30 ET)

**Step 3.0: Pre-Trade Gate.** Fortress Dashboard → Reports tab → "Run pre-trade checks on all universe tickers" button. Or check a single ticker in the Trade tab.

Four checks run in order, hard-fail on any:
1. **Hard exclusion (§3.3)** — checks `ticker_universe.json` excluded list.
2. **Earnings blackout (§4)** — days-to-earnings vs strategy window.
3. **Concentration (§7)** — flags >50% as failed.
4. **VIX state (§7)** — fails if VIX > `cfg("strategy.vix_high")` (default 25).

**Step 3.1: Trade Entry Scoring Engine.** `workflow_02_entry_scoring.py <TICKER>`. Same as v2.7.

**Step 3.2: GEX & OI Profile.** `gex_oi_report.py`. Same as v2.7.

**Step 3.3: Manage Tab Chart Review.** Same as v2.7 — DP/GEX overlays.

**Step 3.4: Strategy-specific validators.**
- **Jade Lizard:** Manage tab → "Validate Jade Lizard" form, or `POST /api/manage/validate_jade_lizard`. Hard-FAIL if total credit ≤ call spread width (Strategy §2.E).
- **Post-earnings entry:** Playbook tab → matrix form with gap %, IV crush %, thesis checkboxes. Returns PROCEED only when matrix verdict is PRIME_ENTRY/CONDITIONAL/EVALUATE AND all 4 thesis checks pass.

### Phase 4 — Mid-Day Monitoring (11:00–15:45 ET)

**Step 4.1: Position Monitor.** `workflow_03_position_monitor.py` (auto at 12:00 + 15:45 ET) or Dashboard → Reports tab → "Check active book for alerts". Checks for stop-loss triggers and automatically creates `URGENT` or `ACT` alerts. The live alerts banner will appear at the top of the dashboard if any action is required.

**Step 4.2: Dark Pool Alert Report.** `workflow_06_dark_pool_alert.py`.

**Step 4.3: Stop-loss aggregator (on-demand).** Manage tab → "Run stop-loss evaluator on all positions" button. The dashboard evaluates all positions against the 3-signal logic per Strategy §6 and displays a HIGH/MED/LOW priority verdict for each. You can also evaluate a single position using the `⋯` row action.

**Step 4.4: Roll candidate evaluator (on-demand).** Manage tab → "Run roll evaluator on all positions" button. The dashboard evaluates all eligible positions, returns the top 3 candidates per Strategy §5, and generates the IBKR ticket text. You can also evaluate a single position using the `⋯` row action.

### Phase 5 — Pre-Close Review (15:00–16:00 ET)

Same as v2.7. Manual but informed by 15:45 outputs.

### Phase 6 — End of Day (16:15–17:00 ET)

**Step 6.1: End of Day Review.** `workflow_04_eod_review.py`. Same as v2.7.

**Step 6.2: Journal entries.** Open dashboard Journal tab. Click "Auto-suggest from IBKR" to pre-fill the form with the most recent sync change. Enter any missing trade details. Ensure `outside_universe_justification` is provided if trading outside the universe (Strategy §3.4.4).

---

## 4. Weekly Workflow

### 4.1 Sunday Evening Planning

| Task | Where | Purpose |
|---|---|---|
| IV Crush scan | `workflow_05_iv_crush_report.py` | Identify richest premium-selling candidates |
| GEX & OI profile | `gex_oi_report.py` | Review structural levels |
| Auto-fetch earnings calendar | Universe tab → "Auto-fetch from Yahoo ↻" | Pre-stage 10-day blackout windows |
| Trigger fresh IBKR sync | header refresh, or `POST /api/ibkr/sync` | Sync positions + account + Greeks |
| Review Portfolio Greeks bias | Briefing → Greeks card | Set directional context |
| SPY hedge coverage check | Manage → SPY hedge card | Confirm hedge MV in $20K–$30K target band |
| **Settings review** (NEW v2.8) | Settings tab | Revisit `delta_critical_threshold`, USD floors, etc. quarterly |
| Clean Decision Charts review | TradingView | Flag any 200-day MA breaks |

### 4.2 Friday Afternoon Wrap

| Task | Where | Purpose |
|---|---|---|
| Max Pain Report | `workflow_08_max_pain_report.py` | Pinning targets for next week |
| Position review at 14 DTE | Manual + max pain | Flag positions entering time-based roll window |
| SPY hedge coverage check | Manage tab | Confirm MV is in $20K–$30K band before close |

---

## 5. Max Pain Report

Unchanged from v2.7.

---

## 6. Operational Notes

### 6.1 Currency convention (v2.8 — USD-native)

Strategy v3.6 §7 thresholds are **USD-denominated** (was EUR pre-v2.8). The dashboard now stores and compares in USD natively.

Display:
- **Primary value** in USD (matches IBKR).
- **Sub-text** shows EUR equivalent (informational only) and threshold check ("≈ €27.7K · target >$25K · ok").
- **Threshold breach** flips to amber.

When entering trades manually, IBKR shows USD; the dashboard's USD threshold check is direct.

EUR equivalent is shown alongside via yfinance EUR/USD rate (1h cache) for users who think in EUR; not used in any decision logic.

### 6.2 IBKR Read-Only API permission (CP Gateway)

The dashboard's broker integration is now CP Gateway (voyz/ibeam) at `https://localhost:5000`. With Read-Only API enabled at the IBKR account level (May 5, 2026), the gateway no longer interrupts snapshot fetches with the "API client needs write access" dialog.

**Daily operational reality:** CP Gateway sessions expire every ~24h. `voyz/ibeam` re-authenticates automatically but **requires an IBKR Mobile push approval each cycle** — Steven gets a phone notification, taps to approve, ibeam continues.

If the push is missed:
- Capability badge in the dashboard header turns amber ("Δ: BS yfinance") within 60s of the auto-fall back.
- ibeam retries every ~60s; another push will arrive.
- During the fallback window, all sync paths still work — Greeks come from Black-Scholes via yfinance (less precise but reasonable for 30–45 DTE drift monitoring).

**Mitigation candidate:** OAuth 2.0 direct (deferred per migration plan §10).

### 6.3 Per-leg vs aggregated view

IBKR Web API writes one record per option leg. PMCC and diagonal positions appear as multiple rows. Dashboard provides two views:
- **Per-leg view** (`/api/positions`) — what IBKR sees. Used for the Positions tab table and audit.
- **Aggregated view** (`/api/manage/positions`) — one record per ticker with primary short call + primary long surfaced. Used by Phase 4 stop-loss / roll evaluator and the Briefing actions list.

Don't hand-edit `active_positions.json` between syncs — your edits will be wiped on the next `POST /api/ibkr/sync`.

### 6.4 Greeks backend selection (NEW v2.8)

Settings tab → Technical → Greeks backend lets you pick:

| Setting | Behavior | When to use |
|---|---|---|
| `auto` (default) | Capability check picks: web_api if OPRA + session OK, else bs_yfinance | Always |
| `web_api` | Force CP Gateway. Errors loudly if OPRA / session not ready | Confirm broker truly down before changing |
| `bs_yfinance` | Synthetic sync — refresh BS deltas against existing book; no broker call | Diagnostics; weekend reads when CP Gateway not authenticated |
| `tws_ibkr` | Force legacy TWS gateway (currently stopped) | Diagnostics only — must `docker compose up` the legacy gateway first |

The header backend badge shows the active backend. Hover for last-checked timestamp.

### 6.5 Settings hot-reload

`fortress_config.json` is the canonical runtime config. Edits via Settings tab take effect on the next API call — no restart. This means you can:
- Tighten `delta_critical_threshold` from 0.35 → 0.32 (or whatever) and the next sync immediately re-evaluates `delta_state` against the new threshold.
- Bump `available_funds_min_usd` from $17K → $20K to tighten margin discipline.
- Switch `greeks_backend` between `auto`, `web_api`, `bs_yfinance` without restarting the dashboard.

Live-tunable. No downtime. No restart.

### 6.6 Data-source enable/disable toggles (NEW v2.8.1)

Settings → Security exposes two master toggles:

**Enable IBKR Web API** (`security.use_ibkr_web_api`):
- When **off**: every `/api/ibkr/sync` call forces the `bs_yfinance` synthetic backend, regardless of `technical.greeks_backend`. Greeks are estimated via Black-Scholes; positions are read from the last snapshot; NetLiq is stale. An amber banner appears in the Settings UI immediately.
- Use this when CP Gateway is down for maintenance or you want to avoid live broker calls.

**Enable QuantData** (`security.use_quantdata`):
- When **off**: all QuantData-dependent workflow scripts return HTTP 503 when triggered via the dashboard. Chart DP/GEX overlays return empty arrays (plain candlesticks only). The stop-loss aggregator’s DP floor signal (Signal 4) is suppressed. An amber banner appears in the Settings UI immediately.
- `position_monitor` is **exempt** — it uses only yfinance/IBKR data and always runs.
- Use this when the QuantData API key is expired, the subscription has lapsed, or you are in a maintenance window.

Both toggles default to `true`. Turning them off does not require a restart.

---

## 7. Workflow Diagram (v2.8)

```
PRE-MARKET (09:00)
    ├─ workflow_01_premarket_scanner.py → Watchlist
    ├─ POST /api/ibkr/sync → backend dispatcher (auto → web_api or bs_yfinance)
    ├─ Header backend badge: green = Web API+OPRA, amber = BS yfinance
    └─ Briefing tab: pacing, concentration, Greeks bias (all 4 if web_api), VIX state

MARKET OPEN (09:35)
    ├─ quantdata_daily.py → Regime + IVR table
    ├─ workflow_05_iv_crush_report.py → IV/HV spread ranking
    └─ workflow_07_whale_flow_report.py → Institutional bias

ENTRY WINDOW (10:00–11:30)
    ├─ Dashboard → New Trade → Pre-Trade Gate (excl + earnings + conc + VIX)
    ├─ workflow_02_entry_scoring.py <TICKER> → Score 0-4
    ├─ Dashboard → Manage tab → Chart review (DP + GEX overlays)
    ├─ Dashboard → Manage → validate_jade_lizard (if applicable)
    └─ Dashboard → Playbook → post-earnings matrix (if morning-after)

MID-DAY (12:00 & 15:45)
    ├─ workflow_03_position_monitor.py → 200-day SMA check
    ├─ workflow_06_dark_pool_alert.py → DP floor alerts
    ├─ Dashboard → Manage → stop_loss aggregator (on-demand)
    └─ Dashboard → Manage → roll evaluator (on-demand) — flagged at delta > 0.35

PRE-CLOSE (15:00–16:00)
    └─ Manual: 80%/50% profit targets, 200% loss rule, HIGH actions

END OF DAY (16:15)
    ├─ workflow_04_eod_review.py → Next-day regime signal
    └─ Dashboard → Journal → log decisions

WEEKLY (Sunday)
    ├─ Auto-fetch earnings (dashboard)
    ├─ POST /api/ibkr/sync → fresh book
    ├─ Settings tab review → tunable thresholds
    ├─ SPY hedge coverage check
    └─ Clean Decision Charts for active LEAPs

WEEKLY (Friday)
    ├─ workflow_08_max_pain_report.py → Pinning targets
    └─ Position review at 14 DTE
```

---

## 8. Data Quality Principles

Unchanged from v2.7. The 5 principles still in force:

1. **TradingView Charts are the Source of Truth** for technical analysis.
2. **IBKR for Trade Decisions.** All trade decisions reference IBKR position MV, P&L, and Greeks (when available).
3. **Reports are Inputs, Not Triggers.** No report fires a trade.
4. **The 10-Day Earnings Window is Absolute.** No new put spreads, diagonals, or Jade Lizards within 10 days.
5. **The Concentration Override Requires Multiple Inputs.** §7 requires gap 5–8% + thesis health + IV crush. Cannot fire on flow signals alone.

---

## 9. Token Refresh Procedure

QuantData session tokens expire (typically 24–48h). When any script returns 401, refresh via DevTools Network tab on `v3.quantdata.us` (same as v2.7).

CP Gateway session refresh is **automatic** via voyz/ibeam — Steven approves the IBKR Mobile push when prompted; ibeam handles the rest.

---

## 10. Change Log

- **v2.8 (May 5, 2026 PM):** Currency convention switched to USD-native (§6.1). Phase 1 Step 1.2 + 1.3 reflect backend dispatcher (web_api vs bs_yfinance). New §6.4 Greeks backend selection. New §6.5 Settings hot-reload. Phase 4 Step 4.4 references **delta > 0.35 critical** (was 0.40). §6.2 IBKR Read-Only API focused on CP Gateway path. §7 workflow diagram updated to show backend dispatch + Settings tab review on Sundays.
- **v2.7 (May 4, 2026 PM):** Strategy v3.5 reference, hard-exclusion gate, IBKR Read-Only API note, per-leg vs aggregated view.
- **v2.6 (May 4, 2026 AM):** Manage Tab Chart Review (§3.3). Auto-fetch earnings on Sunday.
- **v2.4 / v2.3 / v2.2:** Schema reconciliation amendments.
- **v2.0 (May 1, 2026):** Eight scripts confirmed built and scheduled.
- **v1.0 (May 1, 2026):** Initial document.

— End of document —
