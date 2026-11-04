#!/usr/bin/env bash
# ------------------------------------------------------------------
# Pi media station
#   Raspberry Pi 4B + écran tactile officiel 7" (DSI) + ampli
#   - Feishin    : client Subsonic/Navidrome
#   - Supersonic : client Subsonic (via Flatpak)
#   - FreeTube   : YouTube sans pub
#   - Radios     : écran de radios (mpv), liste modifiable
#   - AirPlay    : shairport-sync -> Apple Music depuis iPhone/Mac
#   - Bluetooth  : le Pi devient une enceinte Bluetooth (A2DP)
#   - Accueil rétro hi-fi : horloge, météo, volume, titre en cours
#   - Veille     : horloge + météo après quelques minutes d'inactivité
#   - Sortie audio USB par défaut (sinon HDMI)
#
# Prérequis : Raspberry Pi OS 64 bits AVEC bureau (Bookworm ou Trixie),
#             connexion automatique au bureau activée, accès Internet.
# Usage     : bash install.sh            (en utilisateur normal, pas root)
#   Options : AIRPLAY_NAME="Salon" VILLE="Lyon" LATITUDE=45.76 LONGITUDE=4.84 bash install.sh
#             (nom AirPlay/Bluetooth, et ville pour la météo ; modifiables ensuite
#              dans ~/.local/share/pi-media/config.json)
# ------------------------------------------------------------------
set -euo pipefail

AIRPLAY_NAME="${AIRPLAY_NAME:-Salon}"
VILLE="${VILLE:-Lyon}"
LATITUDE="${LATITUDE:-45.764}"
LONGITUDE="${LONGITUDE:-4.836}"
APP_DIR="$HOME/.local/share/pi-media"

if [ "$(id -u)" -eq 0 ]; then
  echo "Lancez ce script avec votre utilisateur normal (sans sudo)." >&2
  exit 1
fi
if [ "$(dpkg --print-architecture)" != "arm64" ]; then
  echo "Il faut Raspberry Pi OS 64 bits (arm64)." >&2
  exit 1
fi

echo "==> 1/7 Paquets système"
sudo apt update
sudo apt install -y shairport-sync avahi-daemon pulseaudio-utils \
  pipewire-alsa python3-tk python3-numpy curl mpv playerctl wtype \
  bluez bluez-tools libspa-0.2-bluetooth
sudo usermod -aG input "$USER" || true   # lecture des touchers pour la veille

echo "==> 2/7 Feishin, FreeTube et Supersonic"
install_deb() {
  local repo="$1" dir url
  dir="$(mktemp -d)"
  # On parcourt les dernières versions (y compris bêta) jusqu'à trouver un .deb arm64
  url="$(curl -fsSL "https://api.github.com/repos/$repo/releases?per_page=15" | python3 -c '
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
  if [ -z "$url" ]; then
    echo "Aucun .deb arm64 trouvé pour $repo" >&2
    return 1
  fi
  curl -fL -o "$dir/pkg.deb" "$url"
  chmod -R a+rX "$dir"
  sudo apt install -y "$dir/pkg.deb"
  rm -rf "$dir"
}
install_deb jeffvli/feishin
install_deb FreeTubeApp/FreeTube

echo "    Supersonic (client Subsonic, via Flatpak)"
sudo apt install -y flatpak
sudo flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
if ! sudo flatpak install -y --noninteractive flathub io.github.dweymouth.supersonic; then
  echo "AVERTISSEMENT : Supersonic n'a pas pu être installé (version ARM64 indisponible ?)." >&2
  echo "Le reste de l'installation continue." >&2
fi

echo "==> 3/7 Menu tactile, radios, veille et réglage audio"
mkdir -p "$APP_DIR"

# Réglages (créés une seule fois dans le .env, vos modifications sont conservées)
if [ ! -f "$APP_DIR/.env" ] && [ ! -f "$APP_DIR/config.json" ]; then
  umask 077
  cat > "$APP_DIR/.env" <<ENVEOF
# Pi Media Station — réglages et secrets (voir .env.example). Ne jamais publier ce fichier.
DEVICE_NAME="$AIRPLAY_NAME"
WEATHER_CITY="$VILLE"
WEATHER_LATITUDE=$LATITUDE
WEATHER_LONGITUDE=$LONGITUDE
SCREENSAVER_SECONDS=120
ENVEOF
  umask 022
fi

cat > "$APP_DIR/launcher.py" <<'PYEOF'
#!/usr/bin/env python3
"""Menu tactile hi-fi années 80 : applis, radios, Bluetooth, volume, veille."""
import glob
import json
import os
import re
import select
import shutil
import subprocess
import threading
import time
import urllib.request
import tkinter as tk

HOME = os.path.expanduser("~")
APP_DIR = os.path.join(HOME, ".local/share/pi-media")
CFG = {"nom": "Salon", "ville": "Lyon", "latitude": 45.764,
       "longitude": 4.836, "veille_secondes": 120,
       "web_url": "http://127.0.0.1:8099/"}
# Réglages du menu : .env du dossier de données (clés anglaises), sinon ancien config.json
ENV_KEYS = {"DEVICE_NAME": ("nom", str), "WEATHER_CITY": ("ville", str), "WEATHER_LATITUDE": ("latitude", float),
            "WEATHER_LONGITUDE": ("longitude", float), "SCREENSAVER_SECONDS": ("veille_secondes", int),
            "WEB_URL": ("web_url", str)}


def load_settings():
    try:
        with open(os.path.join(APP_DIR, "config.json"), encoding="utf-8") as f:
            CFG.update(json.load(f))
    except Exception:
        pass
    try:
        with open(os.path.join(APP_DIR, ".env"), encoding="utf-8") as f:
            for line in f:
                key, sep, value = line.strip().partition("=")
                if sep and key in ENV_KEYS and not key.startswith("#"):
                    name, kind = ENV_KEYS[key]
                    CFG[name] = kind(value.strip().strip('"').strip("'"))
    except Exception:
        pass


load_settings()

# Radios : (nom, adresse du flux). Modifiez librement cette liste ;
# si une radio ne démarre plus, son adresse a probablement changé.
STATIONS = [
    ("FIP", "https://icecast.radiofrance.fr/fip-hifi.aac"),
    ("France Inter", "https://icecast.radiofrance.fr/franceinter-midfi.mp3"),
    ("France Musique", "https://icecast.radiofrance.fr/francemusique-midfi.mp3"),
    ("France Culture", "https://icecast.radiofrance.fr/franceculture-midfi.mp3"),
    ("TSF Jazz", "https://tsfjazz.ice.infomaniak.ch/tsfjazz-high.mp3"),
    ("Radio Paradise", "https://stream.radioparadise.com/mp3-192"),
    ("SomaFM Groove Salad", "https://ice1.somafm.com/groovesalad-128-mp3"),
    ("KEXP (Seattle)", "https://kexp.streamguys1.com/kexp160.aac"),
    ("Radio Paradise FLAC", "https://stream.radioparadise.com/flac"),
]

# Palette hi-fi années 80 : vert phosphore sur noir
BG = "#040a04"        # fond
PANEL = "#0b1a0d"     # façade des boutons
PANEL_ON = "#14301a"  # bouton pressé
EDGE = "#1f6b2f"      # liseré
GREEN = "#39ff6e"     # texte principal (phosphore)
SOFT = "#9be8ae"      # texte secondaire
DIM = "#2f9a4c"       # texte discret
WARN = "#ffd23f"
RED = "#7f1d1d"

ENV = dict(os.environ, ELECTRON_OZONE_PLATFORM_HINT="auto")
# Applis Electron en Wayland natif : défilement au doigt + clavier tactile
ELECTRON_FLAGS = ["--ozone-platform=wayland", "--enable-wayland-ime"]
current = None        # application lancée (processus)
current_name = None   # nom de la commande de l'appli lancée
watcher_ok = False    # True si on peut détecter les touchers même hors du menu
# applis musique : la veille peut passer dessus (comparaison sur le nom du programme)
SAVER_APPS = ("feishin", "flatpak", "chromium", "chromium-browser")
radio_proc = None     # processus mpv de la radio
radio_txt = ""        # texte "En écoute : ..."
last_activity = time.time()
saver_visible = False
tick_count = 0

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def meteo_texte(code):
    if code == 0:
        return "Ciel dégagé"
    if code in (1, 2):
        return "Éclaircies"
    if code == 3:
        return "Couvert"
    if code in (45, 48):
        return "Brouillard"
    if 51 <= code <= 57:
        return "Bruine"
    if 61 <= code <= 67:
        return "Pluie"
    if 71 <= code <= 77 or code in (85, 86):
        return "Neige"
    if 80 <= code <= 82:
        return "Averses"
    if code >= 95:
        return "Orage"
    return "Variable"


weather = {"main": "Météo indisponible", "sub": ""}
np = {"txt": ""}   # titre en cours (MPRIS : Feishin, Supersonic...)


def weather_loop():
    while True:
        try:
            url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                   "&current=temperature_2m,weather_code"
                   "&daily=temperature_2m_max,temperature_2m_min"
                   "&timezone=auto&forecast_days=1"
                   % (CFG["latitude"], CFG["longitude"]))
            with urllib.request.urlopen(url, timeout=10) as r:
                d = json.load(r)
            t = round(d["current"]["temperature_2m"])
            code = int(d["current"]["weather_code"])
            mx = round(d["daily"]["temperature_2m_max"][0])
            mn = round(d["daily"]["temperature_2m_min"][0])
            weather["main"] = "%d°C · %s" % (t, meteo_texte(code))
            weather["sub"] = "%s · min %d° / max %d°" % (CFG["ville"], mn, mx)
        except Exception:
            pass
        time.sleep(900)


def mpris_loop():
    while True:
        txt = ""
        if shutil.which("playerctl"):
            try:
                out = subprocess.run(
                    ["playerctl", "-a", "metadata", "--format",
                     "{{status}}|{{artist}} – {{title}}"],
                    capture_output=True, text=True, timeout=5).stdout
                for line in out.splitlines():
                    if line.startswith("Playing|"):
                        txt = line.split("|", 1)[1].strip(" –")
                        break
            except Exception:
                pass
        np["txt"] = txt
        time.sleep(3)


def sink_inputs():
    """Flux audio en cours (PipeWire/PulseAudio) : liste de dicts {id, corked, bin, name}."""
    out = subprocess.run(["pactl", "list", "sink-inputs"], capture_output=True,
                         text=True, timeout=3).stdout
    res, cur_in = [], None
    for line in out.splitlines():
        m = re.match(r"Sink Input #(\d+)", line)
        if m:
            cur_in = {"id": int(m.group(1)), "corked": False, "bin": "", "name": ""}
            res.append(cur_in)
            continue
        if cur_in is None:
            continue
        s = line.strip()
        if s.startswith("Corked:"):
            cur_in["corked"] = s.split(":", 1)[1].strip() == "yes"
        elif s.startswith("application.process.binary"):
            cur_in["bin"] = s.split("=", 1)[1].strip().strip('"').lower()
        elif s.startswith("application.name"):
            cur_in["name"] = s.split("=", 1)[1].strip().strip('"').lower()
    return res


HIFI_STREAM = "pi-media-hifi"   # mpv de la lecture haute fidélité : c'est le lecteur de la page, pas la radio


def stream_label(stream):
    """Nom qui identifie un flux : le nom d'application pour la haute fidélité, sinon le programme."""
    if HIFI_STREAM in stream["name"]:
        return HIFI_STREAM
    return stream["bin"] or stream["name"]


def app_of(name):
    """Famille d'application d'un flux audio, d'après son nom de programme."""
    n = (name or "").lower()
    if HIFI_STREAM in n:
        return "web"            # se met en pause par la page, comme le lecteur du navigateur
    if "mpv" in n:
        return "mpv"
    if "chrom" in n:
        return "web"
    if "feishin" in n or "electron" in n:
        return "feishin"
    if "shairport" in n:
        return "airplay"
    if "bluez" in n or "bluetooth" in n:
        return "bluetooth"
    return n or "inconnu"


def decide(prev, running):
    """Le dernier qui démarre gagne. prev / running : {id_flux: nom_programme}.
    Retourne la liste des familles à faire taire (celles déjà en cours, d'une autre
    famille que celle(s) qui viennent de démarrer)."""
    new = {k: v for k, v in running.items() if k not in prev}
    if not new:
        return []
    new_apps = {app_of(v) for v in new.values()}
    silence_apps = []
    for k, v in running.items():
        a = app_of(v)
        if k not in new and a not in new_apps and a not in silence_apps:
            silence_apps.append(a)
    return silence_apps


def players_matching(word):
    try:
        out = subprocess.run(["playerctl", "-l"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return []
    return [p for p in out.split() if word in p.lower()]


def silence(app):
    try:
        if app == "mpv":
            stop_radio()
        elif app == "web":      # lecteur web du Pi : pause demandée directement à la page
            urllib.request.urlopen(CFG["web_url"].rstrip("/") + "/control/send?cmd=pause", timeout=2).read()
        elif app == "feishin":
            for p in players_matching("feishin"):
                subprocess.run(["playerctl", "-p", p, "pause"], capture_output=True, timeout=3)
        elif app == "bluetooth":
            for p in players_matching("bluez"):
                subprocess.run(["playerctl", "-p", p, "pause"], capture_output=True, timeout=3)
        elif app == "airplay":  # on ne peut pas mettre AirPlay en pause : on coupe la session
            subprocess.run(["systemctl", "--user", "restart", "shairport-sync"],
                           capture_output=True, timeout=10)
    except Exception:
        pass


def arbiter_loop():
    """Surveille les flux audio : quand une source démarre (AirPlay, radio, lecteur web,
    Bluetooth...), les autres sources en cours sont arrêtées pour ne jamais se mélanger."""
    prev = {}
    while True:
        try:
            running = {i["id"]: stream_label(i) for i in sink_inputs() if not i["corked"]}
            for app in decide(prev, running):
                silence(app)
            prev = running
        except Exception:
            pass
        time.sleep(1.2)


def vol_get():
    try:
        out = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                             capture_output=True, text=True, timeout=3).stdout
        m = re.search(r"(\d+)%", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


# ---------- Égaliseur à segments (façon chaîne hi-fi des années 80) ----------
NB = 20                      # nombre de colonnes
SEG = 8                      # segments par colonne
SEG_ON = [GREEN] * 5 + [WARN] + ["#ff4b3a"] * 2
SEG_OFF = "#0a2410"
levels = [0.0] * NB          # niveaux 0..1, mis à jour par spectrum_loop


def audio_playing():
    """Vrai si un programme envoie réellement du son (flux non en pause).
    L'égaliseur lui-même n'en est pas un : il écoute, il n'envoie rien."""
    try:
        return any(not i["corked"] for i in sink_inputs())
    except Exception:
        return False


def spectrum_loop():
    """Analyse le son réellement diffusé (toutes sources : Feishin, AirPlay,
    Bluetooth, radio...) via le moniteur de la sortie audio par défaut.
    On n'écoute la sortie que lorsqu'un son est joué : écouter en permanence empêchait PipeWire
    de mettre la sortie en veille, et l'ampli ne s'éteignait jamais tout seul."""
    try:
        import numpy as npy
    except Exception:
        return
    n = 1024
    win = npy.hanning(n)
    edges = npy.logspace(npy.log10(2), npy.log10(n // 2), NB + 1).astype(int)
    reads_between_checks = 40              # ~2 s de son à 22 050 Hz par blocs de 1 024
    while True:
        if not audio_playing():
            for i in range(NB):
                levels[i] = 0.0             # barres éteintes : rien ne joue
            time.sleep(2)
            continue
        p = None
        try:
            p = subprocess.Popen(
                ["parec", "-d", "@DEFAULT_MONITOR@", "--format=s16le",
                 "--rate=22050", "--channels=1", "--latency-msec=40"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            reads = 0
            while True:
                buf = p.stdout.read(n * 2)
                if len(buf) < n * 2:
                    break
                reads += 1
                if reads % reads_between_checks == 0 and not audio_playing():
                    break                   # plus rien ne joue : on lâche la sortie pour qu'elle se mette en veille
                x = npy.frombuffer(buf, dtype=npy.int16).astype(npy.float32) / 32768.0
                spec = npy.abs(npy.fft.rfft(x * win)) / n
                for i in range(NB):
                    lo = int(edges[i])
                    hi = max(int(edges[i + 1]), lo + 1)
                    db = 20 * npy.log10(float(spec[lo:hi].mean()) + 1e-7)
                    lvl = min(1.0, max(0.0, (db + 85) / 50))
                    levels[i] = max(lvl, levels[i] * 0.82)
        except Exception:
            pass
        finally:
            if p is not None:
                try:
                    p.kill()
                except Exception:
                    pass
        time.sleep(1)


def draw_eq(eq):
    for i in range(NB):
        n = int(levels[i] * SEG + 0.5)
        old = eq["lit"][i]
        if n == old:
            continue
        for s in range(min(n, old), max(n, old)):
            eq["canvas"].itemconfig(eq["segs"][i][s],
                                    fill=SEG_ON[s] if s < n else SEG_OFF)
        eq["lit"][i] = n


status = tk.StringVar()
nowplaying = tk.StringVar()
vol_txt = tk.StringVar(value="VOL --")


def show(frame):
    frame.place(x=0, y=0, relwidth=1, relheight=1)
    frame.lift()


def activity(_event=None):
    global last_activity
    last_activity = time.time()


root.bind_all("<Motion>", activity)
root.bind_all("<Button>", activity)


def make_button(parent, text, command, size=18, **grid):
    b = tk.Button(parent, text=text.upper(), font=font(size),
                  bg=PANEL, fg=GREEN, activebackground=PANEL_ON,
                  activeforeground=GREEN, bd=0, relief="flat",
                  highlightthickness=2, highlightbackground=EDGE,
                  highlightcolor=GREEN, command=command)
    b.grid(sticky="nsew", padx=px(5), pady=px(5), **grid)
    return b


def small_button(parent, text, command, bg=PANEL, **pack):
    b = tk.Button(parent, text=text, font=font(13), bg=bg, fg=GREEN,
                  activebackground=PANEL_ON, activeforeground=GREEN, bd=0,
                  highlightthickness=1, highlightbackground=EDGE,
                  padx=px(12), pady=px(4), command=command)
    b.pack(**pack)
    return b


# ---------- Accueil ----------
home = tk.Frame(root, bg=BG)
home.columnconfigure((0, 1, 2), weight=1, uniform="c")
home.rowconfigure(1, weight=1, uniform="r")
home.rowconfigure(2, weight=1, uniform="r")

head = tk.Frame(home, bg=BG)
head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=px(10), pady=(px(6), 0))
h_clock = tk.Label(head, text="--:--", fg=GREEN, bg=BG, font=font(34))
h_clock.pack(side="left")
h_info = tk.Frame(head, bg=BG)
h_info.pack(side="left", padx=px(14))
h_date = tk.Label(h_info, text="", fg=SOFT, bg=BG, font=font(14, False, False))
h_date.pack(anchor="w")
h_meteo = tk.Label(h_info, text="", fg=DIM, bg=BG, font=font(12, False, False))
h_meteo.pack(anchor="w")
eq_home = make_eq(head, px(200), px(40), BG)
eq_home["canvas"].pack(side="right")


def launch(cmd):
    global current, current_name
    if current is not None:
        return
    exe = shutil.which(cmd[0])
    if not exe:
        status.set("%s introuvable" % cmd[0])
        return
    status.set("")
    stop_radio()      # pas deux sons en même temps
    current = subprocess.Popen([exe] + cmd[1:], env=ENV)
    current_name = cmd[0]
    activity()
    root.withdraw()


def web_ui(path=""):
    """Interface web (servie par subsonic-web.py) dans une fenêtre dédiée : musique Subsonic,
    ou la page « /podcasts ». Profil séparé : sinon Chromium se greffe sur une instance
    existante et se ferme aussitôt."""
    exe = shutil.which("chromium") or shutil.which("chromium-browser")
    if not exe:
        status.set("Chromium introuvable")
        return
    launch([exe, "--app=" + CFG["web_url"].rstrip("/") + (path or "/"), "--kiosk",   # plein écran total, sans barre
            "--autoplay-policy=no-user-gesture-required",
            "--user-data-dir=" + os.path.join(HOME, ".config/pi-media-chromium"),
            "--no-first-run", "--password-store=basic"])


def bluetooth():
    script = os.path.join(APP_DIR, "bt-pairing.sh")
    subprocess.Popen([script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    status.set("Bluetooth : cherchez « %s » (2 min)" % CFG["nom"])


def confirm_here(question, on_yes):
    """Confirmation affichée DANS la fenêtre du menu. La boîte de dialogue système passait derrière
    le plein écran et ne recevait plus le toucher : le Pi restait bloqué."""
    veil = tk.Frame(root, bg=BG)
    veil.place(x=0, y=0, relwidth=1, relheight=1)
    veil.lift()
    box = tk.Frame(veil, bg=PANEL, highlightthickness=2, highlightbackground=EDGE)
    box.place(relx=0.5, rely=0.5, anchor="center")
    tk.Label(box, text=question, fg=GREEN, bg=PANEL, font=font(20),
             padx=px(30), pady=px(24)).pack()
    buttons = tk.Frame(box, bg=PANEL)
    buttons.pack(pady=(0, px(20)))

    def answer(yes):
        if not veil.winfo_exists():
            return
        veil.destroy()
        if yes:
            on_yes()

    # Des étiquettes qui réagissent dès l'appui, et non des tk.Button : au toucher, un bouton Tk qui vient
    # d'apparaître ne voit pas le pointeur « entrer » et ignore le relâchement (le menu semblait figé).
    for text, yes in (("Non", False), ("Oui", True)):
        key = tk.Label(buttons, text=text, font=font(20), bg=PANEL_ON, fg=GREEN, highlightthickness=1,
                       highlightbackground=EDGE, padx=px(40), pady=px(12), cursor="hand2")
        key.bind("<ButtonPress-1>", lambda _e, y=yes: answer(y))
        key.pack(side="left", padx=px(14))
    veil.bind("<ButtonPress-1>", lambda _e: answer(False))       # toucher à côté = « Non »
    root.after(20000, lambda: answer(False))                      # sans réponse : on n'insiste pas


POWER_COMMANDS = (
    # --no-ask-password : sans droit suffisant, systemctl échoue au lieu d'ouvrir une demande de mot de passe
    # cachée derrière le plein écran (c'est ce qui figeait le menu)
    ["systemctl", "--no-ask-password"],
    ["sudo", "-n", "systemctl"],          # -n : jamais de question ; autorisé par /etc/sudoers.d/pi-media-power
)


def run_power(action, label):
    """Exécutée hors de la boucle de l'interface : le menu reste toujours utilisable."""
    for prefix in POWER_COMMANDS:
        try:
            if subprocess.run(prefix + [action], capture_output=True, timeout=20).returncode == 0:
                return
        except (OSError, subprocess.TimeoutExpired):
            continue
    root.after(0, lambda: status.set("%s : refusé par le système" % label))


def power(action, label):
    def start():
        status.set("%s en cours…" % label)
        threading.Thread(target=run_power, args=(action, label), daemon=True).start()
    confirm_here("%s le Raspberry Pi ?" % label, start)


def to_desktop():
    """Réduit le menu : la barre du bureau redevient accessible.
    Pour revenir au menu, touchez son icône dans la barre des tâches."""
    root.attributes("-fullscreen", False)
    root.iconify()


def refullscreen():
    """Le compositeur rend parfois la fenêtre « agrandie » mais pas en vrai plein écran :
    on bascule hors puis dans le plein écran pour forcer l'état."""
    root.attributes("-fullscreen", False)
    root.update_idletasks()
    root.after(150, lambda: root.attributes("-fullscreen", True))


def on_map(event):
    if event.widget is root:
        root.after(200, refullscreen)


root.bind("<Map>", on_map)


def vol_change(delta):
    cur = vol_get()
    if cur is None:
        status.set("Volume indisponible")
        return
    new = max(0, min(100, cur + delta))
    subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "%d%%" % new])
    vol_txt.set("VOL %d%%" % new)


buttons = [
    ("Musique\nSubsonic", web_ui),
    ("YouTube\nFreeTube", lambda: launch(["freetube"] + ELECTRON_FLAGS)),
    ("Radio", lambda: show(radio)),
    ("Podcasts", lambda: web_ui("/podcasts")),
    ("Bluetooth\nAppairage", bluetooth),
    ("Horloge", lambda: show_saver()),
]
for i, (text, cmd) in enumerate(buttons):
    make_button(home, text, cmd, size=18, row=1 + i // 3, column=i % 3)

foot = tk.Frame(home, bg=BG)
foot.grid(row=3, column=0, columnspan=3, sticky="ew", padx=px(8), pady=(0, px(6)))
tk.Label(foot, textvariable=nowplaying, fg=GREEN, bg=BG, anchor="w",
         font=font(12, False, False)).pack(side="left")
tk.Label(foot, textvariable=status, fg=WARN, bg=BG, anchor="w",
         font=font(11, False, False)).pack(side="left", padx=(px(10), 0))
small_button(foot, "Éteindre", lambda: power("poweroff", "Éteindre"),
             side="right", padx=px(2))
small_button(foot, "Redémarrer", lambda: power("reboot", "Redémarrer"),
             side="right", padx=px(2))
small_button(foot, "Bureau", to_desktop, side="right", padx=px(2))

# ---------- Radios ----------
radio = tk.Frame(root, bg=BG)
radio.columnconfigure((0, 1, 2), weight=1, uniform="c")
radio.rowconfigure((0, 1, 2), weight=1, uniform="r")


def stop_radio():
    global radio_proc, radio_txt
    if radio_proc is not None and radio_proc.poll() is None:
        radio_proc.terminate()
    radio_proc = None
    radio_txt = ""


def play(name, url):
    global radio_proc, radio_txt
    stop_radio()
    try:      # met en pause les autres lecteurs (Subsonic Web, Feishin...)
        subprocess.run(["playerctl", "-a", "pause"], capture_output=True, timeout=3)
    except Exception:
        pass
    try:      # et demande directement au lecteur web de se mettre en pause
        urllib.request.urlopen(CFG["web_url"].rstrip("/") + "/control/send?cmd=pause", timeout=2).read()
    except Exception:
        pass
    if not shutil.which("mpv"):
        status.set("mpv introuvable")
        return
    radio_proc = subprocess.Popen(
        ["mpv", "--no-video", "--really-quiet", "--cache=yes", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    radio_txt = "En écoute : %s" % name


for i, (name, url) in enumerate(STATIONS[:9]):
    make_button(radio, name, lambda n=name, u=url: play(n, u),
                size=15, row=i // 3, column=i % 3)

rbar = tk.Frame(radio, bg=BG)
rbar.grid(row=3, column=0, columnspan=3, sticky="ew", padx=px(8), pady=(0, px(6)))
tk.Label(rbar, textvariable=nowplaying, fg=GREEN, bg=BG,
         font=font(13, False, False)).pack(side="left")
small_button(rbar, "Retour", lambda: show(home), side="right", padx=px(2))
small_button(rbar, "Arrêter la radio", stop_radio, bg=RED, side="right", padx=px(2))

# ---------- Veille : horloge + météo ----------
saver = tk.Frame(root, bg="black")
clock_lbl = tk.Label(saver, text="", fg=GREEN, bg="black", font=font(72))
date_lbl = tk.Label(saver, text="", fg=SOFT, bg="black", font=font(20, False, False))
meteo_lbl = tk.Label(saver, text="", fg=GREEN, bg="black", font=font(24, False, False))
sub_lbl = tk.Label(saver, text="", fg=DIM, bg="black", font=font(14, False, False))
play_lbl = tk.Label(saver, textvariable=nowplaying, fg=SOFT, bg="black",
                    font=font(14, False, False))
for w, pad in ((clock_lbl, (px(16), 0)), (date_lbl, (0, px(8))),
               (meteo_lbl, (px(4), 0)), (sub_lbl, (0, px(8))),
               (play_lbl, (px(4), 0))):
    w.pack(pady=pad)
eq_saver = make_eq(saver, px(440), px(80), "black")
eq_saver["canvas"].pack(pady=(px(12), 0))

# Volume sur l'écran de veille (un toucher ailleurs ramène à l'appli / au menu)
vrow = tk.Frame(saver, bg="black")
for _txt, _delta in (("−", -5), ("+", 5)):
    _btn = tk.Button(vrow, text=_txt, font=font(22), bg=PANEL, fg=GREEN,
                     activebackground=PANEL_ON, activeforeground=GREEN, bd=0,
                     highlightthickness=1, highlightbackground=EDGE, width=3,
                     command=lambda d=_delta: vol_change(d))
    if _delta < 0:
        _btn.pack(side="left")
        tk.Label(vrow, textvariable=vol_txt, fg=SOFT, bg="black", width=10,
                 font=font(18)).pack(side="left", padx=px(8))
    else:
        _btn.pack(side="left")
vrow.pack(pady=(px(12), 0))


def refresh_clock():
    t = time.localtime()
    hhmm = time.strftime("%H:%M", t)
    date = "%s %d %s" % (JOURS[t.tm_wday], t.tm_mday, MOIS[t.tm_mon - 1])
    clock_lbl.config(text=hhmm)
    date_lbl.config(text=date)
    meteo_lbl.config(text=weather["main"])
    sub_lbl.config(text=weather["sub"])
    h_clock.config(text=hhmm)
    h_date.config(text=date)
    h_meteo.config(text=weather["main"])


def show_saver():
    global saver_visible
    saver_visible = True
    refresh_clock()
    show(saver)


def hide_saver(_event=None):
    global saver_visible
    saver_visible = False
    activity()
    if current is not None:
        root.withdraw()      # retour à l'appli qui joue
    else:
        show(home)


saver.bind("<Button-1>", hide_saver)
for w in saver.winfo_children():
    if w is not vrow:
        w.bind("<Button-1>", hide_saver)


def input_watcher():
    """Détecte les touchers/souris/clavier même quand une appli est au premier plan."""
    global last_activity, watcher_ok
    fds = []
    for p in glob.glob("/dev/input/event*"):
        try:
            fds.append(os.open(p, os.O_RDONLY | os.O_NONBLOCK))
        except OSError:
            pass
    if not fds:
        return
    watcher_ok = True
    while True:
        ready, _, _ = select.select(fds, [], [], 5)
        for fd in ready:
            try:
                os.read(fd, 4096)
            except OSError:
                pass
        if ready:
            last_activity = time.time()


def tick():
    global current, current_name, radio_proc, radio_txt, saver_visible, tick_count
    tick_count += 1
    if current is not None and current.poll() is not None:
        current = None
        current_name = None
        saver_visible = False
        root.deiconify()
        root.attributes("-fullscreen", True)
        show(home)
        activity()
    if radio_proc is not None and radio_proc.poll() is not None:
        radio_proc = None
        radio_txt = "Radio interrompue"
    nowplaying.set(radio_txt or ("♪ " + np["txt"] if np["txt"] else ""))
    refresh_clock()
    if tick_count % 5 == 1:
        v = vol_get()
        if v is not None:
            vol_txt.set("VOL %d%%" % v)
    if not saver_visible and time.time() - last_activity > CFG["veille_secondes"]:
        if current is None:
            show_saver()
        elif watcher_ok and os.path.basename(current_name or "") in SAVER_APPS:
            # appli musique au premier plan : l'horloge passe dessus,
            # un toucher ramène à l'appli (qui continue de jouer)
            root.deiconify()
            root.attributes("-fullscreen", True)
            show_saver()
    root.after(1000, tick)


def anim():
    """Rafraîchit l'égaliseur (~12 images/s) sur l'écran visible uniquement."""
    if saver_visible:
        draw_eq(eq_saver)
    elif current is None:
        draw_eq(eq_home)
    root.after(80, anim)


threading.Thread(target=weather_loop, daemon=True).start()
threading.Thread(target=mpris_loop, daemon=True).start()
threading.Thread(target=input_watcher, daemon=True).start()
threading.Thread(target=spectrum_loop, daemon=True).start()
def awake_loop():
    """L'interface web (paroles affichées) demande qu'on ne lance pas l'écran de veille."""
    global last_activity
    while True:
        try:
            with urllib.request.urlopen(CFG["web_url"].rstrip("/") + "/control/awake", timeout=2) as r:
                if json.loads(r.read().decode()).get("awake"):
                    last_activity = time.time()
        except Exception:
            pass
        time.sleep(10)


threading.Thread(target=arbiter_loop, daemon=True).start()
threading.Thread(target=awake_loop, daemon=True).start()
show(home)
root.after(500, tick)
root.after(700, anim)
root.mainloop()
PYEOF

cat > "$APP_DIR/bt-pairing.sh" <<'SHEOF'
#!/usr/bin/env bash
# Mode appairage Bluetooth pendant 2 minutes. Les appareils appairés sont
# ensuite "de confiance" et se reconnectent tout seuls.
bluetoothctl power on >/dev/null
bluetoothctl pairable on >/dev/null
bluetoothctl discoverable on >/dev/null
for _ in $(seq 1 60); do
  for mac in $(bluetoothctl devices Paired 2>/dev/null | awk '{print $2}'); do
    bluetoothctl trust "$mac" >/dev/null 2>&1
  done
  sleep 2
done
bluetoothctl discoverable off >/dev/null
bluetoothctl pairable off >/dev/null
SHEOF

cat > "$APP_DIR/set-hdmi-audio.sh" <<'SHEOF'
#!/usr/bin/env bash
# Choisit la sortie audio par défaut : USB (ampli en USB) sinon HDMI.
# Pour forcer une sortie précise, mettre son nom (pactl list short sinks)
# dans ~/.local/share/pi-media/hdmi-sink
OVERRIDE="$HOME/.local/share/pi-media/hdmi-sink"
sink=""
for _ in $(seq 1 30); do
  if [ -s "$OVERRIDE" ]; then
    sink="$(head -n1 "$OVERRIDE")"
  else
    all="$(pactl list short sinks 2>/dev/null | awk '{print $2}' || true)"
    sink="$(echo "$all" | grep -i usb | sort | head -n1 || true)"
    [ -n "$sink" ] || sink="$(echo "$all" | grep -i hdmi | sort | head -n1 || true)"
  fi
  [ -n "$sink" ] && break
  sleep 1
done
[ -n "$sink" ] || exit 0
pactl set-default-sink "$sink"
pactl set-sink-volume "$sink" 100%
SHEOF
chmod +x "$APP_DIR/launcher.py" "$APP_DIR/set-hdmi-audio.sh" "$APP_DIR/bt-pairing.sh"

cat > "$APP_DIR/start-menu.sh" <<'SHEOF'
#!/usr/bin/env bash
# Relance le menu (remplace l'instance en cours s'il y en a une)
pkill -f "[p]i-media/launcher.py" || true
sleep 0.3
# Utilisable aussi depuis une session SSH : on cible l'écran du Pi
export DISPLAY="${DISPLAY:-:0}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
exec python3 "$HOME/.local/share/pi-media/launcher.py"
SHEOF
chmod +x "$APP_DIR/start-menu.sh"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/accueil-hifi.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Accueil hi-fi
Exec=$APP_DIR/start-menu.sh
Icon=multimedia-audio-player
Terminal=false
Categories=AudioVideo;
EOF

# Raccourci sur le bureau (comme la corbeille)
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
mkdir -p "$DESKTOP_DIR"
cp "$HOME/.local/share/applications/accueil-hifi.desktop" "$DESKTOP_DIR/"
chmod +x "$DESKTOP_DIR/accueil-hifi.desktop"
gio set "$DESKTOP_DIR/accueil-hifi.desktop" metadata::trusted true 2>/dev/null || true

echo "==> 4/7 Démarrage automatique (labwc)"
mkdir -p "$HOME/.config/labwc"
AUTOSTART="$HOME/.config/labwc/autostart"
if [ ! -f "$AUTOSTART" ] && [ -f /etc/xdg/labwc/autostart ]; then
  cp /etc/xdg/labwc/autostart "$AUTOSTART"   # conserve barre des tâches, fond d'écran…
fi
touch "$AUTOSTART"
if ! grep -q "pi-media" "$AUTOSTART"; then
  {
    echo ""
    echo "# pi-media"
    echo "/usr/bin/bash $APP_DIR/set-hdmi-audio.sh &"
    echo "/usr/bin/python3 $APP_DIR/launcher.py &"
  } >> "$AUTOSTART"
fi

# Fenêtres Feishin / FreeTube / Supersonic ouvertes en plein écran (800x480 = petit)
python3 - <<'PYEOF'
import os, re, shutil
home = os.path.expanduser("~")
rc = os.path.join(home, ".config/labwc/rc.xml")
if not os.path.exists(rc) and os.path.exists("/etc/xdg/labwc/rc.xml"):
    shutil.copy("/etc/xdg/labwc/rc.xml", rc)
if not os.path.exists(rc):
    print("rc.xml labwc introuvable : fenêtres non maximisées automatiquement.")
    raise SystemExit
txt = open(rc, encoding="utf-8").read()
if "supersonic" in txt:
    raise SystemExit
def rule(i):
    return f'<windowRule identifier="{i}"><action name="Maximize"/></windowRule>'
if "<!-- pi-media -->" in txt:
    # installation précédente : on ajoute seulement Supersonic
    extra = rule("io.github.dweymouth.supersonic*") + rule("supersonic*")
    txt = txt.replace("<!-- pi-media -->", "<!-- pi-media -->" + extra, 1)
    open(rc, "w", encoding="utf-8").write(txt)
    raise SystemExit
rules = "".join(rule(i) for i in (
    "feishin*", "freetube*", "io.github.dweymouth.supersonic*", "supersonic*"))
block = f"<!-- pi-media -->{rules}"
if "<windowRules>" in txt:
    txt = txt.replace("<windowRules>", "<windowRules>" + block, 1)
else:
    txt, n = re.subn(r"</(labwc_config|openbox_config)>",
                     lambda m: f"<windowRules>{block}</windowRules>{m.group(0)}", txt, 1)
    if n == 0:
        print("rc.xml inattendu : fenêtres non maximisées automatiquement.")
        raise SystemExit
open(rc, "w", encoding="utf-8").write(txt)
PYEOF

echo "==> 5/7 AirPlay (Apple Music depuis iPhone/Mac)"
sudo systemctl disable --now shairport-sync 2>/dev/null || true
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/shairport-sync.service" <<EOF
[Unit]
Description=AirPlay -> sortie audio par défaut (PipeWire)
After=pipewire.service pipewire-pulse.service wireplumber.service

[Service]
ExecStart=/usr/bin/shairport-sync -a "$AIRPLAY_NAME" -o alsa -- -d pipewire
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
sudo systemctl enable --now avahi-daemon 2>/dev/null || true
sudo loginctl enable-linger "$USER" || true
systemctl --user daemon-reload || true
systemctl --user enable --now shairport-sync || \
  echo "(le service AirPlay démarrera au prochain redémarrage)"

echo "==> 6/7 Bluetooth (le Pi comme enceinte)"
sudo systemctl enable --now bluetooth 2>/dev/null || true
sudo usermod -aG bluetooth "$USER" || true
bluetoothctl system-alias "$AIRPLAY_NAME" >/dev/null 2>&1 || true
cat > "$HOME/.config/systemd/user/bt-agent.service" <<EOF
[Unit]
Description=Agent Bluetooth (appairage sans code)
After=bluetooth.target

[Service]
ExecStart=/usr/bin/bt-agent -c NoInputNoOutput
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload || true
systemctl --user enable --now bt-agent || \
  echo "(l'agent Bluetooth démarrera au prochain redémarrage)"
# Titre du morceau envoyé par le téléphone (métadonnées Bluetooth -> MPRIS)
systemctl --user enable --now mpris-proxy 2>/dev/null || true

echo "==> Subsonic Web (interface tactile pour votre serveur Subsonic)"
mkdir -p "$APP_DIR" "$HOME/.config/systemd/user"

cat > "$APP_DIR/subsonic-web.py" <<'PYEOF'
#!/usr/bin/env python3
"""Point d'entrée du serveur (relais Subsonic, interface web, podcasts, lecture haute fidélité).

Code : paquet « pimedia » (assemblage dans pimedia/server/app.py).
Réglages d'installation et secrets : fichier .env du dossier de données (voir .env.example) ;
réglages modifiés depuis l'application et données : base pi-media.db du même dossier.
"""
import os
import sys

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE_DIR)

from pimedia.server.app import Application  # noqa: E402


def main():
    Application(CODE_DIR).run()


if __name__ == "__main__":
    main()
PYEOF

rm -f "$APP_DIR/subsonic-web.html"
rm -rf "$APP_DIR/web" "$APP_DIR/pimedia" "$APP_DIR/i18n" "$APP_DIR/deploy"
mkdir -p "$APP_DIR/deploy" "$APP_DIR/deploy/bin" "$APP_DIR/deploy/systemd" "$APP_DIR/i18n" "$APP_DIR/pimedia" "$APP_DIR/pimedia/server" "$APP_DIR/pimedia/server/controllers" "$APP_DIR/pimedia/server/extmusic" "$APP_DIR/pimedia/server/podcasts" "$APP_DIR/pimedia/storage" "$APP_DIR/web" "$APP_DIR/web/static/css" "$APP_DIR/web/static/js" "$APP_DIR/web/static/vendor/qrcode-generator" "$APP_DIR/web/static/vendor/simple-keyboard"
cat > "$APP_DIR/web/index.html" <<'WEBEOF_0'
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<meta name="theme-color" content="#040a04">
<title>Subsonic</title>
<link rel="stylesheet" href="/static/css/base.css?v={{V}}">
<link rel="stylesheet" href="/static/css/components.css?v={{V}}">
<link rel="stylesheet" href="/static/css/player.css?v={{V}}">
<link rel="stylesheet" href="/static/css/overlays.css?v={{V}}">
<link rel="stylesheet" href="/static/css/search.css?v={{V}}">
<link rel="stylesheet" href="/static/css/history.css?v={{V}}">
<link rel="stylesheet" href="/static/vendor/simple-keyboard/simple-keyboard.css?v={{V}}">
<link rel="stylesheet" href="/static/css/keyboard.css?v={{V}}">
<link rel="stylesheet" href="/static/css/external.css?v={{V}}">
</head>
<body>
<div id="app">
  <nav>
    <button data-t="home">Accueil</button>
    <button data-t="albums">Albums</button>
    <button data-t="artists">Artistes</button>
    <button data-t="fav">Favoris</button>
    <button data-t="playlists">Playlists</button>
    <button data-t="radios">Radios</button>
    <button data-t="search">Recherche</button>
    <button id="quit" hidden>Menu</button>
  </nav>
  <div id="top" hidden><button id="back"></button><div id="title"></div></div>
  <div id="main"></div>
  <div id="kbwrap" hidden><div id="kbbar"><button id="kbclose">Fermer le clavier &#9662;</button></div><div class="kbd" id="kb"></div></div>
  <div id="bar">
    <div class="prog" id="prog"><u><i></i></u></div>
    <div class="in">
      <div id="np"><img id="npimg" alt=""><div class="t"><b id="nptitle">&mdash;</b><small id="npsub">Choisissez de la musique</small></div></div>
      <div id="ctl">
        <button class="ib" id="npshuf"></button>
        <button class="ib" id="prev"></button>
        <button class="ib big" id="pp"></button>
        <button class="ib" id="next"></button>
        <button class="ib" id="nplist"></button>
        <button class="ib" id="npheart"></button>
      </div>
    </div>
  </div>
</div>
<div id="full" hidden>
  <div id="fbg"></div>
  <button class="ib" id="fclose"></button>
  <div id="fbody">
    <img id="fcover" alt="">
    <div id="finfo">
      <div id="ftitle"></div>
      <div id="fartist"></div>
      <div id="falbum"></div>
      <div id="fprog"><span id="ftcur">0:00</span><div class="prog" id="fbar"><u><i></i></u></div><span id="ftdur">0:00</span></div>
      <div id="fctl">
        <button class="ib" id="fshuf"></button>
        <button class="ib" id="fprev"></button>
        <button class="ib big" id="fpp"></button>
        <button class="ib" id="fnext"></button>
        <button class="ib" id="frep"></button>
      </div>
      <div id="fextra">
        <button id="fheart"></button>
        <button id="fplaylist"></button>
        <button id="fradio"></button>
        <button id="flbtn"></button>
        <button id="fibtn"></button>
        <button id="fvbtn" hidden></button>
        <button id="fqbtn"></button>
      </div>
    </div>
  </div>
  <div id="fqueue" hidden></div>
  <div id="flyr" hidden></div>
  <div id="fanec" hidden><img alt=""><b></b><span></span></div>
  <div id="finf" hidden></div>
  <div id="fvol" hidden><button id="fvm"></button><div id="fvv">--</div><button id="fvp"></button></div>
</div>
<div id="sheet" hidden><div id="sheetbg"></div><div id="sheetbox"><div id="sheettitle"></div><div id="sheetlist"></div></div></div>
<div id="ask" hidden><div id="askbox"><div id="asktitle"></div><div id="askin"></div><div class="kbd" id="askkb"></div>
  <div class="actions"><button id="askcancel">Annuler</button><button id="askok" class="primary">Valider</button></div></div></div>
<div id="ytbox" hidden><div id="ytplayer"></div></div>
<div id="toast" hidden></div>
<script src="/static/js/core.js?v={{V}}" defer></script>
<script src="/static/js/icons.js?v={{V}}" defer></script>
<script src="/static/js/engine.js?v={{V}}" defer></script>
<script src="/static/js/nav.js?v={{V}}" defer></script>
<script src="/static/js/touchscroll.js?v={{V}}" defer></script>
<script src="/static/vendor/simple-keyboard/simple-keyboard.js?v={{V}}" defer></script>
<script src="/static/js/keyboard.js?v={{V}}" defer></script>
<script src="/static/js/dialogs.js?v={{V}}" defer></script>
<script src="/static/js/components.js?v={{V}}" defer></script>
<script src="/static/js/menus.js?v={{V}}" defer></script>
<script src="/static/js/mixes.js?v={{V}}" defer></script>
<script src="/static/js/similar.js?v={{V}}" defer></script>
<script src="/static/js/mixbuilder.js?v={{V}}" defer></script>
<script src="/static/js/tabs.js?v={{V}}" defer></script>
<script src="/static/js/history.js?v={{V}}" defer></script>
<script src="/static/vendor/qrcode-generator/qrcode.js?v={{V}}" defer></script>
<script src="/static/js/remote.js?v={{V}}" defer></script>
<script src="/static/js/search.js?v={{V}}" defer></script>
<script src="/static/js/player.js?v={{V}}" defer></script>
<script src="/static/js/playerui.js?v={{V}}" defer></script>
<script src="/static/js/lyrics.js?v={{V}}" defer></script>
<script src="/static/js/controls.js?v={{V}}" defer></script>
<script src="/static/js/ext.js?v={{V}}" defer></script>
<script src="/static/js/guest.js?v={{V}}" defer></script>
<script src="/static/js/hifi.js?v={{V}}" defer></script>
<script src="/static/js/queue.js?v={{V}}" defer></script>
<script src="/static/js/ytpopup.js?v={{V}}" defer></script>
<script src="/static/js/pi.js?v={{V}}" defer></script>
<script src="/static/js/boot.js?v={{V}}" defer></script>
</body>
</html>
WEBEOF_0
cat > "$APP_DIR/web/podcasts.html" <<'WEBEOF_1'
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<meta name="theme-color" content="#040a04">
<title>Podcasts</title>
<link rel="stylesheet" href="/static/css/base.css?v={{V}}">
<link rel="stylesheet" href="/static/css/podcasts.css?v={{V}}">
<link rel="stylesheet" href="/static/css/history.css?v={{V}}">
<link rel="stylesheet" href="/static/vendor/simple-keyboard/simple-keyboard.css?v={{V}}">
<link rel="stylesheet" href="/static/css/keyboard.css?v={{V}}">
</head>
<body>
<div id="app">
  <nav>
    <button data-t="home">Accueil</button>
    <button data-t="themes">Thèmes</button>
    <button data-t="search">Recherche</button>
    <button data-t="mine">Ma liste</button>
    <button data-t="settings">Réglages</button>
    <button id="quit">Menu</button>
  </nav>
  <div id="top" hidden><button id="back"></button><div id="title"></div></div>
  <div id="main"></div>
  <div id="kbwrap" hidden>
    <div id="kbbar"><button id="kbclose">Fermer le clavier &#9662;</button></div>
    <div class="pkb" id="kb"></div>
  </div>
  <div id="bar" hidden>
    <div class="pprog" id="bprog"><u><i></i></u></div>
    <div class="bin">
      <div id="bnp"><img id="bimg" alt=""><div class="t"><b id="btitle"></b><small id="bsub"></small></div></div>
      <div id="bctl">
        <button class="ib" id="bback" aria-label="Reculer de 15 secondes"></button>
        <button class="ib big" id="bpp" aria-label="Lecture"></button>
        <button class="ib" id="bfwd" aria-label="Avancer de 30 secondes"></button>
      </div>
    </div>
  </div>
</div>
<div id="np" hidden>
  <div id="npbg"></div>
  <button class="ib" id="npclose" aria-label="Fermer"></button>
  <div id="npbody">
    <img id="npimg" alt="">
    <div id="npinfo">
      <div id="nptitle"></div>
      <div id="npsub"></div>
      <div id="npprog"><span id="npcur">0:00</span><div class="pprog" id="npbar"><u><i></i></u></div><span id="npdur">0:00</span></div>
      <div id="npctl">
        <button class="ib" id="npback"></button>
        <button class="ib big" id="nppp"></button>
        <button class="ib" id="npfwd"></button>
      </div>
      <div id="npextra">
        <button id="npspeed">1×</button>
        <button id="npsleep">Minuteur</button>
        <button id="npdone">Marquer écouté</button>
      </div>
      <div id="npdesc"></div>
    </div>
  </div>
</div>
<div id="toast" hidden></div>
<script src="/static/js/pod-core.js?v={{V}}" defer></script>
<script src="/static/vendor/simple-keyboard/simple-keyboard.js?v={{V}}" defer></script>
<script src="/static/js/keyboard.js?v={{V}}" defer></script>
<script src="/static/js/pod-keyboard.js?v={{V}}" defer></script>
<script src="/static/js/pod-views.js?v={{V}}" defer></script>
<script src="/static/js/pod-player.js?v={{V}}" defer></script>
<script src="/static/js/history.js?v={{V}}" defer></script>
<script src="/static/js/pod-pages.js?v={{V}}" defer></script>
<script src="/static/js/pod-app.js?v={{V}}" defer></script>
</body>
</html>
WEBEOF_1
cat > "$APP_DIR/web/telephone.html" <<'WEBEOF_2'
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Pi Media Station</title>
<style>
:root{--bg:#040a04;--panel:#0b1a0d;--edge:#1f6b2f;--g:#39ff6e;--soft:#9be8ae;--dim:#2f9a4c}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--g);font-family:-apple-system,system-ui,sans-serif;padding:18px 16px 40px}
h1{font-size:20px;font-weight:600;margin:0 0 4px}
h2{font-size:15px;font-weight:600;margin:22px 0 8px;color:var(--soft)}
p{color:var(--soft);font-size:14px;margin:0 0 14px;line-height:1.4}
input{width:100%;height:54px;padding:0 16px;font-size:19px;border-radius:14px;border:1px solid var(--edge);background:var(--panel);color:var(--g);outline:none}
input:focus{border-color:var(--g)}
button{height:44px;padding:0 14px;font-size:15px;border-radius:12px;border:1px solid var(--edge);background:var(--panel);color:var(--g)}
#sug{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
#sug button{border-radius:22px}
.song{display:flex;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid #0f2a14}
.song .t{flex:1;min-width:0}
.song b{display:block;font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.song small{display:block;font-size:13px;color:var(--soft);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.song button{flex:0 0 auto;height:40px;font-size:13px;padding:0 10px}
.song button.next{border-color:var(--g)}
.q{padding:6px 0;font-size:14px;border-bottom:1px solid #0f2a14}
.q small{color:var(--dim)}
.q.now{color:var(--g);font-weight:600}
#state{position:sticky;bottom:10px;margin-top:16px;font-size:14px;color:var(--soft);min-height:20px;background:var(--bg)}
#state.err{color:#ffd23f}
</style>
</head>
<body>
<h1>Pi Media Station</h1>
<p>Cherchez un titre et ajoutez-le à la file du Pi. Le texte s’affiche aussi dans la recherche de l’écran.</p>
<input id="q" type="search" autocomplete="off" autocapitalize="off" enterkeyhint="search" placeholder="Artiste, album, titre…" autofocus>
<div id="sug"></div>
<div id="songs"></div>
<h2>File d’attente</h2>
<div id="queue"><p>Chargement…</p></div>
<div id="state"></div>
<script src="/tel.js"></script>
</body>
</html>
WEBEOF_2
cat > "$APP_DIR/web/telephone.js" <<'WEBEOF_3'
"use strict";
// Page du téléphone : recherche dans la bibliothèque du Pi, ajout à la file commune, aperçu de la file.
// Le code (dans l'adresse du QR code) accompagne chaque demande.

const code = new URLSearchParams(location.search).get("c") || "";
const $ = id => document.getElementById(id);
const field = $("q"), state = $("state");
let typingTimer = null, sent = null;

function show(message, isError) { state.textContent = message; state.className = isError ? "err" : ""; }

async function post(path, body) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"},
                               body: JSON.stringify(Object.assign({code}, body))});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
  return j;
}
const failed = e => show(e.message === "Failed to fetch" ? "Pi injoignable : êtes-vous sur le même Wi-Fi ?" : e.message, true);

function button(label, cls, onClick) {
  const b = document.createElement("button"); b.type = "button"; b.textContent = label;
  if (cls) b.className = cls;
  b.onclick = onClick;
  return b;
}

/* ---------- saisie : texte envoyé à l'écran, artistes suggérés, titres trouvés ---------- */
async function sendText(text) {
  if (text === sent) return;
  sent = text;
  try {
    const [typed, found] = await Promise.all([post("/tel/text", {text}), text.trim().length >= 2 ? post("/tel/search", {text}) : {songs: []}]);
    if (field.value !== text) return;
    showArtists(typed.suggestions || []);
    showSongs(found.songs || []);
    show("");
  } catch (e) { sent = null; failed(e); }
}

function showArtists(artists) {
  $("sug").innerHTML = "";
  artists.forEach(artist => $("sug").appendChild(button(artist.name, "", async () => {
    try { await post("/tel/pick", {id: artist.id}); show("« " + artist.name + " » ouvert sur le Pi ✓"); } catch (e) { failed(e); }
  })));
}

function showSongs(songs) {
  const box = $("songs");
  box.innerHTML = "";
  songs.forEach(song => {
    const line = document.createElement("div"); line.className = "song";
    const text = document.createElement("div"); text.className = "t";
    const title = document.createElement("b"); title.textContent = song.title;
    const meta = document.createElement("small"); meta.textContent = [song.artist, song.album].filter(Boolean).join(" · ");
    text.appendChild(title); text.appendChild(meta);
    line.appendChild(text);
    line.appendChild(button("Après ce titre", "next", () => addToQueue(song, "next")));
    line.appendChild(button("À la fin", "", () => addToQueue(song, "end")));
    box.appendChild(line);
  });
}

async function addToQueue(song, mode) {
  try {
    await post("/tel/queue/add", {id: song.id, mode});
    show("« " + song.title + " » ajouté " + (mode === "next" ? "après le titre en cours" : "à la fin de la file") + " ✓");
    refreshQueue();
  } catch (e) { failed(e); }
}

/* ---------- aperçu de la file ---------- */
async function refreshQueue() {
  let view;
  try { view = await post("/tel/queue", {}); } catch (e) { return; }
  const box = $("queue");
  box.innerHTML = "";
  const line = (text, cls, note) => {
    const d = document.createElement("div"); d.className = "q" + (cls ? " " + cls : ""); d.textContent = text;
    if (note) { const s = document.createElement("small"); s.textContent = " · " + note; d.appendChild(s); }
    box.appendChild(d);
  };
  const label = t => t.title + (t.artist ? " — " + t.artist : "");
  if (view.current) line("▶ " + label(view.current), "now");
  view.pending.forEach(t => line(label(t), "", "en cours d’ajout"));
  view.upcoming.forEach(t => line(label(t), "", t.addedBy === "phone" ? "ajouté par téléphone" : ""));
  if (!view.current && !view.upcoming.length && !view.pending.length) box.innerHTML = "<p>La file est vide : ajoutez le premier titre !</p>";
}

field.addEventListener("input", () => { clearTimeout(typingTimer); typingTimer = setTimeout(() => sendText(field.value), 300); });
field.addEventListener("keydown", e => { if (e.key === "Enter") { clearTimeout(typingTimer); sendText(field.value); field.blur(); } });
if (!code) show("Adresse incomplète : scannez le QR code affiché sur le Pi", true);
else { refreshQueue(); setInterval(refreshQueue, 4000); }
WEBEOF_3
cat > "$APP_DIR/web/static/css/base.css" <<'WEBEOF_4'
/* Variables, réinitialisation, structure de la page, navigation */
:root{--bg:#040a04;--bg2:#07130a;--panel:#0b1a0d;--on:#14301a;--edge:#1f6b2f;--g:#39ff6e;--soft:#9be8ae;--dim:#2f9a4c;--warn:#ffd23f;--f:"DejaVu Sans Mono",monospace;--glow:0 0 14px rgba(57,255,110,.35)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;-webkit-user-select:none;user-select:none}
[hidden]{display:none!important}
html,body{margin:0;height:100%;background:var(--bg);color:var(--g);font:15px var(--f);overflow:hidden}
button{font-family:var(--f);color:var(--g);background:var(--panel);border:1px solid var(--edge);cursor:pointer;transition:background .15s,box-shadow .15s}
button:active{background:var(--on);box-shadow:var(--glow)}
svg{display:block;pointer-events:none}
#app{display:flex;flex-direction:column;height:100vh;background:radial-gradient(120% 80% at 50% -10%,#0d2a14 0%,var(--bg) 60%)}
nav{display:flex;gap:3px;padding:4px;flex:0 0 auto}
nav button{flex:1;height:36px;font-size:11px;font-weight:bold;text-transform:uppercase;letter-spacing:.3px;border-radius:18px;border-color:transparent;background:transparent;color:var(--soft);padding:0 2px}
nav button.on{background:var(--on);color:var(--g);border-color:var(--edge);box-shadow:var(--glow)}
#top{display:flex;align-items:center;gap:8px;padding:0 8px 4px;flex:0 0 auto}
#back{height:34px;width:44px;border-radius:17px;display:flex;align-items:center;justify-content:center}
#title{flex:1;color:var(--soft);font-size:15px;font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#main{flex:1;min-height:0;overflow-y:auto;touch-action:pan-y;padding-bottom:8px}
#main.in{animation:up .22s ease}
@keyframes up{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
#kbwrap{flex:0 0 auto;padding:4px;border-top:1px solid var(--edge);background:var(--bg)}
WEBEOF_4
cat > "$APP_DIR/web/static/css/components.css" <<'WEBEOF_5'
/* Composants : listes, cartes, puces, boutons d'action, en-têtes */
.row{display:flex;align-items:center;gap:10px;min-height:58px;padding:5px 8px 5px 12px;border-bottom:1px solid #0f2a14}
.row:active{background:var(--on)}
.row img,.row .ph{width:46px;height:46px;flex:0 0 46px;object-fit:cover;background:#0a2410;border-radius:6px}
.row.round img,.row.round .ph{border-radius:50%}
.row .t{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}
.row .t b{font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .t small{color:var(--dim);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row.cur .t b{color:var(--warn)}
.sb{width:42px;height:46px;flex:0 0 42px;border:0;background:transparent;color:var(--dim);display:flex;align-items:center;justify-content:center}
.sb.on{color:var(--g)}
.h{padding:14px 12px 6px;color:var(--soft);font-size:13px;font-weight:bold;text-transform:uppercase;letter-spacing:1.5px}
.chips,.shelf{display:flex;gap:8px;overflow-x:auto;touch-action:pan-x;padding:2px 12px 6px;scrollbar-width:none}
.chips::-webkit-scrollbar,.shelf::-webkit-scrollbar{display:none}
.chips button{padding:0 14px;height:34px;font-size:13px;white-space:nowrap;border-radius:17px;flex:0 0 auto}
.chips button.on{background:var(--on);border-color:var(--g);box-shadow:var(--glow)}
.chips.wrap{flex-wrap:wrap;overflow:visible;touch-action:auto}
.chips button.sug{border-color:var(--g);border-style:dashed}
.chips.sticky{position:sticky;top:0;z-index:2;background:linear-gradient(var(--bg) 70%,transparent);padding-top:6px}
.card{flex:0 0 128px;width:128px}
.card img,.card .ph{width:128px;height:128px;object-fit:cover;background:#0a2410;border-radius:8px;display:block;box-shadow:0 4px 14px rgba(0,0,0,.5)}
.card.round img,.card.round .ph{border-radius:50%}
.card b{display:block;margin-top:6px;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card small{display:block;color:var(--dim);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card:active img{box-shadow:var(--glow)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:14px 12px;padding:10px 12px}
.grid .card{width:auto;flex:none}
.grid .card img,.grid .card .ph{width:100%;height:auto;aspect-ratio:1}
.tiles{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:10px 12px 2px}
.tile{height:62px;border-radius:10px;display:flex;align-items:center;gap:12px;padding:0 14px;font-size:14px;font-weight:bold;text-align:left;background:linear-gradient(135deg,#124a22,#0b1a0d);border-color:#1f6b2f}
.tile svg{flex:0 0 28px;color:var(--g)}
.actions{display:flex;gap:8px;padding:8px 12px;flex-wrap:wrap}
.actions button{height:42px;padding:0 18px;font-size:14px;font-weight:bold;border-radius:21px;display:flex;align-items:center;gap:8px}
.actions button.primary{background:var(--g);color:#031004;border-color:var(--g)}
.msg{padding:20px;color:var(--warn);line-height:1.6}
.hero,.ahero{display:flex;align-items:center;gap:16px;padding:12px;transition:all .25s}
.hero img,.ahero img{width:104px;height:104px;object-fit:cover;background:#0a2410;border-radius:10px;flex:0 0 auto;box-shadow:0 6px 22px rgba(0,0,0,.6);transition:all .25s;cursor:pointer}
.hero img{border-radius:50%}
.hero.big,.ahero.big{flex-direction:column;align-items:center;text-align:center}
.hero.big img,.ahero.big img{width:250px;height:250px}
.hinfo{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.hinfo b{font-size:20px;line-height:1.2}
.hinfo small,.hinfo .lnk{color:var(--dim);font-size:12px}
.hinfo .lnk{color:var(--soft);font-size:14px;cursor:pointer}
.bio{margin:0 12px;padding:10px 12px;background:rgba(11,26,13,.8);border:1px solid #0f2a14;border-radius:10px;color:var(--soft);font-size:13px;line-height:1.55;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.bio.open{display:block;-webkit-line-clamp:unset}
.biohint{text-align:right;padding:2px 14px;font-size:11px;color:var(--dim)}
WEBEOF_5
cat > "$APP_DIR/web/static/css/external.css" <<'WEBEOF_6'
/* Lecteur YouTube intégré (écran du Pi) : petite fenêtre flottante, ou à la place de la pochette en plein écran */
#ytbox{position:fixed;right:10px;bottom:84px;width:200px;height:200px;z-index:45;background:#000;border:1px solid var(--edge);border-radius:10px;overflow:hidden;box-shadow:0 6px 24px rgba(0,0,0,.7)}
#ytbox.big{right:auto;bottom:auto;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,.7)}
#ytbox iframe{width:100%;height:100%;border:0;display:block}
/* Clavier ouvert : la fenêtre vidéo passe en haut à droite pour ne pas cacher les touches */
body:has(#app.kbopen) #ytbox:not(.big){bottom:auto;top:56px}
/* Lecture sur la vraie page YouTube : fond assombri pendant que la fenêtre est ouverte */
#ytveil{position:fixed;inset:0;z-index:90;background:rgba(0,0,0,.82);display:flex;align-items:flex-end;justify-content:center;padding-bottom:10px}
.ytvbox{display:flex;flex-direction:column;gap:6px;align-items:center;text-align:center;max-width:94%;padding:10px 16px;background:var(--bg2);border:1px solid var(--g);border-radius:14px}
.ytvbox b{font-size:15px}.ytvbox span{color:var(--soft);font-size:13px}.ytvbox em{font-style:normal;color:var(--warn);font-size:13px;min-height:16px}
.ytvbtns{display:flex;gap:10px}.ytvbtns button{height:40px;padding:0 18px;border-radius:20px;font-size:14px}
WEBEOF_6
cat > "$APP_DIR/web/static/css/history.css" <<'WEBEOF_7'
/* Historique des recherches (écran du Pi) */
.hist{margin:6px 12px}
.histhead{color:var(--soft);font-size:13px;font-weight:bold;padding:4px 2px 6px}
.histitem{display:flex;gap:6px;margin-bottom:6px}
.histitem .histtext{flex:1;min-width:0;height:42px;text-align:left;padding:0 14px;font-size:16px;border-radius:21px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.histitem .histdel{flex:0 0 42px;height:42px;padding:0;border-radius:21px;font-size:16px;color:var(--soft)}
.histclear{margin-top:4px;height:34px;padding:0 16px;font-size:13px;border-radius:17px;color:var(--soft)}
WEBEOF_7
cat > "$APP_DIR/web/static/css/keyboard.css" <<'WEBEOF_8'
/* Habillage « hi-fi verte » de simple-keyboard (keyboard.js) : grosses touches pour l'écran 800×480 */
.hg-theme-default.tkb{background:transparent;padding:0;font-family:inherit;border-radius:0}
.tkb .hg-row:not(:last-child){margin-bottom:5px}
.tkb .hg-row .hg-button:not(:last-child){margin-right:5px}
.tkb .hg-button{height:54px;padding:0;font-size:22px;color:var(--g);background:var(--panel);border:1px solid var(--edge);border-radius:8px;box-shadow:none}
.tkb .hg-button.hg-standardBtn{width:auto}
.tkb .hg-button.hg-activeButton,.tkb .hg-button:active{background:var(--on);border-color:var(--g);transform:scale(.94)}
.tkb .hg-button.switch{flex-grow:1.5;font-size:16px}
.tkb .hg-button.on{background:var(--g);color:#031004}
.tkb .hg-button.del{flex-grow:2.5;font-size:28px;background:var(--on);border-color:var(--g)}
.tkb .hg-button.paste{flex-grow:1.3;font-size:15px}
.tkb .hg-button.space{flex-grow:4;font-size:16px}
.tkb .hg-button.ok{flex-grow:1.8;font-size:18px;background:var(--g);color:#031004;border-color:var(--g);font-weight:bold}
WEBEOF_8
cat > "$APP_DIR/web/static/css/overlays.css" <<'WEBEOF_9'
/* Clavier tactile, notifications, feuille d'actions, saisie de texte, connexion */
.kbopen nav,.kbopen #bar{display:none}
#kbbar{display:flex;justify-content:flex-end;gap:8px;padding:0 2px 3px}
#kbphone{height:28px;padding:0 12px;font-size:11px;border-radius:15px;color:var(--dim);border-color:var(--panel);background:transparent;margin-right:auto}
#kbclose{height:28px;padding:0 16px;font-size:12px;border-radius:15px}
.kbd{display:flex;flex-direction:column;gap:3px}
.kbd .kr{display:flex;gap:3px}
#toast{position:fixed;left:50%;bottom:92px;transform:translateX(-50%);background:var(--panel);border:1px solid var(--g);border-radius:18px;padding:8px 16px;font-size:13px;z-index:80;max-width:90%;text-align:center}
#sheet{position:fixed;inset:0;z-index:60}
#sheetbg{position:absolute;inset:0;background:rgba(0,0,0,.6)}
#sheetbox{position:absolute;left:0;right:0;bottom:0;max-height:78%;display:flex;flex-direction:column;background:var(--bg2);border-top:1px solid var(--g);border-radius:16px 16px 0 0;box-shadow:0 -10px 30px rgba(0,0,0,.6)}
#sheettitle{padding:12px 16px 8px;color:var(--soft);font-size:13px;font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#sheetlist{overflow-y:auto;touch-action:pan-y;padding-bottom:8px}
.si{display:flex;align-items:center;gap:14px;width:100%;height:52px;padding:0 18px;border:0;border-bottom:1px solid #0f2a14;background:transparent;font-size:15px;text-align:left;border-radius:0}
.si svg{color:var(--g);flex:0 0 22px}
#ask{position:fixed;inset:0;z-index:70;background:rgba(0,0,0,.75);display:flex;align-items:center;justify-content:center}
#askbox{width:94%;max-width:760px;background:var(--bg2);border:1px solid var(--g);border-radius:14px;padding:10px;box-shadow:var(--glow)}
#asktitle{padding:2px 6px 6px;color:var(--soft);font-size:13px;font-weight:bold}
#askin{margin:0 4px 8px;padding:8px 12px;min-height:40px;border:1px solid var(--edge);border-radius:20px;background:var(--panel);font-size:18px}
#lg_err{min-height:18px;color:var(--warn);font-size:13px;text-align:center}
WEBEOF_9
cat > "$APP_DIR/web/static/css/player.css" <<'WEBEOF_10'
/* Barre de lecture et lecteur plein écran (file, paroles, infos, volume) */
#bar{flex:0 0 auto;border-top:1px solid var(--edge);background:rgba(4,10,4,.92)}
.prog{height:14px;cursor:pointer;position:relative;display:flex;align-items:center}
.prog u{display:block;width:100%;height:4px;background:#0f2a14;border-radius:2px;overflow:hidden}
.prog i{display:block;height:100%;width:0;background:var(--g);box-shadow:var(--glow)}
#bar .in{display:flex;align-items:center;gap:8px;padding:2px 8px 6px;height:66px}
#np{flex:1;min-width:0;display:flex;align-items:center;gap:10px}
#np img{width:52px;height:52px;object-fit:cover;background:#0a2410;border-radius:6px;flex:0 0 52px}
#np .t{min-width:0;display:flex;flex-direction:column;gap:2px}
#np .t b{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#np .t small{color:var(--dim);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#ctl{display:flex;gap:4px;align-items:center}
.ib{width:48px;height:48px;border-radius:24px;display:flex;align-items:center;justify-content:center;border-color:transparent;background:transparent;position:relative}
.ib.big{width:60px;height:60px;border-radius:30px;background:var(--g);color:#031004;border-color:var(--g)}
.ib.big:active{background:#7dff9c}
.ib.on{color:var(--warn)}
.ib .one{position:absolute;font-size:9px;font-style:normal;font-weight:bold;margin-top:1px}
#full{position:fixed;inset:0;z-index:30;background:var(--bg);overflow:hidden}
#fbg{position:absolute;inset:-40px;background-size:cover;background-position:center;filter:blur(36px) brightness(.38) saturate(1.3)}
#fclose{position:absolute;top:8px;left:8px;z-index:3}
#fbody{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:28px;padding:44px 28px 14px}
#fcover{width:290px;height:290px;object-fit:cover;border-radius:12px;background:#0a2410;box-shadow:0 10px 40px rgba(0,0,0,.7);flex:0 0 290px}
#finfo{flex:1;min-width:0;display:flex;flex-direction:column;gap:6px}
#ftitle{font-size:24px;font-weight:bold;line-height:1.2;max-height:58px;overflow:hidden}
#fartist{font-size:16px;color:var(--soft);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
#falbum{font-size:12px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:6px}
#fprog{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--soft)}
#fprog .prog{flex:1;height:26px}
#fprog .prog u{height:6px}
#fctl{display:flex;align-items:center;justify-content:space-between;margin-top:2px}
#fextra{display:flex;gap:6px;margin-top:2px;flex-wrap:wrap}
#fextra button{height:38px;padding:0 12px;border-radius:19px;display:flex;align-items:center;gap:6px;font-size:12px;background:rgba(11,26,13,.7)}
#fqueue{position:absolute;inset:44px 0 0;z-index:2;overflow-y:auto;touch-action:pan-y;background:rgba(4,10,4,.88)}
#fbody{padding-bottom:56px}
#fanec{position:absolute;left:28px;right:28px;bottom:8px;height:40px;z-index:2;font-size:12px;line-height:1.3;color:var(--soft);overflow:hidden;transition:opacity .6s;display:flex;align-items:center;gap:8px}
#fanec b{flex:0 0 auto;color:var(--g);font-size:10px;text-transform:uppercase;letter-spacing:.5px;border:1px solid var(--edge);border-radius:10px;padding:2px 7px}
#fanec span{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-style:italic}
#fqueue .row{transition:transform .12s}
#fqueue .row.drag{transition:none;z-index:5;background:var(--on);box-shadow:var(--glow);position:relative}
.grip{margin-left:auto;width:48px;height:48px;flex:0 0 48px;border-color:transparent;background:transparent;color:var(--dim);touch-action:none;display:flex;align-items:center;justify-content:center}
#fanec img{width:34px;height:34px;border-radius:50%;object-fit:cover;flex:0 0 34px}
#finf{position:absolute;inset:44px 0 0;z-index:2;overflow-y:auto;touch-action:pan-y;background:rgba(4,10,4,.92);padding:14px 28px 40px;font-size:14px;line-height:1.5}
#finf img{float:left;width:110px;height:110px;border-radius:50%;object-fit:cover;margin:0 16px 8px 0}
#finf h3{margin:0 0 6px;font-size:18px;color:var(--g)}
#finf p{margin:0 0 8px;color:var(--soft)}
#fvol{position:absolute;right:20px;bottom:70px;z-index:4;display:flex;align-items:center;gap:10px;background:rgba(4,10,4,.94);border:1px solid var(--g);border-radius:30px;padding:6px;box-shadow:var(--glow)}
#fvol button{width:54px;height:54px;border-radius:27px;font-size:26px;font-weight:bold;display:flex;align-items:center;justify-content:center}
#fvv{min-width:60px;text-align:center;font-size:20px;font-weight:bold;color:var(--g)}
#flyr{position:absolute;inset:44px 0 0;z-index:2;overflow-y:auto;touch-action:pan-y;background:rgba(4,10,4,.9);padding:14px 28px 40px;text-align:center;font-size:18px;line-height:1.5}
#flyr p{margin:0;color:var(--dim);transition:color .3s,font-size .3s}
#flyr p.cur{color:var(--g);font-size:22px;font-weight:bold}
#flyr .msg{color:var(--soft);font-size:14px}
#flyr small{display:block;margin-top:14px;font-size:10px;color:var(--dim)}
/* Invité AirPlay / Bluetooth en attente */
#guestbar{position:fixed;left:8px;right:8px;bottom:84px;z-index:44;display:flex;align-items:center;gap:8px;padding:6px 8px 6px 14px;background:var(--bg2);border:1px solid var(--g);border-radius:22px;box-shadow:var(--glow);font-size:13px}
#guestbar span{flex:1;min-width:0;color:var(--soft)}
#guestbar button{height:34px;padding:0 14px;border-radius:17px;font-size:13px}
body:has(#app.kbopen) #guestbar{display:none}
WEBEOF_10
cat > "$APP_DIR/web/static/css/podcasts.css" <<'WEBEOF_11'
/* Page Podcasts : pochettes, rangées, thèmes, épisodes, lecteur, clavier */
.ph{padding:14px 12px 6px;color:var(--soft);font-size:13px;font-weight:bold;text-transform:uppercase;letter-spacing:1.5px}
.pmsg{padding:24px 16px;color:var(--warn);line-height:1.6}
.phint{margin:8px 12px;padding:8px 12px;border:1px dashed var(--edge);border-radius:10px;color:var(--soft);font-size:12px}
#toast{position:fixed;left:50%;bottom:90px;transform:translateX(-50%);background:var(--on);border:1px solid var(--g);border-radius:20px;padding:10px 18px;font-size:13px;z-index:60;box-shadow:var(--glow);max-width:90vw}
.ib{width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;padding:0;flex:0 0 auto}
.ib.big{width:58px;height:58px;background:var(--g);color:#031004;border-color:var(--g)}

/* pochettes */
.art{position:relative;width:100%;aspect-ratio:1;border-radius:10px;overflow:hidden;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,hsl(var(--h),55%,22%),hsl(calc(var(--h) + 40),60%,9%));color:hsl(var(--h),80%,75%);font-size:42px;font-weight:bold;box-shadow:0 4px 14px rgba(0,0,0,.5)}
.art img{width:100%;height:100%;object-fit:cover;display:block}
.art.small{width:46px;height:46px;flex:0 0 46px;font-size:20px;border-radius:6px;box-shadow:none}
.art.big{width:150px;height:150px;flex:0 0 150px}

/* rangées et grilles */
.pshelf{display:flex;gap:12px;overflow-x:auto;touch-action:pan-x;padding:2px 12px 8px;scrollbar-width:none}
.pshelf::-webkit-scrollbar{display:none}
.pcard{position:relative;flex:0 0 132px;width:132px;padding:0;border:0;background:transparent;text-align:left;color:var(--g)}
.pcard b{display:block;margin-top:6px;font-size:13px;line-height:1.25;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pcard small{display:block;color:var(--dim);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pcard:active .art{box-shadow:var(--glow)}
.pcard .badge{position:absolute;top:6px;right:6px;width:22px;height:22px;border-radius:50%;background:var(--g);color:#031004;display:flex;align-items:center;justify-content:center}
.pcard.resume{flex-basis:150px;width:150px}
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:14px 12px;padding:10px 12px}
.pgrid .pcard{width:auto;flex:none}
.mini{height:4px;background:#0f2a14;border-radius:2px;margin-top:5px;overflow:hidden}
.mini i{display:block;height:100%;background:var(--g)}

/* thèmes */
.ptiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;padding:6px 12px 12px}
.ptile{height:84px;border-radius:12px;border:0;display:flex;align-items:flex-end;padding:10px 12px;text-align:left;font-size:17px;font-weight:bold;color:#fff;
  background:linear-gradient(140deg,hsl(var(--h),60%,30%),hsl(calc(var(--h) + 35),65%,12%));box-shadow:0 4px 14px rgba(0,0,0,.5);text-shadow:0 1px 6px rgba(0,0,0,.6)}
.ptile:active{box-shadow:var(--glow);filter:brightness(1.2)}

/* fiche d'un podcast */
.phero{display:flex;gap:16px;padding:12px;align-items:flex-start}
.pinfo{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.pinfo b{font-size:19px;line-height:1.2}
.pinfo small{color:var(--dim);font-size:12px}
.pinfo p{margin:2px 0;color:var(--soft);font-size:12.5px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.pactions{display:flex;gap:8px;margin-top:4px;flex-wrap:wrap}
.pactions button{height:40px;padding:0 18px;font-size:14px;font-weight:bold;border-radius:20px;display:flex;align-items:center;gap:8px}
.pactions button.primary{background:var(--g);color:#031004;border-color:var(--g)}
.pep{display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid #0f2a14}
.pep:active{background:var(--on)}
.pep .go{width:44px;height:44px;flex:0 0 44px;border-radius:50%;display:flex;align-items:center;justify-content:center;padding:0}
.pep .t{flex:1;min-width:0}
.pep .t b{display:block;font-size:14px;line-height:1.25}
.pep .t small{color:var(--dim);font-size:11.5px}
.pep .t p{margin:3px 0 0;color:var(--soft);font-size:12px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pep.done{opacity:.5}
.pep.cur .t b{color:var(--warn)}

/* recherche, réglages */
.pfield{margin:10px 12px 4px;min-height:46px;padding:12px 14px;border:1px solid var(--edge);border-radius:10px;background:var(--bg2);font-size:16px;word-break:break-all}
.pfield[data-empty="1"]::before{content:attr(data-placeholder);color:var(--dim)}
.pfield[data-empty="1"].on::before{content:""}
.pfield.on{border-color:var(--g);box-shadow:var(--glow)}
.pform{padding:4px 0 12px}
.pform p{margin:6px 12px;color:var(--soft);font-size:12.5px;line-height:1.5}
.psource{display:flex;align-items:center;gap:10px;margin:6px 12px;padding:10px 12px;border:1px solid #0f2a14;border-radius:10px}
.psource i{width:10px;height:10px;border-radius:50%;background:var(--dim);flex:0 0 auto}
.psource.on i{background:var(--g);box-shadow:var(--glow)}
.psource small{flex:1;color:var(--dim);font-size:12px}
.psource em{font-style:normal;font-size:12px;color:var(--soft)}

/* clavier */
#kbwrap{flex:0 0 auto;padding:4px;border-top:1px solid var(--edge);background:var(--bg)}
#kbbar{display:flex;justify-content:flex-end;padding:0 0 4px}
#kbbar button{height:30px;padding:0 14px;font-size:12px;border-radius:15px}
#app.kbopen #bar{display:none}

/* barre du lecteur */
#bar{flex:0 0 auto;background:linear-gradient(#07130a,#030803);border-top:1px solid var(--edge)}
.pprog{height:14px;display:flex;align-items:center;cursor:pointer;touch-action:none}
.pprog u{display:block;width:100%;height:4px;background:#0f2a14;text-decoration:none}
.pprog i{display:block;height:100%;width:0;background:var(--g);box-shadow:var(--glow)}
#bar .bin{display:flex;align-items:center;gap:10px;padding:2px 10px 8px}
#bnp{flex:1;min-width:0;display:flex;align-items:center;gap:10px;cursor:pointer}
#bnp img{width:44px;height:44px;border-radius:6px;object-fit:cover;background:#0a2410}
#bnp .t{min-width:0;display:flex;flex-direction:column}
#bnp b{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#bnp small{color:var(--dim);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#bctl{display:flex;align-items:center;gap:6px}

/* lecteur plein écran */
#np{position:fixed;inset:0;z-index:30;background:var(--bg);overflow:hidden}
#npbg{position:absolute;inset:-30px;background-size:cover;background-position:center;filter:blur(28px) brightness(.35);transform:scale(1.1)}
#npclose{position:absolute;top:8px;left:8px;z-index:2;background:rgba(3,10,4,.7)}
#npbody{position:relative;height:100%;display:flex;align-items:center;gap:26px;padding:20px 28px}
#npimg{width:min(300px,56vh);height:min(300px,56vh);object-fit:cover;border-radius:14px;box-shadow:0 10px 40px rgba(0,0,0,.7);flex:0 0 auto;background:#0a2410}
#npinfo{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px}
#nptitle{font-size:21px;font-weight:bold;line-height:1.25;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
#npsub{color:var(--soft);font-size:14px}
#npprog{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--soft)}
#npprog .pprog{flex:1}
#npctl{display:flex;justify-content:center;gap:16px;align-items:center}
#npextra{display:flex;gap:8px;flex-wrap:wrap;justify-content:center}
#npextra button{height:38px;padding:0 14px;border-radius:19px;font-size:13px}
#npdesc{color:var(--soft);font-size:12px;line-height:1.5;max-height:4.5em;overflow:hidden}
.pchip{margin:8px 12px 0;padding:8px 14px;border-radius:999px;border:1px solid var(--edge);background:transparent;color:var(--soft);font:inherit;font-size:13px}
.pchip.on{border-color:var(--accent,#5fd35f);color:var(--accent,#5fd35f)}
/* Croix « retirer de Reprendre l'écoute » : assez grande pour le doigt */
.pcard.resume{cursor:pointer}
.pcard .forget{position:absolute;top:4px;right:4px;width:36px;height:36px;padding:0;border-radius:50%;background:rgba(3,10,4,.82);border:1px solid var(--edge);color:var(--soft);font-size:16px;line-height:1}
WEBEOF_11
cat > "$APP_DIR/web/static/css/search.css" <<'WEBEOF_12'
/* Recherche */
input#qbox{width:calc(100% - 24px);box-sizing:border-box;outline:none}
#qbox{position:sticky;top:0;z-index:3;margin:6px 12px;padding:8px 12px;min-height:40px;border:1px solid var(--edge);border-radius:20px;background:var(--panel);font-size:18px;color:var(--g)}
/* Suggestions d'artistes : gros boutons faciles à toucher */
.qsug{padding-top:4px}
.qsug:empty{display:none}
.qsug button{height:46px;padding:0 18px;font-size:17px;border-radius:23px}
/* Saisie depuis le téléphone */
#phoneqr{position:fixed;inset:0;z-index:75;background:rgba(0,0,0,.8);display:flex;align-items:center;justify-content:center}
.pqbox{display:flex;gap:18px;align-items:center;background:var(--bg2);border:1px solid var(--g);border-radius:14px;padding:16px;max-width:94%}
.pqcode{background:#fff;padding:6px;border-radius:8px;line-height:0}
.pqcode svg{width:220px;height:220px}
.pqtext{display:flex;flex-direction:column;gap:10px;max-width:300px}
.pqtext b{font-size:18px}.pqtext span{color:var(--soft);font-size:14px;line-height:1.4}
.pqtext small{color:var(--dim);font-size:11px;word-break:break-all}
.pqtext button{height:44px;border-radius:22px;font-size:15px}
WEBEOF_12
cat > "$APP_DIR/web/static/js/boot.js" <<'WEBEOF_13'
"use strict";
// Démarrage de l'application

/* ---------- Démarrage ---------- */
(async () => {
  try { const j = await (await fetch("/settings")).json(); browseMode = j.browse_mode || browseMode; } catch (e) {}
  try { await api("ping"); tab("home"); }
  catch (e) {
    stack.push({title: "Subsonic", build: c => {}});
    $("#title").textContent = "Subsonic";
    main.innerHTML = '<div class="msg">' + esc(e.message) +
      "<br><br>Pour configurer : <b>~/.local/share/pi-media/set-subsonic.sh URL UTILISATEUR MOTDEPASSE</b></div>";
  }
})();
WEBEOF_13
cat > "$APP_DIR/web/static/js/components.js" <<'WEBEOF_14'
"use strict";
// Éléments d'interface : lignes, cartes, vues album/artiste/playlist

/* ---------- Éléments d'interface ---------- */
function row(img, title, sub, onclick, round) {
  const d = document.createElement("div");
  d.className = "row" + (round ? " round" : "");
  d.innerHTML = (img ? '<img src="' + img + '" loading="lazy" alt="">' : '<span class="ph"></span>') +
    '<div class="t"><b>' + esc(title) + "</b><small>" + esc(sub) + "</small></div>";
  d.onclick = onclick;
  return d;
}
function header(c, text) {
  const h = document.createElement("div"); h.className = "h"; h.textContent = text; c.appendChild(h); return h;
}
function iconBtn(icon, onclick, extraClass) {
  const b = document.createElement("button"); b.className = "sb" + (extraClass ? " " + extraClass : "");
  b.innerHTML = ic(icon, 22); b.onclick = e => { e.stopPropagation(); onclick(b); };
  return b;
}
function heartBtn(s) {
  const b = document.createElement("button");
  const paint = () => { const on = isStarred(s); b.className = "sb" + (on ? " on" : ""); b.innerHTML = ic(on ? "heartfill" : "heart", 22); };
  paint();
  b.onclick = async e => {
    e.stopPropagation();
    try {
      await toggleStar(s);
      paint(); refreshUI();
    } catch (err) { toast(err.message); }
  };
  return b;
}
function playNow(s) {      // joue ce titre tout de suite, sans perdre la file en cours
  if (!queue.length) { playQueue([s], 0); return; }
  queue.splice(qi + 1, 0, s);
  playIdx(qi + 1);
}
function songRows(c, songs, ctx) {
  const search = ctx && ctx.search;
  songs.forEach((s, i) => {
    const d = row(coverOf(s, 64), (s.track ? s.track + ". " : "") + s.title,
      (s.artist || "") + (s.duration ? " · " + fmt(s.duration) : ""), search ? () => playNow(s) : () => playQueue(songs, i));
    if (cur() && cur().id === s.id) d.classList.add("cur");
    if (search) d.appendChild(iconBtn("play", () => playNow(s)));
    d.appendChild(iconBtn("plus", () => enqueue([s], false)));
    if (!isExternal(s) || hasLocalHeart(s)) d.appendChild(heartBtn(s));
    d.appendChild(iconBtn("more", () => songMenu(s, ctx ? {playlistId: ctx.playlistId, localPlaylistId: ctx.localPlaylistId, index: i} : null)));
    c.appendChild(d);
  });
}
function actions(c, songs, extra) {
  const a = document.createElement("div"); a.className = "actions";
  if (songs.length) {
    const b1 = document.createElement("button"); b1.className = "primary"; b1.innerHTML = ic("play", 20) + " Lire";
    b1.onclick = () => { b1.className = "primary"; b2.className = ""; playQueue(songs, 0); };
    const b2 = document.createElement("button"); b2.innerHTML = ic("shuffle", 20) + " Aléatoire";
    b2.onclick = () => { b2.className = "primary"; b1.className = ""; playShuffled(songs); toast("Lecture aléatoire"); };
    a.appendChild(b1); a.appendChild(b2);
  }
  (extra || []).forEach(([icon, label, fn]) => {
    const b = document.createElement("button"); b.innerHTML = ic(icon, 20) + " " + label; b.onclick = fn; a.appendChild(b);
  });
  if (a.children.length) c.appendChild(a);
}
function card(al) {
  const d = document.createElement("div"); d.className = "card";
  d.innerHTML = (al.coverArt ? '<img src="' + cover(al.coverArt, 200) + '" loading="lazy" alt="">' : '<span class="ph"></span>') +
    "<b>" + esc(al.name || al.title) + "</b><small>" + esc((al.artist || "") + (al.year ? " · " + al.year : "")) + "</small>";
  d.onclick = () => openView(al.name || al.title, c => albumView(al.id, c));
  return d;
}
function artistCard(ar) {
  const d = document.createElement("div"); d.className = "card round";
  const src = ar.artistImageUrl || cover(ar.coverArt, 200);
  d.innerHTML = (src ? '<img src="' + esc(src) + '" loading="lazy" alt="">' : '<span class="ph"></span>') +
    "<b>" + esc(ar.name) + "</b>";
  d.onclick = () => openView(ar.name, c => artistView(ar.id, c));
  return d;
}
const albumRow = al => row(cover(al.coverArt), al.name || al.title,
  (al.artist || "") + (al.year ? " · " + al.year : ""),
  () => openView(al.name || al.title, c => albumView(al.id, c)));
const artistRow = ar => row(cover(ar.coverArt), ar.name,
  (ar.albumCount != null ? ar.albumCount + " album(s)" : ""),
  () => openView(ar.name, c => artistView(ar.id, c)), true);

function heroToggle(hero) { hero.querySelector("img").onclick = () => hero.classList.toggle("big"); }

async function albumView(id, c) {
  const al = (await api("getAlbum", {id})).album;
  const songs = al.song || [];
  const dur = songs.reduce((t, s) => t + (s.duration || 0), 0);
  const hero = document.createElement("div"); hero.className = "ahero";
  hero.innerHTML = '<img src="' + cover(al.coverArt, 500) + '" alt=""><div class="hinfo"><b>' + esc(al.name) +
    '</b><span class="lnk">' + esc(al.artist || "") + "</span><small>" + esc((al.year ? al.year + " · " : "") +
    songs.length + " titre(s) · " + fmt(dur)) + "</small></div>";
  heroToggle(hero);
  if (al.artistId) hero.querySelector(".lnk").onclick = () => openView(al.artist, cc => artistView(al.artistId, cc));
  c.appendChild(hero);
  actions(c, songs, [["plus", "Playlist", () => addToPlaylist(songs)]]);
  // appui long (1,5 s) sur la pochette : recharge cet album (titres + pochette) depuis le serveur
  const him = hero.querySelector("img");
  if (him) {
    let t = null;
    const stop = () => { if (t) { clearTimeout(t); t = null; } };
    him.addEventListener("pointerdown", () => { t = setTimeout(async () => {
      t = null; him.dataset.long = "1";
      bust[al.coverArt] = Date.now(); saveBust();
      try { await fetch("/cache/refresh?album=" + encodeURIComponent(id) + "&artist=" + encodeURIComponent(al.artistId || "")); toast("Album rafraîchi"); render(); } catch (e) { toast(e.message); }
    }, 1500); });
    ["pointerup", "pointerleave", "pointercancel"].forEach(ev => him.addEventListener(ev, stop));
    him.addEventListener("click", e => { if (him.dataset.long) { delete him.dataset.long; e.stopImmediatePropagation(); } }, true);
  }
  songRows(c, songs);
}
async function artistView(id, c) {
  const [d, inf] = await Promise.all([api("getArtist", {id}), api("getArtistInfo2", {id, count: 12}).catch(() => null)]);
  const ar = d.artist, info = (inf && inf.artistInfo2) || {};
  const albums = ar.album || [];
  const fallback = cover(ar.coverArt || (albums[0] && albums[0].coverArt), 400);
  const hero = document.createElement("div"); hero.className = "hero";
  hero.innerHTML = '<img alt=""><div class="hinfo"><b>' + esc(ar.name) + "</b><small>" + albums.length + " album(s)</small></div>";
  const img = hero.querySelector("img");
  img.onerror = () => { if (fallback && img.src.indexOf(fallback) < 0) img.src = fallback; };
  img.src = info.largeImageUrl || info.mediumImageUrl || fallback;
  heroToggle(hero);
  c.appendChild(hero);
  actions(c, [], [["radio", "Radio de l'artiste", () => radioFromArtist(ar.id, ar.name)]]);
  const bio = stripHtml(info.biography);
  if (bio) {
    const b = document.createElement("div"); b.className = "bio"; b.textContent = bio;
    const hint = document.createElement("div"); hint.className = "biohint"; hint.textContent = "Toucher pour lire la suite";
    b.onclick = () => { b.classList.toggle("open"); hint.textContent = b.classList.contains("open") ? "Toucher pour réduire" : "Toucher pour lire la suite"; };
    c.appendChild(b); c.appendChild(hint);
  }
  const topHolder = document.createElement("div"); c.appendChild(topHolder);
  api("getTopSongs", {artist: ar.name, count: 5}).then(j => {
    const songs = (j.topSongs && j.topSongs.song) || [];
    if (songs.length) { header(topHolder, "Titres populaires"); songRows(topHolder, songs); }
  }).catch(() => {});
  header(c, "Albums");
  const g = document.createElement("div"); g.className = "grid"; albums.forEach(al => g.appendChild(card(al))); c.appendChild(g);
  const sim = info.similarArtist || [];
  if (sim.length) {
    header(c, "Artistes similaires");
    const sh = document.createElement("div"); sh.className = "shelf"; sim.forEach(a => sh.appendChild(artistCard(a))); c.appendChild(sh);
  }
}
async function playlistView(id, c) {
  const p = (await api("getPlaylist", {id})).playlist;
  const songs = p.entry || [];
  actions(c, songs, [["trash", "Supprimer", () => openSheet("Supprimer « " + p.name + " » ?", [
    {icon: "trash", label: "Oui, supprimer la playlist", fn: async () => {
      try { await api("deletePlaylist", {id}); toast("Playlist supprimée"); stack.pop(); render(); } catch (e) { toast(e.message); } }}])]]);
  if (!songs.length) { c.insertAdjacentHTML("beforeend", '<div class="msg">Playlist vide. Ajoutez des titres avec le bouton « ⋯ » d’un morceau.</div>'); return; }
  songRows(c, songs, {playlistId: id});
}
WEBEOF_14
cat > "$APP_DIR/web/static/js/controls.js" <<'WEBEOF_15'
"use strict";
// Boutons du lecteur plein écran, raccourcis média

$("#flbtn").onclick = () => { $("#finf").hidden = true; openLyrics(); };
$("#fibtn").onclick = () => {
  const box = $("#finf"), s = cur();
  if (!box.hidden) { box.hidden = true; return; }
  if (!s) return;
  $("#flyr").hidden = true; $("#fqueue").hidden = true; box.hidden = false;
  box.innerHTML = "";
  if (infoData.img) { const im = document.createElement("img"); im.src = infoData.img; box.appendChild(im); }
  const t = document.createElement("h3"); t.textContent = s.artist || ""; box.appendChild(t);
  if (infoData.bio) { const p = document.createElement("p"); p.textContent = infoData.bio; box.appendChild(p); }
  (infoData.facts || []).forEach(f => { const p = document.createElement("p"); p.textContent = f.t; box.appendChild(p); });
  if (!infoData.bio && !(infoData.facts || []).length) { const p = document.createElement("p"); p.textContent = "Pas d\u2019informations trouvées (elles se chargent quelques secondes après le début du titre)."; box.appendChild(p); }
};
audio.ontimeupdate = () => {
  syncLyrics();
  if (audio.duration && isFinite(audio.duration)) {
    const pct = (100 * audio.currentTime / audio.duration) + "%";
    document.querySelectorAll(".prog i").forEach(i => { i.style.width = pct; });
    $("#ftcur").textContent = fmt(audio.currentTime); $("#ftdur").textContent = fmt(audio.duration);
  }
  const s = cur();
  if (!scrobbled && s && !isExternal(s) && audio.duration && (audio.currentTime > 240 || audio.currentTime > audio.duration / 2)) {
    scrobbled = true;
    api("scrobble", {id: s.id, submission: "true"}).catch(() => {});
  }
};
const toggle = () => { if (audio.src) { if (audio.paused) audio.play(); else audio.pause(); } };
const prevTrack = () => { if (audio.currentTime > 4) audio.currentTime = 0; else playIdx(qi - 1); };
$("#prog").onclick = seek; $("#fbar").onclick = seek;
$("#pp").onclick = toggle; $("#fpp").onclick = toggle;
$("#next").onclick = () => { playNext(); }; $("#fnext").onclick = () => { playNext(); };
$("#prev").onclick = prevTrack; $("#fprev").onclick = prevTrack;
$("#npheart").onclick = toggleHeart; $("#fheart").onclick = toggleHeart;
$("#fshuf").onclick = toggleShuffle;
$("#frep").onclick = () => { repeat = (repeat + 1) % 3; refreshUI(); };
$("#fplaylist").onclick = () => { const s = cur(); if (s && !isRadio(s)) addToPlaylist([s]); };
$("#fradio").onclick = () => { const s = cur(); if (s && !isExternal(s)) radioFromSong(s); else toast("Rien à lancer"); };
$("#fqbtn").onclick = () => {
  const q = $("#fqueue"); $("#flyr").hidden = true; $("#finf").hidden = true; q.hidden = !q.hidden; $("#fbody").hidden = !q.hidden;
  if (!q.hidden) renderQueue();
};
$("#fartist").onclick = async () => { const s = cur(); if (!s || !s.artist) return; const id = await artistIdOf(s); if (id) { closeFull(); openView(s.artist, c => artistView(id, c)); } };
$("#np").onclick = () => { if (cur()) { $("#full").hidden = false; $("#full").scrollTop = 0; $("#flyr").hidden = true; $("#finf").hidden = true; $("#fqueue").hidden = true; $("#fbody").hidden = false; refreshUI(); } };
$("#fclose").onclick = closeFull;
// Sécurité : l'écran plein écran ne doit jamais se décaler (la flèche verte de fermeture resterait hors de vue)
$("#full").addEventListener("scroll", () => { $("#full").scrollTop = 0; $("#full").scrollLeft = 0; });
$("#npshuf").onclick = toggleShuffle;
$("#nplist").onclick = () => {   // ouvre directement la file de lecture
  if (!cur()) { toast("File vide"); return; }
  $("#full").hidden = false; $("#full").scrollTop = 0; $("#flyr").hidden = true;
  $("#fqueue").hidden = false; $("#fbody").hidden = true;
  refreshUI(); renderQueue();
};
if ("mediaSession" in navigator) {
  const h = (a, f) => { try { navigator.mediaSession.setActionHandler(a, f); } catch (e) {} };
  h("play", () => audio.play()); h("pause", () => audio.pause());
  h("nexttrack", () => playNext()); h("previoustrack", prevTrack);
}
refreshUI();
WEBEOF_15
cat > "$APP_DIR/web/static/js/core.js" <<'WEBEOF_16'
"use strict";
// Outils, état partagé, réglages

// Toutes les requêtes de la page portent un en-tête qu'une page d'un autre site ne peut pas ajouter (anti-CSRF)
const _fetch = window.fetch.bind(window);
window.fetch = (u, o) => { o = o || {}; o.headers = Object.assign({"X-Requested-With": "pm"}, o.headers || {}); return _fetch(u, o); };
const $ = s => document.querySelector(s);
let browseMode = "folders";
fetch("/settings").then(r => r.ok ? r.json() : {}).then(j => { browseMode = j.browse_mode || "folders"; }).catch(() => {});
async function artistIdOf(s) {      // en mode dossiers, les titres n\u2019ont pas toujours d\u2019identifiant d\u2019artiste
  if (s.artistId) return s.artistId;
  try {
    const r = (await api("search3", {query: s.artist || "", artistCount: 5, albumCount: 0, songCount: 0})).searchResult3 || {};
    const n = (s.artist || "").toLowerCase();
    const a = (r.artist || []).find(x => (x.name || "").toLowerCase() === n) || (r.artist || [])[0];
    return a ? a.id : null;
  } catch (e) { return null; }
}
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = s => { s = Math.round(s || 0); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
// Versions d'URL pour forcer le rechargement d'une pochette (rafraîchissement d'un album ou de tout)
let bust = {}, bustAll = "";
try { bust = JSON.parse(localStorage.getItem("bust") || "{}"); bustAll = localStorage.getItem("bustAll") || ""; } catch (e) {}
const saveBust = () => { try { localStorage.setItem("bust", JSON.stringify(bust)); localStorage.setItem("bustAll", bustAll); } catch (e) {} };
const cover = (id, size) => id ? "/rest/getCoverArt.view?id=" + encodeURIComponent(id) + "&size=" + (size || 96) +
  ((bust[id] || bustAll) ? "&_b=" + (bust[id] || "") + bustAll : "") : "";
const coverOf = (s, size) => (s && s.imageUrl) || cover(s && s.coverArt, size);
const shuffled = a => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const stripHtml = h => h ? (new DOMParser().parseFromString(h, "text/html").body.textContent || "").replace(/\s*Read more on Last\.fm.*$/i, "").trim() : "";
const main = $("#main");
let toastTimer = null;
/* Clavier : quand il est ouvert, onglets et lecteur sont masqués pour laisser de la place aux résultats */
function setKb(open) { $("#kbwrap").hidden = !open; $("#app").classList.toggle("kbopen", open); }
WEBEOF_16
cat > "$APP_DIR/web/static/js/dialogs.js" <<'WEBEOF_17'
"use strict";
// Feuille d'actions et saisie de texte

/* ---------- Feuille d'actions et saisie de texte ---------- */
function openSheet(title, items) {
  $("#sheettitle").textContent = title;
  const l = $("#sheetlist"); l.innerHTML = "";
  items.forEach(it => {
    const b = document.createElement("button"); b.className = "si";
    b.innerHTML = (it.icon ? ic(it.icon, 22) : "") + "<span>" + esc(it.label) + "</span>";
    b.onclick = () => { closeSheet(); it.fn(); };
    l.appendChild(b);
  });
  $("#sheet").hidden = false;
}
const closeSheet = () => { $("#sheet").hidden = true; };
$("#sheetbg").onclick = closeSheet;

let askResolve = null, askVal = "";
const showAsk = () => { $("#askin").textContent = askVal + "▌"; };
new TouchKeyboard($("#askkb"), async k => {
  if (k === KEY.ENTER) return askDone(askVal.trim() || null);
  askVal = k === KEY.PASTE ? askVal + await clipboardText(toast) : applyKey(askVal, k);
  showAsk();
});
document.addEventListener("paste", e => {                    // Ctrl+V avec un clavier physique
  if ($("#ask").hidden) return;
  askVal += (e.clipboardData.getData("text") || "").trim(); showAsk();
});
function askText(title, initial) {
  return new Promise(res => {
    askResolve = res; askVal = initial || "";
    $("#asktitle").textContent = title; $("#askin").textContent = askVal + "▌";
    $("#ask").hidden = false;
  });
}
const askDone = v => { $("#ask").hidden = true; if (askResolve) { const r = askResolve; askResolve = null; r(v); } };
$("#askok").onclick = () => askDone(askVal.trim() || null);
$("#askcancel").onclick = () => askDone(null);
WEBEOF_17
cat > "$APP_DIR/web/static/js/engine.js" <<'WEBEOF_18'
"use strict";
// Moteur de lecture : l'élément audio habituel, ou le lecteur officiel YouTube intégré.
// Il imite les propriétés de l'élément audio (currentTime, paused, play()…) : le reste de l'application
// n'a pas besoin de savoir quel moteur joue.

const YT_STATE = {ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3};
const HANDLER_NAMES = ["onended", "onplaying", "onplay", "onpause", "onerror", "ontimeupdate"];

class YouTubeLoader {
  /* Charge l'API YouTube une seule fois, au premier titre YouTube */
  constructor() { this.promise = null; }
  load() {
    if (this.promise) return this.promise;
    this.promise = new Promise((resolve, reject) => {
      if (window.YT && window.YT.Player) return resolve(window.YT);
      window.onYouTubeIframeAPIReady = () => resolve(window.YT);
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.onerror = () => { this.promise = null; reject(new Error("YouTube injoignable")); };
      document.head.appendChild(script);
    });
    return this.promise;
  }
}

class PlayerEngine {
  constructor() {
    this.el = new Audio();
    this.dataset = this.el.dataset;
    this.mode = "html";                 // « html » ou « youtube »
    this.handlers = {};
    this.loader = new YouTubeLoader();
    this.player = null;                 // lecteur YouTube
    this.videoId = "";
    this.ytState = -1;
    this.ytError = null;
    this.ticker = null;
    HANDLER_NAMES.forEach(name => Object.defineProperty(this, name, {
      get: () => this.handlers[name],
      set: fn => { this.handlers[name] = fn; if (this.el.handlers) this.el.handlers[name] = fn; else this.el[name] = fn; }
    }));
  }

  fire(name) { if (this.handlers[name]) this.handlers[name](); }
  get isYouTube() { return this.mode === "youtube"; }

  /* Change la sortie du son (lecture haute fidélité : MpvAudio, voir hifi.js) */
  useOutput(el) {
    this.el.pause();
    this.el = el;
    this.dataset = el.dataset;
    HANDLER_NAMES.forEach(name => { if (this.handlers[name]) el.handlers ? (el.handlers[name] = this.handlers[name]) : (el[name] = this.handlers[name]); });
  }
  queueNext(url) { if (this.el.queueNext && !this.isYouTube) this.el.queueNext(url); }

  /* ---------- propriétés imitées ---------- */
  get paused() { return this.isYouTube ? ![YT_STATE.PLAYING, YT_STATE.BUFFERING].includes(this.ytState) : this.el.paused; }
  get src() { return this.isYouTube ? "youtube:" + this.videoId : this.el.src; }
  set src(value) { this.leaveYouTube(); this.el.src = value; }
  get currentTime() { return this.isYouTube ? this.ytCall("getCurrentTime", 0) : this.el.currentTime; }
  set currentTime(t) { if (this.isYouTube) this.ytCall("seekTo", null, t, true); else this.el.currentTime = t; }
  get duration() { return this.isYouTube ? this.ytCall("getDuration", 0) : this.el.duration; }
  get readyState() { return this.isYouTube ? (this.ytState === YT_STATE.PLAYING ? 4 : 0) : this.el.readyState; }
  get error() { return this.isYouTube ? this.ytError : this.el.error; }
  get volume() { return this.isYouTube ? this.ytCall("getVolume", 100) / 100 : this.el.volume; }
  set volume(v) {
    v = Math.min(1, Math.max(0, v));
    if (this.isYouTube) this.ytCall("setVolume", null, Math.round(v * 100)); else this.el.volume = v;
  }

  /* ---------- commandes ---------- */
  play() {
    if (this.isYouTube) { this.ytCall("playVideo"); return Promise.resolve(); }
    return this.el.play();
  }
  pause() { if (this.isYouTube) this.ytCall("pauseVideo"); else this.el.pause(); }
  load() { if (!this.isYouTube) this.el.load(); }
  removeAttribute(name) { this.leaveYouTube(); this.el.removeAttribute(name); }

  /* ---------- YouTube ---------- */
  loadYouTube(videoId) {
    this.el.pause(); this.el.removeAttribute("src"); this.el.load();
    this.mode = "youtube"; this.videoId = videoId; this.ytState = -1; this.ytError = null;
    document.body.classList.add("yt");
    this.loader.load().then(YT => this.startVideo(YT, videoId)).catch(() => this.failWith({code: "yt-load"}));
  }
  startVideo(YT, videoId) {
    if (!this.isYouTube || this.videoId !== videoId) return;          // un autre titre a été choisi entre-temps
    if (this.player) { this.player.loadVideoById(videoId); return; }
    this.player = new YT.Player("ytplayer", {
      width: "100%", height: "100%", videoId,
      playerVars: {autoplay: 1, controls: 0, playsinline: 1, rel: 0, iv_load_policy: 3, disablekb: 1, fs: 0},
      events: {onStateChange: e => this.onYouTubeState(e.data), onError: e => this.failWith({code: e.data})}
    });
    this.ticker = setInterval(() => { if (this.isYouTube && this.ytState === YT_STATE.PLAYING) this.fire("ontimeupdate"); }, 500);
  }
  onYouTubeState(state) {
    this.ytState = state;
    if (state === YT_STATE.PLAYING) { this.fire("onplay"); this.fire("onplaying"); }
    else if (state === YT_STATE.PAUSED) this.fire("onpause");
    else if (state === YT_STATE.ENDED) this.fire("onended");
  }
  failWith(error) { this.ytError = error; this.fire("onerror"); }
  ytCall(method, fallback, ...args) {
    try { if (this.player && this.player[method]) { const r = this.player[method](...args); return r === undefined ? fallback : r; } }
    catch (e) { /* lecteur pas encore prêt */ }
    return fallback;
  }
  leaveYouTube() {
    if (!this.isYouTube) return;
    this.ytCall("stopVideo");
    this.mode = "html"; this.videoId = ""; this.ytState = -1;
    document.body.classList.remove("yt");
  }
}
WEBEOF_18
cat > "$APP_DIR/web/static/js/ext.js" <<'WEBEOF_19'
"use strict";
// Musique d'ailleurs (écran du Pi seulement) : Jamendo, YouTube, playlists locales, réglages

let EXT = {jamendo: {enabled: false}, youtube: {enabled: false}};

async function extGet(path, params) {
  const r = await fetch("/ext/" + path + "?" + new URLSearchParams(params || {}));
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
  return j;
}
async function extPost(path, body) {
  const r = await fetch("/ext/" + path, {method: "POST", body: JSON.stringify(body || {}), headers: {"Content-Type": "application/json"}});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
  if (j.status) EXT = j.status;
  return j;
}
async function loadExtStatus() {
  try { EXT = await extGet("status"); } catch (e) { /* sources externes indisponibles : l'application reste complète */ }
  loadExtFavorites();
}

/* ---------- Favoris des titres d'ailleurs (le cœur de Subsonic ne les connaît pas) ---------- */
let EXT_FAVS = new Set();
const hasLocalHeart = s => !!(s && !isRadio(s) && (s.streamUrl || s.youtubeId));
async function loadExtFavorites() {
  try {
    const songs = (await extGet("favorites")).songs;
    EXT_FAVS = new Set(songs.map(x => x.id));
    return songs;
  } catch (e) { return []; }
}
/* Un seul point d'entrée pour tous les cœurs : titre Subsonic ou titre d'ailleurs */
const isStarred = s => hasLocalHeart(s) ? EXT_FAVS.has(s.id) : !!(s && s.starred);
async function toggleStar(s) {
  if (hasLocalHeart(s)) {
    const r = await extPost("favorite", {song: s});
    if (r.starred) EXT_FAVS.add(s.id); else EXT_FAVS.delete(s.id);
    return;
  }
  await api(s.starred ? "unstar" : "star", {id: s.id});
  s.starred = s.starred ? undefined : new Date().toISOString();
}

/* ---------- Lecteur YouTube : où l'afficher ---------- */
function placeVideo() {
  const box = $("#ytbox"), on = document.body.classList.contains("yt");
  box.hidden = !on;
  const cover = $("#fcover");
  if (!on) { cover.style.visibility = ""; return; }
  const showsCover = !$("#full").hidden && !$("#fbody").hidden && $("#fqueue").hidden && $("#flyr").hidden && $("#finf").hidden;
  box.classList.toggle("big", showsCover);
  const r = cover.getBoundingClientRect();
  for (const [prop, value] of [["left", r.left], ["top", r.top], ["width", r.width], ["height", r.height]]) {
    box.style[prop] = showsCover ? value + "px" : "";
  }
  cover.style.visibility = showsCover ? "hidden" : "";
}
setInterval(() => { if (document.body.classList.contains("yt")) placeVideo(); }, 700);

/* ---------- Recherche : section « Ailleurs » ---------- */
function extSearchSection(container, text) {
  if (text.length < 2) return;
  if (EXT.jamendo.enabled) jamendoResults(container, text);
  if (EXT.youtube.enabled) youtubeButton(container, text);
}
async function jamendoResults(container, text) {
  const holder = document.createElement("div"); container.appendChild(holder);
  try {
    const items = (await extGet("search", {src: "jamendo", q: text})).items;
    if (!items.length || !holder.isConnected) return;
    header(holder, "Ailleurs · Jamendo (musique libre)");
    songRows(holder, items, {search: true});
  } catch (e) { holder.innerHTML = '<div class="msg">Jamendo : ' + esc(e.message) + "</div>"; }
}
function youtubeButton(container, text) {
  const holder = document.createElement("div"); container.appendChild(holder);
  const box = document.createElement("div"); box.className = "actions";
  const b = document.createElement("button"); b.innerHTML = ic("radio", 20) + " Chercher aussi sur YouTube";
  b.onclick = async () => {
    b.disabled = true; b.textContent = "Recherche…";
    try {
      const items = (await extGet("search", {src: "youtube", q: text})).items;
      holder.innerHTML = "";
      header(holder, "Ailleurs · YouTube (vidéo visible, publicités possibles)");
      if (items.length) songRows(holder, items, {search: true}); else holder.insertAdjacentHTML("beforeend", '<div class="msg">Aucun résultat.</div>');
    } catch (e) { b.disabled = false; b.innerHTML = ic("radio", 20) + " Chercher aussi sur YouTube"; toast(e.message); }
  };
  box.appendChild(b); holder.appendChild(box);
}

/* ---------- Playlists locales ---------- */
function localPlaylistItems(songs) {
  const items = [{icon: "plus", label: "Nouvelle playlist locale…", fn: async () => {
    const name = await askText("Nom de la playlist locale", "");
    if (!name) return;
    try { await extPost("create", {name, songs}); toast("Playlist locale « " + name + " » créée"); } catch (e) { toast(e.message); }
  }}];
  return items;
}
async function localPlaylistChoices(songs) {
  const items = localPlaylistItems(songs);
  try {
    (await extGet("playlists")).lists.forEach(p => items.push({icon: "list", label: "Locale : " + p.name + " (" + p.count + ")", fn: async () => {
      try { const r = await extPost("add", {id: p.id, songs}); toast(r.added ? "Ajouté à « " + p.name + " »" : "Déjà dans « " + p.name + " »"); } catch (e) { toast(e.message); }
    }}));
  } catch (e) { /* on propose au moins la création */ }
  return items;
}
async function localPlaylistsSection(container) {
  header(container, "Playlists locales (ce Pi)");
  actions(container, [], [["plus", "Nouvelle playlist locale", async () => {
    const name = await askText("Nom de la playlist locale", "");
    if (!name) return;
    try { await extPost("create", {name}); toast("Playlist locale créée"); tab("playlists"); } catch (e) { toast(e.message); }
  }]]);
  try {
    (await extGet("playlists")).lists.forEach(p => container.appendChild(row("", p.name, p.count + " titre(s) · mélange possible avec la musique d’ailleurs",
      () => openView(p.name, c => localPlaylistView(p.id, c)))));
  } catch (e) { container.insertAdjacentHTML("beforeend", '<div class="msg">' + esc(e.message) + "</div>"); }
}
async function localPlaylistView(id, c) {
  const p = await extGet("playlist", {id});
  actions(c, p.songs, [["trash", "Supprimer", () => openSheet("Supprimer « " + p.name + " » ?", [
    {icon: "trash", label: "Oui, supprimer la playlist", fn: async () => {
      try { await extPost("delete", {id}); toast("Playlist supprimée"); stack.pop(); render(); } catch (e) { toast(e.message); } }}])]]);
  if (!p.songs.length) { c.insertAdjacentHTML("beforeend", '<div class="msg">Playlist vide. Ajoutez des titres avec le bouton « ⋯ » d’un morceau.</div>'); return; }
  songRows(c, p.songs, {localPlaylistId: id});
}

/* ---------- Réglages des sources ---------- */
const EXT_SOURCES = [
  {key: "jamendo", title: "Jamendo", field: "jamendo_id", label: "Client ID Jamendo",
   text: "Musique libre en streaming, sans publicité, qui se mélange à vos playlists. Catalogue indépendant, pas les grands titres. Clé gratuite : devportal.jamendo.com."},
  {key: "youtube", title: "YouTube", field: "youtube_key", label: "Clé API YouTube",
   text: "Presque tout le catalogue, avec le lecteur officiel de YouTube : la vidéo reste visible (petite fenêtre) et les publicités sont possibles. Clé gratuite (API YouTube Data v3, environ 100 recherches par jour) : console.cloud.google.com."}];

function externalSettingsView(c) {
  c.insertAdjacentHTML("beforeend", '<div class="msg" style="color:var(--soft)">Chaque source est désactivée tant que vous ne l’activez pas. Rien n’est envoyé à ces services sans activation.</div>');
  header(c, "Versions originales seulement — " + (EXT.studio !== false ? "oui" : "non"));
  c.insertAdjacentHTML("beforeend", '<div class="msg" style="color:var(--soft);padding-top:4px">Écarte les versions live, reprises, remix et karaoké quand le titre l’indique.</div>');
  actions(c, [], [[EXT.studio !== false ? "pause" : "play", EXT.studio !== false ? "Montrer toutes les versions" : "Versions originales seulement", async () => {
    try { await extPost("settings", {studio: EXT.studio === false}); render(); } catch (e) { toast(e.message); }
  }]]);
  EXT_SOURCES.forEach(src => {
    const st = EXT[src.key] || {};
    header(c, src.title + " — " + (st.enabled ? "activé" : st.configured ? "désactivé" : "clé manquante"));
    c.insertAdjacentHTML("beforeend", '<div class="msg" style="color:var(--soft);padding-top:4px">' + esc(src.text) + "</div>");
    actions(c, [], [
      ["plus", st.configured ? "Changer la clé" : "Saisir la clé", async () => {
        const v = await askText(src.label, "");
        if (!v) return;
        try { await extPost("settings", {[src.field]: v}); toast("Clé enregistrée"); render(); } catch (e) { toast(e.message); }
      }],
      [st.enabled ? "pause" : "play", st.enabled ? "Désactiver" : "Activer", async () => {
        try { await extPost("settings", {[src.key + "_on"]: !st.enabled}); render(); } catch (e) { toast(e.message); }
      }]]);
  });
}

loadExtStatus();
WEBEOF_19
cat > "$APP_DIR/web/static/js/guest.js" <<'WEBEOF_20'
"use strict";
// Invités AirPlay / Bluetooth (écran du Pi) :
// - un téléphone se met à jouer : la musique baisse, se met en pause, puis reprend quand il s'arrête ;
// - un téléphone se connecte et attend en pause : il passera après le titre en cours.

const FADE_MS = 1200;
const POLL_MS = 1500;
const HANDOVER_TIMEOUT_MS = 8000;      // le téléphone n'a pas démarré : on reprend notre musique

class GuestHandover {
  constructor(banner) {
    this.banner = banner;
    this.state = {status: null};
    this.armed = false;                  // « passera après ce titre » : automatique pour un téléphone qui vient d'arriver
    this.pausedForGuest = false;
    this.nextAfterGuest = false;         // passage en fin de titre : au retour, on enchaîne sur le titre suivant
    this.handoverAt = 0;
    this.lastPlayingAt = 0;
    this.quietPolls = 0;
  }

  start() {
    setInterval(() => { if (!audio.paused) this.lastPlayingAt = Date.now(); }, 500);
    setInterval(() => this.poll(), POLL_MS);
  }

  async poll() {
    let s;
    try { s = await (await fetch("/control/guest")).json(); } catch (e) { return; }
    const before = this.state.status;
    this.state = s;
    if (s.status === "waiting" && !before) this.armed = true;           // téléphone qui vient de se connecter
    if (s.status === "waiting" && before === "playing") this.armed = false;  // il vient de finir : pas de nouveau passage tout seul
    if (s.status === "playing") this.guestPlaying();
    else this.guestQuiet();
    this.paintBanner();
  }

  guestPlaying() {
    this.quietPolls = 0;
    this.handoverAt = 0;
    if (!audio.paused) { this.fadeOutAndPause(); this.pausedForGuest = true; }
    else if (Date.now() - this.lastPlayingAt < 4000) this.pausedForGuest = true;   // déjà mis en pause par le menu
  }

  guestQuiet() {
    if (!audio.paused) { this.pausedForGuest = false; this.nextAfterGuest = false; return; }   // on a relancé à la main
    if (this.handoverAt && Date.now() - this.handoverAt > HANDOVER_TIMEOUT_MS) {
      this.handoverAt = 0; this.armed = false;
      toast("Le téléphone n’a pas démarré : la musique reprend");
      this.resume();
      return;
    }
    if (this.pausedForGuest && !this.handoverAt && ++this.quietPolls >= 2) this.resume();
  }

  /* Appelée à la fin de chaque titre : true si on passe la main au téléphone (la page n'enchaîne pas) */
  onTrackEnd() {
    if (this.state.status !== "waiting" || !this.armed) return false;
    this.handOver(true);
    return true;
  }

  async handOver(afterTrack) {
    if (afterTrack) audio.pause();                       // titre terminé : on reste dessus en attendant le retour
    else if (!audio.paused) await this.fadeOutAndPause();
    try {
      const r = await fetch("/control/guest", {method: "POST"});
      if (!r.ok) throw new Error();
    } catch (e) {
      toast("Le téléphone ne répond pas");
      if (afterTrack) playNext(); else this.resume();
      return;
    }
    this.armed = false;
    this.pausedForGuest = true;
    this.nextAfterGuest = afterTrack;
    this.handoverAt = Date.now();
    toast("À " + this.state.label + " de jouer…");
    this.paintBanner();
  }

  resume() {
    this.pausedForGuest = false;
    this.quietPolls = 0;
    if (this.nextAfterGuest) {
      this.nextAfterGuest = false;
      if (qi + 1 < queue.length) { playIdx(qi + 1); return; }
      return;
    }
    if (cur()) this.fadeIn();
  }

  fadeOutAndPause() {
    return new Promise(done => {
      const start = audio.volume, steps = 12;
      let i = 0;
      const t = setInterval(() => {
        audio.volume = start * (1 - ++i / steps);
        if (i >= steps) { clearInterval(t); audio.pause(); audio.volume = start; done(); }
      }, FADE_MS / steps);
    });
  }

  fadeIn() {
    const target = audio.volume || 1, steps = 12;
    let i = 0;
    audio.volume = 0;
    audio.play().catch(() => {});
    const t = setInterval(() => {
      audio.volume = target * (++i / steps);
      if (i >= steps) clearInterval(t);
    }, FADE_MS / steps);
  }

  /* Bandeau discret au-dessus de la barre du lecteur */
  paintBanner() {
    if (typeof syncPreload === "function") syncPreload();   // haute fidélité : pas de titre préchargé si un téléphone attend
    const s = this.state, b = this.banner;
    const show = s.status === "waiting" && !this.handoverAt && !audio.paused && cur();
    b.hidden = !show;
    if (!show) return;
    b.innerHTML = "";
    const text = document.createElement("span");
    text.textContent = this.armed ? s.label + " en attente : passera après ce titre" : s.label + " connecté";
    b.appendChild(text);
    const button = (label, fn) => { const x = document.createElement("button"); x.type = "button"; x.textContent = label; x.onclick = fn; b.appendChild(x); };
    if (this.armed) button("Annuler", () => { this.armed = false; this.paintBanner(); });
    else button("Après ce titre", () => { this.armed = true; this.paintBanner(); });
    button("Maintenant", () => this.handOver(false));
  }
}

const guestHandover = (() => {
  const banner = document.createElement("div"); banner.id = "guestbar"; banner.hidden = true;
  document.body.appendChild(banner);
  const g = new GuestHandover(banner);
  g.start();
  return g;
})();
WEBEOF_20
cat > "$APP_DIR/web/static/js/hifi.js" <<'WEBEOF_21'
"use strict";
// Lecture haute fidélité (écran du Pi) : le son est joué par mpv sur le Pi, à la fréquence d'origine du fichier.
// MpvAudio imite l'élément <audio> (src, play(), pause(), currentTime…) : le reste de l'application ne change pas.

const HIFI_POLL_MS = 400;

class MpvAudio {
  constructor() {
    this.dataset = {};
    this.handlers = {};
    this.url = "";
    this.state = {pos: 0, duration: 0, paused: true, ended: null, errors: null};
    this.stateAt = Date.now();
    this.wantPaused = true;
    this.error = null;
    this.vol = 1;
    this.pauseTimer = null;
    this.nextUrl = null;
    this.timer = setInterval(() => this.poll(), HIFI_POLL_MS);
  }

  fire(name) { const fn = this.handlers[name] || this[name + "_"]; if (typeof fn === "function") fn(); }

  async cmd(action, extra) {
    const r = await fetch("/player/cmd", {method: "POST", headers: {"Content-Type": "application/json"},
                                          body: JSON.stringify(Object.assign({action}, extra || {}))});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
    return j;
  }

  /* ---------- propriétés de l'élément audio ---------- */
  get src() { return this.url; }
  set src(url) {
    clearTimeout(this.pauseTimer);              // loadTrack fait pause() puis src= : pas de coupure entre les deux
    this.url = url; this.error = null; this.wantPaused = false;
    this.state.pos = 0; this.stateAt = Date.now();
    this.cmd("load", {url}).catch(e => { this.error = {code: "hifi", message: e.message}; this.fire("onerror"); });
  }
  get paused() { return this.wantPaused || this.state.paused; }
  get currentTime() {
    const running = !this.paused ? (Date.now() - this.stateAt) / 1000 : 0;
    return Math.min(this.state.pos + running, this.state.duration || Infinity);
  }
  set currentTime(t) { this.state.pos = t; this.stateAt = Date.now(); this.cmd("seek", {value: t}).catch(() => {}); }
  get duration() { return this.state.duration || NaN; }
  get readyState() { return this.state.duration ? 4 : 0; }
  get volume() { return this.vol; }
  set volume(v) { this.vol = Math.min(1, Math.max(0, v)); this.cmd("volume", {value: Math.round(this.vol * 100)}).catch(() => {}); }

  /* ---------- commandes ---------- */
  play() {
    this.wantPaused = false;
    if (!this.url) return Promise.resolve();
    return this.cmd("play").then(() => { this.fire("onplay"); }).catch(() => {});
  }
  pause() {
    this.wantPaused = true;
    clearTimeout(this.pauseTimer);
    this.pauseTimer = setTimeout(() => { this.cmd("pause").catch(() => {}); this.fire("onpause"); }, 0);
  }
  load() {}
  removeAttribute(name) { if (name === "src") this.url = ""; }

  /* Titre suivant préchargé : mpv l'enchaîne sans blanc. null = rien à précharger */
  queueNext(url) {
    if (url === this.nextUrl) return;
    this.nextUrl = url;
    this.cmd("preload", {url: url || ""}).catch(() => { this.nextUrl = null; });
  }

  /* ---------- suivi de l'état de mpv ---------- */
  async poll() {
    let s;
    try { s = await (await fetch("/player/state")).json(); } catch (e) { return; }
    const before = this.state;
    this.state = s; this.stateAt = Date.now();
    if (before.ended !== null && s.ended > before.ended) {
      if (s.url && s.url !== this.url) { this.url = s.url; this.nextUrl = null; }   // mpv a enchaîné tout seul
      this.fire("onended");
    }
    if (before.errors !== null && s.errors > before.errors) { this.error = {code: "hifi"}; this.fire("onerror"); }
    if (before.paused && !s.paused) { this.fire("onplay"); this.fire("onplaying"); }
    if (!s.paused) this.fire("ontimeupdate");
  }
}

/* Au démarrage : si la lecture haute fidélité est activée, le lecteur de la page passe par mpv */
async function setupHifi() {
  try {
    const s = await (await fetch("/player/state")).json();
    window.HIFI = s;
    if (s.enabled && s.available) audio.useOutput(new MpvAudio());
  } catch (e) { /* mpv indisponible : lecture par le navigateur */ }
}

/* Titre qui suivra : préchargé dans mpv pour un enchaînement sans blanc */
function upcomingTrack() {
  if (typeof guestHandover === "object" && guestHandover && guestHandover.armed && guestHandover.state.status === "waiting") return null;
  if (repeat === 2) return null;
  const next = qi + 1 < queue.length ? queue[qi + 1] : (repeat === 1 ? queue[0] : null);
  return next && !next.youtubeId ? next : null;
}
function syncPreload() {
  if (!audio.queueNext) return;
  const next = upcomingTrack();
  audio.queueNext(next ? trackUrl(next, 0) : null);
}

async function toggleHifi() {
  const on = !(window.HIFI && window.HIFI.enabled);
  try {
    audio.pause();
    await fetch("/player/cmd", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({action: "enable", value: on})});
    toast(on ? "Lecture haute fidélité activée" : "Lecture par le navigateur");
    setTimeout(() => location.reload(), 800);       // le lecteur de la page change de sortie au rechargement
  } catch (e) { toast(e.message); }
}

setupHifi();
WEBEOF_21
cat > "$APP_DIR/web/static/js/history.js" <<'WEBEOF_22'
"use strict";
// Historique des recherches de l'écran du Pi : partagé par la page Musique et la page Podcasts

class SearchHistoryList {
  constructor(kind) { this.kind = kind; }

  async entries() {
    try { return (await (await fetch("/ext/history?kind=" + this.kind)).json()).entries || []; }
    catch (e) { return []; }                   // sans historique, la recherche reste utilisable
  }

  async change(action, text) {
    try {
      const r = await fetch("/ext/history", {method: "POST", body: JSON.stringify({kind: this.kind, action, text}),
        headers: {"Content-Type": "application/json", "X-Requested-With": "pm"}});
      return (await r.json()).entries || [];
    } catch (e) { return []; }
  }

  remember(text) {
    if ((text || "").trim().length >= 2) this.change("add", text.trim());
  }

  /* Affiche les recherches récentes dans container ; onPick(texte) relance la recherche */
  async show(container, onPick) {
    const list = await this.entries();
    if (!list.length || !container.isConnected) return;
    const box = document.createElement("div"); box.className = "hist";
    const paint = entries => {
      box.innerHTML = '<div class="histhead">Recherches récentes</div>';
      if (!entries.length) { box.remove(); return; }
      entries.forEach(text => box.appendChild(this.item(text, onPick, paint)));
      const clear = document.createElement("button"); clear.className = "histclear"; clear.textContent = "Effacer l’historique";
      clear.onclick = async () => paint(await this.change("clear"));
      box.appendChild(clear);
    };
    paint(list);
    container.appendChild(box);
  }

  item(text, onPick, repaint) {
    const line = document.createElement("div"); line.className = "histitem";
    const pick = document.createElement("button"); pick.className = "histtext"; pick.textContent = text;
    pick.onclick = () => onPick(text);
    const remove = document.createElement("button"); remove.className = "histdel"; remove.textContent = "✕";
    remove.setAttribute("aria-label", "Retirer « " + text + " »");
    remove.onclick = async e => { e.stopPropagation(); repaint(await this.change("remove", text)); };
    line.appendChild(pick); line.appendChild(remove);
    return line;
  }
}
WEBEOF_22
cat > "$APP_DIR/web/static/js/icons.js" <<'WEBEOF_23'
"use strict";
// Icônes (SVG)

/* ---------- Icônes ---------- */
const ICON = {
  play: "M8 5v14l11-7z", pause: "M6 5h4v14H6zM14 5h4v14h-4z",
  prev: "M6 6h2v12H6zM9.5 12l8.5 6V6z", next: "M16 6h2v12h-2zM6 18l8.5-6L6 6z",
  shuffle: "M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z",
  repeat: "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z",
  heart: "M16.5 3c-1.74 0-3.41.81-4.5 2.09C10.91 3.81 9.24 3 7.5 3 4.42 3 2 5.42 2 8.5c0 3.78 3.4 6.86 8.55 11.54L12 21.35l1.45-1.32C18.6 15.36 22 12.28 22 8.5 22 5.42 19.58 3 16.5 3zm-4.4 15.55l-.1.1-.1-.1C7.14 14.24 4 11.39 4 8.5 4 6.5 5.5 5 7.5 5c1.54 0 3.04.99 3.57 2.36h1.87C13.46 5.99 14.96 5 16.5 5c2 0 3.5 1.5 3.5 3.5 0 2.89-3.14 5.74-7.9 10.05z",
  heartfill: "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z",
  list: "M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z",
  down: "M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z",
  left: "M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z",
  radio: "M3.24 6.15C2.51 6.43 2 7.17 2 8v12c0 1.1.89 2 2 2h16c1.11 0 2-.9 2-2V8c0-1.11-.89-2-2-2H8.3l8.26-3.34L15.88 1 3.24 6.15zM7 20c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm13-8h-2v-2h-2v2H4V8h16v4z",
  disc: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 14.5c-2.49 0-4.5-2.01-4.5-4.5S9.51 7.5 12 7.5s4.5 2.01 4.5 4.5-2.01 4.5-4.5 4.5zm0-5.5c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1z",
  volume: "M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z",
  plus: "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
  refresh: "M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z",
  more: "M6 10c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm12 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-6 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z",
  user: "M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z",
  trash: "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"
};
const ic = (n, s) => '<svg viewBox="0 0 24 24" width="' + (s || 24) + '" height="' + (s || 24) + '" fill="currentColor"><path d="' + ICON[n] + '"/></svg>';

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 2800);
}
async function api(name, params) {
  const usp = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => { (Array.isArray(v) ? v : [v]).forEach(x => usp.append(k, x)); });
  const r = await fetch("/rest/" + name + ".view?" + usp);
  if (!r.ok) throw new Error("HTTP " + r.status);
  const j = (await r.json())["subsonic-response"];
  if (!j || j.status !== "ok") throw new Error((j && j.error && j.error.message) || "Erreur Subsonic");
  return j;
}
WEBEOF_23
cat > "$APP_DIR/web/static/js/keyboard.js" <<'WEBEOF_24'
"use strict";
// Clavier tactile de l'écran du Pi, commun aux pages Musique et Podcasts.
// Construit sur simple-keyboard (web/static/vendor, licence MIT) ; ici seulement la disposition et le branchement.
// Touches transmises à onKey : un caractère, ou KEY.ERASE / KEY.PASTE / KEY.ENTER.

const KEY = {ERASE: "⌫", PASTE: "⎘", ENTER: "⏎"};

const BOTTOM_ROW = "{paste} {space} . {enter}";
const KEY_LAYOUTS = {
  default: ["a z e r t y u i o p", "q s d f g h j k l m", "{shift} w x c v b n ' {bksp}", "{num} " + BOTTOM_ROW],
  shift: ["A Z E R T Y U I O P", "Q S D F G H J K L M", "{shift} W X C V B N ' {bksp}", "{num} " + BOTTOM_ROW],
  num: ["1 2 3 4 5 6 7 8 9 0", "é è ê à ç ù ô î - _", "{sym} , @ & / : ? ! {bksp}", "{abc} " + BOTTOM_ROW],
  sym: ["( ) [ ] < > | \\ = +", "$ % * ~ ^ ; \" # € £", "{num} ° § ` ¨ {bksp}", "{abc} " + BOTTOM_ROW]
};
const KEY_LABELS = {
  "{bksp}": "⌫", "{shift}": "⇧", "{num}": "123 é", "{abc}": "abc", "{sym}": "#+=",
  "{paste}": "Coller", "{space}": "Espace", "{enter}": "OK"
};
const KEY_THEMES = [
  {class: "del", buttons: "{bksp}"}, {class: "ok", buttons: "{enter}"}, {class: "space", buttons: "{space}"},
  {class: "paste", buttons: "{paste}"}, {class: "switch", buttons: "{shift} {num} {abc} {sym}"}
];
const PAGE_KEYS = {"{num}": "num", "{abc}": "default", "{sym}": "sym"};
const SPECIAL_KEYS = {"{bksp}": KEY.ERASE, "{space}": " ", "{enter}": KEY.ENTER, "{paste}": KEY.PASTE};

class TouchKeyboard {
  constructor(el, onKey) {
    this.onKey = onKey;
    el.classList.add("touch-keyboard");  // simple-keyboard exige une classe sur l'élément qui l'accueille
    this.board = new (SimpleKeyboard.default || SimpleKeyboard.SimpleKeyboard)(el, {
      layout: KEY_LAYOUTS, layoutName: "default", display: KEY_LABELS, buttonTheme: KEY_THEMES,
      theme: "hg-theme-default tkb",
      useButtonTag: true,               // de vrais boutons : accessibles et faciles à tester
      preventMouseDownDefault: true,    // le champ garde la main pendant la frappe
      onKeyPress: button => this.press(button)
      // appui long : simple-keyboard répète tout seul la touche (effacer en continu, par exemple)
    });
  }

  press(button) {
    if (button === "{shift}") return this.setPage(this.page === "shift" ? "default" : "shift");
    if (PAGE_KEYS[button]) return this.setPage(PAGE_KEYS[button]);
    this.onKey(SPECIAL_KEYS[button] || button);
    if (this.page === "shift" && !SPECIAL_KEYS[button]) this.setPage("default");     // majuscule pour une seule lettre
  }

  get page() { return this.board.options.layoutName; }

  setPage(name) {
    this.board.setOptions({layoutName: name});
    if (name === "shift") this.board.addButtonTheme("{shift}", "on");
    else this.board.removeButtonTheme("{shift}", "on");
  }
}

/* Texte du presse-papiers (une longue clé API, par exemple) */
async function clipboardText(onRefused) {
  try { return (await navigator.clipboard.readText()).trim(); }
  catch (e) { onRefused("Collage refusé : autorisez le presse-papiers dans le navigateur"); return ""; }
}

/* Applique une touche à un texte (sauf « coller », asynchrone, et « OK », propre à chaque champ) */
function applyKey(text, k) {
  return k === KEY.ERASE ? text.slice(0, -1) : text + k;
}
WEBEOF_24
cat > "$APP_DIR/web/static/js/lyrics.js" <<'WEBEOF_25'
"use strict";
// Paroles synchronisées et anecdotes

/* ---- Paroles et anecdotes ---- */
let infoId = null, lyr = null, lyrId = null, lines = [], lineEl = [], lineIdx = -1, plainEl = [], lastTouch = 0, lastAuto = 0;
let facts = [], factI = 0, factTimer = null, infoData = {};
const infoQ = s => "artist=" + encodeURIComponent(s.artist || "") + "&title=" + encodeURIComponent(s.title || "");
function showFact() {
  const box = $("#fanec");
  if (!facts.length) { box.hidden = true; return; }
  const f = facts[factI % facts.length]; factI++;
  box.style.opacity = 0;
  setTimeout(() => {
    const im = box.querySelector("img");
    if (infoData.img) { im.src = infoData.img; im.hidden = false; } else im.hidden = true;
    box.hidden = false; box.querySelector("b").textContent = f.k; box.querySelector("span").textContent = f.t;
    box.style.opacity = 1;
  }, 600);
}
function infoFor(s) {
  if (!s || isRadio(s) || !s.artist || !s.title) { facts = []; infoData = {}; $("#fanec").hidden = true; return; }
  if (infoId === s.id) return;
  infoId = s.id; facts = []; infoData = {}; factI = 0; $("#fanec").hidden = true;
  clearInterval(factTimer);
  const id = s.id;
  fetch("/info/facts?" + infoQ(s) + "&aid=" + encodeURIComponent(s.artistId || "") + "&album=" + encodeURIComponent(s.album || ""))
    .then(r => r.json()).then(j => {
      if (infoId !== id) return;
      infoData = j; facts = j.facts || []; factI = 0; showFact();
      factTimer = setInterval(() => { if ($("#full").hidden) return; showFact(); }, 14000);
    }).catch(() => {});
}
function parseLrc(t) {
  const out = [];
  (t || "").split("\n").forEach(l => {
    const m = l.match(/^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/);
    if (m) out.push({t: +m[1] * 60 + parseFloat(m[2]), s: m[3].trim()});
  });
  return out;
}
async function openLyrics() {
  const s = cur(), box = $("#flyr");
  if (!s) return;
  if (!box.hidden) { box.hidden = true; return; }
  $("#fqueue").hidden = true; box.hidden = false;
  if (lyrId !== s.id) {
    lyrId = s.id; lyr = null; lines = []; lineEl = []; lineIdx = -1; plainEl = [];
    box.innerHTML = '<div class="msg">Recherche des paroles\u2026</div>';
    try {
      const j = await (await fetch("/info/lyrics?" + infoQ(s) + "&album=" + encodeURIComponent(s.album || "") + "&duration=" + (s.duration || 0))).json();
      if (lyrId !== s.id) return;
      lyr = j;
    } catch (e) { lyr = {}; }
    box.innerHTML = "";
    lines = parseLrc(lyr.synced);
    if (lines.length) {
      lineEl = lines.map(l => { const p = document.createElement("p"); p.textContent = l.s || "\u266a"; box.appendChild(p); return p; });
    } else if (lyr.plain) {
      lyr.plain.split("\n").forEach(l => { const p = document.createElement("p"); p.style.color = "var(--soft)"; p.textContent = l || "\u00a0"; box.appendChild(p); plainEl.push(p); });
    } else {
      box.innerHTML = '<div class="msg">Aucune parole trouvée pour ce titre.</div>';
    }
    if (lyr.src) { const sm = document.createElement("small"); sm.textContent = "Source : " + lyr.src + (lines.length ? "" : " · non synchronisées, défilement estimé"); box.appendChild(sm); }
  }
}
// Paroles sans synchronisation : défilement estimé d'après l'avancement du morceau (approximatif)
$("#flyr").addEventListener("pointerdown", () => { lastTouch = Date.now(); });
$("#flyr").addEventListener("wheel", () => { lastTouch = Date.now(); });
function autoScrollPlain() {
  const box = $("#flyr");
  if (!plainEl.length || box.hidden || !audio.duration || lyrId !== (cur() || {}).id) return;
  const now = Date.now();
  if (now - lastTouch < 8000 || now - lastAuto < 1500) return;     // l'utilisateur lit à son rythme : on ne le dérange pas
  lastAuto = now;
  const f = Math.min(1, Math.max(0, (audio.currentTime - 8) / Math.max(1, audio.duration - 30)));
  const k = Math.min(plainEl.length - 1, Math.floor(f * plainEl.length));
  const el = plainEl[k];
  box.scrollTo({top: el.offsetTop - box.clientHeight / 3, behavior: "smooth"});
}
function syncLyrics() {
  autoScrollPlain();
  if (!lines.length || $("#flyr").hidden || lyrId !== (cur() || {}).id) return;
  const t = audio.currentTime + 0.3;
  let k = -1;
  for (let i = 0; i < lines.length && lines[i].t <= t; i++) k = i;
  if (k === lineIdx) return;
  if (lineEl[lineIdx]) lineEl[lineIdx].classList.remove("cur");
  lineIdx = k;
  if (k >= 0) {
    const el = lineEl[k]; el.classList.add("cur");
    const box = $("#flyr");
    box.scrollTo({top: el.offsetTop - box.clientHeight / 2 + el.clientHeight / 2, behavior: "smooth"});
  }
}
WEBEOF_25
cat > "$APP_DIR/web/static/js/menus.js" <<'WEBEOF_26'
"use strict";
// Playlists, file d'attente, menus

/* ---------- Playlists, file d'attente, menus ---------- */
function enqueue(songs, next) {
  if (!queue.length) { playQueue(songs, 0); return; }
  if (next) queue.splice(qi + 1, 0, ...songs); else queue.push(...songs);
  toast(next ? "Lecture ensuite" : "Ajouté à la file d’attente");
  if (!$("#fqueue").hidden) renderQueue();
}
async function addToPlaylist(songs) {
  if (!songs.length) return;
  const external = songs.some(isExternal);          // une playlist Subsonic ne peut contenir que des titres de la bibliothèque
  try {
    const items = [];
    if (!external) {
      const ps = (await api("getPlaylists")).playlists.playlist || [];
      const ids = songs.map(s => s.id);
      items.push({icon: "plus", label: "Nouvelle playlist…", fn: async () => {
        const name = await askText("Nom de la nouvelle playlist", "");
        if (!name) return;
        try { await api("createPlaylist", {name, songId: ids}); toast("Playlist « " + name + " » créée"); } catch (e) { toast(e.message); }
      }});
      ps.forEach(p => items.push({icon: "list", label: p.name + " (" + p.songCount + ")", fn: async () => {
        try { await api("updatePlaylist", {playlistId: p.id, songIdToAdd: ids}); toast("Ajouté à « " + p.name + " »"); } catch (e) { toast(e.message); }
      }}));
    }
    (await localPlaylistChoices(songs)).forEach(it => items.push(it));
    openSheet("Ajouter à une playlist", items);
  } catch (e) { toast(e.message); }
}
function songMenu(s, ctx) {
  const items = [
    {icon: "next", label: "Lire ensuite", fn: () => enqueue([s], true)},
    {icon: "list", label: "Ajouter à la file d’attente", fn: () => enqueue([s], false)},
    {icon: "plus", label: "Ajouter à une playlist…", fn: () => addToPlaylist([s])},
    ];
  if (!isExternal(s)) items.push({icon: "radio", label: "Radio de ce titre", fn: () => radioFromSong(s)});
  if (s.albumId) items.push({icon: "disc", label: "Voir l’album", fn: () => { closeFull(); openView(s.album || "Album", c => albumView(s.albumId, c)); }});
  if (s.artist) items.push({icon: "user", label: "Voir l’artiste", fn: async () => { const id = await artistIdOf(s); if (!id) return toast("Artiste introuvable"); closeFull(); openView(s.artist || "Artiste", c => artistView(id, c)); }});
  if (ctx && ctx.playlistId) items.push({icon: "trash", label: "Retirer de cette playlist", fn: async () => {
    try { await api("updatePlaylist", {playlistId: ctx.playlistId, songIndexToRemove: ctx.index}); toast("Retiré"); render(); } catch (e) { toast(e.message); }
  }});
  if (ctx && ctx.localPlaylistId) items.push({icon: "trash", label: "Retirer de cette playlist locale", fn: async () => {
    try { await extPost("remove", {id: ctx.localPlaylistId, index: ctx.index}); toast("Retiré"); render(); } catch (e) { toast(e.message); }
  }});
  openSheet(s.title, items);
}
WEBEOF_26
cat > "$APP_DIR/web/static/js/mixbuilder.js" <<'WEBEOF_27'
"use strict";
// Créateur de mix par style

/* ---------- Créateur de mix par style ---------- */
const normG = g => (g || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]/g, "");
let genreCache = null;
async function genreGroups() {      // regroupe « Hip-Hop », « Hip hop », « hiphop »… en un seul style
  if (genreCache) return genreCache;
  const gs = ((await api("getGenres")).genres || {}).genre || [];
  const m = {};
  gs.forEach(g => {
    const k = normG(g.value); if (!k) return;
    const e = m[k] || (m[k] = {key: k, names: [], count: 0, best: 0, label: g.value});
    e.names.push(g.value); e.count += g.songCount || 0;
    if ((g.songCount || 0) > e.best) { e.best = g.songCount || 0; e.label = g.value; }
  });
  genreCache = Object.values(m).sort((a, b) => b.count - a.count);
  return genreCache;
}
const DECADES = [1960, 1970, 1980, 1990, 2000, 2010, 2020];
async function buildMix(o) {
  const variants = [].concat(...o.genres.map(g => g.names.slice(0, 4)));
  const ranges = o.decades.map(y => [y, y + 9]);
  const gl = variants.length ? variants : [null], dl = ranges.length ? ranges : [null];
  const jobs = [];
  gl.forEach(g => dl.forEach(r => jobs.push({g, r})));
  const per = Math.min(150, Math.max(30, Math.ceil(300 / jobs.length)));
  const pool = [];
  for (let i = 0; i < jobs.length; i += 3) {       // 3 requêtes à la fois : on ménage le serveur
    await Promise.all(jobs.slice(i, i + 3).map(async ({g, r}) => {
      const p = {size: per};
      if (g) p.genre = g;
      if (r) { p.fromYear = r[0]; p.toYear = r[1]; }
      try { pool.push(...((await api("getRandomSongs", p)).randomSongs || {}).song || []); } catch (e) {}
    }));
  }
  const inRanges = s => !ranges.length || (s.year && ranges.some(r => s.year >= r[0] && s.year <= r[1]));
  const inGenres = s => !o.genres.length || o.genres.some(g => g.names.some(n => normG(n) === normG(s.genre)));
  let seed = [], near = [], far = [];
  if (o.seed) {
    try { seed = (((await api("getSimilarSongs2", {id: o.seed.id, count: 80})).similarSongs2 || {}).song || []).filter(inRanges); } catch (e) {}
    try { seed = seed.concat((((await api("getTopSongs", {artist: o.seed.name, count: 15})).topSongs || {}).song || []).filter(inRanges)); } catch (e) {}
    const w = await similarWide(o.seed.id, o.wide ? 4 : 1, 5, 30);     // jusqu'à 4 niveaux si les premiers sont maigres
    near = w[1].filter(inRanges); far = w[2].concat(w[3], w[4]).filter(inRanges);
  }
  let favs = [];
  if (o.favs) {
    try { favs = (((await api("getStarred2")).starred2 || {}).song || []).filter(s => inRanges(s) && inGenres(s)); } catch (e) {}
  }
  const seen = new Set(), out = [], perArtist = {};
  let cap = 2;
  const take = (list, max) => {
    let n = 0;
    for (const s of shuffled(list)) {
      if (n >= max || out.length >= o.size) break;
      if (seen.has(s.id) || (perArtist[s.artist] || 0) >= cap) continue;
      seen.add(s.id); perArtist[s.artist] = (perArtist[s.artist] || 0) + 1; out.push(s); n++;
    }
  };
  take(seed, Math.ceil(o.size * 0.2));
  take(near, Math.ceil(o.size * (far.length ? 0.2 : 0.3)));
  take(far, Math.ceil(o.size * 0.2));
  take(favs, Math.ceil(o.size * 0.3));
  take(pool, o.size);
  if (out.length < o.size * 0.8) { cap = 5; take(pool, o.size); }   // peu de choix : on assouplit la limite par artiste
  if (!out.length) return out;
  if (o.order === "year") return out.sort((a, b) => (a.year || 0) - (b.year || 0));
  return spreadArtists(out);
}
async function mixBuilder(c) {
  const o = {genres: [], decades: [], seed: null, size: 60, favs: false, order: "mix", wide: true};
  const groups = await genreGroups();
  const chipRow = (title, wrap = true) => {
    header(c, title); const d = document.createElement("div"); d.className = "chips" + (wrap ? " wrap" : ""); c.appendChild(d); return d;
  };
  const toggle = (d, label, on, fn, cls) => {
    const b = document.createElement("button"); b.textContent = label; if (cls) b.className = cls;
    b.classList.toggle("on", !!on);
    b.onclick = () => { const v = fn(); b.classList.toggle("on", v); };
    d.appendChild(b); return b;
  };
  // Partir d'un artiste
  const sd = chipRow("Partir d’un artiste (facultatif)");
  const seedBtn = document.createElement("button"); seedBtn.textContent = "Choisir un artiste…"; sd.appendChild(seedBtn);
  // Styles
  const gh = chipRow("Styles");
  const gbtn = {};
  groups.slice(0, 40).forEach(g => {
    gbtn[g.key] = toggle(gh, g.label, false, () => {
      const i = o.genres.indexOf(g); if (i >= 0) o.genres.splice(i, 1); else o.genres.push(g);
      return i < 0;
    });
  });
  // Époques
  const dh = chipRow("Époques");
  DECADES.forEach(y => toggle(dh, "Années " + String(y).slice(2), false, () => {
    const i = o.decades.indexOf(y); if (i >= 0) o.decades.splice(i, 1); else o.decades.push(y);
    return i < 0;
  }));
  // Réglages
  const oh = chipRow("Réglages");
  const sizes = [30, 60, 100].map(n => toggle(oh, n + " titres", n === o.size, () => { o.size = n; sizes.forEach((b, i) => b.classList.toggle("on", [30, 60, 100][i] === n)); return true; }));
  toggle(oh, "Mes favoris d’abord", false, () => (o.favs = !o.favs));
  toggle(oh, "Artistes proches de proches (jusqu\u2019à 4 niveaux)", true, () => (o.wide = !o.wide));
  const ord = toggle(oh, "Chronologique", false, () => { o.order = o.order === "year" ? "mix" : "year"; return o.order === "year"; });
  // choix de l'artiste : recherche + styles suggérés par MusicBrainz
  seedBtn.onclick = safe(async () => {
    if (o.seed) { o.seed = null; seedBtn.textContent = "Choisir un artiste…"; seedBtn.classList.remove("on"); return; }
    const q = await askText("Nom de l’artiste", "");
    if (!q) return;
    const r = (await api("search3", {query: q, artistCount: 3, albumCount: 0, songCount: 0})).searchResult3 || {};
    const a = (r.artist || [])[0];
    if (!a) { toast("Artiste introuvable"); return; }
    o.seed = a; seedBtn.textContent = "Comme : " + a.name + "  ✕"; seedBtn.classList.add("on");
    try {
      const j = await (await fetch("/info/genres?artist=" + encodeURIComponent(a.name))).json();
      let n = 0;
      (j.genres || []).forEach(name => {
        const k = normG(name);
        const g = groups.find(x => x.key === k) || groups.find(x => x.key.length > 3 && (x.key.includes(k) || k.includes(x.key)));
        if (g && gbtn[g.key] && !gbtn[g.key].classList.contains("sug")) {
          gbtn[g.key].classList.add("sug");
          if (n++ < 3 && o.genres.indexOf(g) < 0) { o.genres.push(g); gbtn[g.key].classList.add("on"); }
        }
      });
      if (n) toast("Styles suggérés : " + n);
    } catch (e) {}
  });
  // Actions
  const run = async save => {
    toast("Création du mix…");
    const songs = await buildMix(o);
    if (!songs.length) { toast("Aucun titre ne correspond"); return; }
    if (!save) { playQueue(songs, 0); toast(songs.length + " titres"); return; }
    const label = o.genres.map(g => g.label).slice(0, 2).join(" + ") || (o.seed ? o.seed.name : "Mix");
    const name = await askText("Nom de la playlist", "Mix " + label + (o.decades.length ? " " + o.decades.map(y => String(y).slice(2) + "s").join("/") : ""));
    if (!name) return;
    await api("createPlaylist", {name, songId: songs.map(x => x.id)});
    toast("Playlist « " + name + " » créée (" + songs.length + " titres)");
  };
  const a = document.createElement("div"); a.className = "actions";
  const b1 = document.createElement("button"); b1.className = "primary"; b1.innerHTML = ic("play", 20) + " Lancer le mix"; b1.onclick = safe(() => run(false));
  const b2 = document.createElement("button"); b2.innerHTML = ic("plus", 20) + " Enregistrer en playlist"; b2.onclick = safe(() => run(true));
  a.appendChild(b1); a.appendChild(b2); c.appendChild(a);
}
WEBEOF_27
cat > "$APP_DIR/web/static/js/mixes.js" <<'WEBEOF_28'
"use strict";
// Mix et radios

/* ---------- Mix et radios ---------- */
async function mixRandom(params) {
  const j = await api("getRandomSongs", Object.assign({size: 60}, params || {}));
  const s = (j.randomSongs && j.randomSongs.song) || [];
  if (!s.length) { toast("Aucun titre trouvé"); return; }
  playQueue(s, 0, {endless: params || true});
}
async function mixFav() {
  const s = shuffled((((await api("getStarred2")).starred2.song) || []).concat(await loadExtFavorites()));
  if (!s.length) { toast("Aucun titre favori"); return; }
  playQueue(s, 0);
}
async function mixAlbums(type, n) {
  const al = ((await api("getAlbumList2", {type, size: n})).albumList2.album) || [];
  const songs = [];
  for (const a of al) songs.push(...(((await api("getAlbum", {id: a.id})).album.song) || []));
  if (!songs.length) { toast("Aucun titre trouvé"); return; }
  playQueue(songs, 0);
}
async function similarOf(s) {
  let sim = [];
  try { sim = ((await api("getSimilarSongs2", {id: s.id, count: 40})).similarSongs2.song) || []; } catch (e) {}
  if (!sim.length && s.genre) { try { sim = ((await api("getRandomSongs", {size: 40, genre: s.genre})).randomSongs.song) || []; } catch (e) {} }
  if (!sim.length) sim = ((await api("getRandomSongs", {size: 40})).randomSongs.song) || [];
  return sim;
}
async function radioFromSong(s) {
  try {
    const sim = await similarOf(s);
    if (cur() && cur().id === s.id) { queue = [s].concat(sim); qi = 0; shuffleOn = false; origQueue = null; endless = true; refreshUI(); }
    else playQueue([s].concat(sim), 0, {endless: true});
    toast("Radio lancée");
  } catch (e) { toast(e.message); }
}
async function radioFromArtist(id, name) {
  try {
    let sim = [];
    try { sim = ((await api("getSimilarSongs2", {id, count: 60})).similarSongs2.song) || []; } catch (e) {}
    if (sim.length < 10) { try { sim = sim.concat(((await api("getTopSongs", {artist: name, count: 30})).topSongs.song) || []); } catch (e) {} }
    toast("Radio de " + name + " : recherche des artistes proches…");
    const w = await similarWide(id, 4, 5, 40);    // niveaux 1 à 4, selon ce qu'on trouve
    const seen = new Set(), all = [];
    sim.concat(w[1], w[2], w[3], w[4]).forEach(s => { if (!seen.has(s.id)) { seen.add(s.id); all.push(s); } });
    if (!all.length) { toast("Pas de données Last.fm : activez-le dans les réglages du serveur"); return; }
    const mixed = spreadArtists(all);
    playQueue(mixed.slice(0, 100), 0);
    toast("Radio de " + name);
  } catch (e) { toast(e.message); }
}
const safe = f => async () => { try { await f(); } catch (e) { toast(e.message); } };
WEBEOF_28
cat > "$APP_DIR/web/static/js/nav.js" <<'WEBEOF_29'
"use strict";
// Navigation par onglets

/* ---------- Navigation ---------- */
const stack = [];
const tabs = {};
async function render() {
  const v = stack[stack.length - 1];
  $("#title").textContent = v.title;
  $("#top").hidden = stack.length <= 1;
  setKb(false);
  main.onscroll = null; main.innerHTML = ""; main.scrollTop = 0;
  main.classList.remove("in"); void main.offsetWidth; main.classList.add("in");
  try { await v.build(main); }
  catch (e) {
    main.innerHTML = '<div class="msg">' + esc(e.message) + '</div><div class="actions"><button id="retry">Réessayer</button></div>';
    const r = $("#retry"); if (r) r.onclick = () => render();
  }
}
function openView(title, build) { stack.push({title, build}); render(); }
$("#back").innerHTML = ic("left");
$("#back").onclick = () => { if (stack.length > 1) { stack.pop(); render(); } };
function tab(name) {
  stack.length = 0;
  document.querySelectorAll("nav button[data-t]").forEach(b => b.classList.toggle("on", b.dataset.t === name));
  tabs[name]();
}
document.querySelectorAll("nav button[data-t]").forEach(b => { b.onclick = () => tab(b.dataset.t); });
const closeFull = () => { $("#full").hidden = true; };
WEBEOF_29
cat > "$APP_DIR/web/static/js/pi.js" <<'WEBEOF_30'
"use strict";
// Fonctions réservées à l'écran du Raspberry Pi (volume, veille, pause à distance, menu)

const quitBtn = document.getElementById("quit");
quitBtn.hidden = false;
quitBtn.onclick = () => fetch("/control/quit").catch(() => {});
/* ---- Volume du Pi (écran local seulement) ---- */
let volTimer = null;
async function volCmd(d) {
  try {
    const j = await (await fetch("/control/volume" + (d ? "?d=" + d : ""))).json();
    if (j.volume !== undefined) $("#fvv").textContent = j.volume + " %";
    clearTimeout(volTimer); volTimer = setTimeout(() => { $("#fvol").hidden = true; }, 4000);
  } catch (e) {}
}
if (/^(127\.0\.0\.1|localhost)$/.test(location.hostname)) $("#fvbtn").hidden = false;
$("#fvbtn").onclick = () => { const v = $("#fvol"); v.hidden = !v.hidden; if (!v.hidden) volCmd(""); };
$("#fvm").onclick = () => volCmd("-5"); $("#fvp").onclick = () => volCmd("+5");
// Paroles affichées et musique en cours : on demande au menu de ne pas lancer l'écran de veille
setInterval(() => {
  if (!$("#full").hidden && !$("#flyr").hidden && !audio.paused) fetch("/control/awake?on=1").catch(() => {});
}, 15000);

/* Le menu du Pi peut demander une pause (ex. : une radio démarre ailleurs) */
setInterval(async () => {
  try {
    const j = await (await fetch("/control/poll")).json();
    if (j.cmd === "pause" && !audio.paused) audio.pause();
  } catch (e) {}
}, 1500);
WEBEOF_30
cat > "$APP_DIR/web/static/js/player.js" <<'WEBEOF_31'
"use strict";
// Lecteur audio : file, lecture, aléatoire, répétition

/* ---------- Lecteur ---------- */
const audio = new PlayerEngine();      // élément audio, ou lecteur YouTube (voir engine.js)
let queue = [], qi = -1, scrobbled = false;
let endless = null, shuffleOn = false, origQueue = null, repeat = 0;   // repeat : 0 non, 1 tout, 2 titre
const cur = () => queue[qi];
const isRadio = s => !!(s && String(s.id || "").startsWith("radio-"));        // radio Internet du serveur Subsonic
const isExternal = s => !!(s && (s.streamUrl || s.youtubeId));      // radio, Jamendo, YouTube : pas de scrobble ni de favori Subsonic

function playQueue(list, i, opts) {
  queue = list.slice(); endless = (opts && opts.endless) || null;
  shuffleOn = false; origQueue = null;
  playIdx(i);
}
function playShuffled(list) {
  queue = shuffled(list); origQueue = list.slice(); endless = null; shuffleOn = true;
  playIdx(0);
}
// Charge un titre dans un lecteur remis à zéro (un lecteur resté « à la fin » après un déplacement
// vers la fin du morceau ne doit jamais bloquer la suite). Garde-fou : si rien ne démarre en 12 s,
// on réessaie une fois avec une nouvelle requête, puis on passe au titre suivant.
let stuckTimer = null;
function trackUrl(s, attempt) {
  if (s.streamUrl) return s.streamUrl;
  let u = "/rest/stream.view?id=" + encodeURIComponent(s.id);
  // format=raw : le serveur envoie le fichier tel quel (FLAC, MP3…), sans recompression
  if (attempt < 2) u += "&format=raw";
  if (attempt > 0) u += "&_r=" + Date.now();
  return u;
}
function loadTrack(s, attempt) {
  clearTimeout(stuckTimer);
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  if (s.youtubeId) audio.loadYouTube(s.youtubeId); else audio.src = trackUrl(s, attempt);
  audio.dataset.attempt = String(attempt);
  audio.play().catch(() => {});
  stuckTimer = setTimeout(() => {
    const c = cur();
    if (!c || c.id !== s.id || audio.currentTime > 0 || (!audio.paused && audio.readyState >= 3)) return;
    if (attempt < 1) { loadTrack(s, attempt + 1); return; }
    toast("Ce titre ne démarre pas : passage au suivant");
    if (qi + 1 < queue.length) playIdx(qi + 1);
  }, 12000);
}
function playIdx(i) {
  if (i < 0 || i >= queue.length) return;
  qi = i; scrobbled = false;
  const s = queue[i];
  loadTrack(s, 0);
  refreshUI();
  if (!isExternal(s)) api("scrobble", {id: s.id, submission: "false"}).catch(() => {});
  if ("mediaSession" in navigator) {
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: s.title, artist: s.artist || "", album: s.album || "",
        artwork: coverOf(s, 256) ? [{src: coverOf(s, 256), sizes: "256x256"}] : []});
    } catch (e) {}
  }
}
async function playNext() {
  if (repeat === 2) { audio.currentTime = 0; audio.play().catch(() => {}); return; }
  if (qi + 1 < queue.length) return playIdx(qi + 1);
  if (endless) {
    try {
      const p = typeof endless === "object" ? endless : {};
      const j = await api("getRandomSongs", Object.assign({size: 40}, p));
      const more = ((j.randomSongs && j.randomSongs.song) || []);
      if (more.length) { queue = queue.concat(more); return playIdx(qi + 1); }
    } catch (e) {}
  }
  if (repeat === 1) return playIdx(0);
  audio.pause();
}
function toggleShuffle() {
  if (!queue.length) return;
  if (!shuffleOn) {
    origQueue = queue.slice();
    queue = queue.slice(0, qi + 1).concat(shuffled(queue.slice(qi + 1)));
    shuffleOn = true;
  } else {
    const id = cur() && cur().id;
    queue = origQueue || queue; origQueue = null; shuffleOn = false;
    const k = queue.findIndex(x => x.id === id); if (k >= 0) qi = k;
  }
  refreshUI();
}
async function toggleHeart() {
  const s = cur(); if (!s || (isExternal(s) && !hasLocalHeart(s))) return;
  try {
    await toggleStar(s);
    refreshUI();
  } catch (e) { toast(e.message); }
}
WEBEOF_31
cat > "$APP_DIR/web/static/js/playerui.js" <<'WEBEOF_32'
"use strict";
// Interface du lecteur (barre et plein écran)

/* ---------- Interface du lecteur ---------- */
function refreshUI() {
  const s = cur();
  if (typeof syncPreload === "function") syncPreload();      // haute fidélité : titre suivant préchargé (hifi.js)
  if (typeof sharedQueue === "object" && sharedQueue) sharedQueue.scheduleSave();   // file commune (queue.js)
  if (typeof placeVideo === "function") placeVideo();      // lecteur YouTube : voir ext.js
  const playing = !audio.paused && !!audio.src;
  $("#pp").innerHTML = ic(playing ? "pause" : "play", 30);
  $("#fpp").innerHTML = ic(playing ? "pause" : "play", 34);
  $("#prev").innerHTML = ic("prev"); $("#next").innerHTML = ic("next");
  $("#fprev").innerHTML = ic("prev", 28); $("#fnext").innerHTML = ic("next", 28);
  $("#fshuf").innerHTML = ic("shuffle", 24); $("#fshuf").classList.toggle("on", shuffleOn);
  $("#frep").innerHTML = ic("repeat", 24) + (repeat === 2 ? '<i class="one">1</i>' : ""); $("#frep").classList.toggle("on", repeat > 0);
  $("#fclose").innerHTML = ic("down", 28);
  $("#npshuf").innerHTML = ic("shuffle", 22); $("#npshuf").classList.toggle("on", shuffleOn);
  $("#nplist").innerHTML = ic("list", 24);
  $("#fplaylist").innerHTML = ic("plus", 18) + "<span>Playlist</span>";
  $("#fradio").innerHTML = ic("radio", 18) + "<span>Radio</span>";
  $("#fqbtn").innerHTML = ic("list", 18) + "<span>File</span>";
  $("#flbtn").innerHTML = ic("list", 18) + "<span>Paroles</span>";
  $("#fibtn").innerHTML = ic("user", 18) + "<span>Infos</span>";
  $("#fvbtn").innerHTML = ic("volume", 18) + "<span>Volume</span>"; $("#fvm").textContent = "\u2212"; $("#fvp").textContent = "+";
  if (!s) { $("#npheart").innerHTML = ic("heart", 24); return; }
  const fmtq = [s.suffix ? s.suffix.toUpperCase() : "", s.bitDepth && s.samplingRate ? s.bitDepth + " bits / " + (s.samplingRate / 1000) + " kHz" : "",
                s.bitRate ? s.bitRate + " kbps" : ""].filter(Boolean).join(" · ");
  const sub = (s.artist || "") + (s.album ? " · " + s.album : "") + (fmtq ? " · " + fmtq : "");
  $("#nptitle").textContent = s.title; $("#npsub").textContent = sub;
  $("#npimg").src = coverOf(s, 96);
  $("#ftitle").textContent = s.title; $("#fartist").textContent = s.artist || "";
  $("#falbum").textContent = (s.album || "") + (fmtq ? "  ·  " + fmtq : "");
  const big = coverOf(s, 400);
  $("#fcover").src = big; $("#fbg").style.backgroundImage = big ? 'url("' + big + '")' : "none";
  const starred = isStarred(s), hv = starred ? "heartfill" : "heart";
  $("#npheart").innerHTML = ic(hv, 24); $("#npheart").classList.toggle("on", starred);
  $("#fheart").innerHTML = ic(hv, 18) + "<span>" + (starred ? "Favori" : "Favoris") + "</span>";
  if (!$("#fqueue").hidden) renderQueue();
  if (!$("#full").hidden) infoFor(s);
}
function renderQueue(keepScroll) {
  const q = $("#fqueue"), top = q.scrollTop; q.innerHTML = "";
  queue.forEach((s, i) => {
    const d = row(coverOf(s, 64), s.title, (s.artist || "") + (s.duration ? " · " + fmt(s.duration) : ""), () => playIdx(i));
    if (i === qi) d.classList.add("cur");
    const g = document.createElement("button"); g.className = "grip"; g.innerHTML = ic("list", 22);
    g.onclick = e => e.stopPropagation();
    attachDrag(g, d, i);
    d.appendChild(g);
    q.appendChild(d);
  });
  if (keepScroll) { q.scrollTop = top; return; }
  const el = q.children[qi];      // pas de scrollIntoView : il décalait tout l'écran plein écran
  if (el) q.scrollTop = el.offsetTop - q.clientHeight / 2 + el.offsetHeight / 2;
}
// Réorganisation par glisser-déposer : on attrape la poignée à droite d'une ligne
function attachDrag(g, d, i) {
  g.onpointerdown = e => {
    e.preventDefault(); e.stopPropagation();
    const q = $("#fqueue"), rows = Array.from(q.children), hh = d.offsetHeight;
    g.setPointerCapture(e.pointerId);
    const y0 = e.clientY, s0 = q.scrollTop;
    let lastY = y0, to = i;
    d.classList.add("drag");
    const update = () => {
      const dy = lastY - y0 + (q.scrollTop - s0);
      d.style.transform = "translateY(" + dy + "px)";
      to = Math.max(0, Math.min(rows.length - 1, i + Math.round(dy / hh)));
      rows.forEach((r, k) => {
        if (r === d) return;
        let sh = 0;
        if (i < to && k > i && k <= to) sh = -hh; else if (i > to && k < i && k >= to) sh = hh;
        r.style.transform = sh ? "translateY(" + sh + "px)" : "";
      });
    };
    const timer = setInterval(() => {      // défilement automatique près des bords
      const r = q.getBoundingClientRect();
      if (lastY < r.top + 50) q.scrollTop -= 12; else if (lastY > r.bottom - 50) q.scrollTop += 12; else return;
      update();
    }, 16);
    g.onpointermove = ev => { lastY = ev.clientY; update(); };
    const end = () => {
      clearInterval(timer); g.onpointermove = g.onpointerup = g.onpointercancel = null;
      if (to !== i) {
        const m = queue.splice(i, 1)[0]; queue.splice(to, 0, m);
        if (qi === i) qi = to; else if (i < qi && to >= qi) qi--; else if (i > qi && to <= qi) qi++;
      }
      renderQueue(true);
    };
    g.onpointerup = g.onpointercancel = end;
  };
}
function seek(e) {
  const r = e.currentTarget.getBoundingClientRect();
  if (audio.duration && isFinite(audio.duration)) {
    const ratio = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    if (ratio > 0.985) { playNext(); return; }       // tout au bout de la barre : on passe directement au titre suivant
    audio.currentTime = audio.duration * ratio;
  }
}
audio.onended = () => {
  if (typeof guestHandover === "object" && guestHandover.onTrackEnd()) return;     // un téléphone attend son tour (guest.js)
  playNext();
};
audio.onplaying = () => clearTimeout(stuckTimer);
audio.onplay = refreshUI; audio.onpause = refreshUI;
// Codes d'erreur du lecteur YouTube intégré
const YT_ERRORS = {2: "paramètre refusé", 5: "lecteur HTML5", 100: "vidéo supprimée ou privée",
                   101: "intégration interdite", 150: "intégration interdite", 152: "intégration interdite",
                   153: "configuration du lecteur", "yt-load": "YouTube injoignable"};
const YT_VIDEO_REFUSALS = [100, 101, 150, 152];
/* Vidéo refusée : on cherche une autre vidéo du même titre (une seule fois), sinon titre suivant */
async function youtubeRefused(s, code) {
  const refused = YT_VIDEO_REFUSALS.includes(code);
  // seuls les refus propres à la vidéo la font retenir comme illisible ; les autres codes viennent plutôt de notre côté
  if (refused) extPost("unplayable", {id: s.youtubeId}).catch(() => {});
  const label = "Vidéo illisible (code " + code + (YT_ERRORS[code] ? " : " + YT_ERRORS[code] : "") + ")";
  if (refused && !s.altTried && EXT.youtube.enabled) {
    toast(label + " — recherche d’une autre version…");
    try {
      const alt = (await extGet("alternative", {id: s.youtubeId, title: s.title, artist: s.artist || ""})).item;
      if (alt && cur() === s) {
        queue[qi] = Object.assign({}, alt, {altTried: true});
        toast("Autre version trouvée : " + alt.title);
        playIdx(qi);
        return;
      }
    } catch (e) { /* pas de remplacement : on passe à la suite */ }
  }
  if (cur() !== s) return;
  if (refused && typeof offerYouTubeWindow === "function") { offerYouTubeWindow(s, label); return; }   // ytpopup.js
  toast(label + (qi + 1 < queue.length ? " — titre suivant" : ""));
  if (qi + 1 < queue.length) setTimeout(() => { if (cur() === s) playIdx(qi + 1); }, 1500);
}
audio.onerror = () => {
  const s = cur();
  if (s && s.youtubeId) { youtubeRefused(s, audio.error ? audio.error.code : "?"); return; }
  if (!s || s.streamUrl) { toast("Lecture impossible"); return; }
  const attempt = parseInt(audio.dataset.attempt || "0", 10);
  // 1) nouvelle requête ; 2) format non lisible par le navigateur (rare : APE, WMA…) : le serveur convertit
  if (attempt < 2) { loadTrack(s, attempt + 1); return; }
  const code = audio.error ? audio.error.code : "?";
  toast("Lecture impossible (code " + code + ")" + (qi + 1 < queue.length ? " : titre suivant" : ""));
  if (qi + 1 < queue.length) setTimeout(() => { if (cur() === s) playIdx(qi + 1); }, 1500);   // la file ne reste jamais bloquée
};
WEBEOF_32
cat > "$APP_DIR/web/static/js/pod-app.js" <<'WEBEOF_33'
"use strict";
// Podcasts : démarrage et onglets

const TABS = {
  home: ["Podcasts", pageHome], themes: ["Thèmes", pageThemes], search: ["Recherche", pageSearch],
  mine: ["Ma liste", pageMine], settings: ["Réglages", pageSettings]
};

function selectTab(name) {
  document.querySelectorAll("nav button[data-t]").forEach(b => b.classList.toggle("on", b.dataset.t === name));
  const [title, build] = TABS[name];
  showScreen(title, build, {root: true});
}

async function boot() {
  $("#back").innerHTML = ic("left", 22);
  $("#back").onclick = goBack;
  $("#quit").onclick = () => { player.saveNow(); fetch("/control/quit").catch(() => {}); };
  document.querySelectorAll("nav button[data-t]").forEach(b => { b.onclick = () => selectTab(b.dataset.t); });
  try {
    const status = await pget("status");
    sources = status.sources; themeList = status.themes; french = status.french !== false;
  } catch (e) { toast("Serveur indisponible : " + e.message); }
  selectTab("home");
}
boot();
WEBEOF_33
cat > "$APP_DIR/web/static/js/pod-core.js" <<'WEBEOF_34'
"use strict";
// Podcasts : outils communs (requêtes, formats, icônes, messages)

const $ = s => document.querySelector(s);
const main = $("#main");
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

/* ---------- Requêtes ---------- */
async function pget(name, params) {
  const r = await fetch("/podcast-api/" + name + "?" + new URLSearchParams(params || {}));
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
  return j;
}
async function ppost(name, body) {
  const r = await fetch("/podcast-api/" + name, {method: "POST", body: JSON.stringify(body || {}),
    headers: {"Content-Type": "application/json", "X-Requested-With": "pm"}});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
  return j;
}

/* ---------- Formats ---------- */
function fmtTime(s) {
  s = Math.max(0, Math.round(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0");
}
function fmtLength(s) {
  s = Math.round((s || 0) / 60);
  if (!s) return "";
  return s >= 60 ? Math.floor(s / 60) + " h " + String(s % 60).padStart(2, "0") : s + " min";
}
function fmtDate(t) {
  if (!t) return "";
  const days = Math.floor((Date.now() / 1000 - t) / 86400);
  if (days <= 0) return "aujourd’hui";
  if (days === 1) return "hier";
  if (days < 7) return "il y a " + days + " jours";
  return new Date(t * 1000).toLocaleDateString("fr-FR", {day: "numeric", month: "short", year: days > 300 ? "numeric" : undefined});
}
const stripTags = s => String(s || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

/* ---------- Icônes ---------- */
const ICON = {
  play: "M8 5v14l11-7z", pause: "M6 5h4v14H6zM14 5h4v14h-4z", left: "M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z",
  down: "M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z", check: "M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
  plus: "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
  back: "M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z",
  fwd: "M12 5V1l5 5-5 5V7c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6h2c0 4.42-3.58 8-8 8s-8-3.58-8-8 3.58-8 8-8z",
  mic: "M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"
};
const ic = (n, s) => '<svg viewBox="0 0 24 24" width="' + (s || 24) + '" height="' + (s || 24) + '" fill="currentColor"><path d="' + ICON[n] + '"/></svg>';

let toastTimer = null;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 2800);
}

/* ---------- Défilement au doigt (secours si le navigateur émule la souris) ---------- */
let dragState = null, dragSuppress = false;
document.addEventListener("pointerdown", e => {
  if (e.pointerType === "touch") return;
  const shelf = e.target.closest(".pshelf");
  const el = shelf || (e.target.closest("#main") ? main : null);
  if (el) dragState = {el, horiz: !!shelf, x: e.clientX, y: e.clientY, sl: el.scrollLeft, st: el.scrollTop, moved: false};
});
window.addEventListener("pointermove", e => {
  if (!dragState) return;
  const dx = e.clientX - dragState.x, dy = e.clientY - dragState.y;
  if (Math.abs(dx) > 6 || Math.abs(dy) > 6) dragState.moved = true;
  if (!dragState.moved) return;
  if (dragState.horiz) dragState.el.scrollLeft = dragState.sl - dx; else dragState.el.scrollTop = dragState.st - dy;
});
window.addEventListener("pointerup", () => {
  if (dragState && dragState.moved) { dragSuppress = true; setTimeout(() => { dragSuppress = false; }, 60); }
  dragState = null;
});
document.addEventListener("click", e => { if (dragSuppress) { e.stopPropagation(); e.preventDefault(); } }, true);
WEBEOF_34
cat > "$APP_DIR/web/static/js/pod-keyboard.js" <<'WEBEOF_35'
"use strict";
// Podcasts : champs de saisie branchés sur le clavier tactile commun (keyboard.js)

/* Un seul clavier, branché sur le champ « actif ». La touche OK valide le champ. */
let activeField = null;
const keyboard = new TouchKeyboard($("#kb"), k => { if (activeField) activeField.press(k); });
function showKeyboard(open) { $("#kbwrap").hidden = !open; $("#app").classList.toggle("kbopen", open); }
$("#kbclose").onclick = () => showKeyboard(false);

class TextField {
  /* secret : texte masqué ; onEnter(texte) à la touche OK ; onChange(texte) à chaque frappe */
  constructor(el, {secret = false, onEnter = null, onChange = null} = {}) {
    this.el = el; this.secret = secret; this.onEnter = onEnter; this.onChange = onChange; this.text = "";
    el.classList.add("pfield");
    el.onclick = () => this.focus();
    this.paint();
  }
  focus() {
    activeField = this;
    document.querySelectorAll(".pfield").forEach(f => f.classList.toggle("on", f === this.el));
    showKeyboard(true); this.paint();
  }
  async press(k) {
    if (k === KEY.PASTE) return this.insert(await clipboardText(toast));
    if (k === KEY.ENTER) { if (this.onEnter) this.onEnter(this.text); return; }
    this.text = applyKey(this.text, k);
    this.paint();
    if (this.onChange) this.onChange(this.text);
  }
  insert(text) {
    if (!text) return;
    this.text += text;
    this.paint();
    if (this.onChange) this.onChange(this.text);
  }
  paint() {
    const shown = this.secret ? "•".repeat(this.text.length) : this.text;
    this.el.textContent = shown + (activeField === this ? "▌" : "");
    this.el.dataset.empty = this.text ? "" : "1";
  }
}

document.addEventListener("paste", e => {                    // Ctrl+V avec un clavier physique
  if (activeField) activeField.insert((e.clipboardData.getData("text") || "").trim());
});
WEBEOF_35
cat > "$APP_DIR/web/static/js/pod-pages.js" <<'WEBEOF_36'
"use strict";
// Podcasts : les écrans (accueil, thèmes, recherche, ma liste, réglages, fiche d'un podcast)

/* ---------- Navigation : une pile d'écrans, le bouton retour dépile ---------- */
const navStack = [];
let sources = {itunes: true, podcastindex: false}, themeList = [], french = true;
let searchState = {text: "", items: null};
const podcastHistory = new SearchHistoryList("podcasts");
let pickSearch = null;                                // relance une recherche passée (défini par l'écran Recherche)         // dernière recherche : retrouvée en revenant en arrière

function showScreen(title, build, {root = false} = {}) {
  if (navStack.length) navStack[navStack.length - 1].scroll = main.scrollTop;
  if (root) navStack.length = 0;
  navStack.push({title, build});
  renderTop();
}
function renderTop() {
  const view = navStack[navStack.length - 1];
  $("#top").hidden = navStack.length < 2;
  $("#title").textContent = view.title;
  showKeyboard(false);
  main.innerHTML = "";
  main.classList.remove("in"); void main.offsetWidth; main.classList.add("in");
  main.scrollTop = 0;
  view.build(main);
  if (view.scroll) restoreScroll(view.scroll);
}
function restoreScroll(top) {
  [0, 250, 700].forEach(delay => setTimeout(() => { if (main.scrollHeight >= top) main.scrollTop = top; }, delay));
}
function goBack() {
  if (navStack.length < 2) return;
  navStack.pop();
  renderTop();
}

/* Charge des données puis construit l'écran ; une erreur réseau s'affiche à la place du contenu */
async function withData(container, loader, build) {
  container.appendChild(loadingMessage());
  let data;
  try { data = await loader(); } catch (e) { container.innerHTML = ""; container.appendChild(emptyMessage(e.message)); return; }
  if (!container.isConnected) return;
  container.innerHTML = "";
  build(data);
}

/* ---------- Accueil ---------- */
function pageHome(root) {
  withData(root, () => pget("home"), data => {
    if (data.resume.length) root.appendChild(shelf("Reprendre l’écoute", data.resume, resumeCard));
    if (data.subs.length) root.appendChild(shelf("Mes podcasts", data.subs.map(s => Object.assign({subscribed: true}, s)), podcastCard));
    const latest = el("section", "psection"); root.appendChild(latest);
    data.rows.forEach(r => root.appendChild(shelf(r.title, r.items, podcastCard)));
    if (!data.rows.length && !data.resume.length && !data.subs.length) root.appendChild(emptyMessage("Rien à afficher : essayez l’onglet Thèmes ou la Recherche."));
    if (data.subs.length) fillLatest(latest);
  });
}
async function fillLatest(section) {
  try {
    const lib = await pget("library");
    if (!lib.latest.length || !section.isConnected) return;
    section.appendChild(heading("Nouveaux épisodes"));
    lib.latest.slice(0, 8).forEach(e => section.appendChild(latestRow(e)));
  } catch (e) { /* l'accueil reste utilisable sans cette rangée */ }
}

/* ---------- Thèmes ---------- */
function pageThemes(root) {
  root.appendChild(heading("Parcourir par thème"));
  root.appendChild(frenchChip(() => {}));
  const tiles = el("div", "ptiles");
  themeList.forEach(t => tiles.appendChild(themeTile(t)));
  root.appendChild(tiles);
}
function openTheme(theme) {
  showScreen(theme.label, root => withData(root, () => pget("theme", {id: theme.key}), data => {
    root.appendChild(frenchChip(() => renderTop()));
    if (!data.items.length) return root.appendChild(emptyMessage("Aucun podcast trouvé pour ce thème."));
    if (!sources.podcastindex) root.appendChild(el("div", "phint", "Astuce : ajoutez une clé Podcast Index (Réglages) pour des tendances par thème plus riches."));
    root.appendChild(cardGrid(data.items));
  }));
}

/* ---------- Recherche ---------- */
function pageSearch(root) {
  root.appendChild(frenchChip(() => { if (searchState.text.trim().length >= 2) runSearch(searchState.text, results); }));
  const field = el("div", "psearch"); root.appendChild(field);
  const results = el("div", "presults"); root.appendChild(results);
  let timer = null;
  const input = new TextField(field, {onEnter: t => { clearTimeout(timer); showKeyboard(false); runSearch(t, results); },
                                      onChange: t => { searchState.text = t; clearTimeout(timer); timer = setTimeout(() => runSearch(t, results), 900); }});
  field.dataset.placeholder = "Touchez ici pour chercher un podcast…";
  pickSearch = text => { input.text = text; input.paint(); showKeyboard(false); runSearch(text, results); };
  results.addEventListener("click", e => { if (e.target.closest(".pcard")) podcastHistory.remember(searchState.text); }, true);   // un podcast ouvert = recherche utile
  if (searchState.text) {                                  // retour à la recherche : on retrouve texte et résultats
    input.text = searchState.text; input.paint();
    if (searchState.items) showResults(results, searchState.items, searchState.text);
  } else { input.focus(); podcastHistory.show(results, pickSearch); }
}
function showResults(results, items, text) {
  results.innerHTML = "";
  results.appendChild(items.length ? cardGrid(items) : emptyMessage("Aucun résultat pour « " + text + " »."));
}
async function runSearch(text, results) {
  searchState = {text, items: null};
  results.innerHTML = "";
  if (text.trim().length < 2) { if (pickSearch) podcastHistory.show(results, pickSearch); return; }
  results.appendChild(loadingMessage());
  try {
    const data = await pget("search", {q: text});
    searchState.items = data.items;
    if (results.isConnected) showResults(results, data.items, text);
  } catch (e) { if (results.isConnected) { results.innerHTML = ""; results.appendChild(emptyMessage(e.message)); } }
}

/* ---------- Ma liste ---------- */
function pageMine(root) {
  withData(root, () => pget("library"), lib => {
    if (!lib.subs.length) return root.appendChild(emptyMessage("Vous n’êtes abonné à aucun podcast. Ouvrez-en un et touchez « S’abonner »."));
    root.appendChild(heading("Mes abonnements"));
    root.appendChild(cardGrid(lib.subs.map(s => Object.assign({subscribed: true}, s))));
    if (lib.latest.length) {
      const sec = el("section", "psection"); sec.appendChild(heading("Derniers épisodes"));
      lib.latest.forEach(e => sec.appendChild(latestRow(e)));
      root.appendChild(sec);
    }
  });
}

/* ---------- Fiche d'un podcast ---------- */
function openShow(feed, card) {
  showScreen((card && card.title) || "Podcast", root => withData(root, () => pget("show", {feed}), show => {
    const head = el("div", "phero");
    head.appendChild(artwork(show.image || (card && card.image), show.title, "big"));
    const info = el("div", "pinfo");
    info.appendChild(el("b", "", esc(show.title)));
    if (show.author) info.appendChild(el("small", "", esc(show.author)));
    info.appendChild(el("p", "", esc(show.desc)));
    const actions = el("div", "pactions");
    actions.appendChild(subscribeButton(show, card));
    actions.appendChild(hideButton(show));
    info.appendChild(actions);
    head.appendChild(info);
    root.appendChild(head);
    const similar = el("div"); root.appendChild(similar);
    fillSimilar(similar, show, card);
    root.appendChild(heading(show.episodes.length + " épisodes"));
    const context = {feed, podcast: show.title, image: show.image};
    show.episodes.forEach(e => root.appendChild(episodeRow(e, context)));
  }));
}
async function fillSimilar(box, show, card) {
  try {
    const data = await pget("similar", {feed: show.feed, genre: (card && card.genre) || "", title: show.title});
    if (data.items.length && box.isConnected) box.appendChild(shelf("Dans le même genre", data.items, podcastCard));
  } catch (e) { /* la fiche reste utilisable sans cette rangée */ }
}
function subscribeButton(show, card) {
  const button = el("button", "primary");
  const paint = () => { button.innerHTML = show.subscribed ? ic("check", 18) + " Abonné" : ic("plus", 18) + " S’abonner"; };
  paint();
  button.onclick = async () => {
    try {
      if (show.subscribed) await ppost("unsubscribe", {feed: show.feed});
      else await ppost("subscribe", {feed: show.feed, title: show.title, image: show.image, author: show.author});
      show.subscribed = !show.subscribed; if (card) card.subscribed = show.subscribed; paint();
    } catch (e) { toast(e.message); }
  };
  return button;
}
function hideButton(show) {
  const button = el("button", "", "Masquer");
  button.onclick = async () => {
    try { await ppost("hide", {feed: show.feed}); toast("Podcast masqué"); goBack(); } catch (e) { toast(e.message); }
  };
  return button;
}

/* ---------- Réglages : annuaires et clé Podcast Index ---------- */
function pageSettings(root) {
  root.appendChild(heading("Langue"));
  root.appendChild(frenchChip(() => {}));
  root.appendChild(heading("Annuaires"));
  root.appendChild(sourceLine("Apple Podcasts", "toujours disponible, sans clé", true));
  const index = sourceLine("Podcast Index", "tendances par thème, plus de choix", sources.podcastindex);
  root.appendChild(index);
  const form = el("div", "pform");
  form.appendChild(el("p", "", "Clé gratuite à créer sur <b>api.podcastindex.org</b>. Touchez un champ pour saisir au clavier de l’écran (touche 123# pour les symboles)."));
  const keyBox = el("div"), secretBox = el("div");
  const key = new TextField(keyBox, {onEnter: () => secret.focus()});
  const secret = new TextField(secretBox, {secret: true, onEnter: () => save()});
  keyBox.dataset.placeholder = "Clé API"; secretBox.dataset.placeholder = "Secret";
  form.appendChild(keyBox); form.appendChild(secretBox);
  const actions = el("div", "pactions");
  const saveButton = el("button", "primary", "Enregistrer"); const clearButton = el("button", "", "Désactiver");
  actions.appendChild(saveButton); actions.appendChild(clearButton); form.appendChild(actions);
  root.appendChild(form);
  const save = () => storeKey(key.text.trim(), secret.text.trim());
  saveButton.onclick = save;
  clearButton.onclick = () => storeKey("", "");
}
function sourceLine(name, detail, on) {
  return el("div", "psource" + (on ? " on" : ""), "<i></i><b>" + esc(name) + "</b><small>" + esc(detail) + "</small><em>" + (on ? "actif" : "inactif") + "</em>");
}
async function storeKey(key, secret) {
  if ((key && !secret) || (!key && secret)) return toast("Il faut la clé et le secret");
  try {
    const r = await ppost("key", {key, secret});
    sources = r.sources;
    toast(key ? "Clé enregistrée" : "Podcast Index désactivé");
    showScreen("Réglages", pageSettings, {root: true});
  } catch (e) { toast(e.message); }
}
WEBEOF_36
cat > "$APP_DIR/web/static/js/pod-player.js" <<'WEBEOF_37'
"use strict";
// Podcasts : lecteur (reprise, ±15/30 s, vitesse, minuteur d'arrêt, enregistrement de la progression)

class PodcastPlayer {
  static SPEEDS = [1, 1.25, 1.5, 1.75, 2, 0.8];
  static SLEEP_STEPS = [0, 15, 30, 45, 60];
  static SAVE_EVERY_MS = 10000;

  constructor() {
    this.audio = new Audio();
    this.audio.preload = "auto";
    this.episode = null;
    this.speedIndex = 0;
    this.sleepIndex = 0;
    this.sleepTimer = null;
    this.lastSave = 0;
    this.bindAudio();
    this.bindControls();
  }

  isCurrent(id) { return !!this.episode && this.episode.id === id; }

  /* ---------- lecture ---------- */
  play(episode) {
    if (this.isCurrent(episode.id)) { this.toggle(); return; }
    this.saveNow();
    this.episode = episode;
    this.audio.src = episode.audio;
    this.audio.playbackRate = PodcastPlayer.SPEEDS[this.speedIndex];
    const start = episode.pos > 10 ? episode.pos : 0;
    this.audio.onloadedmetadata = () => { if (start) this.audio.currentTime = start; this.refresh(); };
    this.audio.play().catch(() => toast("Lecture impossible : épisode introuvable ou réseau coupé"));
    $("#bar").hidden = false;
    this.show();
    this.refresh();
  }
  toggle() { if (this.audio.paused) this.audio.play().catch(() => {}); else this.audio.pause(); }
  skip(seconds) { this.audio.currentTime = Math.max(0, Math.min(this.length(), this.audio.currentTime + seconds)); }
  seekRatio(ratio) { if (this.length()) this.audio.currentTime = ratio * this.length(); }
  length() { return this.audio.duration || (this.episode && this.episode.duration) || 0; }

  /* ---------- vitesse et minuteur ---------- */
  cycleSpeed() {
    this.speedIndex = (this.speedIndex + 1) % PodcastPlayer.SPEEDS.length;
    this.audio.playbackRate = PodcastPlayer.SPEEDS[this.speedIndex];
    this.refresh();
  }
  cycleSleep() {
    this.sleepIndex = (this.sleepIndex + 1) % PodcastPlayer.SLEEP_STEPS.length;
    clearTimeout(this.sleepTimer);
    const minutes = PodcastPlayer.SLEEP_STEPS[this.sleepIndex];
    if (minutes) this.sleepTimer = setTimeout(() => this.sleepNow(), minutes * 60000);
    this.refresh();
  }
  sleepNow() { this.audio.pause(); this.sleepIndex = 0; this.refresh(); toast("Minuteur : lecture arrêtée"); }

  /* ---------- progression ---------- */
  saveNow() {
    if (!this.episode) return;
    const e = this.episode;
    ppost("progress", {id: e.id, feed: e.feed, title: e.title, podcast: e.podcast, image: e.image, audio: e.audio,
                       pos: this.audio.currentTime || 0, dur: this.length()}).catch(() => {});
    this.lastSave = Date.now();
  }
  markDone() {
    if (!this.episode) return;
    ppost("played", {id: this.episode.id, played: true}).then(() => toast("Marqué comme écouté")).catch(() => {});
  }

  /* ---------- liaisons ---------- */
  bindAudio() {
    const a = this.audio;
    a.ontimeupdate = () => { this.paintProgress(); if (Date.now() - this.lastSave > PodcastPlayer.SAVE_EVERY_MS) this.saveNow(); };
    a.onpause = () => { this.saveNow(); this.refresh(); };
    a.onplay = () => this.refresh();
    a.onended = () => { this.saveNow(); this.refresh(); };
    a.onerror = () => toast("Erreur de lecture");
    window.addEventListener("pagehide", () => this.saveNow());
    setInterval(() => { if (!$("#np").hidden && !a.paused) fetch("/control/awake?on=1").catch(() => {}); }, 15000);
    setInterval(async () => {          // le menu du Pi peut demander une pause (une radio démarre ailleurs)
      try { if ((await (await fetch("/control/poll")).json()).cmd === "pause" && !a.paused) a.pause(); } catch (e) {}
    }, 1500);
  }
  bindControls() {
    $("#bpp").onclick = $("#nppp").onclick = () => this.toggle();
    $("#bback").onclick = $("#npback").onclick = () => this.skip(-15);
    $("#bfwd").onclick = $("#npfwd").onclick = () => this.skip(30);
    $("#npspeed").onclick = () => this.cycleSpeed();
    $("#npsleep").onclick = () => this.cycleSleep();
    $("#npdone").onclick = () => this.markDone();
    $("#bnp").onclick = () => { $("#np").hidden = false; this.refresh(); };
    $("#npclose").onclick = () => { $("#np").hidden = true; };
    for (const [id, host] of [["bprog", "#bprog"], ["npbar", "#npbar"]]) {
      $(host).onclick = ev => { const r = $(host).getBoundingClientRect(); this.seekRatio((ev.clientX - r.left) / r.width); };
    }
    $("#bback").innerHTML = $("#npback").innerHTML = ic("back", 26);
    $("#bfwd").innerHTML = $("#npfwd").innerHTML = ic("fwd", 26);
    $("#npclose").innerHTML = ic("down", 28);
  }

  /* ---------- affichage ---------- */
  show() {
    const e = this.episode;
    $("#btitle").textContent = $("#nptitle").textContent = e.title;
    $("#bsub").textContent = $("#npsub").textContent = e.podcast;
    $("#npdesc").textContent = e.desc || "";
    for (const sel of ["#bimg", "#npimg"]) { $(sel).src = e.image || ""; $(sel).style.visibility = e.image ? "visible" : "hidden"; }
    $("#npbg").style.backgroundImage = e.image ? 'url("' + e.image.replace(/"/g, "%22") + '")' : "none";
  }
  refresh() {
    const icon = ic(this.audio.paused ? "play" : "pause", 30);
    $("#bpp").innerHTML = $("#nppp").innerHTML = icon;
    $("#npspeed").textContent = PodcastPlayer.SPEEDS[this.speedIndex] + "×";
    const minutes = PodcastPlayer.SLEEP_STEPS[this.sleepIndex];
    $("#npsleep").textContent = minutes ? "Arrêt dans " + minutes + " min" : "Minuteur";
    this.paintProgress();
  }
  paintProgress() {
    const length = this.length(), now = this.audio.currentTime || 0;
    const width = (length ? Math.min(100, now / length * 100) : 0) + "%";
    document.querySelectorAll("#bprog i, #npbar i").forEach(i => { i.style.width = width; });
    $("#npcur").textContent = fmtTime(now);
    $("#npdur").textContent = fmtTime(length);
  }
}
const player = new PodcastPlayer();
WEBEOF_37
cat > "$APP_DIR/web/static/js/pod-views.js" <<'WEBEOF_38'
"use strict";
// Podcasts : éléments d'affichage (cartes, rangées, tuiles, épisodes)

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

/* Pochette : image, ou pastille colorée avec l'initiale si elle manque ou ne charge pas */
function artwork(url, title, cls) {
  const box = el("div", "art " + (cls || ""));
  const hue = [...(title || "?")].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  box.style.setProperty("--h", hue);
  box.innerHTML = '<span>' + esc((title || "?").trim().charAt(0).toUpperCase()) + '</span>';
  if (url) {
    const img = new Image();
    img.loading = "lazy"; img.alt = "";
    img.onload = () => { box.innerHTML = ""; box.appendChild(img); };
    img.src = url;
  }
  return box;
}

function podcastCard(p) {
  const card = el("button", "pcard");
  card.appendChild(artwork(p.image, p.title));
  card.appendChild(el("b", "", esc(p.title)));
  card.appendChild(el("small", "", esc(p.author || p.genre || "")));
  if (p.subscribed) card.appendChild(el("i", "badge", ic("check", 14)));
  card.onclick = () => openShow(p.feed, p);
  return card;
}

function heading(text) { return el("div", "ph", esc(text)); }

function shelf(title, items, build) {
  const wrap = el("section", "psection");
  wrap.appendChild(heading(title));
  const row = el("div", "pshelf");
  items.forEach(i => row.appendChild(build(i)));
  wrap.appendChild(row);
  return wrap;
}

function cardGrid(items) {
  const g = el("div", "pgrid");
  items.forEach(p => g.appendChild(podcastCard(p)));
  return g;
}

function themeTile(t) {
  const tile = el("button", "ptile", "<span>" + esc(t.label) + "</span>");
  tile.style.setProperty("--h", t.hue);
  tile.onclick = () => openTheme(t);
  return tile;
}

/* Épisode commencé : carte avec barre de progression, et une croix pour le retirer de la liste */
function resumeCard(e) {
  const card = el("div", "pcard resume");
  card.appendChild(artwork(e.image, e.podcast));
  card.appendChild(el("b", "", esc(e.title)));
  card.appendChild(el("small", "", esc(e.podcast) + " · reste " + fmtLength(e.dur - e.pos)));
  const bar = el("div", "mini", "<i></i>");
  bar.firstChild.style.width = Math.min(100, e.dur ? e.pos / e.dur * 100 : 0) + "%";
  card.appendChild(bar);
  card.onclick = () => player.play({id: e.id, feed: e.feed, title: e.title, podcast: e.podcast, image: e.image,
                                    audio: e.audio, duration: e.dur, pos: e.pos});
  const remove = el("button", "forget", "✕");
  remove.setAttribute("aria-label", "Retirer « " + e.title + " » de la liste");
  remove.onclick = async ev => {
    ev.stopPropagation();
    try {
      await ppost("forget", {id: e.id});
      const shelfEl = card.closest(".psection");
      card.remove();
      if (shelfEl && !shelfEl.querySelector(".pcard")) shelfEl.remove();     // plus rien à reprendre : la rangée disparaît
    } catch (err) { toast(err.message); }
  };
  card.appendChild(remove);
  return card;
}

/* Une ligne d'épisode. context : {feed, podcast, image} du podcast affiché */
function episodeRow(ep, context) {
  const row = el("div", "pep" + (ep.played ? " done" : "") + (player.isCurrent(ep.id) ? " cur" : ""));
  const play = el("button", "go", ic("play", 26));
  const info = el("div", "t");
  info.appendChild(el("b", "", esc(ep.title)));
  const meta = [fmtDate(ep.date), fmtLength(ep.duration)].filter(Boolean).join(" · ");
  info.appendChild(el("small", "", esc(meta) + (ep.pos > 10 ? " · repris à " + fmtTime(ep.pos) : "")));
  if (ep.desc) info.appendChild(el("p", "", esc(ep.desc)));
  if (ep.pos > 10 && ep.duration) {
    const bar = el("div", "mini", "<i></i>"); bar.firstChild.style.width = Math.min(100, ep.pos / ep.duration * 100) + "%";
    info.appendChild(bar);
  }
  row.appendChild(play); row.appendChild(info);
  row.onclick = () => player.play({id: ep.id, feed: context.feed, title: ep.title, podcast: context.podcast,
                                   image: ep.image || context.image, audio: ep.audio, duration: ep.duration,
                                   pos: ep.pos, desc: ep.desc});
  return row;
}

function latestRow(ep) {
  const row = episodeRow(ep, {feed: ep.feed, podcast: ep.podcast, image: ep.image});
  row.insertBefore(artwork(ep.image, ep.podcast, "small"), row.firstChild);
  const meta = row.querySelector("small");
  meta.textContent = ep.podcast + " · " + meta.textContent;
  return row;
}

function emptyMessage(text) { return el("div", "pmsg", esc(text)); }
function loadingMessage() { return el("div", "pmsg", "Chargement…"); }

/* Filtre « français uniquement » : puce à placer en tête des écrans qui listent des podcasts */
function frenchChip(onChange) {
  const chip = el("button", "pchip");
  const paint = () => { chip.classList.toggle("on", french); chip.textContent = french ? "Français uniquement : oui" : "Toutes les langues"; };
  paint();
  chip.onclick = async () => {
    try {
      const r = await ppost("language", {french: !french});
      french = r.french; paint(); onChange();
    } catch (e) { toast(e.message); }
  };
  return chip;
}
WEBEOF_38
cat > "$APP_DIR/web/static/js/queue.js" <<'WEBEOF_39'
"use strict";
// File d'attente commune (écran du Pi) : la file de la page est enregistrée sur le Pi à chaque changement
// (retrouvée après un redémarrage, visible des téléphones), et les ajouts faits depuis un téléphone y sont rangés.

const QUEUE_SAVE_DELAY_MS = 600;
const QUEUE_TAKE_EVERY_MS = 1500;

class SharedQueue {
  constructor() { this.saved = ""; this.timer = null; }

  start() {
    this.restore();
    setInterval(() => this.takeRequests(), QUEUE_TAKE_EVERY_MS);
  }

  /* Au démarrage : on retrouve la file enregistrée (sans lancer la lecture) */
  async restore() {
    if (queue.length) return;
    try {
      const state = await (await fetch("/queue/state")).json();
      if (!state.items.length || queue.length) return;
      queue = state.items.map(item => Object.assign({}, item.track, {_addedBy: item.addedBy}));
      qi = Math.max(-1, state.currentIndex);
      this.saved = this.signature();
      refreshUI();
    } catch (e) { /* pas de file enregistrée : on démarre vide */ }
  }

  signature() { return JSON.stringify([qi, queue.map(s => s.id + ":" + (s._addedBy || ""))]); }

  /* Appelée à chaque rafraîchissement de l'interface : n'envoie que si la file a changé */
  scheduleSave() {
    if (this.signature() === this.saved) return;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.save(), QUEUE_SAVE_DELAY_MS);
  }

  async save() {
    const signature = this.signature();
    const body = {currentIndex: qi, items: queue.map(s => ({track: s, addedBy: s._addedBy || "screen"}))};
    try {
      const r = await fetch("/queue/save", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      if (r.ok) this.saved = signature;
    } catch (e) { /* nouvel essai au prochain changement */ }
  }

  /* Ajouts demandés depuis un téléphone */
  async takeRequests() {
    let requests;
    try { requests = (await (await fetch("/queue/take", {method: "POST"})).json()).requests || []; } catch (e) { return; }
    if (!requests.length) return;
    const wasIdle = !cur() || (audio.paused && qi >= queue.length - 1);
    requests.forEach(request => this.insert(Object.assign({}, request.track, {_addedBy: request.addedBy}), request.mode));
    toast(requests.length === 1 ? "Ajouté depuis un téléphone : " + requests[0].track.title
                                : requests.length + " titres ajoutés depuis un téléphone");
    if (wasIdle) playIdx(Math.max(0, cur() ? qi + 1 : 0)); else refreshUI();
  }

  /* « après ce titre » : juste après le titre en cours, derrière les autres demandes « après ce titre » */
  insert(track, mode) {
    if (mode !== "next" || qi < 0) { queue.push(track); return; }
    let at = qi + 1;
    while (at < queue.length && queue[at]._playNext) at++;
    track._playNext = true;
    queue.splice(at, 0, track);
  }
}

const sharedQueue = new SharedQueue();
sharedQueue.start();
WEBEOF_39
cat > "$APP_DIR/web/static/js/remote.js" <<'WEBEOF_40'
"use strict";
// Taper depuis le téléphone (écran du Pi) : QR code à scanner, puis le texte tapé arrive dans la recherche

class PhoneRemote {
  constructor() { this.version = null; this.pickVersion = null; this.timer = null; this.overlay = null; this.shared = false; }

  /* Une seule fois : noms et identifiants des artistes, pour que le téléphone affiche les suggestions */
  shareArtists(artists) {
    if (this.shared || !artists.length) return;
    this.shared = true;
    fetch("/ext/remote/artists", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({artists: artists.map(a => ({id: a.id, name: a.name}))})}).catch(() => { this.shared = false; });
  }

  async fetchState(renew) {
    const r = await fetch("/ext/remote", renew ? {method: "POST"} : {});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
    return j;
  }

  /* Tant que l'écran de recherche est affiché, on regarde si le téléphone a envoyé du texte */
  watch(isVisible) {
    clearInterval(this.timer);
    this.version = this.pickVersion = null;
    this.timer = setInterval(async () => {
      if (!isVisible()) { clearInterval(this.timer); this.close(); return; }
      try {
        const s = await this.fetchState(false);
        if (this.version !== null && s.version !== this.version) this.received(s.text);
        if (this.pickVersion !== null && s.pickVersion !== this.pickVersion && s.pick) this.picked(s.pick);
        this.version = s.version; this.pickVersion = s.pickVersion;
      } catch (e) { /* serveur téléphone arrêté : la recherche au clavier reste disponible */ }
    }, 500);
  }

  received(text) {
    this.close();
    setKb(false);
    setSearchText(text);
  }

  /* Suggestion touchée sur le téléphone : l'artiste s'ouvre sur l'écran du Pi */
  picked(artist) {
    this.close();
    setKb(false);
    musicHistory.remember(qtext);
    openView(artist.name, c => artistView(artist.id, c));
  }

  async open() {
    let s;
    try { s = await this.fetchState(true); } catch (e) { toast(e.message); return; }   // nouveau code à chaque affichage
    this.version = s.version; this.pickVersion = s.pickVersion;
    this.close();
    const qr = qrcode(0, "M"); qr.addData(s.url); qr.make();
    const veil = document.createElement("div"); veil.id = "phoneqr";
    veil.innerHTML = '<div class="pqbox"><div class="pqcode"></div><div class="pqtext"><b>Scannez avec votre téléphone</b>'
      + "<span>Même Wi-Fi que le Pi. Ce que vous tapez sur le téléphone s’affiche ici, dans la recherche.</span>"
      + '<small></small><button type="button">Fermer</button></div></div>';
    veil.querySelector(".pqcode").innerHTML = qr.createSvgTag(5, 2);
    veil.querySelector("small").textContent = s.url;
    veil.querySelector("button").onclick = () => this.close();
    veil.onclick = e => { if (e.target === veil) this.close(); };
    document.body.appendChild(veil);
    this.overlay = veil;
  }

  close() { if (this.overlay) { this.overlay.remove(); this.overlay = null; } }
}

const phoneRemote = new PhoneRemote();

/* Petit bouton discret dans la barre du clavier : le clavier de l'écran reste la saisie principale */
function addPhoneButton() {
  const bar = $("#kbbar");
  if (!bar) return;
  const b = document.createElement("button"); b.type = "button"; b.id = "kbphone";
  b.textContent = "Saisir sur le téléphone";
  b.onclick = () => phoneRemote.open();
  bar.insertBefore(b, bar.firstChild);
}
addPhoneButton();
WEBEOF_40
cat > "$APP_DIR/web/static/js/search.js" <<'WEBEOF_41'
"use strict";
// Recherche

/* ---------- Suggestions : artistes de la bibliothèque, dès les premières lettres ---------- */
const plainText = s => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

class ArtistSuggestions {
  /* La liste des artistes vient de getArtists, déjà en cache côté serveur : rien à attendre du serveur Subsonic */
  constructor(limit) { this.limit = limit; this.artists = null; this.loading = null; }

  load() {
    if (!this.loading) {
      this.loading = api("getArtists").then(r => {
        this.artists = [];
        ((r.artists || {}).index || []).forEach(group => (group.artist || []).forEach(ar =>
          this.artists.push({ar, name: plainText(ar.name), words: plainText(ar.name).split(/[^a-z0-9]+/)})));
      }).catch(() => { this.loading = null; });
    }
    return this.loading;
  }

  /* Le nom commence par le texte tapé d'abord, puis un mot du nom qui commence par lui */
  find(text) {
    const wanted = plainText(text).trim();
    if (wanted.length < 2 || !this.artists) return [];
    const starts = [], inside = [];
    for (const a of this.artists) {
      if (a.name.startsWith(wanted)) starts.push(a.ar);
      else if (a.words.some(w => w.startsWith(wanted))) inside.push(a.ar);
      if (starts.length >= this.limit) break;
    }
    return starts.concat(inside).slice(0, this.limit);
  }

  show(container, text) {
    container.innerHTML = "";
    const found = this.find(text);
    if (!found.length) return;
    found.forEach(ar => {
      const b = document.createElement("button");
      b.textContent = ar.name;
      b.onclick = () => { musicHistory.remember(qtext); openView(ar.name, c => artistView(ar.id, c)); };
      container.appendChild(b);
    });
  }
}

/* ---------- Recherche avec clavier intégré ---------- */
let qtext = "", qtimer = null, qbox = null, qres = null, qsug = null;
const musicHistory = new SearchHistoryList("music");
const suggestions = new ArtistSuggestions(8);

/* Point d'entrée unique pour changer le texte : clavier, historique, téléphone */
function setSearchText(text) {
  qtext = text;
  if (qbox) qbox.textContent = qtext || "Artiste, album, titre…";
  if (qsug) suggestions.show(qsug, qtext);           // tout de suite, sans attendre le serveur
  runSearch();
}
const pickFromHistory = text => setSearchText(text);

function runSearch() {
  clearTimeout(qtimer);
  qtimer = setTimeout(async () => {
    if (!qres) return;
    qres.innerHTML = "";
    if (qtext.trim().length < 2) { musicHistory.show(qres, pickFromHistory); return; }
    try {
      const r = (await api("search3", {query: qtext.trim(), artistCount: 6, albumCount: 12, songCount: 30})).searchResult3 || {};
      if ((r.artist || []).length) { header(qres, "Artistes"); r.artist.forEach(ar => qres.appendChild(artistRow(ar))); }
      if ((r.album || []).length) { header(qres, "Albums"); r.album.forEach(al => qres.appendChild(albumRow(al))); }
      if ((r.song || []).length) { header(qres, "Titres"); songRows(qres, r.song, {search: true}); }
      if (!qres.children.length) qres.innerHTML = '<div class="msg">Aucun résultat.</div>';
      if (typeof extSearchSection === "function") extSearchSection(qres, qtext.trim());      // « Ailleurs » (ext.js)
    } catch (e) { qres.innerHTML = '<div class="msg">' + esc(e.message) + "</div>"; }
  }, 350);
}
new TouchKeyboard($("#kb"), async k => {
  if (k === KEY.ENTER) { setKb(false); return; }
  setSearchText(k === KEY.PASTE ? qtext + await clipboardText(toast) : applyKey(qtext, k));
});
tabs.search = () => openView("Recherche", async c => {
  qbox = document.createElement("div"); qbox.id = "qbox"; qbox.textContent = qtext || "Artiste, album, titre…";
  qsug = document.createElement("div"); qsug.className = "chips qsug";
  qres = document.createElement("div");
  // toucher un résultat = la recherche a servi : on la garde dans l'historique
  qres.addEventListener("click", e => { if (!e.target.closest(".hist, .msg")) musicHistory.remember(qtext); }, true);
  c.appendChild(qbox); c.appendChild(qsug); c.appendChild(qres);
  if (typeof phoneRemote === "object") phoneRemote.watch(() => qsug.isConnected);      // texte envoyé du téléphone (remote.js)
  setKb(true);
  qbox.onclick = () => { setKb(true); };          // toucher la zone rouvre le clavier
  main.onscroll = () => { if (main.scrollTop > 20) setKb(false); };   // défiler le ferme
  suggestions.load().then(() => {
    if (qsug && qsug.isConnected) suggestions.show(qsug, qtext);
    if (typeof phoneRemote === "object" && suggestions.artists) phoneRemote.shareArtists(suggestions.artists.map(a => a.ar));
  });
  runSearch();
});
$("#kbclose").onclick = () => { setKb(false); };
WEBEOF_41
cat > "$APP_DIR/web/static/js/similar.js" <<'WEBEOF_42'
"use strict";
// Artistes similaires sur plusieurs niveaux

/* ---------- Artistes similaires sur 2 niveaux ---------- */
async function runPool(items, n, fn) {
  let i = 0;
  await Promise.all(Array.from({length: Math.min(n, items.length)}, async () => { while (i < items.length) await fn(items[i++]); }));
}
// Artistes proches sur plusieurs niveaux : niveau 1 = proches de l'artiste, niveau 2 = proches de ceux-là, etc.
// On descend d'un niveau tant qu'on n'a pas assez d'artistes (target), jusqu'à maxDepth.
async function similarArtists(id, maxDepth, target) {
  const get = async (aid, count) => [].concat(((await api("getArtistInfo2", {id: aid, count})).artistInfo2 || {}).similarArtist || []);
  const seen = new Set([id]), all = [];
  let prev = [{id}];
  for (let lvl = 1; lvl <= (maxDepth || 1); lvl++) {
    const cur = [];
    const sources = lvl === 1 ? prev : shuffled(prev).slice(0, 8);
    await runPool(sources, 4, async src => {
      try {
        (await get(src.id, lvl === 1 ? 12 : 10)).forEach(x => {
          if (x.id && !seen.has(x.id)) { seen.add(x.id); const a = {id: x.id, name: x.name, level: lvl}; cur.push(a); all.push(a); }
        });
      } catch (e) {}
    });
    if (!cur.length || all.length >= (target || 30)) break;
    prev = cur;
  }
  return all;
}
// Titres populaires de ces artistes, rangés par niveau
async function similarWide(id, depth, perArtist, target) {
  const out = {1: [], 2: [], 3: [], 4: []};
  let arts = [];
  try { arts = await similarArtists(id, depth, target); } catch (e) {}
  await runPool(arts, 4, async a => {
    try { out[a.level].push(...([].concat(((await api("getTopSongs", {artist: a.name, count: perArtist || 5})).topSongs || {}).song || []))); } catch (e) {}
  });
  return out;
}
// Mélange sans deux titres du même artiste à la suite
function spreadArtists(list) {
  const res = []; let rest = shuffled(list);
  while (rest.length) {
    const k = rest.findIndex(s => !res.length || s.artist !== res[res.length - 1].artist);
    res.push(...rest.splice(k < 0 ? 0 : k, 1));
  }
  return res;
}
WEBEOF_42
cat > "$APP_DIR/web/static/js/tabs.js" <<'WEBEOF_43'
"use strict";
// Onglets : accueil, albums, artistes, favoris, playlists, radios

/* ---------- Onglets ---------- */
tabs.home = () => openView("Accueil", async c => {
  const tiles = document.createElement("div"); tiles.className = "tiles";
  [["shuffle", "Mix aléatoire", () => mixRandom()],
   ["heart", "Mix favoris", mixFav],
   ["disc", "Découverte", () => mixAlbums("random", 6)],
   ["radio", "Derniers ajouts", () => mixAlbums("newest", 3)],
   ["plus", "Créer un mix", () => openView("Créer un mix", mixBuilder)]].forEach(([icon, label, fn]) => {
    const b = document.createElement("button"); b.className = "tile";
    b.innerHTML = ic(icon, 28) + "<span>" + label + "</span>"; b.onclick = safe(fn); tiles.appendChild(b);
  });
  c.appendChild(tiles);
  const loaders = [["Écoutés récemment", "recent"], ["Ajoutés récemment", "newest"],
                   ["Plus écoutés", "frequent"], ["À redécouvrir", "random"]].map(([title, type]) => {
    const h = header(c, title); const sh = document.createElement("div"); sh.className = "shelf"; c.appendChild(sh);
    return async () => {
      try {
        const j = await api("getAlbumList2", {type, size: 14});
        ((j.albumList2 && j.albumList2.album) || []).forEach(al => sh.appendChild(card(al)));
        if (!sh.children.length) { h.remove(); sh.remove(); }
      } catch (e) { h.remove(); sh.remove(); }
    };
  });
  (async () => { for (const f of loaders) await f(); })();   // l'une après l'autre : ménage un serveur lent
  header(c, "Décennies"); const dc = document.createElement("div"); dc.className = "chips"; c.appendChild(dc);
  [1960, 1970, 1980, 1990, 2000, 2010, 2020].forEach(y => {
    const b = document.createElement("button"); b.textContent = "Années " + String(y).slice(2);
    b.onclick = safe(() => mixRandom({fromYear: y, toYear: y + 9})); dc.appendChild(b);
  });
  actions(c, [], [["list", "Classement : " + (browseMode === "folders" ? "dossiers" : "tags"), async () => {
    browseMode = browseMode === "folders" ? "tags" : "folders";
    try { await fetch("/settings?browse_mode=" + browseMode); toast("Classement par " + (browseMode === "folders" ? "dossiers" : "tags")); tab("home"); } catch (e) { toast(e.message); }
  }]].concat(window.HIFI && window.HIFI.available ? [["volume", "Haute fidélité : " + (window.HIFI.enabled ? "oui (mpv)" : "non (navigateur)"), toggleHifi]] : []).concat([["radio", "Sources externes (Jamendo, YouTube)", () => openView("Sources externes", externalSettingsView)], ["refresh", "Actualiser la bibliothèque", async () => {
    try { await fetch("/cache/clear"); toast("Bibliothèque actualisée"); tab("home"); } catch (e) { toast(e.message); }
  }]]));
  // appui long (1,5 s) sur « Actualiser » : tout vider, pochettes, bios et paroles compris
  const rb = Array.from(c.querySelectorAll("button")).find(b => /Actualiser/.test(b.textContent));
  if (rb) {
    let t = null;
    const start = () => { t = setTimeout(async () => {
      t = null; rb.dataset.long = "1";
      try { await fetch("/cache/clear?all=1"); bustAll = String(Date.now()); bust = {}; saveBust(); toast("Tout a été rafraîchi"); tab("home"); } catch (e) { toast(e.message); }
    }, 1500); };
    const stop = () => { if (t) { clearTimeout(t); t = null; } };
    rb.addEventListener("pointerdown", start); rb.addEventListener("pointerup", stop);
    rb.addEventListener("pointerleave", stop); rb.addEventListener("pointercancel", stop);
    rb.addEventListener("click", e => { if (rb.dataset.long) { delete rb.dataset.long; e.stopImmediatePropagation(); } }, true);
  }
});

tabs.albums = () => openView("Albums", async c => {
  const types = [["newest", "Récents"], ["recent", "Écoutés"], ["frequent", "Plus écoutés"],
                 ["random", "Aléatoire"], ["alphabeticalByName", "A-Z"], ["byYear", "Par année"]];
  const chips = document.createElement("div"); chips.className = "chips sticky";
  const grid = document.createElement("div"); grid.className = "grid";
  const note = document.createElement("div"); note.className = "msg"; note.style.color = "var(--soft)";
  note.textContent = "Chargement\u2026"; note.hidden = true;
  c.appendChild(chips); c.appendChild(note); c.appendChild(grid);
  async function load(type) {
    chips.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.t === type));
    grid.innerHTML = ""; main.scrollTop = 0;
    let offset = 0, done = false, busy = false;
    const size = 40;
    const more = async () => {
      if (done || busy) return;
      busy = true; note.hidden = false;
      try {
        const p = {type, size, offset};
        if (type === "byYear") { p.fromYear = 2030; p.toYear = 1900; }
        const a = ((await api("getAlbumList2", p)).albumList2.album) || [];
        a.forEach(al => grid.appendChild(card(al)));
        offset += a.length; if (a.length < size) done = true;
      } catch (e) { done = true; grid.insertAdjacentHTML("afterend", '<div class="msg">' + esc(e.message) + "</div>"); }
      busy = false; note.hidden = true;
    };
    main.onscroll = () => { if (main.scrollTop + main.clientHeight > main.scrollHeight - 300) more(); };
    await more();
  }
  types.forEach(([t, label]) => {
    const b = document.createElement("button"); b.textContent = label; b.dataset.t = t;
    b.onclick = () => load(t); chips.appendChild(b);
  });
  await load("newest");
});

tabs.artists = () => openView("Artistes", async c => {
  c.innerHTML = '<div class="msg" style="color:var(--soft)">Chargement des artistes\u2026<br>La première fois, avec une grande bibliothèque, cela peut prendre quelques minutes ; ensuite c\u2019est instantané.</div>';
  const idx = (await api("getArtists")).artists.index || [];
  c.innerHTML = "";
  const items = [];
  idx.forEach(g => { items.push({h: g.name}); (g.artist || []).forEach(ar => items.push({ar})); });
  if (!items.length) { c.innerHTML = '<div class="msg">Aucun artiste.</div>'; return; }
  const bar = document.createElement("div"); bar.className = "chips sticky";
  const list = document.createElement("div");
  c.appendChild(bar); c.appendChild(list);
  const heads = {};
  let shown = 0;
  const STEP = 80;     // lignes ajoutées à chaque fois : la page reste fluide même avec des milliers d'artistes
  const renderMore = upTo => {
    const end = Math.min(items.length, Math.max(shown + STEP, upTo || 0));
    for (; shown < end; shown++) {
      const it = items[shown];
      if (it.h !== undefined) heads[it.h] = header(list, it.h); else list.appendChild(artistRow(it.ar));
    }
  };
  idx.forEach(g => {
    const b = document.createElement("button"); b.textContent = g.name;
    b.onclick = () => {
      const k = items.findIndex(x => x.h === g.name);
      if (k >= shown) renderMore(k + 1);
      const el = heads[g.name];
      if (el) main.scrollTop = el.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop - 46;
    };
    bar.appendChild(b);
  });
  renderMore(0);
  main.onscroll = () => { if (shown < items.length && main.scrollTop + main.clientHeight > main.scrollHeight - 400) renderMore(0); };
});

tabs.fav = () => openView("Favoris", async c => {
  const s = (await api("getStarred2")).starred2 || {};
  const songs = (s.song || []).concat(await loadExtFavorites());       // Subsonic puis titres d'ailleurs, dans la même liste
  if (songs.length) { header(c, "Titres (" + songs.length + ")"); actions(c, songs, [["plus", "Playlist", () => addToPlaylist(songs)]]); songRows(c, songs); }
  if ((s.album || []).length) {
    header(c, "Albums"); const g = document.createElement("div"); g.className = "grid"; c.appendChild(g);
    s.album.forEach(al => g.appendChild(card(al)));
  }
  if ((s.artist || []).length) { header(c, "Artistes"); s.artist.forEach(ar => c.appendChild(artistRow(ar))); }
  if (!songs.length && !(s.album || []).length && !(s.artist || []).length)
    c.innerHTML = '<div class="msg">Aucun favori pour l’instant.</div>';
});

tabs.playlists = () => openView("Playlists", async c => {
  await localPlaylistsSection(c);
  header(c, "Playlists Subsonic");
  const ps = (await api("getPlaylists")).playlists.playlist || [];
  actions(c, [], [["plus", "Nouvelle playlist", async () => {
    const name = await askText("Nom de la nouvelle playlist", "");
    if (!name) return;
    try { await api("createPlaylist", {name}); toast("Playlist créée"); tab("playlists"); } catch (e) { toast(e.message); }
  }]]);
  if (!ps.length) { c.insertAdjacentHTML("beforeend", '<div class="msg">Aucune playlist pour l’instant.</div>'); return; }
  ps.forEach(p => c.appendChild(row(cover(p.coverArt), p.name, p.songCount + " titre(s)",
    () => openView(p.name, cc => playlistView(p.id, cc)))));
});

tabs.radios = () => openView("Radios", async c => {
  header(c, "Radios Internet");
  const holder = document.createElement("div"); c.appendChild(holder);
  api("getInternetRadioStations").then(j => {
    const st = (j.internetRadioStations && j.internetRadioStations.internetRadioStation) || [];
    if (!st.length) { holder.innerHTML = '<div class="msg">Aucune radio enregistrée sur le serveur Subsonic.</div>'; return; }
    st.forEach(r => holder.appendChild(row("", r.name, r.homePageUrl || "Radio Internet", () =>
      playQueue([{id: "radio-" + r.id, title: r.name, artist: "Radio Internet", album: "", streamUrl: r.streamUrl}], 0))));
  }).catch(() => { holder.innerHTML = '<div class="msg">Radios Internet indisponibles sur ce serveur.</div>'; });
  header(c, "Radio par genre");
  const gh = document.createElement("div"); gh.className = "tiles"; c.appendChild(gh);
  api("getGenres").then(j => {
    const gs = ((j.genres && j.genres.genre) || []).slice().sort((a, b) => (b.songCount || 0) - (a.songCount || 0)).slice(0, 30);
    if (!gs.length) { gh.innerHTML = '<div class="msg">Aucun genre trouvé.</div>'; return; }
    gs.forEach(g => {
      const b = document.createElement("button"); b.className = "tile";
      b.innerHTML = ic("radio", 26) + "<span>" + esc(g.value) + "</span>";
      b.onclick = safe(() => mixRandom({genre: g.value})); gh.appendChild(b);
    });
  }).catch(() => { gh.innerHTML = '<div class="msg">Genres indisponibles.</div>'; });
  header(c, "Radio d’artiste ou de titre");
  c.insertAdjacentHTML("beforeend", '<div class="msg" style="color:var(--soft)">Ouvrez la page d’un artiste puis « Radio de l’artiste », ou le menu « ⋯ » d’un titre puis « Radio de ce titre ». Les suggestions viennent de Last.fm via votre serveur.</div>');
});
WEBEOF_43
cat > "$APP_DIR/web/static/js/touchscroll.js" <<'WEBEOF_44'
"use strict";
// Défilement au doigt

/* ---------- Défilement au doigt (secours si le navigateur émule la souris) ---------- */
let drag = null, suppress = false;
document.addEventListener("pointerdown", e => {
  if (e.pointerType === "touch") return;
  const h = e.target.closest(".shelf, .chips");
  const el = h || e.target.closest("#fqueue, #sheetlist") || (e.target.closest("#main") ? main : null);
  if (!el) return;
  drag = {el, horiz: !!h, x: e.clientX, y: e.clientY, sl: el.scrollLeft, st: el.scrollTop, moved: false};
});
window.addEventListener("pointermove", e => {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (Math.abs(dx) > 6 || Math.abs(dy) > 6) drag.moved = true;
  if (!drag.moved) return;
  if (drag.horiz) drag.el.scrollLeft = drag.sl - dx; else drag.el.scrollTop = drag.st - dy;
});
window.addEventListener("pointerup", () => {
  if (drag && drag.moved) { suppress = true; setTimeout(() => { suppress = false; }, 60); }
  drag = null;
});
document.addEventListener("click", e => { if (suppress) { e.stopPropagation(); e.preventDefault(); } }, true);
WEBEOF_44
cat > "$APP_DIR/web/static/js/ytpopup.js" <<'WEBEOF_45'
"use strict";
// Vidéo refusée par le lecteur intégré (écran du Pi) : on propose de la lire sur la vraie page YouTube,
// dans une petite fenêtre par-dessus l'interface (pas un onglet). Ce n'est pas un titre de la file :
// à la fermeture, ou à la fin prévue du morceau, la liste reprend au titre suivant.

const POPUP_FEATURES = "popup,width=760,height=340,left=20,top=8";   // laisse le bandeau visible en bas de l’écran 800×480
const LOAD_MARGIN_S = 8;              // temps de chargement de la page avant le début du morceau
const CLOSE_WARNING_S = 15;           // « Fermeture dans 15 s » : on peut garder la fenêtre ouverte
const ANSWER_TIMEOUT_MS = 12000;      // sans réponse à la proposition : titre suivant

class YouTubeWindow {
  constructor() { this.win = null; this.veil = null; this.watch = null; this.endTimer = null; this.countdown = null; }

  open(song) {
    this.close(false);
    this.win = window.open("https://www.youtube.com/watch?v=" + encodeURIComponent(song.youtubeId), "pm-youtube", POPUP_FEATURES);
    if (!this.win) { toast("Fenêtre bloquée par le navigateur"); this.finish(); return; }
    this.showVeil(song);
    this.watch = setInterval(() => { if (!this.win || this.win.closed) this.finish(); }, 1000);
    if (song.duration > 0) this.endTimer = setTimeout(() => this.warnBeforeClosing(), (song.duration + LOAD_MARGIN_S) * 1000);
  }

  /* Fond assombri derrière la fenêtre, comme une pop-in */
  showVeil(song) {
    const veil = document.createElement("div"); veil.id = "ytveil";
    veil.innerHTML = '<div class="ytvbox"><b></b><span>Lecture sur YouTube. Votre liste reprendra à la fermeture.</span>'
      + '<em></em><div class="ytvbtns"><button type="button" class="keep" hidden>Garder ouverte</button>'
      + '<button type="button" class="close">Fermer YouTube</button></div></div>';
    veil.querySelector("b").textContent = song.title + (song.artist ? " · " + song.artist : "");
    veil.querySelector(".close").onclick = () => this.close(true);
    veil.querySelector(".keep").onclick = () => this.keepOpen();
    document.body.appendChild(veil);
    this.veil = veil;
  }

  warnBeforeClosing() {
    if (!this.veil) return;
    let left = CLOSE_WARNING_S;
    const note = this.veil.querySelector("em"), keep = this.veil.querySelector(".keep");
    keep.hidden = false;
    const paint = () => { note.textContent = "Fermeture de YouTube dans " + left + " s"; };
    paint();
    this.countdown = setInterval(() => { if (--left <= 0) this.close(true); else paint(); }, 1000);
  }

  keepOpen() {
    clearInterval(this.countdown); this.countdown = null;
    if (!this.veil) return;
    this.veil.querySelector("em").textContent = "";
    this.veil.querySelector(".keep").hidden = true;
  }

  close(resume) {
    clearInterval(this.watch); clearTimeout(this.endTimer); clearInterval(this.countdown);
    this.watch = this.endTimer = this.countdown = null;
    if (this.win && !this.win.closed) this.win.close();
    this.win = null;
    if (this.veil) { this.veil.remove(); this.veil = null; }
    if (resume) this.resumeList();
  }

  finish() { this.close(true); }

  resumeList() { if (qi + 1 < queue.length) playIdx(qi + 1); }
}

const youTubeWindow = new YouTubeWindow();

/* Appelée quand le lecteur intégré refuse une vidéo et qu'aucune autre version n'a été trouvée */
function offerYouTubeWindow(song, label) {
  let answered = false;
  openSheet(label + " — lecture impossible ici", [
    {icon: "play", label: "Lire sur YouTube (fenêtre)", fn: () => { answered = true; youTubeWindow.open(song); }},
    {icon: "next", label: qi + 1 < queue.length ? "Passer au titre suivant" : "Ne rien faire", fn: () => { answered = true; youTubeWindow.resumeList(); }}
  ]);
  setTimeout(() => {
    if (answered || cur() !== song) return;
    closeSheet();
    youTubeWindow.resumeList();                 // personne n'a répondu : la musique ne reste pas bloquée
  }, ANSWER_TIMEOUT_MS);
}
WEBEOF_45
cat > "$APP_DIR/web/static/vendor/qrcode-generator/VERSION" <<'WEBEOF_46'
qrcode-generator 2.0.4 (MIT, Kazuhiko Arase) — https://github.com/kazuhikoarase/qrcode-generator
Fichier copié tel quel depuis le paquet npm (dist/qrcode.js). La licence MIT figure en tête du fichier.
WEBEOF_46
cat > "$APP_DIR/web/static/vendor/qrcode-generator/qrcode.js" <<'WEBEOF_47'
//---------------------------------------------------------------------
//
// QR Code Generator for JavaScript
//
// Copyright (c) 2009 Kazuhiko Arase
//
// URL: http://www.d-project.com/
//
// Licensed under the MIT license:
//  http://www.opensource.org/licenses/mit-license.php
//
// The word 'QR Code' is registered trademark of
// DENSO WAVE INCORPORATED
//  http://www.denso-wave.com/qrcode/faqpatent-e.html
//
//---------------------------------------------------------------------

var qrcode = function() {

  //---------------------------------------------------------------------
  // qrcode
  //---------------------------------------------------------------------

  /**
   * qrcode
   * @param typeNumber 1 to 40
   * @param errorCorrectionLevel 'L','M','Q','H'
   */
  var qrcode = function(typeNumber, errorCorrectionLevel) {

    var PAD0 = 0xEC;
    var PAD1 = 0x11;

    var _typeNumber = typeNumber;
    var _errorCorrectionLevel = QRErrorCorrectionLevel[errorCorrectionLevel];
    var _modules = null;
    var _moduleCount = 0;
    var _dataCache = null;
    var _dataList = [];

    var _this = {};

    var makeImpl = function(test, maskPattern) {

      _moduleCount = _typeNumber * 4 + 17;
      _modules = function(moduleCount) {
        var modules = new Array(moduleCount);
        for (var row = 0; row < moduleCount; row += 1) {
          modules[row] = new Array(moduleCount);
          for (var col = 0; col < moduleCount; col += 1) {
            modules[row][col] = null;
          }
        }
        return modules;
      }(_moduleCount);

      setupPositionProbePattern(0, 0);
      setupPositionProbePattern(_moduleCount - 7, 0);
      setupPositionProbePattern(0, _moduleCount - 7);
      setupPositionAdjustPattern();
      setupTimingPattern();
      setupTypeInfo(test, maskPattern);

      if (_typeNumber >= 7) {
        setupTypeNumber(test);
      }

      if (_dataCache == null) {
        _dataCache = createData(_typeNumber, _errorCorrectionLevel, _dataList);
      }

      mapData(_dataCache, maskPattern);
    };

    var setupPositionProbePattern = function(row, col) {

      for (var r = -1; r <= 7; r += 1) {

        if (row + r <= -1 || _moduleCount <= row + r) continue;

        for (var c = -1; c <= 7; c += 1) {

          if (col + c <= -1 || _moduleCount <= col + c) continue;

          if ( (0 <= r && r <= 6 && (c == 0 || c == 6) )
              || (0 <= c && c <= 6 && (r == 0 || r == 6) )
              || (2 <= r && r <= 4 && 2 <= c && c <= 4) ) {
            _modules[row + r][col + c] = true;
          } else {
            _modules[row + r][col + c] = false;
          }
        }
      }
    };

    var getBestMaskPattern = function() {

      var minLostPoint = 0;
      var pattern = 0;

      for (var i = 0; i < 8; i += 1) {

        makeImpl(true, i);

        var lostPoint = QRUtil.getLostPoint(_this);

        if (i == 0 || minLostPoint > lostPoint) {
          minLostPoint = lostPoint;
          pattern = i;
        }
      }

      return pattern;
    };

    var setupTimingPattern = function() {

      for (var r = 8; r < _moduleCount - 8; r += 1) {
        if (_modules[r][6] != null) {
          continue;
        }
        _modules[r][6] = (r % 2 == 0);
      }

      for (var c = 8; c < _moduleCount - 8; c += 1) {
        if (_modules[6][c] != null) {
          continue;
        }
        _modules[6][c] = (c % 2 == 0);
      }
    };

    var setupPositionAdjustPattern = function() {

      var pos = QRUtil.getPatternPosition(_typeNumber);

      for (var i = 0; i < pos.length; i += 1) {

        for (var j = 0; j < pos.length; j += 1) {

          var row = pos[i];
          var col = pos[j];

          if (_modules[row][col] != null) {
            continue;
          }

          for (var r = -2; r <= 2; r += 1) {

            for (var c = -2; c <= 2; c += 1) {

              if (r == -2 || r == 2 || c == -2 || c == 2
                  || (r == 0 && c == 0) ) {
                _modules[row + r][col + c] = true;
              } else {
                _modules[row + r][col + c] = false;
              }
            }
          }
        }
      }
    };

    var setupTypeNumber = function(test) {

      var bits = QRUtil.getBCHTypeNumber(_typeNumber);

      for (var i = 0; i < 18; i += 1) {
        var mod = (!test && ( (bits >> i) & 1) == 1);
        _modules[Math.floor(i / 3)][i % 3 + _moduleCount - 8 - 3] = mod;
      }

      for (var i = 0; i < 18; i += 1) {
        var mod = (!test && ( (bits >> i) & 1) == 1);
        _modules[i % 3 + _moduleCount - 8 - 3][Math.floor(i / 3)] = mod;
      }
    };

    var setupTypeInfo = function(test, maskPattern) {

      var data = (_errorCorrectionLevel << 3) | maskPattern;
      var bits = QRUtil.getBCHTypeInfo(data);

      // vertical
      for (var i = 0; i < 15; i += 1) {

        var mod = (!test && ( (bits >> i) & 1) == 1);

        if (i < 6) {
          _modules[i][8] = mod;
        } else if (i < 8) {
          _modules[i + 1][8] = mod;
        } else {
          _modules[_moduleCount - 15 + i][8] = mod;
        }
      }

      // horizontal
      for (var i = 0; i < 15; i += 1) {

        var mod = (!test && ( (bits >> i) & 1) == 1);

        if (i < 8) {
          _modules[8][_moduleCount - i - 1] = mod;
        } else if (i < 9) {
          _modules[8][15 - i - 1 + 1] = mod;
        } else {
          _modules[8][15 - i - 1] = mod;
        }
      }

      // fixed module
      _modules[_moduleCount - 8][8] = (!test);
    };

    var mapData = function(data, maskPattern) {

      var inc = -1;
      var row = _moduleCount - 1;
      var bitIndex = 7;
      var byteIndex = 0;
      var maskFunc = QRUtil.getMaskFunction(maskPattern);

      for (var col = _moduleCount - 1; col > 0; col -= 2) {

        if (col == 6) col -= 1;

        while (true) {

          for (var c = 0; c < 2; c += 1) {

            if (_modules[row][col - c] == null) {

              var dark = false;

              if (byteIndex < data.length) {
                dark = ( ( (data[byteIndex] >>> bitIndex) & 1) == 1);
              }

              var mask = maskFunc(row, col - c);

              if (mask) {
                dark = !dark;
              }

              _modules[row][col - c] = dark;
              bitIndex -= 1;

              if (bitIndex == -1) {
                byteIndex += 1;
                bitIndex = 7;
              }
            }
          }

          row += inc;

          if (row < 0 || _moduleCount <= row) {
            row -= inc;
            inc = -inc;
            break;
          }
        }
      }
    };

    var createBytes = function(buffer, rsBlocks) {

      var offset = 0;

      var maxDcCount = 0;
      var maxEcCount = 0;

      var dcdata = new Array(rsBlocks.length);
      var ecdata = new Array(rsBlocks.length);

      for (var r = 0; r < rsBlocks.length; r += 1) {

        var dcCount = rsBlocks[r].dataCount;
        var ecCount = rsBlocks[r].totalCount - dcCount;

        maxDcCount = Math.max(maxDcCount, dcCount);
        maxEcCount = Math.max(maxEcCount, ecCount);

        dcdata[r] = new Array(dcCount);

        for (var i = 0; i < dcdata[r].length; i += 1) {
          dcdata[r][i] = 0xff & buffer.getBuffer()[i + offset];
        }
        offset += dcCount;

        var rsPoly = QRUtil.getErrorCorrectPolynomial(ecCount);
        var rawPoly = qrPolynomial(dcdata[r], rsPoly.getLength() - 1);

        var modPoly = rawPoly.mod(rsPoly);
        ecdata[r] = new Array(rsPoly.getLength() - 1);
        for (var i = 0; i < ecdata[r].length; i += 1) {
          var modIndex = i + modPoly.getLength() - ecdata[r].length;
          ecdata[r][i] = (modIndex >= 0)? modPoly.getAt(modIndex) : 0;
        }
      }

      var totalCodeCount = 0;
      for (var i = 0; i < rsBlocks.length; i += 1) {
        totalCodeCount += rsBlocks[i].totalCount;
      }

      var data = new Array(totalCodeCount);
      var index = 0;

      for (var i = 0; i < maxDcCount; i += 1) {
        for (var r = 0; r < rsBlocks.length; r += 1) {
          if (i < dcdata[r].length) {
            data[index] = dcdata[r][i];
            index += 1;
          }
        }
      }

      for (var i = 0; i < maxEcCount; i += 1) {
        for (var r = 0; r < rsBlocks.length; r += 1) {
          if (i < ecdata[r].length) {
            data[index] = ecdata[r][i];
            index += 1;
          }
        }
      }

      return data;
    };

    var createData = function(typeNumber, errorCorrectionLevel, dataList) {

      var rsBlocks = QRRSBlock.getRSBlocks(typeNumber, errorCorrectionLevel);

      var buffer = qrBitBuffer();

      for (var i = 0; i < dataList.length; i += 1) {
        var data = dataList[i];
        buffer.put(data.getMode(), 4);
        buffer.put(data.getLength(), QRUtil.getLengthInBits(data.getMode(), typeNumber) );
        data.write(buffer);
      }

      // calc num max data.
      var totalDataCount = 0;
      for (var i = 0; i < rsBlocks.length; i += 1) {
        totalDataCount += rsBlocks[i].dataCount;
      }

      if (buffer.getLengthInBits() > totalDataCount * 8) {
        throw 'code length overflow. ('
          + buffer.getLengthInBits()
          + '>'
          + totalDataCount * 8
          + ')';
      }

      // end code
      if (buffer.getLengthInBits() + 4 <= totalDataCount * 8) {
        buffer.put(0, 4);
      }

      // padding
      while (buffer.getLengthInBits() % 8 != 0) {
        buffer.putBit(false);
      }

      // padding
      while (true) {

        if (buffer.getLengthInBits() >= totalDataCount * 8) {
          break;
        }
        buffer.put(PAD0, 8);

        if (buffer.getLengthInBits() >= totalDataCount * 8) {
          break;
        }
        buffer.put(PAD1, 8);
      }

      return createBytes(buffer, rsBlocks);
    };

    _this.addData = function(data, mode) {

      mode = mode || 'Byte';

      var newData = null;

      switch(mode) {
      case 'Numeric' :
        newData = qrNumber(data);
        break;
      case 'Alphanumeric' :
        newData = qrAlphaNum(data);
        break;
      case 'Byte' :
        newData = qr8BitByte(data);
        break;
      case 'Kanji' :
        newData = qrKanji(data);
        break;
      default :
        throw 'mode:' + mode;
      }

      _dataList.push(newData);
      _dataCache = null;
    };

    _this.isDark = function(row, col) {
      if (row < 0 || _moduleCount <= row || col < 0 || _moduleCount <= col) {
        throw row + ',' + col;
      }
      return _modules[row][col];
    };

    _this.getModuleCount = function() {
      return _moduleCount;
    };

    _this.make = function() {
      if (_typeNumber < 1) {
        var typeNumber = 1;

        for (; typeNumber < 40; typeNumber++) {
          var rsBlocks = QRRSBlock.getRSBlocks(typeNumber, _errorCorrectionLevel);
          var buffer = qrBitBuffer();

          for (var i = 0; i < _dataList.length; i++) {
            var data = _dataList[i];
            buffer.put(data.getMode(), 4);
            buffer.put(data.getLength(), QRUtil.getLengthInBits(data.getMode(), typeNumber) );
            data.write(buffer);
          }

          var totalDataCount = 0;
          for (var i = 0; i < rsBlocks.length; i++) {
            totalDataCount += rsBlocks[i].dataCount;
          }

          if (buffer.getLengthInBits() <= totalDataCount * 8) {
            break;
          }
        }

        _typeNumber = typeNumber;
      }

      makeImpl(false, getBestMaskPattern() );
    };

    _this.createTableTag = function(cellSize, margin) {

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      var qrHtml = '';

      qrHtml += '<table style="';
      qrHtml += ' border-width: 0px; border-style: none;';
      qrHtml += ' border-collapse: collapse;';
      qrHtml += ' padding: 0px; margin: ' + margin + 'px;';
      qrHtml += '">';
      qrHtml += '<tbody>';

      for (var r = 0; r < _this.getModuleCount(); r += 1) {

        qrHtml += '<tr>';

        for (var c = 0; c < _this.getModuleCount(); c += 1) {
          qrHtml += '<td style="';
          qrHtml += ' border-width: 0px; border-style: none;';
          qrHtml += ' border-collapse: collapse;';
          qrHtml += ' padding: 0px; margin: 0px;';
          qrHtml += ' width: ' + cellSize + 'px;';
          qrHtml += ' height: ' + cellSize + 'px;';
          qrHtml += ' background-color: ';
          qrHtml += _this.isDark(r, c)? '#000000' : '#ffffff';
          qrHtml += ';';
          qrHtml += '"/>';
        }

        qrHtml += '</tr>';
      }

      qrHtml += '</tbody>';
      qrHtml += '</table>';

      return qrHtml;
    };

    _this.createSvgTag = function(cellSize, margin, alt, title) {

      var opts = {};
      if (typeof arguments[0] == 'object') {
        // Called by options.
        opts = arguments[0];
        // overwrite cellSize and margin.
        cellSize = opts.cellSize;
        margin = opts.margin;
        alt = opts.alt;
        title = opts.title;
      }

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      // Compose alt property surrogate
      alt = (typeof alt === 'string') ? {text: alt} : alt || {};
      alt.text = alt.text || null;
      alt.id = (alt.text) ? alt.id || 'qrcode-description' : null;

      // Compose title property surrogate
      title = (typeof title === 'string') ? {text: title} : title || {};
      title.text = title.text || null;
      title.id = (title.text) ? title.id || 'qrcode-title' : null;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var c, mc, r, mr, qrSvg='', rect;

      rect = 'l' + cellSize + ',0 0,' + cellSize +
        ' -' + cellSize + ',0 0,-' + cellSize + 'z ';

      qrSvg += '<svg version="1.1" xmlns="http://www.w3.org/2000/svg"';
      qrSvg += !opts.scalable ? ' width="' + size + 'px" height="' + size + 'px"' : '';
      qrSvg += ' viewBox="0 0 ' + size + ' ' + size + '" ';
      qrSvg += ' preserveAspectRatio="xMinYMin meet"';
      qrSvg += (title.text || alt.text) ? ' role="img" aria-labelledby="' +
          escapeXml([title.id, alt.id].join(' ').trim() ) + '"' : '';
      qrSvg += '>';
      qrSvg += (title.text) ? '<title id="' + escapeXml(title.id) + '">' +
          escapeXml(title.text) + '</title>' : '';
      qrSvg += (alt.text) ? '<description id="' + escapeXml(alt.id) + '">' +
          escapeXml(alt.text) + '</description>' : '';
      qrSvg += '<rect width="100%" height="100%" fill="white" cx="0" cy="0"/>';
      qrSvg += '<path d="';

      for (r = 0; r < _this.getModuleCount(); r += 1) {
        mr = r * cellSize + margin;
        for (c = 0; c < _this.getModuleCount(); c += 1) {
          if (_this.isDark(r, c) ) {
            mc = c*cellSize+margin;
            qrSvg += 'M' + mc + ',' + mr + rect;
          }
        }
      }

      qrSvg += '" stroke="transparent" fill="black"/>';
      qrSvg += '</svg>';

      return qrSvg;
    };

    _this.createDataURL = function(cellSize, margin) {

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var min = margin;
      var max = size - margin;

      return createDataURL(size, size, function(x, y) {
        if (min <= x && x < max && min <= y && y < max) {
          var c = Math.floor( (x - min) / cellSize);
          var r = Math.floor( (y - min) / cellSize);
          return _this.isDark(r, c)? 0 : 1;
        } else {
          return 1;
        }
      } );
    };

    _this.createImgTag = function(cellSize, margin, alt) {

      cellSize = cellSize || 2;
      margin = (typeof margin == 'undefined')? cellSize * 4 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;

      var img = '';
      img += '<img';
      img += '\u0020src="';
      img += _this.createDataURL(cellSize, margin);
      img += '"';
      img += '\u0020width="';
      img += size;
      img += '"';
      img += '\u0020height="';
      img += size;
      img += '"';
      if (alt) {
        img += '\u0020alt="';
        img += escapeXml(alt);
        img += '"';
      }
      img += '/>';

      return img;
    };

    var escapeXml = function(s) {
      var escaped = '';
      for (var i = 0; i < s.length; i += 1) {
        var c = s.charAt(i);
        switch(c) {
        case '<': escaped += '&lt;'; break;
        case '>': escaped += '&gt;'; break;
        case '&': escaped += '&amp;'; break;
        case '"': escaped += '&quot;'; break;
        default : escaped += c; break;
        }
      }
      return escaped;
    };

    var _createHalfASCII = function(margin) {
      var cellSize = 1;
      margin = (typeof margin == 'undefined')? cellSize * 2 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var min = margin;
      var max = size - margin;

      var y, x, r1, r2, p;

      var blocks = {
        '██': '█',
        '█ ': '▀',
        ' █': '▄',
        '  ': ' '
      };

      var blocksLastLineNoMargin = {
        '██': '▀',
        '█ ': '▀',
        ' █': ' ',
        '  ': ' '
      };

      var ascii = '';
      for (y = 0; y < size; y += 2) {
        r1 = Math.floor((y - min) / cellSize);
        r2 = Math.floor((y + 1 - min) / cellSize);
        for (x = 0; x < size; x += 1) {
          p = '█';

          if (min <= x && x < max && min <= y && y < max && _this.isDark(r1, Math.floor((x - min) / cellSize))) {
            p = ' ';
          }

          if (min <= x && x < max && min <= y+1 && y+1 < max && _this.isDark(r2, Math.floor((x - min) / cellSize))) {
            p += ' ';
          }
          else {
            p += '█';
          }

          // Output 2 characters per pixel, to create full square. 1 character per pixels gives only half width of square.
          ascii += (margin < 1 && y+1 >= max) ? blocksLastLineNoMargin[p] : blocks[p];
        }

        ascii += '\n';
      }

      if (size % 2 && margin > 0) {
        return ascii.substring(0, ascii.length - size - 1) + Array(size+1).join('▀');
      }

      return ascii.substring(0, ascii.length-1);
    };

    _this.createASCII = function(cellSize, margin) {
      cellSize = cellSize || 1;

      if (cellSize < 2) {
        return _createHalfASCII(margin);
      }

      cellSize -= 1;
      margin = (typeof margin == 'undefined')? cellSize * 2 : margin;

      var size = _this.getModuleCount() * cellSize + margin * 2;
      var min = margin;
      var max = size - margin;

      var y, x, r, p;

      var white = Array(cellSize+1).join('██');
      var black = Array(cellSize+1).join('  ');

      var ascii = '';
      var line = '';
      for (y = 0; y < size; y += 1) {
        r = Math.floor( (y - min) / cellSize);
        line = '';
        for (x = 0; x < size; x += 1) {
          p = 1;

          if (min <= x && x < max && min <= y && y < max && _this.isDark(r, Math.floor((x - min) / cellSize))) {
            p = 0;
          }

          // Output 2 characters per pixel, to create full square. 1 character per pixels gives only half width of square.
          line += p ? white : black;
        }

        for (r = 0; r < cellSize; r += 1) {
          ascii += line + '\n';
        }
      }

      return ascii.substring(0, ascii.length-1);
    };

    _this.renderTo2dContext = function(context, cellSize) {
      cellSize = cellSize || 2;
      var length = _this.getModuleCount();
      for (var row = 0; row < length; row++) {
        for (var col = 0; col < length; col++) {
          context.fillStyle = _this.isDark(row, col) ? 'black' : 'white';
          context.fillRect(col * cellSize, row * cellSize, cellSize, cellSize);
        }
      }
    }

    return _this;
  };

  //---------------------------------------------------------------------
  // qrcode.stringToBytes
  //---------------------------------------------------------------------

  qrcode.stringToBytesFuncs = {
    'default' : function(s) {
      var bytes = [];
      for (var i = 0; i < s.length; i += 1) {
        var c = s.charCodeAt(i);
        bytes.push(c & 0xff);
      }
      return bytes;
    }
  };

  qrcode.stringToBytes = qrcode.stringToBytesFuncs['default'];

  //---------------------------------------------------------------------
  // qrcode.createStringToBytes
  //---------------------------------------------------------------------

  /**
   * @param unicodeData base64 string of byte array.
   * [16bit Unicode],[16bit Bytes], ...
   * @param numChars
   */
  qrcode.createStringToBytes = function(unicodeData, numChars) {

    // create conversion map.

    var unicodeMap = function() {

      var bin = base64DecodeInputStream(unicodeData);
      var read = function() {
        var b = bin.read();
        if (b == -1) throw 'eof';
        return b;
      };

      var count = 0;
      var unicodeMap = {};
      while (true) {
        var b0 = bin.read();
        if (b0 == -1) break;
        var b1 = read();
        var b2 = read();
        var b3 = read();
        var k = String.fromCharCode( (b0 << 8) | b1);
        var v = (b2 << 8) | b3;
        unicodeMap[k] = v;
        count += 1;
      }
      if (count != numChars) {
        throw count + ' != ' + numChars;
      }

      return unicodeMap;
    }();

    var unknownChar = '?'.charCodeAt(0);

    return function(s) {
      var bytes = [];
      for (var i = 0; i < s.length; i += 1) {
        var c = s.charCodeAt(i);
        if (c < 128) {
          bytes.push(c);
        } else {
          var b = unicodeMap[s.charAt(i)];
          if (typeof b == 'number') {
            if ( (b & 0xff) == b) {
              // 1byte
              bytes.push(b);
            } else {
              // 2bytes
              bytes.push(b >>> 8);
              bytes.push(b & 0xff);
            }
          } else {
            bytes.push(unknownChar);
          }
        }
      }
      return bytes;
    };
  };

  //---------------------------------------------------------------------
  // QRMode
  //---------------------------------------------------------------------

  var QRMode = {
    MODE_NUMBER :    1 << 0,
    MODE_ALPHA_NUM : 1 << 1,
    MODE_8BIT_BYTE : 1 << 2,
    MODE_KANJI :     1 << 3
  };

  //---------------------------------------------------------------------
  // QRErrorCorrectionLevel
  //---------------------------------------------------------------------

  var QRErrorCorrectionLevel = {
    L : 1,
    M : 0,
    Q : 3,
    H : 2
  };

  //---------------------------------------------------------------------
  // QRMaskPattern
  //---------------------------------------------------------------------

  var QRMaskPattern = {
    PATTERN000 : 0,
    PATTERN001 : 1,
    PATTERN010 : 2,
    PATTERN011 : 3,
    PATTERN100 : 4,
    PATTERN101 : 5,
    PATTERN110 : 6,
    PATTERN111 : 7
  };

  //---------------------------------------------------------------------
  // QRUtil
  //---------------------------------------------------------------------

  var QRUtil = function() {

    var PATTERN_POSITION_TABLE = [
      [],
      [6, 18],
      [6, 22],
      [6, 26],
      [6, 30],
      [6, 34],
      [6, 22, 38],
      [6, 24, 42],
      [6, 26, 46],
      [6, 28, 50],
      [6, 30, 54],
      [6, 32, 58],
      [6, 34, 62],
      [6, 26, 46, 66],
      [6, 26, 48, 70],
      [6, 26, 50, 74],
      [6, 30, 54, 78],
      [6, 30, 56, 82],
      [6, 30, 58, 86],
      [6, 34, 62, 90],
      [6, 28, 50, 72, 94],
      [6, 26, 50, 74, 98],
      [6, 30, 54, 78, 102],
      [6, 28, 54, 80, 106],
      [6, 32, 58, 84, 110],
      [6, 30, 58, 86, 114],
      [6, 34, 62, 90, 118],
      [6, 26, 50, 74, 98, 122],
      [6, 30, 54, 78, 102, 126],
      [6, 26, 52, 78, 104, 130],
      [6, 30, 56, 82, 108, 134],
      [6, 34, 60, 86, 112, 138],
      [6, 30, 58, 86, 114, 142],
      [6, 34, 62, 90, 118, 146],
      [6, 30, 54, 78, 102, 126, 150],
      [6, 24, 50, 76, 102, 128, 154],
      [6, 28, 54, 80, 106, 132, 158],
      [6, 32, 58, 84, 110, 136, 162],
      [6, 26, 54, 82, 110, 138, 166],
      [6, 30, 58, 86, 114, 142, 170]
    ];
    var G15 = (1 << 10) | (1 << 8) | (1 << 5) | (1 << 4) | (1 << 2) | (1 << 1) | (1 << 0);
    var G18 = (1 << 12) | (1 << 11) | (1 << 10) | (1 << 9) | (1 << 8) | (1 << 5) | (1 << 2) | (1 << 0);
    var G15_MASK = (1 << 14) | (1 << 12) | (1 << 10) | (1 << 4) | (1 << 1);

    var _this = {};

    var getBCHDigit = function(data) {
      var digit = 0;
      while (data != 0) {
        digit += 1;
        data >>>= 1;
      }
      return digit;
    };

    _this.getBCHTypeInfo = function(data) {
      var d = data << 10;
      while (getBCHDigit(d) - getBCHDigit(G15) >= 0) {
        d ^= (G15 << (getBCHDigit(d) - getBCHDigit(G15) ) );
      }
      return ( (data << 10) | d) ^ G15_MASK;
    };

    _this.getBCHTypeNumber = function(data) {
      var d = data << 12;
      while (getBCHDigit(d) - getBCHDigit(G18) >= 0) {
        d ^= (G18 << (getBCHDigit(d) - getBCHDigit(G18) ) );
      }
      return (data << 12) | d;
    };

    _this.getPatternPosition = function(typeNumber) {
      return PATTERN_POSITION_TABLE[typeNumber - 1];
    };

    _this.getMaskFunction = function(maskPattern) {

      switch (maskPattern) {

      case QRMaskPattern.PATTERN000 :
        return function(i, j) { return (i + j) % 2 == 0; };
      case QRMaskPattern.PATTERN001 :
        return function(i, j) { return i % 2 == 0; };
      case QRMaskPattern.PATTERN010 :
        return function(i, j) { return j % 3 == 0; };
      case QRMaskPattern.PATTERN011 :
        return function(i, j) { return (i + j) % 3 == 0; };
      case QRMaskPattern.PATTERN100 :
        return function(i, j) { return (Math.floor(i / 2) + Math.floor(j / 3) ) % 2 == 0; };
      case QRMaskPattern.PATTERN101 :
        return function(i, j) { return (i * j) % 2 + (i * j) % 3 == 0; };
      case QRMaskPattern.PATTERN110 :
        return function(i, j) { return ( (i * j) % 2 + (i * j) % 3) % 2 == 0; };
      case QRMaskPattern.PATTERN111 :
        return function(i, j) { return ( (i * j) % 3 + (i + j) % 2) % 2 == 0; };

      default :
        throw 'bad maskPattern:' + maskPattern;
      }
    };

    _this.getErrorCorrectPolynomial = function(errorCorrectLength) {
      var a = qrPolynomial([1], 0);
      for (var i = 0; i < errorCorrectLength; i += 1) {
        a = a.multiply(qrPolynomial([1, QRMath.gexp(i)], 0) );
      }
      return a;
    };

    _this.getLengthInBits = function(mode, type) {

      if (1 <= type && type < 10) {

        // 1 - 9

        switch(mode) {
        case QRMode.MODE_NUMBER    : return 10;
        case QRMode.MODE_ALPHA_NUM : return 9;
        case QRMode.MODE_8BIT_BYTE : return 8;
        case QRMode.MODE_KANJI     : return 8;
        default :
          throw 'mode:' + mode;
        }

      } else if (type < 27) {

        // 10 - 26

        switch(mode) {
        case QRMode.MODE_NUMBER    : return 12;
        case QRMode.MODE_ALPHA_NUM : return 11;
        case QRMode.MODE_8BIT_BYTE : return 16;
        case QRMode.MODE_KANJI     : return 10;
        default :
          throw 'mode:' + mode;
        }

      } else if (type < 41) {

        // 27 - 40

        switch(mode) {
        case QRMode.MODE_NUMBER    : return 14;
        case QRMode.MODE_ALPHA_NUM : return 13;
        case QRMode.MODE_8BIT_BYTE : return 16;
        case QRMode.MODE_KANJI     : return 12;
        default :
          throw 'mode:' + mode;
        }

      } else {
        throw 'type:' + type;
      }
    };

    _this.getLostPoint = function(qrcode) {

      var moduleCount = qrcode.getModuleCount();

      var lostPoint = 0;

      // LEVEL1

      for (var row = 0; row < moduleCount; row += 1) {
        for (var col = 0; col < moduleCount; col += 1) {

          var sameCount = 0;
          var dark = qrcode.isDark(row, col);

          for (var r = -1; r <= 1; r += 1) {

            if (row + r < 0 || moduleCount <= row + r) {
              continue;
            }

            for (var c = -1; c <= 1; c += 1) {

              if (col + c < 0 || moduleCount <= col + c) {
                continue;
              }

              if (r == 0 && c == 0) {
                continue;
              }

              if (dark == qrcode.isDark(row + r, col + c) ) {
                sameCount += 1;
              }
            }
          }

          if (sameCount > 5) {
            lostPoint += (3 + sameCount - 5);
          }
        }
      };

      // LEVEL2

      for (var row = 0; row < moduleCount - 1; row += 1) {
        for (var col = 0; col < moduleCount - 1; col += 1) {
          var count = 0;
          if (qrcode.isDark(row, col) ) count += 1;
          if (qrcode.isDark(row + 1, col) ) count += 1;
          if (qrcode.isDark(row, col + 1) ) count += 1;
          if (qrcode.isDark(row + 1, col + 1) ) count += 1;
          if (count == 0 || count == 4) {
            lostPoint += 3;
          }
        }
      }

      // LEVEL3

      for (var row = 0; row < moduleCount; row += 1) {
        for (var col = 0; col < moduleCount - 6; col += 1) {
          if (qrcode.isDark(row, col)
              && !qrcode.isDark(row, col + 1)
              &&  qrcode.isDark(row, col + 2)
              &&  qrcode.isDark(row, col + 3)
              &&  qrcode.isDark(row, col + 4)
              && !qrcode.isDark(row, col + 5)
              &&  qrcode.isDark(row, col + 6) ) {
            lostPoint += 40;
          }
        }
      }

      for (var col = 0; col < moduleCount; col += 1) {
        for (var row = 0; row < moduleCount - 6; row += 1) {
          if (qrcode.isDark(row, col)
              && !qrcode.isDark(row + 1, col)
              &&  qrcode.isDark(row + 2, col)
              &&  qrcode.isDark(row + 3, col)
              &&  qrcode.isDark(row + 4, col)
              && !qrcode.isDark(row + 5, col)
              &&  qrcode.isDark(row + 6, col) ) {
            lostPoint += 40;
          }
        }
      }

      // LEVEL4

      var darkCount = 0;

      for (var col = 0; col < moduleCount; col += 1) {
        for (var row = 0; row < moduleCount; row += 1) {
          if (qrcode.isDark(row, col) ) {
            darkCount += 1;
          }
        }
      }

      var ratio = Math.abs(100 * darkCount / moduleCount / moduleCount - 50) / 5;
      lostPoint += ratio * 10;

      return lostPoint;
    };

    return _this;
  }();

  //---------------------------------------------------------------------
  // QRMath
  //---------------------------------------------------------------------

  var QRMath = function() {

    var EXP_TABLE = new Array(256);
    var LOG_TABLE = new Array(256);

    // initialize tables
    for (var i = 0; i < 8; i += 1) {
      EXP_TABLE[i] = 1 << i;
    }
    for (var i = 8; i < 256; i += 1) {
      EXP_TABLE[i] = EXP_TABLE[i - 4]
        ^ EXP_TABLE[i - 5]
        ^ EXP_TABLE[i - 6]
        ^ EXP_TABLE[i - 8];
    }
    for (var i = 0; i < 255; i += 1) {
      LOG_TABLE[EXP_TABLE[i] ] = i;
    }

    var _this = {};

    _this.glog = function(n) {

      if (n < 1) {
        throw 'glog(' + n + ')';
      }

      return LOG_TABLE[n];
    };

    _this.gexp = function(n) {

      while (n < 0) {
        n += 255;
      }

      while (n >= 256) {
        n -= 255;
      }

      return EXP_TABLE[n];
    };

    return _this;
  }();

  //---------------------------------------------------------------------
  // qrPolynomial
  //---------------------------------------------------------------------

  function qrPolynomial(num, shift) {

    if (typeof num.length == 'undefined') {
      throw num.length + '/' + shift;
    }

    var _num = function() {
      var offset = 0;
      while (offset < num.length && num[offset] == 0) {
        offset += 1;
      }
      var _num = new Array(num.length - offset + shift);
      for (var i = 0; i < num.length - offset; i += 1) {
        _num[i] = num[i + offset];
      }
      return _num;
    }();

    var _this = {};

    _this.getAt = function(index) {
      return _num[index];
    };

    _this.getLength = function() {
      return _num.length;
    };

    _this.multiply = function(e) {

      var num = new Array(_this.getLength() + e.getLength() - 1);

      for (var i = 0; i < _this.getLength(); i += 1) {
        for (var j = 0; j < e.getLength(); j += 1) {
          num[i + j] ^= QRMath.gexp(QRMath.glog(_this.getAt(i) ) + QRMath.glog(e.getAt(j) ) );
        }
      }

      return qrPolynomial(num, 0);
    };

    _this.mod = function(e) {

      if (_this.getLength() - e.getLength() < 0) {
        return _this;
      }

      var ratio = QRMath.glog(_this.getAt(0) ) - QRMath.glog(e.getAt(0) );

      var num = new Array(_this.getLength() );
      for (var i = 0; i < _this.getLength(); i += 1) {
        num[i] = _this.getAt(i);
      }

      for (var i = 0; i < e.getLength(); i += 1) {
        num[i] ^= QRMath.gexp(QRMath.glog(e.getAt(i) ) + ratio);
      }

      // recursive call
      return qrPolynomial(num, 0).mod(e);
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // QRRSBlock
  //---------------------------------------------------------------------

  var QRRSBlock = function() {

    var RS_BLOCK_TABLE = [

      // L
      // M
      // Q
      // H

      // 1
      [1, 26, 19],
      [1, 26, 16],
      [1, 26, 13],
      [1, 26, 9],

      // 2
      [1, 44, 34],
      [1, 44, 28],
      [1, 44, 22],
      [1, 44, 16],

      // 3
      [1, 70, 55],
      [1, 70, 44],
      [2, 35, 17],
      [2, 35, 13],

      // 4
      [1, 100, 80],
      [2, 50, 32],
      [2, 50, 24],
      [4, 25, 9],

      // 5
      [1, 134, 108],
      [2, 67, 43],
      [2, 33, 15, 2, 34, 16],
      [2, 33, 11, 2, 34, 12],

      // 6
      [2, 86, 68],
      [4, 43, 27],
      [4, 43, 19],
      [4, 43, 15],

      // 7
      [2, 98, 78],
      [4, 49, 31],
      [2, 32, 14, 4, 33, 15],
      [4, 39, 13, 1, 40, 14],

      // 8
      [2, 121, 97],
      [2, 60, 38, 2, 61, 39],
      [4, 40, 18, 2, 41, 19],
      [4, 40, 14, 2, 41, 15],

      // 9
      [2, 146, 116],
      [3, 58, 36, 2, 59, 37],
      [4, 36, 16, 4, 37, 17],
      [4, 36, 12, 4, 37, 13],

      // 10
      [2, 86, 68, 2, 87, 69],
      [4, 69, 43, 1, 70, 44],
      [6, 43, 19, 2, 44, 20],
      [6, 43, 15, 2, 44, 16],

      // 11
      [4, 101, 81],
      [1, 80, 50, 4, 81, 51],
      [4, 50, 22, 4, 51, 23],
      [3, 36, 12, 8, 37, 13],

      // 12
      [2, 116, 92, 2, 117, 93],
      [6, 58, 36, 2, 59, 37],
      [4, 46, 20, 6, 47, 21],
      [7, 42, 14, 4, 43, 15],

      // 13
      [4, 133, 107],
      [8, 59, 37, 1, 60, 38],
      [8, 44, 20, 4, 45, 21],
      [12, 33, 11, 4, 34, 12],

      // 14
      [3, 145, 115, 1, 146, 116],
      [4, 64, 40, 5, 65, 41],
      [11, 36, 16, 5, 37, 17],
      [11, 36, 12, 5, 37, 13],

      // 15
      [5, 109, 87, 1, 110, 88],
      [5, 65, 41, 5, 66, 42],
      [5, 54, 24, 7, 55, 25],
      [11, 36, 12, 7, 37, 13],

      // 16
      [5, 122, 98, 1, 123, 99],
      [7, 73, 45, 3, 74, 46],
      [15, 43, 19, 2, 44, 20],
      [3, 45, 15, 13, 46, 16],

      // 17
      [1, 135, 107, 5, 136, 108],
      [10, 74, 46, 1, 75, 47],
      [1, 50, 22, 15, 51, 23],
      [2, 42, 14, 17, 43, 15],

      // 18
      [5, 150, 120, 1, 151, 121],
      [9, 69, 43, 4, 70, 44],
      [17, 50, 22, 1, 51, 23],
      [2, 42, 14, 19, 43, 15],

      // 19
      [3, 141, 113, 4, 142, 114],
      [3, 70, 44, 11, 71, 45],
      [17, 47, 21, 4, 48, 22],
      [9, 39, 13, 16, 40, 14],

      // 20
      [3, 135, 107, 5, 136, 108],
      [3, 67, 41, 13, 68, 42],
      [15, 54, 24, 5, 55, 25],
      [15, 43, 15, 10, 44, 16],

      // 21
      [4, 144, 116, 4, 145, 117],
      [17, 68, 42],
      [17, 50, 22, 6, 51, 23],
      [19, 46, 16, 6, 47, 17],

      // 22
      [2, 139, 111, 7, 140, 112],
      [17, 74, 46],
      [7, 54, 24, 16, 55, 25],
      [34, 37, 13],

      // 23
      [4, 151, 121, 5, 152, 122],
      [4, 75, 47, 14, 76, 48],
      [11, 54, 24, 14, 55, 25],
      [16, 45, 15, 14, 46, 16],

      // 24
      [6, 147, 117, 4, 148, 118],
      [6, 73, 45, 14, 74, 46],
      [11, 54, 24, 16, 55, 25],
      [30, 46, 16, 2, 47, 17],

      // 25
      [8, 132, 106, 4, 133, 107],
      [8, 75, 47, 13, 76, 48],
      [7, 54, 24, 22, 55, 25],
      [22, 45, 15, 13, 46, 16],

      // 26
      [10, 142, 114, 2, 143, 115],
      [19, 74, 46, 4, 75, 47],
      [28, 50, 22, 6, 51, 23],
      [33, 46, 16, 4, 47, 17],

      // 27
      [8, 152, 122, 4, 153, 123],
      [22, 73, 45, 3, 74, 46],
      [8, 53, 23, 26, 54, 24],
      [12, 45, 15, 28, 46, 16],

      // 28
      [3, 147, 117, 10, 148, 118],
      [3, 73, 45, 23, 74, 46],
      [4, 54, 24, 31, 55, 25],
      [11, 45, 15, 31, 46, 16],

      // 29
      [7, 146, 116, 7, 147, 117],
      [21, 73, 45, 7, 74, 46],
      [1, 53, 23, 37, 54, 24],
      [19, 45, 15, 26, 46, 16],

      // 30
      [5, 145, 115, 10, 146, 116],
      [19, 75, 47, 10, 76, 48],
      [15, 54, 24, 25, 55, 25],
      [23, 45, 15, 25, 46, 16],

      // 31
      [13, 145, 115, 3, 146, 116],
      [2, 74, 46, 29, 75, 47],
      [42, 54, 24, 1, 55, 25],
      [23, 45, 15, 28, 46, 16],

      // 32
      [17, 145, 115],
      [10, 74, 46, 23, 75, 47],
      [10, 54, 24, 35, 55, 25],
      [19, 45, 15, 35, 46, 16],

      // 33
      [17, 145, 115, 1, 146, 116],
      [14, 74, 46, 21, 75, 47],
      [29, 54, 24, 19, 55, 25],
      [11, 45, 15, 46, 46, 16],

      // 34
      [13, 145, 115, 6, 146, 116],
      [14, 74, 46, 23, 75, 47],
      [44, 54, 24, 7, 55, 25],
      [59, 46, 16, 1, 47, 17],

      // 35
      [12, 151, 121, 7, 152, 122],
      [12, 75, 47, 26, 76, 48],
      [39, 54, 24, 14, 55, 25],
      [22, 45, 15, 41, 46, 16],

      // 36
      [6, 151, 121, 14, 152, 122],
      [6, 75, 47, 34, 76, 48],
      [46, 54, 24, 10, 55, 25],
      [2, 45, 15, 64, 46, 16],

      // 37
      [17, 152, 122, 4, 153, 123],
      [29, 74, 46, 14, 75, 47],
      [49, 54, 24, 10, 55, 25],
      [24, 45, 15, 46, 46, 16],

      // 38
      [4, 152, 122, 18, 153, 123],
      [13, 74, 46, 32, 75, 47],
      [48, 54, 24, 14, 55, 25],
      [42, 45, 15, 32, 46, 16],

      // 39
      [20, 147, 117, 4, 148, 118],
      [40, 75, 47, 7, 76, 48],
      [43, 54, 24, 22, 55, 25],
      [10, 45, 15, 67, 46, 16],

      // 40
      [19, 148, 118, 6, 149, 119],
      [18, 75, 47, 31, 76, 48],
      [34, 54, 24, 34, 55, 25],
      [20, 45, 15, 61, 46, 16]
    ];

    var qrRSBlock = function(totalCount, dataCount) {
      var _this = {};
      _this.totalCount = totalCount;
      _this.dataCount = dataCount;
      return _this;
    };

    var _this = {};

    var getRsBlockTable = function(typeNumber, errorCorrectionLevel) {

      switch(errorCorrectionLevel) {
      case QRErrorCorrectionLevel.L :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 0];
      case QRErrorCorrectionLevel.M :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 1];
      case QRErrorCorrectionLevel.Q :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 2];
      case QRErrorCorrectionLevel.H :
        return RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 3];
      default :
        return undefined;
      }
    };

    _this.getRSBlocks = function(typeNumber, errorCorrectionLevel) {

      var rsBlock = getRsBlockTable(typeNumber, errorCorrectionLevel);

      if (typeof rsBlock == 'undefined') {
        throw 'bad rs block @ typeNumber:' + typeNumber +
            '/errorCorrectionLevel:' + errorCorrectionLevel;
      }

      var length = rsBlock.length / 3;

      var list = [];

      for (var i = 0; i < length; i += 1) {

        var count = rsBlock[i * 3 + 0];
        var totalCount = rsBlock[i * 3 + 1];
        var dataCount = rsBlock[i * 3 + 2];

        for (var j = 0; j < count; j += 1) {
          list.push(qrRSBlock(totalCount, dataCount) );
        }
      }

      return list;
    };

    return _this;
  }();

  //---------------------------------------------------------------------
  // qrBitBuffer
  //---------------------------------------------------------------------

  var qrBitBuffer = function() {

    var _buffer = [];
    var _length = 0;

    var _this = {};

    _this.getBuffer = function() {
      return _buffer;
    };

    _this.getAt = function(index) {
      var bufIndex = Math.floor(index / 8);
      return ( (_buffer[bufIndex] >>> (7 - index % 8) ) & 1) == 1;
    };

    _this.put = function(num, length) {
      for (var i = 0; i < length; i += 1) {
        _this.putBit( ( (num >>> (length - i - 1) ) & 1) == 1);
      }
    };

    _this.getLengthInBits = function() {
      return _length;
    };

    _this.putBit = function(bit) {

      var bufIndex = Math.floor(_length / 8);
      if (_buffer.length <= bufIndex) {
        _buffer.push(0);
      }

      if (bit) {
        _buffer[bufIndex] |= (0x80 >>> (_length % 8) );
      }

      _length += 1;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qrNumber
  //---------------------------------------------------------------------

  var qrNumber = function(data) {

    var _mode = QRMode.MODE_NUMBER;
    var _data = data;

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return _data.length;
    };

    _this.write = function(buffer) {

      var data = _data;

      var i = 0;

      while (i + 2 < data.length) {
        buffer.put(strToNum(data.substring(i, i + 3) ), 10);
        i += 3;
      }

      if (i < data.length) {
        if (data.length - i == 1) {
          buffer.put(strToNum(data.substring(i, i + 1) ), 4);
        } else if (data.length - i == 2) {
          buffer.put(strToNum(data.substring(i, i + 2) ), 7);
        }
      }
    };

    var strToNum = function(s) {
      var num = 0;
      for (var i = 0; i < s.length; i += 1) {
        num = num * 10 + chatToNum(s.charAt(i) );
      }
      return num;
    };

    var chatToNum = function(c) {
      if ('0' <= c && c <= '9') {
        return c.charCodeAt(0) - '0'.charCodeAt(0);
      }
      throw 'illegal char :' + c;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qrAlphaNum
  //---------------------------------------------------------------------

  var qrAlphaNum = function(data) {

    var _mode = QRMode.MODE_ALPHA_NUM;
    var _data = data;

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return _data.length;
    };

    _this.write = function(buffer) {

      var s = _data;

      var i = 0;

      while (i + 1 < s.length) {
        buffer.put(
          getCode(s.charAt(i) ) * 45 +
          getCode(s.charAt(i + 1) ), 11);
        i += 2;
      }

      if (i < s.length) {
        buffer.put(getCode(s.charAt(i) ), 6);
      }
    };

    var getCode = function(c) {

      if ('0' <= c && c <= '9') {
        return c.charCodeAt(0) - '0'.charCodeAt(0);
      } else if ('A' <= c && c <= 'Z') {
        return c.charCodeAt(0) - 'A'.charCodeAt(0) + 10;
      } else {
        switch (c) {
        case ' ' : return 36;
        case '$' : return 37;
        case '%' : return 38;
        case '*' : return 39;
        case '+' : return 40;
        case '-' : return 41;
        case '.' : return 42;
        case '/' : return 43;
        case ':' : return 44;
        default :
          throw 'illegal char :' + c;
        }
      }
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qr8BitByte
  //---------------------------------------------------------------------

  var qr8BitByte = function(data) {

    var _mode = QRMode.MODE_8BIT_BYTE;
    var _data = data;
    var _bytes = qrcode.stringToBytes(data);

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return _bytes.length;
    };

    _this.write = function(buffer) {
      for (var i = 0; i < _bytes.length; i += 1) {
        buffer.put(_bytes[i], 8);
      }
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // qrKanji
  //---------------------------------------------------------------------

  var qrKanji = function(data) {

    var _mode = QRMode.MODE_KANJI;
    var _data = data;

    var stringToBytes = qrcode.stringToBytesFuncs['SJIS'];
    if (!stringToBytes) {
      throw 'sjis not supported.';
    }
    !function(c, code) {
      // self test for sjis support.
      var test = stringToBytes(c);
      if (test.length != 2 || ( (test[0] << 8) | test[1]) != code) {
        throw 'sjis not supported.';
      }
    }('\u53cb', 0x9746);

    var _bytes = stringToBytes(data);

    var _this = {};

    _this.getMode = function() {
      return _mode;
    };

    _this.getLength = function(buffer) {
      return ~~(_bytes.length / 2);
    };

    _this.write = function(buffer) {

      var data = _bytes;

      var i = 0;

      while (i + 1 < data.length) {

        var c = ( (0xff & data[i]) << 8) | (0xff & data[i + 1]);

        if (0x8140 <= c && c <= 0x9FFC) {
          c -= 0x8140;
        } else if (0xE040 <= c && c <= 0xEBBF) {
          c -= 0xC140;
        } else {
          throw 'illegal char at ' + (i + 1) + '/' + c;
        }

        c = ( (c >>> 8) & 0xff) * 0xC0 + (c & 0xff);

        buffer.put(c, 13);

        i += 2;
      }

      if (i < data.length) {
        throw 'illegal char at ' + (i + 1);
      }
    };

    return _this;
  };

  //=====================================================================
  // GIF Support etc.
  //

  //---------------------------------------------------------------------
  // byteArrayOutputStream
  //---------------------------------------------------------------------

  var byteArrayOutputStream = function() {

    var _bytes = [];

    var _this = {};

    _this.writeByte = function(b) {
      _bytes.push(b & 0xff);
    };

    _this.writeShort = function(i) {
      _this.writeByte(i);
      _this.writeByte(i >>> 8);
    };

    _this.writeBytes = function(b, off, len) {
      off = off || 0;
      len = len || b.length;
      for (var i = 0; i < len; i += 1) {
        _this.writeByte(b[i + off]);
      }
    };

    _this.writeString = function(s) {
      for (var i = 0; i < s.length; i += 1) {
        _this.writeByte(s.charCodeAt(i) );
      }
    };

    _this.toByteArray = function() {
      return _bytes;
    };

    _this.toString = function() {
      var s = '';
      s += '[';
      for (var i = 0; i < _bytes.length; i += 1) {
        if (i > 0) {
          s += ',';
        }
        s += _bytes[i];
      }
      s += ']';
      return s;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // base64EncodeOutputStream
  //---------------------------------------------------------------------

  var base64EncodeOutputStream = function() {

    var _buffer = 0;
    var _buflen = 0;
    var _length = 0;
    var _base64 = '';

    var _this = {};

    var writeEncoded = function(b) {
      _base64 += String.fromCharCode(encode(b & 0x3f) );
    };

    var encode = function(n) {
      if (n < 0) {
        // error.
      } else if (n < 26) {
        return 0x41 + n;
      } else if (n < 52) {
        return 0x61 + (n - 26);
      } else if (n < 62) {
        return 0x30 + (n - 52);
      } else if (n == 62) {
        return 0x2b;
      } else if (n == 63) {
        return 0x2f;
      }
      throw 'n:' + n;
    };

    _this.writeByte = function(n) {

      _buffer = (_buffer << 8) | (n & 0xff);
      _buflen += 8;
      _length += 1;

      while (_buflen >= 6) {
        writeEncoded(_buffer >>> (_buflen - 6) );
        _buflen -= 6;
      }
    };

    _this.flush = function() {

      if (_buflen > 0) {
        writeEncoded(_buffer << (6 - _buflen) );
        _buffer = 0;
        _buflen = 0;
      }

      if (_length % 3 != 0) {
        // padding
        var padlen = 3 - _length % 3;
        for (var i = 0; i < padlen; i += 1) {
          _base64 += '=';
        }
      }
    };

    _this.toString = function() {
      return _base64;
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // base64DecodeInputStream
  //---------------------------------------------------------------------

  var base64DecodeInputStream = function(str) {

    var _str = str;
    var _pos = 0;
    var _buffer = 0;
    var _buflen = 0;

    var _this = {};

    _this.read = function() {

      while (_buflen < 8) {

        if (_pos >= _str.length) {
          if (_buflen == 0) {
            return -1;
          }
          throw 'unexpected end of file./' + _buflen;
        }

        var c = _str.charAt(_pos);
        _pos += 1;

        if (c == '=') {
          _buflen = 0;
          return -1;
        } else if (c.match(/^\s$/) ) {
          // ignore if whitespace.
          continue;
        }

        _buffer = (_buffer << 6) | decode(c.charCodeAt(0) );
        _buflen += 6;
      }

      var n = (_buffer >>> (_buflen - 8) ) & 0xff;
      _buflen -= 8;
      return n;
    };

    var decode = function(c) {
      if (0x41 <= c && c <= 0x5a) {
        return c - 0x41;
      } else if (0x61 <= c && c <= 0x7a) {
        return c - 0x61 + 26;
      } else if (0x30 <= c && c <= 0x39) {
        return c - 0x30 + 52;
      } else if (c == 0x2b) {
        return 62;
      } else if (c == 0x2f) {
        return 63;
      } else {
        throw 'c:' + c;
      }
    };

    return _this;
  };

  //---------------------------------------------------------------------
  // gifImage (B/W)
  //---------------------------------------------------------------------

  var gifImage = function(width, height) {

    var _width = width;
    var _height = height;
    var _data = new Array(width * height);

    var _this = {};

    _this.setPixel = function(x, y, pixel) {
      _data[y * _width + x] = pixel;
    };

    _this.write = function(out) {

      //---------------------------------
      // GIF Signature

      out.writeString('GIF87a');

      //---------------------------------
      // Screen Descriptor

      out.writeShort(_width);
      out.writeShort(_height);

      out.writeByte(0x80); // 2bit
      out.writeByte(0);
      out.writeByte(0);

      //---------------------------------
      // Global Color Map

      // black
      out.writeByte(0x00);
      out.writeByte(0x00);
      out.writeByte(0x00);

      // white
      out.writeByte(0xff);
      out.writeByte(0xff);
      out.writeByte(0xff);

      //---------------------------------
      // Image Descriptor

      out.writeString(',');
      out.writeShort(0);
      out.writeShort(0);
      out.writeShort(_width);
      out.writeShort(_height);
      out.writeByte(0);

      //---------------------------------
      // Local Color Map

      //---------------------------------
      // Raster Data

      var lzwMinCodeSize = 2;
      var raster = getLZWRaster(lzwMinCodeSize);

      out.writeByte(lzwMinCodeSize);

      var offset = 0;

      while (raster.length - offset > 255) {
        out.writeByte(255);
        out.writeBytes(raster, offset, 255);
        offset += 255;
      }

      out.writeByte(raster.length - offset);
      out.writeBytes(raster, offset, raster.length - offset);
      out.writeByte(0x00);

      //---------------------------------
      // GIF Terminator
      out.writeString(';');
    };

    var bitOutputStream = function(out) {

      var _out = out;
      var _bitLength = 0;
      var _bitBuffer = 0;

      var _this = {};

      _this.write = function(data, length) {

        if ( (data >>> length) != 0) {
          throw 'length over';
        }

        while (_bitLength + length >= 8) {
          _out.writeByte(0xff & ( (data << _bitLength) | _bitBuffer) );
          length -= (8 - _bitLength);
          data >>>= (8 - _bitLength);
          _bitBuffer = 0;
          _bitLength = 0;
        }

        _bitBuffer = (data << _bitLength) | _bitBuffer;
        _bitLength = _bitLength + length;
      };

      _this.flush = function() {
        if (_bitLength > 0) {
          _out.writeByte(_bitBuffer);
        }
      };

      return _this;
    };

    var getLZWRaster = function(lzwMinCodeSize) {

      var clearCode = 1 << lzwMinCodeSize;
      var endCode = (1 << lzwMinCodeSize) + 1;
      var bitLength = lzwMinCodeSize + 1;

      // Setup LZWTable
      var table = lzwTable();

      for (var i = 0; i < clearCode; i += 1) {
        table.add(String.fromCharCode(i) );
      }
      table.add(String.fromCharCode(clearCode) );
      table.add(String.fromCharCode(endCode) );

      var byteOut = byteArrayOutputStream();
      var bitOut = bitOutputStream(byteOut);

      // clear code
      bitOut.write(clearCode, bitLength);

      var dataIndex = 0;

      var s = String.fromCharCode(_data[dataIndex]);
      dataIndex += 1;

      while (dataIndex < _data.length) {

        var c = String.fromCharCode(_data[dataIndex]);
        dataIndex += 1;

        if (table.contains(s + c) ) {

          s = s + c;

        } else {

          bitOut.write(table.indexOf(s), bitLength);

          if (table.size() < 0xfff) {

            if (table.size() == (1 << bitLength) ) {
              bitLength += 1;
            }

            table.add(s + c);
          }

          s = c;
        }
      }

      bitOut.write(table.indexOf(s), bitLength);

      // end code
      bitOut.write(endCode, bitLength);

      bitOut.flush();

      return byteOut.toByteArray();
    };

    var lzwTable = function() {

      var _map = {};
      var _size = 0;

      var _this = {};

      _this.add = function(key) {
        if (_this.contains(key) ) {
          throw 'dup key:' + key;
        }
        _map[key] = _size;
        _size += 1;
      };

      _this.size = function() {
        return _size;
      };

      _this.indexOf = function(key) {
        return _map[key];
      };

      _this.contains = function(key) {
        return typeof _map[key] != 'undefined';
      };

      return _this;
    };

    return _this;
  };

  var createDataURL = function(width, height, getPixel) {
    var gif = gifImage(width, height);
    for (var y = 0; y < height; y += 1) {
      for (var x = 0; x < width; x += 1) {
        gif.setPixel(x, y, getPixel(x, y) );
      }
    }

    var b = byteArrayOutputStream();
    gif.write(b);

    var base64 = base64EncodeOutputStream();
    var bytes = b.toByteArray();
    for (var i = 0; i < bytes.length; i += 1) {
      base64.writeByte(bytes[i]);
    }
    base64.flush();

    return 'data:image/gif;base64,' + base64;
  };

  //---------------------------------------------------------------------
  // returns qrcode function.

  return qrcode;
}();

// multibyte support
!function() {

  qrcode.stringToBytesFuncs['UTF-8'] = function(s) {
    // http://stackoverflow.com/questions/18729405/how-to-convert-utf8-string-to-byte-array
    function toUTF8Array(str) {
      var utf8 = [];
      for (var i=0; i < str.length; i++) {
        var charcode = str.charCodeAt(i);
        if (charcode < 0x80) utf8.push(charcode);
        else if (charcode < 0x800) {
          utf8.push(0xc0 | (charcode >> 6),
              0x80 | (charcode & 0x3f));
        }
        else if (charcode < 0xd800 || charcode >= 0xe000) {
          utf8.push(0xe0 | (charcode >> 12),
              0x80 | ((charcode>>6) & 0x3f),
              0x80 | (charcode & 0x3f));
        }
        // surrogate pair
        else {
          i++;
          // UTF-16 encodes 0x10000-0x10FFFF by
          // subtracting 0x10000 and splitting the
          // 20 bits of 0x0-0xFFFFF into two halves
          charcode = 0x10000 + (((charcode & 0x3ff)<<10)
            | (str.charCodeAt(i) & 0x3ff));
          utf8.push(0xf0 | (charcode >>18),
              0x80 | ((charcode>>12) & 0x3f),
              0x80 | ((charcode>>6) & 0x3f),
              0x80 | (charcode & 0x3f));
        }
      }
      return utf8;
    }
    return toUTF8Array(s);
  };

}();

(function (factory) {
  if (typeof define === 'function' && define.amd) {
      define([], factory);
  } else if (typeof exports === 'object') {
      module.exports = factory();
  }
}(function () {
    return qrcode;
}));
WEBEOF_47
cat > "$APP_DIR/web/static/vendor/simple-keyboard/LICENSE" <<'WEBEOF_48'
MIT License

Copyright (c) 2019 Francisco Hodge and project contributors.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
WEBEOF_48
cat > "$APP_DIR/web/static/vendor/simple-keyboard/VERSION" <<'WEBEOF_49'
simple-keyboard 3.8.179 (MIT) — https://github.com/hodgef/simple-keyboard
Fichiers copiés tels quels depuis le paquet npm (build/index.js, build/css/index.css).
WEBEOF_49
cat > "$APP_DIR/web/static/vendor/simple-keyboard/simple-keyboard.css" <<'WEBEOF_50'
/*!
 * 
 *   simple-keyboard v3.8.179
 *   https://github.com/hodgef/simple-keyboard
 *
 *   Copyright (c) Francisco Hodge (https://github.com/hodgef) and project contributors.
 *
 *   This source code is licensed under the MIT license found in the
 *   LICENSE file in the root directory of this source tree.
 *
 */.hg-theme-default{background-color:#ececec;border-radius:5px;box-sizing:border-box;font-family:HelveticaNeue-Light,Helvetica Neue Light,Helvetica Neue,Helvetica,Arial,Lucida Grande,sans-serif;overflow:hidden;padding:5px;touch-action:manipulation;-webkit-user-select:none;-moz-user-select:none;user-select:none;width:100%}.hg-theme-default .hg-button span,.hg-theme-default .hg-button span svg{pointer-events:none}.hg-theme-default button.hg-button{border-width:0;font-size:inherit}.hg-theme-default .hg-button{display:inline-block;flex-grow:1}.hg-theme-default .hg-row{display:flex}.hg-theme-default .hg-row:not(:last-child){margin-bottom:5px}.hg-theme-default .hg-row .hg-button-container,.hg-theme-default .hg-row .hg-button:not(:last-child){margin-right:5px}.hg-theme-default .hg-row>div:last-child{margin-right:0}.hg-theme-default .hg-row .hg-button-container{display:flex}.hg-theme-default .hg-button{align-items:center;background:#fff;border-bottom:1px solid #b5b5b5;border-radius:5px;box-shadow:0 0 3px -1px rgba(0,0,0,.3);box-sizing:border-box;cursor:pointer;display:flex;height:40px;justify-content:center;padding:5px;-webkit-tap-highlight-color:rgba(0,0,0,0)}.hg-theme-default .hg-button.hg-standardBtn{width:20px}.hg-theme-default .hg-button.hg-activeButton{background:#efefef}.hg-theme-default.hg-layout-numeric .hg-button{align-items:center;display:flex;height:60px;justify-content:center;width:33.3%}.hg-theme-default .hg-button.hg-button-numpadadd,.hg-theme-default .hg-button.hg-button-numpadenter{height:85px}.hg-theme-default .hg-button.hg-button-numpad0{width:105px}.hg-theme-default .hg-button.hg-button-com{max-width:85px}.hg-theme-default .hg-button.hg-standardBtn.hg-button-at{max-width:45px}.hg-theme-default .hg-button.hg-selectedButton{background:rgba(5,25,70,.53);color:#fff}.hg-theme-default .hg-button.hg-standardBtn[data-skbtn=".com"]{max-width:82px}.hg-theme-default .hg-button.hg-standardBtn[data-skbtn="@"]{max-width:60px}.hg-candidate-box{background:#ececec;border-bottom:2px solid #b5b5b5;border-radius:5px;display:inline-flex;margin-top:-10px;position:absolute;transform:translateY(-100%);-webkit-user-select:none;-moz-user-select:none;user-select:none}ul.hg-candidate-box-list{display:flex;flex:1;list-style:none;margin:0;padding:0}li.hg-candidate-box-list-item{align-items:center;display:flex;height:40px;justify-content:center;width:40px}li.hg-candidate-box-list-item:hover{background:rgba(0,0,0,.03);cursor:pointer}li.hg-candidate-box-list-item:active{background:rgba(0,0,0,.1)}.hg-candidate-box-prev:before{content:"◄"}.hg-candidate-box-next:before{content:"►"}.hg-candidate-box-next,.hg-candidate-box-prev{align-items:center;color:#969696;cursor:pointer;display:flex;padding:0 10px}.hg-candidate-box-next{border-bottom-right-radius:5px;border-top-right-radius:5px}.hg-candidate-box-prev{border-bottom-left-radius:5px;border-top-left-radius:5px}.hg-candidate-box-btn-active{color:#444}
WEBEOF_50
cat > "$APP_DIR/web/static/vendor/simple-keyboard/simple-keyboard.js" <<'WEBEOF_51'
/*!
 * 
 *   simple-keyboard v3.8.179
 *   https://github.com/hodgef/simple-keyboard
 *
 *   Copyright (c) Francisco Hodge (https://github.com/hodgef) and project contributors.
 *
 *   This source code is licensed under the MIT license found in the
 *   LICENSE file in the root directory of this source tree.
 *
 */
!function(t,e){"object"==typeof exports&&"object"==typeof module?module.exports=e():"function"==typeof define&&define.amd?define([],e):"object"==typeof exports?exports.SimpleKeyboard=e():t.SimpleKeyboard=e()}(this,function(){return function(){var t,e,n={529:function(t){"use strict";t.exports=function(t,e){return{value:t,done:e}}},606:function(t,e,n){"use strict";var r=n(823),o=TypeError;t.exports=function(t,e){if(!delete t[e])throw new o("Cannot delete property "+r(e)+" of "+r(t))}},837:function(t){"use strict";var e=TypeError;t.exports=function(t){if(t>9007199254740991)throw new e("Maximum allowed index exceeded");return t}},400:function(t){"use strict";t.exports={CSSRuleList:0,CSSStyleDeclaration:0,CSSValueList:0,ClientRectList:0,DOMRectList:0,DOMStringList:0,DOMTokenList:1,DataTransferItemList:0,FileList:0,HTMLAllCollection:0,HTMLCollection:0,HTMLFormElement:0,HTMLSelectElement:0,MediaList:0,MimeTypeArray:0,NamedNodeMap:0,NodeList:1,PaintRequestList:0,Plugin:0,PluginArray:0,SVGLengthList:0,SVGNumberList:0,SVGPathSegList:0,SVGPointList:0,SVGStringList:0,SVGTransformList:0,SourceBufferList:0,StyleSheetList:0,TextTrackCueList:0,TextTrackList:0,TouchList:0}},117:function(t){"use strict";t.exports=function(t){return null==t}},269:function(t){"use strict";t.exports=Object.create?Object.create(null):{}},741:function(t){"use strict";var e=Math.ceil,n=Math.floor;t.exports=Math.trunc||function(t){var r=+t;return(r>0?n:e)(r)}},717:function(t,e){"use strict";e.f=Object.getOwnPropertySymbols},823:function(t){"use strict";var e=String;t.exports=function(t){try{return e(t)}catch(t){return"Object"}}}},r={};function o(t){var e=r[t];if(void 0!==e)return e.exports;var i=r[t]={exports:{}};return n[t](i,i.exports,o),i.exports}o.cw=function(t){var e;return function(){if(t){var n=t;t=0,e={exports:{}},n.call(e.exports,e,e.exports)}return e.exports}},e=Object.getPrototypeOf,o.t=function(n,r){if(1&r&&(n=this(n)),8&r)return n;if("object"==typeof n&&n){if(4&r&&n.__esModule)return n;if(16&r&&"function"==typeof n.then)return n}var i=Object.create(null);o.r(i);var a={};t=t||[null,e({}),e([]),e(e)];for(var u=2&r&&n;("object"==typeof u||"function"==typeof u)&&!~t.indexOf(u);u=e(u))Object.getOwnPropertyNames(u).forEach(function(t){a[t]=function(){return n[t]}});return a.default=function(){return n},o.d(i,a),i},o.d=function(t,e){for(var n in e)o.o(e,n)&&!o.o(t,n)&&Object.defineProperty(t,n,{enumerable:!0,get:e[n]})},o.g=function(){if("object"==typeof globalThis)return globalThis;try{return this||new Function("return this")()}catch(t){if("object"==typeof window)return window}}(),o.o=function(t,e){return Object.prototype.hasOwnProperty.call(t,e)},o.r=function(t){"undefined"!=typeof Symbol&&Symbol.toStringTag&&Object.defineProperty(t,Symbol.toStringTag,{value:"Module"}),Object.defineProperty(t,"__esModule",{value:!0})};var i={};return function(){"use strict";o.r(i),o.d(i,{SimpleKeyboard:function(){return br},default:function(){return wr}});var t=o.cw(function(t,e){var n=Ot(),r=_e(),o=TypeError;t.exports=function(t){if(n(t))return t;throw new o(r(t)+" is not a function")}}),e=o.cw(function(t,e){var n=Et(),r=_e(),o=TypeError;t.exports=function(t){if(n(t))return t;throw new o(r(t)+" is not a constructor")}}),n=o.cw(function(t,e){var n=Ct(),r=String,o=TypeError;t.exports=function(t){if(n(t))return t;throw new o("Can't set "+r(t)+" as a prototype")}}),r=o.cw(function(t,e){var n=ze(),r=$t(),o=Gt().f,i=n("unscopables"),a=Array.prototype;void 0===a[i]&&o(a,i,{configurable:!0,value:r(null)}),t.exports=function(t){a[i][t]=!0}}),a=o.cw(function(t,e){var n=Se().o;t.exports=function(t,e,r){return e+(r&&n(t,e).length||1)}}),u=o.cw(function(t,e){var n=It(),r=String,o=TypeError;t.exports=function(t){if(n(t))return t;throw new o(r(t)+" is not an object")}}),s=o.cw(function(t,e){var n=f().jJ,r=p()("forEach");t.exports=r?[].forEach:function(t){return n(this,t,arguments.length>1?arguments[1]:void 0)}}),c=o.cw(function(t,e){var n=Q(),r=et(),o=Re(),i=w(),a=wt(),u=Et(),s=Kt(),c=M(),l=v(),f=ut(),d=st(),p=Tt(),h=K(),y=Array;t.exports=function(t){var e=u(this),v=arguments.length,g=v>1?arguments[1]:void 0,m=void 0!==g;m&&(g=n(g,v>2?arguments[2]:void 0));var b,w,x,O,E,S,k=o(t),P=d(k),I=0;if(!P||this===y&&a(P))for(b=s(k),w=e?new this(b):y(b);b>I;I++)S=m?g(k[I],I):k[I],c(w,I,S);else for(w=e?new this:[],E=(O=f(k,P)).next;!(x=r(E,O)).done;I++){try{h(I)}catch(t){p(O,"throw",t)}S=m?i(O,g,[x.value,I],!0):x.value;try{c(w,I,S)}catch(t){p(O,"throw",t)}}return l(w,I),w}}),l=o.cw(function(t,e){var n=De(),r=Ne(),o=Kt(),i=function(t){return function(e,i,a){var u=n(e),s=o(u);if(0===s)return!t&&-1;var c,l=r(a,s);if(t&&i!=i){for(;s>l;)if((c=u[l++])!=c)return!0}else for(;s>l;l++)if((t||l in u)&&u[l]===i)return t||l||0;return!t&&-1}};t.exports={m:i(!0),q:i(!1)}}),f=o.cw(function(t,e){var n=Q(),r=yt(),o=Re(),i=Kt(),a=b(),u=M(),s=function(t){var e=1===t,s=2===t,c=3===t,l=4===t,f=6===t,d=7===t,p=5===t||f;return function(h,v,y){for(var g,m,b=o(h),w=r(b),x=i(w),O=n(v,y),E=0,S=0,k=e?a(h,x):s||d?a(h,0):void 0;x>E;E++)if((p||E in w)&&(m=O(g=w[E],E,b),t))if(e)u(k,E,m);else if(m)switch(t){case 3:return!0;case 5:return g;case 6:return E;case 2:u(k,S++,g)}else switch(t){case 4:return!1;case 7:u(k,S++,g)}return f?-1:c||l?l:k}};t.exports={jJ:s(0),Tj:s(1),pb:s(2),some:s(3),every:s(4),find:s(5),findIndex:s(6),filterReject:s(7)}}),d=o.cw(function(t,e){var n=q(),r=ze(),o=G(),i=r("species");t.exports=function(t){return o>=51||!n(function(){var e=[];return(e.constructor={})[i]=function(){return{foo:1}},1!==e[t](Boolean).foo})}}),p=o.cw(function(t,e){var n=q();t.exports=function(t,e){var r=[][t];return!!r&&n(function(){r.call(null,e||function(){return 1},1)})}}),h=o.cw(function(e,n){var r=t(),o=Re(),i=yt(),a=Kt(),u=TypeError,s="Reduce of empty array with no initial value",c=function(t){return function(e,n,c,l){var f=o(e),d=i(f),p=a(f);if(r(n),0===p&&c<2)throw new u(s);var h=t?p-1:0,v=t?-1:1;if(c<2)for(;;){if(h in d){l=d[h],h+=v;break}if(h+=v,t?h<0:p<=h)throw new u(s)}for(;t?h>=0:p>h;h+=v)h in d&&(l=n(l,d[h],h,f));return l}};e.exports={k:c(!1),right:c(!0)}}),v=o.cw(function(t,e){var n=L(),r=xt(),o=TypeError,i=Object.getOwnPropertyDescriptor,a=n&&!function(){if(void 0!==this)return!0;try{Object.defineProperty([],"length",{writable:!1}).length=1}catch(t){return t instanceof TypeError}}();t.exports=a?function(t,e){if(r(t)&&!i(t,"length").writable)throw new o("Cannot set read only .length");return t.length=e}:function(t,e){return t.length=e}}),y=o.cw(function(t,e){var n=it();t.exports=n([].slice)}),g=o.cw(function(t,e){var n=y(),r=Math.floor,o=function(t,e){var i=t.length;if(i<8)for(var a,u,s=1;s<i;){for(u=s,a=t[s];u&&e(t[u-1],a)>0;)t[u]=t[--u];u!==s++&&(t[u]=a)}else for(var c=r(i/2),l=o(n(t,0,c),e),f=o(n(t,c),e),d=l.length,p=f.length,h=0,v=0;h<d||v<p;)t[h+v]=h<d&&v<p?e(l[h],f[v])<=0?l[h++]:f[v++]:h<d?l[h++]:f[v++];return t};t.exports=o}),m=o.cw(function(t,e){var n=xt(),r=Et(),o=It(),i=ze()("species"),a=Array;t.exports=function(t){var e;return n(t)&&(e=t.constructor,(r(e)&&(e===a||n(e.prototype))||o(e)&&null===(e=e[i]))&&(e=void 0)),void 0===e?a:e}}),b=o.cw(function(t,e){var n=m();t.exports=function(t,e){return new(n(t))(0===e?0:e)}}),w=o.cw(function(t,e){var n=u(),r=Tt();t.exports=function(t,e,o,i){try{return i?e(n(o)[0],o[1]):e(o)}catch(e){r(t,"throw",e)}}}),x=o.cw(function(t,e){var n=ze()("iterator"),r=!1;try{var o=0,i={next:function(){return{done:!!o++}},return:function(){r=!0}};i[n]=function(){return this},Array.from(i,function(){throw 2})}catch(t){}t.exports=function(t,e){try{if(!e&&!r)return!1}catch(t){return!1}var o=!1;try{var i={};i[n]=function(){return{next:function(){return{done:o=!0}}}},t(i)}catch(t){}return o}}),O=o.cw(function(t,e){var n=it(),r=n({}.toString),o=n("".slice);t.exports=function(t){return o(r(t),8,-1)}}),E=o.cw(function(t,e){var n=Ke(),r=Ot(),o=O(),i=ze()("toStringTag"),a=Object,u="Arguments"===o(function(){return arguments}());t.exports=n?o:function(t){var e,n,s;return void 0===t?"Undefined":null===t?"Null":"string"==typeof(n=function(t,e){try{return t[e]}catch(t){}}(e=a(t),i))?n:u?o(e):"Object"===(s=o(e))&&r(e.callee)?"Arguments":s}}),S=o.cw(function(t,e){var n=dt(),r=ie(),o=Vt(),i=Gt();t.exports=function(t,e,a){for(var u=r(e),s=i.f,c=o.f,l=0;l<u.length;l++){var f=u[l];n(t,f)||a&&n(a,f)||s(t,f,c(e,f))}}}),k=o.cw(function(t,e){var n=ze()("match");t.exports=function(t){var e=/./;try{"/./"[t](e)}catch(r){try{return e[n]=!1,"/./"[t](e)}catch(t){}}return!1}}),P=o.cw(function(t,e){var n=q();t.exports=!n(function(){function t(){}return t.prototype.constructor=null,Object.getPrototypeOf(new t)!==t.prototype})}),I=function(){return o(529)},C=o.cw(function(t,e){var n=L(),r=Gt(),o=A();t.exports=n?function(t,e,n){return r.f(t,e,o(1,n))}:function(t,e,n){return t[e]=n,t}}),A=o.cw(function(t,e){t.exports=function(t,e){return{enumerable:!(1&t),configurable:!(2&t),writable:!(4&t),value:e}}}),M=o.cw(function(t,e){var n=L(),r=Gt(),o=A();t.exports=function(t,e,i){n?r.f(t,e,o(0,i)):t[e]=i}}),N=o.cw(function(t,e){var n=u(),r=oe(),o=TypeError;t.exports=function(t){if(n(this),"string"===t||"default"===t)t="string";else if("number"!==t)throw new o("Incorrect hint");return r(this,t)}}),D=o.cw(function(t,e){var n=Ft(),r=Gt();t.exports=function(t,e,o){return o.get&&n(o.get,e,{getter:!0}),o.set&&n(o.set,e,{setter:!0}),r.f(t,e,o)}}),T=o.cw(function(t,e){var n=Ot(),r=Gt(),o=Ft(),i=j();t.exports=function(t,e,a,u){u||(u={});var s=u.enumerable,c=void 0!==u.name?u.name:e;if(n(a)&&o(a,c,u),u.global)s?t[e]=a:i(e,a);else{try{u.unsafe?t[e]&&(s=!0):delete t[e]}catch(t){}s?t[e]=a:r.f(t,e,{value:a,enumerable:!1,configurable:!u.nonConfigurable,writable:!u.nonWritable})}return t}}),j=o.cw(function(t,e){var n=ft(),r=Object.defineProperty;t.exports=function(t,e){try{r(n,t,{value:e,configurable:!0,writable:!0})}catch(r){n[t]=e}return e}}),R=function(){return o(606)},L=o.cw(function(t,e){var n=q();t.exports=!n(function(){return 7!==Object.defineProperty({},1,{get:function(){return 7}})[1]})}),B=o.cw(function(t,e){var n=ft(),r=It(),o=n.document,i=r(o)&&r(o.createElement);t.exports=function(t){return i?o.createElement(t):{}}}),K=function(){return o(837)},F=o.cw(function(t,e){var n=B()("span").classList,r=n&&n.constructor&&n.constructor.prototype;t.exports=r===Object.prototype?void 0:r}),_=o.cw(function(t,e){t.exports=["constructor","hasOwnProperty","isPrototypeOf","propertyIsEnumerable","toLocaleString","toString","valueOf"]}),U=o.cw(function(t,e){var n=J().match(/firefox\/(\d+)/i);t.exports=!!n&&+n[1]}),H=o.cw(function(t,e){var n=J();t.exports=/MSIE|Trident/.test(n)}),$=o.cw(function(t,e){var n=z();t.exports="NODE"===n}),J=o.cw(function(t,e){var n=ft().navigator,r=n&&n.userAgent;t.exports=r?String(r):""}),G=o.cw(function(t,e){var n,r,o=ft(),i=J(),a=o.process,u=o.Deno,s=a&&a.versions||u&&u.version,c=s&&s.v8;c&&(r=(n=c.split("."))[0]>0&&n[0]<4?1:+(n[0]+n[1])),!r&&i&&(!(n=i.match(/Edge\/(\d+)/))||n[1]>=74)&&(n=i.match(/Chrome\/(\d+)/))&&(r=+n[1]),t.exports=r}),V=o.cw(function(t,e){var n=J().match(/AppleWebKit\/(\d+)\./);t.exports=!!n&&+n[1]}),z=o.cw(function(t,e){var n=ft(),r=J(),o=O(),i=function(t){return r.slice(0,t.length)===t};t.exports=i("Bun/")?"BUN":i("Cloudflare-Workers")?"CLOUDFLARE":i("Deno/")?"DENO":i("Node.js/")?"NODE":n.Bun&&"string"==typeof Bun.version?"BUN":n.Deno&&"object"==typeof Deno.version?"DENO":"process"===o(n.process)?"NODE":n.window&&n.document?"BROWSER":"REST"}),Y=o.cw(function(t,e){var n=ft(),r=Vt().f,o=C(),i=T(),a=j(),u=S(),s=St();t.exports=function(t,e){var c,l,f,d,p,h=t.target,v=t.global,y=t.stat;if(c=v?n:y?n[h]||a(h,{}):n[h]&&n[h].prototype)for(l in e){if(d=e[l],f=t.dontCallGetSet?(p=r(c,l))&&p.value:c[l],!s(v?l:h+(y?".":"#")+l,t.forced)&&void 0!==f){if(typeof d==typeof f)continue;u(d,f)}(t.sham||f&&f.sham)&&o(d,"sham",!0),i(c,l,d,t)}}}),q=o.cw(function(t,e){t.exports=function(t){try{return!!t()}catch(t){return!0}}}),W=o.cw(function(t,e){Sn();var n=et(),r=T(),o=le(),i=q(),a=ze(),u=C(),s=a("species"),c=RegExp.prototype;t.exports=function(t,e,l,f){var d=a(t),p=!i(function(){var e={};return e[d]=function(){return 7},7!==""[t](e)}),h=p&&!i(function(){var e=!1,n=/a/;if("split"===t){var r={};r[s]=function(){return n},(n={constructor:r,flags:""})[d]=/./[d]}return n.exec=function(){return e=!0,null},n[d](""),!e});if(!p||!h||l){var v=/./[d],y=e(d,""[t],function(t,e,r,i,a){var u=e.exec;return u===o||u===c.exec?p&&!a?{done:!0,value:n(v,e,r,i)}:{done:!0,value:n(t,r,e,i)}:{done:!1}});r(String.prototype,t,y[0]),r(c,d,y[1])}f&&u(c[d],"sham",!0)}}),X=o.cw(function(t,e){var n=Z(),r=Function.prototype,o=r.apply,i=r.call;t.exports="object"==typeof Reflect&&Reflect.apply||(n?i.bind(o):function(){return i.apply(o,arguments)})}),Q=o.cw(function(e,n){var r=ot(),o=t(),i=Z(),a=r(r.bind);e.exports=function(t,e){return o(t),void 0===e?t:i?a(t,e):function(){return t.apply(e,arguments)}}}),Z=o.cw(function(t,e){var n=q();t.exports=!n(function(){var t=function(){}.bind();return"function"!=typeof t||t.hasOwnProperty("prototype")})}),tt=o.cw(function(e,n){var r=it(),o=t(),i=It(),a=dt(),u=y(),s=Z(),c=Function,l=r([].concat),f=r([].join),d={};e.exports=s?c.bind:function(t){var e=o(this),n=e.prototype,r=u(arguments,1),s=function(){var n=l(r,u(arguments));return this instanceof s?function(t,e,n){if(!a(d,e)){for(var r=[],o=0;o<e;o++)r[o]="a["+o+"]";d[e]=c("C,a","return new C("+f(r,",")+")")}return d[e](t,n)}(e,n.length,n):e.apply(t,n)};return i(n)&&(s.prototype=n),s}}),et=o.cw(function(t,e){var n=Z(),r=Function.prototype.call;t.exports=n?r.bind(r):function(){return r.apply(r,arguments)}}),nt=o.cw(function(t,e){var n=L(),r=dt(),o=Function.prototype,i=n&&Object.getOwnPropertyDescriptor,a=r(o,"name"),u=a&&"something"===function(){}.name,s=a&&(!n||n&&i(o,"name").configurable);t.exports={EXISTS:a,PROPER:u,CONFIGURABLE:s}}),rt=o.cw(function(e,n){var r=it(),o=t();e.exports=function(t,e,n){try{return r(o(Object.getOwnPropertyDescriptor(t,e)[n]))}catch(t){}}}),ot=o.cw(function(t,e){var n=O(),r=it();t.exports=function(t){if("Function"===n(t))return r(t)}}),it=o.cw(function(t,e){var n=Z(),r=Function.prototype,o=r.call,i=n&&r.bind.bind(o,o);t.exports=n?i:function(t){return function(){return o.apply(t,arguments)}}}),at=o.cw(function(t,e){var n=ft(),r=Ot();t.exports=function(t,e){return arguments.length<2?(o=n[t],r(o)?o:void 0):n[t]&&n[t][e];var o}}),ut=o.cw(function(t,e){var n=et(),r=Ot(),o=u(),i=_e(),a=st(),s=TypeError;t.exports=function(t,e){var u=arguments.length<2?a(t):e;if(r(u))return o(n(u,t));throw new s(i(t)+" is not iterable")}}),st=o.cw(function(t,e){var n=O(),r=Pt(),o=ct(),i=ze()("iterator"),a=Array.prototype;t.exports=function(t){if(!r(t))return o(t,i)||o(t,"@@iterator")||("Arguments"===n(t)?a[i]:void 0)}}),ct=o.cw(function(e,n){var r=t(),o=Pt();e.exports=function(t,e){var n=t[e];return o(n)?void 0:r(n)}}),lt=o.cw(function(t,e){var n=it(),r=Re(),o=Math.floor,i=n("".charAt),a=n("".replace),u=n("".slice),s=/\$([$&'`]|\d{1,2}|<[^>]*>)/g,c=/\$([$&'`]|\d{1,2})/g;t.exports=function(t,e,n,l,f,d){var p=n+t.length,h=l.length,v=c;return void 0!==f&&(f=r(f),v=s),a(d,v,function(r,a){var s;switch(i(a,0)){case"$":return"$";case"&":return t;case"`":return u(e,0,n);case"'":return u(e,p);case"<":s=f[u(a,1,-1)];break;default:var c=+a;if(0===c)return r;if(c>h){var d=o(c/10);return 0===d?r:d<=h?void 0===l[d-1]?i(a,1):l[d-1]+i(a,1):r}s=l[c-1]}return void 0===s?"":s})}}),ft=o.cw(function(t,e){var n=function(t){return t&&t.Math===Math&&t};t.exports=n("object"==typeof globalThis&&globalThis)||n("object"==typeof window&&window)||n("object"==typeof self&&self)||n("object"==typeof o.g&&o.g)||n("object"==typeof this&&this)||function(){return this}()||Function("return this")()}),dt=o.cw(function(t,e){var n=it(),r=Re(),o=n({}.hasOwnProperty);t.exports=Object.hasOwn||function(t,e){return o(r(t),e)}}),pt=o.cw(function(t,e){t.exports={}}),ht=o.cw(function(t,e){var n=at();t.exports=n("document","documentElement")}),vt=o.cw(function(t,e){var n=L(),r=q(),o=B();t.exports=!n&&!r(function(){return 7!==Object.defineProperty(o("div"),"a",{get:function(){return 7}}).a})}),yt=o.cw(function(t,e){var n=it(),r=q(),o=O(),i=Object,a=n("".split);t.exports=r(function(){return!i("z").propertyIsEnumerable(0)})?function(t){return"String"===o(t)?a(t,""):i(t)}:i}),gt=o.cw(function(t,e){var n=Ot(),r=It(),o=ne();t.exports=function(t,e,i){var a,u;return o&&n(a=e.constructor)&&a!==i&&r(u=a.prototype)&&u!==i.prototype&&o(t,u),t}}),mt=o.cw(function(t,e){var n=it(),r=Ot(),o=xe(),i=n(Function.toString);r(o.inspectSource)||(o.inspectSource=function(t){return i(t)}),t.exports=o.inspectSource}),bt=o.cw(function(t,e){var n,r,o,i=Je(),a=ft(),u=It(),s=C(),c=dt(),l=xe(),f=we(),d=pt(),p="Object already initialized",h=a.TypeError,v=a.WeakMap;if(i||l.state){var y=l.state||(l.state=new v);y.get=y.get,y.has=y.has,y.set=y.set,n=function(t,e){if(y.has(t))throw new h(p);return e.facade=t,y.set(t,e),e},r=function(t){return y.get(t)||{}},o=function(t){return y.has(t)}}else{var g=f("state");d[g]=!0,n=function(t,e){if(c(t,g))throw new h(p);return e.facade=t,s(t,g,e),e},r=function(t){return c(t,g)?t[g]:{}},o=function(t){return c(t,g)}}t.exports={set:n,get:r,has:o,enforce:function(t){return o(t)?r(t):n(t,{})},getterFor:function(t){return function(e){var n;if(!u(e)||(n=r(e)).type!==t)throw new h("Incompatible receiver, "+t+" required");return n}}}}),wt=o.cw(function(t,e){var n=ze(),r=Bt(),o=n("iterator"),i=Array.prototype;t.exports=function(t){return void 0!==t&&(r.Array===t||i[o]===t)}}),xt=o.cw(function(t,e){var n=O();t.exports=Array.isArray||function(t){return"Array"===n(t)}}),Ot=o.cw(function(t,e){var n="object"==typeof document&&document.all;t.exports=void 0===n&&void 0!==n?function(t){return"function"==typeof t||t===n}:function(t){return"function"==typeof t}}),Et=o.cw(function(t,e){var n=it(),r=q(),o=Ot(),i=E(),a=at(),u=mt(),s=function(){},c=a("Reflect","construct"),l=/^\s*(?:class|function)\b/,f=n(l.exec),d=!l.test(s),p=function(t){if(!o(t))return!1;try{return c(s,[],t),!0}catch(t){return!1}},h=function(t){if(!o(t))return!1;switch(i(t)){case"AsyncFunction":case"GeneratorFunction":case"AsyncGeneratorFunction":return!1}try{return d||!!f(l,u(t))}catch(t){return!0}};h.sham=!0,t.exports=!c||r(function(){var t;return p(p.call)||!p(Object)||!p(function(){t=!0})||t})?h:p}),St=o.cw(function(t,e){var n=q(),r=Ot(),o=/#|\.prototype\./,i=function(t,e){var o=u[a(t)];return o===c||o!==s&&(r(e)?n(e):!!e)},a=i.normalize=function(t){return String(t).replace(o,".").toLowerCase()},u=i.data={},s=i.NATIVE="N",c=i.POLYFILL="P";t.exports=i}),kt=o.cw(function(t,e){var n=It(),r=Math.floor;t.exports=Number.isInteger||function(t){return!n(t)&&isFinite(t)&&r(t)===t}}),Pt=function(){return o(117)},It=o.cw(function(t,e){var n=Ot();t.exports=function(t){return"object"==typeof t?null!==t:n(t)}}),Ct=o.cw(function(t,e){var n=It();t.exports=function(t){return n(t)||null===t}}),At=o.cw(function(t,e){t.exports=!1}),Mt=o.cw(function(t,e){var n=It(),r=bt().get;t.exports=function(t){if(!n(t))return!1;var e=r(t);return!!e&&"RawJSON"===e.type}}),Nt=o.cw(function(t,e){var n=It(),r=O(),o=ze()("match");t.exports=function(t){var e;return n(t)&&(void 0!==(e=t[o])?!!e:"RegExp"===r(t))}}),Dt=o.cw(function(t,e){var n=at(),r=Ot(),o=Xt(),i=He(),a=Object;t.exports=i?function(t){return"symbol"==typeof t}:function(t){var e=n("Symbol");return r(e)&&o(e.prototype,a(t))}}),Tt=o.cw(function(t,e){var n=et(),r=u(),o=ct();t.exports=function(t,e,i){var a,u;r(t);try{if(!(a=o(t,"return"))){if("throw"===e)throw i;return i}a=n(a,t)}catch(t){u=!0,a=t}if("throw"===e)throw i;if(u)throw a;return r(a),i}}),jt=o.cw(function(t,e){var n=Lt().IteratorPrototype,r=$t(),o=A(),i=be(),a=Bt(),u=function(){return this};t.exports=function(t,e,s,c){var l=e+" Iterator";return t.prototype=r(n,{next:o(+!c,s)}),i(t,l,!1,!0),a[l]=u,t}}),Rt=o.cw(function(t,e){var n=Y(),r=et(),o=At(),i=nt(),a=Ot(),u=jt(),s=Wt(),c=ne(),l=be(),f=C(),d=T(),p=ze(),h=Bt(),v=Lt(),y=i.PROPER,g=i.CONFIGURABLE,m=v.IteratorPrototype,b=v.BUGGY_SAFARI_ITERATORS,w=p("iterator"),x="keys",O="values",E="entries",S=function(){return this};t.exports=function(t,e,i,p,v,k,P){u(i,e,p);var I,C,A,M=function(t){if(t===v&&R)return R;if(!b&&t&&t in T)return T[t];switch(t){case x:case O:case E:return function(){return new i(this,t)}}return function(){return new i(this)}},N=e+" Iterator",D=!1,T=t.prototype,j=T[w]||T["@@iterator"]||v&&T[v],R=!b&&j||M(v),L="Array"===e&&T.entries||j;if(L&&(I=s(L.call(new t)))!==Object.prototype&&I.next&&(o||s(I)===m||(c?c(I,m):a(I[w])||d(I,w,S)),l(I,N,!0,!0),o&&(h[N]=S)),y&&v===O&&j&&j.name!==O&&(!o&&g?f(T,"name",O):(D=!0,R=function(){return r(j,this)})),v)if(C={values:M(O),keys:k?R:M(x),entries:M(E)},P)for(A in C)(b||D||!(A in T))&&d(T,A,C[A]);else n({target:e,proto:!0,forced:b||D},C);return o&&!P||T[w]===R||d(T,w,R,{name:v}),h[e]=R,C}}),Lt=o.cw(function(t,e){var n,r,o,i=q(),a=Ot(),u=It(),s=$t(),c=Wt(),l=T(),f=ze(),d=At(),p=f("iterator"),h=!1;[].keys&&("next"in(o=[].keys())?(r=c(c(o)))!==Object.prototype&&(n=r):h=!0),!u(n)||i(function(){var t={};return n[p].call(t)!==t})?n={}:d&&(n=s(n)),a(n[p])||l(n,p,function(){return this}),t.exports={IteratorPrototype:n,BUGGY_SAFARI_ITERATORS:h}}),Bt=function(){return o(269)},Kt=o.cw(function(t,e){var n=je();t.exports=function(t){return n(t.length)}}),Ft=o.cw(function(t,e){var n=it(),r=q(),o=Ot(),i=dt(),a=L(),u=nt().CONFIGURABLE,s=mt(),c=bt(),l=c.enforce,f=c.get,d=String,p=Object.defineProperty,h=n("".slice),v=n("".replace),y=n([].join),g=a&&!r(function(){return 8!==p(function(){},"length",{value:8}).length}),m=String(String).split("String"),b=t.exports=function(t,e,n){"Symbol("===h(d(e),0,7)&&(e="["+v(d(e),/^Symbol\(([^)]*)\).*$/,"$1")+"]"),n&&n.getter&&(e="get "+e),n&&n.setter&&(e="set "+e),(!i(t,"name")||u&&t.name!==e)&&(a?p(t,"name",{value:e,configurable:!0}):t.name=e),g&&n&&i(n,"arity")&&t.length!==n.arity&&p(t,"length",{value:n.arity});try{n&&i(n,"constructor")&&n.constructor?a&&p(t,"prototype",{writable:!1}):t.prototype&&(t.prototype=void 0)}catch(t){}var r=l(t);return i(r,"source")||(r.source=y(m,"string"==typeof e?e:"")),t};Function.prototype.toString=b(function(){return o(this)&&f(this).source||s(this)},"toString")}),_t=o.cw(function(t,e){var n=q();t.exports=!n(function(){var t="9007199254740993",e=JSON.rawJSON(t);return!JSON.isRawJSON(e)||JSON.stringify(e)!==t})}),Ut=o.cw(function(t,e){var n=Nt(),r=TypeError;t.exports=function(t){if(n(t))throw new r("The method doesn't accept regular expressions");return t}}),Ht=o.cw(function(t,e){var n=L(),r=it(),o=et(),i=q(),a=Zt(),u=$n(),s=te(),c=Re(),l=yt(),f=Object.assign,d=Object.defineProperty,p=r([].concat);t.exports=!f||i(function(){if(n&&1!==f({b:1},f(d({},"a",{enumerable:!0,get:function(){d(this,"b",{value:3,enumerable:!1})}}),{b:2})).b)return!0;var t={},e={},r=Symbol("assign detection"),o="abcdefghijklmnopqrst";return t[r]=7,o.split("").forEach(function(t){e[t]=t}),7!==f({},t)[r]||a(f({},e)).join("")!==o})?function(t,e){for(var r=c(t),i=arguments.length,f=1,d=u.f,h=s.f;i>f;)for(var v,y=l(arguments[f++]),g=d?p(a(y),d(y)):a(y),m=g.length,b=0;m>b;)v=g[b++],n&&!o(h,y,v)||(r[v]=y[v]);return r}:f}),$t=o.cw(function(t,e){var n,r=u(),o=Jt(),i=_(),a=pt(),s=ht(),c=B(),l=we(),f="prototype",d="script",p=l("IE_PROTO"),h=function(){},v=function(t){return"<"+d+">"+t+"</"+d+">"},y=function(t){t.write(v("")),t.close();var e=t.parentWindow.Object;return t=null,e},g=function(){try{n=new ActiveXObject("htmlfile")}catch(t){}var t,e,r;g="undefined"!=typeof document?document.domain&&n?y(n):(e=c("iframe"),r="java"+d+":",e.style.display="none",s.appendChild(e),e.src=String(r),(t=e.contentWindow.document).open(),t.write(v("document.F=Object")),t.close(),t.F):y(n);for(var o=i.length;o--;)delete g[f][i[o]];return g()};a[p]=!0,t.exports=Object.create||function(t,e){var n;return null!==t?(h[f]=r(t),n=new h,h[f]=null,n[p]=t):n=g(),void 0===e?n:o.f(n,e)}}),Jt=o.cw(function(t,e){var n=L(),r=$e(),o=Gt(),i=u(),a=De(),s=Zt();e.f=n&&!r?Object.defineProperties:function(t,e){i(t);for(var n,r=a(e),u=s(e),c=u.length,l=0;c>l;)o.f(t,n=u[l++],r[n]);return t}}),Gt=o.cw(function(t,e){var n=L(),r=vt(),o=$e(),i=u(),a=Be(),s=TypeError,c=Object.defineProperty,l=Object.getOwnPropertyDescriptor,f="enumerable",d="configurable",p="writable";e.f=n?o?function(t,e,n){if(i(t),e=a(e),i(n),"function"==typeof t&&"prototype"===e&&"value"in n&&p in n&&!n[p]){var r=l(t,e);r&&r[p]&&(t[e]=n.value,n={configurable:d in n?n[d]:r[d],enumerable:f in n?n[f]:r[f],writable:!1})}return c(t,e,n)}:c:function(t,e,n){if(i(t),e=a(e),i(n),r)try{return c(t,e,n)}catch(t){}if("get"in n||"set"in n)throw new s("Accessors not supported");return"value"in n&&(t[e]=n.value),t}}),Vt=o.cw(function(t,e){var n=L(),r=et(),o=te(),i=A(),a=De(),u=Be(),s=dt(),c=vt(),l=Object.getOwnPropertyDescriptor;e.f=n?l:function(t,e){if(t=a(t),e=u(e),c)try{return l(t,e)}catch(t){}if(s(t,e))return i(!r(o.f,t,e),t[e])}}),zt=o.cw(function(t,e){var n=O(),r=De(),o=Yt().f,i=y(),a="object"==typeof window&&window&&Object.getOwnPropertyNames?Object.getOwnPropertyNames(window):[];t.exports.f=function(t){return a&&"Window"===n(t)?function(t){try{return o(t)}catch(t){return i(a)}}(t):o(r(t))}}),Yt=o.cw(function(t,e){var n=Qt(),r=_().concat("length","prototype");e.f=Object.getOwnPropertyNames||function(t){return n(t,r)}}),qt=function(){return o(717)},Wt=o.cw(function(t,e){var n=dt(),r=Ot(),o=Re(),i=we(),a=P(),u=i("IE_PROTO"),s=Object,c=s.prototype;t.exports=a?s.getPrototypeOf:function(t){var e=o(t);if(n(e,u))return e[u];var i=e.constructor;return r(i)&&e instanceof i?i.prototype:e instanceof s?c:null}}),Xt=o.cw(function(t,e){var n=it();t.exports=n({}.isPrototypeOf)}),Qt=o.cw(function(t,e){var n=it(),r=dt(),o=De(),i=l().q,a=pt(),u=n([].push);t.exports=function(t,e){var n,s=o(t),c=0,l=[];for(n in s)!r(a,n)&&r(s,n)&&u(l,n);for(;e.length>c;)r(s,n=e[c++])&&(~i(l,n)||u(l,n));return l}}),Zt=o.cw(function(t,e){var n=Qt(),r=_();t.exports=Object.keys||function(t){return n(t,r)}}),te=o.cw(function(t,e){var n={}.propertyIsEnumerable,r=Object.getOwnPropertyDescriptor,o=r&&!n.call({1:2},1);e.f=o?function(t){var e=r(this,t);return!!e&&e.enumerable}:n}),ee=o.cw(function(t,e){var n=At(),r=ft(),o=q(),i=V();t.exports=n||!o(function(){if(!(i&&i<535)){var t=Math.random();__defineSetter__.call(null,t,function(){}),delete r[t]}})}),ne=o.cw(function(t,e){var r=rt(),o=It(),i=ge(),a=n();t.exports=Object.setPrototypeOf||("__proto__"in{}?function(){var t,e=!1,n={};try{(t=r(Object.prototype,"__proto__","set"))(n,[]),e=n instanceof Array}catch(t){}return function(n,r){return i(n),a(r),o(n)?(e?t(n,r):n.__proto__=r,n):n}}():void 0)}),re=o.cw(function(t,e){var n=Ke(),r=E();t.exports=n?{}.toString:function(){return"[object "+r(this)+"]"}}),oe=o.cw(function(t,e){var n=et(),r=Ot(),o=It(),i=TypeError;t.exports=function(t,e){var a,u;if("string"===e&&r(a=t.toString)&&!o(u=n(a,t)))return u;if(r(a=t.valueOf)&&!o(u=n(a,t)))return u;if("string"!==e&&r(a=t.toString)&&!o(u=n(a,t)))return u;throw new i("Can't convert object to primitive value")}}),ie=o.cw(function(t,e){var n=at(),r=it(),o=Yt(),i=$n(),a=u(),s=r([].concat);t.exports=n("Reflect","ownKeys")||function(t){var e=o.f(a(t)),n=i.f;return n?s(e,n(t)):e}}),ae=o.cw(function(t,e){var n=it(),r=dt(),o=SyntaxError,i=parseInt,a=String.fromCharCode,u=n("".charAt),s=n("".slice),c=n(/./.exec),l={'\\"':'"',"\\\\":"\\","\\/":"/","\\b":"\b","\\f":"\f","\\n":"\n","\\r":"\r","\\t":"\t"},f=/^[\da-f]{4}$/i,d=/^[\u0000-\u001F]$/;t.exports=function(t,e){for(var n=!0,p="";e<t.length;){var h=u(t,e);if("\\"===h){var v=s(t,e,e+2);if(r(l,v))p+=l[v],e+=2;else{if("\\u"!==v)throw new o('Unknown escape sequence: "'+v+'"');var y=s(t,e+=2,e+4);if(!c(f,y))throw new o("Bad Unicode escape at: "+e);p+=a(i(y,16)),e+=4}}else{if('"'===h){n=!1,e++;break}if(c(d,h))throw new o("Bad control character in string literal at: "+e);p+=h,e++}}if(n)throw new o("Unterminated string at: "+e);return{value:p,end:e}}}),ue=o.cw(function(t,e){var n=ft();t.exports=n}),se=o.cw(function(t,e){var n=Gt().f;t.exports=function(t,e,r){r in t||n(t,r,{configurable:!0,get:function(){return e[r]},set:function(t){e[r]=t}})}}),ce=o.cw(function(t,e){var n=et(),r=u(),o=Ot(),i=O(),a=le(),s=TypeError;t.exports=function(t,e){var u=t.exec;if(o(u)){var c=n(u,t,e);return null!==c&&r(c),c}if("RegExp"===i(t))return n(a,t,e);throw new s("RegExp#exec called on incompatible receiver")}}),le=o.cw(function(t,e){var n,r,o=et(),i=it(),a=Fe(),u=de(),s=he(),c=Oe(),l=$t(),f=bt().get,d=ve(),p=ye(),h=c("native-string-replace",String.prototype.replace),v=RegExp.prototype.exec,y=v,g=i("".charAt),m=i("".indexOf),b=i("".replace),w=i("".slice),x=(r=/b*/g,o(v,n=/a/,"a"),o(v,r,"a"),0!==n.lastIndex||0!==r.lastIndex),O=s.BROKEN_CARET,E=void 0!==/()??/.exec("")[1],S=function(t,e){for(var n=t.groups=l(null),r=0;r<e.length;r++){var o=e[r];n[o[0]]=t[o[1]]}};(x||E||O||d||p)&&(y=function(t){var e,n,r,i=this,s=f(i),c=a(t),l=s.raw;if(l)return l.lastIndex=i.lastIndex,e=o(y,l,c),i.lastIndex=l.lastIndex,e&&s.groups&&S(e,s.groups),e;var d=s.groups,p=O&&i.sticky,k=o(u,i),P=i.source,I=0,C=c;if(p){k=b(k,"y",""),-1===m(k,"g")&&(k+="g"),C=w(c,i.lastIndex);var A=i.lastIndex>0&&g(c,i.lastIndex-1);i.lastIndex>0&&(!i.multiline||i.multiline&&"\n"!==A&&"\r"!==A&&"\u2028"!==A&&"\u2029"!==A)&&(P="(?: (?:"+P+"))",C=" "+C,I++),n=new RegExp("^(?:"+P+")",k)}E&&(n=new RegExp("^"+P+"$(?!\\s)",k)),x&&(r=i.lastIndex);var M=o(v,p?n:i,C);return p?M?(M.input=c,M[0]=w(M[0],I),M.index=i.lastIndex,i.lastIndex+=M[0].length):i.lastIndex=0:x&&M&&(i.lastIndex=i.global?M.index+M[0].length:r),E&&M&&M.length>1&&o(h,M[0],n,function(){for(var t=1;t<arguments.length-2;t++)void 0===arguments[t]&&(M[t]=void 0)}),M&&d&&S(M,d),M}),t.exports=y}),fe=o.cw(function(t,e){var n=ft(),r=q(),o=n.RegExp,i=!r(function(){var t=!0;try{o(".","d")}catch(e){t=!1}var e={},n="",r=t?"dgimsy":"gimsy",i=function(t,r){Object.defineProperty(e,t,{get:function(){return n+=r,!0}})},a={dotAll:"s",global:"g",ignoreCase:"i",multiline:"m",sticky:"y"};for(var u in t&&(a.hasIndices="d"),a)i(u,a[u]);return Object.getOwnPropertyDescriptor(o.prototype,"flags").get.call(e)!==r||n!==r});t.exports={correct:i}}),de=o.cw(function(t,e){var n=u();t.exports=function(){var t=n(this),e="";return t.hasIndices&&(e+="d"),t.global&&(e+="g"),t.ignoreCase&&(e+="i"),t.multiline&&(e+="m"),t.dotAll&&(e+="s"),t.unicode&&(e+="u"),t.unicodeSets&&(e+="v"),t.sticky&&(e+="y"),e}}),pe=o.cw(function(t,e){var n=et(),r=dt(),o=Xt(),i=fe(),a=de(),u=RegExp.prototype;t.exports=i.correct?function(t){return t.flags}:function(t){return i.correct||!o(u,t)||r(t,"flags")?t.flags:n(a,t)}}),he=o.cw(function(t,e){var n=q(),r=ft().RegExp,o=n(function(){var t=r("a","y");return t.lastIndex=2,null!==t.exec("abcd")}),i=o||n(function(){return!r("a","y").sticky}),a=o||n(function(){var t=r("^r","gy");return t.lastIndex=2,null!==t.exec("str")});t.exports={BROKEN_CARET:a,MISSED_STICKY:i,UNSUPPORTED_Y:o}}),ve=o.cw(function(t,e){var n=q(),r=ft().RegExp;t.exports=n(function(){var t=r(".","s");return!(t.dotAll&&t.test("\n")&&"s"===t.flags)})}),ye=o.cw(function(t,e){var n=q(),r=ft().RegExp;t.exports=n(function(){var t=r("(?<a>b)","g");return"b"!==t.exec("b").groups.a||"bc"!=="b".replace(t,"$<a>c")})}),ge=o.cw(function(t,e){var n=Pt(),r=TypeError;t.exports=function(t){if(n(t))throw new r("Can't call method on "+t);return t}}),me=o.cw(function(t,e){var n=at(),r=D(),o=ze(),i=L(),a=o("species");t.exports=function(t){var e=n(t);i&&e&&!e[a]&&r(e,a,{configurable:!0,get:function(){return this}})}}),be=o.cw(function(t,e){var n=Gt().f,r=dt(),o=ze()("toStringTag");t.exports=function(t,e,i){t&&!i&&(t=t.prototype),t&&!r(t,o)&&n(t,o,{configurable:!0,value:e})}}),we=o.cw(function(t,e){var n=Oe(),r=Ue(),o=n("keys");t.exports=function(t){return o[t]||(o[t]=r(t))}}),xe=o.cw(function(t,e){var n=At(),r=ft(),o=j(),i="__core-js_shared__",a=t.exports=r[i]||o(i,{});(a.versions||(a.versions=[])).push({version:"3.50.0",mode:n?"pure":"global",copyright:"© 2013–2025 Denis Pushkarev (zloirock.ru), 2025–2026 CoreJS Company (core-js.io). All rights reserved.",license:"https://github.com/zloirock/core-js/blob/v3.50.0/LICENSE",source:"https://github.com/zloirock/core-js"})}),Oe=o.cw(function(t,e){var n=xe(),r=Object.create||Object;t.exports=function(t,e){return n[t]||(n[t]=e||r(null))}}),Ee=o.cw(function(t,n){var r=u(),o=e(),i=Pt(),a=ze()("species");t.exports=function(t,e){var n,u=r(t).constructor;return void 0===u||i(n=r(u)[a])?e:o(n)}}),Se=o.cw(function(t,e){var n=it(),r=Te(),o=Fe(),i=ge(),a=n("".charAt),u=n("".charCodeAt),s=n("".slice),c=function(t){return function(e,n){var c,l,f=o(i(e)),d=r(n),p=f.length;return d<0||d>=p?t?"":void 0:(c=u(f,d))<55296||c>56319||d+1===p||(l=u(f,d+1))<56320||l>57343?t?a(f,d):c:t?s(f,d,d+2):l-56320+(c-55296<<10)+65536}};t.exports={codeAt:c(!1),o:c(!0)}}),ke=o.cw(function(t,e){var n=nt().PROPER,r=q(),o=Ye();t.exports=function(t){return r(function(){return!!o[t]()||"​᠎"!=="​᠎"[t]()||n&&o[t].name!==t})}}),Pe=o.cw(function(t,e){var n=it(),r=ge(),o=Fe(),i=Ye(),a=n("".replace),u=RegExp("^["+i+"]+"),s=RegExp("(^|[^"+i+"])["+i+"]+$"),c=function(t){return function(e){var n=o(r(e));return 1&t&&(n=a(n,u,"")),2&t&&(n=a(n,s,"$1")),n}};t.exports={start:c(1),end:c(2),Bq:c(3)}}),Ie=o.cw(function(t,e){var n=G(),r=q(),o=ft().String;t.exports=!!Object.getOwnPropertySymbols&&!r(function(){var t=Symbol("symbol detection");return!o(t)||!(Object(t)instanceof Symbol)||!Symbol.sham&&n&&n<41})}),Ce=o.cw(function(t,e){var n=et(),r=at(),o=ze(),i=T();t.exports=function(){var t=r("Symbol"),e=t&&t.prototype,a=e&&e.valueOf,u=o("toPrimitive");e&&!e[u]&&i(e,u,function(t){return n(a,this)},{arity:1})}}),Ae=o.cw(function(t,e){var n=Ie();t.exports=n&&!!Symbol.for&&!!Symbol.keyFor}),Me=o.cw(function(t,e){var n=it();t.exports=n(1.1.valueOf)}),Ne=o.cw(function(t,e){var n=Te(),r=Math.max,o=Math.min;t.exports=function(t,e){var i=n(t);return i<0?r(i+e,0):o(i,e)}}),De=o.cw(function(t,e){var n=yt(),r=ge();t.exports=function(t){return n(r(t))}}),Te=o.cw(function(t,e){var n=o(741);t.exports=function(t){var e=+t;return e!=e||0===e?0:n(e)}}),je=o.cw(function(t,e){var n=Te(),r=Math.min;t.exports=function(t){var e=n(t);return e>0?r(e,9007199254740991):0}}),Re=o.cw(function(t,e){var n=ge(),r=Object;t.exports=function(t){return r(n(t))}}),Le=o.cw(function(t,e){var n=et(),r=It(),o=Dt(),i=ct(),a=oe(),u=ze(),s=TypeError,c=u("toPrimitive");t.exports=function(t,e){if(!r(t)||o(t))return t;var u,l=i(t,c);if(l){if(void 0===e&&(e="default"),u=n(l,t,e),!r(u)||o(u))return u;throw new s("Can't convert object to primitive value")}return void 0===e&&(e="number"),a(t,e)}}),Be=o.cw(function(t,e){var n=Le(),r=Dt();t.exports=function(t){var e=n(t,"string");return r(e)?e:e+""}}),Ke=o.cw(function(t,e){var n={};n[ze()("toStringTag")]="z",t.exports="[object z]"===String(n)}),Fe=o.cw(function(t,e){var n=E(),r=String;t.exports=function(t){if("Symbol"===n(t))throw new TypeError("Cannot convert a Symbol value to a string");return r(t)}}),_e=function(){return o(823)},Ue=o.cw(function(t,e){var n=it(),r=0,o=Math.random(),i=n(1.1.toString);t.exports=function(t){return"Symbol("+(void 0===t?"":t)+")_"+i(++r+o,36)}}),He=o.cw(function(t,e){var n=Ie();t.exports=n&&!Symbol.sham&&"symbol"==typeof Symbol.iterator}),$e=o.cw(function(t,e){var n=L(),r=q();t.exports=n&&r(function(){return 42!==Object.defineProperty(function(){},"prototype",{value:42,writable:!1}).prototype})}),Je=o.cw(function(t,e){var n=ft(),r=Ot(),o=n.WeakMap;t.exports=r(o)&&/native code/.test(String(o))}),Ge=o.cw(function(t,e){var n=ue(),r=dt(),o=Ve(),i=Gt().f;t.exports=function(t){var e=n.Symbol||(n.Symbol={});r(e,t)||i(e,t,{value:o.f(t)})}}),Ve=o.cw(function(t,e){var n=ze();e.f=n}),ze=o.cw(function(t,e){var n=ft(),r=Oe(),o=dt(),i=Ue(),a=Ie(),u=He(),s=n.Symbol,c=r("wks"),l=u?s.for||s:s&&s.withoutSetter||i;t.exports=function(t){return o(c,t)||(c[t]=a&&o(s,t)?s[t]:l("Symbol."+t)),c[t]}}),Ye=o.cw(function(t,e){t.exports="\t\n\v\f\r                　\u2028\u2029\ufeff"}),qe=o.cw(function(t,e){var n=Y(),r=q(),o=xt(),i=It(),a=Re(),u=Kt(),s=K(),c=M(),l=v(),f=b(),p=d(),h=ze(),y=G(),g=h("isConcatSpreadable"),m=y>=51||!r(function(){var t=[];return t[g]=!1,t.concat()[0]!==t}),w=function(t){if(!i(t))return!1;var e=t[g];return void 0!==e?!!e:o(t)};n({target:"Array",proto:!0,arity:1,forced:!m||!p("concat")},{concat:function(t){var e,n,r,o,i,d=a(this),p=f(d,0),h=0;for(e=-1,r=arguments.length;e<r;e++)if(w(i=-1===e?d:arguments[e]))for(o=u(i),s(h+o),n=0;n<o;n++,h++)n in i&&c(p,h,i[n]);else s(h+1),c(p,h++,i);return l(p,h),p}})}),We=o.cw(function(t,e){var n=Y(),r=f().pb;n({target:"Array",proto:!0,forced:!d()("filter")},{filter:function(t){return r(this,t,arguments.length>1?arguments[1]:void 0)}})}),Xe=o.cw(function(t,e){var n=Y(),r=c();n({target:"Array",stat:!0,forced:!x()(function(t){Array.from(t)})},{from:r})}),Qe=o.cw(function(t,e){var n=Y(),o=l().m,i=q(),a=r(),u=i(function(){return!Array(1).includes()}),s=i(function(){return[,1].includes(void 0,1)});n({target:"Array",proto:!0,forced:u||s},{includes:function(t){return o(this,t,arguments.length>1?arguments[1]:void 0)}}),a("includes")}),Ze=o.cw(function(t,e){var n=Y(),r=ot(),o=l().q,i=p(),a=r([].indexOf),u=!!a&&1/a([1],1,-0)<0;n({target:"Array",proto:!0,forced:u||!i("indexOf")},{indexOf:function(t){var e=arguments.length>1?arguments[1]:void 0;return u?a(this,t,e)||0:o(this,t,e)}})}),tn=o.cw(function(t,e){var n=De(),o=r(),i=Bt(),a=bt(),u=Gt().f,s=Rt(),c=I(),l=At(),f=L(),d="Array Iterator",p=a.set,h=a.getterFor(d);t.exports=s(Array,"Array",function(t,e){p(this,{type:d,target:n(t),index:0,kind:e})},function(){var t=h(this),e=t.target,n=t.index++;if(!e||n>=e.length)return t.target=null,c(void 0,!0);switch(t.kind){case"keys":return c(n,!1);case"values":return c(e[n],!1)}return c([n,e[n]],!1)},"values");var v=i.Arguments=i.Array;if(o("keys"),o("values"),o("entries"),!l&&f&&"values"!==v.name)try{u(v,"name",{value:"values"})}catch(t){}}),en=o.cw(function(t,e){var n=Y(),r=it(),o=yt(),i=De(),a=p(),u=r([].join);n({target:"Array",proto:!0,forced:o!==Object||!a("join",",")},{join:function(t){return u(i(this),void 0===t?",":t)}})}),nn=o.cw(function(t,e){var n=Y(),r=f().Tj;n({target:"Array",proto:!0,forced:!d()("map")},{map:function(t){return r(this,t,arguments.length>1?arguments[1]:void 0)}})}),rn=o.cw(function(t,e){var n=Y(),r=h().k,o=p(),i=G();n({target:"Array",proto:!0,forced:!$()&&i>79&&i<83||!o("reduce")},{reduce:function(t){var e=arguments.length;return r(this,t,e,e>1?arguments[1]:void 0)}})}),on=o.cw(function(t,e){var n=Y(),r=xt(),o=Et(),i=It(),a=Ne(),u=Kt(),s=De(),c=M(),l=v(),f=ze(),p=d(),h=y(),g=p("slice"),m=f("species"),b=Array,w=Math.max;n({target:"Array",proto:!0,forced:!g},{slice:function(t,e){var n,f,d,p=s(this),v=u(p),y=a(t,v),g=a(void 0===e?v:e,v);if(r(p)&&(n=p.constructor,(o(n)&&(n===b||r(n.prototype))||i(n)&&null===(n=n[m]))&&(n=void 0),n===b||void 0===n))return h(p,y,g);for(f=new(void 0===n?b:n)(w(g-y,0)),d=0;y<g;y++,d++)y in p&&c(f,d,p[y]);return l(f,d),f}})}),an=o.cw(function(e,n){var r=Y(),o=it(),i=t(),a=Re(),u=Kt(),s=R(),c=Fe(),l=q(),f=g(),d=p(),h=U(),v=H(),y=G(),m=V(),b=[],w=o(b.sort),x=o(b.push),O=l(function(){b.sort(void 0)}),E=l(function(){b.sort(null)}),S=d("sort"),k=!l(function(){if(y)return y<70;if(!(h&&h>3)){if(v)return!0;if(m)return m<603;var t,e,n,r,o="";for(t=65;t<76;t++){switch(e=String.fromCharCode(t),t){case 66:case 69:case 70:case 72:n=3;break;case 68:case 71:n=4;break;default:n=2}for(r=0;r<47;r++)b.push({k:e+r,v:n})}for(b.sort(function(t,e){return e.v-t.v}),r=0;r<b.length;r++)e=b[r].k.charAt(0),o.charAt(o.length-1)!==e&&(o+=e);return"DGBEFHACIJK"!==o}});r({target:"Array",proto:!0,forced:O||!E||!S||!k},{sort:function(t){void 0!==t&&i(t);var e=a(this);if(k)return void 0===t?w(e):w(e,t);var n,r,o=[],l=u(e);for(r=0;r<l;r++)r in e&&x(o,e[r]);for(f(o,function(t){return function(e,n){if(void 0===n)return-1;if(void 0===e)return 1;if(void 0!==t)return+t(e,n)||0;var r=c(e),o=c(n);return r===o?0:r>o?1:-1}}(t)),n=u(o),r=0;r<n;)e[r]=o[r++];for(;r<l;)s(e,r++);return e}})}),un=o.cw(function(t,e){var n=Y(),r=Re(),o=Ne(),i=Te(),a=Kt(),u=v(),s=K(),c=b(),l=M(),f=R(),p=d()("splice"),h=Math.max,y=Math.min;n({target:"Array",proto:!0,forced:!p},{splice:function(t,e){var n,d,p,v,g,m,b=r(this),w=a(b),x=o(t,w),O=arguments.length;for(0===O?n=d=0:1===O?(n=0,d=w-x):(n=O-2,d=y(h(i(e),0),w-x)),s(w+n-d),p=c(b,d),v=0;v<d;v++)(g=x+v)in b&&l(p,v,b[g]);if(u(p,d),n<d){for(v=x;v<w-d;v++)m=v+n,(g=v+d)in b?b[m]=b[g]:f(b,m);for(v=w;v>w-d+n;v--)f(b,v-1)}else if(n>d)for(v=w-d;v>x;v--)m=v+n-1,(g=v+d-1)in b?b[m]=b[g]:f(b,m);for(v=0;v<n;v++)b[v+x]=arguments[v+2];return u(b,w-d+n),p}})}),sn=o.cw(function(t,e){var n=Y(),r=q(),o=Re(),i=Le();n({target:"Date",proto:!0,forced:r(function(){return null!==new Date(NaN).toJSON()||1!==Date.prototype.toJSON.call({toISOString:function(){return 1}})})},{toJSON:function(t){var e=o(this),n=i(e,"number");return"number"!=typeof n||isFinite(n)?e.toISOString():null}})}),cn=o.cw(function(t,e){var n=dt(),r=T(),o=N(),i=ze()("toPrimitive"),a=Date.prototype;n(a,i)||r(a,i,o)}),ln=o.cw(function(t,e){var n=L(),r=nt().EXISTS,o=it(),i=D(),a=Function.prototype,u=o(a.toString),s=/function\b(?:\s|\/\*[\S\s]*?\*\/|\/\/[^\n\r]*[\n\r]+)*([^\s(/]*)/,c=o(s.exec);n&&!r&&i(a,"name",{configurable:!0,get:function(){try{return c(s,u(this))[1]}catch(t){return""}}})}),fn=o.cw(function(t,e){var n=Y(),r=at(),o=et(),i=it(),a=q(),u=xt(),s=Ot(),c=It(),f=$t(),d=Mt(),p=Dt(),h=O(),v=Me(),y=l().m,g=dt(),m=Fe(),b=ae(),w=Ue(),x=Ie(),E=_t(),S=String,k=TypeError,P=r("JSON","stringify"),I=r("BigInt"),C=i("".valueOf),A=i((!0).valueOf),M=I&&i(I.prototype.valueOf),N=i(/./.exec),D=i("".charAt),T=i("".charCodeAt),j=i("".replace),R=i("".slice),L=i([].push),B=i([].pop),K=i(1.1.toString),F=/[\uD800-\uDFFF]/g,_=/^[\uD800-\uDBFF]$/,U=/^[\uDC00-\uDFFF]$/,H=/^\d+$/,$=w(),J=w(),G=w(),V=$.length,z=J.length,W=!x||a(function(){var t=r("Symbol")("stringify detection");return"[null]"!==P([t])||"{}"!==P({a:t})||"{}"!==P(Object(t))}),X=a(function(){return'"\\udf06\\ud834"'!==P("\udf06\ud834")||'"\\udead"'!==P("\udead")}),Q=E?r("JSON","isRawJSON"):d,Z=W?function(t,e,n){return P(t,function(t,n){var r=o(e,this,t,n);if(!p(r))return r},n)}:P,tt=function(t,e,n){var r=D(n,e-1),o=D(n,e+1);return N(_,t)&&!N(U,o)||N(U,t)&&!N(_,r)?"\\u"+K(T(t,0),16):t},nt=function(t,e){try{return t(e),!0}catch(t){return!1}},rt=function(t){if(!c(t)||s(t)||u(t))return!1;try{return!function(t){var e=h(t);return"Number"===e&&nt(v,t)||"String"===e&&nt(C,t)||"Boolean"===e&&nt(A,t)||!!M&&"BigInt"===e&&nt(M,t)}(t)}catch(t){return!0}},ot=function(t,e){return{toJSON:function(){var n=t[e];if(c(n)||"bigint"==typeof n){var r=n.toJSON;s(r)&&(n=o(r,n,e))}return n}}};P&&n({target:"JSON",stat:!0,arity:3,forced:W||X||!E},{stringify:function(t,e,n){var r,i=s(e)?e:void 0,a=i?void 0:function(t){if(u(t)){for(var e=t.length,n=[],r=f(null),o=0;o<e;o++){var i,a=t[o];if("string"==typeof a)i=a;else{if("number"!=typeof a&&"Number"!==h(a)&&"String"!==h(a))continue;i=m(a)}g(r,i)||(r[i]=!0,L(n,i))}return n}}(e),c=a&&function(t){for(var e=0,n=t.length;e<n;e++)if(N(H,t[e]))return J;return""}(a),l=[],d=[],p=[],v=!1,w=!0,x=Z(t,function(t,e){if(t=S(t),a){if(t===G)return B(d),void(r=B(p));if(w)w=!1;else if(this!==r&&!u(this)&&!y(a,t))return}else i&&(e=o(i,this,t,e));if(Q(e))return E?e:(v=!0,$+(L(l,e.rawJSON)-1));if(a&&rt(e)){if(y(d,e))throw new k("Converting circular structure to JSON");var n=function(t,e,n){for(var r=f(null),o=0,i=e.length;o<i;o++){var a=e[o];r[n+a]=ot(t,a)}return r[G]=null,r}(e,a,c);return L(d,e),L(p,r),r=n,c&&(v=!0),n}return e},n);if("string"!=typeof x)return x;if(X&&(x=j(x,F,tt)),!v)return x;for(var O="",P=x.length,I=0;I<P;I++){var C=D(x,I);if('"'===C){var A=b(x,++I).end-1,M=R(x,I,A);R(M,0,V)===$?O+=l[R(M,V)]:R(M,0,z)===J?O+='"'+R(M,z)+'"':O+='"'+M+'"',I=A}else O+=C}return O}})}),dn=o.cw(function(t,e){var n=Y(),r=At(),o=L(),i=ft(),a=ue(),u=it(),s=St(),c=dt(),l=gt(),f=Xt(),d=Dt(),p=Le(),h=q(),v=Yt().f,y=Vt().f,g=Gt().f,m=Me(),b=Pe().Bq,w="Number",x=i[w],O=a[w],E=x.prototype,S=i.TypeError,k=u("".slice),P=u("".charCodeAt),I=function(t){var e,n,r,o,i,a,u,s,c=p(t,"number");if(d(c))throw new S("Cannot convert a Symbol value to a number");if("string"==typeof c&&c.length>2)if(c=b(c),43===(e=P(c,0))||45===e){if(88===(n=P(c,2))||120===n)return NaN}else if(48===e){switch(P(c,1)){case 66:case 98:r=2,o=49;break;case 79:case 111:r=8,o=55;break;default:return+c}for(a=(i=k(c,2)).length,u=0;u<a;u++)if((s=P(i,u))<48||s>o)return NaN;return parseInt(i,r)}return+c},C=s(w,!x(" 0o1")||!x("0b1")||x("+0x1")),A=function(t){var e,n=arguments.length<1?0:x(function(t){var e=p(t,"number");return"bigint"==typeof e?e:I(e)}(t));return f(E,e=this)&&h(function(){m(e)})?l(Object(n),this,A):n};A.prototype=E,C&&!r&&(E.constructor=A),n({global:!0,constructor:!0,wrap:!0,forced:C},{Number:A});var M=function(t,e){for(var n,r=o?v(e):"MAX_VALUE,MIN_VALUE,NaN,NEGATIVE_INFINITY,POSITIVE_INFINITY,EPSILON,MAX_SAFE_INTEGER,MIN_SAFE_INTEGER,isFinite,isInteger,isNaN,isSafeInteger,parseFloat,parseInt,fromString,range".split(","),i=0;r.length>i;i++)c(e,n=r[i])&&!c(t,n)&&g(t,n,y(e,n))};r&&O&&M(a[w],O),(C||r)&&M(a[w],x)}),pn=o.cw(function(t,e){Y()({target:"Number",stat:!0},{isInteger:kt()})}),hn=o.cw(function(t,e){var n=Y(),r=Ht();n({target:"Object",stat:!0,arity:2,forced:Object.assign!==r},{assign:r})}),vn=o.cw(function(e,n){var r=Y(),o=L(),i=ee(),a=t(),u=Re(),s=Gt();o&&r({target:"Object",proto:!0,forced:i},{__defineGetter__:function(t,e){s.f(u(this),t,{get:a(e),enumerable:!0,configurable:!0})}})}),yn=o.cw(function(t,e){var n=Y(),r=q(),o=De(),i=Vt().f,a=L();n({target:"Object",stat:!0,forced:!a||r(function(){i(1)}),sham:!a},{getOwnPropertyDescriptor:function(t,e){return i(o(t),e)}})}),gn=o.cw(function(t,e){var n=Y(),r=L(),o=ie(),i=De(),a=Vt(),u=M();n({target:"Object",stat:!0,sham:!r},{getOwnPropertyDescriptors:function(t){for(var e,n,r=i(t),s=a.f,c=o(r),l={},f=0;c.length>f;)void 0!==(n=s(r,e=c[f++]))&&u(l,e,n);return l}})}),mn=o.cw(function(t,e){var n=Y(),r=q(),o=zt().f;n({target:"Object",stat:!0,forced:r(function(){return!Object.getOwnPropertyNames(1)})},{getOwnPropertyNames:o})}),bn=o.cw(function(t,e){var n=Y(),r=Ie(),o=q(),i=$n(),a=Re();n({target:"Object",stat:!0,forced:!r||o(function(){i.f(1)})},{getOwnPropertySymbols:function(t){var e=i.f;return e?e(a(t)):[]}})}),wn=o.cw(function(t,e){var n=Y(),r=Re(),o=Zt();n({target:"Object",stat:!0,forced:q()(function(){o(1)})},{keys:function(t){return o(r(t))}})}),xn=o.cw(function(t,e){var n=Ke(),r=T(),o=re();n||r(Object.prototype,"toString",o,{unsafe:!0})}),On=o.cw(function(t,n){var r=Y(),o=at(),i=X(),a=tt(),s=e(),c=u(),l=It(),f=$t(),d=q(),p=o("Reflect","construct"),h=Object.prototype,v=[].push,y=d(function(){function t(){}return!(p(function(){},[],t)instanceof t)}),g=!d(function(){p(function(){})}),m=y||g;r({target:"Reflect",stat:!0,forced:m,sham:m},{construct:function(t,e){s(t);var n=arguments.length<3?t:s(arguments[2]);if(c(e),g&&!y)return p(t,e,n);if(t===n){switch(e.length){case 0:return new t;case 1:return new t(e[0]);case 2:return new t(e[0],e[1]);case 3:return new t(e[0],e[1],e[2]);case 4:return new t(e[0],e[1],e[2],e[3])}var r=[null];return i(v,r,e),new(i(a,t,r))}var o=n.prototype,u=f(l(o)?o:h),d=i(t,u,e);return l(d)?d:u}})}),En=o.cw(function(t,e){var n=L(),r=ft(),o=it(),i=St(),a=gt(),u=C(),s=$t(),c=Yt().f,l=Xt(),f=Nt(),d=Fe(),p=pe(),h=he(),v=se(),y=T(),g=q(),m=dt(),b=bt().enforce,w=me(),x=ze(),O=ve(),E=ye(),S=x("match"),k=r.RegExp,P=k.prototype,I=r.SyntaxError,A=o(P.exec),M=o("".charAt),N=o("".replace),D=o("".indexOf),j=o("".slice),R=/^\?<[^\s\d!#%&*+<=>@^][^\s!#%&*+<=>@^]*>/,B=/a/g,K=/a/g,F=new k(B)!==B,_=h.MISSED_STICKY,U=h.UNSUPPORTED_Y,H=n&&(!F||_||O||E||g(function(){return K[S]=!1,k(B)!==B||k(K)===K||"/a/i"!==String(k(B,"i"))}));if(i("RegExp",H)){for(var $=function(t,e){var n,r,o,i,c,h,v=l(P,this),y=f(t),g=void 0===e,w=[],x=t;if(!v&&y&&g&&t.constructor===$)return t;if((y||l(P,t))&&(t=t.source,g&&(e=p(x))),t=void 0===t?"":d(t),e=void 0===e?"":d(e),x=t,O&&"dotAll"in B&&(r=!!e&&D(e,"s")>-1)&&(e=N(e,/s/g,"")),n=e,_&&"sticky"in B&&(o=!!e&&D(e,"y")>-1)&&U&&(e=N(e,/y/g,"")),E&&(i=function(t){for(var e,n=t.length,r=0,o="",i=[],a=s(null),u=!1,c=!1,l=0,f="";r<n;r++){if("\\"===(e=M(t,r))){if(e+=M(t,++r),!c&&"\\"===M(e,1)){o+="\\x5c";continue}}else if("]"===e)u=!1;else if(!u)switch(!0){case"["===e:u=!0;break;case"("===e:o+=e,A(R,j(t,r+1))?(r+=2,c=!0,l++):"?"!==M(t,r+1)&&l++;continue;case">"===e&&c:if(""===f||m(a,f))throw new I("Invalid capture group name");a[f]=!0,i[i.length]=[f,l],c=!1,f="";continue}c?f+=e:o+=e}for(var d=0;d<i.length;d++)for(var p="\\k<"+i[d][0]+">",h="\\"+i[d][1];D(o,p)>-1;)o=N(o,p,h);return[o,i]}(t),t=i[0],w=i[1]),c=a(k(t,e),v?this:P,$),(r||o||w.length)&&(h=b(c),r&&(h.dotAll=!0,h.raw=$(function(t){for(var e,n=t.length,r=0,o="",i=!1;r<n;r++)"\\"!==(e=M(t,r))?i||"."!==e?("["===e?i=!0:"]"===e&&(i=!1),o+=e):o+="[\\s\\S]":o+=e+M(t,++r);return o}(t),n)),o&&(h.sticky=!0),w.length&&(h.groups=w)),t!==x)try{u(c,"source",""===x?"(?:)":x)}catch(t){}return c},J=c(k),G=0;J.length>G;)v($,k,J[G++]);P.constructor=$,$.prototype=P,y(r,"RegExp",$,{constructor:!0})}w("RegExp")}),Sn=o.cw(function(t,e){var n=Y(),r=le();n({target:"RegExp",proto:!0,forced:/./.exec!==r},{exec:r})}),kn=o.cw(function(t,e){var n=nt().PROPER,r=T(),o=u(),i=Fe(),a=q(),s=pe(),c="toString",l=RegExp.prototype,f=l[c],d=a(function(){return"/a/b"!==f.call({source:"a",flags:"b"})}),p=n&&f.name!==c;(d||p)&&r(l,c,function(){var t=o(this);return"/"+i(t.source)+"/"+i(s(t))},{unsafe:!0})}),Pn=o.cw(function(t,e){var n=Y(),r=it(),o=Ut(),i=ge(),a=Fe(),u=k(),s=r("".indexOf);n({target:"String",proto:!0,forced:!u("includes")},{includes:function(t){return!!~s(a(i(this)),a(o(t)),arguments.length>1?arguments[1]:void 0)}})}),In=o.cw(function(t,e){var n=Se().o,r=Fe(),o=bt(),i=Rt(),a=I(),u="String Iterator",s=o.set,c=o.getterFor(u);i(String,"String",function(t){s(this,{type:u,string:r(t),index:0})},function(){var t,e=c(this),r=e.string,o=e.index;return o>=r.length?a(void 0,!0):(t=n(r,o),e.index+=t.length,a(t,!1))})}),Cn=o.cw(function(t,e){var n=Y(),r=et(),o=ot(),i=jt(),s=I(),c=ge(),l=je(),f=Fe(),d=u(),p=It(),h=O(),v=Nt(),y=pe(),g=ct(),m=T(),b=q(),w=ze(),x=Ee(),E=a(),S=ce(),k=bt(),P=At(),C=w("matchAll"),A="RegExp String",M=A+" Iterator",N=k.set,D=k.getterFor(M),j=RegExp.prototype,R=TypeError,L=o("".indexOf),B=o("".matchAll),K=!!B&&!b(function(){B("a",/./)}),F=i(function(t,e,n,r){N(this,{type:M,regexp:t,string:e,global:n,unicode:r,done:!1})},A,function(){var t=D(this);if(t.done)return s(void 0,!0);var e=t.regexp,n=t.string,r=S(e,n);return null===r?(t.done=!0,s(void 0,!0)):t.global?(""===f(r[0])&&(e.lastIndex=E(n,l(e.lastIndex),t.unicode)),s(r,!1)):(t.done=!0,s(r,!1))}),_=function(t){var e,n,r,o=d(this),i=f(t),a=x(o,RegExp),u=f(y(o));return e=new a(a===RegExp?o.source:o,u),n=!!~L(u,"g"),r=!!~L(u,"u")||!!~L(u,"v"),e.lastIndex=l(o.lastIndex),new F(e,i,n,r)};n({target:"String",proto:!0,forced:K},{matchAll:function(t){var e,n,o,i,a=c(this);if(p(t)){if(v(t)&&(e=f(c(y(t))),!~L(e,"g")))throw new R("`.matchAll` does not allow non-global regexes");if(K)return B(a,t);if(void 0===(o=g(t,C))&&P&&"RegExp"===h(t)&&(o=_),o)return r(o,t,a)}else if(K)return B(a,t);return n=f(a),i=new RegExp(t,"g"),P?r(_,i,n):i[C](n)}}),P||C in j||m(j,C,_)}),An=o.cw(function(t,e){var n=et(),r=it(),o=W(),i=u(),s=It(),c=je(),l=Fe(),f=ge(),d=ct(),p=a(),h=pe(),v=ce(),y=r("".indexOf);o("match",function(t,e,r){return[function(e){var r=f(this),o=s(e)?d(e,t):void 0;if(o)return n(o,e,r);var i=l(r);return new RegExp(e)[t](i)},function(t){var n=i(this),o=l(t),a=r(e,n,o);if(a.done)return a.value;var u=l(h(n));if(!~y(u,"g"))return v(n,o);var s=!!~y(u,"u")||!!~y(u,"v");n.lastIndex=0;for(var f,d=[],g=0;null!==(f=v(n,o));){var m=l(f[0]);d[g]=m,""===m&&(n.lastIndex=p(o,c(n.lastIndex),s)),g++}return 0===g?null:d}]})}),Mn=o.cw(function(t,e){var n=X(),r=et(),o=it(),i=W(),s=q(),c=u(),l=Ot(),f=It(),d=Te(),p=je(),h=Fe(),v=ge(),y=a(),g=ct(),m=lt(),b=pe(),w=ce(),x=ze()("replace"),O=Math.max,E=Math.min,S=o([].concat),k=o([].push),P=o("".indexOf),I=o("".slice),C=function(t){return void 0===t?t:String(t)},A="$0"==="a".replace(/./,"$0"),M=!!/./[x]&&""===/./[x]("a","$0");i("replace",function(t,e,o){var i=M?"$":"$0";return[function(t,n){var o=v(this),i=f(t)?g(t,x):void 0;return i?r(i,t,o,n):r(e,h(o),t,n)},function(t,r){var a=c(this),u=h(t),s=l(r);s||(r=h(r));var f=h(b(a));if("string"==typeof r&&!~P(r,i)&&!~P(r,"$<")&&!~P(f,"y")){var v=o(e,a,u,r);if(v.done)return v.value}var g,x=!!~P(f,"g");x&&(g=!!~P(f,"u")||!!~P(f,"v"),a.lastIndex=0);for(var A,M=[];null!==(A=w(a,u))&&(k(M,A),x);){""===h(A[0])&&(a.lastIndex=y(u,p(a.lastIndex),g))}for(var N="",D=0,T=0;T<M.length;T++){for(var j,R=h((A=M[T])[0]),L=O(E(d(A.index),u.length),0),B=[],K=1;K<A.length;K++)k(B,C(A[K]));var F=A.groups;if(s){var _=S([R],B,L,u);void 0!==F&&k(_,F),j=h(n(r,void 0,_))}else j=m(R,u,L,B,F,r);L>=D&&(N+=I(u,D,L)+j,D=L+R.length)}return N+I(u,D)}]},!!s(function(){var t=/./;return t.exec=function(){var t=[];return t.groups={a:"7"},t},"7"!=="".replace(t,"$<a>")})||!A||M)}),Nn=o.cw(function(t,e){var n=et(),r=it(),o=W(),i=u(),s=It(),c=ge(),l=Ee(),f=a(),d=je(),p=Fe(),h=ct(),v=pe(),y=ce(),g=he(),m=q(),b=g.UNSUPPORTED_Y,w=Math.min,x=r([].push),O=r("".slice),E=r("".indexOf),S=!m(function(){var t=/(?:)/,e=t.exec;t.exec=function(){return e.apply(this,arguments)};var n="ab".split(t);return 2!==n.length||"a"!==n[0]||"b"!==n[1]}),k="c"==="abbc".split(/(b)*/)[1]||4!=="test".split(/(?:)/,-1).length||2!=="ab".split(/(?:ab)*/).length||4!==".".split(/(.?)(.?)/).length||".".split(/()()/).length>1||"".split(/.?/).length;o("split",function(t,e,r){var o="0".split(void 0,0).length?function(t,r){return void 0===t&&0===r?[]:n(e,this,t,r)}:e;return[function(e,r){var i=c(this),a=s(e)?h(e,t):void 0;return a?n(a,e,i,r):n(o,p(i),e,r)},function(t,n){var a=i(this),u=p(t);if(!k){var s=r(o,a,u,n,o!==e);if(s.done)return s.value}var c=l(a,RegExp),h=p(v(a)),g=!!~E(h,"u")||!!~E(h,"v");b?~E(h,"g")||(h+="g"):~E(h,"y")||(h+="y");var m=new c(b?"^(?:"+a.source+")":a,h),S=void 0===n?4294967295:n>>>0;if(0===S)return[];if(0===u.length)return null===y(m,u)?[u]:[];for(var P=0,I=0,C=[];I<u.length;){m.lastIndex=b?0:I;var A,M=y(m,b?O(u,I):u);if(null===M||(A=w(d(m.lastIndex+(b?I:0)),u.length))===P)I=f(u,I,g);else{if(x(C,O(u,P,I)),C.length===S)return C;for(var N=1;N<=M.length-1;N++)if(x(C,M[N]),C.length===S)return C;I=P=A}}return x(C,O(u,P)),C}]},k||!S,b)}),Dn=o.cw(function(t,e){var n=Y(),r=Pe().Bq;n({target:"String",proto:!0,forced:ke()("trim")},{trim:function(){return r(this)}})}),Tn=o.cw(function(t,e){var n=Y(),r=ft(),o=et(),i=it(),a=At(),s=L(),c=Ie(),l=q(),d=dt(),p=Xt(),h=u(),v=De(),y=Be(),g=Fe(),m=A(),b=$t(),w=Zt(),x=Yt(),O=zt(),E=$n(),S=Vt(),k=Gt(),P=Jt(),I=te(),C=T(),M=D(),N=Oe(),j=we(),R=pt(),B=Ue(),K=ze(),F=Ve(),_=Ge(),U=Ce(),H=be(),$=bt(),J=f().jJ,G=j("hidden"),V="Symbol",z="prototype",W=$.set,X=$.getterFor(V),Q=Object[z],Z=r.Symbol,tt=Z&&Z[z],nt=r.RangeError,rt=r.TypeError,ot=r.QObject,at=S.f,ut=k.f,st=O.f,ct=I.f,lt=i([].push),ht=N("symbols"),vt=N("op-symbols"),yt=N("wks"),gt=!ot||!ot[z]||!ot[z].findChild,mt=function(t,e,n){var r=at(Q,e);return r&&delete Q[e],ut(t,e,n),r&&t!==Q&&ut(Q,e,r),t},wt=s&&l(function(){return 7!==b(ut({},"a",{get:function(){return ut(this,"a",{value:7}).a}})).a})?mt:ut,xt=function(t,e){var n=ht[t]=b(tt);return W(n,{type:V,tag:t,description:e}),s||(n.description=e),n},Ot=function(t,e,n){t===Q&&Ot(vt,e,n),h(t);var r=y(e);return h(n),d(ht,r)?(("enumerable"in n?!n.enumerable:!d(t,r)||d(t,G)&&t[G][r])?(d(t,G)||ut(t,G,m(1,b(null))),t[G][r]=!0):(d(t,G)&&t[G][r]&&(t[G][r]=!1),n=b(n,{enumerable:m(0,!1)})),wt(t,r,n)):ut(t,r,n)},Et=function(t,e){h(t);var n=v(e),r=w(n).concat(It(n));return J(r,function(e){s&&!o(St,n,e)||Ot(t,e,n[e])}),t},St=function(t){var e=y(t),n=o(ct,this,e);return!(this===Q&&d(ht,e)&&!d(vt,e))&&(!(n||!d(this,e)||!d(ht,e)||d(this,G)&&this[G][e])||n)},kt=function(t,e){var n=v(t),r=y(e);if(n!==Q||!d(ht,r)||d(vt,r)){var o=at(n,r);return!o||!d(ht,r)||d(n,G)&&n[G][r]||(o.enumerable=!0),o}},Pt=function(t){var e=st(v(t)),n=[];return J(e,function(t){d(ht,t)||d(R,t)||lt(n,t)}),n},It=function(t){var e=t===Q,n=st(e?vt:v(t)),r=[];return J(n,function(t){!d(ht,t)||e&&!d(Q,t)||lt(r,ht[t])}),r};c||(Z=function(){if(p(tt,this))throw new rt("Symbol is not a constructor");var t=arguments.length&&void 0!==arguments[0]?g(arguments[0]):void 0,e=B(t),n=function(t){var i=void 0===this?r:this;i===Q&&o(n,vt,t),d(i,G)&&d(i[G],e)&&(i[G][e]=!1);var a=m(1,t);try{wt(i,e,a)}catch(t){if(!(t instanceof nt))throw t;mt(i,e,a)}};return s&&gt&&wt(Q,e,{configurable:!0,set:n}),xt(e,t)},C(tt=Z[z],"toString",function(){return X(this).tag}),C(Z,"withoutSetter",function(t){return xt(B(t),t)}),I.f=St,k.f=Ot,P.f=Et,S.f=kt,x.f=O.f=Pt,E.f=It,F.f=function(t){return xt(K(t),t)},s&&(M(tt,"description",{configurable:!0,get:function(){return X(this).description}}),a||C(Q,"propertyIsEnumerable",St,{unsafe:!0}))),n({global:!0,constructor:!0,wrap:!0,forced:!c,sham:!c},{Symbol:Z}),J(w(yt),function(t){_(t)}),n({target:V,stat:!0,forced:!c},{useSetter:function(){gt=!0},useSimple:function(){gt=!1}}),n({target:"Object",stat:!0,forced:!c,sham:!s},{create:function(t,e){return void 0===e?b(t):Et(b(t),e)},defineProperty:Ot,defineProperties:Et,getOwnPropertyDescriptor:kt}),n({target:"Object",stat:!0,forced:!c},{getOwnPropertyNames:Pt}),U(),H(Z,V),R[G]=!0}),jn=o.cw(function(t,e){var n=Y(),r=L(),o=ft(),i=et(),a=it(),u=dt(),s=Ot(),c=Xt(),l=Fe(),f=D(),d=S(),p=o.Symbol,h=p&&p.prototype;if(r&&s(p)&&(!("description"in h)||void 0!==p().description)){var v={},y=function(){var t=arguments.length<1||void 0===arguments[0]?void 0:l(arguments[0]),e=c(h,this)?new p(t):void 0===t?p():p(t);return""===t&&(v[e]=!0),e};d(y,p);var g=y.for;y.for={for:function(t){var e=l(t),n=i(g,this,e);return""===e&&(v[n]=!0),n}}.for,y.prototype=h,h.constructor=y;var m="Symbol(description detection)"===String(p("description detection")),b=a(h.valueOf),w=a(h.toString),x=/^Symbol\((.*)\)[^)]+$/,O=a("".replace),E=a("".slice);f(h,"description",{configurable:!0,get:function(){var t=b(this);if(u(v,t))return"";var e=w(t),n=m?E(e,7,-1):O(e,x,"$1");return""===n?void 0:n}}),n({global:!0,constructor:!0,forced:!0},{Symbol:y})}}),Rn=o.cw(function(t,e){var n=Y(),r=at(),o=dt(),i=Fe(),a=Oe(),u=Ae(),s=a("string-to-symbol-registry"),c=a("symbol-to-string-registry");n({target:"Symbol",stat:!0,forced:!u},{for:function(t){var e=i(t);if(o(s,e))return s[e];var n=r("Symbol")(e);return s[e]=n,c[n]=e,n}})}),Ln=o.cw(function(t,e){Ge()("iterator")}),Bn=o.cw(function(t,e){Tn(),Rn(),Kn(),fn(),bn()}),Kn=o.cw(function(t,e){var n=Y(),r=dt(),o=Dt(),i=_e(),a=Oe(),u=Ae(),s=a("symbol-to-string-registry");n({target:"Symbol",stat:!0,forced:!u},{keyFor:function(t){if(!o(t))throw new TypeError(i(t)+" is not a symbol");if(r(s,t))return s[t]}})}),Fn=o.cw(function(t,e){var n=Ge(),r=Ce();n("toPrimitive"),r()}),_n=o.cw(function(t,e){Cn()}),Un=o.cw(function(t,e){var n=ft(),r=Jn(),o=F(),i=s(),a=C(),u=function(t){if(t&&t.forEach!==i)try{a(t,"forEach",i)}catch(e){t.forEach=i}};for(var c in r)r[c]&&u(n[c]&&n[c].prototype);u(o)}),Hn=o.cw(function(t,e){var n=ft(),r=Jn(),o=F(),i=tn(),a=C(),u=be(),s=ze()("iterator"),c=i.values,l=function(t,e){if(t){if(t[s]!==c)try{a(t,s,c)}catch(e){t[s]=c}if(u(t,e,!0),r[e])for(var n in i)if(t[n]!==i[n])try{a(t,n,i[n])}catch(e){t[n]=i[n]}}};for(var f in r)l(n[f]&&n[f].prototype,f);l(o,"DOMTokenList")});function $n(){return $n.c||($n.c=o.t(qt(),2))}function Jn(){return Jn.c||(Jn.c=o.t(o(400),2))}Ze(),en(),on(),un(),ln(),vn(),xn(),Sn(),kn(),Mn(),Nn(),Dn(),"undefined"==typeof Element||"remove"in Element.prototype||(Element.prototype.remove=function(){this.parentNode&&this.parentNode.removeChild(this)}),"undefined"!=typeof self&&"document"in self&&((!("classList"in document.createElement("_"))||document.createElementNS&&!("classList"in document.createElementNS("http://www.w3.org/2000/svg","g")))&&function(t){if("Element"in t){var e="classList",n="prototype",r=t.Element[n],o=Object,i=String[n].trim||function(){return this.replace(/^\s+|\s+$/g,"")},a=Array[n].indexOf||function(t){for(var e=0,n=this.length;e<n;e++)if(e in this&&this[e]===t)return e;return-1},u=function(t,e){this.name=t,this.code=DOMException[t],this.message=e},s=function(t,e){if(""===e)throw new u("SYNTAX_ERR","The token must not be empty.");if(/\s/.test(e))throw new u("INVALID_CHARACTER_ERR","The token must not contain space characters.");return a.call(t,e)},c=function(t){for(var e=i.call(t.getAttribute("class")||""),n=e?e.split(/\s+/):[],r=0,o=n.length;r<o;r++)this.push(n[r]);this._updateClassName=function(){t.setAttribute("class",this.toString())}},l=c[n]=[],f=function(){return new c(this)};if(u[n]=Error[n],l.item=function(t){return this[t]||null},l.contains=function(t){return~s(this,t+"")},l.add=function(){var t,e=arguments,n=0,r=e.length,o=!1;do{~s(this,t=e[n]+"")||(this.push(t),o=!0)}while(++n<r);o&&this._updateClassName()},l.remove=function(){var t,e,n=arguments,r=0,o=n.length,i=!1;do{for(e=s(this,t=n[r]+"");~e;)this.splice(e,1),i=!0,e=s(this,t)}while(++r<o);i&&this._updateClassName()},l.toggle=function(t,e){var n=this.contains(t),r=n?!0!==e&&"remove":!1!==e&&"add";return r&&this[r](t),!0===e||!1===e?e:!n},l.replace=function(t,e){var n=s(t+"");~n&&(this.splice(n,1,e),this._updateClassName())},l.toString=function(){return this.join(" ")},o.defineProperty){var d={get:f,enumerable:!0,configurable:!0};try{o.defineProperty(r,e,d)}catch(t){void 0!==t.number&&-2146823252!==t.number||(d.enumerable=!1,o.defineProperty(r,e,d))}}else o[n].__defineGetter__&&r.__defineGetter__(e,f)}}(self),function(){var t=document.createElement("_");if(t.classList.add("c1","c2"),!t.classList.contains("c2")){var e=function(t){var e=DOMTokenList.prototype[t];DOMTokenList.prototype[t]=function(t){var n,r=arguments.length;for(n=0;n<r;n++)t=arguments[n],e.call(this,t)}};e("add"),e("remove")}if(t.classList.toggle("c3",!1),t.classList.contains("c3")){var n=DOMTokenList.prototype.toggle;DOMTokenList.prototype.toggle=function(t,e){return 1 in arguments&&!this.contains(t)==!e?e:n.call(this,t)}}"replace"in document.createElement("_").classList||(DOMTokenList.prototype.replace=function(t,e){var n=this.toString().split(" "),r=n.indexOf(t+"");~r&&(n=n.slice(r),this.remove.apply(this,n),this.add(e),this.add.apply(this,n.slice(1)))}),t=null}()),Bn(),jn(),Ln(),Fn(),qe(),We(),Xe(),Qe(),tn(),nn(),an(),sn(),cn(),dn(),hn(),yn(),gn(),wn(),En(),Pn(),In(),_n(),Un(),Hn();function Gn(t){return function(t){if(Array.isArray(t))return zn(t)}(t)||function(t){if("undefined"!=typeof Symbol&&null!=t[Symbol.iterator]||null!=t["@@iterator"])return Array.from(t)}(t)||Vn(t)||function(){throw new TypeError("Invalid attempt to spread non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.")}()}function Vn(t,e){if(t){if("string"==typeof t)return zn(t,e);var n={}.toString.call(t).slice(8,-1);return"Object"===n&&t.constructor&&(n=t.constructor.name),"Map"===n||"Set"===n?Array.from(t):"Arguments"===n||/^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n)?zn(t,e):void 0}}function zn(t,e){(null==e||e>t.length)&&(e=t.length);for(var n=0,r=Array(e);n<e;n++)r[n]=t[n];return r}function Yn(t){return Yn="function"==typeof Symbol&&"symbol"==typeof Symbol.iterator?function(t){return typeof t}:function(t){return t&&"function"==typeof Symbol&&t.constructor===Symbol&&t!==Symbol.prototype?"symbol":typeof t},Yn(t)}function qn(t,e){for(var n=0;n<e.length;n++){var r=e[n];r.enumerable=r.enumerable||!1,r.configurable=!0,"value"in r&&(r.writable=!0),Object.defineProperty(t,Xn(r.key),r)}}function Wn(t,e,n){return(e=Xn(e))in t?Object.defineProperty(t,e,{value:n,enumerable:!0,configurable:!0,writable:!0}):t[e]=n,t}function Xn(t){var e=function(t,e){if("object"!=Yn(t)||!t)return t;var n=t[Symbol.toPrimitive];if(void 0!==n){var r=n.call(t,e||"default");if("object"!=Yn(r))return r;throw new TypeError("@@toPrimitive must return a primitive value.")}return("string"===e?String:Number)(t)}(t,"string");return"symbol"==Yn(e)?e:e+""}rn(),pn(),mn(),On(),An();var Qn=function(){return t=function t(e){var n=e.getOptions,r=e.getCaretPosition,o=e.getCaretPositionEnd,i=e.dispatch;!function(t,e){if(!(t instanceof e))throw new TypeError("Cannot call a class as a function")}(this,t),Wn(this,"getOptions",void 0),Wn(this,"getCaretPosition",void 0),Wn(this,"getCaretPositionEnd",void 0),Wn(this,"dispatch",void 0),Wn(this,"maxLengthReached",void 0),Wn(this,"isStandardButton",function(t){return t&&!("{"===t[0]&&"}"===t[t.length-1])}),this.getOptions=n,this.getCaretPosition=r,this.getCaretPositionEnd=o,this.dispatch=i,t.bindMethods(t,this)},e=[{key:"getButtonType",value:function(t){return t.includes("{")&&t.includes("}")&&"{//}"!==t?"functionBtn":"standardBtn"}},{key:"getButtonClass",value:function(t){var e=this.getButtonType(t),n=t.replace("{","").replace("}",""),r="";return"standardBtn"!==e&&(r=" hg-button-".concat(n)),"hg-".concat(e).concat(r)}},{key:"getDefaultDiplay",value:function(){return{"{bksp}":"backspace","{backspace}":"backspace","{enter}":"< enter","{shift}":"shift","{shiftleft}":"shift","{shiftright}":"shift","{alt}":"alt","{s}":"shift","{tab}":"tab","{lock}":"caps","{capslock}":"caps","{accept}":"Submit","{space}":" ","{//}":" ","{esc}":"esc","{escape}":"esc","{f1}":"f1","{f2}":"f2","{f3}":"f3","{f4}":"f4","{f5}":"f5","{f6}":"f6","{f7}":"f7","{f8}":"f8","{f9}":"f9","{f10}":"f10","{f11}":"f11","{f12}":"f12","{numpaddivide}":"/","{numlock}":"lock","{arrowup}":"↑","{arrowleft}":"←","{arrowdown}":"↓","{arrowright}":"→","{prtscr}":"print","{scrolllock}":"scroll","{pause}":"pause","{insert}":"ins","{home}":"home","{pageup}":"up","{delete}":"del","{forwarddelete}":"del","{end}":"end","{pagedown}":"down","{numpadmultiply}":"*","{numpadsubtract}":"-","{numpadadd}":"+","{numpadenter}":"enter","{period}":".","{numpaddecimal}":".","{numpad0}":"0","{numpad1}":"1","{numpad2}":"2","{numpad3}":"3","{numpad4}":"4","{numpad5}":"5","{numpad6}":"6","{numpad7}":"7","{numpad8}":"8","{numpad9}":"9"}}},{key:"getButtonDisplayName",value:function(t,e){return(e=arguments.length>2&&void 0!==arguments[2]&&arguments[2]?Object.assign({},this.getDefaultDiplay(),e):e||this.getDefaultDiplay())[t]||t}},{key:"getUpdatedInput",value:function(t,e,n){var r=arguments.length>3&&void 0!==arguments[3]?arguments[3]:n,o=arguments.length>4&&void 0!==arguments[4]&&arguments[4],i=this.getOptions(),a=[n,r,o],u=e;return("{bksp}"===t||"{backspace}"===t)&&u.length>0?u=this.removeAt.apply(this,[u].concat(a)):("{delete}"===t||"{forwarddelete}"===t)&&u.length>0?u=this.removeForwardsAt.apply(this,[u].concat(a)):"{space}"===t?u=this.addStringAt.apply(this,[u," "].concat(a)):"{tab}"!==t||"boolean"==typeof i.tabCharOnTab&&!1===i.tabCharOnTab?"{enter}"!==t&&"{numpadenter}"!==t||!i.newLineOnEnter?t.includes("numpad")&&Number.isInteger(Number(t[t.length-2]))?u=this.addStringAt.apply(this,[u,t[t.length-2]].concat(a)):"{numpaddivide}"===t?u=this.addStringAt.apply(this,[u,"/"].concat(a)):"{numpadmultiply}"===t?u=this.addStringAt.apply(this,[u,"*"].concat(a)):"{numpadsubtract}"===t?u=this.addStringAt.apply(this,[u,"-"].concat(a)):"{numpadadd}"===t?u=this.addStringAt.apply(this,[u,"+"].concat(a)):"{numpaddecimal}"===t?u=this.addStringAt.apply(this,[u,"."].concat(a)):"{"===t||"}"===t?u=this.addStringAt.apply(this,[u,t].concat(a)):t.includes("{")||t.includes("}")||(u=this.addStringAt.apply(this,[u,t].concat(a))):u=this.addStringAt.apply(this,[u,"\n"].concat(a)):u=this.addStringAt.apply(this,[u,"\t"].concat(a)),i.debug&&console.log("Input will be: "+u),u}},{key:"updateCaretPos",value:function(t){var e=arguments.length>1&&void 0!==arguments[1]&&arguments[1],n=this.updateCaretPosAction(t,e);this.dispatch(function(t){t.setCaretPosition(n)})}},{key:"updateCaretPosAction",value:function(t){var e=arguments.length>1&&void 0!==arguments[1]&&arguments[1],n=this.getOptions(),r=this.getCaretPosition();return null!=r&&(e?r>0&&(r-=t):r+=t),n.debug&&console.log("Caret at:",r),r}},{key:"addStringAt",value:function(t,e){var n,r=arguments.length>2&&void 0!==arguments[2]?arguments[2]:t.length,o=arguments.length>3&&void 0!==arguments[3]?arguments[3]:t.length,i=arguments.length>4&&void 0!==arguments[4]&&arguments[4];return r||0===r?(n=[t.slice(0,r),e,t.slice(o)].join(""),this.isMaxLengthReached()||i&&this.updateCaretPos(e.length)):n=t+e,n}},{key:"removeAt",value:function(t){var e,n=arguments.length>1&&void 0!==arguments[1]?arguments[1]:t.length,r=arguments.length>2&&void 0!==arguments[2]?arguments[2]:t.length,o=arguments.length>3&&void 0!==arguments[3]&&arguments[3];if(0===n&&0===r)return t;if(n===r){var i=/([\uD800-\uDBFF][\uDC00-\uDFFF])/g;n&&n>=0?t.substring(n-2,n).match(i)?(e=t.substr(0,n-2)+t.substr(n),o&&this.updateCaretPos(2,!0)):(e=t.substr(0,n-1)+t.substr(n),o&&this.updateCaretPos(1,!0)):t.slice(-2).match(i)?(e=t.slice(0,-2),o&&this.updateCaretPos(2,!0)):(e=t.slice(0,-1),o&&this.updateCaretPos(1,!0))}else e=t.slice(0,n)+t.slice(r),o&&this.dispatch(function(t){t.setCaretPosition(n)});return e}},{key:"removeForwardsAt",value:function(t){var e,n=arguments.length>1&&void 0!==arguments[1]?arguments[1]:t.length,r=arguments.length>2&&void 0!==arguments[2]?arguments[2]:t.length,o=arguments.length>3&&void 0!==arguments[3]&&arguments[3];return null!=t&&t.length&&null!==n?(n===r?e=t.substring(n,n+2).match(/([\uD800-\uDBFF][\uDC00-\uDFFF])/g)?t.substr(0,n)+t.substr(n+2):t.substr(0,n)+t.substr(n+1):(e=t.slice(0,n)+t.slice(r),o&&this.dispatch(function(t){t.setCaretPosition(n)})),e):t}},{key:"handleMaxLength",value:function(t,e){var n=this.getOptions(),r=n.maxLength,o=t[n.inputName||"default"],i=e.length-1>=r;if(e.length<=o.length)return!1;if(Number.isInteger(r))return n.debug&&console.log("maxLength (num) reached:",i),i?(this.maxLengthReached=!0,!0):(this.maxLengthReached=!1,!1);if("object"===Yn(r)){var a=e.length-1>=r[n.inputName||"default"];return n.debug&&console.log("maxLength (obj) reached:",a),a?(this.maxLengthReached=!0,!0):(this.maxLengthReached=!1,!1)}}},{key:"isMaxLengthReached",value:function(){return Boolean(this.maxLengthReached)}},{key:"isTouchDevice",value:function(){return"ontouchstart"in window||navigator.maxTouchPoints}},{key:"pointerEventsSupported",value:function(){return!!window.PointerEvent}},{key:"camelCase",value:function(t){return t?t.toLowerCase().trim().split(/[.\-_\s]/g).reduce(function(t,e){return e.length?t+e[0].toUpperCase()+e.slice(1):t}):""}},{key:"chunkArray",value:function(t,e){return Gn(Array(Math.ceil(t.length/e))).map(function(n,r){return t.slice(e*r,e+e*r)})}},{key:"escapeRegex",value:function(t){return t.replace(/[-\/\\^$*+?.()|[\]{}]/g,"\\$&")}},{key:"getRtlOffset",value:function(t,e){var n=t,r=e.indexOf("‫");return r<t&&-1!=r&&n--,e.indexOf("‬")<t&&-1!=r&&n--,n<0?0:n}},{key:"isConstructor",value:function(t){try{Reflect.construct(String,[],t)}catch(t){return!1}return!0}}],n=[{key:"bindMethods",value:function(t,e){var n,r=function(t,e){var n="undefined"!=typeof Symbol&&t[Symbol.iterator]||t["@@iterator"];if(!n){if(Array.isArray(t)||(n=Vn(t))||e&&t&&"number"==typeof t.length){n&&(t=n);var r=0,o=function(){};return{s:o,n:function(){return r>=t.length?{done:!0}:{done:!1,value:t[r++]}},e:function(t){throw t},f:o}}throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.")}var i,a=!0,u=!1;return{s:function(){n=n.call(t)},n:function(){var t=n.next();return a=t.done,t},e:function(t){u=!0,i=t},f:function(){try{a||null==n.return||n.return()}finally{if(u)throw i}}}}(Object.getOwnPropertyNames(t.prototype));try{for(r.s();!(n=r.n()).done;){var o=n.value;"constructor"===o||"bindMethods"===o||(e[o]=e[o].bind(e))}}catch(t){r.e(t)}finally{r.f()}}}],e&&qn(t.prototype,e),n&&qn(t,n),Object.defineProperty(t,"prototype",{writable:!1}),t;var t,e,n}();Wn(Qn,"noop",function(){});var Zn=Qn;function tr(t){return tr="function"==typeof Symbol&&"symbol"==typeof Symbol.iterator?function(t){return typeof t}:function(t){return t&&"function"==typeof Symbol&&t.constructor===Symbol&&t!==Symbol.prototype?"symbol":typeof t},tr(t)}function er(t,e){for(var n=0;n<e.length;n++){var r=e[n];r.enumerable=r.enumerable||!1,r.configurable=!0,"value"in r&&(r.writable=!0),Object.defineProperty(t,rr(r.key),r)}}function nr(t,e,n){return(e=rr(e))in t?Object.defineProperty(t,e,{value:n,enumerable:!0,configurable:!0,writable:!0}):t[e]=n,t}function rr(t){var e=function(t,e){if("object"!=tr(t)||!t)return t;var n=t[Symbol.toPrimitive];if(void 0!==n){var r=n.call(t,e||"default");if("object"!=tr(r))return r;throw new TypeError("@@toPrimitive must return a primitive value.")}return("string"===e?String:Number)(t)}(t,"string");return"symbol"==tr(e)?e:e+""}var or=function(){return t=function t(e){var n=this,r=e.dispatch,o=e.getOptions;!function(t,e){if(!(t instanceof e))throw new TypeError("Cannot call a class as a function")}(this,t),nr(this,"getOptions",void 0),nr(this,"dispatch",void 0),nr(this,"isModifierKey",function(t){return t.altKey||t.ctrlKey||t.shiftKey||["Tab","CapsLock","Esc","ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(t.code||t.key||n.keyCodeToKey(null==t?void 0:t.keyCode))}),this.dispatch=r,this.getOptions=o,Zn.bindMethods(t,this)},e=[{key:"handleHighlightKeyDown",value:function(t){var e=this.getOptions();e.physicalKeyboardHighlightPreventDefault&&this.isModifierKey(t)&&(t.preventDefault(),t.stopImmediatePropagation());var n=this.getSimpleKeyboardLayoutKey(t);this.dispatch(function(r){var o,i,a=r.getButtonElement(n),u=r.getButtonElement("{".concat(n,"}"));if(a)o=a,i=n;else{if(!u)return;o=u,i="{".concat(n,"}")}var s,c,l,f,d=function(t){t.style.background=e.physicalKeyboardHighlightBgColor||"#dadce4",t.style.color=e.physicalKeyboardHighlightTextColor||"black"};if(o)if(Array.isArray(o)){if(o.forEach(function(t){return d(t)}),e.physicalKeyboardHighlightPress)if(e.physicalKeyboardHighlightPressUsePointerEvents)null===(s=o[0])||void 0===s||null===(c=s.onpointerdown)||void 0===c||c.call(s,t);else if(e.physicalKeyboardHighlightPressUseClick){var p;null===(p=o[0])||void 0===p||p.click()}else r.handleButtonClicked(i,t)}else d(o),e.physicalKeyboardHighlightPress&&(e.physicalKeyboardHighlightPressUsePointerEvents?null===(l=o)||void 0===l||null===(f=l.onpointerdown)||void 0===f||f.call(l,t):e.physicalKeyboardHighlightPressUseClick?o.click():r.handleButtonClicked(i,t))})}},{key:"handleHighlightKeyUp",value:function(t){var e=this.getOptions();e.physicalKeyboardHighlightPreventDefault&&this.isModifierKey(t)&&(t.preventDefault(),t.stopImmediatePropagation());var n=this.getSimpleKeyboardLayoutKey(t);this.dispatch(function(r){var o,i,a,u=r.getButtonElement(n)||r.getButtonElement("{".concat(n,"}")),s=function(t){t.removeAttribute&&t.removeAttribute("style")};u&&(Array.isArray(u)?(u.forEach(function(t){return s(t)}),e.physicalKeyboardHighlightPressUsePointerEvents&&(null===(o=u[0])||void 0===o||null===(i=o.onpointerup)||void 0===i||i.call(o,t))):(s(u),e.physicalKeyboardHighlightPressUsePointerEvents&&(null==u||null===(a=u.onpointerup)||void 0===a||a.call(u,t))))})}},{key:"getSimpleKeyboardLayoutKey",value:function(t){var e,n="",r=t.code||t.key||this.keyCodeToKey(null==t?void 0:t.keyCode);return(n=null!=r&&r.includes("Numpad")||null!=r&&r.includes("Shift")||null!=r&&r.includes("Space")||null!=r&&r.includes("Backspace")||null!=r&&r.includes("Control")||null!=r&&r.includes("Alt")||null!=r&&r.includes("Meta")?t.code||"":t.key||this.keyCodeToKey(null==t?void 0:t.keyCode)||"").length>1?null===(e=n)||void 0===e?void 0:e.toLowerCase():n}},{key:"keyCodeToKey",value:function(t){return{8:"Backspace",9:"Tab",13:"Enter",16:"Shift",17:"Ctrl",18:"Alt",19:"Pause",20:"CapsLock",27:"Esc",32:"Space",33:"PageUp",34:"PageDown",35:"End",36:"Home",37:"ArrowLeft",38:"ArrowUp",39:"ArrowRight",40:"ArrowDown",45:"Insert",46:"Delete",48:"0",49:"1",50:"2",51:"3",52:"4",53:"5",54:"6",55:"7",56:"8",57:"9",65:"A",66:"B",67:"C",68:"D",69:"E",70:"F",71:"G",72:"H",73:"I",74:"J",75:"K",76:"L",77:"M",78:"N",79:"O",80:"P",81:"Q",82:"R",83:"S",84:"T",85:"U",86:"V",87:"W",88:"X",89:"Y",90:"Z",91:"Meta",96:"Numpad0",97:"Numpad1",98:"Numpad2",99:"Numpad3",100:"Numpad4",101:"Numpad5",102:"Numpad6",103:"Numpad7",104:"Numpad8",105:"Numpad9",106:"NumpadMultiply",107:"NumpadAdd",109:"NumpadSubtract",110:"NumpadDecimal",111:"NumpadDivide",112:"F1",113:"F2",114:"F3",115:"F4",116:"F5",117:"F6",118:"F7",119:"F8",120:"F9",121:"F10",122:"F11",123:"F12",144:"NumLock",145:"ScrollLock",186:";",187:"=",188:",",189:"-",190:".",191:"/",192:"`",219:"[",220:"\\",221:"]",222:"'"}[t]||""}}],e&&er(t.prototype,e),n&&er(t,n),Object.defineProperty(t,"prototype",{writable:!1}),t;var t,e,n}();function ir(t){return ir="function"==typeof Symbol&&"symbol"==typeof Symbol.iterator?function(t){return typeof t}:function(t){return t&&"function"==typeof Symbol&&t.constructor===Symbol&&t!==Symbol.prototype?"symbol":typeof t},ir(t)}function ar(t,e){for(var n=0;n<e.length;n++){var r=e[n];r.enumerable=r.enumerable||!1,r.configurable=!0,"value"in r&&(r.writable=!0),Object.defineProperty(t,sr(r.key),r)}}function ur(t,e,n){return(e=sr(e))in t?Object.defineProperty(t,e,{value:n,enumerable:!0,configurable:!0,writable:!0}):t[e]=n,t}function sr(t){var e=function(t,e){if("object"!=ir(t)||!t)return t;var n=t[Symbol.toPrimitive];if(void 0!==n){var r=n.call(t,e||"default");if("object"!=ir(r))return r;throw new TypeError("@@toPrimitive must return a primitive value.")}return("string"===e?String:Number)(t)}(t,"string");return"symbol"==ir(e)?e:e+""}var cr=function(){return t=function t(e){var n=e.utilities,r=e.options;!function(t,e){if(!(t instanceof e))throw new TypeError("Cannot call a class as a function")}(this,t),ur(this,"utilities",void 0),ur(this,"options",void 0),ur(this,"candidateBoxElement",void 0),ur(this,"pageIndex",0),ur(this,"pageSize",void 0),this.utilities=n,this.options=r,Zn.bindMethods(t,this),this.pageSize=this.utilities.getOptions().layoutCandidatesPageSize||5},e=[{key:"destroy",value:function(){this.candidateBoxElement&&(this.candidateBoxElement.remove(),this.pageIndex=0)}},{key:"show",value:function(t){var e=this,n=t.candidateValue,r=t.targetElement,o=t.onSelect;if(n&&n.length){var i=this.utilities.chunkArray(n.split(" "),this.pageSize);this.renderPage({candidateListPages:i,targetElement:r,pageIndex:this.pageIndex,nbPages:i.length,onItemSelected:function(t,n){o(t,n),e.destroy()}})}}},{key:"renderPage",value:function(t){var e,n=this,r=t.candidateListPages,o=t.targetElement,i=t.pageIndex,a=t.nbPages,u=t.onItemSelected;null===(e=this.candidateBoxElement)||void 0===e||e.remove(),this.candidateBoxElement=document.createElement("div"),this.candidateBoxElement.className="hg-candidate-box";var s=document.createElement("ul");s.className="hg-candidate-box-list",r[i].forEach(function(t){var e,r=document.createElement("li"),o=function(){var t=new(n.options.useTouchEvents?TouchEvent:MouseEvent)("click");return Object.defineProperty(t,"target",{value:r}),t};r.className="hg-candidate-box-list-item",r.innerHTML=(null===(e=n.options.display)||void 0===e?void 0:e[t])||t,n.options.useTouchEvents?r.ontouchstart=function(e){return u(t,e||o())}:r.onclick=function(){var e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:o();return u(t,e)},s.appendChild(r)});var c=i>0,l=document.createElement("div");l.classList.add("hg-candidate-box-prev"),c&&l.classList.add("hg-candidate-box-btn-active");var f=function(){c&&n.renderPage({candidateListPages:r,targetElement:o,pageIndex:i-1,nbPages:a,onItemSelected:u})};this.options.useTouchEvents?l.ontouchstart=f:l.onclick=f,this.candidateBoxElement.appendChild(l),this.candidateBoxElement.appendChild(s);var d=i<a-1,p=document.createElement("div");p.classList.add("hg-candidate-box-next"),d&&p.classList.add("hg-candidate-box-btn-active");var h=function(){d&&n.renderPage({candidateListPages:r,targetElement:o,pageIndex:i+1,nbPages:a,onItemSelected:u})};this.options.useTouchEvents?p.ontouchstart=h:p.onclick=h,this.candidateBoxElement.appendChild(p),o.prepend(this.candidateBoxElement)}}],e&&ar(t.prototype,e),n&&ar(t,n),Object.defineProperty(t,"prototype",{writable:!1}),t;var t,e,n}(),lr=cr;function fr(t){return function(t){if(Array.isArray(t))return dr(t)}(t)||function(t){if("undefined"!=typeof Symbol&&null!=t[Symbol.iterator]||null!=t["@@iterator"])return Array.from(t)}(t)||function(t,e){if(t){if("string"==typeof t)return dr(t,e);var n={}.toString.call(t).slice(8,-1);return"Object"===n&&t.constructor&&(n=t.constructor.name),"Map"===n||"Set"===n?Array.from(t):"Arguments"===n||/^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n)?dr(t,e):void 0}}(t)||function(){throw new TypeError("Invalid attempt to spread non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.")}()}function dr(t,e){(null==e||e>t.length)&&(e=t.length);for(var n=0,r=Array(e);n<e;n++)r[n]=t[n];return r}function pr(t){return pr="function"==typeof Symbol&&"symbol"==typeof Symbol.iterator?function(t){return typeof t}:function(t){return t&&"function"==typeof Symbol&&t.constructor===Symbol&&t!==Symbol.prototype?"symbol":typeof t},pr(t)}function hr(t,e){var n=Object.keys(t);if(Object.getOwnPropertySymbols){var r=Object.getOwnPropertySymbols(t);e&&(r=r.filter(function(e){return Object.getOwnPropertyDescriptor(t,e).enumerable})),n.push.apply(n,r)}return n}function vr(t,e){for(var n=0;n<e.length;n++){var r=e[n];r.enumerable=r.enumerable||!1,r.configurable=!0,"value"in r&&(r.writable=!0),Object.defineProperty(t,gr(r.key),r)}}function yr(t,e,n){return(e=gr(e))in t?Object.defineProperty(t,e,{value:n,enumerable:!0,configurable:!0,writable:!0}):t[e]=n,t}function gr(t){var e=function(t,e){if("object"!=pr(t)||!t)return t;var n=t[Symbol.toPrimitive];if(void 0!==n){var r=n.call(t,e||"default");if("object"!=pr(r))return r;throw new TypeError("@@toPrimitive must return a primitive value.")}return("string"===e?String:Number)(t)}(t,"string");return"symbol"==pr(e)?e:e+""}var mr=function(){return t=function t(e,n){var r=this;if(function(t,e){if(!(t instanceof e))throw new TypeError("Cannot call a class as a function")}(this,t),yr(this,"input",void 0),yr(this,"options",void 0),yr(this,"utilities",void 0),yr(this,"caretPosition",void 0),yr(this,"caretPositionEnd",void 0),yr(this,"keyboardDOM",void 0),yr(this,"keyboardPluginClasses",void 0),yr(this,"keyboardDOMClass",void 0),yr(this,"buttonElements",void 0),yr(this,"currentInstanceName",void 0),yr(this,"allKeyboardInstances",void 0),yr(this,"keyboardInstanceNames",void 0),yr(this,"isFirstKeyboardInstance",void 0),yr(this,"physicalKeyboard",void 0),yr(this,"modules",void 0),yr(this,"activeButtonClass",void 0),yr(this,"holdInteractionTimeout",void 0),yr(this,"holdTimeout",void 0),yr(this,"isMouseHold",void 0),yr(this,"initialized",void 0),yr(this,"candidateBox",void 0),yr(this,"keyboardRowsDOM",void 0),yr(this,"defaultName","default"),yr(this,"activeInputElement",null),yr(this,"handleParams",function(t,e){var n,r,o;if("string"==typeof t)n=t.split(".").join(""),r=document.querySelector(".".concat(n)),o=e;else if(t instanceof HTMLDivElement){if(!t.className)throw console.warn("Any DOM element passed as parameter must have a class."),new Error("KEYBOARD_DOM_CLASS_ERROR");n=t.className.split(" ")[0],r=t,o=e}else n="simple-keyboard",r=document.querySelector(".".concat(n)),o=t;return{keyboardDOMClass:n,keyboardDOM:r,options:o}}),yr(this,"getOptions",function(){return r.options}),yr(this,"getCaretPosition",function(){return r.caretPosition}),yr(this,"getCaretPositionEnd",function(){return r.caretPositionEnd}),yr(this,"registerModule",function(t,e){r.modules[t]||(r.modules[t]={}),e(r.modules[t])}),yr(this,"getKeyboardClassString",function(){for(var t=arguments.length,e=new Array(t),n=0;n<t;n++)e[n]=arguments[n];return[r.keyboardDOMClass].concat(e).filter(function(t){return!!t}).join(" ")}),"undefined"!=typeof window){var o=this.handleParams(e,n),i=o.keyboardDOMClass,a=o.keyboardDOM,u=o.options,s=void 0===u?{}:u;this.utilities=new Zn({getOptions:this.getOptions,getCaretPosition:this.getCaretPosition,getCaretPositionEnd:this.getCaretPositionEnd,dispatch:this.dispatch}),this.caretPosition=null,this.caretPositionEnd=null,this.keyboardDOM=a,this.options=function(t){for(var e=1;e<arguments.length;e++){var n=null!=arguments[e]?arguments[e]:{};e%2?hr(Object(n),!0).forEach(function(e){yr(t,e,n[e])}):Object.getOwnPropertyDescriptors?Object.defineProperties(t,Object.getOwnPropertyDescriptors(n)):hr(Object(n)).forEach(function(e){Object.defineProperty(t,e,Object.getOwnPropertyDescriptor(n,e))})}return t}({layoutName:"default",theme:"hg-theme-default",inputName:"default",preventMouseDownDefault:!1,enableLayoutCandidates:!0,excludeFromLayout:{}},s),this.keyboardPluginClasses="",Zn.bindMethods(t,this);var c=this.options.inputName,l=void 0===c?this.defaultName:c;if(this.input={},this.input[l]="",this.keyboardDOMClass=i,this.buttonElements={},window.SimpleKeyboardInstances||(window.SimpleKeyboardInstances={}),this.currentInstanceName=this.utilities.camelCase(this.keyboardDOMClass),window.SimpleKeyboardInstances[this.currentInstanceName]=this,this.allKeyboardInstances=window.SimpleKeyboardInstances,this.keyboardInstanceNames=Object.keys(window.SimpleKeyboardInstances),this.isFirstKeyboardInstance=this.keyboardInstanceNames[0]===this.currentInstanceName,this.physicalKeyboard=new or({dispatch:this.dispatch,getOptions:this.getOptions}),this.candidateBox=this.options.enableLayoutCandidates?new lr({utilities:this.utilities,options:this.options}):null,!this.keyboardDOM)throw console.warn('".'.concat(i,'" was not found in the DOM.')),new Error("KEYBOARD_DOM_ERROR");this.render(),this.modules={},this.loadModules()}},e=[{key:"setCaretPosition",value:function(t){var e=arguments.length>1&&void 0!==arguments[1]?arguments[1]:t;this.caretPosition=t,this.caretPositionEnd=e}},{key:"getInputCandidates",value:function(t){var e=this,n=this.options,r=n.layoutCandidates,o=n.layoutCandidatesCaseSensitiveMatch;if(!r||"object"!==pr(r))return{};var i=Object.keys(r).filter(function(n){var r=t.substring(0,e.getCaretPositionEnd()||0)||t,i=new RegExp("".concat(e.utilities.escapeRegex(n),"$"),o?"g":"gi");return!!fr(r.matchAll(i)).length});if(i.length>1){var a=i.sort(function(t,e){return e.length-t.length})[0];return{candidateKey:a,candidateValue:r[a]}}if(i.length){var u=i[0];return{candidateKey:u,candidateValue:r[u]}}return{}}},{key:"showCandidatesBox",value:function(t,e,n){var r=this;this.candidateBox&&this.candidateBox.show({candidateValue:e,targetElement:n,onSelect:function(e,n){var o=r.options,i=o.layoutCandidatesCaseSensitiveMatch,a=o.disableCandidateNormalization,u=o.enableLayoutCandidatesKeyPress,s=e;a||(s=e.normalize("NFD")),"function"==typeof r.options.beforeInputUpdate&&r.options.beforeInputUpdate(r);var c=r.getInput(r.options.inputName,!0),l=r.getCaretPositionEnd()||0,f=c.substring(0,l||0)||c,d=new RegExp("".concat(r.utilities.escapeRegex(t),"$"),i?"g":"gi"),p=f.replace(d,s),h=c.replace(f,p),v=p.length-f.length,y=(l||c.length)+v;y<0&&(y=0),r.setInput(h,r.options.inputName,!0),r.setCaretPosition(y),u&&"function"==typeof r.options.onKeyPress&&r.options.onKeyPress(e,n),"function"==typeof r.options.onChange&&r.options.onChange(r.getInput(r.options.inputName,!0),n),"function"==typeof r.options.onChangeAll&&r.options.onChangeAll(r.getAllInputs(),n)}})}},{key:"handleButtonClicked",value:function(t,e){var n=this.options,r=n.inputName,o=void 0===r?this.defaultName:r,i=n.debug;if("{//}"!==t){this.input[o]||(this.input[o]=""),"function"==typeof this.options.beforeInputUpdate&&this.options.beforeInputUpdate(this);var a=this.utilities.getUpdatedInput(t,this.input[o],this.caretPosition,this.caretPositionEnd);if(this.utilities.isStandardButton(t)&&this.activeInputElement&&this.input[o]&&this.input[o]===a&&0===this.caretPosition&&this.caretPositionEnd===a.length)return this.setInput("",this.options.inputName,!0),this.setCaretPosition(0),this.activeInputElement.value="",this.activeInputElement.setSelectionRange(0,0),void this.handleButtonClicked(t,e);if("function"==typeof this.options.onKeyPress&&this.options.onKeyPress(t,e),this.input[o]!==a&&(!this.options.inputPattern||this.options.inputPattern&&this.inputPatternIsValid(a))){if(this.options.maxLength&&this.utilities.handleMaxLength(this.input,a))return;var u=this.utilities.getUpdatedInput(t,this.input[o],this.caretPosition,this.caretPositionEnd,!0);if(this.setInput(u,this.options.inputName,!0),i&&console.log("Input changed:",this.getAllInputs()),this.options.debug&&console.log("Caret at: ",this.getCaretPosition(),this.getCaretPositionEnd(),"(".concat(this.keyboardDOMClass,")"),null==e?void 0:e.type),this.options.syncInstanceInputs&&this.syncInstanceInputs(),"function"==typeof this.options.onChange&&this.options.onChange(this.getInput(this.options.inputName,!0),e),"function"==typeof this.options.onChangeAll&&this.options.onChangeAll(this.getAllInputs(),e),null!=e&&e.target&&this.options.enableLayoutCandidates){var s,c=this.getInputCandidates(a),l=c.candidateKey,f=c.candidateValue;l&&f?this.showCandidatesBox(l,f,this.keyboardDOM):null===(s=this.candidateBox)||void 0===s||s.destroy()}}this.caretPositionEnd&&this.caretPosition!==this.caretPositionEnd&&(this.setCaretPosition(this.caretPositionEnd,this.caretPositionEnd),this.activeInputElement&&this.activeInputElement.setSelectionRange(this.caretPositionEnd,this.caretPositionEnd),this.options.debug&&console.log("Caret position aligned",this.caretPosition)),i&&console.log("Key pressed:",t)}}},{key:"getMouseHold",value:function(){return this.isMouseHold}},{key:"setMouseHold",value:function(t){this.options.syncInstanceInputs?this.dispatch(function(e){e.isMouseHold=t}):this.isMouseHold=t}},{key:"handleButtonMouseDown",value:function(t,e){var n=this;e&&(this.options.preventMouseDownDefault&&e.preventDefault(),this.options.stopMouseDownPropagation&&e.stopPropagation(),e.target.classList.add(this.activeButtonClass)),this.holdInteractionTimeout&&clearTimeout(this.holdInteractionTimeout),this.holdTimeout&&clearTimeout(this.holdTimeout),this.setMouseHold(!0),this.options.disableButtonHold||(this.holdTimeout=window.setTimeout(function(){(n.getMouseHold()&&(!t.includes("{")&&!t.includes("}")||"{delete}"===t||"{backspace}"===t||"{bksp}"===t||"{space}"===t||"{tab}"===t)||"{arrowright}"===t||"{arrowleft}"===t||"{arrowup}"===t||"{arrowdown}"===t)&&(n.options.debug&&console.log("Button held:",t),n.handleButtonHold(t)),clearTimeout(n.holdTimeout)},500))}},{key:"handleButtonMouseUp",value:function(t,e){var n=this;e&&(this.options.preventMouseUpDefault&&e.preventDefault&&e.preventDefault(),this.options.stopMouseUpPropagation&&e.stopPropagation&&e.stopPropagation(),!(e.target===this.keyboardDOM||e.target&&this.keyboardDOM.contains(e.target)||this.candidateBox&&this.candidateBox.candidateBoxElement&&(e.target===this.candidateBox.candidateBoxElement||e.target&&this.candidateBox.candidateBoxElement.contains(e.target)))&&this.candidateBox&&this.candidateBox.destroy()),this.recurseButtons(function(t){t.classList.remove(n.activeButtonClass)}),this.setMouseHold(!1),this.holdInteractionTimeout&&clearTimeout(this.holdInteractionTimeout),t&&"function"==typeof this.options.onKeyReleased&&this.options.onKeyReleased(t,e)}},{key:"handleKeyboardContainerMouseDown",value:function(t){this.options.preventMouseDownDefault&&t.preventDefault()}},{key:"handleButtonHold",value:function(t){var e=this;this.holdInteractionTimeout&&clearTimeout(this.holdInteractionTimeout),this.holdInteractionTimeout=window.setTimeout(function(){e.getMouseHold()?(e.handleButtonClicked(t),e.handleButtonHold(t)):clearTimeout(e.holdInteractionTimeout)},100)}},{key:"syncInstanceInputs",value:function(){var t=this;this.dispatch(function(e){e.replaceInput(t.input),e.setCaretPosition(t.caretPosition,t.caretPositionEnd)})}},{key:"clearInput",value:function(){var t=arguments.length>0&&void 0!==arguments[0]?arguments[0]:this.options.inputName||this.defaultName;this.input[t]="",this.setCaretPosition(0),this.options.syncInstanceInputs&&this.syncInstanceInputs()}},{key:"getInput",value:function(){var t=arguments.length>0&&void 0!==arguments[0]?arguments[0]:this.options.inputName||this.defaultName,e=arguments.length>1&&void 0!==arguments[1]&&arguments[1];return this.options.syncInstanceInputs&&!e&&this.syncInstanceInputs(),this.options.rtl?"‫"+this.input[t].replace("‫","").replace("‬","")+"‬":this.input[t]}},{key:"getAllInputs",value:function(){var t=this,e={};return Object.keys(this.input).forEach(function(n){e[n]=t.getInput(n,!0)}),e}},{key:"setInput",value:function(t){var e=arguments.length>1&&void 0!==arguments[1]?arguments[1]:this.options.inputName||this.defaultName,n=arguments.length>2?arguments[2]:void 0;this.input[e]=t,!n&&this.options.syncInstanceInputs&&this.syncInstanceInputs()}},{key:"replaceInput",value:function(t){this.input=t}},{key:"setOptions",value:function(){var t=arguments.length>0&&void 0!==arguments[0]?arguments[0]:{},e=this.changedOptions(t);this.options=Object.assign(this.options,t),e.length&&(this.options.debug&&console.log("changedOptions",e),this.onSetOptions(e),this.render())}},{key:"changedOptions",value:function(t){var e=this;return Object.keys(t).filter(function(n){return JSON.stringify(t[n])!==JSON.stringify(e.options[n])})}},{key:"onSetOptions",value:function(){var t=arguments.length>0&&void 0!==arguments[0]?arguments[0]:[];t.includes("layoutName")&&this.candidateBox&&this.candidateBox.destroy(),(t.includes("layoutCandidatesPageSize")||t.includes("layoutCandidates"))&&this.candidateBox&&(this.candidateBox.destroy(),this.candidateBox=new lr({utilities:this.utilities,options:this.options}))}},{key:"resetRows",value:function(){this.keyboardRowsDOM&&this.keyboardRowsDOM.remove(),this.keyboardDOM.className=this.keyboardDOMClass,this.keyboardDOM.setAttribute("data-skInstance",this.currentInstanceName),this.buttonElements={}}},{key:"dispatch",value:function(t){if(!window.SimpleKeyboardInstances)throw console.warn("SimpleKeyboardInstances is not defined. Dispatch cannot be called."),new Error("INSTANCES_VAR_ERROR");return Object.keys(window.SimpleKeyboardInstances).forEach(function(e){t(window.SimpleKeyboardInstances[e],e)})}},{key:"addButtonTheme",value:function(t,e){var n=this;e&&t&&(t.split(" ").forEach(function(r){e.split(" ").forEach(function(e){n.options.buttonTheme||(n.options.buttonTheme=[]);var o=!1;n.options.buttonTheme.map(function(t){if(null!=t&&t.class.split(" ").includes(e)){o=!0;var n=t.buttons.split(" ");n.includes(r)||(o=!0,n.push(r),t.buttons=n.join(" "))}return t}),o||n.options.buttonTheme.push({class:e,buttons:t})})}),this.render())}},{key:"removeButtonTheme",value:function(t,e){var n=this;if(!t&&!e)return this.options.buttonTheme=[],void this.render();t&&Array.isArray(this.options.buttonTheme)&&this.options.buttonTheme.length&&(t.split(" ").forEach(function(t){var r;null===(r=n.options)||void 0===r||null===(r=r.buttonTheme)||void 0===r||r.map(function(r,o){if(r&&e&&e.includes(r.class)||!e){var i,a,u=null===(i=r)||void 0===i?void 0:i.buttons.split(" ").filter(function(e){return e!==t});r&&null!=u&&u.length?r.buttons=u.join(" "):(null===(a=n.options.buttonTheme)||void 0===a||a.splice(o,1),r=null)}return r})}),this.render())}},{key:"getButtonElement",value:function(t){var e,n=this.buttonElements[t];return n&&(e=n.length>1?n:n[0]),e}},{key:"inputPatternIsValid",value:function(t){var e,n=this.options.inputPattern;if((e=n instanceof RegExp?n:n[this.options.inputName||this.defaultName])&&t){var r=e.test(t);return this.options.debug&&console.log('inputPattern ("'.concat(e,'"): ').concat(r?"passed":"did not pass!")),r}return!0}},{key:"setEventListeners",value:function(){if(this.isFirstKeyboardInstance||!this.allKeyboardInstances){this.options.debug&&console.log("Caret handling started (".concat(this.keyboardDOMClass,")"));var t=this.options.physicalKeyboardHighlightPreventDefault,e=void 0!==t&&t;document.addEventListener("keyup",this.handleKeyUp,e),document.addEventListener("keydown",this.handleKeyDown,e),document.addEventListener("mouseup",this.handleMouseUp),document.addEventListener("touchend",this.handleTouchEnd),this.options.updateCaretOnSelectionChange&&document.addEventListener("selectionchange",this.handleSelectionChange),document.addEventListener("select",this.handleSelect)}}},{key:"handleKeyUp",value:function(t){this.caretEventHandler(t),this.options.physicalKeyboardHighlight&&this.physicalKeyboard.handleHighlightKeyUp(t)}},{key:"handleKeyDown",value:function(t){this.options.physicalKeyboardHighlight&&this.physicalKeyboard.handleHighlightKeyDown(t)}},{key:"handleMouseUp",value:function(t){this.caretEventHandler(t)}},{key:"handleTouchEnd",value:function(t){this.caretEventHandler(t)}},{key:"handleSelect",value:function(t){this.caretEventHandler(t)}},{key:"handleSelectionChange",value:function(t){navigator.userAgent.includes("Firefox")||this.caretEventHandler(t)}},{key:"caretEventHandler",value:function(t){var e,n=this;t.target.tagName&&(e=t.target.tagName.toLowerCase()),this.dispatch(function(r){var o=t.target===r.keyboardDOM||t.target&&r.keyboardDOM.contains(t.target);if(n.options.syncInstanceInputs){var i="function"==typeof t.composedPath?t.composedPath():t.path;Array.isArray(i)&&(o=i.some(function(t){var e;return null==t||null===(e=t.hasAttribute)||void 0===e?void 0:e.call(t,"data-skInstance")}))}if(("textarea"===e||"input"===e&&["text","search","url","tel","password"].includes(t.target.type))&&!r.options.disableCaretPositioning){var a=t.target.selectionStart,u=t.target.selectionEnd;r.options.rtl&&(a=r.utilities.getRtlOffset(a,r.getInput()),u=r.utilities.getRtlOffset(u,r.getInput())),r.setCaretPosition(a,u),r.activeInputElement=t.target,r.options.debug&&console.log("Caret at: ",r.getCaretPosition(),r.getCaretPositionEnd(),t&&t.target.tagName.toLowerCase(),"(".concat(r.keyboardDOMClass,")"),null==t?void 0:t.type)}else!r.options.disableCaretPositioning&&o||"selectionchange"===(null==t?void 0:t.type)||(r.setCaretPosition(null),r.activeInputElement=null,r.options.debug&&console.log('Caret position reset due to "'.concat(null==t?void 0:t.type,'" event'),t))})}},{key:"recurseButtons",value:function(t){var e=this;t&&Object.keys(this.buttonElements).forEach(function(n){return e.buttonElements[n].forEach(t)})}},{key:"destroy",value:function(){this.options.debug&&console.log("Destroying simple-keyboard instance: ".concat(this.currentInstanceName));var t=this.options.physicalKeyboardHighlightPreventDefault,e=void 0!==t&&t;document.removeEventListener("keyup",this.handleKeyUp,e),document.removeEventListener("keydown",this.handleKeyDown,e),document.removeEventListener("mouseup",this.handleMouseUp),document.removeEventListener("touchend",this.handleTouchEnd),document.removeEventListener("select",this.handleSelect),this.options.updateCaretOnSelectionChange&&document.removeEventListener("selectionchange",this.handleSelectionChange),document.onpointerup=null,document.ontouchend=null,document.ontouchcancel=null,document.onmouseup=null,this.recurseButtons(function(t){t&&(t.onpointerdown=null,t.onpointerup=null,t.onpointercancel=null,t.ontouchstart=null,t.ontouchend=null,t.ontouchcancel=null,t.onclick=null,t.onmousedown=null,t.onmouseup=null,t.remove(),t=null)}),this.keyboardDOM.onpointerdown=null,this.keyboardDOM.ontouchstart=null,this.keyboardDOM.onmousedown=null,this.resetRows(),this.candidateBox&&(this.candidateBox.destroy(),this.candidateBox=null),this.activeInputElement=null,this.keyboardDOM.removeAttribute("data-skInstance"),this.keyboardDOM.innerHTML="",window.SimpleKeyboardInstances[this.currentInstanceName]=null,delete window.SimpleKeyboardInstances[this.currentInstanceName],this.initialized=!1}},{key:"getButtonThemeClasses",value:function(t){var e=this.options.buttonTheme,n=[];return Array.isArray(e)&&e.forEach(function(e){if(e&&e.class&&"string"==typeof e.class&&e.buttons&&"string"==typeof e.buttons){var r=e.class.split(" ");e.buttons.split(" ").includes(t)&&(n=[].concat(fr(n),fr(r)))}else console.warn('Incorrect "buttonTheme". Please check the documentation.',e)}),n}},{key:"setDOMButtonAttributes",value:function(t,e){var n=this.options.buttonAttributes;Array.isArray(n)&&n.forEach(function(n){n.attribute&&"string"==typeof n.attribute&&n.value&&"string"==typeof n.value?n.buttons&&"string"==typeof n.buttons?n.buttons.split(" ").includes(t)&&e(n.attribute,n.value):e(n.attribute,n.value):console.warn('Incorrect "buttonAttributes". Please check the documentation.',n)})}},{key:"onTouchDeviceDetected",value:function(){this.processAutoTouchEvents(),this.disableContextualWindow()}},{key:"disableContextualWindow",value:function(){window.oncontextmenu=function(t){var e;if(null!==(e=t.target.classList)&&void 0!==e&&e.contains("hg-button"))return t.preventDefault(),t.stopPropagation(),!1}}},{key:"processAutoTouchEvents",value:function(){this.options.autoUseTouchEvents&&(this.options.useTouchEvents=!0,this.options.debug&&console.log("autoUseTouchEvents: Touch device detected, useTouchEvents enabled."))}},{key:"onInit",value:function(){this.options.debug&&console.log("".concat(this.keyboardDOMClass," Initialized")),this.setEventListeners(),"function"==typeof this.options.onInit&&this.options.onInit(this)}},{key:"beforeFirstRender",value:function(){this.utilities.isTouchDevice()&&this.onTouchDeviceDetected(),"function"==typeof this.options.beforeFirstRender&&this.options.beforeFirstRender(this),this.isFirstKeyboardInstance&&this.utilities.pointerEventsSupported()&&!this.options.useTouchEvents&&!this.options.useMouseEvents&&this.options.debug&&console.log("Using PointerEvents as it is supported by this browser"),this.options.useTouchEvents&&this.options.debug&&console.log("useTouchEvents has been enabled. Only touch events will be used.")}},{key:"beforeRender",value:function(){"function"==typeof this.options.beforeRender&&this.options.beforeRender(this)}},{key:"onRender",value:function(){"function"==typeof this.options.onRender&&this.options.onRender(this)}},{key:"onModulesLoaded",value:function(){"function"==typeof this.options.onModulesLoaded&&this.options.onModulesLoaded(this)}},{key:"loadModules",value:function(){var t=this;Array.isArray(this.options.modules)&&(this.options.modules.forEach(function(e){var n=t.utilities.isConstructor(e)?new e(t):e(t);n.init&&n.init(t)}),this.keyboardPluginClasses="modules-loaded",this.render(),this.onModulesLoaded())}},{key:"getModuleProp",value:function(t,e){return!!this.modules[t]&&this.modules[t][e]}},{key:"getModulesList",value:function(){return Object.keys(this.modules)}},{key:"parseRowDOMContainers",value:function(t,e,n,r){var o=this,i=Array.from(t.children),a=0;return i.length&&n.forEach(function(n,u){var s=r[u];if(!(s&&s>n))return!1;var c=n-a,l=s-a,f=document.createElement("div");f.className+="hg-button-container";var d="".concat(o.options.layoutName,"-r").concat(e,"c").concat(u);f.setAttribute("data-skUID",d);var p=i.splice(c,l-c+1);a+=l-c,p.forEach(function(t){return f.appendChild(t)}),i.splice(c,0,f),t.innerHTML="",i.forEach(function(e){return t.appendChild(e)}),o.options.debug&&console.log("rowDOMContainer",p,c,l,a+1)}),t}},{key:"render",value:function(){var t=this;this.resetRows(),this.initialized||this.beforeFirstRender(),this.beforeRender();var e="hg-layout-".concat(this.options.layoutName),n=this.options.layout||{default:["` 1 2 3 4 5 6 7 8 9 0 - = {bksp}","{tab} q w e r t y u i o p [ ] \\","{lock} a s d f g h j k l ; ' {enter}","{shift} z x c v b n m , . / {shift}",".com @ {space}"],shift:["~ ! @ # $ % ^ & * ( ) _ + {bksp}","{tab} Q W E R T Y U I O P { } |",'{lock} A S D F G H J K L : " {enter}',"{shift} Z X C V B N M < > ? {shift}",".com @ {space}"]},r=this.options.useTouchEvents||!1,o=r?"hg-touch-events":"",i=this.options.useMouseEvents||!1,a=this.options.disableRowButtonContainers;this.keyboardDOM.className=this.getKeyboardClassString(this.options.theme,e,this.keyboardPluginClasses,o),this.keyboardDOM.setAttribute("data-skInstance",this.currentInstanceName),this.keyboardRowsDOM=document.createElement("div"),this.keyboardRowsDOM.className="hg-rows",n[this.options.layoutName||this.defaultName].forEach(function(e,n){var o=e.split(" ");t.options.excludeFromLayout&&t.options.excludeFromLayout[t.options.layoutName||t.defaultName]&&(o=o.filter(function(e){return t.options.excludeFromLayout&&!t.options.excludeFromLayout[t.options.layoutName||t.defaultName].includes(e)}));var u=document.createElement("div");u.className+="hg-row";var s=[],c=[];o.forEach(function(e,o){var l,f=!a&&"string"==typeof e&&e.length>1&&0===e.indexOf("["),d=!a&&"string"==typeof e&&e.length>1&&e.indexOf("]")===e.length-1;f&&(s.push(o),e=e.replace(/\[/g,"")),d&&(c.push(o),e=e.replace(/\]/g,""));var p=t.utilities.getButtonClass(e),h=t.utilities.getButtonDisplayName(e,t.options.display,t.options.mergeDisplay),v=t.options.useButtonTag?"button":"div",y=document.createElement(v);y.className+="hg-button ".concat(p),(l=y.classList).add.apply(l,fr(t.getButtonThemeClasses(e))),t.setDOMButtonAttributes(e,function(t,e){y.setAttribute(t,e)}),t.activeButtonClass="hg-activeButton",!t.utilities.pointerEventsSupported()||r||i?r?(y.ontouchstart=function(n){t.handleButtonClicked(e,n),t.handleButtonMouseDown(e,n)},y.ontouchend=function(n){t.handleButtonMouseUp(e,n)},y.ontouchcancel=function(n){t.handleButtonMouseUp(e,n)}):(y.onclick=function(n){t.setMouseHold(!1),"function"==typeof t.options.onKeyReleased||t.options.useMouseEvents&&t.options.clickOnMouseDown||t.handleButtonClicked(e,n)},y.onmousedown=function(n){("function"==typeof t.options.onKeyReleased||t.options.useMouseEvents&&t.options.clickOnMouseDown)&&!t.isMouseHold&&t.handleButtonClicked(e,n),t.handleButtonMouseDown(e,n)},y.onmouseup=function(n){t.handleButtonMouseUp(e,n)}):(y.onpointerdown=function(n){t.handleButtonClicked(e,n),t.handleButtonMouseDown(e,n)},y.onpointerup=function(n){t.handleButtonMouseUp(e,n)},y.onpointercancel=function(n){t.handleButtonMouseUp(e,n)}),y.setAttribute("data-skBtn",e);var g="".concat(t.options.layoutName,"-r").concat(n,"b").concat(o);y.setAttribute("data-skBtnUID",g);var m=document.createElement("span");m.innerHTML=h,y.appendChild(m),t.buttonElements[e]||(t.buttonElements[e]=[]),t.buttonElements[e].push(y),u.appendChild(y)}),u=t.parseRowDOMContainers(u,n,s,c),t.keyboardRowsDOM.appendChild(u)}),this.keyboardDOM.appendChild(this.keyboardRowsDOM),this.onRender(),this.initialized||(this.initialized=!0,!this.utilities.pointerEventsSupported()||r||i?r?(document.ontouchend=function(e){return t.handleButtonMouseUp(void 0,e)},document.ontouchcancel=function(e){return t.handleButtonMouseUp(void 0,e)},this.keyboardDOM.ontouchstart=function(e){return t.handleKeyboardContainerMouseDown(e)}):r||(document.onmouseup=function(e){return t.handleButtonMouseUp(void 0,e)},this.keyboardDOM.onmousedown=function(e){return t.handleKeyboardContainerMouseDown(e)}):(document.onpointerup=function(e){return t.handleButtonMouseUp(void 0,e)},this.keyboardDOM.onpointerdown=function(e){return t.handleKeyboardContainerMouseDown(e)}),this.onInit())}}],e&&vr(t.prototype,e),n&&vr(t,n),Object.defineProperty(t,"prototype",{writable:!1}),t;var t,e,n}(),br=mr,wr=mr}(),i}()});
WEBEOF_51
cat > "$APP_DIR/pimedia/__init__.py" <<'WEBEOF_52'
"""Pi Media Station : serveur (relais Subsonic, podcasts, lecture), données et réglages."""
WEBEOF_52
cat > "$APP_DIR/pimedia/cli.py" <<'WEBEOF_53'
"""Petits réglages en ligne de commande (sur le Pi ou le serveur, sans ouvrir l'application).

  python3 -m pimedia.cli set SUBSONIC_URL=https://… SUBSONIC_USER=thomas SUBSONIC_PASS=…
  python3 -m pimedia.cli show            (affiche les clés du .env, secrets masqués)
  python3 -m pimedia.cli migrate         (reprend secrets et clés API de l'ancien config.json dans le .env)
"""
import os
import sys

from .envfile import EnvFile
from .paths import resolve_data_dir
from .settings import ENV_TYPES
from .storage.legacy import RENAMED_KEYS, env_text, read_json

SECRET_WORDS = ("PASS", "SECRET", "KEY", "TOKEN")


def data_dir():
    code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    directory = resolve_data_dir(code_dir, os.environ)
    os.makedirs(directory, exist_ok=True)
    return directory


def env_file():
    return EnvFile(os.path.join(data_dir(), ".env"))


def masked(key, value):
    return "••••" if any(w in key for w in SECRET_WORDS) and value else value


def migrate():
    """Ancien config.json (ou sa copie .importe) -> .env : adresse et identifiants Subsonic, clés API, réglages du menu.
    Les valeurs déjà présentes dans le .env sont gardées."""
    old = next((p for p in (os.path.join(data_dir(), n) for n in ("config.json", "config.json.importe")) if os.path.exists(p)), None)
    data = read_json(old) if old else None
    if not isinstance(data, dict):
        print("Aucun ancien config.json à reprendre.")
        return 0
    env = env_file()
    present = env.values()
    data = {RENAMED_KEYS.get(k, k): v for k, v in data.items()}
    fresh = {k.upper(): env_text(v) for k, v in data.items() if k in ENV_TYPES and k.upper() not in present and v not in ("", None)}
    if fresh:
        env.set(**fresh)
    print("Repris depuis %s :" % os.path.basename(old))
    for key, value in sorted(fresh.items()):
        print("  %s=%s" % (key, masked(key, value)))
    if not fresh:
        print("  rien de nouveau (tout est déjà dans le .env)")
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "set" and all("=" in a for a in argv[1:]):
        changes = dict(a.split("=", 1) for a in argv[1:])
        env_file().set(**{k.strip().upper(): v for k, v in changes.items()})
        print("Enregistré dans", env_file().path, ":", ", ".join(k.upper() for k in changes))
        return 0
    if argv == ["show"]:
        for key, value in sorted(env_file().values().items()):
            print("%s=%s" % (key, masked(key, value)))
        return 0
    if argv == ["migrate"]:
        return migrate()
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
WEBEOF_53
cat > "$APP_DIR/pimedia/entities.py" <<'WEBEOF_54'
"""Entités : les objets métier que les dépôts (storage/) renvoient.

Chaque entité sait se convertir au format JSON attendu par la page (to_api) ; les noms d'attributs
suivent les colonnes de la base (en anglais), les clés du JSON restent celles que la page utilise déjà."""
from dataclasses import dataclass, field
from typing import List, Optional

from .tracks import clean_track


@dataclass(frozen=True)
class Track:
    """Un titre (Subsonic, Jamendo, YouTube…). Ses champs varient selon la source : on garde le dictionnaire validé."""
    fields: dict

    @classmethod
    def from_api(cls, raw):
        """Titre reçu de la page : seuls les champs connus sont gardés, les adresses douteuses refusées."""
        return cls(clean_track(raw))

    @property
    def id(self):
        return self.fields["id"]

    @property
    def title(self):
        return self.fields["title"]

    @property
    def youtube_id(self):
        return self.fields.get("youtubeId")

    def to_api(self):
        return dict(self.fields)


@dataclass(frozen=True)
class PodcastSubscription:
    feed_url: str
    title: str
    image_url: str = ""
    author: str = ""
    subscribed_at: int = 0

    def to_api(self):
        return {"feed": self.feed_url, "title": self.title, "image": self.image_url, "author": self.author,
                "added": self.subscribed_at}


@dataclass(frozen=True)
class EpisodeProgress:
    episode_id: str
    feed_url: str = ""
    title: str = ""
    podcast_title: str = ""
    image_url: str = ""
    audio_url: str = ""
    position_s: float = 0.0
    duration_s: float = 0.0
    played: bool = False
    updated_at: int = 0

    def to_api(self):
        return {"id": self.episode_id, "feed": self.feed_url, "title": self.title, "podcast": self.podcast_title,
                "image": self.image_url, "audio": self.audio_url, "pos": self.position_s, "dur": self.duration_s,
                "played": self.played, "t": self.updated_at}


@dataclass(frozen=True)
class PlaylistSummary:
    id: str
    name: str
    track_count: int

    def to_api(self):
        return {"id": self.id, "name": self.name, "count": self.track_count}


@dataclass(frozen=True)
class Playlist:
    id: str
    name: str
    created_at: int = 0
    tracks: List[Track] = field(default_factory=list)

    def to_api(self):
        return {"id": self.id, "name": self.name, "songs": [t.to_api() for t in self.tracks]}


@dataclass(frozen=True)
class QueueItem:
    """Un titre de la file d'attente commune du Pi, et qui l'a ajouté (écran, téléphone…)."""
    id: int
    position: int
    track: Track
    added_by: str = "screen"
    added_at: int = 0

    def to_api(self):
        return {"itemId": self.id, "position": self.position, "addedBy": self.added_by, "track": self.track.to_api()}


@dataclass(frozen=True)
class QueueSnapshot:
    """La file entière à un instant : titres, titre en cours, numéro de version (change à chaque modification)."""
    items: List[QueueItem]
    current_item_id: Optional[int]
    version: int

    @property
    def current_index(self):
        return next((i for i, item in enumerate(self.items) if item.id == self.current_item_id), -1)

    @property
    def current(self):
        index = self.current_index
        return self.items[index] if index >= 0 else None

    def to_api(self):
        return {"items": [i.to_api() for i in self.items], "currentItemId": self.current_item_id,
                "currentIndex": self.current_index, "version": self.version}


@dataclass(frozen=True)
class QueueRequest:
    """Demande d'ajout à la file faite depuis un téléphone : « après ce titre » (next) ou « à la fin » (end)."""
    id: int
    track: Track
    mode: str
    added_by: str

    def to_api(self):
        return {"requestId": self.id, "mode": self.mode, "addedBy": self.added_by, "track": self.track.to_api()}
WEBEOF_54
cat > "$APP_DIR/pimedia/envfile.py" <<'WEBEOF_55'
"""Fichier .env : réglages d'installation et secrets (adresse Subsonic, mots de passe, clés API…).
Il reste sur la machine, hors du code et des archives. Format : une ligne CLE=valeur, # pour un commentaire."""
import os
import threading

QUOTES = ("'", '"')


def parse(text):
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in QUOTES:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def quote(value):
    value = str(value)
    if value == "" or any(c in value for c in " #'\"\t"):
        return '"' + value.replace('"', '\\"') + '"'
    return value


class EnvFile:
    """Lecture (relue si le fichier change) et mise à jour d'un .env, en gardant commentaires et ordre."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._mtime = None
        self._values = {}

    def values(self):
        try:
            mtime = os.stat(self.path).st_mtime_ns
        except OSError:
            return {}
        with self._lock:
            if mtime != self._mtime:
                with open(self.path, encoding="utf-8") as f:
                    self._values = parse(f.read())
                self._mtime = mtime
            return dict(self._values)

    def set(self, **changes):
        """Remplace ou ajoute des lignes CLE=valeur. Le fichier n'est lisible que par son propriétaire."""
        with self._lock:
            try:
                with open(self.path, encoding="utf-8") as f:
                    lines = f.read().splitlines()
            except OSError:
                lines = []
            pending = dict(changes)
            for i, line in enumerate(lines):
                key = line.split("=", 1)[0].strip()
                if "=" in line and not line.lstrip().startswith("#") and key in pending:
                    lines[i] = "%s=%s" % (key, quote(pending.pop(key)))
            lines += ["%s=%s" % (key, quote(value)) for key, value in pending.items()]
            tmp = self.path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            os.replace(tmp, self.path)
            self._mtime = None
WEBEOF_55
cat > "$APP_DIR/pimedia/i18n.py" <<'WEBEOF_56'
"""Textes affichés : i18n/<langue>.yaml, organisés par clés anglaises (« player.next: Titre suivant »).

t("podcasts.unknown_theme") renvoie le texte ; une clé absente renvoie la clé elle-même (repérable à l'écran)."""
import os

try:
    import yaml
except ImportError:            # python3-yaml absent : les clés s'affichent telles quelles, rien ne plante
    yaml = None

DEFAULT_LANGUAGE = "fr"


def flatten(tree, prefix=""):
    """{"player": {"next": "Titre suivant"}} -> {"player.next": "Titre suivant"}"""
    flat = {}
    for key, value in (tree or {}).items():
        name = prefix + str(key)
        if isinstance(value, dict):
            flat.update(flatten(value, name + "."))
        else:
            flat[name] = str(value)
    return flat


class Texts:
    def __init__(self, directory, language=DEFAULT_LANGUAGE):
        self.directory = directory
        self.language = language or DEFAULT_LANGUAGE
        self.strings = self._load()

    def _load(self):
        path = os.path.join(self.directory, self.language + ".yaml")
        if yaml is None or not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return flatten(yaml.safe_load(f))

    def t(self, key, **params):
        text = self.strings.get(key, key)
        return text.format(**params) if params else text

    def section(self, prefix):
        """Les textes d'une partie (« web. » pour la page), clés sans le préfixe."""
        return {k[len(prefix):]: v for k, v in self.strings.items() if k.startswith(prefix)}
WEBEOF_56
cat > "$APP_DIR/pimedia/paths.py" <<'WEBEOF_57'
"""Emplacements : le code (remplacé à chaque mise à jour) et les données (gardées d'une version à l'autre).

Après un déploiement par archive :  ~/.local/share/pi-media/releases/<version>/  (code)
                                     ~/.local/share/pi-media/                     (données : .env, pi-media.db)
"""
import os


def resolve_data_dir(code_dir, environ):
    """PI_MEDIA_DATA si défini ; sinon le dossier qui contient « releases/ » ; sinon le dossier du code."""
    if environ.get("PI_MEDIA_DATA"):
        return environ["PI_MEDIA_DATA"]
    parent = os.path.dirname(os.path.abspath(code_dir))
    if os.path.basename(parent) == "releases":
        return os.path.dirname(parent)
    return code_dir


def default_cache_dir(environ):
    return environ.get("PI_MEDIA_CACHE") or os.path.expanduser("~/.cache/pi-media-subsonic")


class Paths:
    def __init__(self, code_dir, data_dir, cache_dir):
        # code
        self.code_dir = code_dir
        self.web_dir = os.path.join(code_dir, "web")
        self.static_dir = os.path.join(self.web_dir, "static")
        self.i18n_dir = os.path.join(code_dir, "i18n")
        # données à garder
        self.data_dir = data_dir
        self.env_file = os.path.join(data_dir, ".env")
        self.db_file = os.path.join(data_dir, "pi-media.db")
        # anciens fichiers (importés une fois dans la base, voir storage/legacy.py)
        self.legacy_config = os.path.join(data_dir, "config.json")
        self.legacy_podcasts = os.path.join(data_dir, "podcasts.json")
        self.legacy_playlists = os.path.join(data_dir, "playlists.json")
        self.legacy_history = os.path.join(data_dir, "recherches.json")
        self.legacy_unplayable = os.path.join(data_dir, "youtube-illisibles.json")
        # cache (peut être vidé sans rien perdre)
        self.cache_dir = cache_dir
        self.json_dir = os.path.join(cache_dir, "json")
        self.cover_dir = os.path.join(cache_dir, "covers")
        self.newest_file = os.path.join(cache_dir, "newest.json")
WEBEOF_57
cat > "$APP_DIR/pimedia/settings.py" <<'WEBEOF_58'
"""Réglages : où chercher une valeur, et dans quel ordre.

1. app_settings (base SQLite) : ce que l'on change depuis l'application (sources activées, clé saisie à l'écran…) ;
2. variables d'environnement du processus (préfixe PI_MEDIA_) ;
3. fichier .env : réglages d'installation et secrets ;
4. valeur par défaut.
"""
import json
import threading

# Réglages d'installation lus dans le .env, avec leur type (les valeurs du .env sont du texte)
ENV_TYPES = {
    "bind": str, "subsonic_url": str, "subsonic_user": str, "subsonic_pass": str,
    "podcastindex_key": str, "podcastindex_secret": str, "ext_jamendo_id": str, "ext_youtube_key": str,
    "ext_youtube_region": str, "phone_port": int, "phone_remote": bool, "podcast_home": list, "language": str,
    # menu tactile (launcher.py)
    "device_name": str, "weather_city": str, "weather_latitude": float, "weather_longitude": float,
    "screensaver_seconds": int, "web_url": str,
}
TRUE_WORDS = ("1", "true", "yes", "oui", "on")


def convert(text, kind):
    if kind is int:
        return int(text)
    if kind is float:
        return float(text)
    if kind is bool:
        return str(text).strip().lower() in TRUE_WORDS
    if kind is list:
        return [part.strip() for part in str(text).split(",") if part.strip()]
    return text


class AppSettingsStore:
    """Table app_settings, gardée en mémoire (un seul processus écrit : le serveur)."""

    def __init__(self, db):
        self.db = db
        self._lock = threading.Lock()
        self._values = {row["key"]: json.loads(row["value"]) for row in db.query("SELECT key, value FROM app_settings")}

    def get(self, key, default=None):
        with self._lock:
            return self._values.get(key, default)

    def has(self, key):
        with self._lock:
            return key in self._values

    def set_many(self, changes):
        with self._lock, self.db.transaction() as conn:
            for key, value in changes.items():
                conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                             "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, json.dumps(value)))
                self._values[key] = value


class Settings:
    """Même interface que l'ancien config.json : get(), update() et quelques raccourcis typés."""

    def __init__(self, store, env_file, environ):
        self.store = store
        self.env_file = env_file
        self.environ = environ

    def get(self, key, default=None):
        if self.store.has(key):
            return self.store.get(key)
        env_name = key.upper()
        raw = self.environ.get("PI_MEDIA_" + env_name)       # seulement avec le préfixe : LANGUAGE, MODE… existent déjà
        if raw is None:
            raw = self.env_file.values().get(env_name)
        if raw is None:
            return default
        try:
            return convert(raw, ENV_TYPES.get(key, str))
        except ValueError:
            return default

    def update(self, **changes):
        """Réglages changés depuis l'application : enregistrés en base."""
        self.store.set_many(changes)

    @property
    def subsonic_url(self):
        return (self.get("subsonic_url") or "").rstrip("/")

    @property
    def bind_address(self):
        return self.get("bind", "127.0.0.1")
WEBEOF_58
cat > "$APP_DIR/pimedia/tracks.py" <<'WEBEOF_59'
"""Format commun d'un titre (Subsonic, Jamendo, YouTube…), tel que la page l'utilise et tel qu'on le stocke."""
import urllib.parse

TRACK_KEYS = ("id", "title", "artist", "album", "albumId", "artistId", "coverArt", "duration", "track", "suffix",
              "bitRate", "bitDepth", "samplingRate", "streamUrl", "youtubeId", "imageUrl", "ext")


def clean_track(raw):
    """Ne garde que les champs connus ; refuse un titre sans identifiant ou avec une adresse de lecture étrangère."""
    if not isinstance(raw, dict) or not raw.get("id") or not raw.get("title"):
        raise ValueError("titre invalide")
    track = {k: raw[k] for k in TRACK_KEYS if k in raw and isinstance(raw[k], (str, int, float))}
    for key in ("streamUrl", "imageUrl"):
        if track.get(key) and urllib.parse.urlsplit(str(track[key])).scheme not in ("http", "https"):
            raise ValueError("adresse invalide")
    track["id"], track["title"] = str(track["id"]), str(track["title"])[:300]
    return track
WEBEOF_59
cat > "$APP_DIR/pimedia/server/__init__.py" <<'WEBEOF_60'
"""Serveur de l'écran du Raspberry Pi : relais Subsonic avec cache, interface web, podcasts, lecture."""
WEBEOF_60
cat > "$APP_DIR/pimedia/server/api.py" <<'WEBEOF_61'
"""Appels à Subsonic avec cache : réponses JSON et pochettes."""
import json
import threading
from collections import namedtuple

from .constants import STALE_WHILE_REVALIDATE_MIN_TTL
from .tasks import in_background

ApiResult = namedtuple("ApiResult", "status ctype body state")


def is_ok(body):
    """Vrai si le corps est une réponse Subsonic de statut « ok »."""
    try:
        return json.loads(body)["subsonic-response"]["status"] == "ok"
    except (ValueError, KeyError, TypeError):
        return False


class _Job:
    def __init__(self):
        self.event = threading.Event()
        self.result = None
        self.error = None


class SharedCalls:
    """Si le même appel est déjà en cours (ex. : préchargement), on attend son résultat
    au lieu de relancer une requête sur un serveur déjà occupé."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}

    def run(self, key, func, wait_seconds):
        job, leader = self._join(key)
        if leader:
            self._execute(key, job, func)
        else:
            job.event.wait(wait_seconds)
        if job.error is not None:
            raise job.error
        if job.result is None:
            raise TimeoutError("délai dépassé")
        return job.result

    def _join(self, key):
        with self._lock:
            job = self._jobs.get(key)
            if job is not None:
                return job, False
            job = self._jobs[key] = _Job()
            return job, True

    def _execute(self, key, job, func):
        try:
            job.result = func()
        except Exception as error:      # noqa: BLE001 - relancée chez tous ceux qui attendent
            job.error = error
        finally:
            with self._lock:
                self._jobs.pop(key, None)
            job.event.set()


class CachedApi:
    """Appels JSON à Subsonic : cache, version périmée servie le temps d'un rafraîchissement,
    appels identiques regroupés, et traduction en parcours par dossiers quand ce mode est choisi."""

    HEAVY_TIMEOUTS = {"getArtists": 300, "getIndexes": 300, "getAlbumList2": 180, "getGenres": 180, "search3": 120}
    DEFAULT_TIMEOUT = 60

    def __init__(self, client, cache, policy, keys, browse):
        self.client = client
        self.cache = cache
        self.policy = policy
        self.keys = keys
        self.browse = browse
        self.shared = SharedCalls()
        self.folders = None             # FolderAdapter, branché par l'application (dépendance circulaire)

    def timeout_for(self, endpoint):
        return self.HEAVY_TIMEOUTS.get(endpoint, self.DEFAULT_TIMEOUT)

    # --- appels publics ---
    def call(self, endpoint, params):
        """Appel JSON avec cache. params : liste de couples (nom, valeur)."""
        ttl = self.policy.ttl_for(endpoint, dict(params))
        key = self.keys.for_call(endpoint, params)
        if ttl <= 0:
            return self._fetch(endpoint, params, key, 0)
        entry = self.cache.get(key)
        if entry:
            return ApiResult(200, entry.ctype, entry.body, "HIT")
        stale = self.cache.get(key, allow_stale=True)
        if stale and ttl >= STALE_WHILE_REVALIDATE_MIN_TTL:
            in_background(self._fetch_shared, endpoint, params, key, ttl)
            return ApiResult(200, stale.ctype, stale.body, "STALE")
        return self._fetch_shared(endpoint, params, key, ttl)

    def call_json(self, endpoint, params=()):
        """Comme call, mais retourne le contenu de « subsonic-response » (erreur si le statut n'est pas ok)."""
        result = self.call(endpoint, list(params))
        response = json.loads(result.body)["subsonic-response"]
        if response.get("status") != "ok":
            raise RuntimeError((response.get("error") or {}).get("message", "Erreur Subsonic"))
        return response

    def call_fresh(self, endpoint, params):
        """Appel sans lire ni écrire le cache (détection de nouveautés)."""
        return self._fetch(endpoint, params, self.keys.for_call(endpoint, params), 0)

    # --- coulisses ---
    def _fetch_shared(self, endpoint, params, key, ttl):
        return self.shared.run(key, lambda: self._fetch(endpoint, params, key, ttl),
                               self.timeout_for(endpoint) + 10)

    def _fetch(self, endpoint, params, key, ttl):
        try:
            status, ctype, body = self._remote(endpoint, params)
        except Exception:
            stale = self.cache.get(key, allow_stale=True) if ttl > 0 else None
            if stale:
                return ApiResult(200, stale.ctype, stale.body, "STALE")
            raise
        if status == 200 and is_ok(body):
            self._store(endpoint, params, key, ttl, ctype, body)
        return ApiResult(status, ctype, body, "MISS")

    def _remote(self, endpoint, params):
        """Un appel réel : directement à Subsonic, ou traduit en parcours par dossiers."""
        if self.browse.uses_folders(endpoint):
            payload = {"subsonic-response": self.folders.translate(endpoint, params)}
            return 200, "application/json", json.dumps(payload, ensure_ascii=False).encode("utf-8")
        response = self.client.open(endpoint, params, timeout=self.timeout_for(endpoint))
        try:
            status = getattr(response, "status", None) or response.code
            return status, response.headers.get("Content-Type", "application/json"), response.read()
        finally:
            response.close()

    def _store(self, endpoint, params, key, ttl, ctype, body):
        if ttl > 0:
            self.cache.put(key, endpoint, params, ttl, ctype, body)
        if self.policy.is_write(endpoint):
            self._invalidate_after_write(endpoint, params)

    def _invalidate_after_write(self, endpoint, params):
        rule = self.policy.stale_rule(endpoint, dict(params))
        if rule:
            self.cache.invalidate(rule)


class CoverService:
    """Pochettes : cache disque de longue durée, version ancienne servie si Subsonic est injoignable."""

    def __init__(self, client, covers, keys):
        self.client = client
        self.covers = covers
        self.keys = keys

    def get(self, params):
        key = self.keys.for_call("getCoverArt", params)
        cached = self.covers.get(key)
        if cached:
            return ApiResult(200, cached[0], cached[1], "HIT")
        try:
            status, ctype, body = self._download(params)
        except Exception:
            old = self.covers.get(key, allow_stale=True)
            if old:
                return ApiResult(200, old[0], old[1], "HIT")
            raise
        if status == 200 and ctype.startswith("image/"):
            self.covers.put(key, ctype, body)
        return ApiResult(status, ctype, body, "MISS")

    def _download(self, params):
        response = self.client.open("getCoverArt", params)
        try:
            status = getattr(response, "status", None) or response.code
            return status, response.headers.get("Content-Type", "image/jpeg"), response.read()
        finally:
            response.close()
WEBEOF_61
cat > "$APP_DIR/pimedia/server/app.py" <<'WEBEOF_62'
"""Assemblage de l'édition Pi (un seul utilisateur) : crée les objets, les relie, déclare les routes, lance le serveur.

Toutes les dépendances sont créées ici, une seule fois, et passées aux classes qui en ont besoin
(aucune variable globale) : chaque classe peut être testée seule avec des faux."""
import os

from .api import CachedApi, CoverService
from .cache import CoverCache, JsonCache
from .constants import FOREVER
from .controllers.extmusic import ExtMusicController
from .controllers.history import HistoryController
from .controllers.library import CacheController, InfoController, RestController
from .controllers.pages import PagesController
from .controllers.pi import GuestController, PiController, PiState, SystemVolume
from .controllers.player import PlayerController
from .controllers.podcasts import PodcastController
from .controllers.queue import QueueController
from .controllers.settings import SettingsController
from .external import ExternalInfo, FactsBuilder, JsonFetcher, LyricsFinder, MusicBrainz, Wikipedia
from .extmusic.service import ExtMusicService
from .extmusic.sources import JamendoSource, YouTubeSource
from .folders import FolderAdapter
from .guests import GuestWatcher
from .keys import BrowseMode, CacheKeys
from .playback import HifiPlayer
from .podcasts.directories import DirectoryHub, ItunesDirectory, JsonHttp, PodcastIndexDirectory
from .podcasts.feeds import FeedFetcher, FeedReader
from .podcasts.service import PodcastService
from .policy import CachePolicy
from .queue import QueueService
from .remote import DEFAULT_PORT as PHONE_PORT, PhoneQueue, PhoneServer, RemoteController, RemoteTyping
from .transport import HttpApp, Reply, Router, ThreadedServer, make_request_handler
from .upstream import SubsonicClient
from .watcher import LibraryCache, LibraryWatcher, NewestAlbums
from .webfiles import WebFiles
from ..entities import Track
from ..envfile import EnvFile
from ..i18n import Texts
from ..paths import Paths, default_cache_dir, resolve_data_dir
from ..settings import AppSettingsStore, Settings
from ..storage.database import Database
from ..storage.history import SearchHistory
from ..storage.legacy import LegacyImport
from ..storage.playlists import LocalPlaylists
from ..storage.podcasts import PodcastLibrary
from ..storage.queue import PlayQueue
from ..storage.videos import UnplayableVideos


def read_version(code_dir):
    """Version déployée (fichier VERSION de l'archive) ; « dev » quand on lance depuis les sources."""
    try:
        with open(os.path.join(code_dir, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "dev"
    except OSError:
        return "dev"


class Application:
    def __init__(self, code_dir, environ=None, data_dir=None):
        self.environ = os.environ if environ is None else environ
        data_dir = data_dir or resolve_data_dir(code_dir, self.environ)
        self.paths = Paths(code_dir, data_dir, default_cache_dir(self.environ))
        os.makedirs(data_dir, exist_ok=True)
        self.db = Database(self.paths.db_file)
        env_file = EnvFile(self.paths.env_file)
        store = AppSettingsStore(self.db)
        LegacyImport(self.paths, self.db, env_file, store).run()      # anciens config.json et JSON : une seule fois
        self.config = Settings(store, env_file, self.environ)
        self.texts = Texts(self.paths.i18n_dir, self.config.get("language"))
        self.version = read_version(code_dir)
        self.port = int(self.environ.get("PI_MEDIA_PORT", "8099"))
        self.bound_port = self.port
        self.phone_server = None
        self._build_library_relay()
        router = Router()
        self._add_page_routes(router)
        self._add_library_routes(router)
        self._add_screen_routes(router)
        self._add_player_routes(router)
        self._add_podcast_routes(router)
        self._add_extmusic_routes(router)
        self._add_phone_and_queue_routes(router)
        self.http = HttpApp(router, self._on_error)

    # ---------- relais Subsonic (cache, pochettes, informations) ----------
    def _build_library_relay(self):
        self.client = SubsonicClient(self.config)
        self.cache = JsonCache(self.paths.json_dir)
        self.covers_cache = CoverCache(self.paths.cover_dir, FOREVER)
        self.browse = BrowseMode(self.config)
        self.keys = CacheKeys(self.browse)
        self.api = CachedApi(self.client, self.cache, CachePolicy(), self.keys, self.browse)
        self.api.folders = FolderAdapter(self.api)
        self.covers = CoverService(self.client, self.covers_cache, self.keys)
        self.library = LibraryCache(self.cache)
        self.watcher = LibraryWatcher(self.api, self.library, NewestAlbums(self.paths.newest_file))
        fetcher = JsonFetcher()
        musicbrainz = MusicBrainz(fetcher)
        lyrics = LyricsFinder(fetcher, self._subsonic_lyrics)
        facts = FactsBuilder(musicbrainz, Wikipedia(fetcher), self._artist_biography)
        self.external = ExternalInfo(self.cache, self.keys, lyrics, facts, musicbrainz)

    def _subsonic_lyrics(self, artist, title):
        response = self.api.call_json("getLyrics", [("artist", artist), ("title", title)])
        return response.get("lyrics", {}).get("value", "")

    def _artist_biography(self, artist_id):
        response = self.api.call_json("getArtistInfo2", [("id", artist_id)])
        return response.get("artistInfo2", {}).get("biography", "")

    # ---------- routes ----------
    def _add_page_routes(self, router):
        self.pages = PagesController(WebFiles(self.paths))
        for path in ("/", "/index.html"):
            router.add("GET", path, self.pages.index)
        router.add_prefix("GET", "/static/", self.pages.static)
        router.add("GET", "/i18n.json", lambda request: Reply.json(self.texts.section("web.")))   # textes de la page
        router.add("GET", "/health", lambda request: Reply.json({"ok": True, "version": self.version}))
        router.add("GET", "/settings", SettingsController(self.config, self.browse).page)

    def _add_library_routes(self, router):
        info = InfoController(self.external)
        cache = CacheController(self.cache, self.covers_cache, self.library, self.watcher)
        router.add("GET", "/info/genres", info.genres)
        router.add("GET", "/info/lyrics", info.lyrics)
        router.add("GET", "/info/facts", info.facts)
        router.add("GET", "/cache/refresh", cache.refresh_album)
        router.add("GET", "/cache/clear", cache.clear)
        router.add_prefix("GET", "/rest/", RestController(self.api, self.covers, self.client).handle)

    def _add_screen_routes(self, router):
        """Échanges avec le menu tactile, volume, invités AirPlay/Bluetooth, historique des recherches."""
        pi = PiController(PiState(), SystemVolume(), self.browse)
        for name in ("send", "poll", "awake", "quit", "mode"):
            router.add("GET", "/control/" + name, getattr(pi, name))
        router.add("GET", "/control/volume", pi.set_volume)
        self.guests = GuestWatcher()
        guests = GuestController(self.guests)
        router.add("GET", "/control/guest", guests.state)
        router.add("POST", "/control/guest", guests.hand_over)
        history = HistoryController(SearchHistory(self.db))
        router.add("GET", "/ext/history", history.entries)
        router.add("POST", "/ext/history", history.change)

    def _add_player_routes(self, router):
        """Lecture haute fidélité par mpv."""
        socket_dir = self.environ.get("XDG_RUNTIME_DIR") or self.paths.cache_dir
        self.hifi = HifiPlayer(self.config, os.path.join(socket_dir, "pi-media-mpv.sock"),
                               lambda: "http://127.0.0.1:%d" % self.bound_port)
        player = PlayerController(self.hifi)
        router.add("GET", "/player/state", player.state)
        router.add("POST", "/player/cmd", player.command)

    def _add_podcast_routes(self, router):
        http = JsonHttp()
        hub = DirectoryHub(ItunesDirectory(http), PodcastIndexDirectory(http, self.config))
        self.podcasts = PodcastService(self.config, hub, FeedReader(FeedFetcher()), PodcastLibrary(self.db))
        podcasts = PodcastController(self.config, self.podcasts, self.pages)
        router.add("GET", "/podcasts", podcasts.page)
        for name in ("status", "home", "theme", "search", "show", "similar", "library"):
            router.add("GET", "/podcast-api/" + name, getattr(podcasts, name))
        for name in ("subscribe", "unsubscribe", "hide", "progress", "played", "language", "forget"):
            router.add("POST", "/podcast-api/" + name, getattr(podcasts, name))
        router.add("POST", "/podcast-api/key", podcasts.save_key)

    def _add_extmusic_routes(self, router):
        """Jamendo, YouTube et playlists locales."""
        http = JsonHttp()
        sources = [JamendoSource(http, self.config), YouTubeSource(http, self.config)]
        self.extmusic = ExtMusicService(self.config, sources, LocalPlaylists(self.db), UnplayableVideos(self.db))
        ext = ExtMusicController(self.extmusic)
        for name in ("status", "search", "playlists", "playlist", "favorites", "alternative"):
            router.add("GET", "/ext/" + name, getattr(ext, name))
        for name in ("settings", "create", "add", "remove", "delete", "favorite", "unplayable"):
            router.add("POST", "/ext/" + name, getattr(ext, name))

    def _add_phone_and_queue_routes(self, router):
        """File d'attente commune et saisie depuis le téléphone (côté écran du Pi)."""
        self.queue_service = QueueService(PlayQueue(self.db))
        queue = QueueController(self.queue_service)
        router.add("GET", "/queue/state", queue.state)
        router.add("POST", "/queue/save", queue.save)
        router.add("POST", "/queue/take", queue.take)
        self.remote_typing = RemoteTyping()
        remote = RemoteController(self.remote_typing, lambda: self.phone_server.port if self.phone_server else None)
        router.add("GET", "/ext/remote", remote.state)
        router.add("POST", "/ext/remote", remote.renew)
        router.add("POST", "/ext/remote/artists", remote.artists)

    @staticmethod
    def _on_error(error):
        print("erreur : %r" % (error,), flush=True)
        return Reply.json({"error": "erreur interne"}, 500)

    # ---------- démarrage ----------
    def prepare(self):
        """Charge le cache et lance la tâche de fond (préchauffage, nouveaux albums)."""
        self.cache.load()
        self.watcher.start()

    def make_server(self):
        server = ThreadedServer((self.config.bind_address, self.port), make_request_handler(self.http))
        self.bound_port = server.server_address[1]      # port réel (0 dans les tests : choisi par le système)
        return server

    def start_phone_server(self, port=None):
        """Petit serveur séparé, ouvert sur le réseau local, pour les téléphones (désactivable : PHONE_REMOTE=false)."""
        if self.config.get("phone_remote") is False:
            return None
        try:
            phone_queue = PhoneQueue(self.remote_typing, self._search_tracks, self.queue_service)
            self.phone_server = PhoneServer(self.remote_typing, self.paths.web_dir,
                                            port if port is not None else int(self.config.get("phone_port", PHONE_PORT)),
                                            phone_queue=phone_queue)
        except OSError as error:            # port déjà pris : le reste de l'application fonctionne quand même
            print("Saisie depuis le téléphone indisponible :", error, flush=True)
            return None
        return self.phone_server.start()

    def _search_tracks(self, text):
        """Recherche de titres dans la bibliothèque Subsonic (pour les téléphones)."""
        response = self.api.call_json("search3", [("query", text), ("songCount", "20"), ("artistCount", "0"), ("albumCount", "0")])
        tracks = []
        for raw in (response.get("searchResult3") or {}).get("song") or []:
            try:
                tracks.append(Track.from_api(raw))
            except ValueError:
                continue
        return tracks

    def run(self):
        self.prepare()
        self.start_phone_server()
        self.make_server().serve_forever()
WEBEOF_62
cat > "$APP_DIR/pimedia/server/cache.py" <<'WEBEOF_63'
"""Caches sur disque : réponses JSON de Subsonic et pochettes."""
import json
import os
import shutil
import threading
import time


class CacheEntry:
    """Une réponse mise en cache : métadonnées (échéance, type, utilisateur…) et corps."""

    def __init__(self, meta, body):
        self.meta = meta
        self.body = body

    @property
    def ctype(self):
        return self.meta["ctype"]

    def expired(self, now=None):
        return self.meta["exp"] < (now or time.time())


class JsonCache:
    """Réponses JSON : un index en mémoire, les corps sur disque (les plus récents aussi en mémoire)."""

    EXPIRED_KEEP_SECONDS = 30 * 86400      # une entrée périmée depuis plus longtemps est supprimée au démarrage

    def __init__(self, directory, max_entries=200000, max_memory=300):
        self.directory = directory
        self.max_entries = max_entries
        self.max_memory = max_memory
        self._index = {}                   # clé -> métadonnées
        self._memory = {}                  # clé -> CacheEntry
        self._lock = threading.Lock()

    # --- chemins ---
    def _paths(self, key):
        base = os.path.join(self.directory, key)
        return base + ".json", base + ".bin"

    def _remove_files(self, key):
        for path in self._paths(key):
            try:
                os.remove(path)
            except OSError:
                pass

    # --- démarrage ---
    def load(self):
        """Reconstruit l'index à partir des fichiers du disque."""
        os.makedirs(self.directory, exist_ok=True)
        now = time.time()
        for name in os.listdir(self.directory):
            if name.endswith(".json"):
                self._load_one(name[:-5], now)

    def _load_one(self, key, now):
        try:
            with open(self._paths(key)[0], encoding="utf-8") as f:
                meta = json.load(f)
            if meta["exp"] < now - self.EXPIRED_KEEP_SECONDS:
                self._remove_files(key)
            else:
                self._index[key] = meta
        except (OSError, ValueError, KeyError):
            self._remove_files(key)

    # --- lecture / écriture ---
    def get(self, key, allow_stale=False):
        with self._lock:
            entry = self._memory.get(key) or self._read_from_disk(key)
        if entry is None or (entry.expired() and not allow_stale):
            return None
        return entry

    def _read_from_disk(self, key):
        meta = self._index.get(key)
        if meta is None:
            return None
        try:
            with open(self._paths(key)[1], "rb") as f:
                entry = CacheEntry(meta, f.read())
        except OSError:
            self._index.pop(key, None)
            return None
        self._memory[key] = entry
        return entry

    def put(self, key, endpoint, params, ttl, ctype, body):
        meta = {"ep": endpoint, "q": dict(params), "exp": time.time() + ttl, "ctype": ctype}
        if not self._write_files(key, meta, body):
            return
        with self._lock:
            self._index[key] = meta
            self._memory[key] = CacheEntry(meta, body)
            self._trim()

    def _write_files(self, key, meta, body):
        meta_path, body_path = self._paths(key)
        try:
            for path, data, mode in ((body_path, body, "wb"), (meta_path, json.dumps(meta), "w")):
                tmp = path + ".tmp"
                with open(tmp, mode) as f:
                    f.write(data)
                os.replace(tmp, path)
        except OSError:
            return False
        return True

    def _trim(self):
        while len(self._memory) > self.max_memory:
            self._memory.pop(next(iter(self._memory)))
        if len(self._index) > self.max_entries:
            oldest = sorted(self._index, key=lambda k: self._index[k]["exp"])[:500]
            for key in oldest:
                self._drop(key)

    def _drop(self, key):
        self._index.pop(key, None)
        self._memory.pop(key, None)
        self._remove_files(key)

    # --- invalidation ---
    def invalidate(self, predicate):
        """Supprime toutes les entrées dont les métadonnées satisfont predicate."""
        with self._lock:
            for key in [k for k, meta in self._index.items() if predicate(meta)]:
                self._drop(key)

    def clear(self):
        with self._lock:
            self._index.clear()
            self._memory.clear()
        shutil.rmtree(self.directory, ignore_errors=True)
        os.makedirs(self.directory, exist_ok=True)


class CoverCache:
    """Pochettes : un fichier image et un fichier de type par pochette."""

    def __init__(self, directory, ttl):
        self.directory = directory
        self.ttl = ttl
        os.makedirs(directory, exist_ok=True)

    def _paths(self, key):
        return os.path.join(self.directory, key + ".img"), os.path.join(self.directory, key + ".ct")

    def get(self, key, allow_stale=False):
        """Retourne (type, octets) ou None."""
        image, ctype_file = self._paths(key)
        if not os.path.exists(image):
            return None
        if not allow_stale and time.time() - os.path.getmtime(image) >= self.ttl:
            return None
        with open(image, "rb") as f:
            body = f.read()
        try:
            with open(ctype_file, encoding="utf-8") as f:
                ctype = f.read()
        except OSError:
            ctype = "image/jpeg"
        return ctype, body

    def put(self, key, ctype, body):
        image, ctype_file = self._paths(key)
        try:
            with open(image, "wb") as f:
                f.write(body)
            with open(ctype_file, "w", encoding="utf-8") as f:
                f.write(ctype)
        except OSError:
            pass

    def clear(self):
        shutil.rmtree(self.directory, ignore_errors=True)
        os.makedirs(self.directory, exist_ok=True)
WEBEOF_63
cat > "$APP_DIR/pimedia/server/constants.py" <<'WEBEOF_64'
"""Constantes partagées par tout le programme."""

API_VERSION = "1.16.1"
CLIENT_NAME = "pi-media"

# Durées de validité du cache, en secondes
FOREVER = 10 * 365 * 86400      # pochettes, bios, paroles : ne changent pas
LIBRARY_TTL = 30 * 86400        # bibliothèque : renouvelée seulement quand de nouveaux albums arrivent
SHORT_TTL = 300                 # favoris, playlists, recherche
STALE_WHILE_REVALIDATE_MIN_TTL = 3600   # au-delà : on sert l'ancienne version tout de suite et on rafraîchit en fond

# Paramètres d'authentification que le relais ajoute lui-même (le navigateur ne les envoie jamais)
AUTH_PARAMS = frozenset(("u", "t", "s", "p", "v", "c"))

# Appels qui renvoient du binaire (pas de cache JSON)
BINARY_ENDPOINTS = frozenset(("stream", "download", "hls", "getCoverArt", "getAvatar"))

# Appels qui modifient des données : le cache concerné est invalidé après coup
WRITE_ENDPOINTS = frozenset(("star", "unstar", "createPlaylist", "updatePlaylist", "deletePlaylist", "scrobble"))
STAR_AFFECTED = frozenset(("getStarred2", "getAlbum", "getPlaylist", "getTopSongs", "search3"))
PLAYLIST_AFFECTED = frozenset(("getPlaylists", "getPlaylist"))

# Appels « bibliothèque » (vidés quand de nouveaux albums arrivent ou sur demande)
LIBRARY_ENDPOINTS = frozenset(("getArtists", "getArtist", "getAlbum", "getGenres",
                               "getAlbumList2", "search3", "getStarred2"))
# Appels ID3 traduits en parcours par dossiers quand ce mode est choisi
FOLDER_ENDPOINTS = frozenset(("getArtists", "getArtist", "getAlbum", "getAlbumList2", "getStarred2",
                              "search3", "getArtistInfo2", "getSimilarSongs2"))

BROWSE_MODES = ("folders", "tags")

# Sécurité : les écritures demandent cet en-tête, qu'une page d'un autre site ne peut pas ajouter
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "pm"
LOOPBACK = ("127.0.0.1", "::1")
WEBEOF_64
cat > "$APP_DIR/pimedia/server/external.py" <<'WEBEOF_65'
"""Sources externes : paroles (LRCLIB, lyrics.ovh), anecdotes et photo (MusicBrainz, Wikipédia)."""
import json
import re
import time
import urllib.parse
import urllib.request

from .constants import FOREVER

USER_AGENT = "PiMediaStation/1.0 (lecteur personnel)"
EMPTY_RESULT_TTL = 86400            # un résultat vide est retenté le lendemain

TITLE_NOISE = r"remaster|live|version|edit|mix|feat|ft\.|radio|mono|stereo|bonus|deluxe|acoustic"
MUSIC_WORDS = r"chant|music|band|group|rap|dj|compos|singer|duo|trio|artist|musici|pianist|guitar"


# ---------- fonctions de texte (pures) ----------
def clean_title(title):
    """Titre sans les mentions « (Remastered) », « - Live », « feat. … » qui gênent les recherches."""
    title = re.sub(r"\s*[\(\[][^)\]]*(%s)[^)\]]*[\)\]]" % TITLE_NOISE, "", title, flags=re.I)
    title = re.sub(r"\s+-\s+(.*(remaster|live|version|edit|mix|mono|stereo|bonus|single).*)$", "", title, flags=re.I)
    title = re.sub(r"\s+(feat\.?|ft\.?|featuring)\s+.*$", "", title, flags=re.I)
    return title.strip() or title


def first_artist(artist):
    """Premier artiste d'une mention « A feat. B »."""
    head = re.split(r"\s+(?:feat\.?|ft\.?|featuring)\s+", artist, maxsplit=1, flags=re.I)[0].strip()
    return head or artist


def sentences(text, maximum, min_len=45, max_len=280):
    """Phrases d'un texte (HTML retiré) ni trop courtes ni trop longues."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.split(r"(?:Read more on Last\.fm|Lire la suite|Lire plus)", text)[0]
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ«\"])", text)
    return [p.strip() for p in parts if min_len <= len(p.strip()) <= max_len][:maximum]


def distinct_pairs(pairs):
    seen = []
    for pair in pairs:
        if pair not in seen:
            seen.append(pair)
    return seen


# ---------- accès HTTP ----------
class JsonFetcher:
    def get(self, url, timeout=8):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))

    def try_get(self, url, timeout=8):
        """Comme get, mais retourne None au lieu de lever une erreur."""
        try:
            return self.get(url, timeout)
        except Exception:
            return None


def query_url(base, params):
    return base + "?" + urllib.parse.urlencode(params)


# ---------- paroles ----------
class LyricsFinder:
    """LRCLIB d'abord (version synchronisée si possible), puis lyrics.ovh, puis le serveur Subsonic."""

    LRCLIB = "https://lrclib.net/api/"
    MAX_DURATION_GAP = 10

    def __init__(self, fetcher, subsonic_lyrics):
        self.fetcher = fetcher
        self.subsonic_lyrics = subsonic_lyrics      # fonction (artiste, titre) -> texte ou ""

    def find(self, artist, title, album="", duration=0):
        attempts = distinct_pairs([(title, artist), (clean_title(title), first_artist(artist))])
        best = self._best_lrclib(self._lrclib_candidates(attempts, album, duration), duration)
        if best:
            return {"synced": best.get("syncedLyrics") or "", "plain": best.get("plainLyrics") or "", "src": "LRCLIB"}
        plain = self._lyrics_ovh(attempts) or self._subsonic(artist, title)
        return plain or {}

    # --- LRCLIB ---
    def _lrclib(self, path, params):
        return self.fetcher.try_get(query_url(self.LRCLIB + path, params))

    def _lrclib_candidates(self, attempts, album, duration):
        candidates = []
        for title, artist in attempts:
            candidates += self._exact_and_search(title, artist, album, duration)
            if self._has_synced(candidates):
                return candidates
        if not self._has_synced(candidates):
            found = self._lrclib("search", [("q", "%s %s" % (clean_title(attempts[0][0]), first_artist(attempts[0][1])))])
            candidates += found if isinstance(found, list) else []
        return candidates

    def _exact_and_search(self, title, artist, album, duration):
        params = [("artist_name", artist), ("track_name", title)]
        if album:
            params.append(("album_name", album))
        if duration:
            params.append(("duration", str(int(duration))))
        found = []
        exact = self._lrclib("get", params)
        if isinstance(exact, dict):
            found.append(exact)
        similar = self._lrclib("search", [("track_name", title), ("artist_name", artist)])
        return found + (similar if isinstance(similar, list) else [])

    @staticmethod
    def _has_synced(candidates):
        return any(c.get("syncedLyrics") for c in candidates)

    def _best_lrclib(self, candidates, duration):
        usable = [c for c in candidates if c.get("syncedLyrics") or c.get("plainLyrics")]

        def gap(candidate):
            return abs((candidate.get("duration") or 0) - duration) if duration else 0
        synced = [c for c in usable if c.get("syncedLyrics") and (not duration or gap(c) <= self.MAX_DURATION_GAP)]
        pool = synced or usable
        return min(pool, key=gap) if pool else None

    # --- sources de secours ---
    def _lyrics_ovh(self, attempts):
        for title, artist in attempts:
            url = "https://api.lyrics.ovh/v1/%s/%s" % (urllib.parse.quote(artist, safe=""),
                                                       urllib.parse.quote(title, safe=""))
            data = self.fetcher.try_get(url, timeout=10)
            text = ((data or {}).get("lyrics") or "").strip()
            if text:
                return {"synced": "", "plain": text, "src": "lyrics.ovh"}
        return None

    def _subsonic(self, artist, title):
        try:
            text = (self.subsonic_lyrics(artist, title) or "").strip()
        except Exception:
            return None
        return {"synced": "", "plain": text, "src": "Subsonic"} if text else None


# ---------- anecdotes, genres, photo ----------
class MusicBrainz:
    BASE = "https://musicbrainz.org/ws/2/"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def genres(self, artist):
        """Genres d'après MusicBrainz (vocabulaire commun, plus fiable que les tags des fichiers)."""
        data = self.fetcher.get(query_url(self.BASE + "artist", [
            ("query", 'artist:"%s"' % artist.replace('"', "")), ("fmt", "json"), ("limit", "3")]))
        for found in data.get("artists", []):
            if found.get("score", 0) >= 90:
                tags = sorted(found.get("tags", []), key=lambda t: -t.get("count", 0))
                names = [t["name"] for t in tags if t.get("count", 0) >= 1][:8]
                if names:
                    return {"genres": names}
        return {}

    def release_fact(self, artist, album):
        """« Album X, sorti en 1999 (il y a N ans) » d'après le groupe de sorties (les recherches par titre de chanson sont peu fiables)."""
        if not album:
            return None
        query = 'releasegroup:"%s" AND artist:"%s"' % (album.replace('"', ""), artist.replace('"', ""))
        data = self.fetcher.try_get(query_url(self.BASE + "release-group", [
            ("query", query), ("fmt", "json"), ("limit", "3")]))
        for group in (data or {}).get("release-groups", []):
            year = re.match(r"(\d{4})", group.get("first-release-date") or "")
            if group.get("score", 0) >= 90 and year:
                return self._describe(group.get("title") or album, int(year.group(1)))
        return None

    @staticmethod
    def _describe(title, year):
        text = "Album « %s », sorti en %d" % (title, year)
        age = time.localtime().tm_year - year
        if age > 0:
            text += " (il y a %d an%s)" % (age, "s" if age > 1 else "")
        return text + "."


class Wikipedia:
    LANGUAGES = ("fr", "en")

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def _summary(self, lang, page):
        url = "https://%s.wikipedia.org/api/rest_v1/page/summary/%s" % (
            lang, urllib.parse.quote(page.replace(" ", "_"), safe=""))
        return self.fetcher.get(url)

    def song_facts(self, artist, title):
        last_name = artist.split()[-1].lower() if artist else ""
        for lang in self.LANGUAGES:
            try:
                facts = self._song_facts_in(lang, artist, title, last_name)
            except Exception:
                continue
            if facts:
                return facts
        return []

    def _song_facts_in(self, lang, artist, title, last_name):
        word = "chanson" if lang == "fr" else "song"
        hits = self.fetcher.get(query_url("https://%s.wikipedia.org/w/api.php" % lang, [
            ("action", "query"), ("list", "search"), ("format", "json"), ("srlimit", "4"),
            ("srsearch", '"%s" %s %s' % (title, artist, word))]))
        for hit in hits.get("query", {}).get("search", []):
            page = self._summary(lang, hit["title"])
            extract = page.get("extract", "")
            low = extract.lower()
            if title.lower()[:20] in low and last_name in low and page.get("type") == "standard":
                found = sentences(extract, 6)
                if found:
                    return found
        return []

    def artist_photo(self, artist):
        """Photo de l'artiste, seulement si la page est bien celle d'un musicien ou d'un groupe."""
        for lang in self.LANGUAGES:
            try:
                page = self._summary(lang, artist)
            except Exception:
                continue
            desc = ((page.get("description") or "") + " " + (page.get("extract") or "")[:200]).lower()
            if page.get("type") == "standard" and page.get("thumbnail") and re.search(MUSIC_WORDS, desc):
                return page["thumbnail"]["source"]
        return ""


class FactsBuilder:
    """Assemble anecdotes (sortie de l'album, Wikipédia, biographie Subsonic), biographie et photo."""

    def __init__(self, musicbrainz, wikipedia, artist_biography):
        self.musicbrainz = musicbrainz
        self.wikipedia = wikipedia
        self.artist_biography = artist_biography    # fonction (id artiste) -> texte

    def build(self, artist, title, artist_id, album=""):
        release = self.musicbrainz.release_fact(artist, album)
        song_facts = self.wikipedia.song_facts(artist, title)
        biography = self._biography(artist_id)
        facts = [{"k": "Sortie", "t": release}] if release else []
        facts += self._interleave(song_facts, sentences(biography, 5))
        photo = self.wikipedia.artist_photo(artist)
        full_bio = " ".join(sentences(biography, 12, 20, 400))
        result = {"facts": facts, "img": photo, "bio": full_bio}
        return result if (facts or photo or full_bio) else {}

    def _biography(self, artist_id):
        if not artist_id:
            return ""
        try:
            return self.artist_biography(artist_id) or ""
        except Exception:
            return ""

    @staticmethod
    def _interleave(song_facts, bio_facts):
        facts = []
        for i in range(max(len(song_facts), len(bio_facts))):
            if i < len(song_facts):
                facts.append({"k": "La chanson", "t": song_facts[i]})
            if i < len(bio_facts):
                facts.append({"k": "L’artiste", "t": bio_facts[i]})
        return facts


# ---------- façade avec cache ----------
class ExternalInfo:
    """Résultats des sources externes, conservés dans le cache (définitivement s'ils ne sont pas vides)."""

    def __init__(self, cache, keys, lyrics, facts, musicbrainz):
        self.cache = cache
        self.keys = keys
        self.lyrics_finder = lyrics
        self.facts_builder = facts
        self.musicbrainz = musicbrainz

    def lyrics(self, artist, title, album="", duration=0):
        params = [("artist", artist), ("title", title), ("album", album), ("duration", str(duration))]
        return self._cached("lyrics2", params, lambda: self.lyrics_finder.find(artist, title, album, duration))

    def facts(self, artist, title, artist_id, album=""):
        params = [("artist", artist), ("title", title), ("aid", artist_id), ("album", album)]
        return self._cached("facts", params, lambda: self.facts_builder.build(artist, title, artist_id, album))

    def genres(self, artist):
        return self._cached("genres", [("artist", artist)], lambda: self.musicbrainz.genres(artist))

    def _cached(self, kind, params, builder):
        """Retourne le corps JSON (octets), depuis le cache ou après calcul."""
        key = self.keys.for_call("ext-" + kind, params)
        entry = self.cache.get(key)
        if entry:
            return entry.body
        try:
            data = builder()
        except Exception:
            data = {}
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.cache.put(key, "ext", params, FOREVER if data else EMPTY_RESULT_TTL, "application/json", body)
        return body
WEBEOF_65
cat > "$APP_DIR/pimedia/server/folders.py" <<'WEBEOF_66'
"""Mode « dossiers » : traduit les appels de l'API par tags (ID3) en appels de l'API par dossiers,
pour retrouver le classement de l'interface Subsonic d'origine."""
import re
import unicodedata

from .constants import API_VERSION


# ---------- fonctions pures ----------
def as_list(value):
    """Subsonic renvoie un objet seul ou une liste : on veut toujours une liste."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def normalize_name(name):
    """Nom comparable : sans accents, sans majuscules, sans « the », sans ponctuation."""
    text = unicodedata.normalize("NFD", (name or "").lower())
    text = re.sub(r"[̀-ͯ]", "", text)
    text = re.sub(r"^the\s+", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def merge_artists(artists):
    """Le même artiste présent dans plusieurs dossiers (FLAC et MP3, Abba / ABBA) ne forme qu'une entrée.
    L'identifiant fusionné est « id1|id2 » ; getArtist rassemble alors les albums de chaque dossier."""
    groups, order = {}, []
    for artist in artists:
        key = normalize_name(artist.get("name")) or artist.get("id")
        if key not in groups:
            groups[key] = dict(artist)
            order.append(key)
        elif artist["id"] not in groups[key]["id"].split("|"):
            groups[key]["id"] += "|" + artist["id"]
    return [groups[key] for key in order]


def first_id(merged_id):
    return merged_id.split("|")[0]


def pick_params(params, *names):
    return [(k, v) for k, v in params if k in names]


def with_first_id(params):
    """Remplace un identifiant fusionné par son premier élément (appels qui n'en acceptent qu'un)."""
    return [(k, first_id(v) if k == "id" else v) for k, v in params]


def to_album(child, artist=None, artist_id=None):
    """Un dossier (ou une entrée d'album) Subsonic, au format « album » de l'API ID3."""
    album = {"id": child["id"], "name": child.get("title") or child.get("album") or child.get("name") or "",
             "artist": child.get("artist") or artist or "", "artistId": artist_id or child.get("parent"),
             "coverArt": child.get("coverArt") or child["id"], "year": child.get("year"),
             "songCount": child.get("songCount"), "duration": child.get("duration"),
             "starred": child.get("starred")}
    return {k: v for k, v in album.items() if v is not None}


def sort_tracks(songs):
    songs.sort(key=lambda c: (c.get("discNumber") or 0, c.get("track") or 0))
    return songs


# ---------- adaptateur ----------
class FolderAdapter:
    MAX_SUBFOLDERS = 20          # sous-dossiers explorés pour un album en plusieurs CD
    MAX_DEPTH = 2

    def __init__(self, api):
        self.api = api
        self._handlers = {
            "getArtists": self._artists, "getArtist": self._artist, "getAlbum": self._album,
            "getAlbumList2": self._album_list, "getStarred2": self._starred, "search3": self._search,
            "getArtistInfo2": self._artist_info, "getSimilarSongs2": self._similar_songs,
        }

    def translate(self, endpoint, params):
        """Contenu de « subsonic-response » pour l'appel ID3 demandé."""
        handler = self._handlers.get(endpoint)
        if handler is None:
            raise RuntimeError("non géré")
        return dict(handler(params), status="ok", version=API_VERSION)

    # --- accès ---
    def _call(self, endpoint, params=()):
        return self.api.call_json(endpoint, params)

    def _directory(self, dir_id):
        return self._call("getMusicDirectory", [("id", dir_id)])["directory"]

    def _songs_in(self, dir_id, depth=0):
        """Titres d'un dossier ; s'il n'en contient pas, on descend dans ses sous-dossiers (CD1, CD2…)."""
        directory = self._directory(dir_id)
        kids = as_list(directory.get("child"))
        songs = [c for c in kids if not c.get("isDir")]
        if not songs and depth < self.MAX_DEPTH:
            for sub in [c for c in kids if c.get("isDir")][:self.MAX_SUBFOLDERS]:
                songs += self._songs_in(sub["id"], depth + 1)[1]
        return directory, songs

    # --- artistes ---
    def _artists(self, params):
        indexes = self._call("getIndexes").get("indexes") or {}
        groups = as_list(indexes.get("index"))
        everyone = [{"id": a["id"], "name": a.get("name", "")}
                    for g in groups for a in as_list(g.get("artist"))]
        merged = {first_id(a["id"]): a for a in merge_artists(everyone)}
        return {"artists": {"index": self._regroup(groups, merged)}}

    @staticmethod
    def _regroup(groups, merged):
        result = []
        for group in groups:
            kept = [merged[a["id"]] for a in as_list(group.get("artist")) if a["id"] in merged]
            if kept:
                result.append({"name": group.get("name", "#"), "artist": kept})
        return result

    def _artist(self, params):
        artist_id = dict(params)["id"]
        albums, name, seen = [], "", set()
        for folder_id in artist_id.split("|"):
            directory = self._directory(folder_id)
            name = name or directory.get("name", "")
            for album in self._albums_of_folder(directory, folder_id, artist_id):
                key = normalize_name(album.get("name"))
                if key not in seen:                 # même album présent dans deux dossiers
                    seen.add(key)
                    albums.append(album)
        return {"artist": {"id": artist_id, "name": name, "albumCount": len(albums), "album": albums}}

    @staticmethod
    def _albums_of_folder(directory, folder_id, artist_id):
        kids = as_list(directory.get("child"))
        albums = [to_album(c, directory.get("name"), artist_id) for c in kids if c.get("isDir")]
        if any(not c.get("isDir") for c in kids):   # titres posés directement dans le dossier de l'artiste
            albums.append(to_album({"id": folder_id, "title": "Titres seuls"}, directory.get("name"), artist_id))
        return albums

    # --- albums ---
    def _album(self, params):
        album_id = dict(params)["id"]
        directory, songs = self._songs_in(album_id)
        artist_id = directory.get("parent")
        for song in sort_tracks(songs):
            song.setdefault("artistId", artist_id)
            song.setdefault("albumId", album_id)
        first = songs[0] if songs else {}
        return {"album": {
            "id": album_id, "name": directory.get("name", ""), "artist": first.get("artist", ""),
            "artistId": artist_id, "coverArt": directory.get("coverArt") or album_id, "year": first.get("year"),
            "songCount": len(songs), "duration": sum(c.get("duration") or 0 for c in songs), "song": songs}}

    def _album_list(self, params):
        wanted = pick_params(params, "type", "size", "offset", "genre", "fromYear", "toYear")
        result = self._call("getAlbumList", wanted).get("albumList") or {}
        return {"albumList2": {"album": [to_album(c) for c in as_list(result.get("album"))]}}

    # --- favoris et recherche ---
    def _starred(self, params):
        found = self._call("getStarred").get("starred") or {}
        return {"starred2": self._library_sections(found)}

    def _search(self, params):
        wanted = pick_params(params, "query", "artistCount", "albumCount", "songCount")
        found = self._call("search2", wanted).get("searchResult2") or {}
        return {"searchResult3": self._library_sections(found)}

    @staticmethod
    def _library_sections(found):
        return {"artist": merge_artists(as_list(found.get("artist"))),
                "album": [to_album(c) for c in as_list(found.get("album"))],
                "song": as_list(found.get("song"))}

    # --- informations ---
    def _artist_info(self, params):
        wanted = pick_params(with_first_id(params), "id", "count", "includeNotPresent")
        return {"artistInfo2": self._call("getArtistInfo", wanted).get("artistInfo") or {}}

    def _similar_songs(self, params):
        wanted = pick_params(with_first_id(params), "id", "count")
        return {"similarSongs2": self._call("getSimilarSongs", wanted).get("similarSongs") or {}}
WEBEOF_66
cat > "$APP_DIR/pimedia/server/guests.py" <<'WEBEOF_67'
"""Invités AirPlay et Bluetooth (écran du Pi) : savoir si un téléphone joue, ou attend en pause,
et lui demander de lancer la lecture quand vient son tour.

- « joue » : un flux audio AirPlay (shairport-sync) ou Bluetooth (bluez) est actif dans PipeWire (pactl) ;
- « attend » : le téléphone est connecté mais en pause (lecteur MPRIS visible par playerctl) ;
- « lecture » : playerctl envoie Play au téléphone (AVRCP en Bluetooth, DACP en AirPlay)."""
import re
import shutil
import subprocess
import threading
import time

SOURCES = (("airplay", ("shairport",), "AirPlay"), ("bluetooth", ("bluez", "bluetooth"), "Bluetooth"))
WAITING_STATUSES = ("Paused", "Stopped")
WAITING_MAX_AGE = 600            # un téléphone resté en pause plus de 10 minutes n'est plus « en attente »
CACHE_SECONDS = 1.0


def source_of(name):
    """« airplay », « bluetooth » ou None, d'après un nom de programme ou de lecteur."""
    lowered = (name or "").lower()
    for key, words, _ in SOURCES:
        if any(w in lowered for w in words):
            return key
    return None


def label_of(source):
    return next((label for key, _, label in SOURCES if key == source), "")


def parse_sink_inputs(text):
    """Sortie de « pactl list sink-inputs » -> [{"name", "corked"}]."""
    streams, current = [], None
    for line in text.splitlines():
        if re.match(r"Sink Input #\d+", line):
            current = {"name": "", "corked": False}
            streams.append(current)
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("Corked:"):
            current["corked"] = stripped.split(":", 1)[1].strip() == "yes"
        elif stripped.startswith(("application.process.binary", "application.name")) and not current["name"]:
            current["name"] = stripped.split("=", 1)[1].strip().strip('"')
    return streams


class SystemAudio:
    """Accès au système (remplacé par un faux dans les tests)."""

    @staticmethod
    def _run(args):
        if not shutil.which(args[0]):
            return ""
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    def sink_inputs(self):
        return parse_sink_inputs(self._run(["pactl", "list", "sink-inputs"]))

    def players(self):
        """{nom du lecteur MPRIS: statut}"""
        names = self._run(["playerctl", "-l"]).split()
        return {name: self._run(["playerctl", "-p", name, "status"]).strip() for name in names}

    def play(self, player):
        self._run(["playerctl", "-p", player, "play"])      # le téléphone peut ignorer la demande : la page le verra


class GuestWatcher:
    def __init__(self, system=None, clock=time.time):
        self.system = system or SystemAudio()
        self.clock = clock
        self._lock = threading.Lock()
        self._waiting_since = {}         # lecteur -> instant où il a été vu en pause pour la première fois
        self._cached = None
        self._cached_at = 0

    def state(self):
        """{"source", "label", "status": "playing" | "waiting" | None, "player"}"""
        with self._lock:
            now = self.clock()
            if self._cached is None or now - self._cached_at >= CACHE_SECONDS:
                self._cached = self._compute(now)
                self._cached_at = now
            return dict(self._cached)

    def _compute(self, now):
        playing = next((source_of(s["name"]) for s in self.system.sink_inputs()
                        if not s["corked"] and source_of(s["name"])), None)
        players = {name: status for name, status in self.system.players().items() if source_of(name)}
        self._waiting_since = {p: t for p, t in self._waiting_since.items()
                               if players.get(p) in WAITING_STATUSES}
        if playing:
            return {"source": playing, "label": label_of(playing), "status": "playing", "player": None}
        for player, status in players.items():
            if status in WAITING_STATUSES:
                since = self._waiting_since.setdefault(player, now)
                if now - since <= WAITING_MAX_AGE:
                    source = source_of(player)
                    return {"source": source, "label": label_of(source), "status": "waiting", "player": player}
        return {"source": None, "label": "", "status": None, "player": None}

    def hand_over(self):
        """C'est au téléphone : on lui envoie « lecture ». False si aucun téléphone n'attend."""
        current = self.state()
        if current["status"] != "waiting" or not current["player"]:
            return False
        self.system.play(current["player"])
        with self._lock:
            self._cached = None              # l'état change : on relira tout de suite
        return True
WEBEOF_67
cat > "$APP_DIR/pimedia/server/keys.py" <<'WEBEOF_68'
"""Mode de navigation (dossiers ou tags) et construction des clés de cache."""
import hashlib
import urllib.parse

from .constants import BROWSE_MODES, FOLDER_ENDPOINTS


class BrowseMode:
    """Classement de la bibliothèque : « folders » (arborescence, comme l'interface Subsonic d'origine)
    ou « tags » (tags ID3). Réglage enregistré en base."""

    def __init__(self, config):
        self.config = config
        saved = config.get("browse_mode")
        self._mode = saved if saved in BROWSE_MODES else "folders"

    def current(self):
        return self._mode

    def set(self, mode):
        if mode in BROWSE_MODES:
            self._mode = mode
            self.config.update(browse_mode=mode)

    def uses_folders(self, endpoint):
        return self.current() == "folders" and endpoint in FOLDER_ENDPOINTS


class CacheKeys:
    """Clé de cache d'un appel : l'appel lui-même et le mode de navigation."""

    def __init__(self, browse):
        self.browse = browse

    def for_call(self, endpoint, params):
        suffix = "|F2" if self.browse.uses_folders(endpoint) else ""
        raw = endpoint + "?" + urllib.parse.urlencode(sorted(params)) + suffix
        return hashlib.sha1(raw.encode()).hexdigest()
WEBEOF_68
cat > "$APP_DIR/pimedia/server/playback.py" <<'WEBEOF_69'
"""Lecture haute fidélité sur le Pi : le son est joué par mpv au lieu du navigateur.

Chromium convertit tout en 48 kHz ; mpv envoie chaque fichier à sa fréquence d'origine (44,1, 96, 192 kHz…)
et enchaîne les titres sans blanc. La page garde sa file d'attente et pilote mpv comme un élément audio.

mpv tourne en arrière-plan, piloté par son interface JSON (socket Unix, une commande par ligne)."""
import itertools
import json
import os
import socket
import subprocess
import threading
import time
import urllib.parse

CLIENT_NAME = "pi-media-hifi"          # nom du flux audio : le menu le reconnaît comme « lecteur de la page »
OBSERVED = ("time-pos", "duration", "pause", "idle-active", "playlist-pos", "playlist-count")
STREAM_PATH = "/rest/stream.view"


def mpv_command(socket_path):
    return ["mpv", "--idle=yes", "--no-video", "--no-terminal", "--audio-display=no",
            "--gapless-audio=yes", "--prefetch-playlist=yes", "--cache=yes",
            "--audio-client-name=" + CLIENT_NAME, "--input-ipc-server=" + socket_path]


class MpvError(Exception):
    pass


class MpvConnection:
    """Un processus mpv et sa connexion de commande. Redémarre mpv s'il s'est arrêté."""

    def __init__(self, socket_path, command=None, on_event=None):
        self.socket_path = socket_path
        self.command = command or mpv_command(socket_path)
        self.on_event = on_event or (lambda event: None)
        self.process = None
        self.sock = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._waiting = {}

    def ensure(self):
        with self._lock:
            if self.sock is not None and self.process is not None and self.process.poll() is None:
                return
            self._start()

    def _start(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        try:
            self.process = subprocess.Popen(self.command, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error:
            raise MpvError("mpv introuvable (%s)" % error)
        deadline = time.time() + 5
        while time.time() < deadline:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(self.socket_path)
                self.sock = sock
                threading.Thread(target=self._read, args=(sock,), daemon=True).start()
                for number, name in enumerate(OBSERVED, start=1):
                    self._send({"command": ["observe_property", number, name]})
                return
            except OSError:
                sock.close()
                time.sleep(0.1)
        raise MpvError("mpv ne répond pas")

    def _send(self, message):
        self.sock.sendall((json.dumps(message) + "\n").encode("utf-8"))

    def call(self, *args, timeout=3):
        """Commande mpv ; renvoie sa donnée, ou lève MpvError."""
        self.ensure()
        request_id = next(self._ids)
        done = threading.Event()
        slot = {"event": done}
        self._waiting[request_id] = slot
        try:
            with self._lock:
                self._send({"command": list(args), "request_id": request_id})
        except OSError as error:
            self._waiting.pop(request_id, None)
            self.sock = None
            raise MpvError(str(error))
        if not done.wait(timeout):
            self._waiting.pop(request_id, None)
            raise MpvError("mpv ne répond pas")
        reply = slot["reply"]
        if reply.get("error") not in (None, "success"):
            raise MpvError(reply["error"])
        return reply.get("data")

    def _read(self, sock):
        buffer = b""
        while True:
            try:
                chunk = sock.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                try:
                    message = json.loads(line.decode("utf-8"))
                except ValueError:
                    continue
                slot = self._waiting.pop(message.get("request_id"), None) if "request_id" in message else None
                if slot is not None:
                    slot["reply"] = message
                    slot["event"].set()
                elif "event" in message:
                    self.on_event(message)
        if self.sock is sock:
            self.sock = None

    def stop(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(2)
            except subprocess.TimeoutExpired:
                self.process.kill()


class HifiPlayer:
    """État de lecture que la page interroge, et commandes qu'elle envoie."""

    def __init__(self, config, socket_path, local_base, command=None):
        self.config = config
        self.local_base = local_base           # fonction : « http://127.0.0.1:8099 » (port réel du serveur)
        self.mpv = MpvConnection(socket_path, command, self._on_event)
        self._lock = threading.Lock()
        self.props = {}
        self.current = ""                      # adresse (telle que la page la connaît) du titre en cours
        self.queued = ""                       # titre suivant préchargé (enchaînement sans blanc)
        self.ended = 0                         # compteurs : la page voit qu'un titre s'est fini ou a échoué
        self.errors = 0

    # ---------- réglage ----------
    @property
    def enabled(self):
        return bool(self.config.get("hifi_playback"))

    def set_enabled(self, on):
        self.config.update(hifi_playback=bool(on))
        if not on:
            self._safe("stop")

    # ---------- état ----------
    def state(self):
        with self._lock:
            props = dict(self.props)
            return {"enabled": self.enabled, "url": self.current, "queued": self.queued,
                    "pos": props.get("time-pos") or 0, "duration": props.get("duration") or 0,
                    "paused": bool(props.get("pause")) or bool(props.get("idle-active", True)),
                    "idle": bool(props.get("idle-active", True)), "ended": self.ended, "errors": self.errors}

    def _on_event(self, event):
        with self._lock:
            if event["event"] == "property-change":
                self.props[event["name"]] = event.get("data")
            elif event["event"] == "end-file":
                reason = event.get("reason")
                if reason == "error":
                    self.errors += 1
                elif reason == "eof":
                    self.ended += 1
                    if self.queued:                # mpv enchaîne seul sur le titre préchargé
                        self.current, self.queued = self.queued, ""

    # ---------- commandes ----------
    def resolve(self, url):
        """Adresse donnée par la page -> adresse jouée par mpv. Seuls le flux Subsonic du relais local
        et les adresses web publiques (radio, Jamendo) sont acceptés."""
        parts = urllib.parse.urlsplit(url or "")
        if not parts.scheme and parts.path == STREAM_PATH:
            return self.local_base() + url
        if parts.scheme in ("http", "https") and parts.hostname and parts.hostname not in ("localhost", "127.0.0.1"):
            return url
        raise ValueError("adresse refusée")

    def load(self, url):
        target = self.resolve(url)
        with self._lock:
            already_playing = url == self.current and url and not self.props.get("idle-active", True)
            if not already_playing:
                self.current, self.queued = url, ""
        if not already_playing:                     # sinon : enchaîné tout seul par mpv, rien à recharger
            self.mpv.call("loadfile", target, "replace")
        self.mpv.call("set_property", "pause", False)

    def preload(self, url):
        """Titre suivant ajouté derrière le titre en cours : mpv l'enchaîne sans blanc."""
        if not url:
            return self.drop_preload()
        target = self.resolve(url)
        with self._lock:
            if url == self.queued:
                return
            self.queued = url
        self._safe("playlist-clear")               # retire tout sauf le titre en cours (ancien préchargement, titres joués)
        self.mpv.call("loadfile", target, "append")

    def drop_preload(self):
        with self._lock:
            self.queued = ""
        self._safe("playlist-clear")

    def pause(self, paused):
        self.mpv.call("set_property", "pause", bool(paused))

    def seek(self, seconds):
        self.mpv.call("seek", float(seconds), "absolute")

    def volume(self, level):
        self.mpv.call("set_property", "volume", max(0, min(100, float(level))))

    def stop(self):
        with self._lock:
            self.current = self.queued = ""
        self._safe("stop")

    def _safe(self, *args):
        try:
            self.mpv.call(*args)
        except MpvError:
            pass
WEBEOF_69
cat > "$APP_DIR/pimedia/server/policy.py" <<'WEBEOF_70'
"""Règles de cache : durée de vie de chaque appel et ce qu'il faut vider après une modification."""
from .constants import (FOREVER, LIBRARY_TTL, PLAYLIST_AFFECTED, SHORT_TTL, STAR_AFFECTED,
                        WRITE_ENDPOINTS)


class CachePolicy:
    TTLS = {
        "getArtists": LIBRARY_TTL, "getArtist": LIBRARY_TTL, "getAlbum": LIBRARY_TTL,
        "getGenres": LIBRARY_TTL, "getArtistInfo2": FOREVER, "getTopSongs": FOREVER,
        "getInternetRadioStations": 3600, "getPlaylists": SHORT_TTL, "getPlaylist": SHORT_TTL,
        "getStarred2": SHORT_TTL, "search3": SHORT_TTL,
    }
    RECENT_ALBUM_LISTS = ("recent", "frequent")     # changent à chaque écoute : cache très court

    def ttl_for(self, endpoint, params):
        """Durée de validité en secondes (0 = jamais en cache). params : dict."""
        if endpoint == "getAlbumList2":
            return self._album_list_ttl(params.get("type"))
        return self.TTLS.get(endpoint, 0)

    def _album_list_ttl(self, list_type):
        if list_type == "random":
            return 0
        if list_type in self.RECENT_ALBUM_LISTS:
            return 30
        return LIBRARY_TTL          # « newest » inclus : vidé quand de nouveaux albums sont détectés

    def is_write(self, endpoint):
        return endpoint in WRITE_ENDPOINTS

    def stale_rule(self, endpoint, params):
        """Après une modification, retourne le filtre des entrées de cache devenues fausses (ou None)."""
        if endpoint in ("star", "unstar"):
            return lambda meta: meta["ep"] in STAR_AFFECTED
        if endpoint in ("createPlaylist", "updatePlaylist", "deletePlaylist"):
            return lambda meta: meta["ep"] in PLAYLIST_AFFECTED
        if endpoint == "scrobble" and params.get("submission") == "true":
            return lambda meta: (meta["ep"] == "getAlbumList2"
                                 and meta["q"].get("type") in self.RECENT_ALBUM_LISTS)
        return None
WEBEOF_70
cat > "$APP_DIR/pimedia/server/queue.py" <<'WEBEOF_71'
"""File d'attente commune : ce que l'écran du Pi envoie (sa file) et ce que les téléphones demandent (ajouts)."""
from ..entities import Track

PHONE = "phone"
UPCOMING_FOR_PHONE = 20


class QueueService:
    def __init__(self, queue):
        self.queue = queue

    # --- écran du Pi ---
    def state(self):
        snapshot = self.queue.snapshot()
        return dict(snapshot.to_api(), pending=[r.to_api() for r in self.queue.pending()])

    def save_from_screen(self, body):
        """body : {items: [{track, addedBy}], currentIndex}. Titres invalides écartés sans tout refuser."""
        items = body.get("items")
        if not isinstance(items, list):
            raise ValueError("liste attendue")
        entries, current, kept = [], int(body.get("currentIndex", -1)), 0
        for index, item in enumerate(items):
            try:
                track = Track.from_api((item or {}).get("track"))
            except (ValueError, AttributeError):
                if index < current:
                    current -= 1          # le titre en cours garde sa place malgré l'entrée écartée
                continue
            entries.append((track, str(item.get("addedBy") or "screen")[:20]))
            kept += 1
        return self.queue.replace(entries, current if 0 <= current < kept else -1).to_api()

    def take_for_screen(self):
        return [r.to_api() for r in self.queue.take_requests()]

    # --- téléphones ---
    def request_from_phone(self, track, mode):
        return self.queue.request(track, mode, PHONE)

    def upcoming_for_phone(self):
        """Ce qui va passer (sans le détail technique), et les demandes pas encore prises par l'écran."""
        snapshot = self.queue.snapshot()
        start = snapshot.current_index
        brief = lambda item: {"title": item.track.title, "artist": item.track.fields.get("artist", ""), "addedBy": item.added_by}
        current = snapshot.current
        return {"current": brief(current) if current else None,
                "upcoming": [brief(i) for i in snapshot.items[start + 1:start + 1 + UPCOMING_FOR_PHONE]],
                "pending": [{"title": r.track.title, "artist": r.track.fields.get("artist", ""), "mode": r.mode}
                            for r in self.queue.pending()]}
WEBEOF_71
cat > "$APP_DIR/pimedia/server/remote.py" <<'WEBEOF_72'
"""Taper depuis le téléphone : un petit serveur à part, ouvert sur le réseau local, qui ne sait faire qu'une chose,
recevoir le texte de la recherche. L'interface du Pi, elle, reste fermée au réseau (127.0.0.1).

Le téléphone scanne un QR code affiché par le Pi ; l'adresse contient un code qui change à chaque affichage :
un autre appareil de la maison ne peut pas taper à votre place sans avoir vu l'écran."""
import os
import re
import secrets
import socket
import threading
import time
import unicodedata

from .transport import Reply, Router, HttpApp, ThreadedServer, make_request_handler

DEFAULT_PORT = 8100
MAX_TEXT = 100
MAX_ARTISTS = 50000
MAX_SUGGESTIONS = 8
WORD_SPLIT = re.compile(r"[^a-z0-9]+")
MAX_FAILURES = 10                # mauvais codes tolérés par minute, ensuite on refuse tout pendant une minute
FAILURE_WINDOW = 60
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
PHONE_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                 "Cache-Control": "no-store",
                 "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                            "connect-src 'self'; frame-ancestors 'none'; form-action 'none'; base-uri 'none'"}


def lan_address():
    """Adresse du Pi sur le réseau local (aucun paquet n'est envoyé : on demande seulement la route au système)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))          # adresse réservée à la documentation, jamais jointe
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def plain(text):
    """Minuscules sans accents : « Björk » -> « bjork » (même règle que les suggestions de l'écran du Pi)."""
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


class ArtistIndex:
    """Noms d'artistes envoyés par l'écran du Pi, pour proposer des suggestions sur le téléphone."""

    def __init__(self, artists=()):
        self.entries = []
        self.by_id = {}
        for artist in list(artists)[:MAX_ARTISTS]:
            if not isinstance(artist, dict) or not artist.get("id") or not artist.get("name"):
                continue
            item = {"id": str(artist["id"]), "name": str(artist["name"])[:200]}
            name = plain(item["name"])
            self.entries.append((name, WORD_SPLIT.split(name), item))
            self.by_id[item["id"]] = item

    def suggest(self, text):
        """Le nom commence par le texte d'abord, puis un mot du nom qui commence par lui."""
        wanted = plain(text).strip()
        if len(wanted) < 2:
            return []
        starts, inside = [], []
        for name, words, item in self.entries:
            if name.startswith(wanted):
                starts.append(item)
                if len(starts) >= MAX_SUGGESTIONS:
                    break
            elif len(inside) < MAX_SUGGESTIONS and any(w.startswith(wanted) for w in words):
                inside.append(item)
        return (starts + inside)[:MAX_SUGGESTIONS]


class RemoteTyping:
    """Le texte tapé sur le téléphone et le code valable en ce moment."""

    def __init__(self, clock=time.monotonic):
        self._lock = threading.Lock()
        self._clock = clock
        self.code = self._fresh_code()
        self.text = ""
        self.version = 0
        self.pick = None                 # artiste touché sur le téléphone, à ouvrir sur l'écran du Pi
        self.pick_version = 0
        self.artists = ArtistIndex()
        self._failures = []

    @staticmethod
    def _fresh_code():
        return secrets.token_urlsafe(6)

    def renew(self):
        """Nouveau code (à chaque affichage du QR code) : l'ancien ne marche plus."""
        with self._lock:
            self.code = self._fresh_code()
            return self.code

    def snapshot(self):
        with self._lock:
            return {"code": self.code, "text": self.text, "version": self.version,
                    "pick": self.pick, "pickVersion": self.pick_version}

    def share_artists(self, artists):
        index = ArtistIndex(artists)
        with self._lock:
            self.artists = index
        return len(index.entries)

    def receive(self, code, text):
        """Enregistre le texte et renvoie les suggestions. Lève PermissionError (mauvais code)
        ou OverflowError (trop d'essais)."""
        with self._lock:
            self._check(code)
            self.text = CONTROL_CHARS.sub("", str(text or ""))[:MAX_TEXT]
            self.version += 1
            index = self.artists
        return index.suggest(self.text)

    def choose(self, code, artist_id):
        """Le téléphone a touché une suggestion : seul un artiste réellement proposé est accepté."""
        with self._lock:
            self._check(code)
            artist = self.artists.by_id.get(str(artist_id or ""))
            if artist is None:
                raise LookupError("Artiste introuvable")
            self.pick = artist
            self.pick_version += 1
            return artist

    def verify(self, code):
        """Vérifie le code du QR code (mêmes limites d'essais que pour le texte)."""
        with self._lock:
            self._check(code)

    def _check(self, code):
        now = self._clock()
        self._failures = [t for t in self._failures if now - t < FAILURE_WINDOW]
        if len(self._failures) >= MAX_FAILURES:
            raise OverflowError("trop d'essais")
        if not isinstance(code, str) or not secrets.compare_digest(code, self.code):
            self._failures.append(now)
            raise PermissionError("code invalide")


class PhoneQueue:
    """Ajouts à la file commune depuis le téléphone : on cherche un titre dans la bibliothèque, puis on l'ajoute.
    Seuls les titres renvoyés par une recherche peuvent être ajoutés."""

    MAX_RESULTS = 20
    MAX_REMEMBERED = 200

    def __init__(self, typing, search, queue):
        self.typing = typing
        self.search_tracks = search          # fonction : texte -> [Track] (recherche Subsonic)
        self.queue = queue                   # QueueService
        self._lock = threading.Lock()
        self._found = {}

    def search(self, code, text):
        self.typing.verify(code)
        text = CONTROL_CHARS.sub("", str(text or "")).strip()[:MAX_TEXT]
        if len(text) < 2:
            return []
        tracks = self.search_tracks(text)[:self.MAX_RESULTS]
        with self._lock:
            self._found.update((t.id, t) for t in tracks)
            while len(self._found) > self.MAX_REMEMBERED:
                self._found.pop(next(iter(self._found)))
        return [{"id": t.id, "title": t.title, "artist": t.fields.get("artist", ""), "album": t.fields.get("album", ""),
                 "duration": t.fields.get("duration", 0)} for t in tracks]

    def add(self, code, track_id, mode):
        self.typing.verify(code)
        with self._lock:
            track = self._found.get(str(track_id or ""))
        if track is None:
            raise LookupError("Titre introuvable : cherchez-le à nouveau")
        self.queue.request_from_phone(track, mode)
        return track.title

    def view(self, code):
        self.typing.verify(code)
        return self.queue.upcoming_for_phone()


class PhoneController:
    def __init__(self, typing, web_dir, phone_queue=None):
        self.typing = typing
        self.web_dir = web_dir
        self.phone_queue = phone_queue

    def page(self, request):
        return self._file("telephone.html", "text/html; charset=utf-8")

    def script(self, request):
        return self._file("telephone.js", "application/javascript; charset=utf-8")

    def _file(self, name, ctype):
        try:
            with open(os.path.join(self.web_dir, name), "rb") as f:
                return Reply(200, f.read(), ctype)
        except OSError:
            return Reply.not_found()

    def text(self, request):
        return self._guarded(request, lambda b: {"suggestions": self.typing.receive(b.get("code"), b.get("text"))})

    def pick(self, request):
        return self._guarded(request, lambda b: {"artist": self.typing.choose(b.get("code"), b.get("id"))})

    def search(self, request):
        return self._guarded(request, lambda b: {"songs": self.phone_queue.search(b.get("code"), b.get("text"))})

    def queue_add(self, request):
        return self._guarded(request, lambda b: {"added": self.phone_queue.add(b.get("code"), b.get("id"), b.get("mode", "next"))})

    def queue_view(self, request):
        return self._guarded(request, lambda b: self.phone_queue.view(b.get("code")))

    @staticmethod
    def _guarded(request, action):
        try:
            result = action(request.json_body(limit=2048))
        except PermissionError:
            return Reply.json({"error": "Code périmé : scannez à nouveau le QR code affiché sur le Pi"}, 403)
        except OverflowError:
            return Reply.json({"error": "Trop d'essais, réessayez dans une minute"}, 429)
        except LookupError as error:
            return Reply.json({"error": str(error)}, 404)
        except (ValueError, AttributeError):
            return Reply.json({"error": "requête invalide"}, 400)
        except (RuntimeError, OSError):
            return Reply.json({"error": "Bibliothèque injoignable pour le moment"}, 502)
        return Reply.json(dict(result, ok=True))


class PhoneServer:
    """Serveur du téléphone, sur toutes les interfaces du Pi, dans son propre fil d'exécution."""

    def __init__(self, typing, web_dir, port=DEFAULT_PORT, host="0.0.0.0", phone_queue=None):
        router = Router()
        controller = PhoneController(typing, web_dir, phone_queue)
        router.add("GET", "/tel", controller.page)
        router.add("GET", "/tel.js", controller.script)
        router.add("POST", "/tel/text", controller.text)
        router.add("POST", "/tel/pick", controller.pick)
        if phone_queue is not None:
            router.add("POST", "/tel/search", controller.search)
            router.add("POST", "/tel/queue/add", controller.queue_add)
            router.add("POST", "/tel/queue", controller.queue_view)
        app = HttpApp(router, lambda error: Reply.json({"error": "erreur"}, 500), PHONE_HEADERS)
        self.server = ThreadedServer((host, port), make_request_handler(app))

    @property
    def port(self):
        return self.server.server_address[1]

    def start(self):
        threading.Thread(target=self.server.serve_forever, args=(0.5,), daemon=True).start()
        return self


class RemoteController:
    """Côté Pi (127.0.0.1) : adresse à mettre dans le QR code, et texte reçu."""

    def __init__(self, typing, port_of):
        self.typing = typing
        self.port_of = port_of              # fonction : port réel du serveur téléphone (None s'il n'a pas démarré)

    def state(self, request):
        port = self.port_of()
        if port is None:
            return Reply.json({"error": "Saisie depuis le téléphone indisponible"}, 503)
        snap = self.typing.snapshot()
        snap["url"] = "http://%s:%d/tel?c=%s" % (lan_address(), port, snap.pop("code"))
        return Reply.json(snap)

    def renew(self, request):
        if request.header("X-Requested-With") != "pm":
            return Reply.json({"error": "refus"}, 403)
        self.typing.renew()
        return self.state(request)

    def artists(self, request):
        """L'écran du Pi partage la liste des artistes (noms et identifiants) pour les suggestions du téléphone."""
        if request.header("X-Requested-With") != "pm":
            return Reply.json({"error": "refus"}, 403)
        try:
            body = request.json_body(limit=8 * 1024 * 1024)
            count = self.typing.share_artists(body.get("artists") or [])
        except (ValueError, AttributeError, TypeError):
            return Reply.json({"error": "requête invalide"}, 400)
        return Reply.json({"count": count})
WEBEOF_72
cat > "$APP_DIR/pimedia/server/tasks.py" <<'WEBEOF_73'
"""Tâches de fond (rafraîchir le cache, détecter les nouveautés…) : les erreurs n'interrompent jamais le serveur."""
import threading


def in_background(func, *args, delay=0):
    def job():
        try:
            func(*args)
        except Exception:       # noqa: BLE001 - une tâche de fond ratée sera refaite plus tard
            pass
    runner = threading.Timer(delay, job) if delay else threading.Thread(target=job)
    runner.daemon = True
    runner.start()
    return runner
WEBEOF_73
cat > "$APP_DIR/pimedia/server/transport.py" <<'WEBEOF_74'
"""Couche HTTP : requête, réponse, routage et gestionnaire du serveur. Aucune logique métier ici."""
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .constants import LOOPBACK


# ---------- requête ----------
class Request:
    """Ce qu'un contrôleur a besoin de savoir d'une requête, sans dépendre de http.server."""

    def __init__(self, method, target, headers, peer, rfile, connection=None):
        parts = urllib.parse.urlsplit(target)
        self.method = method
        self.path = parts.path
        self.query_string = parts.query
        self.query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        self.headers = headers
        self.peer = peer                     # adresse de l'appelant
        self.rfile = rfile
        self.connection = connection

    # --- paramètres ---
    def param(self, name, default=""):
        return dict(self.query).get(name, default)

    @property
    def content_length(self):
        try:
            return int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return 0

    def header(self, name, default=""):
        return self.headers.get(name) or default

    def json_body(self, limit=4096):
        """Corps JSON (limité en taille) ; un dictionnaire vide si absent ou invalide."""
        length = self.content_length
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(min(length, limit)).decode("utf-8"))
        except (ValueError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    # --- identité de l'appelant ---
    @property
    def is_local(self):
        return self.peer in LOOPBACK

    def set_timeout(self, seconds):
        """Délai d'inactivité de la connexion (un client qui ne lit plus ne bloque pas ce fil indéfiniment)."""
        try:
            self.connection.settimeout(seconds)
        except (AttributeError, OSError):
            pass


# ---------- réponses ----------
NO_STORE = {"Cache-Control": "no-store"}


class Reply:
    def __init__(self, status=200, body=b"", ctype="text/plain", headers=None):
        self.status = status
        self.body = body
        self.ctype = ctype
        self.headers = dict(headers or {})
        self.close_connection = False

    @classmethod
    def json(cls, data, status=200, headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return cls(status, body, "application/json", dict(NO_STORE, **(headers or {})))

    @classmethod
    def raw_json(cls, body, status=200, headers=None):
        """Corps JSON déjà encodé."""
        return cls(status, body, "application/json; charset=utf-8", dict(NO_STORE, **(headers or {})))

    @classmethod
    def error(cls, status, code):
        return cls.json({"error": code}, status)

    @classmethod
    def not_found(cls):
        return cls(404, b"404", "text/plain")

    @classmethod
    def from_web_file(cls, web_file):
        return cls(web_file.status, web_file.body, web_file.ctype, web_file.headers)

    def write_to(self, handler):
        handler.send_response(self.status)
        if self.status != 304:
            handler.send_header("Content-Type", self.ctype)
            handler.send_header("Content-Length", str(len(self.body)))
        for name, value in self.headers.items():
            handler.send_header(name, value)
        handler.end_headers()
        if self.status != 304:
            handler.wfile.write(self.body)


class StreamReply(Reply):
    """Relaie une réponse Subsonic (audio) par morceaux, sans la garder en mémoire."""

    CHUNK = 65536
    COPIED_HEADERS = ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges")

    def __init__(self, upstream, status):
        super().__init__(status)
        self.upstream = upstream
        self.has_length = bool(upstream.headers.get("Content-Length"))
        self.close_connection = not self.has_length

    def write_to(self, handler):
        handler.send_response(self.status)
        for name in self.COPIED_HEADERS:
            value = self.upstream.headers.get(name)
            if value:
                handler.send_header(name, value)
        if not self.has_length:
            handler.send_header("Connection", "close")
        handler.end_headers()
        self._pump(handler.wfile)

    def _pump(self, out):
        try:
            while True:
                chunk = self.upstream.read(self.CHUNK)
                if not chunk:
                    break
                out.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.upstream.close()


# ---------- routage ----------
class Router:
    """Associe (méthode, chemin) à une fonction de contrôleur : chemin exact, ou préfixe (« /static/… »)."""

    def __init__(self):
        self._exact = {}
        self._prefixes = []

    def add(self, method, path, handler):
        self._exact[(method, path)] = handler

    def add_prefix(self, method, prefix, handler):
        self._prefixes.append((method, prefix, handler))

    def find(self, method, path):
        handler = self._exact.get((method, path))
        if handler:
            return handler
        for route_method, prefix, route_handler in self._prefixes:
            if route_method == method and path.startswith(prefix):
                return route_handler
        return None


# ---------- application HTTP ----------
class HttpApp:
    """Chaîne de traitement d'une requête : routage, contrôleur, en-têtes communs, erreurs."""

    def __init__(self, router, on_error, headers=None):
        self.router = router
        self.on_error = on_error             # fonction (exception) -> Reply
        self.headers = headers or {}         # ajoutés à chaque réponse (ex. sécurité du serveur téléphone)

    def handle(self, request):
        try:
            reply = self._dispatch(request)
        except Exception as error:           # noqa: BLE001 - toute erreur devient une réponse propre
            reply = self.on_error(error)
        for name, value in self.headers.items():
            reply.headers.setdefault(name, value)
        return reply

    def _dispatch(self, request):
        handler = self.router.find(request.method, request.path)
        return handler(request) if handler else Reply.not_found()


def make_request_handler(app):
    """Fabrique la classe de gestionnaire http.server liée à l'application."""

    class RequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = 300          # une connexion silencieuse est fermée (évite d'accumuler des connexions mortes)

        def log_message(self, *args):
            pass

        def _serve(self, method):
            request = Request(method, self.path, self.headers, self.client_address[0], self.rfile, self.connection)
            reply = app.handle(request)
            if reply.close_connection:
                self.close_connection = True
            reply.write_to(self)

        def do_GET(self):
            self._serve("GET")

        def do_POST(self):
            self._serve("POST")

    return RequestHandler


class ThreadedServer(ThreadingHTTPServer):
    daemon_threads = True
WEBEOF_74
cat > "$APP_DIR/pimedia/server/upstream.py" <<'WEBEOF_75'
"""Accès HTTP au serveur Subsonic."""
import hashlib
import secrets
import urllib.error
import urllib.parse
import urllib.request

from .constants import API_VERSION, AUTH_PARAMS, BINARY_ENDPOINTS, CLIENT_NAME


class NotConfigured(Exception):
    """Aucun serveur Subsonic ou aucun utilisateur configuré : impossible d'appeler Subsonic."""


def make_token(password):
    """Jeton d'authentification Subsonic : (sel, md5(mot de passe + sel))."""
    salt = secrets.token_hex(8)
    return salt, hashlib.md5((password + salt).encode()).hexdigest()


class SubsonicClient:
    def __init__(self, config):
        self.config = config

    # --- identité : le compte Subsonic du .env ---
    def credentials(self):
        """(utilisateur, sel, jeton) pour la requête."""
        user, password = self.config.get("subsonic_user", ""), self.config.get("subsonic_pass", "")
        if not user:
            raise NotConfigured()
        salt, token = make_token(password)
        return user, salt, token

    # --- requêtes ---
    def build_url(self, endpoint, params, credentials):
        user, salt, token = credentials
        items = [(k, v) for k, v in params if k not in AUTH_PARAMS and not k.startswith("_")]
        items += [("u", user), ("t", token), ("s", salt), ("v", API_VERSION), ("c", CLIENT_NAME)]
        if endpoint not in BINARY_ENDPOINTS and "f" not in dict(items):
            items.append(("f", "json"))
        return "%s/rest/%s.view?%s" % (self.config.subsonic_url, endpoint, urllib.parse.urlencode(items))

    def open(self, endpoint, params, headers=None, timeout=30):
        """Ouvre une réponse Subsonic (une réponse d'erreur HTTP est retournée comme les autres)."""
        if not self.config.subsonic_url:
            raise NotConfigured()
        request = urllib.request.Request(self.build_url(endpoint, params, self.credentials()))
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            return error

    def trigger_scan(self):
        """Demande à Subsonic de scanner sa bibliothèque (réservé parfois aux administrateurs)."""
        try:
            response = self.open("startScan", [], timeout=30)
            response.read()
            response.close()
        except Exception:
            pass
WEBEOF_75
cat > "$APP_DIR/pimedia/server/watcher.py" <<'WEBEOF_76'
"""Surveillance de la bibliothèque : détection des nouveaux albums et préchauffage du cache."""
import json
import threading
import time

from .api import is_ok
from .constants import LIBRARY_ENDPOINTS
from .upstream import NotConfigured
from .folders import as_list


class LibraryCache:
    """Vidage ciblé du cache : seule la « bibliothèque » est concernée,
    jamais les pochettes, biographies ni paroles (qui ne changent pas)."""

    def __init__(self, cache):
        self.cache = cache

    def refresh(self):
        self.cache.invalidate(lambda meta: meta["ep"] in LIBRARY_ENDPOINTS)


class NewestAlbums:
    """Mémorise les derniers albums vus, pour repérer les nouveautés."""

    def __init__(self, path):
        self.path = path

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def save(self, ids):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(ids, f)
        except OSError:
            pass


class LibraryWatcher:
    NEWEST = [("type", "newest"), ("size", "40")]
    WARM_UP = [("getArtists", []), ("getGenres", []), ("getPlaylists", []), ("getStarred2", []),
               ("getAlbumList2", [("type", "newest"), ("size", "14")]),
               ("getAlbumList2", [("type", "newest"), ("size", "40"), ("offset", "0")]),
               ("getAlbumList2", [("type", "alphabeticalByName"), ("size", "40"), ("offset", "0")])]
    FIRST_DELAY = 3
    PERIOD = 1800
    RETRY_PERIOD = 600

    def __init__(self, api, library, newest):
        self.api = api
        self.library = library
        self.newest = newest
        self._started = False

    # --- détection ---
    def check_new(self, force=False):
        """Compare les 40 derniers albums du serveur à ceux déjà vus. Retourne True s'il y a des nouveautés."""
        result = self.api.call_fresh("getAlbumList2", self.NEWEST)
        if not is_ok(result.body):
            return False
        ids = self._ids(result.body)
        seen = self.newest.load()
        changed = seen is not None and any(i not in seen for i in ids)
        self.newest.save(ids)
        if changed or force:
            self.library.refresh()
        return changed

    @staticmethod
    def _ids(body):
        albums = json.loads(body)["subsonic-response"].get("albumList2", {}).get("album")
        return [a.get("id") for a in as_list(albums)]

    # --- préchauffage ---
    def warm_up(self):
        """Détection + préchauffage, une fois, au nom de l'utilisateur courant. Retourne False en cas d'échec."""
        failed = False
        try:
            self.check_new()
        except NotConfigured:
            raise
        except Exception:
            failed = True
        for endpoint, params in self.WARM_UP:
            try:
                self.api.call(endpoint, params)
            except NotConfigured:
                raise
            except Exception:
                failed = True
        return not failed

    def run_forever(self):
        """Boucle de fond : préchauffe le cache et détecte les nouveaux albums."""
        time.sleep(self.FIRST_DELAY)
        while True:
            try:
                ok = self.warm_up()
            except NotConfigured:
                return
            time.sleep(self.PERIOD if ok else self.RETRY_PERIOD)

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self.run_forever, daemon=True).start()
WEBEOF_76
cat > "$APP_DIR/pimedia/server/webfiles.py" <<'WEBEOF_77'
"""Fichiers de l'interface web (page, CSS, JavaScript) : version, compression, en-têtes de cache."""
import gzip
import hashlib
import os
import threading
import time
import urllib.parse

MIME = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon",
        ".woff2": "font/woff2", ".json": "application/json", ".webmanifest": "application/manifest+json"}
GZIP_EXT = frozenset((".css", ".js", ".svg", ".json", ".webmanifest"))
STATIC_PREFIX = "/static/"


class WebFile:
    """Réponse prête à envoyer : statut, corps, type, en-têtes."""

    def __init__(self, status, body=b"", ctype="text/plain", headers=None):
        self.status = status
        self.body = body
        self.ctype = ctype
        self.headers = headers or {}


def etag_matches(header, etag):
    """L'en-tête If-None-Match désigne-t-il cette version ?"""
    header = header or ""
    return etag in [part.strip() for part in header.split(",")] or header.strip() == "*"


class AssetVersion:
    """Empreinte des fichiers de l'interface. Elle change à chaque mise à jour : le navigateur recharge alors
    les fichiers (adresse ?v=…), alors qu'entre deux mises à jour ils restent en cache un an."""

    REFRESH_SECONDS = 5

    def __init__(self, web_dir):
        self.web_dir = web_dir
        self._checked = 0
        self._value = "0"
        self._lock = threading.Lock()

    def current(self):
        with self._lock:
            if time.time() - self._checked >= self.REFRESH_SECONDS:
                self._value = self._compute()
                self._checked = time.time()
            return self._value

    def _compute(self):
        digest = hashlib.sha1()
        for root, dirs, files in sorted(os.walk(self.web_dir)):
            dirs.sort()
            for name in sorted(files):
                self._add_file(digest, os.path.join(root, name))
        return digest.hexdigest()[:10]

    def _add_file(self, digest, path):
        try:
            stat = os.stat(path)
        except OSError:
            return
        digest.update(("%s|%d|%d;" % (os.path.relpath(path, self.web_dir), stat.st_size, stat.st_mtime_ns)).encode())


class GzipCache:
    """Version compressée de chaque fichier, recalculée seulement s'il change."""

    def __init__(self):
        self._items = {}

    def compressed(self, path, signature, body):
        cached = self._items.get(path)
        if not cached or cached[0] != signature:
            cached = (signature, gzip.compress(body, 6))
            self._items[path] = cached
        return cached[1]


class WebFiles:
    def __init__(self, paths):
        self.paths = paths
        self.version = AssetVersion(paths.web_dir)
        self.gzip = GzipCache()

    # --- page d'accueil ---
    def index(self, if_none_match):
        return self.page("index.html", if_none_match)

    def page(self, name, if_none_match):
        """Une page HTML du dossier web/, avec l'empreinte des fichiers dans les adresses (?v=…)."""
        try:
            with open(os.path.join(self.paths.web_dir, name), "rb") as f:
                page = f.read().replace(b"{{V}}", self.version.current().encode())
        except OSError:
            return WebFile(500, ("web/%s introuvable" % name).encode())
        etag = '"%s"' % hashlib.sha1(page).hexdigest()[:16]
        headers = {"Cache-Control": "no-cache", "ETag": etag}
        if etag_matches(if_none_match, etag):
            return WebFile(304, headers=headers)
        return WebFile(200, page, "text/html; charset=utf-8", headers)

    # --- fichiers statiques ---
    def static(self, url_path, query, if_none_match, accept_encoding):
        full = self._safe_path(url_path)
        if full is None:
            return WebFile(404, b"404")
        ext = os.path.splitext(full)[1].lower()
        stat = os.stat(full)
        signature = "%d-%d" % (stat.st_mtime_ns, stat.st_size)
        use_gzip = ext in GZIP_EXT and "gzip" in (accept_encoding or "")
        etag = '"%s%s"' % (signature, "-gz" if use_gzip else "")
        headers = self._static_headers(etag, "v" in dict(urllib.parse.parse_qsl(query)))
        if etag_matches(if_none_match, etag):
            return WebFile(304, headers=headers)
        with open(full, "rb") as f:
            body = f.read()
        if use_gzip:
            body = self.gzip.compressed(full, signature, body)
            headers["Content-Encoding"] = "gzip"
        return WebFile(200, body, MIME.get(ext, "application/octet-stream"), headers)

    def _safe_path(self, url_path):
        """Chemin réel du fichier demandé, s'il est bien dans le dossier static (sinon None)."""
        relative = urllib.parse.unquote(url_path[len(STATIC_PREFIX):])
        root = os.path.realpath(self.paths.static_dir)
        full = os.path.realpath(os.path.join(root, relative))
        return full if full.startswith(root + os.sep) and os.path.isfile(full) else None

    @staticmethod
    def _static_headers(etag, versioned):
        # fichier versionné (?v=…) : mis en cache un an ; sinon revalidation courte
        cache = "public, max-age=31536000, immutable" if versioned else "public, max-age=300"
        return {"ETag": etag, "Vary": "Accept-Encoding", "Cache-Control": cache, "X-Content-Type-Options": "nosniff"}
WEBEOF_77
cat > "$APP_DIR/pimedia/server/controllers/__init__.py" <<'WEBEOF_78'
"""Contrôleurs : un par domaine (page, session, bibliothèque, informations, cache, envois, commandes du Pi)."""
WEBEOF_78
cat > "$APP_DIR/pimedia/server/controllers/extmusic.py" <<'WEBEOF_79'
"""Interface de programmation de la musique d'ailleurs et des playlists locales."""
from ..podcasts.directories import DirectoryError
from ...entities import Track
from ..transport import Reply

CSRF_VALUE = "pm"


def _refusal(message, status=400):
    return Reply.json({"error": message}, status)


def tracks_from(raw):
    """Liste de titres envoyée par la page -> entités Track (ValueError si la liste ou un titre est invalide)."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("liste de titres attendue")
    return [Track.from_api(t) for t in raw]


class ExtMusicController:
    def __init__(self, service):
        self.service = service

    # ---------- lecture ----------
    def status(self, request):
        return Reply.json(self.service.status())

    def search(self, request):
        try:
            return Reply.json(self.service.search(request.param("src"), request.param("q")))
        except DirectoryError as error:
            return _refusal(str(error), 502)

    def playlists(self, request):
        return Reply.json({"lists": [p.to_api() for p in self.service.playlists.overview()]})

    def alternative(self, request):
        try:
            found = self.service.alternative(request.param("id"), request.param("title"), request.param("artist"))
        except DirectoryError as error:
            return _refusal(str(error), 502)
        return Reply.json({"item": found})

    def favorites(self, request):
        return Reply.json({"songs": [t.to_api() for t in self.service.playlists.favorites()]})

    def playlist(self, request):
        try:
            return Reply.json(self.service.playlists.get(request.param("id")).to_api())
        except KeyError as error:
            return _refusal(error.args[0], 404)

    # ---------- écriture (POST JSON + en-tête anti-CSRF) ----------
    def settings(self, request):
        if not request.is_local:
            return _refusal("Réservé à l’écran du Pi", 403)
        return self._write(request, self.service.update)

    def unplayable(self, request):
        """Le lecteur intégré a refusé cette vidéo : elle ne sera plus proposée."""
        return self._write(request, lambda b: self.service.mark_unplayable(b.get("id")))

    def favorite(self, request):
        return self._write(request, lambda b: {"starred": self.service.playlists.toggle_favorite(Track.from_api(b.get("song")))})

    def create(self, request):
        return self._write(request, lambda b: {"id": self.service.playlists.create(b.get("name"), tracks_from(b.get("songs")))})

    def add(self, request):
        return self._write(request, lambda b: {"added": self.service.playlists.add(b.get("id", ""), tracks_from(b.get("songs")))})

    def remove(self, request):
        return self._write(request, lambda b: self.service.playlists.remove(b.get("id", ""), int(b.get("index", -1))))

    def delete(self, request):
        return self._write(request, lambda b: self.service.playlists.delete(b.get("id", "")))

    def _write(self, request, action):
        if request.header("X-Requested-With") != CSRF_VALUE:
            return _refusal("refus", 403)
        try:
            result = action(request.json_body(limit=262144)) or {}
        except KeyError as error:
            return _refusal(error.args[0], 404)
        except (ValueError, TypeError) as error:
            return _refusal(str(error))
        return Reply.json(dict(result, ok=True, status=self.service.status()))
WEBEOF_79
cat > "$APP_DIR/pimedia/server/controllers/history.py" <<'WEBEOF_80'
"""Historique des recherches."""
from ..transport import Reply

CSRF_VALUE = "pm"
ACTIONS = ("add", "remove", "clear")


class HistoryController:
    def __init__(self, history):
        self.history = history

    def entries(self, request):
        try:
            return Reply.json({"entries": self.history.entries(request.param("kind"))})
        except ValueError as error:
            return Reply.json({"error": str(error)}, 400)

    def change(self, request):
        """POST {kind, action: add|remove|clear, text}"""
        if request.header("X-Requested-With") != CSRF_VALUE:
            return Reply.json({"error": "refus"}, 403)
        try:
            body = request.json_body(limit=4096)
            action = body.get("action")
            if action not in ACTIONS:
                raise ValueError("action inconnue")
            kind = body.get("kind")
            if action == "clear":
                self.history.clear(kind)
            else:
                getattr(self.history, action)(kind, body.get("text", ""))
            return Reply.json({"entries": self.history.entries(kind)})
        except (ValueError, AttributeError) as error:
            return Reply.json({"error": str(error)}, 400)
WEBEOF_80
cat > "$APP_DIR/pimedia/server/controllers/library.py" <<'WEBEOF_81'
"""Relais des appels Subsonic (/rest/…), informations externes (/info/…) et gestion du cache (/cache/…)."""
from ..constants import API_VERSION, AUTH_PARAMS, BINARY_ENDPOINTS
from ..upstream import NotConfigured
from ..tasks import in_background
from ..transport import NO_STORE, Reply, StreamReply

COVER_HEADERS = {"Cache-Control": "max-age=604800"}


def failure_body(message):
    """Réponse Subsonic « échec », que l'interface sait afficher."""
    return {"subsonic-response": {"status": "failed", "version": API_VERSION,
                                  "error": {"code": 0, "message": message}}}


def endpoint_of(path):
    """« /rest/getArtists.view » -> « getArtists »."""
    name = path.rsplit("/", 1)[-1]
    return name[:-5] if name.endswith(".view") else name


class RestController:
    def __init__(self, api, covers, client):
        self.api = api
        self.covers = covers
        self.client = client

    def handle(self, request):
        endpoint = endpoint_of(request.path)
        params = [(k, v) for k, v in request.query if k not in AUTH_PARAMS]
        try:
            return self._route(request, endpoint, params)
        except NotConfigured:
            return Reply.json(failure_body("Serveur non configuré : lancez set-subsonic.sh"))
        except Exception as error:      # noqa: BLE001
            return Reply.json(failure_body("Serveur injoignable : %s" % error))

    def _route(self, request, endpoint, params):
        if endpoint == "getCoverArt":
            result = self.covers.get(params)
            return Reply(result.status, result.body, result.ctype, dict(COVER_HEADERS, **{"X-Cache": result.state}))
        if endpoint in BINARY_ENDPOINTS:
            return self._stream(request, endpoint, params)
        result = self.api.call(endpoint, params)
        return Reply(result.status, result.body, result.ctype, dict(NO_STORE, **{"X-Cache": result.state}))

    def _stream(self, request, endpoint, params):
        """Flux audio : pas de cache, relais direct avec prise en charge de Range."""
        range_header = request.header("Range")
        request.set_timeout(120)
        upstream = self.client.open(endpoint, params, {"Range": range_header} if range_header else None)
        status = getattr(upstream, "status", None) or upstream.code
        if status >= 400:
            print("flux Subsonic : HTTP %s (Range: %s)" % (status, range_header), flush=True)
        return StreamReply(upstream, status)


class InfoController:
    """Paroles, anecdotes et genres venant de sources externes."""

    def __init__(self, external):
        self.external = external

    def genres(self, request):
        artist = request.param("artist")
        return Reply.raw_json(self.external.genres(artist) if artist else b"{}")

    def lyrics(self, request):
        artist, title = request.param("artist"), request.param("title")
        if not artist or not title:
            return Reply.raw_json(b"{}")
        duration = int(float(request.param("duration") or 0))
        return Reply.raw_json(self.external.lyrics(artist, title, request.param("album"), duration))

    def facts(self, request):
        artist, title = request.param("artist"), request.param("title")
        if not artist or not title:
            return Reply.raw_json(b"{}")
        return Reply.raw_json(self.external.facts(artist, title, request.param("aid"), request.param("album")))


class CacheController:
    def __init__(self, cache, covers, library, watcher):
        self.cache = cache
        self.covers = covers
        self.library = library
        self.watcher = watcher

    def refresh_album(self, request):
        """Rafraîchit un seul album ou artiste (la pochette est rechargée : l'interface change l'adresse)."""
        album, artist = request.param("album"), request.param("artist")

        def stale(meta):
            wanted = (meta["ep"] == "getAlbum" and meta["q"].get("id") == album) or \
                     (meta["ep"] == "getArtist" and meta["q"].get("id") == artist)
            return wanted
        self.cache.invalidate(stale)
        return Reply.json({"ok": True})

    def clear(self, request):
        if request.param("all"):
            self.cache.clear()          # tout, pochettes, bios et paroles compris
            self.covers.clear()
        else:
            self.library.refresh()
            in_background(self.watcher.check_new, True)
        return Reply.json({"ok": True})
WEBEOF_81
cat > "$APP_DIR/pimedia/server/controllers/pages.py" <<'WEBEOF_82'
"""Page d'accueil et fichiers statiques."""
from ..transport import Reply


class PagesController:
    def __init__(self, web_files):
        self.web_files = web_files

    def index(self, request):
        return Reply.from_web_file(self.web_files.index(request.header("If-None-Match")))

    def page(self, name, request):
        return Reply.from_web_file(self.web_files.page(name, request.header("If-None-Match")))

    def static(self, request):
        web_file = self.web_files.static(request.path, request.query_string,
                                         request.header("If-None-Match"), request.header("Accept-Encoding"))
        return Reply.from_web_file(web_file)
WEBEOF_82
cat > "$APP_DIR/pimedia/server/controllers/pi.py" <<'WEBEOF_83'
"""Échanges avec le menu tactile, volume du Pi, invités AirPlay/Bluetooth."""
import re
import subprocess
import threading
import time

from ..constants import BROWSE_MODES
from ..transport import Reply


class PiState:
    """Ce que la page et le menu Tk se transmettent : commande en attente, « écran occupé »."""

    AWAKE_SECONDS = 40

    def __init__(self):
        self._lock = threading.Lock()
        self._command = None
        self._awake_at = 0

    def send(self, command):
        with self._lock:
            self._command = command

    def take_command(self):
        with self._lock:
            command, self._command = self._command, None
            return command

    def mark_awake(self):
        self._awake_at = time.time()

    def is_awake(self):
        return time.time() - self._awake_at < self.AWAKE_SECONDS


class SystemVolume:
    """Volume système du Pi, via pactl."""

    STEP_FORMAT = re.compile(r"[+-]\d{1,2}")
    SINK = "@DEFAULT_SINK@"

    def read(self):
        text = self._pactl("get-sink-volume", self.SINK, capture=True)
        found = re.search(r"(\d+)%", text)
        return int(found.group(1)) if found else None

    def change(self, step):
        if step and self.STEP_FORMAT.fullmatch(step):
            self._pactl("set-sink-volume", self.SINK, step + "%")

    def cap_at_100(self, level):
        if level is not None and level > 100:
            self._pactl("set-sink-volume", self.SINK, "100%")
            return 100
        return level

    @staticmethod
    def _pactl(*args, capture=False):
        result = subprocess.run(["pactl"] + list(args), capture_output=capture, text=True, timeout=5)
        return result.stdout if capture else ""


class PiController:
    def __init__(self, state, volume, browse):
        self.state = state
        self.volume = volume
        self.browse = browse

    def send(self, request):
        self.state.send(request.param("cmd") or None)
        return Reply.json({"ok": True})

    def poll(self, request):
        return Reply.json({"cmd": self.state.take_command()})

    def awake(self, request):
        """« Ne pas lancer l'écran de veille » : la page signale qu'elle est utilisée (paroles affichées)."""
        if request.param("on"):
            self.state.mark_awake()
        return Reply.json({"awake": self.state.is_awake()})

    def set_volume(self, request):
        """?d=+5 / ?d=-5 ; sans paramètre : lecture. Uniquement depuis l'écran local."""
        if not request.is_local:
            return Reply.json({})
        try:
            self.volume.change(request.param("d"))
            level = self.volume.cap_at_100(self.volume.read())
        except Exception:      # noqa: BLE001 - pactl absent ou en échec : pas de volume à afficher
            return Reply.json({})
        return Reply.json({} if level is None else {"volume": level})

    def quit(self, request):
        """Ferme la fenêtre plein écran du Pi (retour au menu) ; uniquement en local."""
        if request.is_local:
            subprocess.Popen(["pkill", "-f", "pi-media-chromium"])
        return Reply.json({"ok": True})

    def mode(self, request):
        wanted = request.param("m")
        if wanted in BROWSE_MODES:
            self.browse.set(wanted)
        return Reply.json({"mode": self.browse.current()})


class GuestController:
    """Invités AirPlay / Bluetooth : état pour la page, et « à toi » en fin de titre."""

    def __init__(self, watcher):
        self.watcher = watcher

    def state(self, request):
        current = self.watcher.state()
        current.pop("player", None)            # nom technique du lecteur : inutile à la page
        return Reply.json(current)

    def hand_over(self, request):
        if request.header("X-Requested-With") != "pm":
            return Reply.json({"error": "refus"}, 403)
        if not self.watcher.hand_over():
            return Reply.json({"error": "Aucun téléphone en attente"}, 409)
        return Reply.json({"ok": True})
WEBEOF_83
cat > "$APP_DIR/pimedia/server/controllers/player.py" <<'WEBEOF_84'
"""Lecture haute fidélité (écran du Pi) : la page pilote mpv comme un élément audio."""
import shutil

from ..playback import MpvError
from ..transport import Reply

CSRF_VALUE = "pm"


class PlayerController:
    def __init__(self, player):
        self.player = player

    def state(self, request):
        state = self.player.state()
        state["available"] = bool(shutil.which("mpv")) or self.player.mpv.command[0] != "mpv"
        return Reply.json(state)

    def command(self, request):
        if request.header("X-Requested-With") != CSRF_VALUE:
            return Reply.json({"error": "refus"}, 403)
        body = request.json_body(limit=8192)
        action = body.get("action")
        handlers = {
            "load": lambda: self.player.load(str(body.get("url", ""))),
            "preload": lambda: self.player.preload(str(body.get("url", ""))),
            "play": lambda: self.player.pause(False),
            "pause": lambda: self.player.pause(True),
            "seek": lambda: self.player.seek(float(body.get("value", 0))),
            "volume": lambda: self.player.volume(float(body.get("value", 100))),
            "stop": self.player.stop,
            "enable": lambda: self.player.set_enabled(bool(body.get("value"))),
        }
        if action not in handlers:
            return Reply.json({"error": "commande inconnue"}, 400)
        try:
            handlers[action]()
        except (ValueError, TypeError) as error:
            return Reply.json({"error": str(error)}, 400)
        except MpvError as error:
            return Reply.json({"error": "Lecteur haute fidélité indisponible : " + str(error)}, 503)
        return Reply.json(self.player.state())
WEBEOF_84
cat > "$APP_DIR/pimedia/server/controllers/podcasts.py" <<'WEBEOF_85'
"""Page et interface de programmation des podcasts."""
from ..podcasts.directories import DirectoryError
from ..podcasts.feeds import FeedError
from ..transport import Reply

CSRF_VALUE = "pm"


def _refusal(message, status=502):
    return Reply.json({"error": message}, status)


class PodcastController:
    def __init__(self, config, service, pages):
        self.config = config
        self.service = service
        self.pages = pages

    # ---------- lecture ----------
    def page(self, request):
        return self.pages.page("podcasts.html", request)

    def status(self, request):
        return Reply.json(self.service.status())

    def home(self, request):
        return self._answer(self.service.home)

    def theme(self, request):
        return self._answer(self.service.theme, request.param("id"))

    def search(self, request):
        return self._answer(self.service.search, request.param("q"))

    def show(self, request):
        return self._answer(self.service.show, request.param("feed"))

    def similar(self, request):
        return self._answer(self.service.similar, request.param("feed"), request.param("genre"), request.param("title"))

    def library(self, request):
        return self._answer(self.service.library_view)

    def _answer(self, action, *args):
        try:
            return Reply.json(action(*args))
        except (FeedError, DirectoryError) as error:
            return _refusal(str(error))

    # ---------- écriture (POST JSON, avec l'en-tête anti-CSRF) ----------
    def subscribe(self, request):
        return self._write(request, lambda b: self.service.subscribe(
            b.get("feed", ""), b.get("title", ""), b.get("image", ""), b.get("author", "")))

    def unsubscribe(self, request):
        return self._write(request, lambda b: self.service.unsubscribe(b.get("feed", "")))

    def hide(self, request):
        return self._write(request, lambda b: self.service.hide(b.get("feed", "")))

    def progress(self, request):
        return self._write(request, self.service.save_progress)

    def played(self, request):
        return self._write(request, lambda b: self.service.mark_played(b.get("id", ""), bool(b.get("played", True))))

    def language(self, request):
        return self._write(request, lambda b: self.service.set_french_only(b.get("french", True)))

    def forget(self, request):
        return self._write(request, lambda b: self.service.forget(str(b.get("id", ""))))

    def save_key(self, request):
        """Clé Podcast Index saisie dans la page (depuis l'écran du Pi seulement). Vide = désactiver."""
        if not request.is_local:
            return _refusal("Réservé à l'écran du Pi", 403)

        def store(body):
            self.config.update(podcastindex_key=str(body.get("key", "")).strip(),
                               podcastindex_secret=str(body.get("secret", "")).strip())
        return self._write(request, store)

    def _write(self, request, action):
        if request.header("X-Requested-With") != CSRF_VALUE:
            return _refusal("refus", 403)
        try:
            action(request.json_body(limit=16384))
        except (FeedError, ValueError, KeyError) as error:
            return _refusal(str(error), 400)
        status = self.service.status()
        return Reply.json({"ok": True, "sources": status["sources"], "french": status["french"]})
WEBEOF_85
cat > "$APP_DIR/pimedia/server/controllers/queue.py" <<'WEBEOF_86'
"""File d'attente commune, côté écran du Pi (127.0.0.1)."""
from ..transport import Reply

CSRF_VALUE = "pm"


class QueueController:
    def __init__(self, service):
        self.service = service

    def state(self, request):
        return Reply.json(self.service.state())

    def save(self, request):
        """L'écran envoie sa file à chaque changement."""
        if request.header("X-Requested-With") != CSRF_VALUE:
            return Reply.json({"error": "refus"}, 403)
        try:
            return Reply.json(self.service.save_from_screen(request.json_body(limit=4 * 1024 * 1024)))
        except (ValueError, TypeError) as error:
            return Reply.json({"error": str(error)}, 400)

    def take(self, request):
        """L'écran prend les demandes d'ajout des téléphones."""
        if request.header("X-Requested-With") != CSRF_VALUE:
            return Reply.json({"error": "refus"}, 403)
        return Reply.json({"requests": self.service.take_for_screen()})
WEBEOF_86
cat > "$APP_DIR/pimedia/server/controllers/settings.py" <<'WEBEOF_87'
"""Réglages de l'interface : classement de la bibliothèque (dossiers ou tags)."""
from ..transport import Reply


class SettingsController:
    def __init__(self, config, browse):
        self.config = config
        self.browse = browse

    def current(self):
        return {"browse_mode": self.browse.current()}

    def page(self, request):
        """GET /settings : sans paramètre, lit ; avec browse_mode=, change puis renvoie les réglages."""
        if request.param("browse_mode"):
            self.browse.set(request.param("browse_mode"))
        return Reply.json(self.current())
WEBEOF_87
cat > "$APP_DIR/pimedia/server/extmusic/__init__.py" <<'WEBEOF_88'
"""Musique d'ailleurs : Jamendo, YouTube, playlists locales."""
WEBEOF_88
cat > "$APP_DIR/pimedia/server/extmusic/service.py" <<'WEBEOF_89'
"""Musique d'ailleurs : réglages (chaque source est désactivée par défaut), recherche, playlists locales."""
from ..podcasts.directories import DirectoryError
from ..podcasts.feeds import TtlCache
from ..podcasts.relevance import normalize, words_of
from .sources import is_alternate_version, song_parts


class ExtMusicService:
    SOURCE_KEYS = {"jamendo": ("ext_jamendo_on", "ext_jamendo_id"), "youtube": ("ext_youtube_on", "ext_youtube_key")}

    def __init__(self, config, sources, playlists, unplayable):
        self.config = config
        self.sources = {s.name: s for s in sources}
        self.playlists = playlists
        self.unplayable = unplayable
        self.cache = TtlCache(1800)

    # ---------- réglages ----------
    def status(self):
        """État de chaque source. Les clés elles-mêmes ne sont jamais renvoyées."""
        status = {name: {"configured": src.configured, "on": self._on(name), "enabled": self.enabled(name)}
                  for name, src in self.sources.items()}
        status["studio"] = self.studio_only
        return status

    @property
    def studio_only(self):
        """« Versions originales seulement » (sans live, reprises, remix…) : activé par défaut."""
        return self.config.get("ext_studio_only") is not False

    def _on(self, name):
        return bool(self.config.get(self.SOURCE_KEYS[name][0]))

    def enabled(self, name):
        return self._on(name) and self.sources[name].configured

    def update(self, body):
        """body : {jamendo_on, youtube_on, jamendo_id, youtube_key, studio} (champs facultatifs)."""
        changes = {}
        if "studio" in body:
            changes["ext_studio_only"] = bool(body["studio"])
        for name, (flag, key) in self.SOURCE_KEYS.items():
            if name + "_on" in body:
                changes[flag] = bool(body[name + "_on"])
            secret_field = "jamendo_id" if name == "jamendo" else "youtube_key"
            if secret_field in body:
                changes[key] = str(body[secret_field]).strip()
        for name, (flag, key) in self.SOURCE_KEYS.items():
            if changes.get(flag) and not (changes.get(key) if key in changes else self.config.get(key)):
                raise ValueError("Saisissez d’abord la clé de %s" % name.capitalize())
        self.config.update(**changes)

    # ---------- recherche ----------
    def search(self, source, term):
        term = (term or "").strip()
        if source not in self.sources or not self.enabled(source):
            raise DirectoryError("Source désactivée")
        if len(term) < 2:
            return {"items": []}
        key = source + ":" + term.lower()
        cached = self.cache.get(key)
        if cached is None:
            cached = self.sources[source].search(term)
            self.cache.put(key, cached)
        return {"items": self._filtered(cached)}

    def _filtered(self, items):
        """Filtres appliqués après le cache : un changement de réglage ou une vidéo refusée comptent tout de suite."""
        items = [i for i in items if not (i.get("youtubeId") and i["youtubeId"] in self.unplayable)]
        if self.studio_only:
            items = [i for i in items if not is_alternate_version(i.get("title"))]
        return items

    def alternative(self, video_id, title, artist=""):
        """Une autre vidéo du même titre, quand le lecteur a refusé celle-ci. None si rien de sûr n'est trouvé :
        on préfère passer au titre suivant que jouer une autre chanson."""
        artist, song = song_parts(title, artist)
        words = words_of(song)
        if not words:
            return None
        for item in self.search("youtube", (artist + " " + song).strip())["items"]:
            haystack = normalize(item["title"])
            if item["youtubeId"] != video_id and all(" " + w in haystack for w in words):
                return item
        return None

    def mark_unplayable(self, video_id):
        self.unplayable.add(video_id)
WEBEOF_89
cat > "$APP_DIR/pimedia/server/extmusic/sources.py" <<'WEBEOF_90'
"""Musique « ailleurs » : Jamendo (musique libre, streaming direct) et YouTube (lecteur officiel intégré)."""
import html
import re
import urllib.parse

from ..podcasts.directories import DirectoryError

JAMENDO_TRACKS = "https://api.jamendo.com/v3.0/tracks/"
YOUTUBE_SEARCH = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"          # 1 unité de quota pour 50 vidéos
MAX_RESULTS = 20


# ---------- fonctions pures ----------
def jamendo_track(item):
    """Un morceau Jamendo, au format commun de l'interface. None s'il n'a pas d'adresse de lecture."""
    if not item.get("audio") or not item.get("id"):
        return None
    return {"id": "jamendo-" + str(item["id"]), "title": item.get("name") or "Sans titre",
            "artist": item.get("artist_name") or "", "album": item.get("album_name") or "",
            "duration": int(item.get("duration") or 0), "streamUrl": item["audio"],
            "imageUrl": item.get("image") or item.get("album_image") or "", "ext": "jamendo"}


def clean_channel(name):
    """« Artiste - Topic » (chaînes automatiques de YouTube) -> « Artiste »."""
    return re.sub(r"\s*-\s*Topic$", "", name or "").strip()


# Versions qui ne sont pas l'enregistrement original : live, reprises, remix, karaoké…
# Prudence avec « live » : « Live Forever » ou « Oasis - Live Forever » sont de vrais titres.
ALTERNATE_VERSION = re.compile(
    r"[(\[][^)\]]*\b(live|tour|concert|session|cover|remix|acoustic|acoustique|instrumental|karaok[eé]|demo|unplugged)\b"
    r"|\blive\s+(at|from|in|on|à|au|aux|@)\b|\blive\s*\d{4}\b|\blive$"
    r"|\b(en concert|in concert|unplugged|karaok[eé]|nightcore|sped up|slowed|8d audio)\b"
    r"|\|\s*(live|cover|remix|karaok)", re.IGNORECASE)


def is_alternate_version(title):
    return bool(ALTERNATE_VERSION.search((title or "").strip()))


def song_parts(title, artist=""):
    """« Britney Spears - Toxic (Official HD Video) » -> ("Britney Spears", "Toxic") : de quoi chercher une autre version."""
    core = re.sub(r"[(\[][^)\]]*[)\]]", " ", title or "")            # parenthèses et crochets
    core = re.sub(r"\b(official|officiel|video|vidéo|clip|audio|lyrics?|paroles|hd|4k)\b", " ", core, flags=re.I)
    if " - " in core:
        artist, core = core.split(" - ", 1)
    return " ".join((artist or "").split()), " ".join(core.replace("|", " ").split())


def is_topic_channel(item):
    """Chaîne « Artiste - Topic » : version audio officielle générée par YouTube, presque toujours intégrable."""
    return ((item.get("snippet") or {}).get("channelTitle") or "").endswith("- Topic")


def topic_first(items):
    """Les chaînes « Topic » d'abord (l'ordre de YouTube est conservé dans chaque groupe) : les clips officiels
    des grands artistes interdisent souvent la lecture hors de YouTube."""
    return sorted(items, key=lambda item: not is_topic_channel(item))


def parse_iso_duration(text):
    """« PT3M25S » -> 205 secondes."""
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text or "")
    if not match:
        return 0
    days, hours, minutes, seconds = (int(x or 0) for x in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def playable_details(video, region):
    """Durée en secondes si la vidéo est lisible dans notre lecteur intégré depuis ce pays, sinon None.
    (Intégration interdite, vidéo non publique, ou bloquée dans le pays.)"""
    status = video.get("status") or {}
    if not status.get("embeddable") or status.get("privacyStatus") not in (None, "public", "unlisted"):
        return None
    restriction = (video.get("contentDetails") or {}).get("regionRestriction") or {}
    if region in (restriction.get("blocked") or []):
        return None
    if "allowed" in restriction and region not in restriction["allowed"]:
        return None
    return parse_iso_duration((video.get("contentDetails") or {}).get("duration"))


def youtube_track(item):
    video = (item.get("id") or {}).get("videoId")
    snippet = item.get("snippet") or {}
    if not video:
        return None
    thumbs = snippet.get("thumbnails") or {}
    image = (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
    return {"id": "yt-" + video, "youtubeId": video, "title": html.unescape(snippet.get("title") or "Sans titre"),
            "artist": clean_channel(html.unescape(snippet.get("channelTitle") or "")), "album": "",
            "duration": 0, "imageUrl": image, "ext": "youtube"}


# ---------- sources ----------
class JamendoSource:
    name = "jamendo"

    def __init__(self, http, config):
        self.http = http
        self.config = config

    @property
    def configured(self):
        return bool(self.config.get("ext_jamendo_id"))

    def search(self, term):
        query = urllib.parse.urlencode([
            ("client_id", self.config.get("ext_jamendo_id")), ("format", "json"), ("limit", MAX_RESULTS),
            ("search", term), ("audioformat", "mp32"), ("imagesize", 300), ("type", "single albumtrack")])
        data = self.http.get(JAMENDO_TRACKS + "?" + query)
        headers = data.get("headers") or {}
        if headers.get("status") not in (None, "success"):
            raise DirectoryError(headers.get("error_message") or "Jamendo a refusé la demande")
        return [t for t in (jamendo_track(i) for i in data.get("results", [])) if t]


class YouTubeSource:
    name = "youtube"

    def __init__(self, http, config):
        self.http = http
        self.config = config

    @property
    def configured(self):
        return bool(self.config.get("ext_youtube_key"))

    def search(self, term):
        query = urllib.parse.urlencode([
            ("part", "snippet"), ("type", "video"), ("videoCategoryId", "10"), ("videoEmbeddable", "true"),
            ("maxResults", MAX_RESULTS), ("q", term), ("key", self.config.get("ext_youtube_key"))])
        data = self.http.get(YOUTUBE_SEARCH + "?" + query)
        tracks = [t for t in (youtube_track(i) for i in topic_first(data.get("items", []))) if t]
        return self._keep_playable(tracks)

    def _keep_playable(self, tracks):
        """Vérifie avant l'affichage ce que le lecteur intégré pourra lire. Si cette vérification échoue,
        on garde la liste telle quelle : mieux vaut un titre peut-être illisible que plus de résultats."""
        if not tracks:
            return tracks
        query = urllib.parse.urlencode([("part", "status,contentDetails"), ("key", self.config.get("ext_youtube_key")),
                                        ("id", ",".join(t["youtubeId"] for t in tracks))])
        try:
            details = {v.get("id"): v for v in self.http.get(YOUTUBE_VIDEOS + "?" + query).get("items", [])}
        except DirectoryError:
            return tracks
        region = (self.config.get("ext_youtube_region") or "FR").upper()
        kept = []
        for track in tracks:
            duration = playable_details(details.get(track["youtubeId"]) or {}, region)
            if duration is not None:
                kept.append(dict(track, duration=duration))
        return kept
WEBEOF_90
cat > "$APP_DIR/pimedia/server/podcasts/__init__.py" <<'WEBEOF_91'
"""Podcasts : annuaires, flux RSS, abonnements et progression."""
WEBEOF_91
cat > "$APP_DIR/pimedia/server/podcasts/directories.py" <<'WEBEOF_92'
"""Annuaires de podcasts : iTunes (sans clé) et Podcast Index (clé gratuite, facultative)."""
import hashlib
import json
import time
import urllib.parse
import urllib.request

from .feeds import TtlCache, USER_AGENT

ITUNES_SEARCH = "https://itunes.apple.com/search"
INDEX_API = "https://api.podcastindex.org/api/1.0/"
MAX_AGE_DAYS = 400              # un podcast sans nouvel épisode depuis plus longtemps est considéré abandonné
MIN_EPISODES = 3


class DirectoryError(Exception):
    pass


# ---------- fonctions pures ----------
def podcast_card(feed, title, author="", image="", desc="", genre="", count=None, lang=""):
    """Forme commune d'un podcast, quel que soit l'annuaire."""
    return {"feed": feed, "title": (title or "").strip(), "author": (author or "").strip(), "image": image or "",
            "desc": (desc or "").strip()[:300], "genre": genre or "", "count": count,
            "lang": (lang or "").strip().lower()}


def index_auth_headers(key, secret, now=None):
    """En-têtes d'authentification de Podcast Index : sha1(clé + secret + date)."""
    stamp = str(int(now if now is not None else time.time()))
    digest = hashlib.sha1((key + secret + stamp).encode("utf-8")).hexdigest()
    return {"User-Agent": USER_AGENT, "X-Auth-Date": stamp, "X-Auth-Key": key, "Authorization": digest}


def is_active(feed, now=None):
    """Écarte les flux manifestement abandonnés ou vides (quand l'annuaire donne l'information)."""
    now = now if now is not None else time.time()
    newest = feed.get("newestItemPublishTime") or feed.get("lastUpdateTime")
    if newest and now - newest > MAX_AGE_DAYS * 86400:
        return False
    count = feed.get("episodeCount")
    return not (count is not None and count < MIN_EPISODES)


def from_itunes(result):
    return podcast_card(result.get("feedUrl", ""), result.get("collectionName"), result.get("artistName"),
                        result.get("artworkUrl600") or result.get("artworkUrl100"), "",
                        result.get("primaryGenreName"), result.get("trackCount"))


def from_index(feed):
    categories = feed.get("categories") or {}
    return podcast_card(feed.get("url", ""), feed.get("title"), feed.get("author"),
                        feed.get("artwork") or feed.get("image"), feed.get("description"),
                        ", ".join(list(categories.values())[:2]), feed.get("episodeCount"), feed.get("language"))


def merge_cards(*groups):
    """Concatène plusieurs listes en ôtant les doublons (même flux ou même titre) et les cartes inutilisables."""
    seen, merged = set(), []
    for group in groups:
        for card in group:
            key = card["feed"] or card["title"].lower()
            if card["feed"] and card["title"] and key not in seen and card["title"].lower() not in seen:
                seen.add(key)
                seen.add(card["title"].lower())
                merged.append(card)
    return merged


# ---------- accès réseau ----------
class JsonHttp:
    def get(self, url, headers=None, timeout=12):
        request = urllib.request.Request(url, headers=dict({"User-Agent": USER_AGENT}, **(headers or {})))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except (OSError, ValueError) as error:
            raise DirectoryError(str(getattr(error, "reason", error)))


class ItunesDirectory:
    """Annuaire d'Apple : aucune clé, bonne recherche par mot."""

    def __init__(self, http, country="fr"):
        self.http = http
        self.country = country

    def search(self, term, limit=30):
        query = urllib.parse.urlencode([("media", "podcast"), ("entity", "podcast"), ("country", self.country),
                                        ("limit", limit), ("term", term)])
        data = self.http.get(ITUNES_SEARCH + "?" + query)
        return [from_itunes(r) for r in data.get("results", []) if r.get("feedUrl")]


class PodcastIndexDirectory:
    """Podcast Index : annuaire ouvert avec catégories et tendances. Inactif tant qu'aucune clé n'est donnée."""

    def __init__(self, http, config):
        self.http = http
        self.config = config

    @property
    def enabled(self):
        return bool(self.config.get("podcastindex_key") and self.config.get("podcastindex_secret"))

    def _call(self, path, params):
        headers = index_auth_headers(self.config.get("podcastindex_key"), self.config.get("podcastindex_secret"))
        data = self.http.get(INDEX_API + path + "?" + urllib.parse.urlencode(params), headers)
        return [f for f in data.get("feeds", []) if is_active(f)]

    def trending(self, category, language="fr", limit=40):
        feeds = self._call("podcasts/trending", [("max", limit), ("lang", language), ("cat", category)])
        return [from_index(f) for f in feeds]

    def search(self, term, limit=30):
        return [from_index(f) for f in self._call("search/byterm", [("q", term), ("max", limit)])]


class DirectoryHub:
    """Interroge les annuaires disponibles et présente un résultat propre. Une panne d'un annuaire
    n'empêche pas d'utiliser l'autre."""

    def __init__(self, itunes, index, cache=None):
        self.itunes = itunes
        self.index = index
        self.cache = cache or TtlCache(3600)

    @property
    def sources(self):
        return {"itunes": True, "podcastindex": self.index.enabled}

    def search(self, term):
        return self._cached("s:" + term, lambda: self._gather(
            lambda: self.index.search(term), lambda: self.itunes.search(term)))

    def theme(self, theme):
        return self._cached("t:" + theme.key, lambda: self._gather(
            lambda: self.index.trending(theme.index_category), lambda: self.itunes.search(theme.search_terms)))

    def _gather(self, from_index, from_itunes):
        """Podcast Index d'abord (s'il est actif), puis iTunes ; la liste vide n'est pas une erreur."""
        groups, failures = [], 0
        for enabled, fetch in ((self.index.enabled, from_index), (True, from_itunes)):
            if not enabled:
                continue
            try:
                groups.append(fetch())
            except DirectoryError:
                failures += 1
        if failures and not groups:
            raise DirectoryError("Annuaires injoignables")
        return merge_cards(*groups)

    def _cached(self, key, build):
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            result = build()
        except DirectoryError:
            stale = self.cache.get(key, allow_stale=True)
            if stale is not None:
                return stale
            raise
        self.cache.put(key, result)
        return result
WEBEOF_92
cat > "$APP_DIR/pimedia/server/podcasts/feeds.py" <<'WEBEOF_93'
"""Lecture des flux RSS de podcasts (réseau protégé, XML sans entités, résultat limité)."""
import hashlib
import ipaddress
import re
import socket
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
USER_AGENT = "PiMediaStation/1.0 (lecteur personnel)"
MAX_FEED_BYTES = 6 * 1024 * 1024
MAX_EPISODES = 300


class FeedError(Exception):
    """Flux illisible ou refusé : le message peut être montré à l'utilisateur."""


# ---------- fonctions pures ----------
def parse_duration(text):
    """« 1:02:03 », « 12:30 » ou « 754 » -> secondes (0 si illisible)."""
    parts = (text or "").strip().split(":")
    try:
        numbers = [int(float(p)) for p in parts if p != ""]
    except ValueError:
        return 0
    seconds = 0
    for number in numbers[-3:]:
        seconds = seconds * 60 + number
    return seconds


def parse_date(text):
    """Date RFC 822 -> secondes depuis 1970 (0 si illisible)."""
    try:
        return int(parsedate_to_datetime(text).timestamp())
    except (TypeError, ValueError, IndexError):
        return 0


def plain_text(html, limit=600):
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def episode_id(audio_url, guid=""):
    return hashlib.sha1((guid or audio_url).encode("utf-8")).hexdigest()[:16]


def _text(node, tag):
    child = node.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _image(node):
    picture = node.find(ITUNES_NS + "image")
    if picture is not None and picture.get("href"):
        return picture.get("href")
    return _text(node.find("image"), "url") if node.find("image") is not None else ""


def _episode(item, fallback_image):
    enclosure = item.find("enclosure")
    audio = enclosure.get("url", "") if enclosure is not None else ""
    if not audio:
        return None
    description = _text(item, "description") or _text(item, ITUNES_NS + "summary")
    return {"id": episode_id(audio, _text(item, "guid")), "title": _text(item, "title") or "Épisode",
            "audio": audio, "duration": parse_duration(_text(item, ITUNES_NS + "duration")),
            "date": parse_date(_text(item, "pubDate")), "desc": plain_text(description),
            "image": _image(item) or fallback_image}


def parse_feed(data):
    """Octets d'un flux RSS -> {"title", "author", "image", "desc", "episodes": [...]} (récents d'abord)."""
    if b"<!ENTITY" in data:             # entités définies par le flux : risque d'explosion de mémoire
        raise FeedError("Flux refusé (déclarations XML non autorisées)")
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise FeedError("Flux illisible")
    channel = root.find("channel")
    if channel is None:
        raise FeedError("Ce n’est pas un flux de podcast")
    image = _image(channel)
    episodes = [e for e in (_episode(i, image) for i in channel.findall("item")) if e]
    episodes.sort(key=lambda e: -e["date"])
    return {"title": _text(channel, "title"), "author": _text(channel, ITUNES_NS + "author"), "image": image,
            "desc": plain_text(_text(channel, "description")), "episodes": episodes[:MAX_EPISODES],
            "language": _text(channel, "language").lower()}


# ---------- réseau ----------
def is_public_host(host):
    """Faux pour une adresse locale ou privée (on ne va pas lire le réseau de la maison à la demande d'une page)."""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return bool(addresses) and all(not _private(a) for a in addresses)


def _private(address):
    ip = ipaddress.ip_address(address.split("%")[0])
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast


def check_feed_url(url):
    parts = urllib.parse.urlsplit(url or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FeedError("Adresse de flux invalide")
    if not is_public_host(parts.hostname):
        raise FeedError("Adresse de flux refusée")


class FeedFetcher:
    def fetch(self, url, timeout=15):
        check_feed_url(url)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, */*"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                check_feed_url(response.geturl())          # une redirection ne doit pas mener ailleurs
                data = response.read(MAX_FEED_BYTES + 1)
        except OSError as error:
            raise FeedError("Flux injoignable (%s)" % getattr(error, "reason", error))
        if len(data) > MAX_FEED_BYTES:
            raise FeedError("Flux trop volumineux")
        return data


class TtlCache:
    """Petit cache en mémoire ; une valeur périmée reste utilisable si le réseau est en panne."""

    def __init__(self, ttl, max_items=200):
        self.ttl = ttl
        self.max_items = max_items
        self._items = {}

    def get(self, key, allow_stale=False):
        item = self._items.get(key)
        if item and (allow_stale or item[0] > time.time()):
            return item[1]
        return None

    def put(self, key, value):
        if len(self._items) >= self.max_items:
            self._items.pop(min(self._items, key=lambda k: self._items[k][0]))
        self._items[key] = (time.time() + self.ttl, value)


class FeedReader:
    """Flux lus, mis en cache une demi-heure."""

    def __init__(self, fetcher, cache=None):
        self.fetcher = fetcher
        self.cache = cache or TtlCache(1800)

    def read(self, url):
        cached = self.cache.get(url)
        if cached:
            return cached
        try:
            feed = parse_feed(self.fetcher.fetch(url))
        except FeedError:
            stale = self.cache.get(url, allow_stale=True)
            if stale:
                return stale
            raise
        self.cache.put(url, feed)
        return feed
WEBEOF_93
cat > "$APP_DIR/pimedia/server/podcasts/language.py" <<'WEBEOF_94'
"""Filtre « français » : la langue est donnée par Podcast Index ; pour iTunes (qui ne la donne pas), on la lit
dans le flux lui-même, en parallèle, une seule fois par podcast."""
from concurrent.futures import ThreadPoolExecutor, wait

from .feeds import FeedError

WORKERS = 8
DEADLINE_SECONDS = 8


def is_french(code):
    return code == "fr" or code.startswith("fr-") or code.startswith("fr_")


class LanguageResolver:
    def __init__(self, reader):
        self.reader = reader
        self.known = {}                 # adresse du flux -> code langue ("" si le flux n'en déclare pas)

    def french_only(self, cards):
        """Garde les podcasts français. Langue inconnue (flux illisible ou trop lent) : on garde, par prudence."""
        self._resolve([c for c in cards if not c.get("lang") and c["feed"] not in self.known])
        return [c for c in cards if self._keep(c)]

    def _keep(self, card):
        code = card.get("lang") or self.known.get(card["feed"], "")
        return not code or is_french(code)

    def _resolve(self, cards):
        if not cards:
            return
        pool = ThreadPoolExecutor(WORKERS)
        futures = {pool.submit(self._language_of, c["feed"]): c["feed"] for c in cards}
        done, _ = wait(futures, timeout=DEADLINE_SECONDS)
        for future in done:
            self.known[futures[future]] = future.result()
        pool.shutdown(wait=False)

    def _language_of(self, feed):
        try:
            return self.reader.read(feed).get("language", "")
        except FeedError:
            return ""
WEBEOF_94
cat > "$APP_DIR/pimedia/server/podcasts/relevance.py" <<'WEBEOF_95'
"""Pertinence de la recherche : les annuaires renvoient aussi des résultats « approchants » (un seul des mots).
On ne garde que les podcasts qui contiennent TOUS les mots tapés, titre et auteur d'abord."""
import re
import unicodedata


def normalize(text):
    """Minuscules, sans accents ni ponctuation."""
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return " " + re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip() + " "


def words_of(term):
    return [w for w in normalize(term).split() if w]


def _contains_all(haystack, words):
    return all(" " + w in haystack for w in words)        # début de mot : « hist » trouve « histoire »


def rank(cards, term):
    """Cartes contenant tous les mots, classées : phrase exacte dans le titre, mots dans le titre ou l'auteur,
    puis mots dans la description ou le genre."""
    words = words_of(term)
    if not words:
        return cards
    phrase = " " + " ".join(words)
    scored = []
    for position, card in enumerate(cards):
        title = normalize(card["title"])
        headline = title + normalize(card.get("author"))
        everything = headline + normalize(card.get("desc")) + normalize(card.get("genre"))
        if phrase in title:
            level = 0
        elif _contains_all(headline, words):
            level = 1
        elif _contains_all(everything, words):
            level = 2
        else:
            continue
        scored.append((level, position, card))
    return [card for _, _, card in sorted(scored, key=lambda t: t[:2])]
WEBEOF_95
cat > "$APP_DIR/pimedia/server/podcasts/service.py" <<'WEBEOF_96'
"""Ce que la page Podcasts demande : accueil, thèmes, recherche, fiche d'un podcast, bibliothèque."""
from .directories import DirectoryError
from .feeds import FeedError, check_feed_url
from .language import LanguageResolver
from .relevance import rank
from .themes import DEFAULT_HOME_QUERIES, THEMES, find_theme


class PodcastService:
    HOME_ROW_SIZE = 14
    NEW_EPISODES_PER_SUB = 3

    def __init__(self, config, hub, reader, library):
        self.config = config
        self.hub = hub
        self.reader = reader
        self.library = library
        self.languages = LanguageResolver(reader)

    # ---------- état ----------
    def status(self):
        return {"sources": self.hub.sources, "themes": [t.describe() for t in THEMES], "french": self.french_only}

    @property
    def french_only(self):
        return self.config.get("podcast_french") is not False

    def set_french_only(self, value):
        self.config.update(podcast_french=bool(value))

    # ---------- découverte ----------
    def home(self):
        """Reprendre l'écoute, abonnements, puis une rangée par recherche choisie."""
        rows = []
        for query in self.config.get("podcast_home") or DEFAULT_HOME_QUERIES:
            row = self._safe_search(query)
            if row:
                rows.append({"title": query, "items": row[:self.HOME_ROW_SIZE]})
        return {"resume": self._resume(), "subs": self._subscriptions(), "rows": rows}

    def theme(self, key):
        theme = find_theme(key)
        if theme is None:
            raise DirectoryError("Thème inconnu")
        return {"theme": theme.describe(), "items": self._visible(self.hub.theme(theme))}

    def search(self, term):
        term = (term or "").strip()
        if len(term) < 2:
            return {"items": []}
        return {"items": rank(self._visible(self.hub.search(term)), term)}

    def similar(self, feed, genre, title):
        """« Dans le même genre » : les annuaires n'offrent pas de vraie similarité, on cherche donc par genre
        (ou par titre s'il est inconnu) et on retire le podcast lui-même."""
        term = (genre or "").split(",")[0].strip() or (title or "").strip()
        if len(term) < 2:
            return {"items": []}
        cards = [c for c in self._visible(self.hub.search(term)) if c["feed"] != feed]
        return {"items": cards[:self.HOME_ROW_SIZE]}

    def _safe_search(self, query):
        try:
            return self._visible(self.hub.search(query))
        except DirectoryError:
            return []

    def _visible(self, cards):
        """Sans les podcasts que l'utilisateur a masqués ; avec l'indication « abonné »."""
        shown = [c for c in cards if not self.library.is_hidden(c["feed"])]
        if self.french_only:
            shown = self.languages.french_only(shown)
        return [dict(c, subscribed=self.library.is_subscribed(c["feed"])) for c in shown]

    # ---------- fiche d'un podcast ----------
    def show(self, feed_url):
        check_feed_url(feed_url)
        feed = self.reader.read(feed_url)
        progress = {k: p.to_api() for k, p in self.library.progress_for_feed(feed_url).items()}
        episodes = [dict(e, pos=self._pos(progress, e), played=self._played(progress, e)) for e in feed["episodes"]]
        return {"feed": feed_url, "title": feed["title"], "author": feed["author"], "image": feed["image"],
                "desc": feed["desc"], "subscribed": self.library.is_subscribed(feed_url), "episodes": episodes}

    @staticmethod
    def _pos(progress, episode):
        return progress.get(episode["id"], {}).get("pos", 0)

    @staticmethod
    def _played(progress, episode):
        return bool(progress.get(episode["id"], {}).get("played"))

    # ---------- bibliothèque ----------
    def library_view(self):
        return {"resume": self._resume(), "subs": self._subscriptions(), "latest": self._latest_from_subscriptions()}

    def _resume(self):
        return [p.to_api() for p in self.library.resume_list()]

    def _subscriptions(self):
        return [s.to_api() for s in self.library.subscriptions()]

    def _latest_from_subscriptions(self):
        """Derniers épisodes des podcasts suivis, tous mélangés, du plus récent au plus ancien."""
        latest = []
        for sub in self._subscriptions():
            try:
                feed = self.reader.read(sub["feed"])
            except FeedError:
                continue
            for episode in feed["episodes"][:self.NEW_EPISODES_PER_SUB]:
                latest.append(dict(episode, feed=sub["feed"], podcast=sub["title"], image=episode["image"] or sub["image"],
                                   played=self._played_id(episode["id"])))
        return sorted(latest, key=lambda e: -e["date"])[:20]

    def _played_id(self, episode_id):
        progress = self.library.progress_of(episode_id)
        return bool(progress and progress.played)

    def subscribe(self, feed, title, image="", author=""):
        check_feed_url(feed)
        self.library.subscribe(feed, title or feed, image, author)

    def unsubscribe(self, feed):
        self.library.unsubscribe(feed)

    def hide(self, feed):
        self.library.hide(feed)

    def save_progress(self, episode):
        if not episode.get("id") or not episode.get("audio"):
            raise ValueError("épisode incomplet")
        self.library.save_progress(episode)

    def forget(self, episode_id):
        self.library.forget(episode_id)

    def mark_played(self, episode_id, played):
        self.library.mark_played(episode_id, played)
WEBEOF_96
cat > "$APP_DIR/pimedia/server/podcasts/themes.py" <<'WEBEOF_97'
"""Thèmes proposés dans la page Podcasts, avec de quoi les chercher dans chaque annuaire."""


class Theme:
    def __init__(self, key, label, hue, index_category, search_terms):
        self.key = key
        self.label = label
        self.hue = hue                          # teinte de la vignette (0-360)
        self.index_category = index_category    # catégorie Podcast Index (en anglais)
        self.search_terms = search_terms        # recherche iTunes, en français

    def describe(self):
        return {"key": self.key, "label": self.label, "hue": self.hue}


THEMES = (
    Theme("actualite", "Actualité", 8, "News", "actualité informations"),
    Theme("histoire", "Histoire", 35, "History", "histoire"),
    Theme("science", "Science", 190, "Science", "science"),
    Theme("culture", "Culture", 280, "Arts", "culture littérature cinéma"),
    Theme("humour", "Humour", 50, "Comedy", "humour"),
    Theme("societe", "Société", 320, "Society & Culture", "société débat"),
    Theme("crime", "Faits divers", 0, "True Crime", "affaires criminelles faits divers"),
    Theme("musique", "Musique", 140, "Music", "musique"),
    Theme("tech", "Technologie", 210, "Technology", "technologie numérique"),
    Theme("eco", "Économie", 100, "Business", "économie entreprise"),
    Theme("sante", "Santé & bien-être", 160, "Health & Fitness", "santé bien-être"),
    Theme("sport", "Sport", 25, "Sports", "sport"),
    Theme("fiction", "Fiction", 260, "Fiction", "fiction histoires"),
    Theme("enfants", "Enfants", 80, "Kids & Family", "enfants histoires pour enfants"),
)

# Rangées de l'accueil : recherches que l'on peut modifier dans config.json (clé « podcast_home »)
DEFAULT_HOME_QUERIES = ("France Culture", "France Inter", "Radio France", "Arte Radio")


def find_theme(key):
    for theme in THEMES:
        if theme.key == key:
            return theme
    return None
WEBEOF_97
cat > "$APP_DIR/pimedia/storage/__init__.py" <<'WEBEOF_98'
"""Données durables : base SQLite et accès par domaine (podcasts, playlists, historique…)."""
WEBEOF_98
cat > "$APP_DIR/pimedia/storage/database.py" <<'WEBEOF_99'
"""Base SQLite (pi-media.db) : une connexion par fil d'exécution, schéma versionné (PRAGMA user_version)."""
import contextlib
import sqlite3
import threading

from .schema import MIGRATIONS


class Database:
    def __init__(self, path):
        self.path = path
        self._local = threading.local()
        self._migrate_lock = threading.Lock()
        self.migrate()

    def connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=10, isolation_level=None, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")      # lectures pendant les écritures, robuste aux coupures
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def query(self, sql, params=()):
        return self.connection().execute(sql, params).fetchall()

    def one(self, sql, params=()):
        return self.connection().execute(sql, params).fetchone()

    def execute(self, sql, params=()):
        return self.connection().execute(sql, params)

    @contextlib.contextmanager
    def transaction(self):
        """Plusieurs écritures d'un bloc : tout ou rien (BEGIN IMMEDIATE : pas d'écriture concurrente entre-temps)."""
        conn = self.connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

    @property
    def version(self):
        return self.one("PRAGMA user_version")[0]

    def migrate(self):
        with self._migrate_lock:
            current = self.version
            for number, script in enumerate(MIGRATIONS, start=1):
                if number > current:
                    with self.transaction() as conn:
                        for statement in (s.strip() for s in script.split(";")):
                            if statement:
                                conn.execute(statement)
                        conn.execute("PRAGMA user_version = %d" % number)

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
WEBEOF_99
cat > "$APP_DIR/pimedia/storage/history.py" <<'WEBEOF_100'
"""Historique des recherches de l'écran du Pi (une liste pour la musique, une pour les podcasts)."""
import time

KINDS = ("music", "podcasts")
MAX_ENTRIES = 15
MAX_LENGTH = 100


class SearchHistory:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _kind(kind):
        if kind not in KINDS:
            raise ValueError("historique inconnu")
        return kind

    def entries(self, kind):
        rows = self.db.query("SELECT query FROM search_history WHERE kind = ? ORDER BY searched_at DESC, rowid DESC LIMIT ?",
                             (self._kind(kind), MAX_ENTRIES))
        return [r["query"] for r in rows]

    def add(self, kind, text):
        """Recherche la plus récente en tête ; une recherche déjà présente remonte au lieu d'être répétée."""
        text = " ".join(str(text or "").split())[:MAX_LENGTH]
        if len(text) < 2:
            return
        kind = self._kind(kind)
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM search_history WHERE kind = ? AND query_key = ?", (kind, text.lower()))
            conn.execute("INSERT INTO search_history (kind, query, query_key, searched_at) VALUES (?, ?, ?, ?)",
                         (kind, text, text.lower(), time.time_ns()))
            conn.execute("DELETE FROM search_history WHERE kind = ? AND rowid NOT IN (SELECT rowid FROM search_history "
                         "WHERE kind = ? ORDER BY searched_at DESC LIMIT ?)", (kind, kind, MAX_ENTRIES))

    def remove(self, kind, text):
        self.db.execute("DELETE FROM search_history WHERE kind = ? AND query = ?", (self._kind(kind), text))

    def clear(self, kind):
        self.db.execute("DELETE FROM search_history WHERE kind = ?", (self._kind(kind),))
WEBEOF_100
cat > "$APP_DIR/pimedia/storage/legacy.py" <<'WEBEOF_101'
"""Import, une seule fois, des anciens fichiers (config.json et données JSON) dans le .env et la base.
Les fichiers importés sont renommés en « .importe » : rien n'est supprimé."""
import json
import os
import time

from ..settings import ENV_TYPES
from ..tracks import clean_track

DONE_KEY = "legacy_import_done"
# anciennes clés françaises du menu tactile -> nouvelles clés anglaises (.env)
# réglages de l'ancienne édition serveur (comptes, envois) : sans objet sur le Pi, ignorés
OBSOLETE_KEYS = {"mode", "admins", "uploaders", "upload_dir", "upload_max_mb", "upload_max_unzipped_mb", "session_days"}
RENAMED_KEYS = {"nom": "device_name", "ville": "weather_city", "latitude": "weather_latitude",
                "longitude": "weather_longitude", "veille_secondes": "screensaver_seconds"}
OLD_FAVORITES_ID = "favoris"


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def env_text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


class LegacyImport:
    def __init__(self, paths, db, env_file, store):
        self.paths = paths
        self.db = db
        self.env_file = env_file
        self.store = store

    def run(self):
        if self.store.get(DONE_KEY):
            return
        self._config()
        self._podcasts()
        self._playlists()
        self._history()
        self._unplayable()
        self.store.set_many({DONE_KEY: True})

    def _archive(self, path):
        try:
            os.replace(path, path + ".importe")
        except OSError:
            pass

    # --- config.json -> .env (installation, secrets) et app_settings (le reste) ---
    def _config(self):
        data = read_json(self.paths.legacy_config)
        if not isinstance(data, dict):
            return
        data = {RENAMED_KEYS.get(k, k): v for k, v in data.items() if k not in OBSOLETE_KEYS}
        present = self.env_file.values()
        env = {k.upper(): env_text(v) for k, v in data.items() if k in ENV_TYPES and k.upper() not in present}
        if env:
            self.env_file.set(**env)
        others = {k: v for k, v in data.items() if k not in ENV_TYPES}
        if others:
            self.store.set_many(others)
        self._archive(self.paths.legacy_config)

    # --- podcasts.json ---
    def _podcasts(self):
        data = read_json(self.paths.legacy_podcasts)
        if not isinstance(data, dict):
            return
        now = int(time.time())
        with self.db.transaction() as conn:
            for feed, sub in (data.get("subs") or {}).items():
                conn.execute("INSERT OR IGNORE INTO podcast_subscriptions (feed_url, title, image_url, author, subscribed_at) "
                             "VALUES (?, ?, ?, ?, ?)", (feed, sub.get("title") or feed, sub.get("image") or "",
                                                       sub.get("author") or "", int(sub.get("added") or now)))
            for feed in data.get("hidden") or []:
                conn.execute("INSERT OR IGNORE INTO hidden_podcasts (feed_url) VALUES (?)", (feed,))
            for episode_id, p in (data.get("progress") or {}).items():
                conn.execute("INSERT OR IGNORE INTO episode_progress (episode_id, feed_url, title, podcast_title, image_url, "
                             "audio_url, position_s, duration_s, played, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (episode_id, p.get("feed", ""), p.get("title", ""), p.get("podcast", ""), p.get("image", ""),
                              p.get("audio", ""), float(p.get("pos") or 0), float(p.get("dur") or 0),
                              int(bool(p.get("played"))), int(p.get("t") or now)))
        self._archive(self.paths.legacy_podcasts)

    # --- playlists.json (dont l'ancienne liste réservée « favoris ») ---
    def _playlists(self):
        data = read_json(self.paths.legacy_playlists)
        if not isinstance(data, dict):
            return
        now = int(time.time())
        with self.db.transaction() as conn:
            for order, playlist in enumerate(data.get("lists") or []):
                tracks = [t for t in (self._track(raw) for raw in playlist.get("songs") or []) if t]
                if playlist.get("id") == OLD_FAVORITES_ID:
                    for track in tracks:
                        conn.execute("INSERT OR IGNORE INTO external_favorites (track_id, track, added_at) VALUES (?, ?, ?)",
                                     (track["id"], json.dumps(track, ensure_ascii=False), now))
                    continue
                conn.execute("INSERT OR IGNORE INTO local_playlists (id, name, created_at) VALUES (?, ?, ?)",
                             (playlist["id"], playlist.get("name") or "Playlist", now + order))
                conn.executemany("INSERT OR IGNORE INTO playlist_tracks (playlist_id, position, track_id, track) VALUES (?, ?, ?, ?)",
                                 [(playlist["id"], i, t["id"], json.dumps(t, ensure_ascii=False)) for i, t in enumerate(tracks)])
        self._archive(self.paths.legacy_playlists)

    @staticmethod
    def _track(raw):
        try:
            return clean_track(raw)
        except ValueError:
            return None

    # --- recherches.json : listes de la plus récente à la plus ancienne ---
    def _history(self):
        data = read_json(self.paths.legacy_history)
        if not isinstance(data, dict):
            return
        base = time.time_ns()
        with self.db.transaction() as conn:
            for kind in ("music", "podcasts"):
                for rank, text in enumerate(t for t in data.get(kind) or [] if isinstance(t, str)):
                    conn.execute("INSERT OR IGNORE INTO search_history (kind, query, query_key, searched_at) VALUES (?, ?, ?, ?)",
                                 (kind, text, text.lower(), base - rank))
        self._archive(self.paths.legacy_history)

    def _unplayable(self):
        data = read_json(self.paths.legacy_unplayable)
        if not isinstance(data, dict):
            return
        base = time.time_ns()
        with self.db.transaction() as conn:
            for rank, video_id in enumerate(i for i in data.get("ids") or [] if isinstance(i, str)):
                conn.execute("INSERT OR IGNORE INTO unplayable_videos (video_id, marked_at) VALUES (?, ?)", (video_id, base + rank))
        self._archive(self.paths.legacy_unplayable)
WEBEOF_101
cat > "$APP_DIR/pimedia/storage/playlists.py" <<'WEBEOF_102'
"""Playlists locales du Pi (mélange de titres Subsonic et d'ailleurs) et favoris des titres d'ailleurs."""
import json
import secrets
import time

from ..entities import Playlist, PlaylistSummary, Track

MAX_LISTS = 100
MAX_TRACKS = 500


class LocalPlaylists:
    def __init__(self, db):
        self.db = db

    # --- lecture ---
    def overview(self):
        rows = self.db.query("SELECT p.id, p.name, COUNT(t.track_id) AS count FROM local_playlists p "
                             "LEFT JOIN playlist_tracks t ON t.playlist_id = p.id GROUP BY p.id ORDER BY p.created_at, p.rowid")
        return [PlaylistSummary(r["id"], r["name"], r["count"]) for r in rows]

    def get(self, list_id):
        row = self._find(list_id)
        tracks = [Track(json.loads(r["track"])) for r in
                  self.db.query("SELECT track FROM playlist_tracks WHERE playlist_id = ? ORDER BY position", (list_id,))]
        return Playlist(row["id"], row["name"], row["created_at"], tracks)

    def _find(self, list_id):
        row = self.db.one("SELECT * FROM local_playlists WHERE id = ?", (list_id,))
        if row is None:
            raise KeyError("Playlist introuvable")
        return row

    # --- écriture ---
    def create(self, name, tracks=()):
        """tracks : entités Track (déjà validées)."""
        name = (name or "").strip()[:80]
        if not name:
            raise ValueError("Nom vide")
        cleaned = list(tracks)[:MAX_TRACKS]
        list_id = secrets.token_hex(6)
        with self.db.transaction() as conn:
            if conn.execute("SELECT COUNT(*) FROM local_playlists").fetchone()[0] >= MAX_LISTS:
                raise ValueError("Trop de playlists")
            conn.execute("INSERT INTO local_playlists (id, name, created_at) VALUES (?, ?, ?)", (list_id, name, int(time.time())))
            self._append(conn, list_id, cleaned, 0)
        return list_id

    def add(self, list_id, tracks):
        """Ajoute les titres (entités Track) absents de la playlist ; renvoie le nombre de titres ajoutés."""
        with self.db.transaction() as conn:
            self._find(list_id)
            known = {r[0] for r in conn.execute("SELECT track_id FROM playlist_tracks WHERE playlist_id = ?", (list_id,))}
            fresh, seen = [], set()
            for track in tracks:
                if track.id not in known and track.id not in seen:
                    fresh.append(track)
                    seen.add(track.id)
            count = len(known)
            if count + len(fresh) > MAX_TRACKS:
                raise ValueError("Playlist pleine")
            self._append(conn, list_id, fresh, count)
        return len(fresh)

    @staticmethod
    def _append(conn, list_id, tracks, start):
        conn.executemany("INSERT INTO playlist_tracks (playlist_id, position, track_id, track) VALUES (?, ?, ?, ?)",
                         [(list_id, start + i, t.id, json.dumps(t.fields, ensure_ascii=False)) for i, t in enumerate(tracks)])

    def remove(self, list_id, index):
        with self.db.transaction() as conn:
            self._find(list_id)
            if conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ? AND position = ?", (list_id, index)).rowcount == 0:
                raise ValueError("Position invalide")
            # positions décalées en deux temps : la clé (playlist, position) doit rester unique à chaque instant
            conn.execute("UPDATE playlist_tracks SET position = -(position - 1) WHERE playlist_id = ? AND position > ?", (list_id, index))
            conn.execute("UPDATE playlist_tracks SET position = -position WHERE playlist_id = ? AND position < 0", (list_id,))

    def delete(self, list_id):
        self.db.execute("DELETE FROM local_playlists WHERE id = ?", (list_id,))

    # --- favoris des titres d'ailleurs (YouTube, Jamendo) ---
    def favorites(self):
        return [Track(json.loads(r["track"])) for r in self.db.query("SELECT track FROM external_favorites ORDER BY added_at, rowid")]

    def toggle_favorite(self, track):
        """Ajoute le titre (entité Track) aux favoris, ou l'en retire s'il y est déjà. Renvoie True s'il est favori ensuite."""
        with self.db.transaction() as conn:
            if conn.execute("DELETE FROM external_favorites WHERE track_id = ?", (track.id,)).rowcount:
                return False
            if conn.execute("SELECT COUNT(*) FROM external_favorites").fetchone()[0] >= MAX_TRACKS:
                raise ValueError("Trop de favoris")
            conn.execute("INSERT INTO external_favorites (track_id, track, added_at) VALUES (?, ?, ?)",
                         (track.id, json.dumps(track.fields, ensure_ascii=False), int(time.time())))
        return True
WEBEOF_102
cat > "$APP_DIR/pimedia/storage/podcasts.py" <<'WEBEOF_103'
"""Podcasts de l'écran du Pi : abonnements, podcasts masqués, progression d'écoute."""
import time

from ..entities import EpisodeProgress, PodcastSubscription

MAX_RESUME = 12
FINISHED_MARGIN_S = 30          # à moins de 30 s de la fin, un épisode compte comme écouté


def _subscription(row):
    return PodcastSubscription(row["feed_url"], row["title"], row["image_url"], row["author"], row["subscribed_at"])


def _progress(row):
    return EpisodeProgress(row["episode_id"], row["feed_url"], row["title"], row["podcast_title"], row["image_url"],
                           row["audio_url"], row["position_s"], row["duration_s"], bool(row["played"]), row["updated_at"])


class PodcastLibrary:
    def __init__(self, db):
        self.db = db

    # --- abonnements ---
    def subscribe(self, feed, title, image="", author=""):
        self.db.execute(
            "INSERT INTO podcast_subscriptions (feed_url, title, image_url, author, subscribed_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (feed_url) DO UPDATE SET title = excluded.title, image_url = excluded.image_url, author = excluded.author",
            (feed, title, image or "", author or "", int(time.time())))

    def unsubscribe(self, feed):
        self.db.execute("DELETE FROM podcast_subscriptions WHERE feed_url = ?", (feed,))

    def is_subscribed(self, feed):
        return self.db.one("SELECT 1 FROM podcast_subscriptions WHERE feed_url = ?", (feed,)) is not None

    def subscriptions(self):
        rows = self.db.query("SELECT * FROM podcast_subscriptions ORDER BY title COLLATE NOCASE")
        return [_subscription(r) for r in rows]

    # --- masqués ---
    def hide(self, feed):
        self.db.execute("INSERT OR IGNORE INTO hidden_podcasts (feed_url) VALUES (?)", (feed,))

    def is_hidden(self, feed):
        return self.db.one("SELECT 1 FROM hidden_podcasts WHERE feed_url = ?", (feed,)) is not None

    # --- progression ---
    def save_progress(self, episode):
        """episode : {id, feed, title, podcast, image, audio, pos, dur}. Un épisode fini est marqué « écouté »."""
        position, duration = float(episode.get("pos", 0)), float(episode.get("dur", 0))
        finished = duration > 0 and position >= duration - FINISHED_MARGIN_S
        self.db.execute(
            "INSERT INTO episode_progress (episode_id, feed_url, title, podcast_title, image_url, audio_url, position_s, "
            "duration_s, played, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (episode_id) DO UPDATE SET "
            "feed_url = excluded.feed_url, title = excluded.title, podcast_title = excluded.podcast_title, "
            "image_url = excluded.image_url, audio_url = excluded.audio_url, position_s = excluded.position_s, "
            "duration_s = excluded.duration_s, played = excluded.played, updated_at = excluded.updated_at",
            (episode["id"], episode.get("feed", ""), episode.get("title", ""), episode.get("podcast", ""),
             episode.get("image", ""), episode.get("audio", ""), 0 if finished else position, duration,
             int(finished), int(time.time())))

    def mark_played(self, episode_id, played=True):
        if played:
            self.db.execute("UPDATE episode_progress SET played = 1, position_s = 0 WHERE episode_id = ?", (episode_id,))
        else:
            self.db.execute("UPDATE episode_progress SET played = 0 WHERE episode_id = ?", (episode_id,))

    def forget(self, episode_id):
        """Retire un épisode de « Reprendre l'écoute » (sa position est oubliée)."""
        self.db.execute("DELETE FROM episode_progress WHERE episode_id = ?", (episode_id,))

    def progress_of(self, episode_id):
        row = self.db.one("SELECT * FROM episode_progress WHERE episode_id = ?", (episode_id,))
        return _progress(row) if row else None

    def progress_for_feed(self, feed):
        return {r["episode_id"]: _progress(r) for r in self.db.query("SELECT * FROM episode_progress WHERE feed_url = ?", (feed,))}

    def resume_list(self):
        """Épisodes commencés et non terminés, le plus récent d'abord."""
        rows = self.db.query("SELECT * FROM episode_progress WHERE played = 0 AND position_s > 10 "
                             "ORDER BY updated_at DESC, rowid DESC LIMIT ?", (MAX_RESUME,))
        return [_progress(r) for r in rows]
WEBEOF_103
cat > "$APP_DIR/pimedia/storage/queue.py" <<'WEBEOF_104'
"""File d'attente commune du Pi.

L'écran du Pi joue la file et en envoie une copie à chaque changement (snapshot) : elle est gardée en base,
retrouvée après un redémarrage, et visible des téléphones. Les téléphones, eux, déposent des demandes d'ajout
que l'écran prend et range dans sa file (après le titre en cours, ou à la fin)."""
import json
import time

from ..entities import QueueItem, QueueRequest, QueueSnapshot, Track

MAX_ITEMS = 2000
MAX_PENDING_REQUESTS = 50
MODES = ("next", "end")


class PlayQueue:
    def __init__(self, db):
        self.db = db

    # --- la file jouée par l'écran ---
    def snapshot(self):
        rows = self.db.query("SELECT * FROM queue_items ORDER BY position")
        state = self.db.one("SELECT current_item_id, version FROM queue_state WHERE id = 1")
        items = [QueueItem(r["id"], r["position"], Track(json.loads(r["track"])), r["added_by"], r["added_at"]) for r in rows]
        return QueueSnapshot(items, state["current_item_id"], state["version"])

    def replace(self, entries, current_index):
        """entries : [(Track, added_by)] dans l'ordre ; current_index : titre en cours (-1 : aucun). Renvoie la file."""
        entries = list(entries)[:MAX_ITEMS]
        now = int(time.time())
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM queue_items")
            current_id = None
            for position, (track, added_by) in enumerate(entries):
                cursor = conn.execute("INSERT INTO queue_items (position, track, added_by, added_at) VALUES (?, ?, ?, ?)",
                                      (position, json.dumps(track.fields, ensure_ascii=False), added_by or "screen", now))
                if position == current_index:
                    current_id = cursor.lastrowid
            conn.execute("UPDATE queue_state SET current_item_id = ?, version = version + 1 WHERE id = 1", (current_id,))
        return self.snapshot()

    # --- demandes des téléphones ---
    def request(self, track, mode, added_by):
        if mode not in MODES:
            raise ValueError("mode inconnu")
        with self.db.transaction() as conn:
            if conn.execute("SELECT COUNT(*) FROM queue_requests").fetchone()[0] >= MAX_PENDING_REQUESTS:
                raise ValueError("Trop de demandes en attente")
            cursor = conn.execute("INSERT INTO queue_requests (track, mode, added_by, requested_at) VALUES (?, ?, ?, ?)",
                                  (json.dumps(track.fields, ensure_ascii=False), mode, added_by, int(time.time())))
        return cursor.lastrowid

    def pending(self):
        rows = self.db.query("SELECT * FROM queue_requests ORDER BY id")
        return [QueueRequest(r["id"], Track(json.loads(r["track"])), r["mode"], r["added_by"]) for r in rows]

    def take_requests(self):
        """Demandes en attente, retirées de la base (l'écran les range dans sa file)."""
        with self.db.transaction() as conn:
            rows = conn.execute("SELECT * FROM queue_requests ORDER BY id").fetchall()
            conn.execute("DELETE FROM queue_requests WHERE id <= ?", (rows[-1]["id"] if rows else 0,))
        return [QueueRequest(r["id"], Track(json.loads(r["track"])), r["mode"], r["added_by"]) for r in rows]
WEBEOF_104
cat > "$APP_DIR/pimedia/storage/schema.py" <<'WEBEOF_105'
"""Schéma de la base. Une migration = un script SQL, appliqué une seule fois, dans l'ordre.
Ne jamais modifier une migration déjà publiée : en ajouter une nouvelle à la fin."""

MIGRATIONS = [
    # 1 : première version (remplace config.json et les fichiers JSON de données)
    """
    CREATE TABLE app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL                     -- valeur JSON
    );
    CREATE TABLE podcast_subscriptions (
        feed_url TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        image_url TEXT NOT NULL DEFAULT '',
        author TEXT NOT NULL DEFAULT '',
        subscribed_at INTEGER NOT NULL
    );
    CREATE TABLE hidden_podcasts (
        feed_url TEXT PRIMARY KEY
    );
    CREATE TABLE episode_progress (
        episode_id TEXT PRIMARY KEY,
        feed_url TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        podcast_title TEXT NOT NULL DEFAULT '',
        image_url TEXT NOT NULL DEFAULT '',
        audio_url TEXT NOT NULL DEFAULT '',
        position_s REAL NOT NULL DEFAULT 0,
        duration_s REAL NOT NULL DEFAULT 0,
        played INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL
    );
    CREATE INDEX episode_progress_feed ON episode_progress (feed_url);
    CREATE TABLE local_playlists (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE playlist_tracks (
        playlist_id TEXT NOT NULL REFERENCES local_playlists (id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        track_id TEXT NOT NULL,
        track TEXT NOT NULL,                    -- titre au format de l'interface (JSON)
        PRIMARY KEY (playlist_id, position)
    );
    CREATE TABLE external_favorites (
        track_id TEXT PRIMARY KEY,
        track TEXT NOT NULL,
        added_at INTEGER NOT NULL
    );
    CREATE TABLE search_history (
        kind TEXT NOT NULL,                     -- « music » ou « podcasts »
        query TEXT NOT NULL,
        query_key TEXT NOT NULL,                -- en minuscules : une recherche refaite remonte au lieu d'être répétée
        searched_at INTEGER NOT NULL,
        PRIMARY KEY (kind, query_key)
    );
    CREATE TABLE unplayable_videos (
        video_id TEXT PRIMARY KEY,
        marked_at INTEGER NOT NULL
    );
    CREATE TABLE play_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        track_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        artist TEXT NOT NULL DEFAULT '',
        album TEXT NOT NULL DEFAULT '',
        album_id TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT 'subsonic',
        played_at INTEGER NOT NULL
    );
    CREATE INDEX play_history_album ON play_history (album_id, played_at);
    CREATE TABLE queue_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        position INTEGER NOT NULL,
        track TEXT NOT NULL,                    -- JSON
        added_by TEXT NOT NULL DEFAULT 'screen',
        added_at INTEGER NOT NULL
    );
    CREATE INDEX queue_items_position ON queue_items (position);
    CREATE TABLE queue_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        current_item_id INTEGER,
        version INTEGER NOT NULL DEFAULT 0
    );
    INSERT INTO queue_state (id, current_item_id, version) VALUES (1, NULL, 0)
    """,
    # 2 : demandes d'ajout à la file (téléphones) en attente d'être prises par l'écran du Pi
    """
    CREATE TABLE queue_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        track TEXT NOT NULL,                    -- JSON
        mode TEXT NOT NULL CHECK (mode IN ('next', 'end')),
        added_by TEXT NOT NULL,
        requested_at INTEGER NOT NULL
    )
    """,
]
WEBEOF_105
cat > "$APP_DIR/pimedia/storage/videos.py" <<'WEBEOF_106'
"""Vidéos YouTube que le lecteur intégré a refusées : on ne les propose plus."""
import re
import time

MAX_IDS = 5000
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


class UnplayableVideos:
    def __init__(self, db):
        self.db = db

    def __contains__(self, video_id):
        return self.db.one("SELECT 1 FROM unplayable_videos WHERE video_id = ?", (str(video_id),)) is not None

    def add(self, video_id):
        video_id = str(video_id or "")
        if not VIDEO_ID.match(video_id):
            raise ValueError("identifiant de vidéo invalide")
        with self.db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO unplayable_videos (video_id, marked_at) VALUES (?, ?)", (video_id, time.time_ns()))
            conn.execute("DELETE FROM unplayable_videos WHERE rowid NOT IN "
                         "(SELECT rowid FROM unplayable_videos ORDER BY marked_at DESC LIMIT ?)", (MAX_IDS,))
WEBEOF_106
cat > "$APP_DIR/i18n/fr.yaml" <<'WEBEOF_107'
# Textes de Pi Media Station, en français. Clés en anglais, organisées par partie.
# Les {accolades} sont remplacées à l'affichage (ex. {name}).

server:
  errors:
    refused: "Refusé"
    invalid_request: "Requête invalide"
    pi_only: "Réservé à l’écran du Pi"
  podcasts:
    unknown_theme: "Thème inconnu"
    directories_unreachable: "Annuaires injoignables"
  player:
    unavailable: "Lecteur haute fidélité indisponible : {reason}"
    refused_address: "Adresse refusée"
  queue:
    empty: "La file d’attente est vide"
    added: "Ajouté à la file"
    added_next: "Ajouté après ce titre"

web:
  queue:
    title: "File d’attente"
    added_by_phone: "Ajouté depuis un téléphone"
    play_next: "Après ce titre"
    add_to_end: "À la fin de la file"
    remove: "Retirer de la file"
    clear: "Vider la file"
  phone:
    add_from_library: "Chercher dans la bibliothèque"
    add_link: "Coller un lien (YouTube, Spotify, Deezer…)"
    added: "Ajouté à la file du Pi ✓"

launcher:
  weather:
    unknown: "Variable"
    codes:   # codes météo WMO (Open-Meteo)
      "0": "Ciel dégagé"
      "1": "Éclaircies"
      "2": "Éclaircies"
      "3": "Couvert"
      "45": "Brouillard"
      "48": "Brouillard"
      "51": "Bruine"
      "52": "Bruine"
      "53": "Bruine"
      "54": "Bruine"
      "55": "Bruine"
      "56": "Bruine"
      "57": "Bruine"
      "61": "Pluie"
      "62": "Pluie"
      "63": "Pluie"
      "64": "Pluie"
      "65": "Pluie"
      "66": "Pluie"
      "67": "Pluie"
      "71": "Neige"
      "72": "Neige"
      "73": "Neige"
      "74": "Neige"
      "75": "Neige"
      "76": "Neige"
      "77": "Neige"
      "80": "Averses"
      "81": "Averses"
      "82": "Averses"
      "85": "Neige"
      "86": "Neige"
      "95": "Orage"
      "96": "Orage"
      "99": "Orage"
WEBEOF_107
cat > "$APP_DIR/deploy/build_archive.py" <<'WEBEOF_108'
#!/usr/bin/env python3
"""Fabrique l'archive à déployer sur le Pi : dist/pi-media-<version>.tar.gz (+ une copie de deploy.sh).

Usage : python3 deploy/build_archive.py [version]      (par défaut : date et heure, ex. 2026.10.25-1530)
Contenu : le code et les fichiers nécessaires, jamais de données ni de secrets (.env, *.db, config.json)."""
import io
import os
import shutil
import sys
import tarfile
import time

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCLUDED = ("pimedia", "web", "i18n", "deploy", "launcher.py", "subsonic-web.py", ".env.example")
EXCLUDED_DIRS = {"__pycache__", "dist"}
EXCLUDED_SUFFIXES = (".pyc", ".db", ".db-wal", ".db-shm", ".importe")
EXCLUDED_NAMES = {".env", "config.json"}


def wanted(path):
    name = os.path.basename(path)
    return name not in EXCLUDED_NAMES and not name.endswith(EXCLUDED_SUFFIXES)


def files():
    for entry in INCLUDED:
        full = os.path.join(PROJECT, entry)
        if os.path.isfile(full):
            yield entry
            continue
        for directory, subdirs, names in os.walk(full):
            subdirs[:] = sorted(d for d in subdirs if d not in EXCLUDED_DIRS)
            for name in sorted(names):
                relative = os.path.relpath(os.path.join(directory, name), PROJECT)
                if wanted(relative):
                    yield relative


def build(version):
    dist = os.path.join(PROJECT, "dist")
    os.makedirs(dist, exist_ok=True)
    archive = os.path.join(dist, "pi-media-%s.tar.gz" % version)
    with tarfile.open(archive, "w:gz") as tar:
        for relative in files():
            tar.add(os.path.join(PROJECT, relative), arcname=relative, recursive=False)
        data = (version + "\n").encode()
        info = tarfile.TarInfo("VERSION")
        info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
        tar.addfile(info, io.BytesIO(data))
    shutil.copy(os.path.join(PROJECT, "deploy", "deploy.sh"), os.path.join(dist, "deploy.sh"))
    shutil.copy(os.path.join(PROJECT, "deploy", "bin", "migration.sh"), os.path.join(dist, "migration.sh"))
    return archive


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y.%m.%d-%H%M")))
WEBEOF_108
cat > "$APP_DIR/deploy/deploy.sh" <<'WEBEOF_109'
#!/usr/bin/env bash
# Installe ou met à jour Pi Media Station sur le Pi à partir d'une archive.
#
#   bash deploy.sh                                   installe l'archive pi-media-*.tar.gz la plus récente posée à côté
#   bash deploy.sh pi-media-2026.10.25-1530.tar.gz   installe cette version et la démarre
#   bash deploy.sh --configure                       (re)demande l'adresse Subsonic, l'utilisateur et le mot de passe
#   bash deploy.sh --rollback                        revient à la version précédente
#   bash deploy.sh --status                          versions installées et version active
#
# Au premier déploiement, les réglages manquants sont demandés (le mot de passe ne s'affiche pas) ;
# une ancienne installation (config.json) est reprise telle quelle : rien à ressaisir.
#
# Le code va dans ~/.local/share/pi-media/releases/<version>/, « current » pointe sur la version active.
# Les données (.env, pi-media.db) restent dans ~/.local/share/pi-media/ : une mise à jour n'y touche pas.
set -euo pipefail

APP_DIR="${PI_MEDIA_HOME:-$HOME/.local/share/pi-media}"
RELEASES="$APP_DIR/releases"
KEEP=3
PORT="${PI_MEDIA_PORT:-8099}"
UNIT_DIR="$HOME/.config/systemd/user"

say() { echo "==> $*"; }
die() { echo "Erreur : $*" >&2; exit 1; }

active_version() { [ -L "$APP_DIR/current" ] && basename "$(readlink "$APP_DIR/current")" || true; }

activate() {                                   # bascule « current » d'un coup (pas d'état intermédiaire)
  ln -sfn "releases/$1" "$APP_DIR/current.new"
  mv -T "$APP_DIR/current.new" "$APP_DIR/current"
}

link_entry_points() {                          # chemins historiques (démarrage du menu, raccourcis) gardés
  ln -sfn current/launcher.py "$APP_DIR/launcher.py"
  for script in start-menu.sh set-subsonic.sh set-podcastindex.sh migration.sh; do
    ln -sfn "current/deploy/bin/$script" "$APP_DIR/$script"
  done
}

install_service() {
  mkdir -p "$UNIT_DIR"
  cp "$APP_DIR/current/deploy/systemd/subsonic-web.service" "$UNIT_DIR/subsonic-web.service"
  systemctl --user daemon-reload
  systemctl --user enable subsonic-web >/dev/null 2>&1 || true
  systemctl --user restart subsonic-web
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
  for old in subsonic_web pimedia web i18n deploy subsonic-web.py launcher.py start-menu.sh set-subsonic.sh set-podcastindex.sh; do
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
  if [ -z "$force" ] && [ -n "$(env_value SUBSONIC_URL)" ]; then return 0; fi
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
    echo "Détails : journalctl --user -u subsonic-web -n 40 --no-pager" >&2
    activate "$previous"
    link_entry_points
    install_service
    rm -rf "${RELEASES:?}/$version"            # version défectueuse retirée : un --rollback ne pourra pas y revenir
    exit 1
  else
    die "le serveur ne répond pas (journalctl --user -u subsonic-web -n 40 --no-pager)"
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
  --configure) [ -L "$APP_DIR/current" ] || die "rien d'installé"; configure force; install_service
               healthy "$(active_version)" && say "Serveur redémarré avec les nouveaux réglages" ;;
  *.tar.gz) deploy "$1" ;;
  "") archive="$(latest_archive)"; [ -n "$archive" ] || die "aucune archive pi-media-*.tar.gz trouvée"
      deploy "$archive" ;;
  *) sed -n '2,14p' "$0"; exit 1 ;;
esac
WEBEOF_109
cat > "$APP_DIR/deploy/bin/migration.sh" <<'WEBEOF_110'
#!/usr/bin/env bash
# Reprend les réglages de l'ancienne version (config.json) dans le .env :
# adresse, utilisateur et mot de passe Subsonic, clés API (YouTube, Jamendo, Podcast Index), réglages du menu.
# Les valeurs déjà présentes dans le .env sont gardées. Lancé automatiquement par deploy.sh ; relançable sans risque.
# Usage : bash migration.sh
set -euo pipefail
APP_DIR="${PI_MEDIA_HOME:-$HOME/.local/share/pi-media}"
CODE="$APP_DIR/current"; [ -d "$CODE/pimedia" ] || CODE="$APP_DIR"
[ -d "$CODE/pimedia" ] || { echo "Pi Media Station n'est pas installé : lancez d'abord deploy.sh" >&2; exit 1; }
cd "$CODE"
PI_MEDIA_DATA="$APP_DIR" python3 -m pimedia.cli migrate
WEBEOF_110
cat > "$APP_DIR/deploy/bin/set-podcastindex.sh" <<'WEBEOF_111'
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
WEBEOF_111
cat > "$APP_DIR/deploy/bin/set-subsonic.sh" <<'WEBEOF_112'
#!/usr/bin/env bash
# Enregistre le serveur Subsonic dans le .env du Pi.
# Usage : set-subsonic.sh https://adresse utilisateur motdepasse
set -euo pipefail
if [ $# -ne 3 ]; then
  echo "Usage : $0 URL UTILISATEUR MOTDEPASSE" >&2
  exit 1
fi
APP_DIR="${PI_MEDIA_HOME:-$HOME/.local/share/pi-media}"
CODE="$APP_DIR/current"; [ -d "$CODE" ] || CODE="$APP_DIR"
cd "$CODE"
python3 -m pimedia.cli set "SUBSONIC_URL=${1%/}" "SUBSONIC_USER=$2" "SUBSONIC_PASS=$3"
systemctl --user restart subsonic-web 2>/dev/null || true
echo "OK : serveur Subsonic enregistré."
WEBEOF_112
cat > "$APP_DIR/deploy/bin/start-menu.sh" <<'WEBEOF_113'
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
WEBEOF_113
cat > "$APP_DIR/deploy/systemd/subsonic-web.service" <<'WEBEOF_114'
[Unit]
Description=Pi Media Station : relais Subsonic, interface tactile, podcasts, lecture haute fidélité
After=pipewire.service pipewire-pulse.service network-online.target

[Service]
# %h : dossier personnel. Code dans current/ (lien vers la version installée), données à côté.
Environment=PI_MEDIA_DATA=%h/.local/share/pi-media
ExecStart=/usr/bin/python3 %h/.local/share/pi-media/current/subsonic-web.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
WEBEOF_114

# Scripts de réglage et de relance du menu (versions de deploy/bin, qui écrivent dans le .env)
for script in set-subsonic.sh set-podcastindex.sh start-menu.sh; do
  install -m 755 "$APP_DIR/deploy/bin/$script" "$APP_DIR/$script"
done
chmod +x "$APP_DIR/subsonic-web.py"

# Autorise le bouton « Coller » : en plein écran (kiosque), Chromium ne peut pas afficher sa demande d'autorisation.
# Politique limitée à l'adresse locale de l'interface.
sudo mkdir -p /etc/chromium/policies/managed
echo '{"ClipboardAllowedForUrls": ["http://127.0.0.1:8099"]}' | sudo tee /etc/chromium/policies/managed/pi-media-clipboard.json >/dev/null   || echo "Autorisation du presse-papiers non installée (sudo refusé) : le bouton Coller restera bloqué."

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
  SP_NAME="$(sed -n 's/.*-a "\([^"]*\)".*/\1/p' "$SP_SERVICE" | head -1)"
  [ -n "$SP_NAME" ] || SP_NAME="$(sed -n 's/.*name = "\([^"]*\)".*/\1/p' "$SP_CONF" 2>/dev/null | head -1)"
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
systemctl --user restart subsonic-web || \
  echo "(Subsonic Web démarrera au prochain redémarrage)"

echo "==> 7/7 Terminé"
echo "Redémarrez : sudo reboot"
echo "Subsonic Web : ~/.local/share/pi-media/set-subsonic.sh https://adresse utilisateur motdepasse"
echo "Apple Music : sur l'iPhone/Mac, icône AirPlay > « $AIRPLAY_NAME »."
echo "Bluetooth : bouton Bluetooth du menu, puis « $AIRPLAY_NAME » sur le téléphone."
echo "Météo : ville réglée sur $VILLE (modifiable dans $APP_DIR/config.json)."
