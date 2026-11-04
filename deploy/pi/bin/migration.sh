#!/usr/bin/env bash
# Reprend les réglages de l'ancienne version (config.json) dans le .env :
# adresse, utilisateur et mot de passe Subsonic, clés API (YouTube, Jamendo, Podcast Index), réglages du menu.
# Les valeurs déjà présentes dans le .env sont gardées. Lancé automatiquement par deploy.sh ; relançable sans risque.
# Usage : bash migration.sh
set -euo pipefail
APP_DIR="${PI_MEDIA_HOME:-$HOME/.local/share/pi-media}"
CODE="$APP_DIR/current"; [ -d "$CODE/pimedia" ] || CODE="$APP_DIR"
[ -d "$CODE/pimedia" ] || { echo "Pi Media Station n'est pas installé : lancez d'abord deploy.sh" >&2; exit 1; }
cd "$CODE"
PI_MEDIA_DATA="$APP_DIR" python3 -m pimedia.cli migrate
