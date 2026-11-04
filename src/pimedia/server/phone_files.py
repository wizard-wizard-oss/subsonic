"""Fichiers audio envoyés depuis un téléphone : rangés sur le Pi le temps d'être écoutés, puis effacés.

Chaque fichier reçoit un identifiant aléatoire ; la page (ou mpv) le lit par /phone-files/<identifiant>.<ext>."""
import os
import re
import secrets
import threading
import time

URL_PREFIX = "/phone-files/"
AUDIO_TYPES = {"mp3": "audio/mpeg", "flac": "audio/flac", "m4a": "audio/mp4", "aac": "audio/aac", "ogg": "audio/ogg",
               "oga": "audio/ogg", "opus": "audio/ogg", "wav": "audio/wav", "aiff": "audio/aiff", "aif": "audio/aiff"}
MAX_FILE_BYTES = 300 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_AGE_SECONDS = 7 * 86400
CHUNK = 65536
STORED_NAME = re.compile(r"^[0-9a-f]{16}\.[a-z0-9]{2,4}$")


def title_from_filename(filename):
    """« 01 - Mon_titre.flac » -> « Mon titre »."""
    base = os.path.basename(filename or "")
    base = base.rsplit(".", 1)[0] if "." in base else base
    base = re.sub(r"[_]+", " ", base)
    base = re.sub(r"^\s*\d{1,3}\s*[-.]\s*", "", base)          # numéro de piste en tête
    return " ".join(base.split())[:200] or "Titre envoyé"


class UploadError(Exception):
    pass


class PhoneFiles:
    def __init__(self, directory):
        self.directory = directory
        self._lock = threading.Lock()

    def save(self, stream, length, filename):
        """Copie le corps de la requête (length octets) ; renvoie (nom stocké, titre). UploadError si refusé."""
        extension = os.path.basename(filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
        if extension not in AUDIO_TYPES:
            raise UploadError("Format non accepté (mp3, flac, m4a, ogg, opus, wav, aiff)")
        if not 0 < length <= MAX_FILE_BYTES:
            raise UploadError("Fichier vide ou trop gros (300 Mo au plus)")
        os.makedirs(self.directory, exist_ok=True)
        name = "%s.%s" % (secrets.token_hex(8), extension)
        path = os.path.join(self.directory, name)
        remaining = length
        try:
            with open(path + ".part", "wb") as out:
                while remaining > 0:
                    chunk = stream.read(min(CHUNK, remaining))
                    if not chunk:
                        raise UploadError("Envoi interrompu")
                    out.write(chunk)
                    remaining -= len(chunk)
            os.replace(path + ".part", path)
        except (OSError, UploadError):
            if os.path.exists(path + ".part"):
                os.unlink(path + ".part")
            raise
        self.purge()
        return name, title_from_filename(filename)

    def path_of(self, name):
        """Chemin d'un fichier stocké (None si le nom est invalide ou inconnu : rien d'autre n'est lisible)."""
        if not STORED_NAME.match(name or ""):
            return None
        path = os.path.join(self.directory, name)
        return path if os.path.isfile(path) else None

    @staticmethod
    def content_type(name):
        return AUDIO_TYPES.get(name.rsplit(".", 1)[-1], "application/octet-stream")

    def purge(self, now=None):
        """Efface les fichiers de plus de 7 jours, puis les plus anciens au-delà de 2 Go."""
        now = now or time.time()
        with self._lock:
            try:
                entries = [(e.stat().st_mtime, e.stat().st_size, e.path) for e in os.scandir(self.directory) if e.is_file()]
            except OSError:
                return
            entries.sort()
            total = sum(size for _, size, _ in entries)
            for mtime, size, path in entries:
                if now - mtime > MAX_AGE_SECONDS or total > MAX_TOTAL_BYTES:
                    try:
                        os.unlink(path)
                        total -= size
                    except OSError:
                        pass
