"""Priorité des goûts personnels : écoutes, morceau repris, puis favoris du compte."""
from .entities import PersonalPage


class PersonalHome:
    def __init__(self, history, catalog):
        self.history, self.catalog = history, catalog

    def page(self, user, before=None):
        history = self.history.page(user, before)
        songs = tuple(song for entry in history.entries if (song := self.catalog.song(user, entry.song_id)))
        seed, basis = self._seed(user, songs)
        recent, seen = [], set()
        for song in songs:
            if not song.album_id or song.album_id in seen:
                continue
            seen.add(song.album_id)
            album = self.catalog.album(user, song.album_id)
            if album:
                recent.append(album)
        suggestions = self.catalog.suggestions(user, seed) if seed else ()
        return PersonalPage(basis, seed, tuple(recent), suggestions, history.next_before)

    def _seed(self, user, songs):
        if songs:
            return songs[0], "history"
        current = self.catalog.current(user)
        if current:
            return current, "queue"
        favorites = self.catalog.favorites(user)
        return (favorites[0], "favorites") if favorites else (None, "newest")
