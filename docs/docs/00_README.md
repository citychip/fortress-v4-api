# Fortress Dashboard — Documentation

**Version:** 3.0 | **Updated:** May 18, 2026 | **Strategy:** Portfolio Strategy v3.7 | **Dashboard:** Fortress V3 (React/tRPC)

---

## Reading Order

Read documents in the order below. Each builds on the previous.

| # | File | Purpose | When to Read |
|---|---|---|---|
| 1 | `01_Portfolio_Strategy_v3_7.md` | The rules. Delta targets, position sizing, stop-loss levels, roll criteria, earnings playbook. | Before any trade decision. |
| 2 | `03_Trading_Workflow_v2_9.md` | Daily operating procedure: pre-market, intraday, end-of-day. | Every trading day. |
| 3 | `05_Implementation_Status.md` | What is live, what is pending, known issues. | When onboarding or after a build session. |
| 4 | `07_MCP_Workflow_and_Prompts_v1_3.md` | Claude Desktop MCP prompts and workflows. | When using the MCP server. |
| 5 | `02_Trading_Dashboard_Build_Spec_v2_0.md` | Technical spec: API contract, schema, backend architecture. | When extending the dashboard. |
| 6 | `04_VPS_Implementation_Guide_v1_6.md` | VPS setup, systemd, deployment, Fortress V3 React frontend. | When setting up a new environment or deploying a new build. |
| 7 | `08_Market_Intelligence_Skill_v1_1.md` | Agentic skill workflow combining GEX, Dark Pools, and portfolio constraints. | When using the Market Intelligence MCP tool. |
| 8 | `operations/03_Quick_Start_and_Daily_Cheatsheet.md` | One-page quick reference. | Daily. |
| 9 | `operations/04_Incident_Recovery_Playbook.md` | Recovery procedures for VPS down, gateway crash, data loss, QuantData credential expiry. | During incidents. |
| 10 | `review/10_Strategy_Review_Template.md` | Quarterly strategy review template. | End of each quarter. |
| 11 | `review/11_Todo_Backlog.md` | Prioritised backlog of pending work. | Before each build session. |

---

## Downloads

The following documents are published to GitHub for easy sharing:

| Document | GitHub Link |
|---|---|
| **Fortress V3 Presentation** (15-slide PDF) | [docs/Fortress_V3_Presentation.pdf](https://github.com/citychip/fortress-app/blob/main/docs/Fortress_V3_Presentation.pdf) |
| **Fortress V3 Sales Brochure** (7-page A4 PDF) | [docs/Fortress_V3_Sales_Brochure.pdf](https://github.com/citychip/fortress-app/blob/main/docs/Fortress_V3_Sales_Brochure.pdf) |
| **Portfolio Strategy v3.7** (Markdown) | [docs/Portfolio_Strategy_v3_7.md](https://github.com/citychip/fortress-app/blob/main/docs/Portfolio_Strategy_v3_7.md) |

To download: click the link → click the **Download raw file** (↓) button in the GitHub file viewer.

---

## MCP Server

The Fortress MCP server is built and installed in Claude Desktop.

Files are in `/home/ubuntu/fortress_mcp/`:

| File | Purpose |
|---|---|
| `fortress_mcp.py` | The MCP server — 29 tools (20 Tier 1 read-only including `get_market_intelligence`, 9 Tier 2 write) |
| `README.md` | Installation instructions for Claude Desktop |
| `claude_desktop_config_snippet.json` | Ready-to-paste config snippet with live token |

See `07_MCP_Workflow_and_Prompts_v1_3.md` for example prompts and workflows.

---

## Current Live State (May 18, 2026)

| Component | Status | Notes |
|---|---|---|
| **Fortress V3 Frontend** | **Active** | React 19 + Tailwind 4 + tRPC. Served on port 3000 via nginx. |
| **Python Backend (FastAPI)** | **Active** | `fortress-dashboard.service` on port 8080. |
| Bearer token auth | **Live** | All `/api/*` endpoints protected. |
| Greeks backend | **Web API** | CP Gateway (voyz/ibeam) + OPRA. |
| Settings — QuantData Credentials | **Live** | Update `auth_token` + `cookie` from the Settings tab without SSH. |
| Market Intelligence | **Live** | Sort dropdown, per-card refresh, metric tooltips (Sprint v7.1). |
| Candidates All-tab | **Live** | Shows all 19 universe tickers; actionable at top, monitoring below divider (Sprint v7.0). |
| MCP server | **Live** | `fortress_mcp.py` — 29 tools. Installed in Claude Desktop. |
| QuantData API | **Active** | Widget-UUID REST endpoints (no deprecated `tool/OPTIONS_*` calls). |

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
| QuantData MCP config | `/home/ubuntu/.quantdata-mcp/config.json` |
| Fortress V3 build | `/home/ubuntu/fortress-v2/` (source) → `/home/ubuntu/Fortress_Dashboard/app/static/` (deployed) |

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

# Re-run IV Crush workflow (after refreshing QuantData credentials)
cd /home/ubuntu/Fortress_Dashboard && source venv/bin/activate
python3 quant/workflow_05_iv_crush_report.py
```

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 3.0 | 2026-05-18 | Full update for Fortress V3 React/tRPC frontend. QuantData credentials manager in Settings. Sprint v7.0/7.1 features. chart.py invalid tool ID fix. All doc references updated to latest versions. Downloads section added. |
| 2.5 | 2026-05-13 | Added Market Intelligence Skill with `/api/market-intelligence` endpoint and `get_market_intelligence` MCP tool. |
| 2.4 | 2026-05-13 | All UX/Automation improvements (A-M) deployed. Trade Reports tab added. Positions tab merged into Dashboard tab. |
| 2.3 | 2026-05-09 | Security section added to Settings tab. `use_ibkr_web_api` and `use_quantdata` toggles. |
| 2.2 | 2026-05-05 | MCP server built (28 tools). Bearer token live. |
| 2.1 | 2026-05-05 | Web API backend live. CP Gateway (voyz/ibeam) active. |
| 2.0 | 2026-05-05 | Full doc restructure. 12-file package. |
