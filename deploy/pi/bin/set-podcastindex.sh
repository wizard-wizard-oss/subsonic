#!/usr/bin/env bash
# Clé Podcast Index (gratuite : https://api.podcastindex.org/). Sans argument : désactive Podcast Index.
# La clé peut aussi se saisir dans la page Podcasts > Réglages.
# Usage : set-podcastindex.sh CLE SECRET
set -euo pipefail
APP_DIR="${PI_MEDIA_HOME:-$HOME/.local/share/pi-media}"
CODE="$APP_DIR/current"; [ -d "$CODE" ] || CODE="$APP_DIR"
cd "$CODE"
python3 -m pimedia.cli set "PODCASTINDEX_KEY=${1:-}" "PODCASTINDEX_SECRET=${2:-}"
systemctl --user restart subsonic-web 2>/dev/null || true
if [ -n "${1:-}" ] && [ -n "${2:-}" ]; then echo "OK : Podcast Index activé."; else echo "OK : Podcast Index désactivé."; fi
