# Fortress — Strategy Data Attributes & Sources
**v1.4 · 2026-06-19 · companion to Strategy v3.9 / Parapet v2.7**

> **v1.4 — Gateway-down integrity guard + source badge SHIPPED (2026-06-19):**
> New backend route `GET /api/data-integrity` (`options_analytics.py`) live-probes the
> IBKR CP Gateway (SPY snapshot) and returns an honest verdict — `live` (source `ibkr`),
> `fallback` (gateway down, ~15m-delayed yfinance answering), or `down` (nothing). It
> **bypasses the `staleness` field entirely**, closing the "frozen feed reads fresh" trap
> in the reliability ledger below. Parapet surfaces it as an always-visible top-bar badge
> (`SourceBadge.tsx`, green ● Live / amber ▲ Delayed / red ■ No data) that also tints the
> header and shows a "↻ Restart gateway" hint when degraded. Use this (or `get_ibkr_status`'s
> `active_backend`) as the gateway-up check — **never trust `staleness.state` alone.**
> Verified live: `{"integrity":"live","source":"ibkr","spot":746.94}`.

> **v1.3 — GEX/skew/liquidity NaN-500 fixed (2026-06-16):** `get_gex`, `get_vol_skew`,
> and `check_liquidity` could throw an uncatchable HTTP 500 on certain tickers (AAPL, TER, V).
> Root cause: yfinance chain rows carry NaN `openInterest`/`bid`/`ask`, and the
> `float(x or 0)` idiom returns NaN (NaN is truthy), which slipped past the `<= 0`
> guards and crashed Starlette's JSON serializer (`allow_nan=False`). Fixed in
> `options_analytics.py` with a NaN/Inf-safe `_f()` coercion + `math.isfinite` skip-guard.
> get_gex verified live on V and AAPL post-deploy. Use `_f()` for any new chain-parsing route.

> **v1.2 — IBKR-first migration DEPLOYED + verified live (2026-06-10, re-confirmed 2026-06-15):**
> spot for conditional alerts, option bid/ask (liquidity), ATM IV (iv-rank), and per-strike
> skew IV try IBKR CP Gateway first (`app/services/ibkr_marketdata.py`), silent yfinance
> fallback. Raw Yahoo IV column eliminated — all fallback paths BS-invert from lastPrice.
> Payloads carry `source`/`iv_source`. Verified live Jun 15: `iv_source: ibkr` on iv-rank,
> CP Gateway/iBeam authenticated (account U7453366, OPRA live) — this is the iBeam `web_api`
> path. ⚠ OAuth Stage 2 (ibind) STILL NOT connected: `test_ibkr_oauth.py` returns
> 401 "Invalid signature" at `ssodh/init` (Stage 1 LST works, Stage 2 pending IBKR activation —
> Priority 7 unresolved). `get_ibkr_status.oauth` reports `authenticated:true` but is MISLEADING
> (it doesn't test the Stage-2 brokerage handshake) — trust the script, not that field.

Truth chain: **IBKR** (account/positions/greeks) → **backend** (port 8081, computes/aggregates) → **Parapet** (displays) / **Claude MCP** (decides). Volatility & market structure come from **yfinance** (computed in `options_analytics.py`) and **QuantData** (flow/dark-pool only — see reliability notes).

---

## 1. Account & risk (entry sizing, pacing, concentration gates)

| Attribute | Strategy use | Origin | Backend route | Dashboard |
|---|---|---|---|---|
| Net Liq, Available, Excess Liq | Position sizing, margin floor checks | IBKR (cp-gateway/iBeam sync) | `/api/briefing` | Briefing stat bar |
| Portfolio Δ (raw) | Direction exposure | IBKR per-leg greeks, summed | `/api/briefing` | Briefing stat bar |
| β-weighted Δ | vs target (settings, ~320) | Backend: leg Δ × β × spot ratio | `/api/portfolio/beta` | Positions > Exposure |
| Θ/day, Vega | Income floor, vol exposure | IBKR greeks (OPRA) | `/api/briefing` | Briefing stat bar |
| Per-name & sector concentration | Max-name / max-sector caps, MSFT lock | Backend from positions | `/api/briefing`, `/api/portfolio/sector-exposure` | Briefing banner, Positions > Exposure |
| PCS spread count / notional vs cap | PCS exposure cap | Backend | `/api/portfolio/pcs-exposure` | Briefing banner |
| Pacing (entries/week) | Max 5 new entries per week | Backend counter | `/api/briefing` | Briefing stat bar |
| Unrealized / realized P&L | Profit-target exits | IBKR cost basis | `/api/pnl` (source of truth since v2.5) | Briefing strip, Positions > P&L |

## 2. Strategy thresholds (single source of truth: settings)

| Attribute | Values (current) | Origin | Consumed by |
|---|---|---|---|
| Δ watch / Δ act | 0.35 / 0.42 | `settings.json` — **Claude-managed via MCP** | `/api/settings` → `useSettings()` → position cards, triage |
| Roll window (DTE) | ≤ 21d | settings | Roll checks, card ⚑ badges |
| IVR entry gates | ≥ 25 required, ≥ 50 prime | settings | Candidates gate, Market board |
| Concentration caps, bid-ask tiers (5%/10%) | settings / Strategy §4 | settings + liquidity route | Pretrade checks |

Since Sprint 13 (#80), Parapet reads these live — no hardcoded copies.

## 3. Volatility (entry selection — the IVR engine)

| Attribute | Strategy use | Origin | Route | Reliability |
|---|---|---|---|---|
| ATM IV (per ticker) | Premium richness | **IBKR CP Gateway field 7633/7283** (real-time) → BS-inversion of yfinance lastPrice as fallback. Payload: `iv_source` | `/api/options/iv-rank/{t}` | ✅ `iv_source: ibkr` verified live Jun 10 |
| IV Rank | 25/50 entry gates | Backend: IV vs 52w HV range (`hv_proxy`) → own snapshot history after 60d (`iv_snapshots`), store: `data/iv_history.json` | same | ✅ proxy now, true rank by ~Sep 2026 |
| HV20, IV–HV spread | Premium vs realized edge | Backend price history (yfinance) | `/api/candidates` | ✅ |
| Vol skew (25d/10d), term structure | Tail-risk pricing, IV-crush timing (e.g. pre-PPI check) | **IBKR strike IV first** → BS-inversion fallback (raw Yahoo IV column eliminated). Payload: `source` | `/api/options/vol-skew/{t}` | ✅ `source: ibkr` verified live Jun 10 (0DTE dailies may fall back — correct) |
| Earnings implied move vs avg historical, crush risk | Earnings blackout / crush plays | Backend (chain + earnings history) | `/api/market/earnings-volatility/{t}` | ✅ |
| Bid-ask spread / liquidity grade | §4 quality filter (5% advisory / 10% block) | **IBKR live bid/ask first** → yfinance fallback. Payload: `source` | `/api/options/liquidity/{t}` | ✅ `source: ibkr` verified live Jun 10 — no more intraday flapping |

## 4. Market structure & regime (entry timing gate)

| Attribute | Strategy use | Origin | Route | Dashboard |
|---|---|---|---|---|
| Regime score + ENTRIES OPEN/BLOCKED | Hard entry gate | Backend composite (VIX, trend signals) | `/api/market-intelligence` | Briefing top banner |
| VIX | Regime input, vol context | yfinance/IBKR | `/api/briefing` | Stat bar |
| GEX walls, flip level | Strike selection near walls | yfinance strikes/OI + sane IV (`_row_iv`: banded column or BS-inversion; lazy IBKR ATM fallback) | `/api/options/gex/{t}` | Market drill-down |
| DP floors/ceilings | SPY support levels | **QuantData** (works) | `/api/chart/{t}/levels` | Briefing > Market Intel |
| SPY hedge coverage | Hedge sizing vs target band | Backend from positions | `/api/manage/spy_hedge_coverage` | Briefing > Market Intel |
| Order flow, max pain, OI, net flow | Confirmation signals | QuantData MCP — **via Claude only** | — | not in Parapet (by design) |

## 5. Calendar & events (blackouts, binary-event timing)

| Attribute | Strategy use | Origin | Route | Dashboard |
|---|---|---|---|---|
| Earnings dates, DTE, blackout state | Earnings blackout gate | Backend fetch (`fetch-earnings`) | `/api/calendar` | Market > Earnings Calendar, Briefing event horizon, Candidates gate |
| Macro events (CPI/PPI/FOMC) | Binary-event entry timing (e.g. AAPL post-PPI rule) | **FMP/FRED MCP via Claude** — not in backend | — | Briefing event horizon shows `intel.events` if backend ever provides them |

## 6. Trade lifecycle (manage/exit)

| Attribute | Strategy use | Origin | Route | Dashboard |
|---|---|---|---|---|
| Roll urgency (Δ + DTE) | Roll triggers | Backend from positions + settings | `/api/manage/roll_all` | Triage |
| Stop-loss verdict (price vs SMA200) | ACT/WATCH/SAFE signals | yfinance price history → SMA200 | `/api/manage/stop_loss_all` | Triage, sidebar badge |
| Pretrade PROCEED/BLOCKED | Final gate before stage | Backend composite of all gates | `/api/manage/pretrade_all` | Candidates |
| Capital efficiency % | Position recycling | Backend | `/api/portfolio/capital-efficiency` | Candidates Eff% |
| Strategy recommendation (PMCC/CSP/IC/…) | §2.5 selection framework | Backend regime + yield calc | `/api/options/strategy_metrics` | Candidates Rec |
| Pending orders + IBKR status | Approval workflow | Backend order store + IBKR | `/api/orders/pending` | Triage (read-only; approve via Claude MCP) |
| Forward P&L curve, breakevens, max P/L | Exit planning, IV-crush scenario | Backend BS model | `/api/options/forward-pnl` | Positions > Risk |

> ⚠ **`strategy_metrics` runs on placeholder vol (verified 2026-06-15).** Its IV/IVR/regime/DTE
> inputs returned hardcoded defaults (IV 30 / IVR 50 / regime "neutral" / DTE 999) for TER, AMD,
> META, V — NOT the live `get_iv_rank` values. Its estimated credit / POP / annualized-yield
> figures are therefore unreliable for sizing. Use it only for the regime-fit *strategy ranking*;
> for actual credit and POP, cross-check `get_iv_rank(ticker)` + a live chain (quantdata/massive).

---

## Reliability ledger (as of 2026-06-16)

| Source | Status |
|---|---|
| IBKR (account/positions/greeks) | ✅ authoritative; LIMITED MODE banner if sync >5m stale during RTH |
| **Gateway-down silent fallback** | ⚠ when CP Gateway drops, backend silently serves a FROZEN snapshot on `bs_yfinance` but `staleness.state` still reads "fresh" — data looks live while stuck at last good `synced_at`. `retry_ibkr_sync()` does NOT fix a 401/iBeam-auth failure (re-runs on stale fallback). Confirm with `get_ibkr_status` (look for `active_backend`); fix = iBeam restart (`docker restart cp-gateway` / Parapet Reconnect), not a sync retry. Hit + recovered 2026-06-15. **✅ Now guarded (2026-06-19):** `GET /api/data-integrity` live-probes the gateway and the Parapet top-bar badge shows live/fallback/down — the false-fresh staleness no longer hides a dead gateway |
| Pacing counter (entries/week) | ⚠ only increments on Fortress-staged orders — manual IBKR fills are NOT counted (showed 0/5 after 4 manual fills 2026-06-15). Track manual entries yourself |
| `get_gex` / `get_vol_skew` / `check_liquidity` routes | ✅ NaN-in-JSON 500 fixed 2026-06-16 (`_f()` NaN/Inf guard + finite-skip; was: AAPL/TER/V 500s on yfinance NaN OI/bid/ask). get_gex verified live V/AAPL. `check_liquidity` trap was latent (fires only on yfinance fallback when gateway down) — now guarded |
| **IBKR CP marketdata snapshot** (spot 31, bid/ask 84/86, IV 7633/7283 via `ibkr_marketdata.py`) | ✅ live primary for alert spot, liquidity, IV rank, skew (verified Jun 10). Computed IV fields need polling — handled. 0DTE dailies may not yield IV → falls back |
| yfinance lastPrice + price history | ✅ good (delayed ~15m) — fallback + structural source (expiries, strikes, OI, history) |
| yfinance IV column | ❌ never trusted — eliminated from ALL paths since v1.1 (sanity-banded or BS-inverted) |
| yfinance bid/ask | fallback only since v1.1 (was: flapping liquidity grades) |
| Conditional-alert spot evaluation | ✅ IBKR live via `chain.get_spot` (was: 15m delayed + 300s cache) |
| QuantData: dark pool, order flow, max pain, OI | ✅ works (via Claude / DP-levels route) |
| QuantData: `iv_rank` | ❌ ticker arg ignored upstream — replaced by backend route |
| QuantData: `exposure_by_strike`, `volatility_skew` | ❌ empty during market hours |
| FMP / FRED / Massive | ✅ via Claude MCP (earnings dates, macro calendar, options-data backup) |
