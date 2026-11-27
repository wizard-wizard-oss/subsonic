"""Changer la pochette d'un album : recherche sur Last.fm (clé LASTFM_API_KEY), puis l'image choisie (ou une adresse
collée à la main) est téléchargée, vérifiée et écrite en cover.jpg (ou cover.png) dans le dossier de l'album, comme dans
Subsonic V1. Une pochette « cover.* » déjà là est gardée à côté, en « .bak » ; Subsonic n'est pas invité à scanner.
Le site téléchargeant une adresse donnée par une personne, il refuse tout ce qui n'est pas http(s) public (adresses
privées, boucle locale, y compris par redirection), les fichiers trop gros et tout ce qui n'est pas un jpg ou un png."""
import os

from ..shared.providers.http import NotPublic, TooLarge
from ..shared.providers.metadata import ProviderUnavailable

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TERM = 200
SIGNATURES = ((b"\xff\xd8\xff", "jpg"), (b"\x89PNG\r\n\x1a\n", "png"))
COVER_NAMES = ("cover.jpg", "cover.jpeg", "cover.png")


class CoverError(ValueError):
    pass


def image_extension(data):
    """« jpg » ou « png » d'après le début du fichier, sinon None."""
    return next((extension for signature, extension in SIGNATURES if data.startswith(signature)), None)


class Covers:
    def __init__(self, folders, music_dir, lastfm, http):
        self.folders = folders
        self.music_dir = music_dir
        self.lastfm = lastfm
        self.http = http

    def status(self):
        """Last.fm réglé ? La racine de la musique est-elle réglée ?"""
        return {"search": self.lastfm.enabled, "writable": bool(self.music_dir) and os.path.isdir(self.music_dir)}

    def search(self, artist, album):
        artist, album = self._term(artist), self._term(album)
        if not self.lastfm.enabled:
            raise CoverError("cover.no_lastfm")
        try:
            return [candidate.to_api() for candidate in self.lastfm.album_images(artist, album)]
        except ProviderUnavailable:
            raise CoverError("cover.search_failed") from None

    def save(self, user, album_id, url):
        """Écrit l'image de url comme pochette de l'album : renvoie son nom de fichier. Rien n'est écrit si l'image est refusée."""
        folder = self._album_directory(user, album_id)
        data = self.download(url)
        name = "cover." + image_extension(data)
        try:
            self._write(folder, name, data)
        except OSError:
            raise CoverError("cover.write_failed")
        return {"file": name}

    def download(self, url):
        """Octets de l'image : adresse publique (redirections comprises), jpg ou png de 10 Mo au plus."""
        try:
            data = self.http.get_bytes(url, accept="image/jpeg,image/png", public_only=True)
        except NotPublic:
            raise CoverError("cover.bad_url") from None
        except TooLarge:
            raise CoverError("cover.too_big") from None
        except (OSError, ValueError):
            raise CoverError("cover.download_failed") from None
        if len(data) > MAX_IMAGE_BYTES:
            raise CoverError("cover.too_big")
        if not image_extension(data):
            raise CoverError("cover.not_image")
        return data

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
