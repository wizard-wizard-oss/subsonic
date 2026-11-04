#!/usr/bin/env bash
# Bluetooth : le Pi devient une enceinte (A2DP), appairage sans code, titre du morceau envoyé au menu (MPRIS).
set -euo pipefail
. "$(dirname "$0")/common.sh"
say "Bluetooth"
sudo systemctl enable --now bluetooth 2>/dev/null || true
sudo usermod -aG bluetooth "$USER" || true
bluetoothctl system-alias "$DEVICE_NAME" >/dev/null 2>&1 || true
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/bt-agent.service" <<'UNITEOF'
[Unit]
Description=Agent Bluetooth (appairage sans code)
After=bluetooth.target

[Service]
ExecStart=/usr/bin/bt-agent -c NoInputNoOutput
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
UNITEOF
user_service bt-agent
systemctl --user enable --now mpris-proxy 2>/dev/null || true
