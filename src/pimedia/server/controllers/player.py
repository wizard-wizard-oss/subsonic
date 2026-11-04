"""Lecture haute fidélité (écran du Pi) : la page pilote mpv comme un élément audio."""
import shutil

from ..playback import MpvError
from ..transport import Reply

CSRF_VALUE = "pm"


class PlayerController:
    def __init__(self, player):
        self.player = player

    def state(self, request):
        state = self.player.state()
        state["available"] = bool(shutil.which("mpv")) or self.player.mpv.command[0] != "mpv"
        return Reply.json(state)

    def command(self, request):
        if request.header("X-Requested-With") != CSRF_VALUE:
            return Reply.json({"error": "refus"}, 403)
        body = request.json_body(limit=8192)
        action = body.get("action")
        handlers = {
            "load": lambda: self.player.load(str(body.get("url", ""))),
            "preload": lambda: self.player.preload(str(body.get("url", ""))),
            "play": lambda: self.player.pause(False),
            "pause": lambda: self.player.pause(True),
            "seek": lambda: self.player.seek(float(body.get("value", 0))),
            "volume": lambda: self.player.volume(float(body.get("value", 100))),
            "stop": self.player.stop,
            "enable": lambda: self.player.set_enabled(bool(body.get("value"))),
        }
        if action not in handlers:
            return Reply.json({"error": "commande inconnue"}, 400)
        try:
            handlers[action]()
        except (ValueError, TypeError) as error:
            return Reply.json({"error": str(error)}, 400)
        except MpvError as error:
            return Reply.json({"error": "Lecteur haute fidélité indisponible : " + str(error)}, 503)
        return Reply.json(self.player.state())
