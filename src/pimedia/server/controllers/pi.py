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
