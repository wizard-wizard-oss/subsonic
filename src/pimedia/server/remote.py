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
import urllib.parse

from .links import LinkError
from .phone_files import UploadError
from .transport import Reply, Router, HttpApp, ThreadedServer, make_request_handler
from ..entities import Track
from ..tracks import PHONE_FILES_PREFIX

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

    def __init__(self, typing, search, queue, files=None, links=None):
        self.typing = typing
        self.search_tracks = search          # fonction : texte -> [Track] (recherche Subsonic)
        self.queue = queue                   # QueueService
        self.files = files                   # PhoneFiles : fichiers envoyés depuis le téléphone
        self.links = links                   # LinkResolver : liens partagés depuis une appli de musique
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

    def upload(self, code, stream, length, filename, mode):
        """Fichier audio envoyé du téléphone : rangé sur le Pi puis ajouté à la file."""
        self.typing.verify(code)
        name, title = self.files.save(stream, length, filename)
        track = Track.from_api({"id": "upload-" + name.split(".")[0], "title": title, "artist": "Envoyé depuis un téléphone",
                                "streamUrl": PHONE_FILES_PREFIX + name, "ext": "upload"})
        self.queue.request_from_phone(track, mode)
        return title

    def link(self, code, url, mode):
        """Lien partagé (YouTube, Deezer, Apple Music, Spotify) : même titre trouvé dans la bibliothèque ou sur YouTube."""
        self.typing.verify(code)
        track, source = self.links.resolve(url)
        self.queue.request_from_phone(track, mode)
        return {"added": track.title, "source": source}


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

    def link(self, request):
        return self._guarded(request, lambda b: self.phone_queue.link(b.get("code"), b.get("url"), b.get("mode", "next")))

    def upload(self, request):
        """Corps brut = le fichier ; code, nom et place dans la file dans les en-têtes (X-Code, X-File-Name, X-Mode)."""
        request.set_timeout(120)
        name = urllib.parse.unquote(request.header("X-File-Name"))
        try:
            title = self.phone_queue.upload(request.header("X-Code"), request.rfile, request.content_length,
                                            name, request.header("X-Mode") or "next")
        except UploadError as error:
            return self._too_much_unread(request, Reply.json({"error": str(error)}, 400))
        except PermissionError:
            return self._too_much_unread(request, Reply.json({"error": "Code périmé : scannez à nouveau le QR code affiché sur le Pi"}, 403))
        except OverflowError:
            return self._too_much_unread(request, Reply.json({"error": "Trop d'essais, réessayez dans une minute"}, 429))
        except ValueError:
            return Reply.json({"error": "requête invalide"}, 400)
        return Reply.json({"ok": True, "added": title})

    @staticmethod
    def _too_much_unread(request, reply):
        """Refusé avant d'avoir lu le fichier : on ferme la connexion plutôt que d'aspirer des centaines de Mo."""
        reply.close_connection = True
        return reply

    @staticmethod
    def _guarded(request, action):
        try:
            result = action(request.json_body(limit=2048))
        except PermissionError:
            return Reply.json({"error": "Code périmé : scannez à nouveau le QR code affiché sur le Pi"}, 403)
        except OverflowError:
            return Reply.json({"error": "Trop d'essais, réessayez dans une minute"}, 429)
        except (LookupError, LinkError) as error:
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
            router.add("POST", "/tel/link", controller.link)
            router.add("POST", "/tel/upload", controller.upload)
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
