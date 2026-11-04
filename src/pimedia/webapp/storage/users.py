"""Comptes (un par identifiant Subsonic) et sessions."""
import hashlib
import secrets
import time

from ..entities import User, roles_to_text


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


class UserRepository:
    def __init__(self, db):
        self.db = db

    def save_login(self, username, salt, token, roles, now=None):
        """Crée le compte à la première connexion, sinon met à jour le jeton et les droits. Renvoie l'utilisateur."""
        now = int(now or time.time())
        self.db.execute(
            "INSERT INTO users (username, subsonic_salt, subsonic_token, is_admin, roles, created_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (username) DO UPDATE SET subsonic_salt = excluded.subsonic_salt, "
            "subsonic_token = excluded.subsonic_token, is_admin = excluded.is_admin, roles = excluded.roles, "
            "last_seen_at = excluded.last_seen_at",
            (username, salt, token, int("admin" in roles), roles_to_text(roles), now, now))
        return self.by_name(username)

    def save_roles(self, user_id, roles):
        self.db.execute("UPDATE users SET roles = ?, is_admin = ? WHERE id = ?",
                        (roles_to_text(roles), int("admin" in roles), user_id))

    def get(self, user_id):
        row = self.db.one("SELECT * FROM users WHERE id = ?", (user_id,))
        return User.from_row(row) if row else None

    def by_name(self, username):
        row = self.db.one("SELECT * FROM users WHERE username = ?", (username,))
        return User.from_row(row) if row else None

    def by_names(self, usernames):
        """Comptes existants parmi ces noms (insensible à la casse)."""
        names = list({n.lower() for n in usernames})[:20]
        if not names:
            return []
        rows = self.db.query("SELECT * FROM users WHERE lower(username) IN (%s)" % ",".join("?" * len(names)), names)
        return [User.from_row(r) for r in rows]

    def by_priority(self):
        """Comptes pour parler à Subsonic au nom du site (préchauffage) : administrateurs, puis les plus récents."""
        return [User.from_row(r) for r in self.db.query("SELECT * FROM users ORDER BY is_admin DESC, last_seen_at DESC")]

    def usernames(self):
        return [r["username"] for r in self.db.query("SELECT username FROM users ORDER BY username COLLATE NOCASE")]

    def touch(self, user_id, now=None):
        self.db.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (int(now or time.time()), user_id))


class SessionRepository:
    def __init__(self, db, days=30):
        self.db = db
        self.days = days

    @property
    def max_age(self):
        return self.days * 86400

    def create(self, user_id, now=None):
        """Renvoie le jeton à mettre dans le cookie (seul son empreinte est gardée)."""
        now = int(now or time.time())
        token = secrets.token_urlsafe(32)
        self.db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        self.db.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                        (hash_token(token), user_id, now, now + self.max_age))
        return token

    def user_id(self, token, now=None):
        if not token:
            return None
        row = self.db.one("SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
                          (hash_token(token), int(now or time.time())))
        return row["user_id"] if row else None

    def delete(self, token):
        if token:
            self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))

    def delete_for_user(self, user_id):
        self.db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
