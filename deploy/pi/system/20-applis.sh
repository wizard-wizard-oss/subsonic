#!/usr/bin/env bash
# Applis facultatives : Feishin et FreeTube (.deb arm64 de leurs dépôts GitHub), Supersonic (Flatpak).
# Un échec ici n'empêche pas le reste : le menu signale simplement « introuvable ».
set -uo pipefail
. "$(dirname "$0")/common.sh"
say "Applis Feishin, FreeTube et Supersonic"

install_deb() {
  local repo="$1" dir url
  dir="$(mktemp -d)"
  # dernières versions (y compris bêta) jusqu'à trouver un .deb arm64
  url="$(curl -fsSL --max-time 20 "https://api.github.com/repos/$repo/releases?per_page=15" | python3 -c '
import json, sys
for r in json.load(sys.stdin):
    if r.get("draft"):
        continue
    for a in r["assets"]:
        n = a["name"].lower()
        if n.endswith(".deb") and ("arm64" in n or "aarch64" in n):
            print(a["browser_download_url"])
            raise SystemExit
')"
  if [ -z "$url" ]; then note "Aucun .deb arm64 trouvé pour $repo"; rm -rf "$dir"; return 1; fi
  curl -fL --max-time 300 -o "$dir/pkg.deb" "$url" && chmod -R a+rX "$dir" && sudo apt-get install -y "$dir/pkg.deb"
  rm -rf "$dir"
}
install_deb jeffvli/feishin || note "Feishin non installé"
install_deb FreeTubeApp/FreeTube || note "FreeTube non installé"

sudo apt-get install -y flatpak
sudo flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
sudo flatpak install -y --noninteractive flathub io.github.dweymouth.supersonic \
  || note "Supersonic non installé (version ARM64 indisponible ?)"
exit 0
