"""Identité Discogs choisie : accès local, persistance et actualisation du catalogue associé."""
import hashlib
import time

from .artist_entities import ArtistContext, ArtistDiscogsLink
from .discogs import discogs_id
from .folders import FolderNotFound
from .music_metadata import MusicSourceError


class ArtistDiscogsLinks:
    def __init__(self, repository, folders, indexes, discogs, catalogs, library_url, clock=time.time):
        self.repository, self.folders, self.indexes = repository, folders, indexes
        self.discogs, self.catalogs, self.clock = discogs, catalogs, clock
        self.library_key = hashlib.sha256(library_url.rstrip("/").encode("utf-8")).hexdigest()

    def _artist(self, user, identity):
        artist = self.folders.artist(user, identity)
        if not any(a["id"] == artist["id"] for group in self.indexes.for_user(user) for a in group["artists"]):
            raise FolderNotFound(identity)
        return artist

    def get(self, user, identity):
        return self.context(user, identity).link

    def context(self, user, identity):
        artist = self._artist(user, identity)
        link = self.repository.get(user.id, self.library_key, artist["id"])
        return ArtistContext(artist["id"], artist["name"], artist["id3Id"], link)

    def choose(self, user, identity, discogs_identity):
        artist = self._artist(user, identity)
        person = self.discogs.artist(discogs_id(discogs_identity)).identity
        if person.id != str(discogs_identity):
            raise MusicSourceError("discovery.unavailable")
        link = ArtistDiscogsLink(user.id, self.library_key, artist["id"], person.id, int(self.clock()))
        self.repository.save(link)
        return link

    def forget(self, user, identity):
        artist = self._artist(user, identity)
        self.repository.delete(user.id, self.library_key, artist["id"])

    def refresh(self, user, identity):
        link = self.get(user, identity)
        if link is None:
            raise ValueError("artist association")
        return self.catalogs.page("artist", link.discogs_artist_id, 1, refresh=True)
