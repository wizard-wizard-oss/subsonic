"""Envoi de fichiers audio : déposés dans le dossier « Incoming » de la musique de Subsonic, puis Subsonic est invité à
scanner. L'API Subsonic n'a pas d'envoi de fichiers : le site écrit donc directement dans le dossier de musique (MUSIC_DIR
dans le .env), monté en écriture dans le conteneur. Un zip est décompressé, puis chaque album trouvé dedans prend
aussitôt sa place dans la bibliothèque (<racine>/Artiste/Album, voir layout.py), même entouré de dossiers en trop ; ce qui
ne peut pas être placé (artiste inconnu, nomenclature non respectée, album déjà présent) reste dans Incoming, tel qu'il
était organisé, pour être rangé à la main. Seuls les fichiers audio et les images (pochettes) d'un zip sont gardés."""
import hashlib
import os
import re
import shutil
import time
import threading
import uuid
import zipfile

from .layout import EXTENSIONS, extension_of, find_albums
from .subsonic import Credentials, SubsonicError, SubsonicUnreachable

IMAGES = ("jpg", "jpeg", "png")                  # pochettes gardées à côté des titres d'un zip
ZIP = "zip"
MAX_FILE_BYTES = 300 * 1024 * 1024
MAX_ZIP_BYTES = 2000 * 1024 * 1024
MAX_UNZIPPED_BYTES = 4000 * 1024 * 1024          # garde-fou contre un zip qui gonfle démesurément
HISTORY_PAGE_SIZE = 50
CHUNK = 65536
NOT_AUTHORIZED = 50
BAD_CREDENTIALS = 40
UNSAFE = re.compile(r'[\x00-\x1f\x7f<>:"|?*]')


class UploadError(ValueError):
    pass


def safe_name(text, fallback):
    """Garde l'orthographe, les accents et la ponctuation ; retire chemins, contrôles et caractères interdits."""
    name = UNSAFE.sub("_", os.path.basename((text or "").replace("\\", "/"))).strip(" .")
    return name[:150] or fallback


def zip_name(member):
    """Certains ZIP contiennent de l'UTF-8 sans le déclarer : zipfile les a alors lus en CP437.
    Rétablit l'UTF-8 s'il est valide, sinon conserve le nom CP437 d'origine."""
    if not member.flag_bits & 0x800:
        try:
            return member.filename.encode("cp437").decode("utf-8")
        except UnicodeError:
            pass
    return member.filename


def incoming_dir(music_dir, incoming_name):
    """Incoming dans la racine de la musique (vide si la racine n'est pas réglée : envoi désactivé)."""
    return os.path.join(music_dir, safe_name(incoming_name, "Incoming")) if music_dir else ""


class Uploads:
    def __init__(self, subsonic, users, library, history):
        self._placement_lock = threading.Lock()
        self.history = history
        self.subsonic = subsonic
        self.users = users
        self.library = library
        self.directory = library.incoming

    @property
    def enabled(self):
        return bool(self.directory)

    def status(self, user):
        """Utilisable ? Sinon pourquoi (racine de la musique absente, ou site sans droit d'écriture). Incoming est créé
        s'il manque dans une racine existante."""
        folder = os.path.basename(self.directory.rstrip("/"))
        if not self.enabled:
            return {"enabled": False, "reason": "off", "folder": ""}
        if not os.path.isdir(os.path.dirname(self.directory.rstrip("/"))):
            return {"enabled": False, "reason": "missing", "folder": folder}
        try:
            self._make_dir(self.directory)
        except OSError:
            return {"enabled": False, "reason": "not_writable", "folder": folder}
        if not os.access(self.directory, os.W_OK | os.X_OK):
            return {"enabled": False, "reason": "not_writable", "folder": folder}
        return {"enabled": True, "reason": "", "folder": folder, "maxBytes": MAX_FILE_BYTES, "maxZipBytes": MAX_ZIP_BYTES}

    @property
    def library_key(self):
        return hashlib.sha256(os.path.realpath(self.library.music_dir).encode("utf-8")).hexdigest()

    def history_page(self, before=None):
        if before is not None and not 0 < before < 2 ** 63:
            raise UploadError("upload.bad_cursor")
        entries = self.history.page(before, HISTORY_PAGE_SIZE + 1)
        return {"entries": [entry.to_api() for entry in entries[:HISTORY_PAGE_SIZE]],
                "before": entries[HISTORY_PAGE_SIZE - 1].id if len(entries) > HISTORY_PAGE_SIZE else None}

    def save(self, user, stream, length, filename):
        """Copie le corps de la requête (length octets) dans Incoming ; un zip y est décompressé et ses albums rangés.
        Renvoie {"files": titres et images gardés, "skipped": fichiers ignorés du zip, "placed": albums rangés dans la
        bibliothèque (« Artiste/Album »), "waiting": ce qui reste dans Incoming, à ranger à la main}."""
        reason = self.status(user)["reason"]
        if reason:
            raise UploadError("upload." + reason)
        name = safe_name(filename, "")
        extension = extension_of(name)
        if extension not in EXTENSIONS + (ZIP,):
            raise UploadError("upload.bad_type")
        if not 0 < length <= (MAX_ZIP_BYTES if extension == ZIP else MAX_FILE_BYTES):
            raise UploadError("upload.bad_size")
        if extension == ZIP:
            saved = self._save_zip(name, stream, length)
        else:
            part = self._part(self.directory, name)
            self._receive(stream, length, part)
            try:
                with self._placement_lock:
                    path = self._free_path(self.directory, name)  # jamais d'écrasement entre deux envois simultanés
                    self._publish(part, path)
            finally:
                self._remove(part)
            saved = {"files": 1, "skipped": 0, "placed": [], "waiting": [os.path.basename(path)]}
        self.history.add(user, name, length, saved, int(time.time()), self.library_key)
        return saved

    def _save_zip(self, name, stream, length):
        """Le zip arrive dans un fichier caché et est décompressé dans un dossier caché. Chaque album trouvé y est rangé
        d'un coup dans la bibliothèque (Subsonic n'en voit jamais une moitié) ; le reste rejoint Incoming. Des titres à la
        racine du zip forment un album au nom du zip (sans artiste connu : il attend dans Incoming). Le zip est effacé."""
        base = name[:-len(ZIP) - 1].strip(" .") or "album"
        archive = self._part(self.directory, name)
        unpacked = self._part(self.directory, base + ".unzip")
        self._receive(stream, length, archive)
        try:
            kept, skipped = self._unzip(archive, unpacked)
            if not kept:
                raise UploadError("upload.empty_zip")
            self._gather_loose_files(unpacked, base)
            with self._placement_lock:
                placed = self._place_albums(unpacked)
                self._remove_empty_dirs(unpacked)
                waiting = self._merge(unpacked, self.directory)
        except OSError:
            raise UploadError("upload.write_failed")
        finally:
            shutil.rmtree(unpacked, ignore_errors=True)
            self._remove(archive)
        return {"files": kept, "skipped": skipped, "placed": placed, "waiting": waiting}

    def _gather_loose_files(self, unpacked, base):
        """Fichiers à la racine du zip → un dossier au nom du zip."""
        loose = [entry for entry in os.listdir(unpacked) if os.path.isfile(os.path.join(unpacked, entry))]
        if loose:
            folder = self._free_path(unpacked, base, directory=True)
            self._make_dir(folder)
            for entry in loose:
                os.replace(os.path.join(unpacked, entry), os.path.join(folder, entry))

    def _place_albums(self, unpacked):
        """Chaque album du zip : le dossier qui le contient est l'artiste. Des dossiers en trop au-dessus de l'artiste
        (« Mes envois/Converge/Jane Doe ») sont ignorés s'ils ne contiennent rien d'autre et ne portent pas le nom d'un
        artiste de la bibliothèque : sinon « Converge/Live/Face A » pourrait passer pour l'artiste « Live ». Dans le doute,
        l'album attend dans Incoming."""
        placed = []
        for album in find_albums(unpacked):
            parts = os.path.relpath(album, unpacked).split(os.sep)
            if len(parts) < 2 or not os.path.isdir(album):
                continue                                     # artiste inconnu, ou déjà parti avec un album englobant
            if not self._only_wrappers(unpacked, parts[:-2]):
                continue
            where = self.library.place(album, parts[-2], parts[-1])
            if where:
                placed.append(where)
        return placed

    def _only_wrappers(self, unpacked, above):
        """Les dossiers au-dessus de l'artiste ne contiennent chacun que le suivant, et aucun n'est un artiste connu."""
        folder = unpacked
        for name in above:
            folder = os.path.join(folder, name)
            if len(os.listdir(folder)) != 1 or self.library.is_artist(name):
                return False
        return True

    @staticmethod
    def _remove_empty_dirs(root):
        """Dossiers vidés par le rangement (« Mes envois/Converge » après le départ de l'album)."""
        for folder, dirs, files in os.walk(root, topdown=False):
            if folder != root and not os.listdir(folder):
                os.rmdir(folder)

    def _merge(self, source, destination):
        """Déplace le contenu de source dans destination : un dossier absent arrive d'un coup, un dossier déjà là (le même
        artiste) reçoit le contenu ; un fichier déjà là n'est jamais écrasé (« titre (2).flac »). Renvoie les noms déplacés."""
        moved = []
        for entry in sorted(os.listdir(source)):
            origin, target = os.path.join(source, entry), os.path.join(destination, entry)
            if os.path.isdir(origin) and os.path.isdir(target):
                self._merge(origin, target)
            else:
                if os.path.exists(target):
                    target = self._free_path(destination, entry, directory=os.path.isdir(origin))
                os.replace(origin, target)
            moved.append(os.path.basename(target))
        return moved

    def _unzip(self, archive, destination):
        """Décompresse les fichiers audio et les images, sous-dossiers compris (noms nettoyés : rien ne sort du dossier).
        Renvoie (gardés, ignorés)."""
        try:
            with zipfile.ZipFile(archive) as source:
                members = [m for m in source.infolist() if not m.is_dir()]
                wanted = [m for m in members if self._wanted(m)]
                if sum(m.file_size for m in wanted) > MAX_UNZIPPED_BYTES or \
                        any(m.file_size > MAX_FILE_BYTES for m in wanted):
                    raise UploadError("upload.bad_size")
                self._make_dir(destination)
                for member in wanted:
                    self._extract(source, member, destination)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, RuntimeError, EOFError):
            raise UploadError("upload.bad_zip")                  # zip abîmé, chiffré ou compression inconnue
        return len(wanted), len(members) - len(wanted)

    @staticmethod
    def _wanted(member):
        parts = zip_name(member).replace("\\", "/").split("/")
        if parts[0] == "__MACOSX" or parts[-1].startswith("."):          # restes du Finder de macOS
            return False
        return extension_of(parts[-1]) in EXTENSIONS + IMAGES

    def _extract(self, source, member, destination):
        parts = [safe_name(p, "_") for p in zip_name(member).replace("\\", "/").split("/") if p not in ("", ".", "..")]
        folder = destination
        for part in parts[:-1]:
            folder = os.path.join(folder, part)
            self._make_dir(folder)
        path = self._free_path(folder, parts[-1])
        with source.open(member) as data, open(path, "wb") as out:
            shutil.copyfileobj(data, out, CHUNK)
        os.chmod(path, 0o664)

    @staticmethod
    def _receive(stream, length, path):
        """Écrit exactement length octets du corps de la requête ; rien ne reste en cas d'échec."""
        remaining = length
        try:
            with open(path, "wb") as out:
                while remaining > 0:
                    chunk = stream.read(min(CHUNK, remaining))
                    if not chunk:
                        raise UploadError("upload.interrupted")
                    out.write(chunk)
                    remaining -= len(chunk)
        except (OSError, UploadError) as error:
            Uploads._remove(path)
            raise error if isinstance(error, UploadError) else UploadError("upload.write_failed")

    @staticmethod
    def _publish(part, path):
        """Donne au fichier ou au dossier caché son vrai nom (lisible par tous, modifiable par le groupe)."""
        try:
            os.chmod(part, 0o775 if os.path.isdir(part) else 0o664)
            os.replace(part, path)
        except OSError:
            Uploads._remove(part)
            raise UploadError("upload.write_failed")

    @staticmethod
    def _make_dir(path):
        if not os.path.isdir(path):
            os.mkdir(path)
            os.chmod(path, 0o775)

    @staticmethod
    def _part(folder, name):
        return os.path.join(folder, "." + name + "." + uuid.uuid4().hex + ".part")                       # caché : Subsonic n'y touche pas

    @staticmethod
    def _remove(path):
        if os.path.isfile(path):
            os.unlink(path)

    @staticmethod
    def _free_path(folder, name, directory=False):
        """Ne jamais écraser : « titre.flac », puis « titre (2).flac »… (dossiers : « Album », « Album (2) »)."""
        base, dot, extension = name.rpartition(".")
        if directory or not dot:
            base, dot, extension = name, "", ""
        for number in range(1, 100):
            candidate = name if number == 1 else "%s (%d)%s" % (base, number, dot + extension)
            if not os.path.exists(os.path.join(folder, candidate)):
                return os.path.join(folder, candidate)
        raise UploadError("upload.write_failed")

    def scan(self, user):
        """Demande à Subsonic de scanner (startScan), réservé aux administrateurs : on essaie avec le compte, puis avec les
        administrateurs connus du site (ceux qui se sont déjà connectés), dont le jeton gardé peut avoir expiré.
        True si un scan est lancé."""
        admins = [u for u in self.users.by_priority() if u.is_admin and u.id != user.id][:3]
        return self._scan_with([user] + admins)

    def scan_as_admin(self):
        """startScan sans personne connectée (rangement automatique d'Incoming) : avec un administrateur connu du site."""
        return self._scan_with([u for u in self.users.by_priority() if u.is_admin][:3])

    def _scan_with(self, accounts):
        for who in accounts:
            try:
                self.subsonic.call(Credentials.of(who), "startScan")
                return True
            except SubsonicError as error:
                if error.code not in (NOT_AUTHORIZED, BAD_CREDENTIALS):
                    return False
            except SubsonicUnreachable:
                return False
        return False
