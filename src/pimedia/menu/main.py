"""Assemble le menu : réglages, thème, textes, services, puis l'interface Tk et ses tâches de fond."""
import os
import shutil
import threading

from ..i18n import Texts
from ..paths import resolve_data_dir
from .audio import AudioArbiter, PulseAudio
from .config import MenuConfig
from .idle import IdleTimer, saver_decision
from .players import MprisPlayers, Radio, WebPlayer, poll_forever
from .spectrum import Spectrum
from .stations import STATIONS
from .system import AppLauncher, InputWatcher, Power, start_bluetooth_pairing
from .theme import load_theme
from .weather import Weather

# Applis Electron en Wayland natif : défilement au doigt + clavier tactile
ELECTRON_FLAGS = ["--ozone-platform=wayland", "--enable-wayland-ime"]


class Services:
    """Tout ce dont l'interface a besoin, sans Tk : remplaçable par des doublures dans les tests."""

    def __init__(self, code_dir, data_dir, environ=None):
        environ = dict(os.environ if environ is None else environ)
        self.code_dir, self.data_dir = code_dir, data_dir
        self.config = MenuConfig.load(data_dir, environ)
        self.texts = Texts(os.path.join(code_dir, "i18n"), self.config.language)
        self.theme = load_theme(os.path.join(code_dir, "themes"), self.config.theme)
        self.stations = STATIONS
        self.idle = IdleTimer()
        self.pulse = PulseAudio()
        self.mpris = MprisPlayers()
        self.web_player = WebPlayer(self.config)
        self.radio = Radio()
        self.apps = AppLauncher(env=dict(environ, ELECTRON_OZONE_PLATFORM_HINT="auto"))
        self.power = Power()
        self.weather = Weather(self.config, self.texts)
        self.spectrum = Spectrum(self.theme.equalizer.columns, self.pulse)
        self.input_watcher = InputWatcher(self.idle.touch)
        self.arbiter = AudioArbiter(self.pulse, {
            "mpv": self.radio.stop,
            "web": self.web_player.pause,
            "feishin": lambda: self.mpris.pause_matching("feishin"),
            "bluetooth": lambda: self.mpris.pause_matching("bluez"),
            "airplay": self.restart_airplay,      # on ne peut pas mettre AirPlay en pause : on coupe la session
        })
        self.freetube_command = ["freetube"] + ELECTRON_FLAGS
        self._now_playing = ""

    # --- utilisés par l'interface ---
    def web_command(self, path=""):
        """Interface web dans une fenêtre dédiée, plein écran total. Profil séparé : sinon Chromium se greffe sur
        une instance existante et se ferme aussitôt."""
        exe = shutil.which("chromium") or shutil.which("chromium-browser")
        if not exe:
            return None
        return [exe, "--app=" + self.config.web(path), "--kiosk", "--autoplay-policy=no-user-gesture-required",
                "--user-data-dir=" + os.path.expanduser("~/.config/pi-media-chromium"),
                "--no-first-run", "--password-store=basic"]

    def start_bluetooth(self):
        start_bluetooth_pairing(self.data_dir)

    def pause_other_players(self):
        self.mpris.pause_all()
        self.web_player.pause()

    def restart_airplay(self):
        self.pulse.run(["systemctl", "--user", "restart", "shairport-sync"], timeout=10)

    def now_playing(self):
        return self._now_playing

    def saver_decision(self, saver_visible):
        return saver_decision(self.idle.idle_seconds(), self.config.screensaver_seconds, saver_visible,
                              self.apps.name, self.input_watcher.available)

    # --- tâches de fond ---
    def _refresh_now_playing(self):
        self._now_playing = self.mpris.now_playing()

    def _keep_awake(self):
        if self.web_player.wants_awake():
            self.idle.touch()

    def background_tasks(self):
        return (self.weather.loop, self.spectrum.loop, self.input_watcher.loop, self.arbiter.loop,
                lambda: poll_forever(self._refresh_now_playing, 3), lambda: poll_forever(self._keep_awake, 10))

    def start_background(self):
        for task in self.background_tasks():
            threading.Thread(target=task, daemon=True).start()


def build(code_dir, tk=None, environ=None):
    """Prépare le menu sans le lancer : une erreur ici permet de basculer sur le menu de secours."""
    if tk is None:
        import tkinter as tk
    from .ui import MenuUI
    environ = os.environ if environ is None else environ
    services = Services(code_dir, resolve_data_dir(code_dir, environ), environ)
    return services, MenuUI(tk, services)


def start(services, ui):
    services.start_background()
    ui.run()
