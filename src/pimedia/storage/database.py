"""Base SQLite (pi-media.db) : une connexion par fil d'exécution, schéma versionné (PRAGMA user_version)."""
import contextlib
import sqlite3
import threading

from .schema import MIGRATIONS


def statements(script):
    """Instructions complètes d'un script, au sens de SQLite (un « ; » dans un texte ne coupe pas)."""
    pending = ""
    for piece in script.split(";"):
        pending += piece + ";"
        if sqlite3.complete_statement(pending):
            statement = pending.rstrip()[:-1].strip()   # sans le « ; » final ni les blancs, comme avant
            if statement:
                yield statement
            pending = ""
    if pending.strip().rstrip(";").strip():
        yield pending.strip()


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
                    self._apply(number, script)

    def _apply(self, number, script):
        """Clés étrangères suspendues (hors transaction, seul moment où SQLite l'accepte) : reconstruire une table
        parente ne supprime pas ses lignes enfants. Les liens sont vérifiés avant de valider."""
        conn = self.connection()
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            with self.transaction():
                for statement in statements(script):
                    conn.execute(statement)
                if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise RuntimeError("migration %d : clé étrangère orpheline" % number)
                conn.execute("PRAGMA user_version = %d" % number)
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
