#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Fortress gateway watchdog  (Sprint 25.1 — the non-OAuth-blocked half)
#
# Keeps the IBKR CP Gateway (iBeam) session alive so the backend stops falling
# back to `bs_yfinance` / `session_not_established` (which degrades every roll,
# stop, greek and liquidity number). It polls the gateway's auth status; on
# repeated failure it issues `docker restart cp-gateway` — iBeam re-authenticates
# automatically on container boot — guarded by a cooldown so a genuine outage
# (or IBKR maintenance window) can't trigger a restart storm.
#
# Escalation: /tickle (gentle warm + status)  →  fail x THRESHOLD  →  restart.
#
# Install as a systemd service (see fortress-gateway-watchdog.service). Tunables
# are all environment variables so the unit can override without editing this.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

GATEWAY_URL="${GATEWAY_URL:-https://localhost:5000}"
CONTAINER="${GATEWAY_CONTAINER:-cp-gateway}"
POLL_SECONDS="${WATCHDOG_POLL_SECONDS:-60}"           # check cadence
FAIL_THRESHOLD="${WATCHDOG_FAIL_THRESHOLD:-3}"        # consecutive fails before a restart
COOLDOWN_SECONDS="${WATCHDOG_COOLDOWN_SECONDS:-600}"  # min gap between restarts (10 min)
SETTLE_SECONDS="${WATCHDOG_SETTLE_SECONDS:-90}"       # wait after a restart for iBeam re-auth
LOG_LOOKBACK="${WATCHDOG_LOG_LOOKBACK:-180}"          # seconds of iBeam log to inspect (~3 maint cycles)
LOG="${WATCHDOG_LOG:-/var/log/fortress-gateway-watchdog.log}"

log(){ echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG" >/dev/null 2>&1; }

# Health probe reads iBeam's OWN truth, not the gateway HTTP endpoints.
#
# Why not curl /v1/api/tickle : on this CP Gateway build a raw request to the
# /v1/api/* endpoints is bounced by IBKR's Akamai edge with a "Bad Request"
# HTML page (verified 2026-07-05) — regardless of User-Agent — so it never
# contains the auth JSON and would false-negative a perfectly HEALTHY, logged-in
# gateway, bouncing it every cooldown. iBeam already self-heals a dropped
# session; its maintenance loop logs "Gateway running and authenticated" every
# 60s while live. So we trust that: a healthy session always has a recent such
# line; a wedged iBeam stops emitting it (or logs login failures), which a
# container restart clears — exactly the case the watchdog exists for.
#
# Returns: 0 = healthy (recent authenticated line), 1 = unhealthy, 2 = UNKNOWN
# (can't read state — e.g. docker hiccup). UNKNOWN is treated as "don't count
# as a failure" so a transient docker error can never trigger a restart.
check_auth(){
  local state logs
  state=$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null) || return 2
  [ "$state" = "true" ] || return 1        # container down → genuinely unhealthy
  logs=$(docker logs --since "${LOG_LOOKBACK}s" "$CONTAINER" 2>&1) || return 2
  [ -n "$logs" ] || return 2               # no log output at all → unknown, not a fail
  echo "$logs" | grep -q "running and authenticated"
}

fails=0
last_restart=0

log "watchdog started (poll=${POLL_SECONDS}s threshold=${FAIL_THRESHOLD} cooldown=${COOLDOWN_SECONDS}s url=${GATEWAY_URL} container=${CONTAINER})"

while true; do
  if check_auth; then
    [ "$fails" -gt 0 ] && log "auth recovered (was ${fails} consecutive fail(s))"
    fails=0
  else
    fails=$((fails + 1))
    log "auth probe FAILED (${fails}/${FAIL_THRESHOLD})"
    if [ "$fails" -ge "$FAIL_THRESHOLD" ]; then
      now=$(date +%s)
      elapsed=$((now - last_restart))
      if [ "$elapsed" -lt "$COOLDOWN_SECONDS" ]; then
        log "in cooldown ($((COOLDOWN_SECONDS - elapsed))s remaining) — NOT restarting (probable IBKR-side outage)"
      else
        log "restarting container '${CONTAINER}' (iBeam will re-auth on boot)…"
        if docker restart "$CONTAINER" >>"$LOG" 2>&1; then
          last_restart=$(date +%s)
          fails=0
          log "restart issued; sleeping ${SETTLE_SECONDS}s for iBeam re-auth before next probe"
          sleep "$SETTLE_SECONDS"
        else
          log "docker restart FAILED — will retry after cooldown"
          last_restart=$(date +%s)   # still start the cooldown to avoid hammering
        fi
      fi
    fi
  fi
  sleep "$POLL_SECONDS"
done
