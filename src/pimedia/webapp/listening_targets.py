"""Resolve musical references using the existing Subsonic and Discogs services."""
from .discogs import discogs_id
from .listen_later_entities import ListeningTarget

KINDS = ("artist", "album")
SOURCES = ("subsonic", "discogs")


class ListenLaterError(ValueError):
    pass


def entry_id(value):
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError("entry id")
    return value


class ListeningTargets:
    def __init__(self, folders, discogs, library_key):
        self.folders, self.discogs, self.library_key = folders, discogs, library_key

    def key(self, kind, source, source_id):
        if kind not in KINDS or source not in SOURCES:
            raise ValueError("listening target")
        if not isinstance(source_id, str) or not 1 <= len(source_id) <= 100:
            raise ValueError("source id")
        if source == "discogs":
            source_id = discogs_id(source_id)
        return kind, source, self.library_key if source == "subsonic" else "", source_id

    def resolve(self, user, kind, source, source_id):
        kind, source, _, source_id = self.key(kind, source, source_id)
        if source == "discogs":
            if kind == "artist":
                person = self.discogs.artist(source_id)
                return ListeningTarget(kind, source, "", person.identity.id, person.identity.name,
                                       image_ref=person.image)
            release = self.discogs.release(source_id)
            return ListeningTarget(kind, source, "", release.id, release.title, release.artist, release.image)
        if kind == "artist":
            artist = self.folders.artist(user, source_id)
            return ListeningTarget(kind, source, self.library_key, artist["id"], artist["name"],
                                   image_ref=artist.get("coverId") or "")
        album = self.folders.album(user, source_id)
        return ListeningTarget(kind, source, self.library_key, album["folderId"], album["name"],
                               album["artist"], album.get("coverId") or "")
