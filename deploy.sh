#!/usr/bin/env bash
# Fortress Dashboard — Deploy / Update Script
#
# Usage (run from the repo root on the VPS):
#   ./deploy.sh
#
# What it does:
#   1. Pulls the latest code from GitHub
#   2. Injects the current git commit hash as the cache-buster version string
#      in index.html for all static JS/CSS assets (?v=<hash>)
#   3. Installs / upgrades Python dependencies
#   4. Restarts the systemd service
#
# The cache-buster is a 7-character git short hash (e.g. ?v=3f8342f).
# This replaces the manual date-based version strings (e.g. ?v=20260509k)
# so you never need to bump them by hand again.

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${APP_DIR}/venv"
INDEX_HTML="${APP_DIR}/app/static/index.html"
SERVICE_NAME="fortress-dashboard"

echo "=========================================================="
echo "🏰 Fortress Dashboard — Deploy"
echo "=========================================================="

# 1. Pull latest code
echo ">> Pulling latest code from GitHub..."
git -C "$APP_DIR" pull --ff-only

# 2. Inject git hash as cache-buster in index.html
GIT_HASH=$(git -C "$APP_DIR" rev-parse --short HEAD)
echo ">> Injecting cache-buster: ?v=${GIT_HASH}"

# Replace all existing ?v=<alphanumeric> patterns with the new hash.
# This covers app.js, phase4.js, chart.js, settings.js, universe.js, etc.
sed -i "s/?v=[a-zA-Z0-9]*/?v=${GIT_HASH}/g" "$INDEX_HTML"

echo "   Updated: $(grep -c '?v=' "$INDEX_HTML") asset references → ?v=${GIT_HASH}"

# 3. Install / upgrade Python dependencies
if [ -d "$VENV_DIR" ]; then
    echo ">> Upgrading Python dependencies..."
    source "$VENV_DIR/bin/activate"
    pip install -q --upgrade pip
    pip install -q -r "${APP_DIR}/requirements.txt"
else
    echo ">> Virtual environment not found. Run install.sh first."
    exit 1
fi

# 4. Restart the service
echo ">> Restarting ${SERVICE_NAME}..."
sudo systemctl restart "$SERVICE_NAME"

# 5. Health check — wait up to 10s for the service to come up
echo ">> Waiting for service to become healthy..."
for i in $(seq 1 10); do
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "   Service is running (attempt ${i})"
        break
    fi
    sleep 1
done

if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "❌ Service failed to start. Check logs:"
    echo "   sudo journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
    exit 1
fi

echo "=========================================================="
echo "✅ Deploy complete — cache-buster: ?v=${GIT_HASH}"
echo "=========================================================="
