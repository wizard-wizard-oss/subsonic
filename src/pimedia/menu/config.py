"""Réglages du menu : .env du dossier de données (clés anglaises), sinon ancien config.json (clés françaises)."""
import json
import os
from dataclasses import dataclass

from ..envfile import EnvFile
from ..settings import convert

# ancien config.json -> nom du champ
LEGACY_KEYS = {"nom": "device_name", "ville": "weather_city", "latitude": "weather_latitude",
               "longitude": "weather_longitude", "veille_secondes": "screensaver_seconds", "web_url": "web_url"}


@dataclass
class MenuConfig:
    device_name: str = "Salon"
    weather_city: str = "Lyon"
    weather_latitude: float = 45.764
    weather_longitude: float = 4.836
    screensaver_seconds: int = 120
    web_url: str = "http://127.0.0.1:8099/"
    theme: str = "retro"
    language: str = "fr"

    def web(self, path=""):
        return self.web_url.rstrip("/") + (path or "/")

    @classmethod
    def load(cls, data_dir, environ=None):
        environ = os.environ if environ is None else environ
        config = cls()
        kinds = {name: type(getattr(config, name)) for name in config.__dataclass_fields__}
        try:
            with open(os.path.join(data_dir, "config.json"), encoding="utf-8") as f:
                legacy = json.load(f)
            for old, name in LEGACY_KEYS.items():
                if old in legacy:
                    setattr(config, name, kinds[name](legacy[old]))
        except (OSError, ValueError):
            pass
        values = EnvFile(os.path.join(data_dir, ".env")).values()
        for name, kind in kinds.items():
            raw = environ.get("PI_MEDIA_" + name.upper(), values.get(name.upper()))
            if raw not in (None, ""):
                try:
                    setattr(config, name, convert(raw, kind))
                except ValueError:
                    pass                    # valeur illisible : on garde la précédente
        return config
