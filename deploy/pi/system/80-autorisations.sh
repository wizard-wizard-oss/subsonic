#!/usr/bin/env bash
# Autorisations limitées au strict nécessaire :
#  - bouton « Coller » de la page en kiosque (Chromium ne peut pas y afficher sa demande), adresse locale seulement ;
#  - boutons Éteindre / Redémarrer du menu, sans mot de passe, et seulement ces deux commandes.
set -euo pipefail
. "$(dirname "$0")/common.sh"
say "Autorisations (presse-papiers de la page, extinction)"
sudo mkdir -p /etc/chromium/policies/managed
echo '{"ClipboardAllowedForUrls": ["http://127.0.0.1:8099"]}' \
  | sudo tee /etc/chromium/policies/managed/pi-media-clipboard.json >/dev/null \
  || note "presse-papiers non autorisé : le bouton Coller restera bloqué"

SYSTEMCTL="$(command -v systemctl)"
RULE="$(mktemp)"
echo "$USER ALL=(root) NOPASSWD: $SYSTEMCTL poweroff, $SYSTEMCTL reboot" > "$RULE"
if sudo visudo -cf "$RULE" >/dev/null; then
  sudo install -m 0440 -o root -g root "$RULE" /etc/sudoers.d/pi-media-power
else
  note "règle refusée par visudo : boutons Éteindre/Redémarrer non autorisés"
fi
rm -f "$RULE"
