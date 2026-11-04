"""Paroles du titre en cours, cherchées directement sur Internet (LRCLIB, version synchronisée si possible, puis
lyrics.ovh) par la classe commune aux deux éditions. Pas de détour par Subsonic. Gardées un jour en mémoire."""
from .library import TtlCache


class InvalidSong(ValueError):
    pass


class Lyrics:
    def __init__(self, finder, cache=None):
        self.finder = finder
        self.cache = cache or TtlCache(86400)

    def find(self, artist, title, album="", duration=0):
        """{"synced": texte LRC, "plain": texte, "src": source} ; {} si rien n'est trouvé."""
        artist, title, album = (str(v or "").strip() for v in (artist, title, album))
        if not artist or not title or max(len(artist), len(title), len(album)) > 300:
            raise InvalidSong(title)
        duration = int(duration) if isinstance(duration, (int, float)) and 0 < duration < 36000 else 0

        def search():
            try:
                return self.finder.find(artist, title, album, duration) or {}
            except Exception:                 # source injoignable : on réessaiera plus tard
                return {}
        return self.cache.get(("lyrics", artist.lower(), title.lower(), album.lower(), duration), search)
