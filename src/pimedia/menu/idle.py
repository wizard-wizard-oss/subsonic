"""Mise en veille de l'écran : horloge + météo après un temps sans toucher."""
import time

# applis musique : la veille peut passer dessus (comparaison sur le nom du programme)
SAVER_OVER_APPS = ("feishin", "flatpak", "chromium", "chromium-browser")


class IdleTimer:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.last = clock()

    def touch(self, *_event):
        self.last = self.clock()

    def idle_seconds(self):
        return self.clock() - self.last


def saver_decision(idle_seconds, limit, saver_visible, app_name, sees_all_touches):
    """None : rien à faire ; « menu » : veille sur le menu ; « over_app » : la veille passe devant l'appli
    (seulement pour une appli musique, et si l'on voit les touchers même hors du menu pour la réveiller)."""
    if saver_visible or idle_seconds <= limit:
        return None
    if app_name is None:
        return "menu"
    if sees_all_touches and app_name in SAVER_OVER_APPS:
        return "over_app"
    return None
