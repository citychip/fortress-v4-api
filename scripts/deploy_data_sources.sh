#!/bin/bash
# deploy_data_sources.sh — Data Sources Optimization Phases 1-4 (2026-06-10)
# Run from WSL:  bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/deploy_data_sources.sh
#
# 1. Copies ibkr_marketdata.py (new service) + options_analytics.py (v2, IBKR-first)
# 2. Patches chain.get_spot() in place: IBKR-first, yfinance body preserved as _yf_get_spot
# 3. Compile-checks everything, restarts backend, verifies routes report their source
set -e

SRC="/mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress"
API="$HOME/fortress-v4-api"
TOKEN=$(cat ~/.fortress_api_token 2>/dev/null) || true
[ -n "$TOKEN" ] || { echo "FATAL: API token not found — create ~/.fortress_api_token (single line, no quotes)"; exit 1; }

echo "── Backups ──"
cp "$API/app/services/chain.py" "$API/app/services/chain.py.pre-ibkr-spot-bak"
cp "$API/app/routes/options_analytics.py" "$API/app/routes/options_analytics.py.pre-ibkr-bak" 2>/dev/null || true

echo "── Copy new/updated files ──"
cp "$SRC/ibkr_marketdata.py"   "$API/app/services/ibkr_marketdata.py"
cp "$SRC/options_analytics.py" "$API/app/routes/options_analytics.py"
# Standalone scripts — kept in repo for version control (not part of the backend service):
cp "$SRC/journal_analytics.py" "$API/journal_analytics.py"
cp "$SRC/snapshot_iv.sh"       "$API/scripts/snapshot_iv.sh"
# Shared IBKR-first IV module (Sprint 18.2) — single source of truth imported by
# BOTH scanners; MUST be copied before them so the sibling import resolves.
cp "$SRC/iv_source.py" "$API/quant/iv_source.py"
# IV-crush scanner (18.1) + premarket scanner (18.2) — now IBKR-first via iv_source.
# Back up before copy so a bad version can roll back. workflow_05 feeds
# /api/candidates via state.get_iv_crush_report().
cp "$API/quant/workflow_05_iv_crush_report.py" "$API/quant/workflow_05_iv_crush_report.py.pre-18.1-bak" 2>/dev/null || true
cp "$SRC/workflow_05_iv_crush_report.py" "$API/quant/workflow_05_iv_crush_report.py"
cp "$API/quant/workflow_01_premarket_scanner.py" "$API/quant/workflow_01_premarket_scanner.py.pre-18.2-bak" 2>/dev/null || true
cp "$SRC/workflow_01_premarket_scanner.py" "$API/quant/workflow_01_premarket_scanner.py"
# Docs → repo (2026-06-22; recursive rsync since 2026-07-09 for the v3/v4/shared
# reorg). Mirrors the WHOLE docs/ tree (root + v3/ + v4/ + shared/ + archive/),
# copying only .md and preserving subfolders. No --delete (repo removals are done
# via `git mv`/`git rm`, not the deploy). Drift-tracked by sync_check.sh's docs section.
mkdir -p "$API/docs/archive"
rsync -am --include='*/' --include='*.md' --exclude='*' "$SRC/docs/" "$API/docs/"
# Deploy scripts → repo (2026-06-22) — so deploy-logic changes reach GitHub.
mkdir -p "$API/scripts"
cp "$SRC/deploy_data_sources.sh" "$API/scripts/deploy_data_sources.sh" 2>/dev/null || true
cp "$SRC/deploy_parapet.sh"      "$API/scripts/deploy_parapet.sh"      2>/dev/null || true

echo "── Patch chain.get_spot (Phase 1) ──"
python3 - "$API/app/services/chain.py" <<'PYEOF'
import sys
p = sys.argv[1]
s = open(p).read()

if "_yf_get_spot" in s:
    print("chain.py already patched — skipping")
    sys.exit(0)

anchor = "def get_spot(ticker):"
if anchor not in s:
    print("FATAL: anchor 'def get_spot(ticker):' not found in chain.py")
    sys.exit(1)

replacement = '''def get_spot(ticker):
    # Phase 1 (2026-06-10): IBKR-first live spot via CP Gateway.
    # yfinance (~15m delayed + 300s module cache) demoted to fallback —
    # conditional alert triggers must evaluate on live prices.
    try:
        from app.services.ibkr_marketdata import ibkr_spot
        p = ibkr_spot(ticker)
        if p and p > 0:
            return p
    except Exception:
        pass
    return _yf_get_spot(ticker)


def _yf_get_spot(ticker):'''

s = s.replace(anchor, replacement, 1)
open(p, "w").write(s)
print("chain.py patched: get_spot is IBKR-first, original body -> _yf_get_spot")
PYEOF

echo "── Compile check (auto-rollback on failure) ──"
if ! python3 -m py_compile "$API/app/services/chain.py" \
                           "$API/app/services/ibkr_marketdata.py" \
                           "$API/app/routes/options_analytics.py" \
                           "$API/quant/iv_source.py" \
                           "$API/quant/workflow_05_iv_crush_report.py" \
                           "$API/quant/workflow_01_premarket_scanner.py"; then
  echo "COMPILE FAILED — rolling back"
  cp "$API/app/services/chain.py.pre-ibkr-spot-bak" "$API/app/services/chain.py"
  cp "$API/app/routes/options_analytics.py.pre-ibkr-bak" "$API/app/routes/options_analytics.py" 2>/dev/null || true
  cp "$API/quant/workflow_05_iv_crush_report.py.pre-18.1-bak" "$API/quant/workflow_05_iv_crush_report.py" 2>/dev/null || true
  cp "$API/quant/workflow_01_premarket_scanner.py.pre-18.2-bak" "$API/quant/workflow_01_premarket_scanner.py" 2>/dev/null || true
  rm -f "$API/app/services/ibkr_marketdata.py"
  exit 1
fi
echo "compile OK"

echo "── NaN smoke-test (options routes must be JSON wire-safe) ──"
mkdir -p "$API/tests"
cp "$SRC/tests/test_options_routes_nan.py" "$API/tests/test_options_routes_nan.py" 2>/dev/null || true
# Use the backend venv interpreter (has numpy/pandas/yfinance); fall back to system python3.
PYBIN="$API/venv/bin/python3"; [ -x "$PYBIN" ] || PYBIN="$(command -v python3)"
if ! ( cd "$API" && PYTHONPATH="$API" "$PYBIN" tests/test_options_routes_nan.py ); then
  echo "NaN SMOKE-TEST FAILED — rolling back options_analytics.py"
  cp "$API/app/routes/options_analytics.py.pre-ibkr-bak" "$API/app/routes/options_analytics.py" 2>/dev/null || true
  exit 1
fi
echo "smoke-test OK"

echo "── Sprint 0: mirror out-of-mount route/service files (OneDrive → repo) ──"
# These route/service files are dev-edited in OneDrive and copied back here so
# pretrade_check / regime / strategy_metrics / pacing become deploy + drift-tracked.
# Self-contained backup → copy → compile-check → rollback; does NOT touch the
# chain.py / options_analytics.py logic above.
ROUTE_FILES=(
  "manage.py:$API/app/routes/manage.py"
  "options.py:$API/app/routes/options.py"
  "briefing.py:$API/app/routes/briefing.py"
  "market_intelligence.py:$API/app/routes/market_intelligence.py"
  "settings.py:$API/app/routes/settings.py"
  "config_store.py:$API/app/services/config_store.py"
  "state.py:$API/app/services/state.py"
  # Sprint 20.1 (2026-06-27): journal route pulled into OneDrive so the
  # POST /api/journal schema fix (prose-tolerant) is deploy + drift-tracked.
  "journal.py:$API/app/routes/journal.py"
  # Sprint 20.3 (2026-06-29): conditional-alerts route + scheduler runner pulled
  # into OneDrive for the close_above/close_below EOD-confirmation alert type.
  "route_conditional_alerts.py:$API/app/routes/conditional_alerts.py"
  "sched_runner.py:$API/app/scheduler/runner.py"
  # Sprint 22.5 (2026-07-03): chart route pulled in to add 1mo/4h intervals.
  "chart_route.py:$API/app/routes/chart.py"
  # O-1 (2026-07-08): candidates route — earnings-null → "unverified" fix
  # (state.earnings_state_from_days; the last "null renders clear" surface).
  "route_candidates.py:$API/app/routes/candidates.py"
  # O-10 (2026-07-12): v4.0 Phase 2 household route (read-only, engine untouched)
  # — /api/household[/overview|/concentration]. Needs the eToro snapshot store
  # copied too (below) AND a one-line app.include_router registration in the API
  # main (see docs). Mirrors fortress-parapet/src/lib/household.ts.
  "route_household.py:$API/app/routes/household.py"
)
r0_paths=()
for pair in "${ROUTE_FILES[@]}"; do
  s="${pair%%:*}"; d="${pair##*:}"
  [ -f "$SRC/$s" ] || { echo "  ⚠ missing in OneDrive: $s — skipping"; continue; }
  cp "$d" "$d.pre-sprint0-bak" 2>/dev/null || true
  cp "$SRC/$s" "$d"
  r0_paths+=("$d")
  echo "  copied $s → $d"
done
echo "── Compile-check route files (auto-rollback on failure) ──"
if ! python3 -m py_compile "${r0_paths[@]}"; then
  echo "ROUTE COMPILE FAILED — rolling back Sprint 0 files"
  for d in "${r0_paths[@]}"; do [ -f "$d.pre-sprint0-bak" ] && cp "$d.pre-sprint0-bak" "$d"; done
  exit 1
fi
echo "route files compile OK"

# O-10 (2026-07-12): seed the eToro household snapshot store into BASE_DIR
# (repo root). COPY-IF-ABSENT so a deploy never clobbers a live snapshot that
# was refreshed in-repo after a new eToro read. It is a committed data store
# (like macro_events.json), NOT tracked in sync_check's strict code-drift MAP.
# Seed target is FORTRESS_DATA_DIR (= $API/quant at runtime — state.BASE_DIR),
# NOT the repo root, else _load_store() 404s. Copy-if-absent so a live snapshot
# refreshed in-repo is never clobbered.
HH_DIR="${FORTRESS_DATA_DIR:-$API/quant}"
if [ -f "$SRC/household_state.json" ]; then
  if [ ! -f "$HH_DIR/household_state.json" ]; then
    cp "$SRC/household_state.json" "$HH_DIR/household_state.json"
    echo "  seeded household_state.json → $HH_DIR/ (first deploy)"
  else
    echo "  household_state.json already present in $HH_DIR — left untouched (live snapshot)"
  fi
fi

echo "── Restart backend ──"
sudo systemctl restart fortress-dashboard-v4
sleep 4

echo "── Verify (look for source fields) ──"
curl -s "http://localhost:8081/api/options/iv-rank/SPY" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('iv-rank:', {k: d.get(k) for k in ('iv_rank','current_iv','source','iv_source')})"
curl -s "http://localhost:8081/api/options/liquidity/SPY" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('liquidity:', {k: d.get(k) for k in ('liquidity_grade','atm_spread_pct','source')})"
curl -s "http://localhost:8081/api/options/vol-skew/SPY" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('vol-skew:', {k: d.get(k) for k in ('atm_iv','skew_25d','source')})"
curl -s "http://localhost:8081/api/options/gex/SPY" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('gex:', {k: d.get(k) for k in ('call_wall','put_wall','source')})"

curl -s "http://localhost:8081/api/household/overview" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('household:', {k: d.get(k) for k in ('household_eur','leaf_ibkr_pct','leaf_etoro_pct','source')})"
curl -s "http://localhost:8081/api/household/uncap_stages" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('uncap_stages:', {'regime': d.get('regime'), 'cash_ok': d.get('cash_ok'), 'names': [r.get('ticker') for r in d.get('rows',[])], 'source': d.get('source')})"
curl -s "http://localhost:8081/api/household/tail_hedge" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('tail_hedge:', {k: d.get(k) for k in ('quarterly_budget_usd','tail_put_count','nearest_roll_dte','source')})"

echo ""
echo "Done. During RTH with gateway up, expect source: ibkr (liquidity/skew/iv_source)."
echo "household/overview → source: live (briefing up) or seed (fallback); needs app.include_router(household.router) in the API main + a backend restart."
echo "Fallback test: docker stop cp-gateway → re-run curls → source: yfinance/_bs → docker start cp-gateway."
