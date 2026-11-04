#!/usr/bin/env bash
# Relance le menu tactile (remplace l'instance en cours s'il y en a une).
# Depuis SSH, pour récupérer la main : setsid -f ~/.local/share/pi-media/start-menu.sh >/dev/null 2>&1
pkill -f "[p]i-media/launcher.py" || true
pkill -f "[p]i-media/current/launcher.py" || true
sleep 0.3
export DISPLAY="${DISPLAY:-:0}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
exec python3 "$HOME/.local/share/pi-media/launcher.py"
