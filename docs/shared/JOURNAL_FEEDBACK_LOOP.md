# Trade-Outcomes Feedback Loop

**v1.0 · 2026-06-16 · backend + MCP + analytics · companion to Strategy §8 / WORKFLOW v2.7**

Turns closed trades into a "which setups actually pay?" report — the highest-ROI
profitability lever that needs no new external data, just disciplined capture of
your own results. **Advisory/learning layer; changes no trading rule.**

---

## 1. Why a sidecar store (not the prose journal)

The prose journal (`journal.json`) is the decision/audit log. Two problems make
it unsuitable for expectancy analysis:

1. **It lacks entry conditions.** Stored entries carry `strategy`, `realized_pnl`,
   `debit_credit`, `notes` — but **not** `ivr_at_entry` / `dte_at_entry` /
   `short_delta_at_entry`, which is exactly what you need to learn which setups
   pay.
2. **Schema drift (noted finding).** The MCP `add_journal_entry` tool sends
   `description`/`reasoning`/`framework_rules`/`outcome`/`tags`, but the stored
   entry shows `strategy`/`realized_pnl`/`debit_credit`/`outside_universe` — they
   don't line up. The backend journal route lives outside the repo mount, so it
   can't be patched from here without risk.

Rather than fight that, the feedback loop uses a **purpose-built sidecar**: one
structured record per *closed* trade, in a store the analytics owns. The prose
journal stays as-is. No fragile joins, no unreachable-file dependency.

## 2. Components (shipped 2026-06-16)

| Layer | What | Where |
|---|---|---|
| Backend | `GET/POST /api/trade-outcomes` (append-only store, summary, NaN-safe) | `options_analytics.py` (auto-deploys) |
| Store | `~/fortress-v4-api/data/trade_outcomes.json` (`{records:[…], updated_at}`) | created on first write |
| MCP | `log_trade_outcome(...)` (Tier-2 write) · `get_trade_outcomes()` (read) | `fortress_mcp` v4.8.0 |
| Analytics | `journal_analytics.py` → expectancy/win-rate by strategy + IVR/DTE/delta buckets | repo root |
| Test | `get_trade_outcomes` added to the NaN smoke-test | `tests/test_options_routes_nan.py` |

## 3. The record (capture at every close)

```
ticker (req) · strategy · realized_pnl (USD, − = loss) · exit_reason
ivr_at_entry · dte_at_entry · short_delta_at_entry      ← the bucketing keys
opened · closed · days_held · notes
```

`exit_reason` convention: `profit_target_50`, `rolled`, `21dte`, `stop_200sma`,
`earnings_close`, `expired_worthless`.

## 4. Usage

At each close, alongside the prose journal entry:

```
log_trade_outcome(ticker="V", strategy="PCS", realized_pnl=140,
  exit_reason="profit_target_50", ivr_at_entry=56, dte_at_entry=42,
  short_delta_at_entry=0.18, days_held=12)
```

Weekly (from the API dir):

```
python3 journal_analytics.py        # reads data/trade_outcomes.json by default
```

Output: overall + by-strategy + by-IVR/DTE/delta expectancy, win rate, profit
factor, avg win/avg loss. Use it to confirm (or refute) the rule defaults —
e.g. whether your higher-IVR / lower-delta entries really do carry the edge.

## 5. Deploy

```bash
bash deploy_data_sources.sh   # backend routes (+ runs the NaN smoke-test)
cp fortress_mcp_v452.py  →  fortress_mcp.py ; relaunch Claude Desktop   # v4.8.0 tools
# journal_analytics.py runs as-is from the API dir
```

## 6. Follow-ups

- **Seed history:** back-log recent closes via `log_trade_outcome` so the report
  has data immediately (otherwise it accrues going forward).
- **Long-term consolidation:** once the backend journal route is in reach, fold
  these fields into the `JournalEntry` model + reconcile the `add_journal_entry`
  schema drift, and this sidecar can merge back into the journal.

## 7. Auto-capture procedure (no manual number-typing)

Key insight: entry conditions must be captured **at open** — you can't recover
what IVR/delta were at entry after the fact. So auto-capture is two saved prompts,
each sourcing every field from the system (never estimated):

**At OPEN** — when a new position is approved:
> *"Snapshot entry conditions for {TICKER} {STRATEGY}: get_iv_rank, the short-leg
> DTE, and short-leg delta; record them in the journal note."*

Claude calls `get_iv_rank(ticker)`, reads short-leg DTE + delta from
`get_positions`, and writes them to the journal so they're retrievable at close.

**At CLOSE / roll** — when the position is closed:
> *"Log the {TICKER} close: realized P&L from IBKR, exit_reason {reason}, and the
> entry conditions snapshotted at open."*

Claude pulls realized P&L (`get_pnl` / IBKR), computes `days_held`, recalls the
at-open snapshot, and calls `log_trade_outcome(...)`. Nothing is typed by hand.

This is the discipline that makes the loop trustworthy: `realized_pnl` comes from
the broker, entry conditions from the at-open snapshot — so the expectancy tables
reflect reality, not memory.

## 8. Back-log status (2026-06-16)

No closed trades exist to back-log: `get_pnl_history` is empty, the journal shows
0 closed positions / $0 realized in 30d, and the entire book is open positions.
The loop accrues data going forward as positions close. (The 6/15 MSFT 310C sale
realized a gain but no system source carries its fill — log it manually if the
figure is known.)

## 9. Change log
- **v1.0 (2026-06-16):** Initial backend store + MCP tools (v4.8.0) + analytics
  repoint + smoke-test coverage.
