"""Réglages de chaque utilisateur, avec leurs valeurs permises (une valeur inconnue est refusée)."""

CHOICES = {
    "sidebar": ("pinned", "hover", "hidden"),       # barre des artistes : fixe, au survol du bord gauche, masquée
    "sidebar_width": (200, 240, 280, 320),
    "sidebar_tab": ("artists", "playlists"),        # onglet affiché dans la barre de gauche
    "density": ("comfortable", "compact"),
    "chat_panel": ("open", "closed"),               # salon à droite
    "album_grid": ("large", "small"),
    "notify_mentions": (True, False),               # notification du navigateur quand on me mentionne
}
DEFAULTS = {"sidebar": "pinned", "sidebar_width": 240, "density": "comfortable", "chat_panel": "open",
            "album_grid": "large", "notify_mentions": True,
            "sidebar_tab": "artists"}


class InvalidPreference(ValueError):
    pass


class Preferences:
    def __init__(self, repository):
        self.repository = repository

    def of(self, user):
        values = dict(DEFAULTS)
        values.update({k: v for k, v in self.repository.all(user.id).items() if v in CHOICES.get(k, ())})
        return values

    def update(self, user, changes):
        if not isinstance(changes, dict) or not changes:
            raise InvalidPreference("vide")
        for key, value in changes.items():
            if key not in CHOICES or value not in CHOICES[key] or type(value) is not type(CHOICES[key][0]):
                raise InvalidPreference(key)
        self.repository.save(user.id, changes)
        return self.of(user)
