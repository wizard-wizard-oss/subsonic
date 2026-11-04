#!/usr/bin/env bash
# Installe ou met à jour Pi Media Station sur le Pi à partir d'une archive.
#
#   bash deploy.sh                                   installe l'archive pi-media-*.tar.gz la plus récente posée à côté
#   bash deploy.sh pi-media-2026.10.25-1530.tar.gz   installe cette version et la démarre
#   bash deploy.sh --configure                       (re)demande l'adresse Subsonic, l'utilisateur et le mot de passe
#   bash deploy.sh --rollback                        revient à la version précédente
#   bash deploy.sh --status                          versions installées et version active
#   bash deploy.sh --start                           (re)démarre le serveur de la version active
#
# Au premier déploiement, les réglages manquants sont demandés (le mot de passe ne s'affiche pas) ;
# une ancienne installation (config.json) est reprise telle quelle : rien à ressaisir.
#
# Le code va dans ~/.local/share/pi-media/releases/<version>/, « current » pointe sur la version active.
# Les données (.env, pi-media.db) restent dans ~/.local/share/pi-media/ : une mise à jour n'y touche pas.
# PI_MEDIA_SERVICE=direct (conteneur de test docker/pi, sans systemd) : le serveur est lancé par ce script.
set -euo pipefail

APP_DIR="${PI_MEDIA_HOME:-$HOME/.local/share/pi-media}"
RELEASES="$APP_DIR/releases"
KEEP=3
PORT="${PI_MEDIA_PORT:-8099}"
UNIT_DIR="$HOME/.config/systemd/user"
SERVICE="${PI_MEDIA_SERVICE:-systemd}"
SERVER_LOG="$APP_DIR/server.log"               # journal du serveur en mode direct

say() { echo "==> $*"; }
die() { echo "Erreur : $*" >&2; exit 1; }

active_version() { [ -L "$APP_DIR/current" ] && basename "$(readlink "$APP_DIR/current")" || true; }

activate() {                                   # bascule « current » d'un coup (pas d'état intermédiaire)
  ln -sfn "releases/$1" "$APP_DIR/current.new"
  mv -T "$APP_DIR/current.new" "$APP_DIR/current"
}

link_entry_points() {                          # chemins historiques (démarrage du menu, raccourcis) gardés
  ln -sfn current/launcher.py "$APP_DIR/launcher.py"
  for script in start-menu.sh set-subsonic.sh set-podcastindex.sh migration.sh bt-pairing.sh set-hdmi-audio.sh; do
    ln -sfn "current/deploy/bin/$script" "$APP_DIR/$script"
  done
}

install_service() {
  if [ "$SERVICE" = direct ]; then restart_direct; return; fi
  mkdir -p "$UNIT_DIR"
  cp "$APP_DIR/current/deploy/systemd/subsonic-web.service" "$UNIT_DIR/subsonic-web.service"
  systemctl --user daemon-reload
  systemctl --user enable subsonic-web >/dev/null 2>&1 || true
  systemctl --user restart subsonic-web
}

restart_direct() {                             # sans systemd : arrête le serveur en marche, lance celui de « current »
  local server="$APP_DIR/current/subsonic-web.py" name empty=()
  pkill -f "$server" 2>/dev/null || true
  for _ in $(seq 1 20); do pgrep -f "$server" >/dev/null || break; sleep 0.5; done
  for name in $(compgen -e | grep '^PI_MEDIA_'); do   # vide (compose.yaml) = pas donné : le .env du Pi s'applique
    [ -n "${!name}" ] || empty+=(-u "$name")
  done
  PI_MEDIA_DATA="$APP_DIR" setsid nohup env "${empty[@]}" python3 "$server" >>"$SERVER_LOG" 2>&1 </dev/null &
}

logs_hint() {
  if [ "$SERVICE" = direct ]; then echo "tail -n 40 $SERVER_LOG"; else echo "journalctl --user -u subsonic-web -n 40 --no-pager"; fi
}

healthy() {                                    # la version attendue répond dans les 20 secondes ?
  local expected="$1"
  for _ in $(seq 1 20); do
    curl -fsS "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q "\"version\": \"$expected\"" && return 0
    sleep 1
  done
  return 1
}

restart_menu() {
  if pgrep -f "pi-media/(current/)?launcher.py" >/dev/null 2>&1; then
    setsid -f "$APP_DIR/start-menu.sh" >/dev/null 2>&1 || true
  fi
}

ensure_packages() {                            # dépendances système (installées une seule fois)
  local missing=()
  python3 -c "import yaml" 2>/dev/null || missing+=(python3-yaml)
  command -v mpv >/dev/null || missing+=(mpv)
  command -v curl >/dev/null || missing+=(curl)
  if [ ${#missing[@]} -gt 0 ]; then
    say "Paquets manquants : ${missing[*]} (le mot de passe de la session peut être demandé)"
    sudo apt-get install -y "${missing[@]}"
  fi
}

archive_old_layout() {                         # ancienne installation (code directement dans pi-media/)
  [ -d "$APP_DIR/subsonic_web" ] || [ -d "$APP_DIR/pimedia" ] || return 0
  local backup="$APP_DIR/ancienne-installation-$(date +%Y%m%d-%H%M%S)"
  say "Ancienne installation rangée dans $backup (vos données restent en place)"
  mkdir -p "$backup"
  for old in subsonic_web pimedia web i18n themes deploy subsonic-web.py launcher.py launcher_classic.py start-menu.sh \
             set-subsonic.sh set-podcastindex.sh bt-pairing.sh set-hdmi-audio.sh; do
    if [ -e "$APP_DIR/$old" ] && [ ! -L "$APP_DIR/$old" ]; then mv "$APP_DIR/$old" "$backup/"; fi
  done
}

env_value() {                                  # valeur d'une clé du .env (vide si absente)
  [ -f "$APP_DIR/.env" ] || return 0
  sed -n "s/^$1=//p" "$APP_DIR/.env" | tail -1 | sed 's/^"\(.*\)"$/\1/'
}

ask() {                                        # ask VARIABLE "Question" [défaut] [secret]
  local answer prompt="$2"
  [ -n "${3:-}" ] && prompt="$prompt [$3]"
  if [ "${4:-}" = secret ]; then read -r -s -p "$prompt : " answer; echo; else read -r -p "$prompt : " answer; fi
  printf -v "$1" '%s' "${answer:-${3:-}}"
}

configure() {                                  # demande ce qui manque (ou tout, avec --configure)
  local force="${1:-}" url user pass
  if [ -z "$force" ] && [ -n "$(env_value SUBSONIC_URL)${PI_MEDIA_SUBSONIC_URL:-}" ]; then return 0; fi   # ou donné par l'environnement
  if [ ! -t 0 ]; then
    echo "(pas de terminal : réglages à compléter avec  $APP_DIR/set-subsonic.sh URL UTILISATEUR MOTDEPASSE)"
    return 0
  fi
  echo
  say "Réglages du serveur Subsonic (enregistrés dans $APP_DIR/.env, lisible par vous seul)"
  ask url "Adresse du serveur Subsonic (ex. https://musique.exemple.fr)" "$(env_value SUBSONIC_URL)"
  ask user "Nom d'utilisateur Subsonic" "$(env_value SUBSONIC_USER)"
  ask pass "Mot de passe Subsonic (rien ne s'affiche)" "" secret
  [ -n "$pass" ] || pass="$(env_value SUBSONIC_PASS)"
  (cd "$APP_DIR/current" && python3 -m pimedia.cli set "SUBSONIC_URL=${url%/}" "SUBSONIC_USER=$user" \
      "SUBSONIC_PASS=$pass" >/dev/null)
  say "Réglages enregistrés. Clés facultatives (Podcast Index, Jamendo, YouTube) : à saisir dans l'application."
}

prune() {                                      # garde les KEEP versions les plus récentes (et toujours l'active)
  local active; active="$(active_version)"
  ls -1t "$RELEASES" | tail -n +$((KEEP + 1)) | while read -r old; do
    [ "$old" != "$active" ] && rm -rf "${RELEASES:?}/$old"
  done
}

deploy() {
  local archive="$1" tmp version previous
  [ -f "$archive" ] || die "archive introuvable : $archive"
  ensure_packages
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  tar -xzf "$archive" -C "$tmp"
  [ -f "$tmp/VERSION" ] || die "archive invalide (fichier VERSION absent)"
  version="$(tr -cd 'A-Za-z0-9._-' < "$tmp/VERSION")"
  mkdir -p "$RELEASES"
  previous="$(active_version)"
  if [ -d "$RELEASES/$version" ]; then
    say "Version $version déjà présente : réinstallation"
    rm -rf "${RELEASES:?}/$version"
  fi
  mv "$tmp" "$RELEASES/$version"
  trap - EXIT
  archive_old_layout
  say "Activation de la version $version"
  activate "$version"
  link_entry_points
  say "Reprise des anciens réglages (secrets et clés API)"
  bash "$APP_DIR/current/deploy/bin/migration.sh" | sed 's/^/    /'
  configure
  install_service
  if healthy "$version"; then
    say "Version $version active et en marche"
    restart_menu
    prune
  elif [ -n "$previous" ] && [ "$previous" != "$version" ]; then
    echo "Le serveur ne répond pas : retour automatique à la version $previous." >&2
    echo "Détails : $(logs_hint)" >&2
    activate "$previous"
    link_entry_points
    install_service
    rm -rf "${RELEASES:?}/$version"            # version défectueuse retirée : un --rollback ne pourra pas y revenir
    exit 1
  else
    die "le serveur ne répond pas ($(logs_hint))"
  fi
}

rollback() {
  local active previous
  active="$(active_version)"
  previous="$(ls -1t "$RELEASES" 2>/dev/null | grep -vx "$active" | head -1 || true)"
  [ -n "$previous" ] || die "aucune version précédente"
  say "Retour de $active à $previous"
  activate "$previous"
  touch "$RELEASES/$previous"                  # devient la plus récente : un second rollback revient en avant
  link_entry_points
  install_service
  healthy "$previous" && restart_menu && say "Version $previous active" || die "le serveur ne répond pas"
}

status() {
  echo "Dossier : $APP_DIR"
  echo "Version active : $(active_version || echo aucune)"
  echo "Versions installées :"; ls -1t "$RELEASES" 2>/dev/null | sed 's/^/  /' || echo "  aucune"
}

latest_archive() {                             # archive la plus récente posée à côté du script (ou ici)
  ls -1t "$(dirname "$0")"/pi-media-*.tar.gz ./pi-media-*.tar.gz 2>/dev/null | head -1
}

case "${1:-}" in
  --rollback) rollback ;;
  --status) status ;;
  --start) [ -L "$APP_DIR/current" ] || die "rien d'installé"; install_service
           healthy "$(active_version)" && say "Version $(active_version) en marche" || die "le serveur ne répond pas ($(logs_hint))" ;;
  --configure) [ -L "$APP_DIR/current" ] || die "rien d'installé"; configure force; install_service
               healthy "$(active_version)" && say "Serveur redémarré avec les nouveaux réglages" ;;
  *.tar.gz) deploy "$1" ;;
  "") archive="$(latest_archive)"; [ -n "$archive" ] || die "aucune archive pi-media-*.tar.gz trouvée"
      deploy "$archive" ;;
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac
