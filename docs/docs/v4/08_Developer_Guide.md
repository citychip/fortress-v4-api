# Fortress V4 — Developer Guide

**Version:** 4.0.0  
**Status:** Authoritative  
**Audience:** Developer setting up and maintaining the Fortress V4 codebase

---

## 1. Repository Structure

Three repositories, all under `github.com/citychip/`:

| Repo | Purpose | Tech Stack |
|---|---|---|
| `fortress-api` | FastAPI backend, four engines, scheduler | Python 3.11+, FastAPI, SQLAlchemy, Redis, APScheduler |
| `fortress-app` | React front-end | React 19, TypeScript, Tailwind 4, tRPC 11 |
| `fortress-mcp` | Claude MCP server (61 tools) | Python, MCP SDK |

All three repos are cloned to the same parent directory during local development.

---

## 2. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | Needed for fortress-api and fortress-mcp |
| Node.js | ≥ 20 LTS | Needed for fortress-app |
| Docker + Compose | Latest stable | For local services (MySQL, Redis, ibeam) |
| Git | Any modern | |
| MySQL client | 8.x | For running migration scripts manually |

---

## 3. Environment Variables

### fortress-api

```env
# Required
FORTRESS_API_TOKEN=your-secret-token          # Bearer token for all /api/* requests
DATABASE_URL=mysql+mysqlconnector://fortress:password@localhost:3306/fortress_db
REDIS_URL=redis://localhost:6379/0

# IBKR
IBKR_GATEWAY_URL=http://localhost:5000

# QuantData
QUANTDATA_AUTH_TOKEN=your-quantdata-token
QUANTDATA_INSTANCE_ID=your-instance-id

# Optional
FORTRESS_ENV=development                       # or production
LOG_LEVEL=INFO
SCHEDULER_ENABLED=true                         # Set false to disable APScheduler in dev
```

### fortress-mcp

```env
FORTRESS_API_URL=http://localhost:8080
FORTRESS_API_TOKEN=your-secret-token           # Must match fortress-api
FORTRESS_MCP_ALLOW_WRITES=0                    # Set 1 to enable Tier 2 write tools
FORTRESS_MCP_VERSION=4.0.0
```

### fortress-app

```env
VITE_API_BASE_URL=http://localhost:8080
VITE_TRPC_URL=http://localhost:8080/trpc
```

Store all secrets in `.env` files (gitignored). Never commit secrets to any repo.

---

## 4. Local Development Setup

### 4.1 Start Infrastructure Services (Docker Compose)

```yaml
# docker-compose.yml (in fortress-api root)
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: rootpassword
      MYSQL_DATABASE: fortress_db
      MYSQL_USER: fortress
      MYSQL_PASSWORD: password
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

  ibeam:
    image: voyz/ibeam:latest
    environment:
      IBEAM_ACCOUNT: ${IBKR_ACCOUNT}
      IBEAM_PASSWORD: ${IBKR_PASSWORD}
    ports:
      - "5000:5000"
    volumes:
      - ibeam_conf:/srv/ibeam/conf

volumes:
  mysql_data:
  ibeam_conf:
```

```bash
# Start all infrastructure
docker compose up -d mysql redis

# Verify
docker compose ps
```

### 4.2 fortress-api Setup

```bash
cd fortress-api

# Create virtualenv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy env file
cp .env.example .env
# Edit .env with your values

# Apply database migrations
alembic upgrade head

# Run migration scripts (V3 → V4, if migrating)
python scripts/migrate/migrate_positions.py
python scripts/migrate/migrate_alerts.py
python scripts/migrate/migrate_journal.py
python scripts/migrate/migrate_config.py
python scripts/migrate/migrate_ibkr_uploads.py

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

API will be live at `http://localhost:8080`. OpenAPI docs at `http://localhost:8080/docs`.

### 4.3 fortress-app Setup

```bash
cd fortress-app

# Install dependencies
npm install

# Copy env file
cp .env.example .env.local
# Edit with your values

# Start development server
npm run dev
```

App will be live at `http://localhost:5173`.

### 4.4 fortress-mcp Setup

```bash
cd fortress-mcp

# Create virtualenv
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env file
cp .env.example .env
# Edit with your values

# Test tool listing
python -c "from app.server import list_tools; print(list_tools())"
```

MCP server is invoked by Claude Desktop / Cowork via the configured `mcpServers` entry — it does not run as a persistent service.

---

## 5. Module Layout

### fortress-api

```
fortress-api/
├── app/
│   ├── main.py                 ← FastAPI app, CORS, auth middleware
│   ├── engines/
│   │   ├── position_engine.py  ← PositionEngine class
│   │   ├── market_engine.py    ← MarketEngine class
│   │   ├── alert_engine.py     ← AlertEngine + rule classes
│   │   └── execution_engine.py ← ExecutionEngine + PreTradeGate
│   ├── routers/
│   │   ├── positions.py
│   │   ├── market.py
│   │   ├── trade.py
│   │   ├── alerts.py
│   │   ├── journal.py
│   │   ├── config.py
│   │   ├── ibkr.py
│   │   ├── scheduler.py
│   │   ├── stream.py           ← SSE endpoint
│   │   └── portfolio.py        ← V4 new: beta, sector, capital efficiency
│   ├── models/
│   │   ├── db.py               ← SQLAlchemy models
│   │   └── schemas.py          ← Pydantic request/response schemas
│   ├── services/
│   │   ├── ibkr.py
│   │   ├── quantdata.py
│   │   └── redis_client.py
│   ├── scheduler/
│   │   ├── runner.py           ← APScheduler setup
│   │   └── scripts/
│   │       ├── premarket_scanner.py
│   │       ├── iv_crush.py
│   │       ├── position_monitor.py
│   │       ├── dark_pool_alert.py
│   │       ├── eod_review.py
│   │       ├── whale_flow.py
│   │       ├── max_pain.py
│   │       └── gex_oi.py
│   └── config.py               ← App settings (reads .env)
├── migrations/                  ← Alembic
│   ├── env.py
│   └── versions/
├── scripts/
│   └── migrate/                 ← V3 JSON → MySQL scripts
├── tests/
│   ├── unit/
│   │   ├── test_position_engine.py
│   │   ├── test_market_engine.py
│   │   ├── test_alert_engine.py
│   │   └── test_execution_engine.py
│   └── integration/
│       └── test_api_endpoints.py
├── requirements.txt
├── alembic.ini
├── .env.example
├── OPERATIONS_NOTES.md         ← V4_09_Operations_Notes.md content (committed here)
└── README.md
```

### fortress-app

```
fortress-app/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── router.tsx
│   ├── styles/
│   │   ├── tokens.css
│   │   ├── reset.css
│   │   └── app.css
│   ├── components/
│   │   ├── ui/                 ← Design system components
│   │   │   ├── Button.tsx
│   │   │   ├── KPICard.tsx
│   │   │   ├── DataTable.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── AlertBanner.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Toast.tsx
│   │   │   └── Chart.tsx
│   │   └── layout/
│   │       ├── Sidebar.tsx     ← 8-item nav (LOCKED)
│   │       └── TopBar.tsx
│   ├── pages/
│   │   ├── Dashboard.tsx
│   │   ├── MarketIntel.tsx
│   │   ├── Positions.tsx
│   │   ├── Trade.tsx
│   │   ├── Analysis.tsx
│   │   ├── Performance.tsx
│   │   ├── Earnings.tsx
│   │   └── Config.tsx
│   ├── hooks/
│   │   ├── useSSEStream.ts     ← SSE subscription hook
│   │   └── useToast.ts
│   ├── lib/
│   │   ├── trpc.ts             ← tRPC client setup
│   │   ├── format.ts           ← formatCurrency, formatDelta, formatGreek
│   │   └── auth.ts             ← Bearer token injection
│   └── types/
│       └── api.ts              ← Shared TypeScript types
├── tailwind.config.js
├── vite.config.ts
├── tsconfig.json
├── package.json
└── .env.example
```

### fortress-mcp

```
fortress-mcp/
├── app/
│   ├── server.py               ← MCP server entry point, tool registration
│   ├── client.py               ← HTTP client for fortress-api
│   ├── tools/
│   │   ├── tier1/              ← 47 read-only tools
│   │   ├── tier1_5/            ← 4 new analytics tools
│   │   └── tier2/              ← 10 write tools (write-guarded)
│   └── types.py                ← Shared response types
├── requirements.txt
├── .env.example
└── README.md
```

---

## 6. Database Migrations (Alembic)

```bash
# Create a new migration
alembic revision --autogenerate -m "add_dte_exception_table"

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Show migration history
alembic history

# Show current revision
alembic current
```

**Rule:** Every schema change must be an Alembic migration. Never alter the schema manually in production.

---

## 7. Testing

### Unit Tests

```bash
cd fortress-api
pytest tests/unit/ -v

# With coverage
pytest tests/unit/ --cov=app --cov-report=html
```

**Required unit test coverage (Phase 4 exit gate):**
- `test_position_engine.py`: `pcs_exposure()`, `beta_weighted_delta()`, `capital_efficiency()`
- `test_market_engine.py`: `earnings_volatility()`, `get_sector()`, session management
- `test_alert_engine.py`: `PCSCapRule` at 4/5, `WeeklyPacingRule` at 2/2
- `test_execution_engine.py`: All 12 pre-trade gate checks; blackout logic with specific dates

### Integration Tests

```bash
pytest tests/integration/ -v
# Requires running API + MySQL + Redis (use docker compose)
```

### MCP Tool Tests

```bash
cd fortress-mcp
pytest tests/ -v
# Tests call fortress-api; requires running API
```

---

## 8. Production Deployment

### First-Time Deployment

```bash
# On VPS as root

# 1. Create deploy directory
mkdir -p /var/www/fortress-v2
cd /var/www/fortress-v2

# 2. Clone repos
git clone https://github.com/citychip/fortress-api .
git clone https://github.com/citychip/fortress-app ../fortress-app-build

# 3. Install Python dependencies
pip install -r requirements.txt --break-system-packages

# 4. Set up env
cp .env.example .env
# Edit .env with production values

# 5. Apply migrations
alembic upgrade head

# 6. Build front-end
cd ../fortress-app-build
npm install
npm run build
cp -r dist/* /var/www/fortress-v2/app/static/

# 7. Configure systemd
# (See V4_09_Operations_Notes.md for unit file)
systemctl daemon-reload
systemctl enable fortress-dashboard
systemctl start fortress-dashboard

# 8. Configure NGINX
# Serve static at /, proxy /api/* to :8080, SSE headers on /api/stream
nginx -t && systemctl reload nginx
```

### Subsequent Deployments

```bash
cd /var/www/fortress-v2
git pull origin main
pip install -r requirements.txt --break-system-packages
alembic upgrade head

# If front-end changed:
cd ../fortress-app-build
git pull origin main
npm install
npm run build
cp -r dist/* /var/www/fortress-v2/app/static/

systemctl restart fortress-dashboard
```

### NGINX SSE Configuration

SSE requires specific NGINX directives — without these the stream will buffer and appear broken:

```nginx
location /api/stream {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;
    proxy_cache off;
    add_header X-Accel-Buffering no;
    proxy_read_timeout 86400s;
}

location /api/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Authorization $http_authorization;
}
```

---

## 9. Common Development Tasks

### Add a New API Endpoint

1. Create router function in `app/routers/<module>.py`
2. Add Pydantic response schema to `app/models/schemas.py`
3. Register router in `app/main.py`
4. Write unit test
5. Update `V4_05_MCP_Spec.md` if a new MCP tool is needed

### Add a New MCP Tool

1. Create tool file in `fortress-mcp/app/tools/tier1/` (or tier1_5/tier2/)
2. Register in `server.py`
3. If write tool: add write guard check at top of function
4. Add to tool count in `get_capability` handler
5. Update `V4_05_MCP_Spec.md`

### Add a New Alert Rule

1. Create rule class in `app/engines/alert_engine.py` extending `AlertRule`
2. Implement `evaluate(self, state: PortfolioState) -> Optional[Alert]`
3. Register in `AlertEngine.__init__`
4. Add unit test in `test_alert_engine.py`
5. Document in `V4_05_MCP_Spec.md` alert types table

### Modify Strategy Parameters

1. Update `Portfolio_Strategy_v3_7.md` first
2. Update the corresponding `config` table key default in `migrate_config.py`
3. Update Alembic migration if a new config key is added
4. Update V4_05_MCP_Spec.md and V4_06_Operations_Guide.md if thresholds changed

---

## 10. Dependency Versions (Pinned)

### Python (fortress-api, fortress-mcp)
```
fastapi==0.115.x
uvicorn==0.32.x
sqlalchemy==2.0.x
mysqlclient==2.2.x
redis==5.2.x
apscheduler==3.10.x
alembic==1.14.x
pydantic==2.10.x
httpx==0.28.x
```

### Node (fortress-app)
```
react@19.x
typescript@5.x
tailwindcss@4.x
@trpc/server@11.x
@trpc/client@11.x
vite@6.x
lucide-react@0.383.x
recharts@2.x
```

---

*Fortress V4 Developer Guide — keep this document updated as dependencies and procedures change.*
