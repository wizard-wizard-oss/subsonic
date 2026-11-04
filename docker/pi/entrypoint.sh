#!/usr/bin/env bash
# Démarrage du conteneur de l'édition Pi : installe la version de l'image avec deploy.sh, comme sur un vrai Pi, puis
# affiche le journal du serveur (lancé par deploy.sh, PI_MEDIA_SERVICE=direct).
# Version de l'image déjà installée dans le volume : simple redémarrage de la version active (une version installée
# ensuite à la main ou un retour arrière sont gardés).
set -euo pipefail
APP_DIR="$HOME/.local/share/pi-media"
ARCHIVE="$(ls -1t /opt/pi-media/pi-media-*.tar.gz | head -1)"
VERSION="$(basename "$ARCHIVE" .tar.gz)"
VERSION="${VERSION#pi-media-}"

: > "$APP_DIR/server.log"                      # journal depuis le démarrage du conteneur
if [ -d "$APP_DIR/releases/$VERSION" ]; then
  bash /opt/pi-media/deploy.sh --start
else
  bash /opt/pi-media/deploy.sh "$ARCHIVE"
fi
exec tail -n +1 -F "$APP_DIR/server.log"
