"""Cibles écoutées, décrites une seule fois et partagées par « À écouter » et les recommandations."""
COLUMNS = "t.kind, t.source, t.library_key, t.source_id, t.title, t.artist, t.image_ref"
IN_LIBRARY = "(t.source != 'subsonic' OR t.library_key = ?)"
BY_KEY = "SELECT id FROM listening_targets WHERE kind = ? AND source = ? AND library_key = ? AND source_id = ?"


def save_target(connection, target):
    """Identifiant de la cible ; sa description devient la plus récente reçue."""
    connection.execute(
        "INSERT INTO listening_targets (kind, source, library_key, source_id, title, artist, image_ref) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (kind, source, library_key, source_id) DO UPDATE SET "
        "title = excluded.title, artist = excluded.artist, image_ref = excluded.image_ref",
        target.key + (target.title, target.artist, target.image_ref))
    return connection.execute(BY_KEY, target.key).fetchone()[0]
