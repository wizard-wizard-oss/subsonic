"""Mode de navigation (dossiers ou tags) et construction des clés de cache."""
import hashlib
import urllib.parse

from .constants import BROWSE_MODES, FOLDER_ENDPOINTS


class BrowseMode:
    """Classement de la bibliothèque : « folders » (arborescence, comme l'interface Subsonic d'origine)
    ou « tags » (tags ID3). Réglage enregistré en base."""

    def __init__(self, config):
        self.config = config
        saved = config.get("browse_mode")
        self._mode = saved if saved in BROWSE_MODES else "folders"

    def current(self):
        return self._mode

    def set(self, mode):
        if mode in BROWSE_MODES:
            self._mode = mode
            self.config.update(browse_mode=mode)

    def uses_folders(self, endpoint):
        return self.current() == "folders" and endpoint in FOLDER_ENDPOINTS


class CacheKeys:
    """Clé de cache d'un appel : l'appel lui-même et le mode de navigation."""

    def __init__(self, browse):
        self.browse = browse

    def for_call(self, endpoint, params):
        suffix = "|F2" if self.browse.uses_folders(endpoint) else ""
        raw = endpoint + "?" + urllib.parse.urlencode(sorted(params)) + suffix
        return hashlib.sha1(raw.encode()).hexdigest()
