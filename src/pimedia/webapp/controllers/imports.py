"""Import d'une playlist venue d'ailleurs : lire (lien ou fichier), retrouver par lots, créer."""
from ..entities import ImportedTrack
from ..import_readers import ImportFailed, NeedsChoice, read_file
from .base import ok
from .library import item_id

MATCH_BATCH = 25                     # titres cherchés dans la bibliothèque par demande
YOUTUBE_BATCH = 5                    # titres cherchés sur YouTube par demande
MAX_ENTRIES = 1000


def tracks(value, limit):
    if not isinstance(value, list) or not value or len(value) > limit:
        raise ImportFailed("request.invalid")
    return [ImportedTrack.from_api(t) for t in value]


def entries(value):
    """[{"songId": id} | {"item": titre d'ailleurs}], dans l'ordre de la playlist."""
    def valid(entry):
        if not isinstance(entry, dict) or len(entry) != 1:
            return None
        if "songId" in entry:
            return {"songId": item_id(entry["songId"])}
        return entry if isinstance(entry.get("item"), dict) else None
    checked = [valid(e) for e in value] if isinstance(value, list) and len(value) <= MAX_ENTRIES else [None]
    if None in checked:
        raise ImportFailed("request.invalid")
    return checked


class ImportController:
    def __init__(self, imports):
        self.imports = imports

    def read(self, request, user, body):
        """{link} (Deezer) ou {name, content, playlist ?} (fichier lu par la page) -> {name, tracks}, ou
        {choose : [{index, name, count}]} quand le fichier contient plusieurs playlists."""
        if isinstance(body.get("link"), str) and body["link"].strip():
            name, found = self.imports.reader.read(body["link"])
        elif isinstance(body.get("content"), str):
            playlist = body.get("playlist")
            if playlist is not None and (not isinstance(playlist, int) or isinstance(playlist, bool)):
                raise ImportFailed("request.invalid")
            try:
                name, found = read_file(body.get("name") if isinstance(body.get("name"), str) else "", body["content"],
                                        playlist)
            except NeedsChoice as choice:           # export de toute la bibliothèque : la personne choisit
                return ok({"choose": choice.playlists})
        else:
            raise ImportFailed("request.invalid")
        return ok({"name": name, "tracks": [t.to_api() for t in found]})

    def match(self, request, user, body):
        return ok({"results": self.imports.match_all(user, tracks(body.get("tracks"), MATCH_BATCH))})

    def youtube(self, request, user, body):
        return ok(self.imports.youtube_all(user, tracks(body.get("tracks"), YOUTUBE_BATCH)))

    def create(self, request, user, body):
        return ok({"playlist": self.imports.create(user, body.get("name"), entries(body.get("entries")))})
