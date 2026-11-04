"""Base SQLite (pi-media.db) : une connexion par fil d'exécution, schéma versionné (PRAGMA user_version)."""
import contextlib
import sqlite3
import threading

from .schema import MIGRATIONS


class Database:
    def __init__(self, path, migrations=MIGRATIONS):
        self.path = path
        self.migrations = migrations          # chaque édition (Pi, PC) a son propre schéma
        self._local = threading.local()
        self._migrate_lock = threading.Lock()
        self.migrate()

    def connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=10, isolation_level=None, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")      # lectures pendant les écritures, robuste aux coupures
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def query(self, sql, params=()):
        return self.connection().execute(sql, params).fetchall()

    def one(self, sql, params=()):
        return self.connection().execute(sql, params).fetchone()

    def execute(self, sql, params=()):
        return self.connection().execute(sql, params)

    @contextlib.contextmanager
    def transaction(self):
        """Plusieurs écritures d'un bloc : tout ou rien (BEGIN IMMEDIATE : pas d'écriture concurrente entre-temps)."""
        conn = self.connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

    @property
    def version(self):
        return self.one("PRAGMA user_version")[0]

    def migrate(self):
        with self._migrate_lock:
            current = self.version
            for number, script in enumerate(self.migrations, start=1):
                if number > current:
                    with self.transaction() as conn:
                        for statement in (s.strip() for s in script.split(";")):
                            if statement:
                                conn.execute(statement)
                        conn.execute("PRAGMA user_version = %d" % number)

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
