"""La seule classe Deezer : un morceau (liens partagés) et une playlist publique (import), par pages de 100."""
from dataclasses import dataclass
from urllib.parse import urlencode

from .http import HttpClient
from .metadata import ProviderUnavailable

API = "https://api.deezer.com/"
PAGE = 100


class DeezerNotFound(LookupError):
    """Deezer répond 200 avec une erreur : élément privé ou inexistant."""


@dataclass(frozen=True)
class DeezerTrack:
    title: str
    artist: str
    album: str = ""
    duration: int = 0
    image: str = ""


@dataclass(frozen=True)
class DeezerPlaylist:
    name: str
    tracks: tuple


class Deezer:
    def __init__(self, http=None):
        self.http = http or HttpClient(timeout=12)

    def _get(self, path):
        try:
            data = self.http.get_json(API + path)
        except (OSError, ValueError) as error:
            raise ProviderUnavailable("deezer.unavailable") from error
        if not isinstance(data, dict):
            raise ProviderUnavailable("deezer.unavailable")
        if data.get("error"):
            raise DeezerNotFound(path)
        return data

    def track(self, track_id):
        data = self._get("track/" + str(track_id))
        if not data.get("title"):
            raise DeezerNotFound(track_id)
        return DeezerTrack(data["title"], (data.get("artist") or {}).get("name", ""),
                           image=(data.get("album") or {}).get("cover_medium", ""))

    def playlist(self, playlist_id, max_tracks):
        name = str(self._get("playlist/" + playlist_id).get("title") or "Deezer")[:100]
        tracks, index = [], 0
        while len(tracks) < max_tracks:
            page = self._get("playlist/%s/tracks?%s" % (playlist_id, urlencode([("index", index), ("limit", PAGE)])))
            items = page.get("data") or []
            tracks += [DeezerTrack(t.get("title"), (t.get("artist") or {}).get("name"), (t.get("album") or {}).get("title"),
                                   int(t.get("duration") or 0)) for t in items]
            index += len(items)
            if not items or not page.get("next"):
                break
        return DeezerPlaylist(name, tuple(tracks))
