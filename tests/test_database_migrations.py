"""Moteur de migrations : reconstruire une table ne perd pas les lignes qui en dépendent."""
import os
import sqlite3
import tempfile
import unittest

from pimedia.storage.database import Database
from pimedia.webapp.schema import MIGRATIONS

CREATE_PARENT_AND_CHILD = """
    CREATE TABLE parents (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
    CREATE TABLE children (id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL REFERENCES parents (id) ON DELETE CASCADE);
    INSERT INTO parents VALUES (1, 'parent');
    INSERT INTO children VALUES (1, 1)
"""
# Le modèle des migrations 20 et 21 : nouvelle table, copie, suppression de l'ancienne, renommage.
REBUILD_PARENT = """
    CREATE TABLE parents_new (id INTEGER PRIMARY KEY, name TEXT NOT NULL, note TEXT NOT NULL DEFAULT '');
    INSERT INTO parents_new (id, name) SELECT id, name FROM parents;
    DROP TABLE parents;
    ALTER TABLE parents_new RENAME TO parents
"""


def fill(db):
    db.execute("INSERT INTO users (username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
               "VALUES ('alice', 's', 't', 0, 0), ('bob', 's', 't', 0, 0)")
    db.execute("INSERT INTO recommendations (sender_id, recipient_id, kind, source, library_key, source_id, title, "
               "created_at) VALUES (1, 2, 'album', 'discogs', '', '1', 'Disque', 0)")
    db.execute("INSERT INTO recommendation_comments (recommendation_id, author_id, body, created_at, client_token) "
               "VALUES (1, 1, 'Écoute la face B', 0, 'jeton')")


class MigrationEngineTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "webapp.db")

    def tearDown(self):
        self.directory.cleanup()

    def migrate_with(self, *extra):
        db = Database(self.path, MIGRATIONS + list(extra))
        self.addCleanup(db.close)
        return db

    def test_rebuilding_a_parent_table_keeps_child_rows(self):
        self.migrate_with(CREATE_PARENT_AND_CHILD)
        db = self.migrate_with(CREATE_PARENT_AND_CHILD, REBUILD_PARENT)
        self.assertEqual(db.version, len(MIGRATIONS) + 2)
        self.assertEqual(db.one("SELECT COUNT(*) FROM children")[0], 1)
        self.assertEqual(db.one("PRAGMA foreign_keys")[0], 1)

    def test_migration_with_semicolon_in_literal(self):
        db = self.migrate_with("CREATE TABLE notes (text TEXT); INSERT INTO notes VALUES ('a;b')")
        self.assertEqual(db.one("SELECT text FROM notes")[0], "a;b")

    def test_broken_foreign_key_rolls_back_migration(self):
        fill(self.migrate_with())
        with self.assertRaisesRegex(RuntimeError, "migration %d" % (len(MIGRATIONS) + 1)):
            self.migrate_with("INSERT INTO recommendation_comments "
                              "(recommendation_id, author_id, body, created_at, client_token) "
                              "VALUES (99, 1, 'orphelin', 0, 'x')")
        connection = sqlite3.connect(self.path)
        self.addCleanup(connection.close)
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], len(MIGRATIONS))
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM recommendation_comments").fetchone()[0], 1)

    def test_all_migrations_give_the_same_schema(self):
        db = self.migrate_with()
        schema = sorted(tuple(row) for row in db.query(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
        reference = os.path.join(os.path.dirname(__file__), "data", "schema_v%d.sql" % len(MIGRATIONS))
        with open(reference, encoding="utf-8") as handle:
            self.assertEqual("\n".join(" | ".join(str(part) for part in row) for row in schema), handle.read().rstrip("\n"))


if __name__ == "__main__":
    unittest.main()
