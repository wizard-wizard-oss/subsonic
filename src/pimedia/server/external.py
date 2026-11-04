"""Sources externes du Pi : les recherches (paroles, anecdotes, genres) viennent de pimedia.shared.external,
leurs résultats sont gardés dans le cache du Pi (définitivement s'ils ne sont pas vides)."""
import json

from ..shared.external import FactsBuilder, JsonFetcher, LyricsFinder, MusicBrainz, Wikipedia  # noqa: F401
from .constants import FOREVER

EMPTY_RESULT_TTL = 86400            # un résultat vide est retenté le lendemain


# ---------- façade avec cache ----------
class ExternalInfo:
    """Résultats des sources externes, conservés dans le cache (définitivement s'ils ne sont pas vides)."""

    def __init__(self, cache, keys, lyrics, facts, musicbrainz):
        self.cache = cache
        self.keys = keys
        self.lyrics_finder = lyrics
        self.facts_builder = facts
        self.musicbrainz = musicbrainz

    def lyrics(self, artist, title, album="", duration=0):
        params = [("artist", artist), ("title", title), ("album", album), ("duration", str(duration))]
        return self._cached("lyrics2", params, lambda: self.lyrics_finder.find(artist, title, album, duration))

    def facts(self, artist, title, artist_id, album=""):
        params = [("artist", artist), ("title", title), ("aid", artist_id), ("album", album)]
        return self._cached("facts", params, lambda: self.facts_builder.build(artist, title, artist_id, album))

    def genres(self, artist):
        return self._cached("genres", [("artist", artist)], lambda: self.musicbrainz.genres(artist))

    def _cached(self, kind, params, builder):
        """Retourne le corps JSON (octets), depuis le cache ou après calcul."""
        key = self.keys.for_call("ext-" + kind, params)
        entry = self.cache.get(key)
        if entry:
            return entry.body
        try:
            data = builder()
        except Exception:
            data = {}
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.cache.put(key, "ext", params, FOREVER if data else EMPTY_RESULT_TTL, "application/json", body)
        return body
