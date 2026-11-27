"""Labels et collaborations MusicBrainz. Aucun enrichissement ne modifie la bibliothèque.

Les éditions sont proposées par titre ET artiste exacts ; plusieurs éditions restent un choix explicite.
Les métadonnées publiques sont partagées, les recherches Subsonic sont toujours faites au nom du lecteur.
Toutes les requêtes MusicBrainz passent par la classe MusicBrainz ; ce service garde les règles de choix.
"""
from ..shared.providers.musicbrainz import mbid
from ..shared.text import normalize
from .exploration_entities import AlbumCredits, ArtistMatches

MAX_OFFSET = 25000


class Exploration:
    def __init__(self, musicbrainz, folders, library):
        self.musicbrainz, self.folders, self.library = musicbrainz, folders, library

    def artists(self, name):
        """Identités exactes, sans choisir un homonyme à la place de la personne."""
        name = str(name or "").strip()
        if not name or len(name) > 300:
            raise ValueError("artist")
        name_key = normalize(name)
        found = self.musicbrainz.search_artists(name)
        return ArtistMatches([a for a in found.value if normalize(a.name) == name_key], found.stale)

    def connections(self, identity):
        return self.musicbrainz.artist_connections(mbid(identity))

    def album(self, user, album_id, release=""):
        # Les noms viennent de l'album accessible par ce compte, pas d'un nom fourni par le navigateur.
        album = self.folders.album(user, album_id)
        title, artist = album["name"], album["artist"]
        found = self.musicbrainz.find_releases(title, artist)
        title_key, artist_key = normalize(title), normalize(artist)
        editions = [edition for edition, names in found.value if normalize(edition.title) == title_key
                    and artist_key in {normalize(name) for name in names}]
        result = AlbumCredits(editions=editions, stale=found.stale)
        if not release:
            return result
        release = mbid(release)
        if release not in {e.id for e in editions}:
            raise ValueError("edition")
        credits = self.musicbrainz.release_credits(release)
        result.labels, result.people = credits.value
        result.stale = result.stale or credits.stale
        result.selected = release
        return result

    def profile(self, kind, identity, offset=0):
        if kind not in ("artist", "label") or not 0 <= offset <= MAX_OFFSET:
            raise ValueError("profile")
        return self.musicbrainz.profile(kind, mbid(identity), offset)

    def local(self, user, title, artist=""):
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 300 or len(artist) > 300:
            raise ValueError("search")
        # Recherche limitée aux résultats autorisés pour cette personne. Pas de cache public de disponibilité.
        found = self.library.search(user, title)
        title_key, artist_key = normalize(title), normalize(artist)
        albums = [a for a in found["albums"] if normalize(a["name"]) == title_key
                  and (not artist or normalize(a["artist"]) == artist_key)]
        # « À écouter » range un album sous son dossier : la carte doit porter la même identité.
        return {"albums": [dict(a, folderId=self.folders.folder_id(user, a["id"])) for a in albums],
                "songs": [s for s in found["songs"] if normalize(s["title"]) == title_key
                          and (not artist or normalize(s["artist"]) == artist_key)]}
