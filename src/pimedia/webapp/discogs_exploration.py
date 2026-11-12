"""Crédits d'un album accessible au compte : choix d'une édition Discogs exacte, jamais d'identité devinée."""
from .discogs import discogs_id
from .discogs_entities import DiscogsAlbumCredits


class DiscogsExploration:
    def __init__(self, discogs, folders):
        self.discogs, self.folders = discogs, folders

    def album(self, user, album_id, release=""):
        album = self.folders.album(user, album_id)
        editions = self.discogs.editions(album["artist"], album["name"])
        if not release:
            return DiscogsAlbumCredits(editions)
        release = discogs_id(release)
        if release not in {e.id for e in editions}:
            raise ValueError("edition")
        details = self.discogs.release(release)
        return DiscogsAlbumCredits(editions, release, details.labels, details.credits)
