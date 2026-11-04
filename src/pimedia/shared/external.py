"""Sources externes, communes aux deux éditions : paroles (LRCLIB, lyrics.ovh, sinon Subsonic), anecdotes et photo
(MusicBrainz, Wikipédia). Rien ici ne dépend du Pi ni du site : chaque édition garde ses résultats à sa façon."""
import json
import re
import time
import urllib.parse
import urllib.request

USER_AGENT = "PiMediaStation/1.0 (lecteur personnel)"

TITLE_NOISE = r"remaster|live|version|edit|mix|feat|ft\.|radio|mono|stereo|bonus|deluxe|acoustic"
MUSIC_WORDS = r"chant|music|band|group|rap|dj|compos|singer|duo|trio|artist|musici|pianist|guitar"


# ---------- fonctions de texte (pures) ----------
def clean_title(title):
    """Titre sans les mentions « (Remastered) », « - Live », « feat. … » qui gênent les recherches."""
    title = re.sub(r"\s*[\(\[][^)\]]*(%s)[^)\]]*[\)\]]" % TITLE_NOISE, "", title, flags=re.I)
    title = re.sub(r"\s+-\s+(.*(remaster|live|version|edit|mix|mono|stereo|bonus|single).*)$", "", title, flags=re.I)
    title = re.sub(r"\s+(feat\.?|ft\.?|featuring)\s+.*$", "", title, flags=re.I)
    return title.strip() or title


def first_artist(artist):
    """Premier artiste d'une mention « A feat. B »."""
    head = re.split(r"\s+(?:feat\.?|ft\.?|featuring)\s+", artist, maxsplit=1, flags=re.I)[0].strip()
    return head or artist


def sentences(text, maximum, min_len=45, max_len=280):
    """Phrases d'un texte (HTML retiré) ni trop courtes ni trop longues."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.split(r"(?:Read more on Last\.fm|Lire la suite|Lire plus)", text)[0]
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ«\"])", text)
    return [p.strip() for p in parts if min_len <= len(p.strip()) <= max_len][:maximum]


def distinct_pairs(pairs):
    seen = []
    for pair in pairs:
        if pair not in seen:
            seen.append(pair)
    return seen


# ---------- accès HTTP ----------
class JsonFetcher:
    def get(self, url, timeout=8):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))

    def try_get(self, url, timeout=8):
        """Comme get, mais retourne None au lieu de lever une erreur."""
        try:
            return self.get(url, timeout)
        except Exception:
            return None


def query_url(base, params):
    return base + "?" + urllib.parse.urlencode(params)


# ---------- paroles ----------
class LyricsFinder:
    """LRCLIB d'abord (version synchronisée si possible), puis lyrics.ovh, puis le serveur Subsonic."""

    LRCLIB = "https://lrclib.net/api/"
    MAX_DURATION_GAP = 10

    def __init__(self, fetcher, subsonic_lyrics):
        self.fetcher = fetcher
        self.subsonic_lyrics = subsonic_lyrics      # fonction (artiste, titre) -> texte ou ""

    def find(self, artist, title, album="", duration=0):
        attempts = distinct_pairs([(title, artist), (clean_title(title), first_artist(artist))])
        best = self._best_lrclib(self._lrclib_candidates(attempts, album, duration), duration)
        if best:
            return {"synced": best.get("syncedLyrics") or "", "plain": best.get("plainLyrics") or "", "src": "LRCLIB"}
        plain = self._lyrics_ovh(attempts) or self._subsonic(artist, title)
        return plain or {}

    # --- LRCLIB ---
    def _lrclib(self, path, params):
        return self.fetcher.try_get(query_url(self.LRCLIB + path, params))

    def _lrclib_candidates(self, attempts, album, duration):
        candidates = []
        for title, artist in attempts:
            candidates += self._exact_and_search(title, artist, album, duration)
            if self._has_synced(candidates):
                return candidates
        if not self._has_synced(candidates):
            found = self._lrclib("search", [("q", "%s %s" % (clean_title(attempts[0][0]), first_artist(attempts[0][1])))])
            candidates += found if isinstance(found, list) else []
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
        return found + (similar if isinstance(similar, list) else [])

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
            data = self.fetcher.try_get(url, timeout=10)
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


# ---------- anecdotes, genres, photo ----------
class MusicBrainz:
    BASE = "https://musicbrainz.org/ws/2/"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def genres(self, artist):
        """Genres d'après MusicBrainz (vocabulaire commun, plus fiable que les tags des fichiers)."""
        data = self.fetcher.get(query_url(self.BASE + "artist", [
            ("query", 'artist:"%s"' % artist.replace('"', "")), ("fmt", "json"), ("limit", "3")]))
        for found in data.get("artists", []):
            if found.get("score", 0) >= 90:
                tags = sorted(found.get("tags", []), key=lambda t: -t.get("count", 0))
                names = [t["name"] for t in tags if t.get("count", 0) >= 1][:8]
                if names:
                    return {"genres": names}
        return {}

    def release_fact(self, artist, album):
        """« Album X, sorti en 1999 (il y a N ans) » d'après le groupe de sorties (les recherches par titre de chanson sont peu fiables)."""
        if not album:
            return None
        query = 'releasegroup:"%s" AND artist:"%s"' % (album.replace('"', ""), artist.replace('"', ""))
        data = self.fetcher.try_get(query_url(self.BASE + "release-group", [
            ("query", query), ("fmt", "json"), ("limit", "3")]))
        for group in (data or {}).get("release-groups", []):
            year = re.match(r"(\d{4})", group.get("first-release-date") or "")
            if group.get("score", 0) >= 90 and year:
                return self._describe(group.get("title") or album, int(year.group(1)))
        return None

    @staticmethod
    def _describe(title, year):
        text = "Album « %s », sorti en %d" % (title, year)
        age = time.localtime().tm_year - year
        if age > 0:
            text += " (il y a %d an%s)" % (age, "s" if age > 1 else "")
        return text + "."


class Wikipedia:
    LANGUAGES = ("fr", "en")

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def _summary(self, lang, page):
        url = "https://%s.wikipedia.org/api/rest_v1/page/summary/%s" % (
            lang, urllib.parse.quote(page.replace(" ", "_"), safe=""))
        return self.fetcher.get(url)

    def song_facts(self, artist, title):
        last_name = artist.split()[-1].lower() if artist else ""
        for lang in self.LANGUAGES:
            try:
                facts = self._song_facts_in(lang, artist, title, last_name)
            except Exception:
                continue
            if facts:
                return facts
        return []

    def _song_facts_in(self, lang, artist, title, last_name):
        word = "chanson" if lang == "fr" else "song"
        hits = self.fetcher.get(query_url("https://%s.wikipedia.org/w/api.php" % lang, [
            ("action", "query"), ("list", "search"), ("format", "json"), ("srlimit", "4"),
            ("srsearch", '"%s" %s %s' % (title, artist, word))]))
        for hit in hits.get("query", {}).get("search", []):
            page = self._summary(lang, hit["title"])
            extract = page.get("extract", "")
            low = extract.lower()
            if title.lower()[:20] in low and last_name in low and page.get("type") == "standard":
                found = sentences(extract, 6)
                if found:
                    return found
        return []

    def artist_page(self, artist, lang):
        """Résumé de la page Wikipédia d'un artiste, seulement si c'est bien celle d'un musicien ou d'un groupe ; {} sinon."""
        try:
            page = self._summary(lang, artist)
        except Exception:
            return {}
        desc = ((page.get("description") or "") + " " + (page.get("extract") or "")[:200]).lower()
        return page if page.get("type") == "standard" and re.search(MUSIC_WORDS, desc) else {}

    def artist_photo(self, artist):
        """Photo de l'artiste, seulement si la page est bien celle d'un musicien ou d'un groupe."""
        for lang in self.LANGUAGES:
            page = self.artist_page(artist, lang)
            if page.get("thumbnail"):
                return page["thumbnail"]["source"]
        return ""


class FactsBuilder:
    """Assemble anecdotes (sortie de l'album, Wikipédia, biographie Subsonic), biographie et photo."""

    def __init__(self, musicbrainz, wikipedia, artist_biography):
        self.musicbrainz = musicbrainz
        self.wikipedia = wikipedia
        self.artist_biography = artist_biography    # fonction (id artiste) -> texte

    def build(self, artist, title, artist_id, album=""):
        release = self.musicbrainz.release_fact(artist, album)
        song_facts = self.wikipedia.song_facts(artist, title)
        biography = self._biography(artist_id)
        facts = [{"k": "Sortie", "t": release}] if release else []
        facts += self._interleave(song_facts, sentences(biography, 5))
        photo = self.wikipedia.artist_photo(artist)
        full_bio = " ".join(sentences(biography, 12, 20, 400))
        result = {"facts": facts, "img": photo, "bio": full_bio}
        return result if (facts or photo or full_bio) else {}

    def _biography(self, artist_id):
        if not artist_id:
            return ""
        try:
            return self.artist_biography(artist_id) or ""
        except Exception:
            return ""

    @staticmethod
    def _interleave(song_facts, bio_facts):
        facts = []
        for i in range(max(len(song_facts), len(bio_facts))):
            if i < len(song_facts):
                facts.append({"k": "La chanson", "t": song_facts[i]})
            if i < len(bio_facts):
                facts.append({"k": "L’artiste", "t": bio_facts[i]})
        return facts
