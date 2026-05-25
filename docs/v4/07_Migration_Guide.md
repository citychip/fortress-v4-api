# Fortress V4 — Migration Guide
## JSON Files → MySQL 8

**Version:** 4.0.0  
**Status:** Authoritative  
**Audience:** Developer executing the V3 → V4 migration

---

## 1. Overview

Fortress V3 stored all persistent state in five JSON files. Fortress V4 replaces these with MySQL 8. This guide covers the migration of each file, the rollback procedure, and validation steps.

**Total JSON files to migrate:**

| JSON File | MySQL Destination | Notes |
|---|---|---|
| `active_positions.json` | `positions` + `position_legs` tables | Flatten leg arrays |
| `alerts.json` | `alerts` table | Straight mapping |
| `journal.json` | `journal` table | Add `close_id` backfill (best-effort) |
| `fortress_config.json` | `config` table | Key-value pairs; add V4 defaults |
| `ibkr_uploads.json` | `ibkr_uploads` table | Straight mapping |

**Pre-migration checklist:**
- [ ] Full VPS backup taken
- [ ] JSON files backed up to `/var/backups/fortress-json-pre-v4/`
- [ ] MySQL 8 installed and secured
- [ ] V4 schema applied (`alembic upgrade head`)
- [ ] Fortress Dashboard service stopped (`systemctl stop fortress-dashboard`)

---

## 2. Pre-Migration: Backup

```bash
# Stop service
systemctl stop fortress-dashboard

# Backup JSON files
# NOTE: JSON files live in the Fortress_Dashboard app directory, NOT /var/www/fortress-v2/data/
# Verify the actual path first:
ls /home/ubuntu/Fortress_Dashboard/data/*.json 2>/dev/null || ls /home/ubuntu/Fortress_Dashboard/*.json 2>/dev/null

mkdir -p /var/backups/fortress-json-pre-v4
cp /home/ubuntu/Fortress_Dashboard/data/*.json /var/backups/fortress-json-pre-v4/
ls -la /var/backups/fortress-json-pre-v4/

# Full database backup (if any existing DB state)
mysqldump -u fortress -p fortress_db > /var/backups/fortress-pre-v4.sql 2>/dev/null || true

# Record timestamp
echo "Migration started: $(date -u)" > /var/backups/migration-log.txt
```

---

## 3. Schema Reference (Targets)

### 3.1 `positions` table

```sql
CREATE TABLE positions (
  id          CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  ticker      VARCHAR(10) NOT NULL,
  strategy    ENUM('PMCC','PCS','JL','HEDGE','OTHER') NOT NULL,
  -- NOTE: V4 Architecture uses 'state' (not 'status') with values open/monitored/rolling/closed
  -- This migration guide uses 'status' for backward-compat during migration.
  -- Alembic migration 001_initial_schema.py renames this column to 'state' with the V4 enum.
  state       ENUM('open','monitored','rolling','closed') DEFAULT 'open',
  opened_at   DATETIME NOT NULL,
  closed_at   DATETIME NULL,
  notes       TEXT NULL,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 3.2 `position_legs` table

```sql
CREATE TABLE position_legs (
  id             CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  position_id    CHAR(36) NOT NULL REFERENCES positions(id),
  leg_type       ENUM('call','put','stock') NOT NULL,
  action         ENUM('buy','sell') NOT NULL,
  expiry         DATE NOT NULL,
  strike         DECIMAL(10,2) NOT NULL,
  quantity       INT NOT NULL,
  cost_basis     DECIMAL(10,4) NOT NULL,
  ibkr_con_id    VARCHAR(20) NULL,
  created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3.3 `alerts` table

```sql
CREATE TABLE alerts (
  id          CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  ticker      VARCHAR(10) NOT NULL,
  type        VARCHAR(50) NOT NULL,
  threshold   DECIMAL(12,4) NULL,
  condition   VARCHAR(20) NULL,
  message     TEXT NOT NULL,
  triggered   BOOLEAN DEFAULT FALSE,
  triggered_at DATETIME NULL,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 3.4 `journal` table

```sql
CREATE TABLE journal (
  id                   CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  ticker               VARCHAR(10) NOT NULL,
  strategy             VARCHAR(20) NULL,
  action               VARCHAR(20) NOT NULL,
  notes                TEXT NULL,
  position_id          CHAR(36) NULL REFERENCES positions(id),
  close_id             CHAR(36) NULL REFERENCES journal(id),  -- V4 NEW
  iv_crush_realized    DECIMAL(5,2) NULL,                    -- V4 NEW
  dte_at_close         INT NULL,                             -- V4 NEW
  created_at           DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3.5 `config` table

```sql
CREATE TABLE config (
  key         VARCHAR(100) PRIMARY KEY,
  value       TEXT NOT NULL,
  section     VARCHAR(50) NOT NULL,
  updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 3.6 `ibkr_uploads` table

```sql
CREATE TABLE ibkr_uploads (
  id          CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  filename    VARCHAR(255) NOT NULL,
  uploaded_at DATETIME NOT NULL,
  status      ENUM('pending','processed','failed') DEFAULT 'pending',
  error_msg   TEXT NULL,
  row_count   INT NULL,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. Migration Scripts

### 4.1 Migrate `active_positions.json`

**JSON structure (V3):**
```json
[
  {
    "id": "...",
    "ticker": "AAPL",
    "strategy": "PMCC",
    "status": "open",
    "opened_at": "2026-05-01T09:35:00Z",
    "legs": [
      {
        "type": "call",
        "action": "buy",
        "expiry": "2027-01-17",
        "strike": 170.0,
        "quantity": 1,
        "cost_basis": 12.40
      }
    ],
    "notes": "LEAPS PMCC, low IV entry"
  }
]
```

**Migration script:** `scripts/migrate/migrate_positions.py`
```python
import json, uuid, mysql.connector
from pathlib import Path
from datetime import datetime

conn = mysql.connector.connect(host='localhost', user='fortress', password='...', database='fortress_db')
cursor = conn.cursor()

with open('/var/backups/fortress-json-pre-v4/active_positions.json') as f:
    positions = json.load(f)

for pos in positions:
    pos_id = pos.get('id') or str(uuid.uuid4())
    # Map V3 'status' values to V4 'state' enum values
    status_map = {'open': 'open', 'closed': 'closed', 'pending': 'monitored'}
    v4_state = status_map.get(pos.get('status', 'open'), 'open')
    cursor.execute("""
        INSERT IGNORE INTO positions (id, ticker, strategy, state, opened_at, closed_at, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        pos_id, pos['ticker'], pos['strategy'],
        v4_state,
        pos['opened_at'], pos.get('closed_at'),
        pos.get('notes')
    ))

    for leg in pos.get('legs', []):
        cursor.execute("""
            INSERT INTO position_legs (position_id, leg_type, action, expiry, strike, quantity, cost_basis)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            pos_id, leg['type'], leg['action'],
            leg['expiry'], leg['strike'],
            leg['quantity'], leg['cost_basis']
        ))

conn.commit()
print(f"Migrated {len(positions)} positions")
```

---

### 4.2 Migrate `alerts.json`

**JSON structure (V3):**
```json
[
  {
    "id": "...",
    "ticker": "AAPL",
    "type": "price_target",
    "threshold": 168.0,
    "condition": "below",
    "message": "AAPL approaching lower bound",
    "triggered": false,
    "created_at": "2026-05-15T10:00:00Z"
  }
]
```

**Migration script:** `scripts/migrate/migrate_alerts.py`
```python
with open('/var/backups/fortress-json-pre-v4/alerts.json') as f:
    alerts = json.load(f)

for alert in alerts:
    cursor.execute("""
        INSERT IGNORE INTO alerts (id, ticker, type, threshold, `condition`, message, triggered, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        alert.get('id') or str(uuid.uuid4()),
        alert['ticker'], alert['type'],
        alert.get('threshold'), alert.get('condition'),
        alert['message'], alert.get('triggered', False),
        alert.get('created_at', datetime.utcnow().isoformat())
    ))
conn.commit()
print(f"Migrated {len(alerts)} alerts")
```

---

### 4.3 Migrate `journal.json`

**JSON structure (V3):**
```json
[
  {
    "id": "...",
    "ticker": "AAPL",
    "strategy": "PMCC",
    "action": "OPEN",
    "notes": "Entered at IVR 42",
    "position_id": "...",
    "created_at": "2026-05-01T09:40:00Z"
  }
]
```

**close_id backfill strategy:**  
V3 journal has no close→open linkage. For V4 migration, backfill is best-effort:
- If a journal entry has `action: CLOSE` and there is exactly one prior `action: OPEN` entry for the same ticker+strategy with no existing close link → set `close_id` to the OPEN entry's id.
- If ambiguous (multiple open entries) → leave `close_id` as NULL. The user can link these manually via the Journal UI.

**Migration script:** `scripts/migrate/migrate_journal.py`
```python
with open('/var/backups/fortress-json-pre-v4/journal.json') as f:
    entries = json.load(f)

# First pass: insert all entries (INSERT IGNORE makes script idempotent)
for entry in entries:
    cursor.execute("""
        INSERT IGNORE INTO journal (id, ticker, strategy, action, notes, position_id, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        entry.get('id') or str(uuid.uuid4()),
        entry['ticker'], entry.get('strategy'),
        entry['action'], entry.get('notes'),
        entry.get('position_id'),
        entry.get('created_at', datetime.utcnow().isoformat())
    ))

conn.commit()

# Second pass: backfill close_id
cursor.execute("SELECT id, ticker, strategy, action, created_at FROM journal ORDER BY created_at")
rows = cursor.fetchall()

opens = {}  # (ticker, strategy) -> id
for row in rows:
    jid, ticker, strategy, action, created_at = row
    key = (ticker, strategy)
    if action == 'OPEN':
        opens[key] = jid
    elif action == 'CLOSE' and key in opens:
        cursor.execute("UPDATE journal SET close_id = %s WHERE id = %s", (opens[key], jid))
        del opens[key]  # link consumed

conn.commit()
print(f"Migrated {len(entries)} journal entries with best-effort close_id backfill")
```

---

### 4.4 Migrate `fortress_config.json`

**V4 config keys (all required):**

| Key | Section | Default |
|---|---|---|
| `vix_max` | `strategy_params` | `35` |
| `ivr_min` | `strategy_params` | `25` |
| `pcs_max_positions` | `strategy_params` | `5` |
| `put_notional_max` | `strategy_params` | `25000` |
| `trades_per_week_max` | `strategy_params` | `2` |
| `delta_target` | `strategy_params` | `0.35` |
| `delta_max` | `strategy_params` | `0.55` |
| `delta_min` | `strategy_params` | `0.20` |
| `hedge_coverage_min` | `strategy_params` | `0.25` |
| `pcs_earnings_blackout_days` | `strategy_params` | `10` |
| `leap_entry_blackout_days` | `strategy_params` | `14` |
| `stop_loss_l1_pct` | `risk_controls` | `0.50` |
| `stop_loss_l2_pct` | `risk_controls` | `0.75` |
| `stop_loss_l3_pct` | `risk_controls` | `1.00` |
| `stop_loss_l4_pct` | `risk_controls` | `1.50` |
| `dte_roll_threshold` | `risk_controls` | `21` |
| `capital_efficiency_min` | `analytics` | `0.12` |
| `sector_concentration_max` | `analytics` | `0.40` |
| `whale_threshold_usd` | `analytics` | `500000` |
| `ibkr_gateway_url` | `integrations` | `http://localhost:5000` |
| `quantdata_instance_id` | `integrations` | *(from env)* |
| `dte_exceptions` | `strategy_params` | `[]` |

**Migration script:** `scripts/migrate/migrate_config.py`
```python
with open('/var/backups/fortress-json-pre-v4/fortress_config.json') as f:
    old_config = json.load(f)

# Map old keys → new keys (adjust as needed for your V3 config structure)
key_map = {
    'max_vix': 'vix_max',
    'min_ivr': 'ivr_min',
    'max_pcs': 'pcs_max_positions',
    # ... add other V3→V4 key renames
}

v4_defaults = {
    'vix_max': '35', 'ivr_min': '25', 'pcs_max_positions': '5',
    'put_notional_max': '25000', 'trades_per_week_max': '2',
    'delta_target': '0.35', 'delta_max': '0.55', 'delta_min': '0.20',
    'hedge_coverage_min': '0.25', 'pcs_earnings_blackout_days': '10',
    'leap_entry_blackout_days': '14',
    'stop_loss_l1_pct': '0.50', 'stop_loss_l2_pct': '0.75',
    'stop_loss_l3_pct': '1.00', 'stop_loss_l4_pct': '1.50',
    'dte_roll_threshold': '21', 'capital_efficiency_min': '0.12',
    'sector_concentration_max': '0.40', 'whale_threshold_usd': '500000',
    'ibkr_gateway_url': 'http://localhost:5000', 'dte_exceptions': '[]'
}

# Build final config (defaults overridden by migrated values)
final_config = dict(v4_defaults)
for old_key, value in old_config.items():
    new_key = key_map.get(old_key, old_key)
    if new_key in final_config:
        final_config[new_key] = str(value)

section_map = {
    'vix_max': 'strategy_params', 'ivr_min': 'strategy_params',
    'pcs_max_positions': 'strategy_params', 'put_notional_max': 'strategy_params',
    'trades_per_week_max': 'strategy_params', 'delta_target': 'strategy_params',
    'delta_max': 'strategy_params', 'delta_min': 'strategy_params',
    'hedge_coverage_min': 'strategy_params', 'pcs_earnings_blackout_days': 'strategy_params',
    'leap_entry_blackout_days': 'strategy_params', 'dte_exceptions': 'strategy_params',
    'stop_loss_l1_pct': 'risk_controls', 'stop_loss_l2_pct': 'risk_controls',
    'stop_loss_l3_pct': 'risk_controls', 'stop_loss_l4_pct': 'risk_controls',
    'dte_roll_threshold': 'risk_controls', 'capital_efficiency_min': 'analytics',
    'sector_concentration_max': 'analytics', 'whale_threshold_usd': 'analytics',
    'ibkr_gateway_url': 'integrations', 'quantdata_instance_id': 'integrations',
}

for key, value in final_config.items():
    cursor.execute("""
        INSERT INTO config (`key`, value, section) VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE value = VALUES(value)
    """, (key, value, section_map.get(key, 'general')))

conn.commit()
print(f"Migrated {len(final_config)} config keys")
```

---

### 4.5 Migrate `ibkr_uploads.json`

```python
with open('/var/backups/fortress-json-pre-v4/ibkr_uploads.json') as f:
    uploads = json.load(f)

for upload in uploads:
    cursor.execute("""
        INSERT INTO ibkr_uploads (id, filename, uploaded_at, status, error_msg, row_count)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        upload.get('id') or str(uuid.uuid4()),
        upload['filename'], upload['uploaded_at'],
        upload.get('status', 'processed'),
        upload.get('error_msg'), upload.get('row_count')
    ))

conn.commit()
print(f"Migrated {len(uploads)} IBKR upload records")
```

---

## 5. Post-Migration Validation

Run these checks before restarting the service:

```bash
mysql -u fortress -p fortress_db <<'EOF'
SELECT 'positions' as tbl, COUNT(*) FROM positions
UNION ALL SELECT 'position_legs', COUNT(*) FROM position_legs
UNION ALL SELECT 'alerts', COUNT(*) FROM alerts
UNION ALL SELECT 'journal', COUNT(*) FROM journal
UNION ALL SELECT 'config', COUNT(*) FROM config
UNION ALL SELECT 'ibkr_uploads', COUNT(*) FROM ibkr_uploads;

-- Check close_id backfill
SELECT
  COUNT(*) as closed_entries,
  SUM(CASE WHEN close_id IS NOT NULL THEN 1 ELSE 0 END) as with_close_id,
  SUM(CASE WHEN close_id IS NULL THEN 1 ELSE 0 END) as without_close_id
FROM journal
WHERE action = 'CLOSE';

-- Confirm all required config keys present
SELECT COUNT(*) FROM config WHERE `key` IN (
  'vix_max','ivr_min','pcs_max_positions','put_notional_max',
  'trades_per_week_max','delta_target','stop_loss_l1_pct'
);
-- Should return 7
EOF
```

**Comparison check:** Count rows in MySQL vs items in JSON files. Counts must match.

---

## 6. Restart and Smoke Test

```bash
# Start service
systemctl start fortress-dashboard

# Verify API is up
curl -s -H "Authorization: Bearer $FORTRESS_API_TOKEN" \
  http://localhost:8080/api/capability | python3 -m json.tool

# Check positions loaded
curl -s -H "Authorization: Bearer $FORTRESS_API_TOKEN" \
  http://localhost:8080/api/positions | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Positions: {d[\"total_positions\"]}')"

# Check config loaded
curl -s -H "Authorization: Bearer $FORTRESS_API_TOKEN" \
  http://localhost:8080/api/config | python3 -m json.tool
```

---

## 7. JSON File Deprecation

After successful validation:

1. Do NOT delete JSON files immediately — keep for 30 days as fallback reference
2. Move them to archive: `mv /var/www/fortress-v2/data/*.json /var/backups/fortress-json-pre-v4/`
3. Remove JSON read/write code paths from application (Phase 4 backend task P4-05 through P4-09)
4. After 30 days with no issues: `rm -rf /var/backups/fortress-json-pre-v4/`

---

## 8. Rollback Procedure

If anything goes wrong, roll back to V3 JSON state in under 10 minutes:

```bash
# 1. Stop service
systemctl stop fortress-dashboard

# 2. Restore JSON files to the correct Fortress_Dashboard data directory
cp /var/backups/fortress-json-pre-v4/*.json /home/ubuntu/Fortress_Dashboard/data/

# 3. Checkout V3 code (requires git tag on last V3 commit)
cd /var/www/fortress-v2
git checkout v3-last-stable

# 4. Reinstall V3 dependencies
pip install -r requirements.txt --break-system-packages

# 5. Start service
systemctl start fortress-dashboard

# 6. Verify
curl -s -H "Authorization: Bearer $FORTRESS_API_TOKEN" http://localhost:8080/api/capability
```

**Pre-condition for safe rollback:** The V3 code must be tagged as `v3-last-stable` in git before beginning the V4 migration.

```bash
# Tag V3 before migration (do this BEFORE any V4 code changes)
git tag v3-last-stable
git push origin v3-last-stable
```

---

## 9. V4-Only Data (Cannot Rollback)

The following V4 additions have no V3 equivalent. If rollback is needed, this data is lost:

| Data | Impact |
|---|---|
| `journal.close_id` links | Lose closed-loop linkage; journal entries remain but unlinked |
| `journal.iv_crush_realized` | Lose post-earnings IV crush records |
| `journal.dte_at_close` | Lose DTE-at-close metadata |
| New config keys | V3 code ignores unknown keys; V4-only config reverts to V3 hardcoded values |
| `pcs_exposure` view | View removed; V3 code doesn't use it |

---

*Fortress V4 Migration Guide — test in a staging copy of the database before running on production.*
