"""Playlists locales du Pi (mélange de titres Subsonic et d'ailleurs) et favoris des titres d'ailleurs."""
import json
import secrets
import time

from ..entities import Playlist, PlaylistSummary, Track

MAX_LISTS = 100
MAX_TRACKS = 500


class LocalPlaylists:
    def __init__(self, db):
        self.db = db

    # --- lecture ---
    def overview(self):
        rows = self.db.query("SELECT p.id, p.name, COUNT(t.track_id) AS count FROM local_playlists p "
                             "LEFT JOIN playlist_tracks t ON t.playlist_id = p.id GROUP BY p.id ORDER BY p.created_at, p.rowid")
        return [PlaylistSummary(r["id"], r["name"], r["count"]) for r in rows]

    def get(self, list_id):
        row = self._find(list_id)
        tracks = [Track(json.loads(r["track"])) for r in
                  self.db.query("SELECT track FROM playlist_tracks WHERE playlist_id = ? ORDER BY position", (list_id,))]
        return Playlist(row["id"], row["name"], row["created_at"], tracks)

    def _find(self, list_id):
        row = self.db.one("SELECT * FROM local_playlists WHERE id = ?", (list_id,))
        if row is None:
            raise KeyError("Playlist introuvable")
        return row

    # --- écriture ---
    def create(self, name, tracks=()):
        """tracks : entités Track (déjà validées)."""
        name = (name or "").strip()[:80]
        if not name:
            raise ValueError("Nom vide")
        cleaned = list(tracks)[:MAX_TRACKS]
        list_id = secrets.token_hex(6)
        with self.db.transaction() as conn:
            if conn.execute("SELECT COUNT(*) FROM local_playlists").fetchone()[0] >= MAX_LISTS:
                raise ValueError("Trop de playlists")
            conn.execute("INSERT INTO local_playlists (id, name, created_at) VALUES (?, ?, ?)", (list_id, name, int(time.time())))
            self._append(conn, list_id, cleaned, 0)
        return list_id

    def add(self, list_id, tracks):
        """Ajoute les titres (entités Track) absents de la playlist ; renvoie le nombre de titres ajoutés."""
        with self.db.transaction() as conn:
            self._find(list_id)
            known = {r[0] for r in conn.execute("SELECT track_id FROM playlist_tracks WHERE playlist_id = ?", (list_id,))}
            fresh, seen = [], set()
            for track in tracks:
                if track.id not in known and track.id not in seen:
                    fresh.append(track)
                    seen.add(track.id)
            count = len(known)
            if count + len(fresh) > MAX_TRACKS:
                raise ValueError("Playlist pleine")
            self._append(conn, list_id, fresh, count)
        return len(fresh)

    @staticmethod
    def _append(conn, list_id, tracks, start):
        conn.executemany("INSERT INTO playlist_tracks (playlist_id, position, track_id, track) VALUES (?, ?, ?, ?)",
                         [(list_id, start + i, t.id, json.dumps(t.fields, ensure_ascii=False)) for i, t in enumerate(tracks)])

    def remove(self, list_id, index):
        with self.db.transaction() as conn:
            self._find(list_id)
            if conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ? AND position = ?", (list_id, index)).rowcount == 0:
                raise ValueError("Position invalide")
            # positions décalées en deux temps : la clé (playlist, position) doit rester unique à chaque instant
            conn.execute("UPDATE playlist_tracks SET position = -(position - 1) WHERE playlist_id = ? AND position > ?", (list_id, index))
            conn.execute("UPDATE playlist_tracks SET position = -position WHERE playlist_id = ? AND position < 0", (list_id,))

    def delete(self, list_id):
        self.db.execute("DELETE FROM local_playlists WHERE id = ?", (list_id,))

    # --- favoris des titres d'ailleurs (YouTube, Jamendo) ---
    def favorites(self):
        return [Track(json.loads(r["track"])) for r in self.db.query("SELECT track FROM external_favorites ORDER BY added_at, rowid")]

    def toggle_favorite(self, track):
        """Ajoute le titre (entité Track) aux favoris, ou l'en retire s'il y est déjà. Renvoie True s'il est favori ensuite."""
        with self.db.transaction() as conn:
            if conn.execute("DELETE FROM external_favorites WHERE track_id = ?", (track.id,)).rowcount:
                return False
            if conn.execute("SELECT COUNT(*) FROM external_favorites").fetchone()[0] >= MAX_TRACKS:
                raise ValueError("Trop de favoris")
            conn.execute("INSERT INTO external_favorites (track_id, track, added_at) VALUES (?, ?, ?)",
                         (track.id, json.dumps(track.fields, ensure_ascii=False), int(time.time())))
        return True
