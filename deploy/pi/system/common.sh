# Variables et petites fonctions communes aux étapes d'installation (chargé par install.sh, pas lancé seul).
APP_DIR="${PI_MEDIA_HOME:-$HOME/.local/share/pi-media}"
UNIT_DIR="$HOME/.config/systemd/user"
env_value() { [ -f "$APP_DIR/.env" ] && sed -n "s/^$1=//p" "$APP_DIR/.env" | tail -1 | sed 's/^"\(.*\)"$/\1/' || true; }
# nom AirPlay / Bluetooth : variable donnée à install.sh, sinon celui du .env, sinon « Salon »
DEVICE_NAME="${DEVICE_NAME:-${AIRPLAY_NAME:-$(env_value DEVICE_NAME)}}"
DEVICE_NAME="${DEVICE_NAME:-Salon}"
say() { echo "==> $*"; }
note() { echo "    $*"; }
user_service() {                                          # user_service NOM : (re)lance un service utilisateur
  systemctl --user daemon-reload || true
  systemctl --user enable "$1" >/dev/null 2>&1 || true
  systemctl --user restart "$1" 2>/dev/null || note "($1 démarrera au prochain redémarrage)"
}
