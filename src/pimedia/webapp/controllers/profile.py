"""Photos de profil (envoyée sur le site, sinon celle de Subsonic) et radios Internet de Subsonic."""
from ...server.transport import Reply, StreamReply
from .base import ok
from .library import item_id

AVATAR_BODY_LIMIT = 512 * 1024        # image de 300 Ko au plus, en base64


class ProfileController:
    def __init__(self, avatars, radios, subsonic_public_url=""):
        self.avatars = avatars
        self.radios = radios
        self.subsonic_public_url = subsonic_public_url

    # --- page « Mon compte » ---
    def account(self, request, user):
        """Photo (sa source), adresse e-mail du compte Subsonic (pour Gravatar), page Subsonic des réglages personnels
        (Last.fm, mot de passe : gérés par Subsonic)."""
        settings = self.subsonic_public_url + "/personalSettings.view" if self.subsonic_public_url else ""
        return ok(dict(self.avatars.account(user), subsonicSettings=settings))

    # --- photos de profil ---
    def avatar(self, request, user):
        image = self.avatars.image(user, request.param("user")[:100])
        if image is None:
            return Reply.not_found()
        mime, data = image
        return Reply(200, data, mime, {"Cache-Control": "private, max-age=3600"})

    def avatar_versions(self, request, user):
        return ok({"versions": self.avatars.versions()})

    def upload_avatar(self, request, user, body):
        return ok({"version": self.avatars.upload(user, body.get("image"))})

    def gravatar(self, request, user, body):
        return ok({"version": self.avatars.from_gravatar(user, body.get("email"))})

    def remove_avatar(self, request, user, body):
        self.avatars.remove(user)
        return ok()

    # --- radios Internet ---
    def stations(self, request, user):
        return ok({"stations": self.radios.stations(user)})

    def stream(self, request, user):
        upstream = self.radios.open_stream(user, item_id(request.param("id")))
        if upstream is None:
            return Reply.not_found()
        return StreamReply(upstream, 200)
