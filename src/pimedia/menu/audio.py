"""Son du Pi : flux en cours (pactl), volume, et arbitre « le dernier qui démarre gagne »."""
import re
import subprocess
import time
from dataclasses import dataclass

HIFI_STREAM = "pi-media-hifi"   # mpv de la lecture haute fidélité : c'est le lecteur de la page, pas la radio


def run_command(args, timeout=3):
    """Sortie texte d'une commande ; vide si elle échoue (programme absent, délai dépassé)."""
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


@dataclass
class AudioStream:
    id: int
    corked: bool = False        # en pause
    binary: str = ""            # programme (application.process.binary)
    name: str = ""              # application.name

    @property
    def label(self):
        """Nom qui identifie le flux : le nom d'application pour la haute fidélité, sinon le programme."""
        if HIFI_STREAM in self.name:
            return HIFI_STREAM
        return self.binary or self.name


def parse_sink_inputs(text):
    """Sortie de « pactl list sink-inputs » -> [AudioStream]."""
    streams, current = [], None
    for line in text.splitlines():
        match = re.match(r"Sink Input #(\d+)", line)
        if match:
            current = AudioStream(int(match.group(1)))
            streams.append(current)
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("Corked:"):
            current.corked = stripped.split(":", 1)[1].strip() == "yes"
        elif stripped.startswith("application.process.binary"):
            current.binary = stripped.split("=", 1)[1].strip().strip('"').lower()
        elif stripped.startswith("application.name"):
            current.name = stripped.split("=", 1)[1].strip().strip('"').lower()
    return streams


def parse_volume(text):
    match = re.search(r"(\d+)%", text or "")
    return int(match.group(1)) if match else None


# famille d'application d'après le nom du flux : (mot cherché, famille), dans l'ordre
FAMILIES = ((HIFI_STREAM, "web"),      # se met en pause par la page, comme le lecteur du navigateur
            ("mpv", "mpv"), ("chrom", "web"), ("feishin", "feishin"), ("electron", "feishin"),
            ("shairport", "airplay"), ("bluez", "bluetooth"), ("bluetooth", "bluetooth"))


def family_of(label):
    name = (label or "").lower()
    for word, family in FAMILIES:
        if word in name:
            return family
    return name or "inconnu"


def families_to_silence(previous, running):
    """Le dernier qui démarre gagne. previous / running : {id_flux: nom}.
    Renvoie les familles déjà en cours, autres que celle(s) qui viennent de démarrer."""
    new = {k: v for k, v in running.items() if k not in previous}
    if not new:
        return []
    new_families = {family_of(v) for v in new.values()}
    result = []
    for key, label in running.items():
        family = family_of(label)
        if key not in new and family not in new_families and family not in result:
            result.append(family)
    return result


class PulseAudio:
    def __init__(self, run=run_command):
        self.run = run

    def streams(self):
        return parse_sink_inputs(self.run(["pactl", "list", "sink-inputs"]))

    def playing(self):
        """Vrai si un programme envoie réellement du son (flux non en pause)."""
        return any(not s.corked for s in self.streams())

    def volume(self):
        return parse_volume(self.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]))

    def change_volume(self, delta):
        """Volume + delta (borné 0..100) ; None si le volume est illisible."""
        current = self.volume()
        if current is None:
            return None
        value = max(0, min(100, current + delta))
        self.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "%d%%" % value])
        return value


class AudioArbiter:
    """Quand une source démarre (AirPlay, radio, lecteur web, Bluetooth…), les autres se taisent."""

    def __init__(self, pulse, silencers):
        self.pulse = pulse
        self.silencers = silencers      # {famille: fonction sans argument}
        self.previous = {}

    def step(self):
        running = {s.id: s.label for s in self.pulse.streams() if not s.corked}
        silenced = families_to_silence(self.previous, running)
        for family in silenced:
            action = self.silencers.get(family)
            if action:
                try:
                    action()
                except Exception:       # une source récalcitrante ne doit pas arrêter l'arbitre
                    pass
        self.previous = running
        return silenced

    def loop(self, every=1.2):
        while True:
            self.step()
            time.sleep(every)
