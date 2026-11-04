"""Import d'une playlist venue d'ailleurs. La page envoie les titres par petits lots : chacun est cherché dans Subsonic
(search3, par le texte : le Subsonic d'origine ne connaît pas les ISRC) et noté ; ceux qui manquent peuvent être
cherchés sur YouTube (YouTube Music, sans quota). La personne vérifie l'aperçu, puis la playlist est créée : titres
Subsonic dans Subsonic, titres YouTube gardés par le site à leur place (comme pour toute playlist mixte)."""
import difflib
import re

from ..server.extmusic.sources import is_alternate_version
from ..server.podcasts.relevance import normalize
from .entities import ImportedTrack
from .extmusic import ExtMusicError
from .import_readers import ImportFailed
from .library import as_list, song_row
from .playlists import MAX_EXT_TRACKS, MAX_SONGS
from .subsonic import Credentials, SubsonicError, SubsonicUnreachable

FOUND, DOUBT, MISSING = "found", "doubt", "missing"
SURE, POSSIBLE = 0.85, 0.6            # note au-dessus de laquelle un titre est pris d'office / proposé
YOUTUBE_SURE = 0.75
CANDIDATES = 3
SONG_COUNT = 40

# Mentions qui ne changent pas la chanson : « (feat. X) », « - Remastered 2011 », « (Radio Edit) », « [Mono] »…
NOISE = re.compile(r"\s*[(\[][^)\]]*\b(feat|ft|featuring|with|avec|remaster(ed)?|radio edit|single version|album version|"
                   r"mono|stereo|bonus track|explicit|deluxe|edit)\b[^)\]]*[)\]]"
                   r"|\s+-\s+[^-]*\b(remaster(ed)?|radio edit|single version|album version|mono|stereo|edit)\b.*$"
                   r"|\s+(feat|ft|featuring)\.?\s.*$", re.IGNORECASE)


def core_title(title):
    """Le titre sans les mentions de version ni les invités, normalisé."""
    return normalize(NOISE.sub("", title or "")).strip()


def similar(a, b):
    a, b = normalize(a).strip(), normalize(b).strip()
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def artist_score(wanted, found):
    """1 si l'un des noms contient l'autre (« Daft Punk » / « Daft Punk, Pharrell Williams »), sinon la ressemblance."""
    wanted, found = normalize(wanted), normalize(found)
    if not wanted.strip():
        return 0.5                                   # artiste inconnu : ni pour ni contre
    if wanted in found or found.strip() and found in wanted:
        return 1.0
    return similar(wanted, found)


def score(track, song):
    """Note de 0 à 1 : ce titre de la bibliothèque est-il celui de la playlist ?"""
    title = max(similar(core_title(track.title), core_title(song.get("title"))), similar(track.title, song.get("title")))
    total = 0.6 * title + 0.3 * artist_score(track.artist, song.get("artist"))
    if track.duration and song.get("duration"):
        gap = abs(track.duration - int(song["duration"]))
        total += 0.1 if gap <= 3 else 0.05 if gap <= 10 else -0.1 if gap > 30 else 0
    else:
        total += 0.05
    if track.album and song.get("album") and similar(track.album, song["album"]) > 0.8:
        total += 0.05
    if is_alternate_version(song.get("title")) != is_alternate_version(track.title):
        total -= 0.2                                  # un live à la place de l'original, ou l'inverse
    return round(max(0.0, min(1.0, total)), 3)


def youtube_score(track, item):
    """Même idée pour un résultat YouTube, dont le titre contient souvent l'artiste (« Artiste - Titre (Clip) »)."""
    title = item.get("title") or ""
    if " - " in title and not item.get("album"):
        maybe_artist, rest = title.split(" - ", 1)
        if artist_score(track.artist, maybe_artist) > 0.8:
            title = rest
    return score(ImportedTrack(track.title, track.artist, "", track.duration),
                 {"title": re.sub(r"\s*[(\[][^)\]]*\b(official|officiel|video|vidéo|clip|audio|lyrics?|paroles|hd|4k)\b[^)\]]*[)\]]",
                                  "", title, flags=re.I),
                  "artist": item.get("artist"), "duration": item.get("duration")})


class PlaylistImport:
    def __init__(self, subsonic, extmusic, playlists, ext_check, reader):
        """extmusic : ExternalMusic ; playlists : Playlists ; ext_check : ExtFavorites ; reader : DeezerReader."""
        self.subsonic, self.extmusic, self.playlists = subsonic, extmusic, playlists
        self.ext_check, self.reader = ext_check, reader

    # ---------- dans la bibliothèque ----------
    def _search(self, user, query):
        if not query.strip():
            return []
        result = self.subsonic.call(Credentials.of(user), "search3", [
            ("query", query), ("songCount", SONG_COUNT), ("artistCount", 0), ("albumCount", 0)])
        return as_list((result.get("searchResult3") or {}).get("song"))

    def match(self, user, track):
        """{track, status, choices : titres de la bibliothèque du plus probable au moins probable, avec leur note}."""
        title = NOISE.sub("", track.title).strip() or track.title
        songs, seen = [], set()
        for query in (title, (title + " " + track.artist).strip()):
            for song in self._search(user, query):
                if song.get("id") not in seen:
                    seen.add(song.get("id"))
                    songs.append(song)
            if songs and max(score(track, s) for s in songs) >= SURE:
                break                                  # pas besoin de la seconde recherche
        ranked = sorted(((score(track, s), s) for s in songs), key=lambda pair: -pair[0])
        choices = [dict(song_row(s), score=note) for note, s in ranked[:CANDIDATES] if note >= POSSIBLE]
        status = FOUND if choices and choices[0]["score"] >= SURE else DOUBT if choices else MISSING
        return {"track": track.to_api(), "status": status, "choices": choices}

    def match_all(self, user, tracks):
        try:
            return [self.match(user, t) for t in tracks]
        except (SubsonicError, SubsonicUnreachable):
            raise ImportFailed("import.library_unreachable")

    # ---------- sur YouTube ----------
    def youtube(self, user, track):
        """Le meilleur résultat YouTube s'il ressemble assez au titre, sinon None. Compte dans la limite de
        recherches de la personne ; une recherche déjà faite (par n'importe qui) est gratuite."""
        items = self.extmusic.search(user, "youtube", (track.artist + " " + NOISE.sub("", track.title)).strip())
        ranked = sorted(((youtube_score(track, i), i) for i in items), key=lambda pair: -pair[0])
        if ranked and ranked[0][0] >= YOUTUBE_SURE:
            return dict(ranked[0][1], score=ranked[0][0])
        return None

    def youtube_all(self, user, tracks):
        """{items : un résultat ou None par titre, stopped : clé de texte si on a dû s'arrêter (limite atteinte,
        YouTube injoignable) ; les titres suivants restent alors sans réponse}."""
        items = []
        for track in tracks:
            try:
                items.append(self.youtube(user, track))
            except ExtMusicError as error:
                return {"items": items, "stopped": error.args[0]}
        return {"items": items, "stopped": None}

    # ---------- création ----------
    def create(self, user, name, entries):
        """entries, dans l'ordre : {"songId"} (bibliothèque) ou {"item"} (titre d'ailleurs au format de la page).
        Crée la playlist Subsonic, puis place les titres d'ailleurs entre les bons titres."""
        song_ids, extras = [], []
        for entry in entries:
            if "songId" in entry:
                song_ids.append(entry["songId"])
            else:
                extras.append((len(song_ids), self.ext_check.checked(entry["item"])))
        if not song_ids and not extras:
            raise ImportFailed("import.nothing_chosen")
        if len(song_ids) > MAX_SONGS or len(extras) > MAX_EXT_TRACKS:
            raise ImportFailed("import.too_long")
        return self.playlists.create_mixed(user, name, song_ids, extras)
