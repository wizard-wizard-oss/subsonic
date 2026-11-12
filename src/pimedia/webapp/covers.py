"""Changer la pochette d'un album : recherche sur Last.fm (clé LASTFM_API_KEY), puis l'image choisie (ou une adresse
collée à la main) est téléchargée, vérifiée et écrite en cover.jpg (ou cover.png) dans le dossier de l'album, comme dans
Subsonic V1. Une pochette « cover.* » déjà là est gardée à côté, en « .bak » ; Subsonic n'est pas invité à scanner.
Le site téléchargeant une adresse donnée par une personne, il refuse tout ce qui n'est pas http(s) public (adresses
privées, boucle locale, y compris par redirection), les fichiers trop gros et tout ce qui n'est pas un jpg ou un png."""
import ipaddress
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

from ..shared.external import USER_AGENT, query_url
from ..shared.text import normalize
from .library import text
from .lastfm import LASTFM_BLANK

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_CANDIDATES = 12
MAX_TERM = 200
CHUNK = 65536
LASTFM = "https://ws.audioscrobbler.com/2.0/"
SIZES = ("mega", "extralarge", "large", "medium")           # du plus grand au plus petit
SIGNATURES = ((b"\xff\xd8\xff", "jpg"), (b"\x89PNG\r\n\x1a\n", "png"))
COVER_NAMES = ("cover.jpg", "cover.jpeg", "cover.png")


class CoverError(ValueError):
    pass


def image_extension(data):
    """« jpg » ou « png » d'après le début du fichier, sinon None."""
    return next((extension for signature, extension in SIGNATURES if data.startswith(signature)), None)


def is_public_host(host, resolve=socket.getaddrinfo):
    """Le nom ne désigne que des adresses publiques (ni privée, ni boucle locale, ni lien local, ni réservée)."""
    try:
        addresses = {ipaddress.ip_address(info[4][0]) for info in resolve(host, None)}
    except (OSError, ValueError):
        return False
    return bool(addresses) and all(a.is_global and not a.is_multicast for a in addresses)


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Chaque redirection est vérifiée comme l'adresse de départ."""

    def __init__(self, check):
        self.check = check

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ImageDownloader:
    def __init__(self, resolve=socket.getaddrinfo, timeout=10):
        self.resolve = resolve
        self.timeout = timeout

    def check(self, url):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise CoverError("cover.bad_url")
        if not is_public_host(parts.hostname, self.resolve):
            raise CoverError("cover.bad_url")

    def fetch(self, url):
        """Octets de l'image (jpg ou png de 10 Mo au plus)."""
        self.check(url)
        opener = urllib.request.build_opener(_PublicRedirects(self.check))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/jpeg,image/png"})
        try:
            with opener.open(request, timeout=self.timeout) as response:
                data = response.read(MAX_IMAGE_BYTES + 1)
        except CoverError:
            raise
        except (urllib.error.URLError, OSError, ValueError):
            raise CoverError("cover.download_failed")
        if len(data) > MAX_IMAGE_BYTES:
            raise CoverError("cover.too_big")
        if not image_extension(data):
            raise CoverError("cover.not_image")
        return data


class LastFmAlbums:
    """Pochettes proposées par Last.fm : l'album exact d'abord (album.getInfo), puis les albums de ce nom (album.search),
    ceux du même artiste en tête."""

    def __init__(self, fetcher, api_key):
        self.fetcher = fetcher
        self.api_key = api_key

    @property
    def enabled(self):
        return bool(self.api_key)

    def search(self, artist, album):
        exact = self._call({"method": "album.getinfo", "artist": artist, "album": album}).get("album") or {}
        found = self._call({"method": "album.search", "album": album, "limit": 30}).get("results") or {}
        matches = (found.get("albummatches") or {}).get("album") or []
        matches = [matches] if isinstance(matches, dict) else matches
        matches.sort(key=lambda m: normalize(text(m.get("artist"))) != normalize(artist))     # tri stable
        candidates, seen = [], set()
        for match in [exact] + matches:
            candidate = self._candidate(match)
            if candidate and candidate["url"] not in seen:
                seen.add(candidate["url"])
                candidates.append(candidate)
        return candidates[:MAX_CANDIDATES]

    def _call(self, params):
        url = query_url(LASTFM, dict(params, api_key=self.api_key, format="json"))
        reply = self.fetcher.try_get(url)
        if reply is None:
            raise CoverError("cover.search_failed")
        return reply if isinstance(reply, dict) else {}

    @staticmethod
    def _candidate(match):
        images = {i.get("size"): text(i.get("#text")) for i in match.get("image") or [] if isinstance(i, dict)}
        urls = [images[size] for size in SIZES if images.get(size) and LASTFM_BLANK not in images[size]]
        if not urls:
            return None
        return {"url": urls[0], "thumb": urls[min(1, len(urls) - 1)], "name": text(match.get("name")),
                "artist": text(match.get("artist"))}


class Covers:
    def __init__(self, folders, music_dir, lastfm, downloader):
        self.folders = folders
        self.music_dir = music_dir
        self.lastfm = lastfm
        self.downloader = downloader

    def status(self):
        """Last.fm réglé ? La racine de la musique est-elle réglée ?"""
        return {"search": self.lastfm.enabled, "writable": bool(self.music_dir) and os.path.isdir(self.music_dir)}

    def search(self, artist, album):
        artist, album = self._term(artist), self._term(album)
        if not self.lastfm.enabled:
            raise CoverError("cover.no_lastfm")
        return self.lastfm.search(artist, album)

    def save(self, user, album_id, url):
        """Écrit l'image de url comme pochette de l'album : renvoie son nom de fichier. Rien n'est écrit si l'image est refusée."""
        folder = self._album_directory(user, album_id)
        data = self.downloader.fetch(url)
        name = "cover." + image_extension(data)
        try:
            self._write(folder, name, data)
        except OSError:
            raise CoverError("cover.write_failed")
        return {"file": name}

    @staticmethod
    def _term(value):
        value = (value or "").strip()
        if not value or len(value) > MAX_TERM:
            raise CoverError("cover.bad_term")
        return value

    def _album_directory(self, user, album_id):
        """Le dossier de l'album, forcément dans la racine de la musique, et en écriture."""
        if not self.music_dir or not os.path.isdir(self.music_dir):
            raise CoverError("cover.off")
        relative = self.folders.album_path(user, album_id)
        root = os.path.realpath(self.music_dir)
        folder = os.path.realpath(os.path.join(root, relative)) if relative else ""
        if not relative or os.path.commonpath([root, folder]) != root or folder == root or not os.path.isdir(folder):
            raise CoverError("cover.not_found")
        if not os.access(folder, os.W_OK | os.X_OK):
            raise CoverError("cover.not_writable")
        return folder

    @staticmethod
    def _keep_old_covers(folder):
        """cover.jpg → cover.jpg.bak (la précédente copie de secours est remplacée) : Subsonic ne lit plus que la nouvelle."""
        for name in COVER_NAMES:
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                os.replace(path, path + ".bak")

    @staticmethod
    def _write(folder, name, data):
        part = os.path.join(folder, ".cover.part")
        try:
            with open(part, "wb") as out:
                out.write(data)
            os.chmod(part, 0o664)                    # lisible par Subsonic, modifiable par le groupe
            Covers._keep_old_covers(folder)          # seulement une fois la nouvelle image bien écrite
            os.replace(part, os.path.join(folder, name))
        finally:
            if os.path.exists(part):
                os.remove(part)
