"""Ce que le menu demande au système : lancer une appli, l'extinction, le Bluetooth, les touchers."""
import glob
import os
import select
import shutil
import subprocess
import threading


class AppLauncher:
    """Une seule appli à la fois (lecteur web en kiosque, FreeTube…) ; le menu se cache pendant ce temps."""

    def __init__(self, env=None, spawn=subprocess.Popen, which=shutil.which):
        self.env = env
        self.spawn = spawn
        self.which = which
        self.process = None
        self.name = None

    @property
    def running(self):
        return self.process is not None

    def launch(self, command):
        """True si lancée ; False si une appli tourne déjà ; FileNotFoundError si le programme manque."""
        if self.process is not None:
            return False
        exe = self.which(command[0])
        if not exe:
            raise FileNotFoundError(command[0])
        self.process = self.spawn([exe] + list(command[1:]), env=self.env)
        self.name = os.path.basename(command[0])
        return True

    def finished(self):
        """True une seule fois, quand l'appli vient de se fermer."""
        if self.process is not None and self.process.poll() is not None:
            self.process = None
            self.name = None
            return True
        return False


POWER_COMMANDS = (
    # --no-ask-password : sans droit suffisant, systemctl échoue au lieu d'ouvrir une demande de mot de passe
    # cachée derrière le plein écran (c'est ce qui figeait le menu)
    ["systemctl", "--no-ask-password"],
    ["sudo", "-n", "systemctl"],          # -n : jamais de question ; autorisé par /etc/sudoers.d/pi-media-power
)
POWER_ACTIONS = ("poweroff", "reboot")


class Power:
    def __init__(self, run=subprocess.run):
        self.run = run

    def execute(self, action):
        """True si le système a accepté. À appeler hors de la boucle de l'interface (peut prendre du temps)."""
        if action not in POWER_ACTIONS:
            raise ValueError(action)
        for prefix in POWER_COMMANDS:
            try:
                if self.run(prefix + [action], capture_output=True, timeout=20).returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError):
                continue
        return False

    def execute_in_background(self, action, on_refused):
        def work():
            if not self.execute(action):
                on_refused()
        threading.Thread(target=work, daemon=True).start()


def start_bluetooth_pairing(app_dir, spawn=subprocess.Popen):
    spawn([os.path.join(app_dir, "bt-pairing.sh")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class InputWatcher:
    """Détecte les touchers/souris/clavier même quand une appli est au premier plan (/dev/input)."""

    def __init__(self, on_input, pattern="/dev/input/event*"):
        self.on_input = on_input
        self.pattern = pattern
        self.available = False

    def open_devices(self):
        fds = []
        for path in glob.glob(self.pattern):
            try:
                fds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
            except OSError:
                pass
        self.available = bool(fds)
        return fds

    def loop(self):
        fds = self.open_devices()
        while fds:
            ready, _, _ = select.select(fds, [], [], 5)
            for fd in ready:
                try:
                    os.read(fd, 4096)
                except OSError:
                    pass
            if ready:
                self.on_input()
