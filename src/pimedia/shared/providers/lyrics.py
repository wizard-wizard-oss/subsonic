"""Paroles : LRCLIB (version synchronisée si possible), puis lyrics.ovh, puis le serveur Subsonic."""
import urllib.parse

from ..external import clean_title, filter_lyrics_candidates, first_artist, lyrics_search_pairs, query_url


def try_json(http, url):
    """Réponse JSON, ou None si le site ne répond pas ou répond autre chose (recherche facultative)."""
    try:
        return http.get_json(url)
    except (OSError, ValueError):
        return None


class LyricsFinder:
    """LRCLIB d'abord (version synchronisée si possible), puis lyrics.ovh, puis le serveur Subsonic."""

    LRCLIB = "https://lrclib.net/api/"
    MAX_DURATION_GAP = 10

    def __init__(self, http, subsonic_lyrics):
        self.http = http
        self.subsonic_lyrics = subsonic_lyrics      # fonction (artiste, titre) -> texte ou ""

    def find(self, artist, title, album="", duration=0):
        attempts = lyrics_search_pairs(artist, title)
        best = self._best_lrclib(self._lrclib_candidates(attempts, album, duration), duration)
        if best:
            return {"synced": best.get("syncedLyrics") or "", "plain": best.get("plainLyrics") or "", "src": "LRCLIB"}
        plain = self._lyrics_ovh(attempts) or self._subsonic(artist, title)
        return plain or {}

    # --- LRCLIB ---
    def _lrclib(self, path, params):
        return try_json(self.http, query_url(self.LRCLIB + path, params))

    def _lrclib_candidates(self, attempts, album, duration):
        candidates = []
        for title, artist in attempts:
            candidates += self._exact_and_search(title, artist, album, duration)
            if self._has_synced(candidates):
                return candidates
        if not self._has_synced(candidates):
            found = self._lrclib("search", [("q", "%s %s" % (clean_title(attempts[0][0]), first_artist(attempts[0][1])))])
            candidates += filter_lyrics_candidates(found, attempts) if isinstance(found, list) else []
        return candidates

    def _exact_and_search(self, title, artist, album, duration):
        params = [("artist_name", artist), ("track_name", title)]
        if album:
            params.append(("album_name", album))
        if duration:
            params.append(("duration", str(int(duration))))
        found = []
        exact = self._lrclib("get", params)
        if isinstance(exact, dict):
            found.append(exact)
        similar = self._lrclib("search", [("track_name", title), ("artist_name", artist)])
        return filter_lyrics_candidates(found + (similar if isinstance(similar, list) else []), [(title, artist)])

    @staticmethod
    def _has_synced(candidates):
        return any(c.get("syncedLyrics") for c in candidates)

    def _best_lrclib(self, candidates, duration):
        usable = [c for c in candidates if c.get("syncedLyrics") or c.get("plainLyrics")]

        def gap(candidate):
            return abs((candidate.get("duration") or 0) - duration) if duration else 0
        synced = [c for c in usable if c.get("syncedLyrics") and (not duration or gap(c) <= self.MAX_DURATION_GAP)]
        pool = synced or usable
        return min(pool, key=gap) if pool else None

    # --- sources de secours ---
    def _lyrics_ovh(self, attempts):
        for title, artist in attempts:
            url = "https://api.lyrics.ovh/v1/%s/%s" % (urllib.parse.quote(artist, safe=""),
                                                       urllib.parse.quote(title, safe=""))
            data = try_json(self.http, url)
            text = ((data or {}).get("lyrics") or "").strip()
            if text:
                return {"synced": "", "plain": text, "src": "lyrics.ovh"}
        return None

    def _subsonic(self, artist, title):
        try:
            text = (self.subsonic_lyrics(artist, title) or "").strip()
        except Exception:
            return None
        return {"synced": "", "plain": text, "src": "Subsonic"} if text else None
