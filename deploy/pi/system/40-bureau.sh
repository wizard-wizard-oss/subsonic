#!/usr/bin/env bash
# Démarrage automatique (labwc), raccourci « Accueil hi-fi », fenêtres des applis en plein écran.
set -euo pipefail
. "$(dirname "$0")/common.sh"
say "Démarrage automatique et raccourcis"

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/accueil-hifi.desktop" <<DESKEOF
[Desktop Entry]
Type=Application
Name=Accueil hi-fi
Exec=$APP_DIR/start-menu.sh
Icon=multimedia-audio-player
Terminal=false
Categories=AudioVideo;
DESKEOF
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
mkdir -p "$DESKTOP_DIR"
cp "$HOME/.local/share/applications/accueil-hifi.desktop" "$DESKTOP_DIR/"
chmod +x "$DESKTOP_DIR/accueil-hifi.desktop"
gio set "$DESKTOP_DIR/accueil-hifi.desktop" metadata::trusted true 2>/dev/null || true

mkdir -p "$HOME/.config/labwc"
AUTOSTART="$HOME/.config/labwc/autostart"
if [ ! -f "$AUTOSTART" ] && [ -f /etc/xdg/labwc/autostart ]; then
  cp /etc/xdg/labwc/autostart "$AUTOSTART"      # conserve barre des tâches, fond d'écran…
fi
touch "$AUTOSTART"
if ! grep -q "pi-media" "$AUTOSTART"; then
  printf '\n# pi-media\n/usr/bin/bash %s/set-hdmi-audio.sh &\n/usr/bin/python3 %s/launcher.py &\n' \
    "$APP_DIR" "$APP_DIR" >> "$AUTOSTART"
fi

python3 "$(dirname "$0")/labwc_rules.py"
