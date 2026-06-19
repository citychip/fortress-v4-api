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
# Convention: any NEW script created in OneDrive must be added to the MAP below
# (and ideally to deploy_data_sources.sh) so it can never silently miss GitHub.

set -u
SRC=/mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress
API=~/fortress-v4-api
MCP=~/fortress-mcp

# OneDrive-relative-path : repo-destination-path
MAP=(
  "ibkr_marketdata.py:$API/app/services/ibkr_marketdata.py"
  "options_analytics.py:$API/app/routes/options_analytics.py"
  "tests/test_options_routes_nan.py:$API/tests/test_options_routes_nan.py"
  "journal_analytics.py:$API/journal_analytics.py"
  "snapshot_iv.sh:$API/scripts/snapshot_iv.sh"
  "test_ibkr_oauth.py:$API/scripts/test_ibkr_oauth.py"
  "fortress_mcp_v452.py:$MCP/fortress_mcp.py"
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
echo "── Repo git status (ahead/behind origin + working tree) ──"
for r in fortress-v4-api fortress-mcp fortress-v4-frontend fortress-parapet; do
  echo "=== $r ==="
  git -C ~/$r fetch -q 2>/dev/null
  git -C ~/$r status -sb | head -1
  git -C ~/$r status -s
done

echo ""
[ "$drift" -eq 0 ] && echo "RESULT: all mapped files in sync ✓" || echo "RESULT: drift detected ✗ — copy the DIFFERS/MISSING files into the repo, commit, push."
