"""Règles pures de correspondance d'un morceau YouTube. Aucun appel réseau ni accès au stockage."""
import html
import re
from difflib import SequenceMatcher

from ..shared.text import normalize
from ..server.extmusic.sources import clean_channel

PRESENTATION = {"official", "officiel", "music", "video", "clip", "audio", "lyric", "lyrics", "hd", "hq", "4k", "1080p"}
UNSUITABLE = re.compile(r"\b(preview|teaser|snippet|sample|sampler|excerpt|extraits?|full album|full ep|full lp|"
                         r"full release|complete album|album complet|dj mix|compilation|shorts)\b", re.I)
VERSION = re.compile(r"\b(remix|mix|edit|live|cover|acoustic|instrumental|karaoke|demo|sped up|slowed|nightcore|remaster(?:ed)?)\b", re.I)
CATALOG_NUMBER = re.compile(r"[A-Z]{2,10}[ ._-]?[0-9]{1,8}(?:[.-][A-Z0-9]{1,6})?")
MUSICAL_NUMBER = re.compile(r"^(?:PART|PT|VOL|VOLUME|SIDE|TAKE|MIX|REMIX|EDIT|VERSION|LIVE|DEMO|EPISODE)", re.I)


def clean_title(value):
    """Retirer la présentation vidéo, conserver les noms de remix, edits et autres versions."""
    value = html.unescape(value or "")
    def bracket(match):
        words = {normalize(w) for w in re.findall(r"\w+", match.group())}
        return " " if words and words <= PRESENTATION else match.group()
    value = re.sub(r"\([^)]*\)|\[[^]]*\]", bracket, value)
    value = re.sub(r"\s+(?:[-|]\s*)?(?:official (?:music )?(?:video|audio)|music video|lyrics|hd|hq|4k)\s*$", "", value, flags=re.I)
    return " ".join(value.split()).strip(" -–—|:")


def source_title(value, labels=()):
    """Habillage d'une vidéo : code catalogue entre crochets et suffixe d'un label effectivement connu."""
    names = {normalize(label) for label in labels}
    def annotation(match):
        content = match.group()[1:-1].strip()
        catalogue = CATALOG_NUMBER.fullmatch(content) and not MUSICAL_NUMBER.match(content)
        return " " if catalogue or normalize(content) in names else match.group()
    title = re.sub(r"\[[^]]*\]", annotation, clean_title(value))
    parts = re.split(r"\s+[-–—|]\s+", title)
    while len(parts) > 1 and normalize(parts[-1].strip()) in names:
        parts.pop()
    return " - ".join(parts).strip()


def has_artist(artist, value):
    wanted, found = normalize(artist), clean_channel(value)
    if not artist.strip():
        return False
    if wanted == normalize(found):
        return True
    credits = re.split(r"\s*[,;&]\s*|\s+(?:feat\.?|ft\.?|featuring|and|with|x)\s+", found, flags=re.I)
    return any(normalize(credit) == wanted for credit in credits)


def credited_title(artist, title):
    """Artiste écrit au début ou à la fin de la vidéo ; jamais un simple bout de mot."""
    spans = list(re.finditer(r"[^\W_]+", title))
    key = normalize(artist)
    if key:
        for span in spans:
            if normalize(title[:span.end()]) == key:
                return title[span.end():].strip(" -–—|:"), True
            if normalize(title[span.start():]) == key:
                return title[:span.start()].strip(" -–—|:"), True
    return title, False


def title_similarity(wanted, found, close_duration=False):
    wanted, found = normalize(wanted), normalize(found)
    if not wanted or not found:
        return 0
    if wanted == found:
        return 1
    # Un titre court ou numérique ne supporte pas de rapprochement approximatif (« 241 » / « 242 »).
    if min(len(wanted), len(found)) < 10 or re.findall(r"\d+", wanted) != re.findall(r"\d+", found):
        return 0
    similarity = SequenceMatcher(None, wanted, found).ratio()
    return similarity if similarity >= (0.93 if close_duration else 0.94) else 0


def match_score(track, item, linked=False, labels=()):
    """Zéro si artiste, titre, version ou durée divergent ; la popularité ne sauve jamais un mauvais morceau."""
    title = source_title(item.get("title"), labels)
    wanted = clean_title(track.title)
    if UNSUITABLE.search(title) and not UNSUITABLE.search(wanted):
        return 0
    title, credited = credited_title(track.artist, title)
    if (VERSION.search(wanted) or VERSION.search(title)) and normalize(wanted) != normalize(title):
        return 0
    artist = has_artist(track.artist, item.get("artist"))
    if not (credited or artist or linked):
        return 0
    duration = item.get("duration") or 0
    gap = abs(track.duration - duration)
    close_duration = bool(track.duration and duration and gap <= min(15, max(5, track.duration * 0.02)))
    similarity = title_similarity(wanted, title, close_duration)
    if not similarity:
        return 0
    if track.duration and duration and gap > max(15, track.duration * 0.12):
        return 0
    return round(0.8 * similarity + 0.1 * bool(track.duration and duration) + 0.1 * (credited or artist), 3)


def search_query(track):
    """Une seule requête ciblée. Les mots de la version demandée restent présents."""
    return " ".join([track.artist.strip(), clean_title(track.title)]).strip()[:200]
