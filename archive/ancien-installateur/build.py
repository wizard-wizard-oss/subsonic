#!/usr/bin/env python3
"""Régénère install.sh (installation complète d'un Pi neuf).

Pour mettre à jour un Pi déjà installé : python3 deploy/build_archive.py, puis deploy.sh sur le Pi."""


def rd(p):
    with open(p, encoding="utf-8") as f:
        return f.read().rstrip("\n")


launcher = rd("launcher.py")
sw_py = rd("subsonic-web.py")
import os


TREES = ("web", "pimedia", "i18n", "themes", "deploy")      # interface, code, textes, thèmes, scripts et services
EXTRA_FILES = ("launcher_classic.py",)                       # menu de secours (voir launcher.py)
SKIPPED_DIRS = {"__pycache__"}


def tree_files(tree):
    files = []
    for dp, dns, fns in os.walk(tree):
        dns[:] = sorted(d for d in dns if d not in SKIPPED_DIRS)
        for fn in sorted(fns):
            if not fn.endswith(".pyc"):
                files.append(os.path.join(dp, fn).replace(os.sep, "/"))
    return files


def web_block(root):
    """Écrit tous les fichiers de web/ (page, CSS, JS) et de subsonic_web/ (code du serveur) sous « root »."""
    files = [f for tree in TREES for f in tree_files(tree)] + list(EXTRA_FILES)
    dirs = sorted({os.path.dirname(f) for f in files if os.path.dirname(f)})
    out = ['rm -rf ' + " ".join('"%s/%s"' % (root, tree) for tree in TREES)]
    out.append("mkdir -p " + " ".join('"%s/%s"' % (root, d) for d in dirs))
    for n, f in enumerate(files):
        content = rd(f)
        tag = "WEBEOF_%d" % n
        assert ("\n" + tag) not in content, f
        out.append('cat > "%s/%s" <<\'%s\'\n%s\n%s' % (root, f, tag, content, tag))
    return "\n".join(out)

SUBSONIC_BLOCK = """echo "==> Subsonic Web (interface tactile pour votre serveur Subsonic)"
mkdir -p "$APP_DIR" "$HOME/.config/systemd/user"

cat > "$APP_DIR/subsonic-web.py" <<'PYEOF'
@@SW_PY@@
PYEOF

rm -f "$APP_DIR/subsonic-web.html"
@@WEB@@

# Scripts de réglage et de relance du menu (versions de deploy/bin, qui écrivent dans le .env)
for script in set-subsonic.sh set-podcastindex.sh start-menu.sh; do
  install -m 755 "$APP_DIR/deploy/bin/$script" "$APP_DIR/$script"
done
chmod +x "$APP_DIR/subsonic-web.py"

# Autorise le bouton « Coller » : en plein écran (kiosque), Chromium ne peut pas afficher sa demande d'autorisation.
# Politique limitée à l'adresse locale de l'interface.
sudo mkdir -p /etc/chromium/policies/managed
echo '{"ClipboardAllowedForUrls": ["http://127.0.0.1:8099"]}' | sudo tee /etc/chromium/policies/managed/pi-media-clipboard.json >/dev/null \
  || echo "Autorisation du presse-papiers non installée (sudo refusé) : le bouton Coller restera bloqué."

# Boutons Éteindre / Redémarrer du menu : autorisés sans mot de passe, et seulement ces deux commandes
SYSTEMCTL="$(command -v systemctl)"
POWER_RULE="$(mktemp)"
echo "$USER ALL=(root) NOPASSWD: $SYSTEMCTL poweroff, $SYSTEMCTL reboot" > "$POWER_RULE"
if sudo visudo -cf "$POWER_RULE" >/dev/null; then
  sudo install -m 0440 -o root -g root "$POWER_RULE" /etc/sudoers.d/pi-media-power
else
  echo "Règle d'extinction refusée par visudo : boutons Éteindre/Redémarrer non autorisés."
fi
rm -f "$POWER_RULE"

# Qualité audio : PipeWire peut passer en 44,1 kHz (AirPlay, la plupart des FLAC) au lieu de tout convertir en 48 kHz
PW_RATES="$HOME/.config/pipewire/pipewire.conf.d/10-pi-media-frequences.conf"
if command -v pipewire >/dev/null && [ ! -f "$PW_RATES" ]; then
  mkdir -p "$(dirname "$PW_RATES")"
  cat > "$PW_RATES" <<'PWEOF'
# Écrit par pi-media : fréquences que la sortie audio peut adopter selon la source (moins de conversions)
context.properties = {
    default.clock.allowed-rates = [ 44100 48000 88200 96000 ]
}
PWEOF
  systemctl --user restart pipewire pipewire-pulse wireplumber 2>/dev/null || true   # coupe le son une seconde
fi

# AirPlay : son envoyé à PipeWire (flux visible : la musique du Pi se met en pause) et lecteur pilotable (MPRIS),
# grâce à un fichier de configuration à nous ; /etc/shairport-sync.conf n'est pas touché.
SP_SERVICE="$HOME/.config/systemd/user/shairport-sync.service"
SP_CONF="$HOME/.config/shairport-sync/pi-media.conf"
if [ -f "$SP_SERVICE" ] && command -v shairport-sync >/dev/null && shairport-sync -V 2>&1 | grep -q -- "-pa-"; then
  SP_NAME="$(sed -n 's/.*-a "\\([^"]*\\)".*/\\1/p' "$SP_SERVICE" | head -1)"
  [ -n "$SP_NAME" ] || SP_NAME="$(sed -n 's/.*name = "\\([^"]*\\)".*/\\1/p' "$SP_CONF" 2>/dev/null | head -1)"
  [ -n "$SP_NAME" ] || SP_NAME="$(hostname)"
  SP_MPRIS=""
  if shairport-sync -V 2>&1 | grep -q mpris; then SP_MPRIS='mpris = { enabled = "yes"; };'; fi
  mkdir -p "$(dirname "$SP_CONF")"
  cat > "$SP_CONF" <<SPEOF
// Écrit par pi-media : AirPlay vers PipeWire (sortie PulseAudio) et lecteur MPRIS sur le bus de session
general = { name = "$SP_NAME"; output_backend = "pa"; mpris_service_bus = "Session"; dbus_service_bus = "Session"; };
pa = { application_name = "Shairport Sync"; };
$SP_MPRIS
SPEOF
  [ -f "$SP_SERVICE.avant-pi-media" ] || cp "$SP_SERVICE" "$SP_SERVICE.avant-pi-media"
  sed -i "s#^ExecStart=.*#ExecStart=/usr/bin/shairport-sync -c $SP_CONF#" "$SP_SERVICE"
  systemctl --user daemon-reload || true
  systemctl --user restart shairport-sync || true
  sleep 3
  if ! systemctl --user is-active --quiet shairport-sync; then
    echo "AirPlay : la nouvelle configuration ne démarre pas, retour à l'ancienne (journalctl --user -u shairport-sync)."
    cp "$SP_SERVICE.avant-pi-media" "$SP_SERVICE"
    systemctl --user daemon-reload || true
    systemctl --user restart shairport-sync || true
  fi
else
  echo "AirPlay : sortie PulseAudio indisponible dans cette version de shairport-sync, configuration inchangée."
fi

cat > "$HOME/.config/systemd/user/subsonic-web.service" <<EOF
[Unit]
Description=Subsonic Web (relais local + interface tactile)

[Service]
ExecStart=/usr/bin/python3 $APP_DIR/subsonic-web.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload || true
systemctl --user enable subsonic-web || true
# restart (et non « enable --now ») : un service déjà lancé garderait l'ancien code en mémoire
systemctl --user restart subsonic-web || \\
  echo "(Subsonic Web démarrera au prochain redémarrage)"
""".replace("@@SW_PY@@", sw_py).replace("@@WEB@@", web_block("$APP_DIR"))

s = open("install.sh", encoding="utf-8").read()

# 1) bloc launcher
a = "cat > \"$APP_DIR/launcher.py\" <<'PYEOF'\n"
i = s.index(a) + len(a)
j = s.index("\nPYEOF\n\ncat > \"$APP_DIR/bt-pairing.sh\"")
s = s[:i] + launcher + s[j:]

# 2) bloc Subsonic Web (remplacé s'il existe, sinon inséré avant l'étape finale)
start_marker = 'echo "==> Subsonic Web (interface tactile pour votre serveur Subsonic)"'
end_marker = 'echo "==> 7/7 Terminé"'
if start_marker in s:
    i = s.index(start_marker)
    j = s.index(end_marker)
    s = s[:i] + SUBSONIC_BLOCK + "\n" + s[j:]
else:
    s = s.replace(end_marker, SUBSONIC_BLOCK + "\n" + end_marker, 1)
s = s.replace(
    'echo "Feishin / Supersonic : ajoutez votre serveur Subsonic dans les réglages."',
    'echo "Subsonic Web : ~/.local/share/pi-media/set-subsonic.sh https://adresse utilisateur motdepasse"',
    1)
with open("install.sh", "w", encoding="utf-8") as f:
    f.write(s)

print("build OK")
