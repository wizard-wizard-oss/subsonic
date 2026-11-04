"""Fichiers de l'interface web (page, CSS, JavaScript) : version, compression, en-têtes de cache."""
import gzip
import hashlib
import os
import threading
import time
import urllib.parse

MIME = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon",
        ".woff2": "font/woff2", ".json": "application/json", ".webmanifest": "application/manifest+json"}
GZIP_EXT = frozenset((".css", ".js", ".svg", ".json", ".webmanifest"))
STATIC_PREFIX = "/static/"


class WebFile:
    """Réponse prête à envoyer : statut, corps, type, en-têtes."""

    def __init__(self, status, body=b"", ctype="text/plain", headers=None):
        self.status = status
        self.body = body
        self.ctype = ctype
        self.headers = headers or {}


def etag_matches(header, etag):
    """L'en-tête If-None-Match désigne-t-il cette version ?"""
    header = header or ""
    return etag in [part.strip() for part in header.split(",")] or header.strip() == "*"


class AssetVersion:
    """Empreinte des fichiers de l'interface. Elle change à chaque mise à jour : le navigateur recharge alors
    les fichiers (adresse ?v=…), alors qu'entre deux mises à jour ils restent en cache un an."""

    REFRESH_SECONDS = 5

    def __init__(self, web_dir):
        self.web_dir = web_dir
        self._checked = 0
        self._value = "0"
        self._lock = threading.Lock()

    def current(self):
        with self._lock:
            if time.time() - self._checked >= self.REFRESH_SECONDS:
                self._value = self._compute()
                self._checked = time.time()
            return self._value

    def _compute(self):
        digest = hashlib.sha1()
        for root, dirs, files in sorted(os.walk(self.web_dir)):
            dirs.sort()
            for name in sorted(files):
                self._add_file(digest, os.path.join(root, name))
        return digest.hexdigest()[:10]

    def _add_file(self, digest, path):
        try:
            stat = os.stat(path)
        except OSError:
            return
        digest.update(("%s|%d|%d;" % (os.path.relpath(path, self.web_dir), stat.st_size, stat.st_mtime_ns)).encode())


class GzipCache:
    """Version compressée de chaque fichier, recalculée seulement s'il change."""

    def __init__(self):
        self._items = {}

    def compressed(self, path, signature, body):
        cached = self._items.get(path)
        if not cached or cached[0] != signature:
            cached = (signature, gzip.compress(body, 6))
            self._items[path] = cached
        return cached[1]


class WebFiles:
    def __init__(self, paths):
        self.paths = paths
        self.version = AssetVersion(paths.web_dir)
        self.gzip = GzipCache()

    # --- page d'accueil ---
    def index(self, if_none_match):
        return self.page("index.html", if_none_match)

    def page(self, name, if_none_match):
        """Une page HTML du dossier web/, avec l'empreinte des fichiers dans les adresses (?v=…)."""
        try:
            with open(os.path.join(self.paths.web_dir, name), "rb") as f:
                page = f.read().replace(b"{{V}}", self.version.current().encode())
        except OSError:
            return WebFile(500, ("web/%s introuvable" % name).encode())
        etag = '"%s"' % hashlib.sha1(page).hexdigest()[:16]
        headers = {"Cache-Control": "no-cache", "ETag": etag}
        if etag_matches(if_none_match, etag):
            return WebFile(304, headers=headers)
        return WebFile(200, page, "text/html; charset=utf-8", headers)

    # --- fichiers statiques ---
    def static(self, url_path, query, if_none_match, accept_encoding):
        full = self._safe_path(url_path)
        if full is None:
            return WebFile(404, b"404")
        ext = os.path.splitext(full)[1].lower()
        stat = os.stat(full)
        signature = "%d-%d" % (stat.st_mtime_ns, stat.st_size)
        use_gzip = ext in GZIP_EXT and "gzip" in (accept_encoding or "")
        etag = '"%s%s"' % (signature, "-gz" if use_gzip else "")
        headers = self._static_headers(etag, "v" in dict(urllib.parse.parse_qsl(query)))
        if etag_matches(if_none_match, etag):
            return WebFile(304, headers=headers)
        with open(full, "rb") as f:
            body = f.read()
        if use_gzip:
            body = self.gzip.compressed(full, signature, body)
            headers["Content-Encoding"] = "gzip"
        return WebFile(200, body, MIME.get(ext, "application/octet-stream"), headers)

    def _safe_path(self, url_path):
        """Chemin réel du fichier demandé, s'il est bien dans le dossier static (sinon None)."""
        relative = urllib.parse.unquote(url_path[len(STATIC_PREFIX):])
        root = os.path.realpath(self.paths.static_dir)
        full = os.path.realpath(os.path.join(root, relative))
        return full if full.startswith(root + os.sep) and os.path.isfile(full) else None

    @staticmethod
    def _static_headers(etag, versioned):
        # fichier versionné (?v=…) : mis en cache un an ; sinon revalidation courte
        cache = "public, max-age=31536000, immutable" if versioned else "public, max-age=300"
        return {"ETag": etag, "Vary": "Accept-Encoding", "Cache-Control": cache, "X-Content-Type-Options": "nosniff"}
