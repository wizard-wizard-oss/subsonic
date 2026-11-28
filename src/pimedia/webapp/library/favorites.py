"""Réunion des favoris par dossiers et par tags, sans confondre leurs identifiants."""
from dataclasses import dataclass
from datetime import datetime, timezone

from ..subsonic import Credentials
from .catalog import PAGE_SIZE, album_card, song_row, text, visible
from .folders import PREFIX, FolderNotFound, folder_ref, is_folder

PORTRAIT_REQUESTS = 3


@dataclass
class FavoriteState:
    starred: bool

    def to_api(self):
        return {"starred": self.starred}


@dataclass
class FavoriteCategoryPage:
    total: int
    has_more: bool

    def to_api(self):
        return {"total": self.total, "hasMore": self.has_more}


@dataclass
class FavoritePagination:
    artists: FavoriteCategoryPage
    albums: FavoriteCategoryPage
    songs: FavoriteCategoryPage

    @property
    def has_more(self):
        return any(section.has_more for section in (self.artists, self.albums, self.songs))

    def to_api(self):
        return {"artists": self.artists.to_api(), "albums": self.albums.to_api(), "songs": self.songs.to_api()}


@dataclass
class FavoritesPage:
    artists: list
    albums: list
    songs: list
    page: int
    pagination: FavoritePagination

    @property
    def has_more(self):
        return self.pagination.has_more

    def to_api(self):
        return {"artists": self.artists, "albums": self.albums, "songs": self.songs,
                "page": self.page, "hasMore": self.has_more, "pagination": self.pagination.to_api(),
                "portraitParallelism": PORTRAIT_REQUESTS}


def unique(items):
    """Les identités sont déjà résolues ; les noms affichés ne servent jamais de clé."""
    return list({str(item["id"]): item for item in items}.values())


def _favorite_time(value):
    """Date ISO Subsonic ; une valeur absente ou invalide garde l'ordre stable après les dates connues."""
    try:
        parsed = datetime.fromisoformat(value)
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
    except (TypeError, ValueError, OverflowError):
        return float("-inf")


def _merge_albums(candidates):
    """Métadonnées de la dernière projection (tags), date de favori la plus récente des deux identités."""
    albums, dates = {}, {}
    for card, favorite in candidates:
        identity, added_at = str(card["id"]), _favorite_time(favorite)
        dates[identity] = max(dates[identity], added_at) if identity in dates else added_at
        albums[identity] = card
    return sorted(albums.values(), key=lambda album: dates[str(album["id"])], reverse=True)


class Favorites:
    def __init__(self, subsonic, library, folders):
        self.subsonic, self.library, self.folders = subsonic, library, folders

    def page(self, user, page=0):
        if not isinstance(page, int) or isinstance(page, bool) or page < 0:
            raise ValueError("page")
        # Subsonic ne propose aucun offset sur getStarred/getStarred2 : pagination après réunion.
        tagged = self._read(user, "getStarred2", "starred2")
        directories = self._read(user, "getStarred", "starred")
        artists = self._artists(user, tagged, directories)
        albums = self._albums(user, tagged, directories)
        # Comme les albums, les pistes gardent la projection par tags quand les deux catalogues les renvoient.
        songs = unique([song_row(s) for source in (directories, tagged) for s in visible(source.get("song"))])
        start, end = page * PAGE_SIZE, (page + 1) * PAGE_SIZE
        pagination = FavoritePagination(*(FavoriteCategoryPage(len(items), len(items) > end)
                                          for items in (artists, albums, songs)))
        return FavoritesPage(artists[start:end], self.library._with_site_data(user, albums[start:end]),
                             songs[start:end], page, pagination)

    def _read(self, user, endpoint, key):
        return self.subsonic.call(Credentials.of(user), endpoint).get(key) or {}

    def _artists(self, user, tagged, directories):
        artists = [{"id": folder_ref(a["id"]), "name": text(a.get("name"), "?")}
                   for a in visible(directories.get("artist"))]
        for artist in visible(tagged.get("artist")):
            artist_id = str(artist["id"])
            try:
                artist_id = self.folders.artist_folder_id(user, artist_id)
            except FolderNotFound:
                pass
            artists.append({"id": artist_id, "name": text(artist.get("name"), "?")})
        return unique(artists)

    def _albums(self, user, tagged, directories):
        candidates = []
        for raw in visible(directories.get("album")):
            card = album_card(raw)
            card["id"] = self.folders.album_id_for_folder(user, str(raw["id"])) or folder_ref(raw["id"])
            candidates.append((card, raw.get("starred")))
        candidates.extend((album_card(raw), raw.get("starred")) for raw in visible(tagged.get("album")))
        return _merge_albums(candidates)

    def set_favorite(self, user, kind, item_id, on):
        """Retirer un cœur retire ses deux identités ; ajouter conserve le choix ID3/dossier du site."""
        params = self._parameters(user, kind, item_id, on)
        self.subsonic.call(Credentials.of(user), "star" if on else "unstar", params)
        return FavoriteState(on)

    def _parameters(self, user, kind, item_id, on):
        key = {"album": "albumId", "artist": "artistId", "song": "id", "folder": "id"}[kind]
        if kind == "folder":
            if not is_folder(item_id):
                raise ValueError("dossier")
            item_id = item_id[len(PREFIX):]
        params = [(key, item_id)]
        if on:
            return params
        try:
            other = self._alternate_identity(user, kind, item_id)
        except FolderNotFound:
            other = None                     # le favori ID3 reste retirable même sans dossier résolu
        if other:
            params.append(other)
        return params

    def _alternate_identity(self, user, kind, item_id):
        if kind == "album":
            folder_id = self.folders.folder_id(user, item_id)
            return "id", folder_id[len(PREFIX):]
        if kind == "folder":
            artist_id = self.folders.artist_id_for_folder(user, item_id)
            if artist_id:
                return "artistId", artist_id
        if kind == "artist":
            return "id", self.folders.artist_folder_id(user, item_id)[len(PREFIX):]
        return None
