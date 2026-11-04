"""Titres d'ailleurs gardés en base : favoris de chacun, et ceux placés dans les playlists Subsonic."""
import time

from ..entities import ExtFavorite, PlaylistExtTrack

# YouTube : titre, chaîne, image et durée viennent de youtube_videos (relus tous les 30 jours) ; une vidéo qui n'y est
# plus (supprimée, privée, devenue illisible) n'est pas montrée.
DESCRIBED = ("f.source, f.item_id, f.added_at, f.play_url, f.page_url, "
             "CASE WHEN f.source = 'youtube' THEN v.title ELSE f.title END AS title, "
             "CASE WHEN f.source = 'youtube' THEN v.artist ELSE f.artist END AS artist, "
             "CASE WHEN f.source = 'youtube' THEN v.image_url ELSE f.image_url END AS image_url, "
             "CASE WHEN f.source = 'youtube' THEN v.duration ELSE f.duration END AS duration ")
YOUTUBE_JOIN = "LEFT JOIN youtube_videos v ON f.source = 'youtube' AND v.video_id = f.item_id "
STILL_PLAYABLE = "(f.source != 'youtube' OR v.checked_at IS NOT NULL)"
SELECT = "SELECT " + DESCRIBED + "FROM ext_favorites f " + YOUTUBE_JOIN + "WHERE f.user_id = ? AND " + STILL_PLAYABLE
INSERTED_COLUMNS = "source, item_id, title, artist, image_url, duration, play_url, page_url, added_at"


def _values(source, track, now):
    """Colonnes d'un titre à garder : pour YouTube, seulement son identifiant (le reste est relu chez YouTube)."""
    if source == "youtube":
        return (source, str(track["itemId"]), "", "", "", 0, "", "", now)
    return (source, str(track["itemId"]), track.get("title") or "", track.get("artist") or "", track.get("imageUrl") or "",
            int(track.get("duration") or 0), track.get("playUrl") or "", track.get("pageUrl") or "", now)


class ExtFavoriteRepository:
    def __init__(self, db, clock=time.time):
        self.db, self.clock = db, clock

    def all(self, user_id):
        """Les derniers ajoutés d'abord ; une playlist importée garde son ordre."""
        return [ExtFavorite.from_row(r) for r in self.db.query(SELECT + " ORDER BY f.added_at DESC, f.rowid", (user_id,))]

    def count(self, user_id):
        return self.db.one("SELECT COUNT(*) FROM ext_favorites WHERE user_id = ?", (user_id,))[0]

    def add(self, user_id, source, tracks):
        """tracks : [{"itemId", "title", "artist", "imageUrl", "duration", "playUrl", "pageUrl"}] (pour YouTube,
        seul itemId compte). Un titre déjà en favori garde sa date. Renvoie le nombre de titres ajoutés."""
        added, now = 0, int(self.clock())
        with self.db.transaction() as conn:
            for t in tracks:
                cursor = conn.execute("INSERT OR IGNORE INTO ext_favorites (user_id, " + INSERTED_COLUMNS + ") "
                                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (user_id,) + _values(source, t, now))
                added += cursor.rowcount
        return added

    def remove(self, user_id, source, item_id):
        self.db.execute("DELETE FROM ext_favorites WHERE user_id = ? AND source = ? AND item_id = ?",
                        (user_id, source, str(item_id)))


class PlaylistExtRepository:
    """Titres d'ailleurs des playlists Subsonic, rangés par place (after_songs, place) puis par ordre d'ajout."""

    def __init__(self, db, clock=time.time):
        self.db, self.clock = db, clock

    def of_playlist(self, playlist_id):
        return [PlaylistExtTrack.from_row(r) for r in self.db.query(
            "SELECT f.id, f.after_songs, f.added_by, u.username AS added_by_name, " + DESCRIBED +
            "FROM playlist_ext_tracks f " + YOUTUBE_JOIN + "LEFT JOIN users u ON u.id = f.added_by "
            "WHERE f.playlist_id = ? AND " + STILL_PLAYABLE + " ORDER BY f.after_songs, f.place, f.id", (str(playlist_id),))]

    def counts(self):
        """{playlist: nombre de titres d'ailleurs} (vidéos YouTube oubliées comprises : simple indication)."""
        return {r["playlist_id"]: r["n"] for r in self.db.query(
            "SELECT playlist_id, COUNT(*) AS n FROM playlist_ext_tracks GROUP BY playlist_id")}

    def add(self, playlist_id, after_songs, tracks, user_id):
        """tracks : [(source, titre)] ; un titre déjà dans la playlist n'y est pas remis. Renvoie le nombre d'ajouts."""
        added, now = 0, int(self.clock())
        with self.db.transaction() as conn:
            last = conn.execute("SELECT COALESCE(MAX(place), 0) FROM playlist_ext_tracks WHERE playlist_id = ?",
                                (str(playlist_id),)).fetchone()[0]
            for n, (source, track) in enumerate(tracks, 1):         # après ceux déjà là, même remis en ordre
                cursor = conn.execute("INSERT OR IGNORE INTO playlist_ext_tracks (playlist_id, after_songs, place, "
                                      "added_by, " + INSERTED_COLUMNS + ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                      (str(playlist_id), int(after_songs), last + n, user_id) + _values(source, track, now))
                added += cursor.rowcount
        return added

    def added_by(self, playlist_id, row_ids):
        """{ligne: personne qui l'a ajoutée} pour les lignes de cette playlist."""
        ids = [int(i) for i in row_ids][:500]
        if not ids:
            return {}
        return {r["id"]: r["added_by"] for r in self.db.query(
            "SELECT id, added_by FROM playlist_ext_tracks WHERE playlist_id = ? AND id IN (%s)" % ",".join("?" * len(ids)),
            [str(playlist_id)] + ids)}

    def remove(self, playlist_id, row_ids):
        for row_id in row_ids:
            self.db.execute("DELETE FROM playlist_ext_tracks WHERE playlist_id = ? AND id = ?", (str(playlist_id), int(row_id)))

    def place(self, playlist_id, places):
        """places : [(ligne, nombre de titres Subsonic avant elle)], dans le nouvel ordre."""
        with self.db.transaction() as conn:
            for n, (row_id, after_songs) in enumerate(places, 1):
                conn.execute("UPDATE playlist_ext_tracks SET after_songs = ?, place = ? WHERE playlist_id = ? AND id = ?",
                             (int(after_songs), n, str(playlist_id), int(row_id)))

    def forget(self, playlist_id):
        self.db.execute("DELETE FROM playlist_ext_tracks WHERE playlist_id = ?", (str(playlist_id),))
