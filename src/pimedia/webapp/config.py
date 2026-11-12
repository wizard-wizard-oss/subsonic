"""Réglages de l'édition PC : variables PI_MEDIA_WEB_* du processus, sinon .env du dossier de données, sinon défaut."""
import os
from dataclasses import dataclass

from ..envfile import EnvFile
from ..settings import convert

ENV_PREFIX = "PI_MEDIA_WEB_"


def default_data_dir(environ):
    return environ.get("PI_MEDIA_WEB_DATA") or os.path.expanduser("~/.local/share/pimedia-web")


@dataclass
class WebConfig:
    subsonic_url: str = ""
    subsonic_public_url: str = ""     # adresse de Subsonic pour les personnes (liens) ; vide : subsonic_url
    subsonic_statistics_file: str = ""  # subsonic.properties en lecture seule ; vide : compteurs masqués
    bind: str = "127.0.0.1"           # derrière un proxy HTTPS (nginx, Caddy) ; 0.0.0.0 pour le réseau local
    port: int = 8200
    secure_cookie: bool = False       # true dès que le site est servi en HTTPS
    trust_proxy: bool = False         # true derrière Apache/nginx : adresse de la personne lue dans X-Forwarded-For
    session_days: int = 30
    language: str = "fr"
    ext_jamendo_id: str = ""          # musique d'ailleurs : une clé par source pour tout le site (EXT_… dans le .env)
    ext_youtube_key: str = ""
    ext_youtube_region: str = "FR"
    lastfm_api_key: str = ""          # clé d'API Last.fm (gratuite, last.fm/api) : recherche de pochettes ; vide : désactivée
    discogs_api_key: str = ""         # jeton personnel Discogs, seulement côté serveur
    music_dir: str = ""               # racine de la musique de Subsonic (vide : envoi de fichiers désactivé)
    incoming_name: str = "Incoming"   # dossier, dans cette racine, où le site range les fichiers envoyés
    shortcut_folders: str = "Compilations"   # dossiers de la racine épinglés en haut de la barre (séparés par des virgules)
    incoming_wait_hours: int = 1      # un album corrigé sur place dans Incoming est rangé après ce délai sans changement (0 : jamais)

    @classmethod
    def load(cls, data_dir, environ):
        config = cls()
        values = EnvFile(os.path.join(data_dir, ".env")).values()
        for name in config.__dataclass_fields__:
            raw = environ.get(ENV_PREFIX + name.upper())
            if raw is None:
                raw = values.get("WEB_" + name.upper(), values.get(name.upper()))   # SUBSONIC_URL partagé
            if raw not in (None, ""):
                try:
                    setattr(config, name, convert(raw, type(getattr(config, name))))
                except ValueError:
                    pass
        config.subsonic_url = config.subsonic_url.rstrip("/")
        config.subsonic_public_url = (config.subsonic_public_url or config.subsonic_url).rstrip("/")
        return config
