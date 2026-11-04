"""File d'attente commune, côté écran du Pi (127.0.0.1)."""
from ..transport import Reply

CSRF_VALUE = "pm"


class QueueController:
    def __init__(self, service):
        self.service = service

    def state(self, request):
        return Reply.json(self.service.state())

    def save(self, request):
        """L'écran envoie sa file à chaque changement."""
        if request.header("X-Requested-With") != CSRF_VALUE:
            return Reply.json({"error": "refus"}, 403)
        try:
            return Reply.json(self.service.save_from_screen(request.json_body(limit=4 * 1024 * 1024)))
        except (ValueError, TypeError) as error:
            return Reply.json({"error": str(error)}, 400)

    def take(self, request):
        """L'écran prend les demandes d'ajout des téléphones."""
        if request.header("X-Requested-With") != CSRF_VALUE:
            return Reply.json({"error": "refus"}, 403)
        return Reply.json({"requests": self.service.take_for_screen()})
