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
