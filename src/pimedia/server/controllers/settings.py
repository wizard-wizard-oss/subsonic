"""Réglages de l'interface : classement de la bibliothèque (dossiers ou tags)."""
from ..transport import Reply


class SettingsController:
    def __init__(self, config, browse):
        self.config = config
        self.browse = browse

    def current(self):
        return {"browse_mode": self.browse.current()}

    def page(self, request):
        """GET /settings : sans paramètre, lit ; avec browse_mode=, change puis renvoie les réglages."""
        if request.param("browse_mode"):
            self.browse.set(request.param("browse_mode"))
        return Reply.json(self.current())
