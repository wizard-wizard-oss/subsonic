"""Réglages : où chercher une valeur, et dans quel ordre.

1. app_settings (base SQLite) : ce que l'on change depuis l'application (sources activées, clé saisie à l'écran…) ;
2. variables d'environnement du processus (préfixe PI_MEDIA_) ;
3. fichier .env : réglages d'installation et secrets ;
4. valeur par défaut.
"""
import json
import threading

# Réglages d'installation lus dans le .env, avec leur type (les valeurs du .env sont du texte)
ENV_TYPES = {
    "bind": str, "subsonic_url": str, "subsonic_user": str, "subsonic_pass": str,
    "podcastindex_key": str, "podcastindex_secret": str, "ext_jamendo_id": str, "ext_youtube_key": str,
    "ext_youtube_region": str, "phone_port": int, "phone_remote": bool, "podcast_home": list, "language": str,
    # menu tactile (launcher.py)
    "device_name": str, "weather_city": str, "weather_latitude": float, "weather_longitude": float,
    "screensaver_seconds": int, "web_url": str, "theme": str,
}
TRUE_WORDS = ("1", "true", "yes", "oui", "on")


def convert(text, kind):
    if kind is int:
        return int(text)
    if kind is float:
        return float(text)
    if kind is bool:
        return str(text).strip().lower() in TRUE_WORDS
    if kind is list:
        return [part.strip() for part in str(text).split(",") if part.strip()]
    return text


class AppSettingsStore:
    """Table app_settings, gardée en mémoire (un seul processus écrit : le serveur)."""

    def __init__(self, db):
        self.db = db
        self._lock = threading.Lock()
        self._values = {row["key"]: json.loads(row["value"]) for row in db.query("SELECT key, value FROM app_settings")}

    def get(self, key, default=None):
        with self._lock:
            return self._values.get(key, default)

    def has(self, key):
        with self._lock:
            return key in self._values

    def set_many(self, changes):
        with self._lock, self.db.transaction() as conn:
            for key, value in changes.items():
                conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                             "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, json.dumps(value)))
                self._values[key] = value


class Settings:
    """Même interface que l'ancien config.json : get(), update() et quelques raccourcis typés."""

    def __init__(self, store, env_file, environ):
        self.store = store
        self.env_file = env_file
        self.environ = environ

    def get(self, key, default=None):
        if self.store.has(key):
            return self.store.get(key)
        env_name = key.upper()
        raw = self.environ.get("PI_MEDIA_" + env_name)       # seulement avec le préfixe : LANGUAGE, MODE… existent déjà
        if raw is None:
            raw = self.env_file.values().get(env_name)
        if raw is None:
            return default
        try:
            return convert(raw, ENV_TYPES.get(key, str))
        except ValueError:
            return default

    def update(self, **changes):
        """Réglages changés depuis l'application : enregistrés en base."""
        self.store.set_many(changes)

    @property
    def subsonic_url(self):
        return (self.get("subsonic_url") or "").rstrip("/")

    @property
    def bind_address(self):
        return self.get("bind", "127.0.0.1")
