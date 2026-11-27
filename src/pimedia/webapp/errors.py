"""Erreurs de droits du domaine, levées par les services et traduites en réponses HTTP par app.error_reply."""


class Unauthorized(Exception):
    pass


class Forbidden(Exception):
    pass


class MissingRight(Forbidden):
    """Le compte Subsonic n'a pas ce droit (télécharger, écouter, playlists, noter et commenter…)."""
