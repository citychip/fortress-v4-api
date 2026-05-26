# Fortress V4 — System Architecture

**Version:** 1.0  
**Date:** 2026-05-23  
**Status:** Design Draft — Pre-implementation  
**Relationship to V3:** Extends and supersedes the V3 architecture. V3 documentation (`docs/`) remains the operational reference until V4 is deployed.

---

## 1. System Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                                    │
│                                                                          │
│  fortress-app (React 19 + Tailwind 4 + tRPC 11)                          │
│                                                                          │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐  │
│  │ Dashboard │ │ Positions │ │   Trade   │ │  Market   │ │  Config   │  │
│  │ (Briefing │ │ (Greeks,  │ │ (Builder, │ │  Intel    │ │(Strategy, │  │
│  │  Alerts,  │ │  PnL, SL, │ │  Orders,  │ │ (GEX, DP, │ │ Settings, │  │
│  │  Pacing)  │ │  Beta, Sx)│ │  Scanner) │ │  Drift)   │ │ Scripts)  │  │
│  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘  │
│        └─────────────┴─────────────┴──────────────┴─────────────┘        │
│                              │                                            │
│             tRPC (HTTPS) + Server-Sent Events (SSE)                      │
└──────────────────────────────┼───────────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────────┐
│                           API GATEWAY                                     │
│                                                                          │
│  fortress-api (FastAPI :8080, behind nginx :443)                         │
│                                                                          │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌────────────┐ │
│  │ Position       │ │ Market         │ │ Alert          │ │ Execution  │ │
│  │ Engine         │ │ Engine         │ │ Engine         │ │ Engine     │ │
│  │                │ │                │ │                │ │            │ │
│  │ • Lifecycle    │ │ • Quotes       │ │ • Rule eval    │ │ • Risk chk │ │
│  │ • PnL calc     │ │ • Vol (IVR)    │ │ • Event queue  │ │ • Order SM │ │
│  │ • Greeks agg   │ │ • Chains       │ │ • Telegram     │ │ • Pre-trade│ │
│  │ • Conc track   │ │ • Exposure     │ │ • Audit log    │ │ • Recon    │ │
│  │ • Roll detect  │ │ • Fallbacks    │ │ • Session mgmt │ │            │ │
│  │ • PCS cap chk  │ │ • Session mgr  │ │                │ │            │ │
│  └───────┬────────┘ └───────┬────────┘ └───────┬────────┘ └──────┬─────┘ │
│          └─────────────────┴──────────────────┴────────────────┘         │
│                              │                                            │
│  ┌──────────────────────────▼─────────────────────────────────────────┐  │
│  │                         DATA LAYER                                   │  │
│  │  ┌────────────────────┐          ┌──────────────────────────────┐   │  │
│  │  │   MySQL 8           │          │       Redis 7                │   │  │
│  │  │  (persistent state) │          │  (cache + pub/sub + locks)   │   │  │
│  │  │                    │          │                              │   │  │
│  │  │ positions           │          │ market:quote:{ticker}        │   │  │
│  │  │ position_legs       │          │ market:greeks:{id}           │   │  │
│  │  │ orders              │          │ market:chain:{t}:{e}         │   │  │
│  │  │ alerts              │          │ market:exposure:{ticker}     │   │  │
│  │  │ audit_log           │          │ alert:queue (LPUSH)          │   │  │
│  │  │ journal             │          │ config.updated (pub/sub)     │   │  │
│  │  │ config              │          │                              │   │  │
│  │  │ earnings_calendar   │          │ Channels:                    │   │  │
│  │  │ market_snapshots    │          │   market.<ticker>            │   │  │
│  │  │ ibkr_sync_events    │          │   alert.<type>               │   │  │
│  │  │ ibkr_uploads        │          │   order.<ticker>             │   │  │
│  │  │ pnl_history         │          │   config.updated             │   │  │
│  │  │ market_bars (P5+)   │          │                              │   │  │
│  │  └────────────────────┘          │   session.expired.<provider> │   │  │
│  │                                  │   sync.completed             │   │  │
│  │                                  └──────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────── EXTERNAL CONNECTORS ──────────────────────────┐  │
│  │ IBKR Connector (voyz/ibeam REST primary, voyz/ibind WS optional)   │  │
│  │ QuantData Connector (widget-UUID REST endpoints)                   │  │
│  │ Provider Registry (yFinance fallback, extensible)                  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────────┐
          ▼                    ▼                        ▼
┌──────────────────┐ ┌──────────────────────┐ ┌────────────────────────────┐
│  fortress-mcp    │ │ quantdata-mcp (PyPI)  │ │ APScheduler (8 workflows)  │
│  (61 tools)      │ │ (19 tools)            │ │                            │
│                  │ │                       │ │  01_premarket_scanner      │
│  Tier 1 (47)     │ │ Claude Desktop        │ │  02_entry_scoring          │
│  Tier 2 (10)     │ │ → GEX/DEX/IV/flow     │ │  03_position_monitor       │
│  Tier 1.5 (new)  │ │                       │ │  04_iv_crush_report        │
│                  │ │                       │ │  05_eod_review             │
│  Claude Desktop  │ │                       │ │  06_dark_pool_alert        │
│  → portfolio     │ │                       │ │  07_whale_flow_report      │
│  → analytics     │ │                       │ │  08_max_pain_report        │
│  → execution q   │ │                       │ │                            │
└──────────────────┘ └──────────────────────┘ └────────────────────────────┘
```

---

## 2. The Four Engines

### 2.1 Position Engine (`app/engines/position/`)

**Responsibility:** Single source of truth for portfolio positions, PnL, Greeks, and strategy-level risk controls.

Replaces: `app/services/state.py`, JSON files for positions/alerts/journal

| Concern | Interface |
|---|---|
| Position normalization | `ingest_from_broker(broker_data) → list[Position]` |
| PnL (realized + unrealized) | `pnl(position_id) → PnLSnapshot` |
| Greeks aggregation | `greeks(position_id) → GreeksSnapshot` |
| Concentration tracking | `concentration() → ConcentrationReport` |
| PCS exposure (V4 new) | `pcs_exposure() → PCSExposure` — count + put notional vs €25K cap |
| Lifecycle state machine | `transition(position_id, event) → Position` |
| Roll detection | `scan_for_rolls() → list[RollCandidate]` (excludes `dte_exceptions` config entries) |
| Strategy inference | `infer_strategy(legs) → Strategy` |
| Beta-weighted delta (V4 new) | `beta_weighted_delta() → BetaSnapshot` — aggregated vs SPY |
| Capital efficiency (V4 new) | `capital_efficiency() → CapEfficiency` — ROC per position |

**Key Pydantic Models:**

```python
class PCSExposure(BaseModel):
    pcs_count: int                    # Current open PCS positions
    pcs_max: int                      # Config: strategy.max_pcs_count (default 5)
    put_notional_eur: float           # Total put-side notional at risk
    put_notional_cap_eur: float       # Config: strategy.max_put_notional_eur (default 25000)
    put_notional_pct: float           # put_notional_eur / net_liquidation
    gate_status: str                  # "ok" | "warn" | "at_cap" | "over_cap"

class BetaSnapshot(BaseModel):
    beta_weighted_delta: float        # Portfolio delta β-weighted to SPY
    spy_equivalent_shares: float      # Equivalent SPY share exposure
    hedge_gap: float                  # Positive = under-hedged vs target
    positions: list[BetaPosition]

class JournalEntry(BaseModel):
    id: UUID
    position_id: UUID | None
    entry_type: str                   # "open" | "close" | "roll" | "note" | "post_mortem"
    close_id: UUID | None             # FK → journal(id) — links closes to opens
    ticker: str
    action: str
    description: str
    reasoning: str
    framework_rules: list[str]        # e.g. ["§4", "§7"]
    realized_pnl: float | None
    iv_crush_realized: float | None   # Actual IV crush % at close
    dte_at_close: int | None          # DTE when position was closed
    created_by: str                   # "user" | "mcp" | "system"
    created_at: datetime
```

---

### 2.2 Market Engine (`app/engines/market/`)

**Responsibility:** Clean, normalized, deduped market data from any source.

Replaces: `app/services/bs_fallback.py`, `app/services/chain.py`, scattered QuantData calls

| Concern | Interface |
|---|---|
| Quotes | `get_quote(ticker) → Quote` |
| Vol profile | `get_vol_profile(ticker) → VolProfile` |
| Option chains | `get_chain(ticker, expiry) → OptionChain` |
| Exposure (GEX/DEX/VEX) | `get_exposure(ticker) → ExposureData` |
| Sector classification | `get_sector(ticker) → str` — GICS via yfinance |
| Earnings volatility (V4 new) | `get_earnings_volatility(ticker) → EarningsVolatility` |
| Session management | `ensure_session(provider) → bool` — QuantData auth refresh |
| Fallback orchestration | `get_with_fallback(ticker, sources) → T` |

**Source Priority:**

```yaml
providers:
  quotes:
    primary: ibkr          # CP Gateway real-time
    fallback: [quantdata, yfinance]
  options:
    primary: quantdata     # Full chain via widget-UUID
    fallback: [ibkr, bs_yfinance]
  exposure:
    primary: quantdata     # GEX/DEX — only source
  sector:
    primary: yfinance      # GICS sector (24h TTL)
```

**Session Management (resolves backlog P-01):**

When QuantData returns 401/auth error:
1. Emit `session.expired.quantdata` event to audit_log + Redis pub/sub
2. Send Telegram notification with link to Settings → QuantData Credentials
3. Degrade gracefully to yfinance fallback during the gap

---

### 2.3 Alert Engine (`app/engines/alert/`)

**Responsibility:** Event-driven alert evaluation. All rules implement Strategy v3.7 thresholds exactly.

Replaces: `app/services/stop_loss.py`, `app/services/roll.py`, `app/services/playbook.py`

**Built-in Rule Classes:**

| Rule | Strategy Ref | Threshold |
|---|---|---|
| `StopLossRule` | §6 | MV drawdown ≥50% from peak, SMA200 + DP floor breach |
| `ProfitTakeRule` | §5 | 50% of max profit achieved |
| `DTERollRule` | §5 | DTE < 21 (urgent: < 14); skips `dte_exceptions` config |
| `IVRankCrossRule` | §4 | IVR crosses 30 (entry gate) or 70 (high vol) |
| `EarningsProximityRule` | §4 | 10 days for PCS; 14 days for LEAPS/PMCC |
| `DeltaBreachRule` | §5 | Delta > 0.35 (critical), > 0.30 (watch) |
| `ConcentrationRule` | §7 | >12% warn, >15% act, MSFT >50% critical |
| `SPYHedgeCheckRule` | §2.D | Hedge MV < $22K USD |
| `PCSCapRule` | §7 new | PCS count ≥ 5 OR put notional ≥ €25K |
| `WeeklyPacingRule` | §7 new | Entries this week ≥ 2 — advisory WARN |
| `VIXRegimeRule` | config | VIX > 25 warn, > 35 halt new entries (matches `V4_06_Operations_Guide.md` §3.2) |
| `EarningsPMCCRule` | §10 | Post-earnings IV crush signal |

**Evaluation Cycle (every 5 minutes during market hours):**
```python
async def evaluate_all_alerts():
    positions = await position_engine.get_all_open()
    market = await market_engine.get_portfolio_state()
    for rule in alert_registry.all():
        for position in positions:
            alert = rule.evaluate(position, market)
            if alert:
                await alert_engine.enqueue(alert)
```

---

### 2.4 Execution Engine (`app/engines/execution/`)

**Responsibility:** Safe order submission with risk checks, pre-trade validation, and audit trail.

Replaces: `app/services/ibkr_web/orders.py`, `scripts/pre_trade_gate.py`

**Pre-trade Gate Checks (Strategy v3.7 compliance):**

```python
class PreTradeGate:
    def validate(self, order: Order, portfolio: PortfolioState) -> ValidationResult:
        checks = [
            self._check_hard_exclusion(order),           # §3.3
            self._check_earnings_blackout(order),        # §4 — PCS 10d, LEAP 14d
            self._check_dte_exception(order),            # config.dte_exceptions
            self._check_concentration(order, portfolio), # §7
            self._check_pcs_cap(portfolio),              # §7 — max 5 PCS
            self._check_put_notional(order, portfolio),  # §7 — max €25K
            self._check_delta_limits(order, portfolio),  # §5
            self._check_pacing(order),                   # §7 — max 2/week
            self._check_ivr_gate(order),                 # §4 — IVR ≥ 25
            self._check_vix_regime(portfolio),           # §4 — VIX < 35
            self._check_spy_hedge(portfolio),            # §2.D
            self._check_leap_coverage(order, portfolio), # §2.A — 1:1 ratio
        ]
        failures = [c for c in checks if c.failed]
        return ValidationResult(order=order, passed=not failures, failures=failures)
```

**Order State Machine:**
```
draft → pending → approved → submitted → filled
  │         │                    │
  │         │                    └→ rejected (broker)
  │         └→ rejected (risk)
  └→ cancelled
```

---

## 3. Database Schema

### 3.1 Core Tables

```
positions
├── id              UUID PK
├── ticker          VARCHAR(10)
├── strategy        ENUM('PMCC','PCS','JADE_LIZARD','LEAPS','DIAGONAL','SPY_HEDGE','CC','STOCK','MIXED')
├── state           ENUM('open','monitored','rolling','closed')  -- NOTE: V3 JSON used 'status'; Alembic 001_initial_schema maps 'status' → 'state'
├── net_market_value DECIMAL(12,2)
├── net_pnl         DECIMAL(12,2)
├── realized_pnl    DECIMAL(12,2)
├── unrealized_pnl  DECIMAL(12,2)
├── aggregated_delta DECIMAL(8,4)
├── aggregated_gamma DECIMAL(8,4)
├── aggregated_theta DECIMAL(8,4)
├── aggregated_vega  DECIMAL(8,4)
├── concentration_pct DECIMAL(5,2)
├── alert_state     ENUM('safe','watch','approaching','broken','critical_gamma','hedge','unknown')
├── dte             INT NULL
├── notes           TEXT
├── created_at      TIMESTAMP
└── updated_at      TIMESTAMP ON UPDATE

position_legs
├── id              UUID PK
├── position_id     UUID FK → positions(id) CASCADE DELETE
├── symbol          VARCHAR(10)
├── right           ENUM('C','P') NULL   -- NULL for stock legs
├── strike          DECIMAL(10,2) NULL
├── expiry          DATE NULL
├── qty             INT
├── avg_cost        DECIMAL(10,2)
├── market_value    DECIMAL(10,2)
├── current_delta   DECIMAL(6,4)
├── current_gamma   DECIMAL(6,4)
├── current_theta   DECIMAL(8,4)
├── current_vega    DECIMAL(8,4)
├── sec_type        ENUM('OPT','STK','FUT') DEFAULT 'OPT'  -- for OPRA test filter
└── ibkr_contract_id VARCHAR(50)

journal
├── id              UUID PK
├── position_id     UUID FK → positions(id) NULL
├── close_id        UUID FK → journal(id) NULL   -- V4 NEW: links closes to opens
├── entry_type      ENUM('open','close','roll','note','post_mortem','strategy_change')
├── ticker          VARCHAR(10)
├── action          VARCHAR(100)
├── description     TEXT
├── reasoning       TEXT
├── framework_rules JSON                          -- e.g. ["§4", "§7"]
├── realized_pnl    DECIMAL(12,2) NULL
├── iv_crush_realized DECIMAL(5,2) NULL           -- V4 NEW: actual IV crush % at close
├── dte_at_close    INT NULL                       -- V4 NEW: DTE when closed
├── created_by      ENUM('user','mcp','system')
└── created_at      TIMESTAMP

config
├── id              UUID PK
├── section         VARCHAR(50)
├── key             VARCHAR(100)
├── value           JSON
├── updated_at      TIMESTAMP ON UPDATE
└── UNIQUE (section, key)

-- Key config entries for V4:
-- strategy.max_pcs_count              = 5
-- strategy.max_put_notional_eur       = 25000
-- strategy.leap_entry_blackout_days   = 14
-- strategy.pcs_earnings_blackout_days = 10
-- strategy.dte_exceptions             = [{ticker,strike,expiry}]  -- suppress roll alerts
-- security.ibkr_auto_sync_enabled     = true
-- security.ibkr_auto_sync_interval_min = 15
```

### 3.2 Analytics Tables

```
pnl_history
├── id              BIGINT AUTO_INCREMENT PK
├── date            DATE UNIQUE
├── net_liquidation DECIMAL(12,2)
├── day_pnl         DECIMAL(12,2)
├── realized_pnl    DECIMAL(12,2)
├── unrealized_pnl  DECIMAL(12,2)
├── available_funds DECIMAL(12,2)
├── portfolio_delta DECIMAL(10,2)
├── spy_hedge_mv    DECIMAL(10,2) NULL
└── source          ENUM('ibkr_sync','system_snapshot')

audit_log
├── id              UUID PK
├── timestamp       TIMESTAMP
├── actor           VARCHAR(50)     -- user | scheduler | mcp | api
├── action          VARCHAR(50)     -- order_submit | alert_fire | config_change | sync | ...
├── entity_type     VARCHAR(50)     -- position | order | config | alert
├── entity_id       UUID
├── old_state       JSON NULL
├── new_state       JSON
└── reason          TEXT NULL       -- "delta 0.38 > threshold 0.35"
```

### 3.3 Redis Key Patterns

| Key | TTL | Purpose |
|---|---|---|
| `market:quote:{ticker}` | 60s | Last quote |
| `market:greeks:{position_id}` | 30s | Live Greeks from IBKR |
| `market:chain:{ticker}:{expiry}` | 300s | Full option chain |
| `market:exposure:{ticker}` | 3600s | GEX/DEX/CEX/VEX walls |
| `market:sector:{ticker}` | 86400s | GICS sector classification |
| `market:earnings_vol:{ticker}` | 3600s | Implied vs historical move |
| `session:quantdata` | Session TTL | QuantData auth state |
| `alert:queue` | — | Redis LPUSH/BRPOP queue |

---

## 4. API Surface

### 4.1 Preserved Endpoints (backward-compatible with current dashboard)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | No auth |
| GET | `/api/briefing` | Portfolio summary + actions |
| GET | `/api/positions` | All positions with Greeks |
| POST | `/api/positions/sync` | Trigger IBKR sync |
| GET | `/api/alerts` | Active alerts |
| POST | `/api/alerts/ack/{id}` | Acknowledge alert |
| GET | `/api/candidates` | Pre-market candidates |
| GET | `/api/market-intelligence` | GEX/DP/Net Drift per ticker |
| GET | `/api/chart/{ticker}` | DP floors + GEX overlays |
| GET | `/api/config` | Full config |
| PATCH | `/api/config/{section}` | Update config section |
| GET | `/api/ibkr/status` | IBKR Gateway connection |
| GET | `/api/ibkr/capability` | Greeks coverage |
| GET | `/api/stream` | SSE event stream |

### 4.2 New V4 Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/api/positions/{id}` | Single position + legs |
| GET | `/api/orders` | Order queue with state |
| POST | `/api/orders` | Submit order (draft) |
| POST | `/api/orders/{id}/approve` | Approve order |
| GET | `/api/pnl` | PnL summary |
| GET | `/api/pnl/history` | Historical daily PnL |
| GET | `/api/audit` | Audit log (paginated) |
| GET | `/api/earnings` | Earnings calendar |
| GET | `/api/market/quote/{ticker}` | Cached quote with fallback |
| GET | `/api/market/vol-surface/{ticker}` | Vol surface (skew + term) |
| GET | `/api/manage/portfolio_beta` | **Tier 1.5** — Beta-weighted delta |
| GET | `/api/manage/sector_exposure` | **Tier 1.5** — GICS sector breakdown |
| GET | `/api/manage/capital_efficiency` | **Tier 1.5** — ROC per position |
| GET | `/api/manage/earnings_volatility/{ticker}` | **Tier 1.5** — Implied vs historical |

### 4.3 SSE Event Types

```
GET /api/stream

Events:
  market_update    — {ticker, type:"quote", price, timestamp}
  alert            — {rule, ticker, severity:"INFO|WARN|ACT|CRITICAL", message}
  order_update     — {order_id, state, ticker}
  session_expired  — {provider, action:"refresh_credentials"}
  sync_completed   — {sync_id, positions_synced, errors:[]}
  heartbeat        — {timestamp}
```

---

## 5. Module Layout

```
fortress-api/
├── app/
│   ├── main.py                   # FastAPI + lifespan + SSE + APScheduler
│   ├── config.py                 # Settings from .env (secrets only)
│   ├── models/                   # Pydantic models (request/response)
│   │   ├── position.py           # Position, Leg, PortfolioState, PnLSnapshot
│   │   ├── order.py              # Order, OrderRequest, ValidationResult
│   │   ├── alert.py              # Alert, AlertRule, AlertResult
│   │   ├── market.py             # Quote, OptionChain, VolProfile, ExposureData
│   │   ├── analytics.py          # BetaSnapshot, SectorExposure, CapEfficiency, EarningsVol
│   │   └── common.py             # PaginatedResponse, HealthResponse
│   ├── engines/
│   │   ├── position/
│   │   │   ├── service.py        # PositionEngine class
│   │   │   ├── pnl.py            # PnL calculations
│   │   │   ├── greeks.py         # Greeks aggregation
│   │   │   ├── concentration.py  # Concentration analysis
│   │   │   ├── pcs_exposure.py   # PCS count + put notional (V4 new)
│   │   │   ├── beta_weights.py   # Beta-weighted delta (V4 new)
│   │   │   └── capital_eff.py    # Capital efficiency (V4 new)
│   │   ├── market/
│   │   │   ├── service.py        # MarketEngine class
│   │   │   ├── ingest.py         # Realtime + batch ingestors
│   │   │   ├── normalizer.py     # Dedup, monotonic timestamps, outlier reject
│   │   │   ├── session_manager.py# QuantData auth state + Telegram fallback
│   │   │   ├── vol_profile.py    # IV skew + term structure
│   │   │   ├── earnings_vol.py   # Implied vs historical move (V4 new)
│   │   │   └── providers/
│   │   │       ├── base.py       # MarketDataProvider ABC
│   │   │       ├── ibkr.py       # voyz/ibeam REST + optional ibind WS
│   │   │       ├── quantdata.py  # QuantData widget-UUID endpoints
│   │   │       └── yfinance.py   # Fallback (delayed, sector, earnings history)
│   │   ├── alert/
│   │   │   ├── service.py        # AlertEngine class
│   │   │   ├── event_queue.py    # Redis LPUSH/BRPOP
│   │   │   ├── rules/
│   │   │   │   ├── base.py       # AlertRule ABC, AlertRuleRegistry
│   │   │   │   ├── stop_loss.py  # §6
│   │   │   │   ├── profit_take.py# §5
│   │   │   │   ├── dte_roll.py   # §5 — respects dte_exceptions config
│   │   │   │   ├── iv_rank.py    # §4
│   │   │   │   ├── earnings.py   # §4 — separate PMCC/PCS blackout windows
│   │   │   │   ├── delta.py      # §5
│   │   │   │   ├── concentration.py # §7
│   │   │   │   ├── spy_hedge.py  # §2.D
│   │   │   │   ├── pcs_cap.py    # §7 — PCS count + put notional (V4 new)
│   │   │   │   ├── pacing.py     # §7 — weekly entry cap (V4 new)
│   │   │   │   └── vix_regime.py # config
│   │   │   └── notifiers/
│   │   │       ├── base.py       # Notifier ABC
│   │   │       └── telegram.py   # Telegram Bot API
│   │   └── execution/
│   │       ├── service.py        # ExecutionEngine + order state machine
│   │       ├── pre_trade_gate.py # All Strategy v3.7 pre-trade checks
│   │       ├── risk_checks.py    # Concentration, delta, pacing, PCS cap checks
│   │       ├── reconciler.py     # Post-trade reconciliation
│   │       └── ibkr_adapter.py   # IBKR submit (ibeam REST → optional ibind WS)
│   ├── api/                      # FastAPI routes
│   │   ├── deps.py               # Auth, DB sessions, engine access
│   │   ├── middleware.py         # Auth + logging + rate limiting
│   │   ├── positions.py
│   │   ├── orders.py
│   │   ├── alerts.py
│   │   ├── market.py             # includes earnings_volatility endpoint
│   │   ├── stream.py             # SSE
│   │   ├── briefing.py
│   │   ├── candidates.py
│   │   ├── chart.py
│   │   ├── config.py
│   │   ├── audit.py
│   │   ├── pnl.py
│   │   ├── journal.py
│   │   ├── analytics.py          # V4 new: portfolio_beta, sector, cap_eff
│   │   └── health.py
│   └── db/
│       ├── session.py            # SQLAlchemy async session factory
│       ├── models.py             # ORM models (matches schema above)
│       └── migrations/           # Alembic
│           └── versions/
│               ├── 001_initial_schema.py
│               ├── 002_journal_close_id.py   # V4 addition
│               ├── 003_ibkr_uploads.py        # V4 — migrate ibkr_uploads.json
│               └── 004_market_bars.py        # Phase 5+ — deferred, not in Phase 4 scope
├── scripts/
│   ├── migrate_json_to_db.py     # One-time JSON → MySQL migration
│   ├── workflow_01_premarket_scanner.py
│   ├── workflow_02_entry_scoring.py
│   ├── workflow_03_position_monitor.py
│   ├── workflow_04_iv_crush_report.py
│   ├── workflow_05_eod_review.py
│   ├── workflow_06_dark_pool_alert.py
│   ├── workflow_07_whale_flow_report.py
│   ├── workflow_08_max_pain_report.py
│   └── workflow_00_premarket.py          # 09:00 ET — pre-market data pull + briefing prep
├── quant/                        # Legacy (DEPRECATED → keep for Phase 3→4 transition)
│   ├── master_orchestrator.py
│   └── ...
├── tests/
│   ├── test_engines/
│   ├── test_api/
│   └── conftest.py               # Fixtures: test DB, Redis mock, IBKR mock, QD mock
├── pyproject.toml
├── Dockerfile
└── .env.example
```

---

## 6. Deployment

### 6.1 Docker Compose (Development)

```yaml
services:
  api:
    build: ./fortress-api
    ports: ["8080:8080"]
    depends_on: [mysql, redis]
    env_file: .env

  frontend:
    build: ./fortress-app
    ports: ["3001:3001"]
    depends_on: [api]

  mysql:
    image: mysql:8.0
    volumes: [mysql_data:/var/lib/mysql]

  redis:
    image: redis:7-alpine
    command: --appendonly yes --maxmemory 256mb

  ibkr-gateway:
    image: voyz/ibeam:latest
    ports: ["5000:5000", "5001:5001"]
```

### 6.2 Production (VPS)

Current production uses systemd and continues to do so. Docker Compose manages dev parity and makes deployments reproducible. The `fortress-dashboard.service` systemd unit is not removed — it is the rollback target.

**nginx proxy config:** Terminate HTTPS at nginx, forward `/api/*` to FastAPI on 8080, serve static React from `/var/www/fortress-v2/`.

---

## 7. Source-of-Truth Hierarchy

Per Strategy v3.7 §2.5 — this governs all data conflicts:

| Domain | Source | Notes |
|---|---|---|
| Position state, P&L, Greeks, margin | IBKR (live) | Trade-level decisions |
| Technical analysis | TradingView charts | No TA without a TradingView chart |
| Market structure (IV, GEX, DP, OI) | QuantData | Daily reports authoritative |
| Live option chain | IBKR option chain | Entry decision strikes |
| Earnings dates | `earnings_blocklist.json` / `earnings_calendar` table | Cross-checked against company IR |
| Active book composition | Position Engine / MySQL `positions` table | Source after V4 migration |
| Decision rules | Portfolio Strategy v3.7 | If tool contradicts strategy, strategy wins |

---

*Document owner: Fortress V4 project*  
*Basis: `260523documentation/00_V3_ARCHITECTURE.md` + `Investment2026/0511/recommendations.md` + `Investment2026/Docs2/fortress_docs/strategy/01_Portfolio_Strategy_v3_6.md`*
