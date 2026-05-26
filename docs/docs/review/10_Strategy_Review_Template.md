# Strategy Review Template

**Version 1.0 — May 5, 2026**

Use this template for quarterly strategy reviews and post-event reviews (significant loss, significant win, market regime change, or any outcome that prompts a strategy question). The review process is defined in Strategy §15.5.

---

## Review Header

| Field | Value |
|---|---|
| Review type | Quarterly / Post-event |
| Review date | |
| Period covered | |
| Reviewer | (your name) |
| Strategy version at start of period | |
| Strategy version at end of period | |

---

## 1. Quantitative Performance

Pull from the Journal tab (30-day and period outcome metrics) and IBKR account statements.

### 1.1 P&L Summary

| Metric | This Period | Prior Period | Target / Benchmark |
|---|---|---|---|
| Total realized P&L (USD) | | | |
| Total unrealized P&L change (USD) | | | |
| Net Liquidity change (USD) | | | |
| Max drawdown (USD) | | | |
| Max drawdown (% of NetLiq) | | | |

### 1.2 Strategy-Level Performance

| Strategy | Positions opened | Positions closed | Win rate | Avg realized P&L per close | Notes |
|---|---|---|---|---|---|
| PMCC | | | | | |
| Diagonal | | | | | |
| Put Credit Spread | | | | | |
| Jade Lizard | | | | | |
| SPY Hedge | | | | | |
| Other | | | | | |

### 1.3 Framework Compliance

| Rule | Violations | Notes |
|---|---|---|
| Pacing (≤2 new positions/week) | | |
| Earnings blackout (10/14-day windows) | | |
| Delta at entry (0.20–0.25 short call) | | |
| DTE at entry (30–45 DTE short call) | | |
| Jade Lizard credit gate | | |
| Post-earnings IV crush floor (≥25%) | | |
| Stop-loss rule followed when ACT/ACT_IMMEDIATELY fired | | |
| Outside-universe entries documented | | |

### 1.4 MCP Prompt Patterns (from journal)

Pull from the MCP prompt: *"Pull the last 30 days of journal. What patterns do you see?"*

| Pattern | Observation |
|---|---|
| Most-used framework rules | |
| Average hold time by strategy | |
| Roll success rate (net credit achieved) | |
| Post-earnings playbook accuracy | |
| Decisions where verdict was overridden | |

---

## 2. Risk Review

### 2.1 Concentration

| Metric | Peak this period | Current | Threshold |
|---|---|---|---|
| MSFT concentration (% of NetLiq) | | | Accepted (offset by hedge) |
| Largest non-MSFT single name | | | <20% |
| Technology sector (% of NetLiq) | | | Flag if >80% |
| SPY hedge MV (USD) | | | $22K–$33K |

### 2.2 Beta-Weighted Risk

| Metric | Value | Notes |
|---|---|---|
| Portfolio beta-weighted delta (SPY-equivalent shares) | | |
| Hedge gap (USD) | | |
| Net raw delta | | |

### 2.3 Capital Efficiency

| Metric | Value | Notes |
|---|---|---|
| Buying power utilisation (%) | | |
| Idle capital (USD) | | |
| Lowest-ROC position | | |
| Highest-ROC position | | |

### 2.4 Worst-Case Scenarios

For each active PMCC position, answer: "If this stock fell 20% tomorrow, what would happen to the position?"

| Ticker | Current price | -20% price | LEAP MV impact (est.) | Short call impact (est.) | Net position impact |
|---|---|---|---|---|---|
| MSFT | | | | | |
| (add rows) | | | | | |

---

## 3. Strategy Review Questions

Answer each question. If the answer suggests a rule change, document the proposed change and the rationale.

### 3.1 Did the strategy perform as expected?

*What did you expect the strategy to do this period? What did it actually do? Where were the gaps?*

### 3.2 Were there any rule violations that led to better outcomes than the rule would have produced?

*If yes: is the rule wrong, or was the violation a one-time exception? If the rule is wrong, update Strategy v3.x.*

### 3.3 Were there any rule violations that led to worse outcomes?

*If yes: what enforcement mechanism would have prevented the violation? Is it a tool gap (add to backlog) or a discipline gap (note in journal)?*

### 3.4 Are there any strategies that should be added, removed, or modified?

*Based on this period's performance, market conditions, and the tool stack's capabilities.*

### 3.5 Are there any names that should be added to or removed from the universe?

*Based on liquidity, thesis health, or sector concentration goals.*

### 3.6 Did the tool stack surface the right information at the right time?

*Were there moments where you needed data the dashboard or MCP didn't have? Were there moments where the tools flagged something that turned out to be a false alarm? What should change?*

### 3.7 Did the MCP prompts work as documented?

*Any prompts that produced unexpected or unhelpful responses? Any new prompts that should be added to `mcp/09_MCP_Workflow_and_Prompts_v2.md`?*

---

## 4. Proposed Changes

For each proposed change, document:

| # | Document to change | Section | Current text | Proposed change | Rationale |
|---|---|---|---|---|---|
| 1 | | | | | |

---

## 5. Action Items

| # | Item | Owner | Due |
|---|---|---|---|
| 1 | Update Strategy v3.x with approved changes | (your name) | |
| 2 | Update backlog with new build items | (your name) | |
| 3 | Schedule next review | (your name) | |

---

## 6. Sign-Off

| Field | Value |
|---|---|
| Review completed | |
| Strategy version after review | |
| Next review scheduled | |
| Notes | |
