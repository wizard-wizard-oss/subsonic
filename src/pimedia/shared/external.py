"""Outils communs aux deux éditions pour les sources externes : nettoyage des titres, recherches de paroles,
assemblage des anecdotes. Les services eux-mêmes sont dans providers/ (un module par service)."""
import re
import urllib.parse

from .text import normalize

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


def lyrics_search_pairs(artist, title):
    """Variantes (titre, artiste) pour les paroles, originales d'abord, sans modifier les données affichées.

    Une vidéo peut créditer l'artiste dans son titre, dans l'un ou l'autre ordre ; son champ artiste
    désigne alors souvent la chaîne. Un sous-titre final entre parenthèses reste une variante de secours.
    """
    pairs = [(title, artist)]
    separator = re.search(r"\s*;\s*|\s+[-–—|]\s+", title)
    if separator:
        left, right = title[:separator.start()].strip(), title[separator.end():].strip()
        if left and right:
            inferred = [(left, right), (right, left)]
            pairs += inferred if ";" in separator.group() else inferred[::-1]
    attempts = []
    for song, performer in pairs:
        cleaned, performer_head = clean_title(song), first_artist(performer)
        attempts += [(song, performer), (cleaned, performer_head)]
        short = re.sub(r"\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$", "", cleaned).strip()
        if short:
            attempts.append((short, performer_head))
    return distinct_pairs(attempts)


def filter_lyrics_candidates(candidates, attempts):
    """Écarter les homonymes et titres voisins des résultats LRCLIB, même après une recherche libre."""
    def key(title, artist):
        return normalize(clean_title(title)), normalize(first_artist(artist))
    wanted = {key(title, artist) for title, artist in attempts}
    return [candidate for candidate in candidates if isinstance(candidate, dict) and
            key(candidate.get("trackName") or "", candidate.get("artistName") or "") in wanted]


def query_url(base, params):
    return base + "?" + urllib.parse.urlencode(params)


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
