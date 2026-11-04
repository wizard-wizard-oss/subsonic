#!/usr/bin/env bash
# Fabrique l'archive du Pi, l'envoie sur le Pi et l'installe (mise à jour d'un Pi déjà installé).
#
#   bash deploy/pi/push.sh pi@adresse-du-pi
#
# Pi neuf : voir install.sh (même archive, copiée à côté de install.sh puis « bash install.sh »).
# Retour arrière : ssh pi@adresse 'bash deploy.sh --rollback'
set -euo pipefail

TARGET="${1:?usage : bash deploy/pi/push.sh pi@adresse-du-pi}"
PROJECT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Fabrication de l'archive"
ARCHIVE="$(python3 "$PROJECT/deploy/pi/build_archive.py" | tail -1)"
test -f "$ARCHIVE" || { echo "Erreur : archive introuvable ($ARCHIVE)"; exit 1; }
DIST="$(dirname "$ARCHIVE")"

echo "==> Envoi sur $TARGET"
scp "$ARCHIVE" "$DIST/deploy.sh" "$TARGET:"

echo "==> Installation"
ssh "$TARGET" "bash deploy.sh '$(basename "$ARCHIVE")'"
