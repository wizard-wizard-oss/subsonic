#!/usr/bin/env bash
# AirPlay (shairport-sync) en service utilisateur, son envoyé à PipeWire (flux visible : la musique du Pi se met
# en pause) et lecteur pilotable (MPRIS). Configuration à nous : /etc/shairport-sync.conf n'est pas touché.
set -euo pipefail
. "$(dirname "$0")/common.sh"
say "AirPlay"
SP_SERVICE="$UNIT_DIR/shairport-sync.service"
SP_CONF="$HOME/.config/shairport-sync/pi-media.conf"
sudo systemctl disable --now shairport-sync 2>/dev/null || true     # le service système joue en ALSA direct
sudo systemctl enable --now avahi-daemon 2>/dev/null || true
sudo loginctl enable-linger "$USER" || true
mkdir -p "$UNIT_DIR" "$(dirname "$SP_CONF")"

if shairport-sync -V 2>&1 | grep -q -- "-pa-"; then
  SP_MPRIS=""
  if shairport-sync -V 2>&1 | grep -q mpris; then SP_MPRIS='mpris = { enabled = "yes"; };'; fi
  cat > "$SP_CONF" <<SPEOF
// Écrit par pi-media : AirPlay vers PipeWire (sortie PulseAudio) et lecteur MPRIS sur le bus de session
general = { name = "$DEVICE_NAME"; output_backend = "pa"; mpris_service_bus = "Session"; dbus_service_bus = "Session"; };
pa = { application_name = "Shairport Sync"; };
$SP_MPRIS
SPEOF
  EXEC="/usr/bin/shairport-sync -c $SP_CONF"
else
  note "sortie PulseAudio absente de cette version de shairport-sync : sortie ALSA vers PipeWire"
  EXEC="/usr/bin/shairport-sync -a \"$DEVICE_NAME\" -o alsa -- -d pipewire"
fi
cat > "$SP_SERVICE" <<UNITEOF
[Unit]
Description=AirPlay -> sortie audio par défaut (PipeWire)
After=pipewire.service pipewire-pulse.service wireplumber.service

[Service]
ExecStart=$EXEC
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
UNITEOF
user_service shairport-sync
sleep 3
if ! systemctl --user is-active --quiet shairport-sync; then
  note "AirPlay ne démarre pas : journalctl --user -u shairport-sync -n 30 --no-pager"
fi
