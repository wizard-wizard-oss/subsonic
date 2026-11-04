#!/usr/bin/env bash
# Premier .env (une seule fois : vos modifications et une ancienne installation sont conservées).
# Options : DEVICE_NAME="Salon" VILLE="Lyon" LATITUDE=45.76 LONGITUDE=4.84 bash install.sh
set -euo pipefail
. "$(dirname "$0")/common.sh"
say "Réglages du menu"
mkdir -p "$APP_DIR"
if [ -f "$APP_DIR/.env" ] || [ -f "$APP_DIR/config.json" ]; then
  note "réglages existants conservés"
  exit 0
fi
umask 077
cat > "$APP_DIR/.env" <<ENVEOF
# Pi Media Station — réglages et secrets (voir .env.example). Ne jamais publier ce fichier.
DEVICE_NAME="$DEVICE_NAME"
WEATHER_CITY="${VILLE:-Lyon}"
WEATHER_LATITUDE=${LATITUDE:-45.764}
WEATHER_LONGITUDE=${LONGITUDE:-4.836}
SCREENSAVER_SECONDS=120
THEME=retro
ENVEOF
