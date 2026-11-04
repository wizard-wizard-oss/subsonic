"""Couche HTTP : requête, réponse, routage et gestionnaire du serveur. Aucune logique métier ici."""
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .constants import LOOPBACK


# ---------- requête ----------
class BodyReader:
    """Corps d'une requête, lu au plus jusqu'à sa longueur annoncée : ce qui reste à lire est connu.
    Une requête refusée avant d'avoir lu son corps (401, 403…) le laisse sur la connexion ; sans le vider, la requête
    suivante sur la même connexion (gardée ouverte, HTTP/1.1) serait lue de travers (« Bad request syntax »)."""

    DRAIN_LIMIT = 1024 * 1024        # au-delà, on ferme la connexion plutôt que de lire pour rien

    def __init__(self, raw, length):
        self.raw, self.left = raw, max(0, length)

    def read(self, size=-1):
        size = self.left if size is None or size < 0 else min(size, self.left)
        data = self.raw.read(size) if size else b""
        self.left -= len(data)
        if size and not data:
            self.left = 0                # connexion coupée : plus rien à attendre
        return data

    def drain(self):
        """Vide ce qui reste ; False si c'est trop (la connexion doit alors être fermée)."""
        if self.left > self.DRAIN_LIMIT:
            return False
        while self.left:
            self.read(65536)
        return True


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


class FileReply(Reply):
    """Fichier local envoyé par morceaux, avec prise en charge de « Range » (avance rapide dans un titre)."""

    CHUNK = 65536

    def __init__(self, path, ctype, range_header=""):
        super().__init__(200, b"", ctype)
        self.path = path
        self.size = os.path.getsize(path)
        self.start, self.end = 0, self.size - 1
        wanted = parse_range(range_header, self.size)
        if wanted:
            self.status, (self.start, self.end) = 206, wanted

    def write_to(self, handler):
        handler.send_response(self.status)
        handler.send_header("Content-Type", self.ctype)
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Content-Length", str(self.end - self.start + 1))
        if self.status == 206:
            handler.send_header("Content-Range", "bytes %d-%d/%d" % (self.start, self.end, self.size))
        handler.end_headers()
        remaining = self.end - self.start + 1
        try:
            with open(self.path, "rb") as f:
                f.seek(self.start)
                while remaining > 0:
                    chunk = f.read(min(self.CHUNK, remaining))
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def parse_range(header, size):
    """« bytes=100-199 » ou « bytes=100- » -> (début, fin) dans les limites du fichier ; None sinon."""
    if not header or not header.startswith("bytes=") or "," in header or size <= 0:
        return None
    first, _, last = header[6:].strip().partition("-")
    try:
        if first == "":
            start, end = max(0, size - int(last)), size - 1          # « bytes=-500 » : les 500 derniers octets
        else:
            start, end = int(first), (int(last) if last else size - 1)
    except ValueError:
        return None
    end = min(end, size - 1)
    return (start, end) if 0 <= start <= end else None


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
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            body = BodyReader(self.rfile, length)
            request = Request(method, self.path, self.headers, self.client_address[0], body, self.connection)
            reply = app.handle(request)
            if not body.drain():                          # corps non lu et trop gros : on ne réutilise pas la connexion
                reply.close_connection = True
                reply.headers["Connection"] = "close"
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
