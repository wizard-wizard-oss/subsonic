"""Mix et radios : la logique « magique » de l'édition Pi, ici côté serveur (testée, écrite une seule fois).

Les suggestions viennent de Last.fm, par Subsonic (clé Last.fm globale dans les réglages du serveur) :
getSimilarSongs2 (titres proches), getTopSongs (titres populaires d'un artiste), getArtistInfo2 (artistes proches).
Sans Last.fm, les radios se replient sur des titres au hasard du même style."""
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..shared.text import normalize
from .library import as_list, song_row, visible
from .subsonic import Credentials, SubsonicError, SubsonicUnreachable

DECADES = (1960, 1970, 1980, 1990, 2000, 2010, 2020)
SIZES = (30, 60, 100)
DEPTHS = (1, 2, 3, 4)
PARALLEL = 4            # appels Subsonic simultanés : on ménage le serveur


class MixError(ValueError):
    """Demande impossible (clé de texte i18n)."""


def spread_artists(songs, rng=random):
    """Mélange sans deux titres du même artiste à la suite, dès que c'est possible : à chaque place, on prend
    l'artiste qui a le plus de titres restants parmi ceux qui ne viennent pas de passer."""
    shuffled = list(songs)
    rng.shuffle(shuffled)
    by_artist = {}
    for song in shuffled:
        by_artist.setdefault(song["artist"], []).append(song)
    result, last = [], None
    while by_artist:
        candidates = [a for a in by_artist if a != last] or list(by_artist)
        artist = max(candidates, key=lambda a: len(by_artist[a]))      # à égalité : ordre du mélange
        result.append(by_artist[artist].pop(0))
        if not by_artist[artist]:
            del by_artist[artist]
        last = artist
    return result


def unique(songs):
    seen, result = set(), []
    for song in songs:
        if song["id"] not in seen:
            seen.add(song["id"])
            result.append(song)
    return result


@dataclass
class GenreGroup:
    key: str
    label: str              # orthographe la plus fréquente
    names: list = field(default_factory=list)
    count: int = 0

    def to_api(self):
        return {"key": self.key, "label": self.label, "count": self.count}


@dataclass
class MixOptions:
    genres: list = field(default_factory=list)       # clés de GenreGroup
    decades: list = field(default_factory=list)      # 1980, 1990…
    seed_artist_id: str = ""
    seed_artist_name: str = ""
    size: int = 60
    favorites_first: bool = False
    depth: int = 4                                   # limite des niveaux d'artistes proches
    chronological: bool = False

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict):
            raise MixError("mix.invalid")
        # Les anciennes pages en cache envoient encore wide (1 ou 4 niveaux).
        depth = data.get("depth", 1 if data.get("wide") is False else 4)
        if type(depth) is not int or depth not in DEPTHS:
            raise MixError("mix.invalid")
        options = cls(
            genres=[str(g)[:60] for g in as_list(data.get("genres"))][:12],
            decades=[d for d in as_list(data.get("decades")) if d in DECADES],
            seed_artist_id=str(data.get("seedArtistId") or "")[:100],
            seed_artist_name=str(data.get("seedArtistName") or "")[:200],
            size=data.get("size") if data.get("size") in SIZES else 60,
            favorites_first=bool(data.get("favoritesFirst")), depth=depth,
            chronological=bool(data.get("chronological")))
        return options

    def in_decades(self, song):
        return not self.decades or bool(song.get("year") and any(d <= song["year"] <= d + 9 for d in self.decades))


class Mixes:
    def __init__(self, subsonic, rng=None):
        self.subsonic = subsonic
        self.rng = rng or random.Random()

    # --- appels ---
    def _call(self, user, endpoint, params=()):
        return self.subsonic.call(Credentials.of(user), endpoint, params)

    def _songs(self, user, endpoint, params, *path):
        """Liste de titres d'une réponse ; vide si Subsonic refuse (ex. Last.fm non branché)."""
        try:
            data = self._call(user, endpoint, params)
        except (SubsonicError, SubsonicUnreachable):
            return []
        for key in path:
            data = (data or {}).get(key) or {}
        return [song_row(s) for s in visible(data)]

    def _parallel(self, items, work):
        with ThreadPoolExecutor(PARALLEL) as pool:
            return list(pool.map(work, items))

    # --- mix simples ---
    def random_mix(self, user, genre="", size=60):
        params = [("size", size)] + ([("genre", genre)] if genre else [])
        return self._songs(user, "getRandomSongs", params, "randomSongs", "song")

    def favorites_mix(self, user):
        songs = self._songs(user, "getStarred2", [], "starred2", "song")
        self.rng.shuffle(songs)
        return songs

    def albums_mix(self, user, kind, count):
        """Découverte (albums au hasard) ou derniers ajouts : les titres de quelques albums entiers."""
        albums = as_list((self._call(user, "getAlbumList2", [("type", kind), ("size", count)]).get("albumList2") or {})
                         .get("album"))
        lists = self._parallel([a["id"] for a in albums],
                               lambda album_id: self._songs(user, "getAlbum", [("id", album_id)], "album", "song"))
        return [song for songs in lists for song in songs]

    # --- Last.fm (clé globale réglée dans Subsonic) ---
    def similar_artists(self, user, artist_id, max_depth=1, target=30):
        """Artistes proches sur plusieurs niveaux : 1 = proches de l'artiste, 2 = proches de ceux-là… On descend
        tant qu'on n'en a pas assez (target), jusqu'à max_depth. Renvoie [(id, nom, niveau)]."""
        seen, found, previous = {artist_id}, [], [artist_id]
        for level in range(1, max_depth + 1):
            sources = previous if level == 1 else self.rng.sample(previous, min(8, len(previous)))

            def neighbours(source_id):
                try:
                    info = self._call(user, "getArtistInfo2", [("id", source_id), ("count", 12 if level == 1 else 10)])
                except (SubsonicError, SubsonicUnreachable):
                    return []
                return as_list((info.get("artistInfo2") or {}).get("similarArtist"))
            current = []
            for artists in self._parallel(sources, neighbours):
                for artist in artists:
                    if artist.get("id") and artist["id"] not in seen:
                        seen.add(artist["id"])
                        current.append((artist["id"], artist.get("name", ""), level))
            found += current
            if not current or len(found) >= target:
                break
            previous = [a[0] for a in current]
        return found

    def similar_wide(self, user, artist_id, depth, per_artist=5, target=40):
        """Titres populaires des artistes proches, rangés par niveau {1: [...], 2: [...], …}."""
        artists = self.similar_artists(user, artist_id, depth, target)
        by_level = {1: [], 2: [], 3: [], 4: []}
        tops = self._parallel(artists, lambda a: self._songs(user, "getTopSongs", [("artist", a[1]), ("count", per_artist)],
                                                             "topSongs", "song"))
        for (_, _, level), songs in zip(artists, tops):
            by_level[level] += songs
        return by_level

    def song_radio(self, user, song_id, genre=""):
        """Radio d'un titre : titres proches (Last.fm), sinon même style, sinon au hasard. Le titre d'abord."""
        start = self._songs(user, "getSong", [("id", song_id)], "song")
        similar = self._songs(user, "getSimilarSongs2", [("id", song_id), ("count", 40)], "similarSongs2", "song")
        genre = genre or (start[0]["genre"] if start else "")
        if not similar and genre:
            similar = self.random_mix(user, genre, 40)
        if not similar:
            similar = self.random_mix(user, size=40)
        return unique(start + [s for s in similar if s["id"] != song_id])

    def artist_radio(self, user, artist_id, artist_name):
        """Radio d'un artiste : ses titres proches et populaires, puis ceux des artistes proches (4 niveaux)."""
        songs = self._songs(user, "getSimilarSongs2", [("id", artist_id), ("count", 60)], "similarSongs2", "song")
        if len(songs) < 10:
            songs += self._songs(user, "getTopSongs", [("artist", artist_name), ("count", 30)], "topSongs", "song")
        wide = self.similar_wide(user, artist_id, 4, 5, 40)
        songs = unique(songs + wide[1] + wide[2] + wide[3] + wide[4])
        if not songs:
            raise MixError("mix.no_lastfm")
        return spread_artists(songs, self.rng)[:100]

    # --- créateur de mix ---
    def genre_groups(self, user):
        """Styles de la bibliothèque, variantes d'écriture regroupées, du plus fourni au moins fourni."""
        groups, best = {}, {}
        for genre in as_list((self._call(user, "getGenres").get("genres") or {}).get("genre")):
            name, count = str(genre.get("value", "")), genre.get("songCount", 0)
            key = normalize(name)
            if not key or not count:                # style sans aucun titre : rien à proposer
                continue
            group = groups.setdefault(key, GenreGroup(key, name))
            group.names.append(name)
            group.count += count
            if count > best.get(key, -1):            # l'orthographe la plus utilisée donne le nom affiché
                best[key], group.label = count, name
        return sorted(groups.values(), key=lambda g: -g.count)

    def build(self, user, options):
        """Mix sur mesure : ~20 % titres proches de l'artiste choisi, ~20 % de ses proches, ~20 % plus loin,
        ~30 % de mes favoris (si demandé), le reste au hasard dans les styles et époques choisis.
        Au plus 2 titres par artiste (5 s'il y a peu de choix)."""
        groups = {g.key: g for g in self.genre_groups(user)} if options.genres else {}
        chosen = [groups[k] for k in options.genres if k in groups]
        variants = [name for g in chosen for name in g.names[:4]] or [None]
        ranges = [(d, d + 9) for d in options.decades] or [None]
        jobs = [(g, r) for g in variants for r in ranges]
        per_job = min(150, max(30, -(-300 // len(jobs))))

        def pool_job(job):
            genre, years = job
            params = [("size", per_job)] + ([("genre", genre)] if genre else [])
            if years:
                params += [("fromYear", years[0]), ("toYear", years[1])]
            return self._songs(user, "getRandomSongs", params, "randomSongs", "song")
        pool = [s for songs in self._parallel(jobs, pool_job) for s in songs]

        names = {normalize(n) for g in chosen for n in g.names}
        in_genres = (lambda s: not names or normalize(s.get("genre")) in names)
        seed, near, far = [], [], []
        if options.seed_artist_id:
            seed = [s for s in self._songs(user, "getSimilarSongs2", [("id", options.seed_artist_id), ("count", 80)],
                                           "similarSongs2", "song") if options.in_decades(s)]
            if options.seed_artist_name:
                seed += [s for s in self._songs(user, "getTopSongs", [("artist", options.seed_artist_name), ("count", 15)],
                                                "topSongs", "song") if options.in_decades(s)]
            wide = self.similar_wide(user, options.seed_artist_id, options.depth, 5, 30)
            near = [s for s in wide[1] if options.in_decades(s)]
            far = [s for s in wide[2] + wide[3] + wide[4] if options.in_decades(s)]
        favorites = []
        if options.favorites_first:
            favorites = [s for s in self.favorites_mix(user) if options.in_decades(s) and in_genres(s)]

        picked, seen, per_artist = [], set(), {}
        limit = {"value": 2}

        def take(songs, maximum):
            shuffled = list(songs)
            self.rng.shuffle(shuffled)
            taken = 0
            for song in shuffled:
                if taken >= maximum or len(picked) >= options.size:
                    break
                if song["id"] in seen or per_artist.get(song["artist"], 0) >= limit["value"]:
                    continue
                seen.add(song["id"])
                per_artist[song["artist"]] = per_artist.get(song["artist"], 0) + 1
                picked.append(song)
                taken += 1
        size = options.size
        take(seed, -(-size * 20 // 100))
        take(near, -(-size * (20 if far else 30) // 100))
        take(far, -(-size * 20 // 100))
        take(favorites, -(-size * 30 // 100))
        take(pool, size)
        if len(picked) < size * 0.8:                 # peu de choix : on assouplit la limite par artiste
            limit["value"] = 5
            take(pool, size)
        if options.chronological:
            return sorted(picked, key=lambda s: s.get("year") or 0)
        return spread_artists(picked, self.rng)

    def mix_name(self, user, options):
        """Nom proposé pour enregistrer le mix en playlist (« Mix Rock + Jazz 80s/90s »)."""
        labels = {g.key: g.label for g in self.genre_groups(user)} if options.genres else {}
        label = " + ".join([labels[k] for k in options.genres if k in labels][:2]) or options.seed_artist_name or "Mix"
        decades = "/".join(str(d)[2:] + "s" for d in sorted(options.decades))
        return ("Mix " + label + (" " + decades if decades else "")).strip()
