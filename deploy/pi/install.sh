#!/usr/bin/env bash
# Installation complète d'un Pi neuf : système (paquets, AirPlay, Bluetooth, démarrage auto…) puis l'application.
#
#   bash install.sh                       tout installer (l'archive pi-media-*.tar.gz doit être posée à côté)
#   bash install.sh --etape airplay       refaire une seule étape (paquets, applis, reglages, bureau, son,
#                                         airplay, bluetooth, autorisations)
#   Options : DEVICE_NAME="Salon" VILLE="Lyon" LATITUDE=45.76 LONGITUDE=4.84 bash install.sh
#
# Ensuite, pour les mises à jour : seulement  bash deploy.sh  (le système n'a pas à être refait).
# Prérequis : Raspberry Pi OS 64 bits avec bureau, connexion automatique au bureau, accès Internet.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
die() { echo "Erreur : $*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "lancez ce script avec votre utilisateur normal (sans sudo)"
[ "$(dpkg --print-architecture 2>/dev/null || echo arm64)" = "arm64" ] || die "il faut Raspberry Pi OS 64 bits (arm64)"

ARCHIVE="$(ls -1t "$HERE"/pi-media-*.tar.gz 2>/dev/null | head -1 || true)"
[ -n "$ARCHIVE" ] || die "aucune archive pi-media-*.tar.gz à côté de install.sh"
[ -f "$HERE/deploy.sh" ] || die "deploy.sh doit être à côté de install.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
tar -xzf "$ARCHIVE" -C "$WORK" deploy/system
STEPS="$WORK/deploy/system"

step() { bash "$STEPS/$1"; }

if [ "${1:-}" = "--etape" ]; then
  match="$(ls "$STEPS" | grep -E "^[0-9]+-${2:-}\.sh$" || true)"
  [ -n "$match" ] || die "étape inconnue : ${2:-} (choix : $(ls "$STEPS" | sed -n 's/^[0-9]*-\(.*\)\.sh$/\1/p' | tr '\n' ' '))"
  step "$match"
  exit 0
fi

step 10-paquets.sh
step 20-applis.sh
step 30-reglages.sh
bash "$HERE/deploy.sh" "$ARCHIVE"                 # l'application : code, service, réglages Subsonic
step 40-bureau.sh
step 50-son.sh
step 60-airplay.sh
step 70-bluetooth.sh
step 80-autorisations.sh

. "$STEPS/common.sh"
echo
say "Terminé. Redémarrez le Pi : sudo reboot"
echo "Apple Music : sur l'iPhone/Mac, icône AirPlay > « $DEVICE_NAME »."
echo "Bluetooth : bouton Bluetooth du menu, puis « $DEVICE_NAME » sur le téléphone."
echo "Réglages (météo, nom, thème) : $APP_DIR/.env ; mises à jour : bash deploy.sh"
