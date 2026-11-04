#!/usr/bin/env bash
# Enregistre le serveur Subsonic dans le .env du Pi.
# Usage : set-subsonic.sh https://adresse utilisateur motdepasse
set -euo pipefail
if [ $# -ne 3 ]; then
  echo "Usage : $0 URL UTILISATEUR MOTDEPASSE" >&2
  exit 1
fi
APP_DIR="${PI_MEDIA_HOME:-$HOME/.local/share/pi-media}"
CODE="$APP_DIR/current"; [ -d "$CODE" ] || CODE="$APP_DIR"
cd "$CODE"
python3 -m pimedia.cli set "SUBSONIC_URL=${1%/}" "SUBSONIC_USER=$2" "SUBSONIC_PASS=$3"
systemctl --user restart subsonic-web 2>/dev/null || true
echo "OK : serveur Subsonic enregistré."
