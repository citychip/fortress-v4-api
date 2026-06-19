#!/usr/bin/env bash
# snapshot_iv.sh — daily IV snapshot sweep for the whole universe.
# Each call to /api/options/iv-rank/{ticker} stores today's ATM IV in
# data/iv_history.json; after ~60 trading days the IV Rank board switches
# from HV-proxy to true IV rank automatically.
#
# Run from WSL during market hours (quotes are junk pre-market):
#   bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/snapshot_iv.sh
#
# Or schedule (10:05 ET ≈ 16:05 CET, Mon-Fri):
#   crontab -e
#   5 16 * * 1-5 bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/snapshot_iv.sh >> ~/iv_snapshot.log 2>&1

set -e
API="http://localhost:8081"
TOKEN=$(cat ~/.fortress_api_token 2>/dev/null || systemctl show fortress-dashboard-v4 -p Environment 2>/dev/null | grep -o 'FORTRESS_API_TOKEN=[^ ]*' | cut -d= -f2)

echo "=== IV snapshot sweep $(date '+%Y-%m-%d %H:%M') ==="

TICKERS=$(curl -sf "$API/api/universe" -H "Authorization: Bearer $TOKEN" | python3 -c "
import json, sys
d = json.load(sys.stdin)
raw = d.get('tier1') or d.get('tickers') or []
print(' '.join(t if isinstance(t, str) else t.get('ticker', '') for t in raw))
")

ok=0; fail=0
for t in $TICKERS; do
  out=$(curl -sf "$API/api/options/iv-rank/$t" -H "Authorization: Bearer $TOKEN" || echo '{}')
  ivr=$(echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('iv_rank','ERR'), d.get('current_iv',''), d.get('source',''), d.get('error','')[:60])" 2>/dev/null || echo "ERR")
  case "$ivr" in
    ERR*|*ERR*) printf "  ✗ %-6s %s\n" "$t" "$ivr"; fail=$((fail+1));;
    *)          printf "  ✓ %-6s IVR %s\n" "$t" "$ivr"; ok=$((ok+1));;
  esac
done

echo "=== Done: $ok ok, $fail failed ==="
