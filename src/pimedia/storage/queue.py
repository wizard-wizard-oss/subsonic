"""File d'attente commune du Pi.

L'écran du Pi joue la file et en envoie une copie à chaque changement (snapshot) : elle est gardée en base,
retrouvée après un redémarrage, et visible des téléphones. Les téléphones, eux, déposent des demandes d'ajout
que l'écran prend et range dans sa file (après le titre en cours, ou à la fin)."""
import json
import time

from ..entities import QueueItem, QueueRequest, QueueSnapshot, Track

MAX_ITEMS = 2000
MAX_PENDING_REQUESTS = 50
MODES = ("next", "end")


class PlayQueue:
    def __init__(self, db):
        self.db = db

    # --- la file jouée par l'écran ---
    def snapshot(self):
        rows = self.db.query("SELECT * FROM queue_items ORDER BY position")
        state = self.db.one("SELECT current_item_id, version FROM queue_state WHERE id = 1")
        items = [QueueItem(r["id"], r["position"], Track(json.loads(r["track"])), r["added_by"], r["added_at"]) for r in rows]
        return QueueSnapshot(items, state["current_item_id"], state["version"])

    def replace(self, entries, current_index):
        """entries : [(Track, added_by)] dans l'ordre ; current_index : titre en cours (-1 : aucun). Renvoie la file."""
        entries = list(entries)[:MAX_ITEMS]
        now = int(time.time())
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM queue_items")
            current_id = None
            for position, (track, added_by) in enumerate(entries):
                cursor = conn.execute("INSERT INTO queue_items (position, track, added_by, added_at) VALUES (?, ?, ?, ?)",
                                      (position, json.dumps(track.fields, ensure_ascii=False), added_by or "screen", now))
                if position == current_index:
                    current_id = cursor.lastrowid
            conn.execute("UPDATE queue_state SET current_item_id = ?, version = version + 1 WHERE id = 1", (current_id,))
        return self.snapshot()

    # --- demandes des téléphones ---
    def request(self, track, mode, added_by):
        if mode not in MODES:
            raise ValueError("mode inconnu")
        with self.db.transaction() as conn:
            if conn.execute("SELECT COUNT(*) FROM queue_requests").fetchone()[0] >= MAX_PENDING_REQUESTS:
                raise ValueError("Trop de demandes en attente")
            cursor = conn.execute("INSERT INTO queue_requests (track, mode, added_by, requested_at) VALUES (?, ?, ?, ?)",
                                  (json.dumps(track.fields, ensure_ascii=False), mode, added_by, int(time.time())))
        return cursor.lastrowid

    def pending(self):
        rows = self.db.query("SELECT * FROM queue_requests ORDER BY id")
        return [QueueRequest(r["id"], Track(json.loads(r["track"])), r["mode"], r["added_by"]) for r in rows]

    def take_requests(self):
        """Demandes en attente, retirées de la base (l'écran les range dans sa file)."""
        with self.db.transaction() as conn:
            rows = conn.execute("SELECT * FROM queue_requests ORDER BY id").fetchall()
            conn.execute("DELETE FROM queue_requests WHERE id <= ?", (rows[-1]["id"] if rows else 0,))
        return [QueueRequest(r["id"], Track(json.loads(r["track"])), r["mode"], r["added_by"]) for r in rows]
