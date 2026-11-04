"""Réglages de chaque utilisateur (barre des artistes, densité…), validés par le service."""
import json


class PreferenceRepository:
    def __init__(self, db):
        self.db = db

    def all(self, user_id):
        return {r["key"]: json.loads(r["value"])
                for r in self.db.query("SELECT key, value FROM user_preferences WHERE user_id = ?", (user_id,))}

    def save(self, user_id, values):
        with self.db.transaction() as conn:
            for key, value in values.items():
                conn.execute("INSERT INTO user_preferences (user_id, key, value) VALUES (?, ?, ?) "
                             "ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value",
                             (user_id, key, json.dumps(value)))
