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
PHONE_FILES_PREFIX = "/phone-files/"    # fichiers envoyés depuis un téléphone
RELEASE_AFTER = 30      # secondes de pause (ou de file vide) après lesquelles mpv lâche la sortie audio
WATCH_EVERY = 5         # secondes entre deux vérifications
WAKE_TIMEOUT = 5        # secondes d'attente du chargement du titre à la reprise


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

    def alive(self):
        return self.sock is not None and self.process is not None and self.process.poll() is None

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

    def __init__(self, config, socket_path, local_base, command=None, release_after=RELEASE_AFTER,
                 clock=time.monotonic):
        self.config = config
        self.local_base = local_base           # fonction : « http://127.0.0.1:8099 » (port réel du serveur)
        self.mpv = MpvConnection(socket_path, command, self._on_event)
        self._lock = threading.Lock()
        self.props = {}
        self.current = ""                      # adresse (telle que la page la connaît) du titre en cours
        self.queued = ""                       # titre suivant préchargé (enchaînement sans blanc)
        self.ended = 0                         # compteurs : la page voit qu'un titre s'est fini ou a échoué
        self.errors = 0
        self.release_after = release_after
        self.clock = clock
        self.released = None                   # {url, pos, live} quand mpv est arrêté pour libérer la sortie audio
        self._silent_since = None
        self._volume = None
        self._power = threading.RLock()        # une commande à la fois, et jamais pendant la libération

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
                    "idle": bool(props.get("idle-active", True)), "released": self.released is not None, "ended": self.ended, "errors": self.errors}

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
        if not parts.scheme and not parts.netloc and (parts.path == STREAM_PATH or
                                                      (parts.path.startswith(PHONE_FILES_PREFIX) and ".." not in parts.path)):
            return self.local_base() + url
        if parts.scheme in ("http", "https") and parts.hostname and parts.hostname not in ("localhost", "127.0.0.1"):
            return url
        raise ValueError("adresse refusée")

    def load(self, url):
        target = self.resolve(url)
        with self._power:
            with self._lock:
                already_playing = (url == self.current and url and not self.props.get("idle-active", True)
                                   and self.released is None)
                if not already_playing:
                    self.current, self.queued = url, ""
                self.released = None               # un nouveau titre remplace celui qui attendait la reprise
            if not already_playing:                # sinon : enchaîné tout seul par mpv, rien à recharger
                self.mpv.call("loadfile", target, "replace")
                self._apply_volume()
            self.mpv.call("set_property", "pause", False)

    def preload(self, url):
        """Titre suivant ajouté derrière le titre en cours : mpv l'enchaîne sans blanc."""
        if not url:
            return self.drop_preload()
        target = self.resolve(url)
        with self._power:
            with self._lock:
                if url == self.queued:
                    return
                self.queued = url
                if self.released is not None:      # ajouté à la reprise
                    return
            self._safe("playlist-clear")           # retire tout sauf le titre en cours (ancien préchargement, titres joués)
            self.mpv.call("loadfile", target, "append")

    def drop_preload(self):
        with self._power:
            with self._lock:
                self.queued = ""
            self._safe("playlist-clear")

    def pause(self, paused):
        with self._power:
            if paused:
                if self.released is None:
                    self.mpv.call("set_property", "pause", True)
                return
            self._wake()
            self.mpv.call("set_property", "pause", False)

    def seek(self, seconds):
        with self._power:
            self._wake()
            self.mpv.call("seek", float(seconds), "absolute")

    def volume(self, level):
        level = max(0, min(100, float(level)))
        with self._power:
            self._volume = level
            if self.released is None:
                self.mpv.call("set_property", "volume", level)

    def stop(self):
        with self._power:
            with self._lock:
                self.current = self.queued = ""
                self.released = None
            self._safe("stop")

    def _safe(self, *args):
        """Commande sans importance : ne démarre pas mpv (rien à arrêter s'il ne tourne pas)."""
        if not self.mpv.alive():
            return
        try:
            self.mpv.call(*args)
        except MpvError:
            pass

    def _apply_volume(self):
        if self._volume is not None:
            self.mpv.call("set_property", "volume", self._volume)

    # ---------- sortie audio libérée après une pause ----------
    # Tant que mpv garde un flux ouvert vers le DAC USB, l'ampli croit qu'on écoute et ne se met jamais en veille
    # (en pause le flux est « corked » mais reste ouvert ; mpv ne rend pas la carte tant qu'il tourne).
    # Après une pause (ou une file finie) assez longue, on arrête donc mpv : la carte est rendue pour de bon.
    # À la reprise, mpv redémarre, recharge le titre en pause, se replace à la même seconde, puis joue.

    def release_if_idle(self):
        """À appeler régulièrement. Vrai si mpv vient d'être arrêté."""
        with self._power:
            if not self.mpv.alive():
                self._silent_since = None
                return False
            with self._lock:
                props = dict(self.props)
                idle = bool(props.get("idle-active", True))
                if not (idle or props.get("pause")):
                    self._silent_since = None
                    return False
                now = self.clock()
                if self._silent_since is None:
                    self._silent_since = now
                if now - self._silent_since < self.release_after:
                    return False
            self.mpv.stop()
            with self._lock:
                loaded = bool(self.current) and not idle
                self.released = {"url": self.current if loaded else "", "pos": props.get("time-pos") or 0,
                                 "live": not props.get("duration")}
                self.props = {"pause": True, "idle-active": not loaded, "time-pos": props.get("time-pos"),
                              "duration": props.get("duration")}
                self._silent_since = None
            return True

    def _wake(self):
        """Redémarre mpv s'il avait été arrêté, et remet le titre en pause à la position gardée."""
        if self.released is None:
            return
        saved = self.released
        if saved["url"]:
            self.mpv.call("set_property", "pause", True)    # le titre ne doit pas démarrer avant d'être replacé
            self._apply_volume()
            self.mpv.call("loadfile", self.resolve(saved["url"]), "replace")
            if not saved["live"]:
                self._wait_loaded()
                if saved["pos"]:
                    self.mpv.call("seek", float(saved["pos"]), "absolute")
            if self.queued:
                self.mpv.call("loadfile", self.resolve(self.queued), "append")
        else:
            self.mpv.ensure()
            self._apply_volume()
        with self._lock:
            self.released = None

    def _wait_loaded(self):
        deadline = time.time() + WAKE_TIMEOUT
        while time.time() < deadline:
            with self._lock:
                if self.props.get("duration"):
                    return
            time.sleep(0.05)

    def watch_forever(self, every=WATCH_EVERY):
        while True:
            try:
                self.release_if_idle()
            except (MpvError, OSError):
                pass
            time.sleep(every)
