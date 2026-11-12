"""Historique SQLite des fichiers et archives reçus par le site."""
import json

from ..upload_entities import UploadEntry, UploadOrigin


class UploadRepository:
    def __init__(self, db):
        self.db = db

    def add(self, user, filename, byte_count, result, now, library_key=""):
        with self.db.transaction() as connection:
            saved = connection.execute(
                "INSERT INTO upload_history (user_id, username, filename, byte_count, file_count, skipped_count, "
                "placed, waiting, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user.id, user.username, filename, byte_count, result["files"], result["skipped"],
                 json.dumps(result["placed"], ensure_ascii=False), json.dumps(result["waiting"], ensure_ascii=False), now))
            for path in result["placed"]:
                connection.execute("INSERT INTO upload_albums (library_key, album_path, upload_id) VALUES (?, ?, ?) "
                                   "ON CONFLICT (library_key, album_path) DO UPDATE SET upload_id = excluded.upload_id", (library_key, path, saved.lastrowid))

    def origins(self, library_key):
        rows = self.db.query("SELECT a.album_path, h.username, h.uploaded_at FROM upload_albums a "
                             "JOIN upload_history h ON h.id = a.upload_id WHERE a.library_key = ?", (library_key,))
        return [UploadOrigin(row["album_path"], row["username"], row["uploaded_at"]) for row in rows]

    def page(self, before, limit):
        where, params = ("", ()) if before is None else (" WHERE id < ?", (before,))
        rows = self.db.query("SELECT * FROM upload_history" + where + " ORDER BY id DESC LIMIT ?", params + (limit,))
        return [UploadEntry.from_row(row) for row in rows]
