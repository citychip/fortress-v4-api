#!/usr/bin/env bash
# deploy_parapet.sh
# Syncs changed source files from OneDrive workspace → WSL home, then builds & deploys.
# Run from WSL:
#   bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/deploy_parapet.sh

set -e
umask 022   # guard: ensure deployed web files are world-readable (nginx www-data), regardless of caller's umask

WIN_SRC="/mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/fortress-parapet"
WSL_DEST="$HOME/fortress-parapet"
WEBROOT="/var/www/fortress-parapet"

echo "=== Step 1: Sync source files from OneDrive ==="
if [ ! -d "$WSL_DEST" ]; then
  echo "  ERROR: $WSL_DEST does not exist. Clone the repo first."
  exit 1
fi

FILES=(
  "package.json"
  "src/App.tsx"
  "src/lib/api.ts"
  "src/lib/positions.ts"
  "src/lib/colors.ts"
  "src/lib/useSettings.ts"
  "src/lib/useMode.ts"
  "src/lib/household.ts"
  "src/components/Layout.tsx"
  "src/components/SourceBadge.tsx"
  "src/components/Sidebar.tsx"
  "src/components/Sortable.tsx"
  "src/components/StatRow.tsx"
  "src/components/Toast.tsx"
  "src/components/KV.tsx"
  "src/components/Badge.tsx"
  "src/components/AnalyticsCharts.tsx"
  "src/components/MtfCandleChart.tsx"
  "src/components/TimelinePanel.tsx"
  "src/components/RiskPanel.tsx"
  "src/components/UncapTracker.tsx"
  "src/components/LeafHeader.tsx"
  "src/components/positions/PositionCards.tsx"
  "src/components/system/UniverseSection.tsx"
  "src/components/system/ConnectionsSection.tsx"
  "src/components/system/ScriptsSection.tsx"
  "src/pages/BriefingPage.tsx"
  "src/pages/TriagePage.tsx"
  "src/pages/PositionsPage.tsx"
  "src/pages/CandidatesPage.tsx"
  "src/pages/MarketPage.tsx"
  "src/pages/TechnicalPage.tsx"
  "src/pages/EfficiencyPage.tsx"
  "src/pages/HouseholdPage.tsx"
  "src/pages/RiskPage.tsx"
  "src/pages/TimelinePage.tsx"
  "src/pages/SystemPage.tsx"
)

# Sprint 13 (#78/#79): pages deleted from the repo — remove stale copies in WSL
# so tsc doesn't typecheck dead code.
REMOVED=(
  "src/pages/OrdersPage.tsx"
  "src/pages/OverviewPage.tsx"
  "src/pages/PortfolioPage.tsx"
)
for f in "${REMOVED[@]}"; do
  if [ -f "$WSL_DEST/$f" ]; then
    rm "$WSL_DEST/$f"
    echo "  ✗ removed $f"
  fi
done

for f in "${FILES[@]}"; do
  SRC="$WIN_SRC/$f"
  DST="$WSL_DEST/$f"
  if [ -f "$SRC" ]; then
    mkdir -p "$(dirname "$DST")"
    cp "$SRC" "$DST"
    echo "  ✓ $f"
  else
    echo "  ⚠ MISSING: $SRC"
  fi
done

echo ""
echo "=== Step 2: Build ==="
cd "$WSL_DEST"

# ALWAYS regenerate .env from the canonical token file so rotations propagate.
# Read ~/.fortress_api_token (quote-free) and strip any stray quotes/whitespace.
# Do NOT scrape the systemd line — its surrounding quotes leak into the value
# (\S+ grabs the trailing "), producing a bad token → 401 invalid_token.
TOKEN=$(tr -d '"[:space:]' < ~/.fortress_api_token 2>/dev/null)
if [ -n "$TOKEN" ]; then
  # Write .env.local — Vite prioritizes it OVER .env, so a stale .env.local would
  # silently override and ship the old token (caused 401s during the 2026-06-19 rotation).
  printf "VITE_API_BASE=\nVITE_API_TOKEN=%s\n" "$TOKEN" > "$WSL_DEST/.env.local"
  printf "VITE_API_BASE=\nVITE_API_TOKEN=%s\n" "$TOKEN" > "$WSL_DEST/.env"
  echo "  ✓ .env + .env.local regenerated from ~/.fortress_api_token"
else
  echo "  ⚠ ERROR: ~/.fortress_api_token empty/missing — aborting"; exit 1
fi

npm install
npm run build

echo ""
echo "=== Step 3: Deploy to $WEBROOT ==="
sudo rm -rf "$WEBROOT"/*
sudo cp -r dist/* "$WEBROOT/"

echo ""
echo "=== Step 4: Reload nginx ==="
sudo nginx -s reload

echo ""
PORT=$(grep -oP '(?<=listen )\d+' "$HOME/fortress-parapet/nginx/parapet.conf" 2>/dev/null || echo "4000")
echo "=== Done. Parapet live at http://localhost:${PORT} ==="
