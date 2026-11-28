"""Projections typées des lectures Subsonic déjà utilisées par la bibliothèque."""
from ...shared.text import normalize
from ..library.catalog import album_card, song_row, visible
from ..subsonic import Credentials, SubsonicError, SubsonicUnreachable
from .entities import Album, PAGE_SIZE, SEED_ATTEMPTS, Seed, SUGGESTION_PAGES

UNAVAILABLE = (SubsonicError, SubsonicUnreachable)


def _album_key(artist, title):
    """Deux copies du même disque se comparent par artiste/titre, si les deux sont renseignés."""
    key = normalize(artist), normalize(title)
    return key if all(key) else None


class HomeCatalog:
    def __init__(self, library, listening):
        self.library, self.listening = library, listening

    def song(self, user, identity):
        try:
            return Seed.of(self.library.song(user, identity))
        except UNAVAILABLE:
            return None

    def album(self, user, identity):
        try:
            raw = self.library.album_brief(user, identity)
            return Album.of(raw) if raw.get("id") else None
        except UNAVAILABLE:
            return None

    def current(self, user):
        try:
            queue = self.listening.play_queue(user)
        except UNAVAILABLE:
            return None
        songs, index = queue["songs"], queue["index"]
        if songs and 0 <= index < len(songs) and str(songs[index]["id"]) == queue["currentId"]:
            return Seed.of(songs[index])
        return None

    def favorites(self, user):
        try:
            raw = self.library.subsonic.call(Credentials.of(user), "getStarred2").get("starred2") or {}
            seeds = [Seed.of(song_row(song)) for song in visible(raw.get("song"))[:SEED_ATTEMPTS]]
            seeds += [self._album_seed(album) for album in visible(raw.get("album"))[:SEED_ATTEMPTS]]
            if seeds:
                return tuple(seeds)
            return self._artist_favorites(user, visible(raw.get("artist"))[:SEED_ATTEMPTS])
        except UNAVAILABLE:
            return ()

    def _artist_favorites(self, user, artists):
        seeds = []
        for artist in artists:
            try:
                raw = self.library.subsonic.call(Credentials.of(user), "getArtist", [("id", artist["id"])])
                albums = visible((raw.get("artist") or {}).get("album"))
                seeds.extend(self._album_seed(album) for album in albums[:1])
            except UNAVAILABLE:
                continue
        return tuple(seeds)

    @staticmethod
    def _album_seed(raw):
        album = Album.of(album_card(raw))
        return Seed(album.id, "", album.artist_id, album.artist, album.id, album.name, album.genre, album.cover_id)

    def suggestions(self, user, seed):
        if not seed.genre:
            return ()
        found = []
        seen_ids = {seed.album_id}
        seed_key = _album_key(seed.artist, seed.album)
        seen_albums = {seed_key} if seed_key else set()
        for page in range(SUGGESTION_PAGES):
            try:
                result = self.library.albums(user, "genre", seed.genre, page)
            except UNAVAILABLE:
                break
            for raw in result["albums"]:
                album = Album.of(raw)
                key = _album_key(album.artist, album.name)
                if album.id in seen_ids or key and key in seen_albums:
                    continue
                seen_ids.add(album.id)
                if key:
                    seen_albums.add(key)
                found.append(album)
            if len(found) >= PAGE_SIZE or not result["hasMore"]:
                break
        return tuple(found[:PAGE_SIZE])
