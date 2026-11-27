"""Resolve musical references using the existing Subsonic and Discogs services."""
from .providers.discogs import discogs_id
from .listen_later_entities import ListeningTarget

TARGET_TYPES = (("artist", "subsonic"), ("artist", "discogs"),
                ("album", "subsonic"), ("album", "discogs"), ("song", "subsonic"))


class ListenLaterError(ValueError):
    pass


def entry_id(value):
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError("entry id")
    return value


class ListeningTargets:
    def __init__(self, folders, discogs, library_key, library):
        self.folders, self.discogs, self.library_key = folders, discogs, library_key
        self.library = library

    def key(self, kind, source, source_id):
        if (kind, source) not in TARGET_TYPES:
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
        if kind == "song":
            song = self.library.song(user, source_id)
            return ListeningTarget(kind, source, self.library_key, song["id"], song["title"],
                                   song["artist"], song.get("coverId") or "")
        if kind == "artist":
            artist = self.folders.artist(user, source_id)
            return ListeningTarget(kind, source, self.library_key, artist["id"], artist["name"],
                                   image_ref=artist.get("coverId") or "")
        album = self.folders.album(user, source_id)
        return ListeningTarget(kind, source, self.library_key, album["folderId"], album["name"],
                               album["artist"], album.get("coverId") or "")
