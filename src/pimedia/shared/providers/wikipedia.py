"""Wikipédia : anecdotes d'une chanson, page et photo d'un artiste (fr puis en)."""
import re
import urllib.parse

from ..external import MUSIC_WORDS, query_url, sentences


class Wikipedia:
    LANGUAGES = ("fr", "en")

    def __init__(self, http):
        self.http = http

    def _summary(self, lang, page):
        url = "https://%s.wikipedia.org/api/rest_v1/page/summary/%s" % (
            lang, urllib.parse.quote(page.replace(" ", "_"), safe=""))
        return self.http.get_json(url)

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
        hits = self.http.get_json(query_url("https://%s.wikipedia.org/w/api.php" % lang, [
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
