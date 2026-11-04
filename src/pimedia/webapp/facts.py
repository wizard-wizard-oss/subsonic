"""Biographie d'un artiste (page artiste) et anecdotes du titre en cours (panneau des paroles), par les classes communes
aux deux éditions (Wikipédia, MusicBrainz). La biographie Last.fm vient de Subsonic (getArtistInfo2, Last.fm réglé sur le
serveur) : seulement si Wikipédia n'a pas de page en français. Gardées un jour en mémoire."""
from ..shared.external import FactsBuilder, sentences
from .library import TtlCache
from .subsonic import Credentials, SubsonicError, SubsonicUnreachable


class Facts:
    def __init__(self, subsonic, musicbrainz, wikipedia, cache=None):
        self.subsonic = subsonic
        self.musicbrainz = musicbrainz
        self.wikipedia = wikipedia
        self.cache = cache or TtlCache(86400)

    def artist_bio(self, user, name, artist_id=""):
        """{"text", "img", "src", "url"} : Wikipédia en français, sinon Last.fm (par Subsonic), sinon Wikipédia en
        anglais ; {} si rien n'est trouvé."""
        name, artist_id = (str(v or "").strip() for v in (name, artist_id))
        if not name or max(len(name), len(artist_id)) > 300:
            raise ValueError("artiste")

        def search():
            try:
                return self._wikipedia_bio(name, "fr") or self._lastfm_bio(user, name, artist_id) \
                    or self._wikipedia_bio(name, "en")
            except Exception:                 # source injoignable : on réessaiera plus tard
                return {}
        return self.cache.get(("bio", name.lower(), artist_id), search)

    def song_facts(self, user, artist, title, artist_id="", album=""):
        """{"facts": [{"k", "t"}], "img", "bio"} comme sur le Pi (sortie de l'album, la chanson, l'artiste) ; {} sinon."""
        artist, title, artist_id, album = (str(v or "").strip() for v in (artist, title, artist_id, album))
        if not artist or not title or max(len(artist), len(title), len(artist_id), len(album)) > 300:
            raise ValueError("titre")

        def search():
            builder = FactsBuilder(self.musicbrainz, self.wikipedia, lambda aid: self._biography(user, aid))
            try:
                return builder.build(artist, title, artist_id, album) or {}
            except Exception:
                return {}
        return self.cache.get(("facts", artist.lower(), title.lower(), album.lower()), search)

    def _wikipedia_bio(self, name, lang):
        page = self.wikipedia.artist_page(name, lang)
        text = (page.get("extract") or "").strip()
        if not text:
            return {}
        return {"text": text, "img": (page.get("thumbnail") or {}).get("source", ""), "src": "Wikipédia",
                "url": ((page.get("content_urls") or {}).get("desktop") or {}).get("page", "")}

    def _lastfm_bio(self, user, name, artist_id):
        info = self._artist_info(user, artist_id)
        text = " ".join(sentences(info.get("biography"), 12, 20, 400))
        if not text:
            return {}
        return {"text": text, "img": self.wikipedia.artist_photo(name), "src": "Last.fm", "url": info.get("lastFmUrl", "")}

    def _biography(self, user, artist_id):
        return self._artist_info(user, artist_id).get("biography", "")

    def _artist_info(self, user, artist_id):
        if not artist_id:
            return {}
        try:
            return self.subsonic.call(Credentials.of(user), "getArtistInfo2", [("id", artist_id)]).get("artistInfo2") or {}
        except (SubsonicError, SubsonicUnreachable):
            return {}
