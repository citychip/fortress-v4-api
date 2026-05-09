#!/usr/bin/env bash
# Fortress Dashboard — Installation Script
# This script sets up the Python virtual environment, installs dependencies,
# configures systemd services, and generates the API token.

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${APP_DIR}/venv"
QUANT_DIR="${APP_DIR}/quant"

echo "=========================================================="
echo "🏰 Fortress Dashboard Installer"
echo "=========================================================="

# 1. System dependencies
echo ">> Checking system dependencies..."
if ! command -v python3 &> /dev/null || ! command -v pip3 &> /dev/null || ! command -v venv &> /dev/null; then
    echo "Installing Python3 and venv..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv build-essential python3-dev
fi

# 2. Virtual Environment
echo ">> Setting up Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo ">> Installing Python dependencies..."
pip install --upgrade pip
pip install -r "${APP_DIR}/requirements.txt"

# 3. Data directory setup
echo ">> Creating data directories..."
mkdir -p "${QUANT_DIR}/reports"
mkdir -p "${QUANT_DIR}/uploads"
mkdir -p "${QUANT_DIR}/backups"

if [ ! -f "${QUANT_DIR}/fortress_config.json" ]; then
    echo ">> Copying example config..."
    cp "${APP_DIR}/fortress_config.example.json" "${QUANT_DIR}/fortress_config.json"
fi

# 4. Generate API Token
echo ">> Generating secure API token..."
TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 5. Systemd Service setup
echo ">> Configuring systemd service (requires sudo)..."

SERVICE_FILE="/etc/systemd/system/fortress-dashboard.service"
sudo bash -c "cat > $SERVICE_FILE" << EOF
[Unit]
Description=Fortress Dashboard API & Web UI
After=network.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
Environment="FORTRESS_API_TOKEN=$TOKEN"
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable fortress-dashboard
sudo systemctl start fortress-dashboard

echo "=========================================================="
echo "✅ Installation Complete!"
echo "=========================================================="
echo "Dashboard is running on port 8080."
echo ""
echo "IMPORTANT: Your API Bearer Token is:"
echo "$TOKEN"
echo ""
echo "Save this token! You will need it to authenticate API requests"
echo "and it is used by the frontend dashboard automatically."
echo "To view it again later, check the systemd service file:"
echo "cat /etc/systemd/system/fortress-dashboard.service"
echo "=========================================================="
