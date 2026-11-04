#!/usr/bin/env python3
"""Menu de SECOURS (ancienne version d’un seul tenant) : lancé par launcher.py si le menu en modules
ne démarre pas. Ne plus le modifier ; il disparaîtra quand le nouveau menu aura fait ses preuves sur le Pi."""
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


root = tk.Tk()
root.title("Accueil")
root.configure(bg=BG)
root.attributes("-fullscreen", True)
root.update_idletasks()
SW = max(root.winfo_screenwidth(), 320)
SH = max(root.winfo_screenheight(), 240)
SC = min(SW / 800.0, SH / 480.0)      # 1.0 sur l'écran officiel 800x480


def px(v):
    return max(1, int(round(v * SC)))


def font(size, bold=True, mono=True):
    """Police en PIXELS (taille négative en Tk) : indépendante du réglage DPI."""
    return ("DejaVu Sans Mono" if mono else "DejaVu Sans", -px(size),
            "bold" if bold else "normal")


def make_eq(parent, w, h, bg):
    canvas = tk.Canvas(parent, width=w, height=h, bg=bg, highlightthickness=0)
    bw = w / NB
    sh = h / SEG
    segs = []
    for i in range(NB):
        col = []
        for s in range(SEG):
            y1 = h - s * sh
            y0 = y1 - sh + 1
            col.append(canvas.create_rectangle(i * bw + 1, y0, (i + 1) * bw - 1, y1,
                                               fill=SEG_OFF, outline=""))
        segs.append(col)
    return {"canvas": canvas, "segs": segs, "lit": [0] * NB}


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
