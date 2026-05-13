# Fortress Dashboard — Documentation

**Version:** 2.4 | **Updated:** May 13, 2026 | **Strategy:** Portfolio Strategy v3.6

---

## Reading Order

Read documents in the order below. Each builds on the previous.

| # | File | Purpose | When to Read |
|---|---|---|---|
| 1 | `01_Portfolio_Strategy_v3_6.md` | The rules. Delta targets, position sizing, stop-loss levels, roll criteria, earnings playbook. | Before any trade decision. |
| 2 | `03_Trading_Workflow_v2_8.md` | Daily operating procedure: pre-market, intraday, end-of-day. | Every trading day. |
| 3 | `05_Implementation_Status.md` | What is live, what is pending, known issues. | When onboarding or after a build session. |
| 4 | `07_MCP_Workflow_and_Prompts_v1_1.md` | Claude Desktop MCP prompts and workflows. | When using the MCP server. |
| 5 | `02_Trading_Dashboard_Build_Spec_v1_8.md` | Technical spec: API contract, schema, backend architecture. | When extending the dashboard. |
| 6 | `04_VPS_Implementation_Guide_v1_5.md` | VPS setup, Docker, systemd, deployment. | When setting up a new environment. |
| 7 | `08_Market_Intelligence_Skill_v1_0.md` | Agentic skill workflow combining GEX, Dark Pools, and portfolio constraints. | When using the Market Intelligence MCP tool. |
| 8 | `operations/03_Quick_Start_and_Daily_Cheatsheet.md` | One-page quick reference. | Daily. |
| 9 | `operations/04_Incident_Recovery_Playbook.md` | Recovery procedures for VPS down, gateway crash, data loss. | During incidents. |
| 10 | `review/10_Strategy_Review_Template.md` | Quarterly strategy review template. | End of each quarter. |
| 11 | `review/11_Todo_Backlog.md` | Prioritised backlog of pending work. | Before each build session. |

---

## MCP Server

The Fortress MCP server is built and ready to install in Claude Desktop.

Files are in `/home/ubuntu/fortress_mcp/`:

| File | Purpose |
|---|---|
| `fortress_mcp.py` | The MCP server — 29 tools (20 Tier 1 read-only including `get_market_intelligence`, 9 Tier 2 write) |
| `README.md` | Installation instructions for Claude Desktop |
| `claude_desktop_config_snippet.json` | Ready-to-paste config snippet with live token |

See `07_MCP_Workflow_and_Prompts_v1_1.md` for example prompts and workflows.

---

## Current Live State (May 9, 2026)

| Component | Status | Notes |
|---|---|---|
| Dashboard service | **Active** | `fortress-dashboard.service` on port 8080 |
| Bearer token auth | **Live** | All `/api/*` endpoints protected |
| Greeks backend | **Web API** | CP Gateway (voyz/ibeam) + OPRA. 25/26 positions with live Greeks. |
| Portfolio Greeks | **Live** | Δ +653, Θ -19.2, V -27.8 |
| Settings tab | **Live** | Five sections: Security (new), Strategy, Alerts, Technical, UI. |
| Security toggles | **Live** | `use_ibkr_web_api` and `use_quantdata` in Settings → Security. Amber banners + runtime guards. |
| MCP server | **Built** | `fortress_mcp.py` — 28 tools. Pending Claude Desktop install. |
| IB Gateway (legacy) | **Stopped** | Superseded by Web API. Container decommissioned. |

---

## Key Configuration

| Item | Location |
|---|---|
| API token | `/home/ubuntu/.fortress_api_token` |
| Systemd override | `/etc/systemd/system/fortress-dashboard.service.d/override.conf` |
| App config | `/home/ubuntu/Fortress_Dashboard/quant/fortress_config.json` |
| Positions | `/home/ubuntu/Fortress_Dashboard/quant/active_positions.json` |
| Backups | `/home/ubuntu/Fortress_Dashboard/quant/backups/` |
| MCP server | `/home/ubuntu/fortress_mcp/fortress_mcp.py` |

---

## Quick Commands

```bash
# Service management
sudo systemctl status fortress-dashboard
sudo systemctl restart fortress-dashboard
journalctl -u fortress-dashboard -f

# Health check (no auth required)
curl http://localhost:8080/api/health

# Authenticated API call
TOKEN=$(cat ~/.fortress_api_token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/briefing | python3 -m json.tool

# Trigger IBKR sync
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/ibkr/sync
```

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 2.5 | 2026-05-13 | Added Market Intelligence Skill with `/api/market-intelligence` endpoint and `get_market_intelligence` MCP tool. Added `08_Market_Intelligence_Skill_v1_0.md`. |
| 2.4 | 2026-05-13 | All UX/Automation improvements (A-M) deployed. Trade Reports tab added. Positions tab merged into Dashboard tab. Build Spec → v1.9.0. |
| 2.3 | 2026-05-09 | Security section added to Settings tab. `use_ibkr_web_api` and `use_quantdata` toggles with amber banners and runtime guards across all dependent routes. Build Spec → v1.8.2, Workflow → v2.8.1, VPS Guide → v1.5.1. |
| 2.2 | 2026-05-05 | MCP server built (28 tools). Bearer token live. Settings tab conflicts resolved. Deprecated docs deleted: MCP Proposal v1.1, IBKR Web API Migration Plan, all subfolder duplicates, archive folder. |
| 2.1 | 2026-05-05 | Web API backend live. CP Gateway (voyz/ibeam) active. All four Greeks live on 25/26 positions. |
| 2.0 | 2026-05-05 | Full doc restructure. 12-file package. Subfolder organisation. |
| 1.x | 2026-04-xx | Phase 1–4 build docs. |
