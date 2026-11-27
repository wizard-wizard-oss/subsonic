"""Réglages de chaque utilisateur, avec leurs valeurs permises (une valeur inconnue est refusée)."""

SONG_COLUMNS = ("track", "artist", "album", "genre", "year", "bitrate", "duration", "format", "size")
# Même matrice que Subsonic : navigation et file de lecture ont leurs propres choix.
SONG_ENABLED = {
    "browse": frozenset(SONG_COLUMNS) - {"format", "size"},
    "queue": frozenset(SONG_COLUMNS) - {"track", "format", "size"},
}
SONG_DEFAULTS = {context + "_" + column: column in enabled
                 for context, enabled in SONG_ENABLED.items() for column in SONG_COLUMNS}

CHOICES = {
    "sidebar": ("pinned", "hover", "hidden"),       # barre des artistes : fixe, au survol du bord gauche, masquée
    "sidebar_width": (200, 240, 280, 320),
    "sidebar_tab": ("artists", "playlists"),        # onglet affiché dans la barre de gauche
    "density": ("comfortable", "compact"),
    "chat_panel": ("open", "closed"),               # salon à droite
    "album_grid": ("large", "small"),
    "notify_mentions": (True, False),               # notification du navigateur quand on me mentionne
    "help_seen": (True, False),                     # la page Help a déjà été ouverte : le site ne la montre plus d'office
    **{key: (True, False) for key in SONG_DEFAULTS},
}
DEFAULTS = {"sidebar": "pinned", "sidebar_width": 240, "density": "comfortable", "chat_panel": "open",
            "album_grid": "large", "notify_mentions": True, "help_seen": False,
            "sidebar_tab": "artists", **SONG_DEFAULTS}


class InvalidPreference(ValueError):
    pass


def valid_preference(key, value):
    choices = CHOICES.get(key)
    return choices is not None and type(value) is type(choices[0]) and value in choices


class Preferences:
    def __init__(self, repository):
        self.repository = repository

    def of(self, user):
        values = dict(DEFAULTS)
        values.update({k: v for k, v in self.repository.all(user.id).items() if valid_preference(k, v)})
        return values

    def update(self, user, changes):
        if not isinstance(changes, dict) or not changes:
            raise InvalidPreference("vide")
        for key, value in changes.items():
            if not valid_preference(key, value):
                raise InvalidPreference(key)
        self.repository.save(user.id, changes)
        return self.of(user)
