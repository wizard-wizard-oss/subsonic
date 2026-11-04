"""Historique des recherches."""
from ..transport import Reply

CSRF_VALUE = "pm"
ACTIONS = ("add", "remove", "clear")


class HistoryController:
    def __init__(self, history):
        self.history = history

    def entries(self, request):
        try:
            return Reply.json({"entries": self.history.entries(request.param("kind"))})
        except ValueError as error:
            return Reply.json({"error": str(error)}, 400)

    def change(self, request):
        """POST {kind, action: add|remove|clear, text}"""
        if request.header("X-Requested-With") != CSRF_VALUE:
            return Reply.json({"error": "refus"}, 403)
        try:
            body = request.json_body(limit=4096)
            action = body.get("action")
            if action not in ACTIONS:
                raise ValueError("action inconnue")
            kind = body.get("kind")
            if action == "clear":
                self.history.clear(kind)
            else:
                getattr(self.history, action)(kind, body.get("text", ""))
            return Reply.json({"entries": self.history.entries(kind)})
        except (ValueError, AttributeError) as error:
            return Reply.json({"error": str(error)}, 400)
