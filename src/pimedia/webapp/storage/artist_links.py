"""Associations Discogs choisies par compte et artiste de la bibliothèque."""
from ..artist_entities import ArtistDiscogsLink


class ArtistLinkRepository:
    def __init__(self, db):
        self.db = db

    def get(self, user_id, library_key, artist_id):
        row = self.db.one("SELECT * FROM artist_discogs_links WHERE user_id = ? AND library_key = ? AND artist_id = ?",
                          (user_id, library_key, artist_id))
        return ArtistDiscogsLink(**dict(row)) if row else None

    def save(self, link):
        self.db.execute("INSERT INTO artist_discogs_links (user_id, library_key, artist_id, discogs_artist_id, selected_at) "
                        "VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT (user_id, library_key, artist_id) DO UPDATE SET "
                        "discogs_artist_id = excluded.discogs_artist_id, selected_at = excluded.selected_at",
                        (link.user_id, link.library_key, link.artist_id, link.discogs_artist_id, link.selected_at))

    def delete(self, user_id, library_key, artist_id):
        self.db.execute("DELETE FROM artist_discogs_links WHERE user_id = ? AND library_key = ? AND artist_id = ?",
                        (user_id, library_key, artist_id))
