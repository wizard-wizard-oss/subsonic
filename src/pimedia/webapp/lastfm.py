"""Service Last.fm : statistiques publiques d'un album identifié, indépendantes de son label."""
from dataclasses import asdict, dataclass

from ..shared.external import query_url
from ..shared.text import normalize
from .music_metadata import PublicMetadata

LASTFM_BLANK = "2a96cbd8b46e442fc41c2b86b821562f"  # Visuel vide renvoyé par Last.fm.


@dataclass(frozen=True)
class AlbumPopularity:
    listeners: int = 0
    plays: int = 0


class LastFm(PublicMetadata):
    prefix = "label-lastfm:"
    interval = 0.25
    base = "https://ws.audioscrobbler.com/2.0/"

    def album(self, artist, title, cached=False):
        params = dict(method="album.getInfo", artist=artist, album=title, autocorrect=0, format="json")
        key = query_url("album", sorted(params.items()))
        data = self.cached(key) if cached else self.read(
            key, query_url(self.base, dict(params, api_key=self.api_key)), {},
            lambda raw: asdict(self._popularity(raw, artist, title)))
        return AlbumPopularity(**data) if data is not None else None

    @staticmethod
    def _popularity(raw, artist, title):
        if raw.get("error"):
            if str(raw["error"]) == "6":
                return AlbumPopularity()
            raise ValueError("Last.fm")
        album = raw.get("album") or {}
        if normalize(album.get("name")) != normalize(title) or normalize(album.get("artist")) != normalize(artist):
            return AlbumPopularity()
        return AlbumPopularity(int(album.get("listeners") or 0), int(album.get("playcount") or 0))
