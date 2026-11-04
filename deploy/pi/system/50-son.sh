#!/usr/bin/env bash
# Son : PipeWire peut passer en 44,1 kHz (AirPlay, la plupart des FLAC) au lieu de tout convertir en 48 kHz.
set -euo pipefail
. "$(dirname "$0")/common.sh"
say "Fréquences audio (PipeWire)"
PW_RATES="$HOME/.config/pipewire/pipewire.conf.d/10-pi-media-frequences.conf"
if ! command -v pipewire >/dev/null; then note "PipeWire absent : rien à faire"; exit 0; fi
[ -f "$PW_RATES" ] && { note "déjà réglé"; exit 0; }
mkdir -p "$(dirname "$PW_RATES")"
cat > "$PW_RATES" <<'PWEOF'
# Écrit par pi-media : fréquences que la sortie audio peut adopter selon la source (moins de conversions)
context.properties = {
    default.clock.allowed-rates = [ 44100 48000 88200 96000 ]
}
PWEOF
systemctl --user restart pipewire pipewire-pulse wireplumber 2>/dev/null || true   # coupe le son une seconde
