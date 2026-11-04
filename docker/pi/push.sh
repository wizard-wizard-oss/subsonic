#!/usr/bin/env bash
# Comme deploy/pi/push.sh, mais vers le conteneur de l'édition Pi au lieu du vrai Pi : fabrique l'archive, la copie
# avec deploy.sh dans le dossier de l'utilisateur pi, puis l'installe (mise à jour, vérification /health, retour
# automatique en cas d'échec). Le conteneur doit tourner.
#
#   bash docker/pi/push.sh             service « pi »       (docker compose --profile pi up -d pi)
#   bash docker/pi/push.sh pi-demo     service « pi-demo »  (docker compose --profile pi-demo up -d pi-demo)
#
# État, retour arrière : docker compose exec pi bash /opt/pi-media/deploy.sh --status | --rollback
set -euo pipefail

SERVICE="${1:-pi}"
PROJECT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT"

echo "==> Fabrication de l'archive"
ARCHIVE="$(python3 deploy/pi/build_archive.py | tail -1)"
test -f "$ARCHIVE" || { echo "Erreur : archive introuvable ($ARCHIVE)"; exit 1; }

echo "==> Envoi dans le conteneur $SERVICE"
for file in "$ARCHIVE" "$(dirname "$ARCHIVE")/deploy.sh"; do     # par l'entrée standard : fichiers à pi, comme scp
  docker compose --profile "$SERVICE" exec -T "$SERVICE" sh -c 'cat > "$1"' copie "$(basename "$file")" < "$file"
done

echo "==> Installation"
docker compose --profile "$SERVICE" exec -T "$SERVICE" bash deploy.sh "$(basename "$ARCHIVE")"
