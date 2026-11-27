"""Radar des sorties en base : sources de chaque compte, sorties synchronisées (partagées), labels des albums."""
import json
import time

from ..weekly_releases.entities import RadarRelease, RadarSource
from ..weekly_releases.limits import MANUAL

SOURCE_COLUMNS = "id, kind, identity, name, origin, hidden, via"
FULL_SYNC = "full"


class ReleaseSources:
    def __init__(self, db, clock=time.time):
        self.db, self.clock = db, clock

    def for_user(self, user_id, include_hidden=False):
        hidden = "" if include_hidden else " AND hidden = 0"
        rows = self.db.query("SELECT " + SOURCE_COLUMNS + " FROM release_sources WHERE user_id = ?" + hidden +
                             " ORDER BY kind, name COLLATE NOCASE, id", (user_id,))
        return [RadarSource.from_row(row) for row in rows]

    def get(self, user_id, kind, identity):
        row = self.db.one("SELECT " + SOURCE_COLUMNS + " FROM release_sources WHERE user_id = ? AND kind = ? "
                          "AND identity = ?", (user_id, kind, identity))
        return RadarSource.from_row(row) if row else None

    def add(self, user_id, kind, identity, name, origin, via=None):
        """Une source masquée ne revient que si la personne l'ajoute elle-même (origine MANUAL)."""
        self.db.execute(
            "INSERT INTO release_sources (user_id, kind, identity, name, origin, via, created_at) "
            "VALUES (:user, :kind, :identity, :name, :origin, :via, :now) ON CONFLICT (user_id, kind, identity) "
            "DO UPDATE SET name = excluded.name, "
            "via = CASE WHEN hidden = 0 THEN COALESCE(excluded.via, via) ELSE via END, "
            "origin = CASE WHEN excluded.origin = :manual THEN :manual ELSE origin END, "
            "hidden = CASE WHEN excluded.origin = :manual THEN 0 ELSE hidden END",
            {"user": user_id, "kind": kind, "identity": identity, "name": name, "origin": origin, "via": via,
             "now": int(self.clock()), "manual": MANUAL})
        return self.get(user_id, kind, identity)

    def hide(self, user_id, source_id):
        self.db.execute("UPDATE release_sources SET hidden = 1 WHERE id = ? AND user_id = ?", (source_id, user_id))

    def hide_identity(self, user_id, kind, identity):
        self.db.execute("UPDATE release_sources SET hidden = 1 WHERE user_id = ? AND kind = ? AND identity = ?",
                        (user_id, kind, identity))

    def prune(self, user_id, origin, kind, keep):
        """Retire les sources automatiques de cette origine et de ce type qui ne sont plus calculées ; une source
        masquée reste (elle mémorise le refus), une source manuelle n'est jamais touchée."""
        rows = self.db.query("SELECT id, identity FROM release_sources WHERE user_id = ? AND origin = ? AND kind = ? "
                             "AND hidden = 0", (user_id, origin, kind))
        for row in rows:
            if row["identity"] not in keep:
                self.db.execute("DELETE FROM release_sources WHERE id = ?", (row["id"],))

    def active_union(self):
        """Sources visibles d'au moins un compte, sans doublon : ce que la synchronisation interroge."""
        rows = self.db.query("SELECT kind, identity, MIN(name) AS name FROM release_sources WHERE hidden = 0 "
                             "GROUP BY kind, identity ORDER BY kind, identity")
        return [(row["kind"], row["identity"], row["name"]) for row in rows]


class RadarReleases:
    def __init__(self, db):
        self.db = db

    def save(self, kind, identity, releases, start, end):
        """Remplace ce que cette source a trouvé entre start et end (bornes comprises)."""
        with self.db.transaction() as connection:
            connection.execute(
                "DELETE FROM radar_release_sources WHERE source_kind = ? AND source_identity = ? AND release_id IN "
                "(SELECT id FROM radar_releases WHERE released_on BETWEEN ? AND ?)",
                (kind, identity, start.isoformat(), end.isoformat()))
            for release in releases:
                connection.execute(
                    "INSERT INTO radar_releases (id, title, artist, released_on, kind, tags, cover) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET title = excluded.title, "
                    "artist = excluded.artist, released_on = excluded.released_on, kind = excluded.kind, "
                    "tags = excluded.tags, cover = CASE WHEN excluded.cover != '' THEN excluded.cover ELSE cover END",
                    (release.id, release.title, release.artist, release.released_on.isoformat(), release.kind,
                     json.dumps(sorted(release.tags)), release.cover))
                connection.execute("INSERT OR IGNORE INTO radar_release_sources VALUES (?, ?, ?)",
                                   (release.id, kind, identity))
                for artist_id in release.artist_ids:
                    connection.execute("INSERT OR IGNORE INTO radar_release_artists VALUES (?, ?)",
                                       (release.id, artist_id))

    def for_sources(self, sources, start, end):
        """[(sortie, type de source, identité de source)] des sources données, sorties entre start et end."""
        rows = self.db.query(
            "SELECT r.*, l.source_kind, l.source_identity FROM radar_releases r "
            "JOIN radar_release_sources l ON l.release_id = r.id WHERE r.released_on BETWEEN ? AND ? "
            "ORDER BY r.released_on, r.id", (start.isoformat(), end.isoformat()))
        return [(RadarRelease.from_row(row), row["source_kind"], row["source_identity"]) for row in rows
                if (row["source_kind"], row["source_identity"]) in sources]

    def window(self, start, end):
        """Toutes les sorties gardées entre start et end, avec leurs artistes crédités (une semaine : quelques
        centaines de lignes)."""
        rows = self.db.query(
            "SELECT r.*, GROUP_CONCAT(a.artist_id) AS artist_ids FROM radar_releases r "
            "LEFT JOIN radar_release_artists a ON a.release_id = r.id WHERE r.released_on BETWEEN ? AND ? "
            "GROUP BY r.id ORDER BY r.released_on, r.id", (start.isoformat(), end.isoformat()))
        return [RadarRelease.from_row(row) for row in rows]

    def without_cover(self, start, end, limit):
        """Sorties de la période sans pochette connue et jamais cherchées ailleurs, les plus proches d'abord."""
        rows = self.db.query("SELECT * FROM radar_releases WHERE released_on BETWEEN ? AND ? AND cover = '' "
                             "AND cover_checked_at IS NULL ORDER BY released_on DESC, id LIMIT ?",
                             (start.isoformat(), end.isoformat(), limit))
        return [RadarRelease.from_row(row) for row in rows]

    def set_cover(self, release_id, cover, at):
        self.db.execute("UPDATE radar_releases SET cover = CASE WHEN ? != '' THEN ? ELSE cover END, "
                        "cover_checked_at = ? WHERE id = ?", (cover, cover, int(at), release_id))

    def purge(self, before):
        self.db.execute("DELETE FROM radar_releases WHERE released_on < ?", (before.isoformat(),))

    def mark_synced(self, kind, identity, at):
        self.db.execute("INSERT INTO radar_sync (source_kind, source_identity, synced_at) VALUES (?, ?, ?) "
                        "ON CONFLICT DO UPDATE SET synced_at = excluded.synced_at", (kind, identity, int(at)))

    def mark_failed(self, kind, identity, at):
        self.db.execute("INSERT INTO radar_sync (source_kind, source_identity, failed_at) VALUES (?, ?, ?) "
                        "ON CONFLICT DO UPDATE SET failed_at = excluded.failed_at", (kind, identity, int(at)))

    def past_synced_at(self, kind, identity):
        row = self.db.one("SELECT past_synced_at FROM radar_sync WHERE source_kind = ? AND source_identity = ?",
                          (kind, identity))
        return row["past_synced_at"] if row else None

    def mark_past_synced(self, kind, identity, at):
        self.db.execute("INSERT INTO radar_sync (source_kind, source_identity, past_synced_at) VALUES (?, ?, ?) "
                        "ON CONFLICT DO UPDATE SET past_synced_at = excluded.past_synced_at", (kind, identity, int(at)))

    def synced_at(self, kind, identity):
        row = self.db.one("SELECT synced_at FROM radar_sync WHERE source_kind = ? AND source_identity = ?",
                          (kind, identity))
        return row["synced_at"] if row else None

    def failing_since(self, before):
        """Sources dont le dernier essai a échoué, au plus tard à « before » (secondes)."""
        rows = self.db.query("SELECT source_kind, source_identity FROM radar_sync WHERE failed_at <= ? "
                             "AND (synced_at IS NULL OR failed_at > synced_at)", (int(before),))
        return {(row["source_kind"], row["source_identity"]) for row in rows}

    def last_synced(self, keys):
        """Synchronisation réussie la plus récente parmi ces sources (None si aucune)."""
        rows = self.db.query("SELECT source_kind, source_identity, synced_at FROM radar_sync "
                             "WHERE synced_at IS NOT NULL")
        found = [row["synced_at"] for row in rows if (row["source_kind"], row["source_identity"]) in keys]
        return max(found) if found else None

    def oldest_first(self, union):
        """Les sources jamais synchronisées d'abord, puis de la plus ancienne synchronisation à la plus récente."""
        synced = {(row["source_kind"], row["source_identity"]): row["synced_at"] or 0
                  for row in self.db.query("SELECT * FROM radar_sync")}
        return sorted(union, key=lambda source: synced.get(source[:2], 0))

    def mark_full_sync(self, at):
        self.mark_run(FULL_SYNC, at)

    def last_full_sync(self):
        return self.run_at(FULL_SYNC)

    def mark_run(self, name, at):
        self.db.execute("INSERT INTO radar_runs (name, finished_at) VALUES (?, ?) ON CONFLICT DO UPDATE SET "
                        "finished_at = excluded.finished_at", (name, int(at)))

    def run_at(self, name):
        row = self.db.one("SELECT finished_at FROM radar_runs WHERE name = ?", (name,))
        return row["finished_at"] if row else None


class RadarProfiles:
    """Réglages d'un compte : d'où viennent ses styles proposés et dernière demande d'actualisation."""
    def __init__(self, db):
        self.db = db

    def _ensure(self, user_id):
        self.db.execute("INSERT OR IGNORE INTO radar_profiles (user_id) VALUES (?)", (user_id,))

    def basis(self, user_id):
        row = self.db.one("SELECT basis FROM radar_profiles WHERE user_id = ?", (user_id,))
        return row["basis"] if row else None

    def set_basis(self, user_id, basis):
        self._ensure(user_id)
        self.db.execute("UPDATE radar_profiles SET basis = ? WHERE user_id = ?", (basis, user_id))

    def refresh_requested_at(self, user_id):
        row = self.db.one("SELECT refresh_requested_at FROM radar_profiles WHERE user_id = ?", (user_id,))
        return row["refresh_requested_at"] if row else None

    def request_refresh(self, user_id, at):
        self._ensure(user_id)
        self.db.execute("UPDATE radar_profiles SET refresh_requested_at = ? WHERE user_id = ?", (int(at), user_id))


class ArtistResolutions:
    """MBID trouvé pour un nom d'artiste normalisé (artist_id vide : aucun ou plusieurs artistes de ce nom)."""
    def __init__(self, db):
        self.db = db

    def get(self, name_key):
        row = self.db.one("SELECT artist_id, resolved_at FROM artist_resolutions WHERE name_key = ?", (name_key,))
        return (row["artist_id"], row["resolved_at"]) if row else None

    def save(self, name_key, artist_id, at):
        self.db.execute("INSERT INTO artist_resolutions VALUES (?, ?, ?) ON CONFLICT (name_key) DO UPDATE SET "
                        "artist_id = excluded.artist_id, resolved_at = excluded.resolved_at",
                        (name_key, artist_id, int(at)))


class AlbumLabels:
    """Label d'un album de la bibliothèque, trouvé une fois dans MusicBrainz (label_id vide : rien trouvé)."""
    def __init__(self, db):
        self.db = db

    def get(self, album_id):
        row = self.db.one("SELECT label_id, label_name, release_id, looked_up_at FROM album_labels "
                          "WHERE album_id = ?", (album_id,))
        return dict(row) if row else None

    def save(self, album_id, label_id, label_name, release_id, at):
        self.db.execute("INSERT INTO album_labels VALUES (?, ?, ?, ?, ?) ON CONFLICT (album_id) DO UPDATE SET "
                        "label_id = excluded.label_id, label_name = excluded.label_name, "
                        "release_id = excluded.release_id, looked_up_at = excluded.looked_up_at",
                        (album_id, label_id, label_name, release_id, int(at)))
