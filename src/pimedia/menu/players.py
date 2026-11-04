"""Les lecteurs que le menu pilote : lecteurs MPRIS (playerctl), lecteur web du Pi, radio (mpv)."""
import json
import shutil
import subprocess
import time
import urllib.request

from .audio import run_command


def open_url(url, timeout=2):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


class MprisPlayers:
    """Feishin, Bluetooth (bluez), AirPlay (shairport-sync)… via playerctl."""

    def __init__(self, run=run_command, which=shutil.which):
        self.run = run
        self.which = which

    def now_playing(self):
        """« Artiste – Titre » du premier lecteur en lecture, sinon ""."""
        if not self.which("playerctl"):
            return ""
        out = self.run(["playerctl", "-a", "metadata", "--format", "{{status}}|{{artist}} – {{title}}"], timeout=5)
        for line in out.splitlines():
            if line.startswith("Playing|"):
                return line.split("|", 1)[1].strip(" –")
        return ""

    def pause_all(self):
        self.run(["playerctl", "-a", "pause"])

    def pause_matching(self, word):
        for player in self.run(["playerctl", "-l"]).split():
            if word in player.lower():
                self.run(["playerctl", "-p", player, "pause"])


class WebPlayer:
    """Le lecteur de la page web (subsonic-web.py), joint par son adresse locale."""

    def __init__(self, config, opener=open_url):
        self.config = config
        self.opener = opener

    def pause(self):
        try:
            self.opener(self.config.web("/control/send?cmd=pause"))
        except OSError:
            pass

    def wants_awake(self):
        """La page (paroles affichées) demande qu'on ne lance pas l'écran de veille."""
        try:
            return bool(json.loads(self.opener(self.config.web("/control/awake")).decode()).get("awake"))
        except (OSError, ValueError, AttributeError):
            return False


class Radio:
    """Une radio à la fois, jouée par mpv."""

    def __init__(self, spawn=subprocess.Popen, which=shutil.which):
        self.spawn = spawn
        self.which = which
        self.process = None
        self.station = None
        self.interrupted = False

    def play(self, station):
        """False si mpv est absent."""
        self.stop()
        if not self.which("mpv"):
            return False
        self.process = self.spawn(["mpv", "--no-video", "--really-quiet", "--cache=yes", station.url],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.station = station
        return True

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
        self.process = None
        self.station = None
        self.interrupted = False

    def check(self):
        """À appeler régulièrement : repère une radio coupée toute seule (flux perdu)."""
        if self.process is not None and self.process.poll() is not None:
            self.process = None
            self.station = None
            self.interrupted = True


def poll_forever(action, every):
    while True:
        action()
        time.sleep(every)
