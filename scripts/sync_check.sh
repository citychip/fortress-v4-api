#!/bin/bash
# sync_check.sh — OneDrive ↔ GitHub drift guard
# Run from WSL:  bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/sync_check.sh
#
# WHY: the OneDrive 2606Fortress folder is the dev/edit copy. Deploys copy files
# INTO the WSL repos, which are what gets pushed to GitHub. A file edited in OneDrive
# but never re-deployed/committed leaves GitHub stale while `git status` still looks clean.
# This script content-diffs every known OneDrive source file against its repo
# destination, then prints per-repo git sync status. Run it at every session wrap.
#
# Convention: any NEW backend script created in OneDrive must be added to the MAP
# below (and ideally to deploy_data_sources.sh) so it can never silently miss
# GitHub. Parapet frontend files are tracked AUTOMATICALLY — the Parapet section
# below derives its file list from deploy_parapet.sh's FILES=() array, so any
# file you add to that deploy list is drift-checked here with no second list to
# maintain. (Add new Parapet files to deploy_parapet.sh's FILES and you're done.)

set -u
SRC=/mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress
API=~/fortress-v4-api
MCP=~/fortress-mcp
PARA_SRC=$SRC/fortress-parapet      # OneDrive dev/edit copy
PARA_REPO=~/fortress-parapet        # WSL repo (what pushes to GitHub)
DEPLOY_PARAPET=$SRC/deploy_parapet.sh

# OneDrive-relative-path : repo-destination-path
MAP=(
  "ibkr_marketdata.py:$API/app/services/ibkr_marketdata.py"
  "options_analytics.py:$API/app/routes/options_analytics.py"
  "tests/test_options_routes_nan.py:$API/tests/test_options_routes_nan.py"
  "journal_analytics.py:$API/journal_analytics.py"
  "snapshot_iv.sh:$API/scripts/snapshot_iv.sh"
  "iv_source.py:$API/quant/iv_source.py"
  "workflow_05_iv_crush_report.py:$API/quant/workflow_05_iv_crush_report.py"
  "workflow_01_premarket_scanner.py:$API/quant/workflow_01_premarket_scanner.py"
  "test_ibkr_oauth.py:$API/scripts/test_ibkr_oauth.py"
  "fortress_mcp_v452.py:$MCP/fortress_mcp.py"
  # Live MCP the desktop plugin actually runs (Windows path, NOT the repo copy).
  # Tracked so an MCP code change can't reach git+repo yet miss the runtime the
  # connector launches. Added 2026-06-20 with the file-preferred token loader.
  "fortress_mcp_v452.py:/mnt/c/Users/cityc.000/fortress_mcp/fortress_mcp.py"
  "sync_check.sh:$API/scripts/sync_check.sh"
  # Deploy scripts (2026-06-22) — version-controlled so deploy-logic changes reach
  # GitHub. They're run from OneDrive; the deploy copies them into the repo too.
  "deploy_data_sources.sh:$API/scripts/deploy_data_sources.sh"
  "deploy_parapet.sh:$API/scripts/deploy_parapet.sh"
  # Sprint 0 (2026-06-19): out-of-mount backend route/service files pulled into
  # OneDrive so pretrade_check / regime / strategy_metrics / pacing are now
  # dev-editable + drift-tracked + deployable (see deploy_data_sources.sh ROUTE_FILES).
  "manage.py:$API/app/routes/manage.py"
  "options.py:$API/app/routes/options.py"
  "briefing.py:$API/app/routes/briefing.py"
  "market_intelligence.py:$API/app/routes/market_intelligence.py"
  "settings.py:$API/app/routes/settings.py"
  "config_store.py:$API/app/services/config_store.py"
  "state.py:$API/app/services/state.py"
  # Sprint 20.1 (2026-06-27): journal route — prose-tolerant POST /api/journal.
  "journal.py:$API/app/routes/journal.py"
  # Sprint 20.3 (2026-06-29): conditional-alerts route + scheduler runner —
  # close_above/close_below EOD-confirmation alert type.
  "route_conditional_alerts.py:$API/app/routes/conditional_alerts.py"
  "sched_runner.py:$API/app/scheduler/runner.py"
  # Sprint 22.5 (2026-07-03): chart route (1mo/4h intervals).
  "chart_route.py:$API/app/routes/chart.py"
)

echo "── File-content drift (OneDrive → repo) ──"
drift=0
for pair in "${MAP[@]}"; do
  s="${pair%%:*}"; d="${pair##*:}"
  if   [ ! -f "$SRC/$s" ];                 then echo "  ⚠ SRC MISSING   : $s"; drift=1
  elif [ ! -f "$d" ];                      then echo "  ⚠ MISSING IN REPO: $s  (expected $d)"; drift=1
  elif diff -q "$SRC/$s" "$d" >/dev/null;  then echo "  ✓ in sync        : $s"
  else                                          echo "  ✗ DIFFERS        : $s  → needs copy + commit"; drift=1
  fi
done

echo ""
echo "── Parapet drift (OneDrive → WSL repo; file list from deploy_parapet.sh) ──"
# Extract the quoted entries from deploy_parapet.sh's FILES=( ... ) array so this
# check always tracks exactly what the deploy copies — no second list to drift.
mapfile -t PARAPET_FILES < <(
  awk '/^FILES=\(/{f=1;next} f&&/^\)/{exit} f{gsub(/[" \t]/,"");if($0!="")print}' "$DEPLOY_PARAPET" 2>/dev/null
)
if [ ! -f "$DEPLOY_PARAPET" ]; then
  echo "  ⚠ deploy_parapet.sh not found at $DEPLOY_PARAPET — cannot derive file list"; drift=1
elif [ "${#PARAPET_FILES[@]}" -eq 0 ]; then
  echo "  ⚠ could not parse FILES=() from deploy_parapet.sh — check its format"; drift=1
else
  for f in "${PARAPET_FILES[@]}"; do
    if   [ ! -f "$PARA_SRC/$f" ];                            then echo "  ⚠ SRC MISSING    : $f"; drift=1
    elif [ ! -f "$PARA_REPO/$f" ];                           then echo "  ⚠ MISSING IN REPO: $f  (expected $PARA_REPO/$f)"; drift=1
    elif diff -q "$PARA_SRC/$f" "$PARA_REPO/$f" >/dev/null;  then echo "  ✓ in sync         : $f"
    else                                                          echo "  ✗ DIFFERS         : $f  → run deploy_parapet.sh + commit"; drift=1
    fi
  done
fi

echo ""
echo "── Docs drift (OneDrive docs/ → repo docs/, recursive — incl. archive/) ──"
# Docs are version-controlled in the repo (2026-06-22). Every .md under OneDrive
# docs/ is diffed against $API/docs/ so the handoff/strategy/session docs can't
# silently miss GitHub. New docs are auto-tracked (directory scan, no second list).
DOCS_SRC="$SRC/docs"; DOCS_REPO="$API/docs"
if [ ! -d "$DOCS_SRC" ]; then
  echo "  ⚠ $DOCS_SRC not found"; drift=1
else
  while IFS= read -r f; do
    rel="${f#"$DOCS_SRC"/}"; d="$DOCS_REPO/$rel"
    if   [ ! -f "$d" ];                 then echo "  ⚠ MISSING IN REPO: docs/$rel"; drift=1
    elif diff -q "$f" "$d" >/dev/null;  then echo "  ✓ in sync         : docs/$rel"
    else                                     echo "  ✗ DIFFERS         : docs/$rel  → copy + commit"; drift=1
    fi
  done < <(find "$DOCS_SRC" -type f -name '*.md' | sort)
fi

echo ""
echo "── Repo git status (ahead/behind origin + working tree) ──"
for r in fortress-v4-api fortress-mcp fortress-v4-frontend fortress-parapet; do
  echo "=== $r ==="
  git -C ~/$r fetch -q 2>/dev/null
  git -C ~/$r status -sb | head -1
  git -C ~/$r status -s
done

echo ""
[ "$drift" -eq 0 ] && echo "RESULT: all mapped files in sync ✓" || echo "RESULT: drift detected ✗ — copy the DIFFERS/MISSING files into the repo, commit, push."
