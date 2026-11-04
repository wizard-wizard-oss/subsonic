"""Emplacements : le code (remplacé à chaque mise à jour) et les données (gardées d'une version à l'autre).

Après un déploiement par archive :  ~/.local/share/pi-media/releases/<version>/  (code)
                                     ~/.local/share/pi-media/                     (données : .env, pi-media.db)
"""
import os


def resolve_data_dir(code_dir, environ):
    """PI_MEDIA_DATA si défini ; sinon le dossier qui contient « releases/ » ; sinon le dossier du code."""
    if environ.get("PI_MEDIA_DATA"):
        return environ["PI_MEDIA_DATA"]
    parent = os.path.dirname(os.path.abspath(code_dir))
    if os.path.basename(parent) == "releases":
        return os.path.dirname(parent)
    return code_dir


def default_cache_dir(environ):
    return environ.get("PI_MEDIA_CACHE") or os.path.expanduser("~/.cache/pi-media-subsonic")


class Paths:
    def __init__(self, code_dir, data_dir, cache_dir):
        # code
        self.code_dir = code_dir
        self.web_dir = os.path.join(code_dir, "web")
        self.static_dir = os.path.join(self.web_dir, "static")
        self.i18n_dir = os.path.join(code_dir, "i18n")
        # données à garder
        self.data_dir = data_dir
        self.env_file = os.path.join(data_dir, ".env")
        self.db_file = os.path.join(data_dir, "pi-media.db")
        # anciens fichiers (importés une fois dans la base, voir storage/legacy.py)
        self.legacy_config = os.path.join(data_dir, "config.json")
        self.legacy_podcasts = os.path.join(data_dir, "podcasts.json")
        self.legacy_playlists = os.path.join(data_dir, "playlists.json")
        self.legacy_history = os.path.join(data_dir, "recherches.json")
        self.legacy_unplayable = os.path.join(data_dir, "youtube-illisibles.json")
        # cache (peut être vidé sans rien perdre)
        self.cache_dir = cache_dir
        self.json_dir = os.path.join(cache_dir, "json")
        self.cover_dir = os.path.join(cache_dir, "covers")
        self.newest_file = os.path.join(cache_dir, "newest.json")
