# Fortress Dashboard MCP Server

Connects Claude Desktop to your Fortress Dashboard via the MCP stdio transport.
19 read-only Tier 1 tools + 9 write Tier 2 tools (env-gated).

---

## Prerequisites

- Python 3.10+ on your local machine
- `mcp` and `httpx` packages installed
- Claude Desktop installed

---

## Installation

### 1. Install dependencies

```bash
pip install mcp httpx
```

### 2. Place the server file

Copy `fortress_mcp.py` to a permanent location on your laptop, e.g.:

```
~/fortress_mcp/fortress_mcp.py
```

### 3. Configure Claude Desktop

Open your Claude Desktop config file:

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Add the following to the `mcpServers` section (merge with existing content):

```json
{
  "mcpServers": {
    "fortress-dashboard": {
      "command": "python3",
      "args": ["/Users/yourname/fortress_mcp/fortress_mcp.py"],
      "env": {
        "FORTRESS_API_URL": "http://76.13.138.194:8080",
        "FORTRESS_API_TOKEN": "07f03fb6e664859ac5e8113eaf1102ac43a3cb785c581af756671072b426db21"
      }
    }
  }
}
```

**Replace `/Users/yourname/fortress_mcp/fortress_mcp.py`** with the actual path on your machine.

### 4. Restart Claude Desktop

Fully quit and relaunch Claude Desktop. The `fortress-dashboard` server should appear in the MCP tools panel.

---

## Enabling Write Tools (Tier 2)

Write tools are disabled by default. To enable them, add `FORTRESS_MCP_ALLOW_WRITES` to the env block:

```json
"env": {
  "FORTRESS_API_URL": "http://76.13.138.194:8080",
  "FORTRESS_API_TOKEN": "07f03fb6e664859ac5e8113eaf1102ac43a3cb785c581af756671072b426db21",
  "FORTRESS_MCP_ALLOW_WRITES": "1"
}
```

Write tools included: `add_journal_entry`, `add_alert`, `update_alert`, `delete_alert`,
`update_calendar`, `add_excluded_ticker`, `add_universe_ticker`, `update_settings_section`,
`trigger_ibkr_sync`.

---

## Tier 1 Tools (19 — always available)

| Tool | What it does |
|---|---|
| `get_briefing()` | Full portfolio briefing — start here |
| `get_positions(aggregated)` | Current option book |
| `get_candidates()` | IV crush candidate scanner |
| `get_calendar(window_days)` | Earnings calendar |
| `get_universe()` | Trading universe (tier1/tier2/macro/excluded) |
| `get_journal(limit)` | Recent trade journal entries |
| `get_alerts()` | Active profit-take / stop-loss alerts |
| `get_dp_floors_and_gex(ticker)` | DP floors and GEX walls |
| `get_chart_data(ticker, period)` | OHLCV candles + overlay levels |
| `evaluate_stop_loss(ticker, ...)` | Multi-signal stop-loss verdict §6 |
| `evaluate_roll(ticker, ...)` | Roll evaluation with top-3 candidates §5 |
| `evaluate_post_earnings(ticker, ...)` | Post-earnings decision matrix §10 |
| `validate_jade_lizard(...)` | Jade lizard credit-vs-width check §2.E |
| `get_spy_hedge_coverage()` | SPY hedge coverage check §2.D |
| `pretrade_check(ticker, strategy)` | Full pre-trade gate §3.3 → §4 → §7 |
| `get_capability(refresh)` | Greeks backend health probe |
| `get_ibkr_status()` | Legacy TWS gateway status |
| `get_settings()` | All runtime configuration |
| `get_quantdata_reports(report, date)` | QuantData report retrieval |

---

## Example Prompts

- *"Give me the full portfolio briefing."*
- *"Run a pre-trade check on AAPL for a short strangle."*
- *"Should I roll my TSLA position? It has 28 DTE."*
- *"Evaluate the post-earnings situation for NVDA — gap down 6%, IV crush 40%."*
- *"Is live Greeks coverage active right now?"*
- *"What are the DP floors and GEX walls for SPY?"*
- *"Check my SPY hedge coverage."*
- *"Validate a jade lizard: put at 180, call spread 200/205, credits 1.50 and 0.80."*

---

## Security Notes

- The token grants full read access to your portfolio data. Keep it private.
- The VPS port 8080 should be firewalled to your IP only (UFW rule recommended).
- Write tools are off by default. Enable only when needed and disable when done.
- The MCP server never executes trades.
