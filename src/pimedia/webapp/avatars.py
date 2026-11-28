"""Avatars : photo envoyée sur le site (ou copiée depuis Gravatar), sinon celle choisie dans Subsonic (getAvatar),
sinon rien (la page affiche alors l'initiale en couleur)."""
import base64
import hashlib
import re

from ..shared.images import image_type
from ..shared.providers.http import TooLarge
from .library.cache import TtlCache
from .providers.gravatar import Gravatar, GravatarUnreachable
from .subsonic import Credentials, SubsonicError, SubsonicUnreachable

MAX_BYTES = 300 * 1024
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidAvatar(ValueError):
    pass


class Avatars:
    def __init__(self, repository, users, subsonic, cache=None, gravatar=None):
        self.repository = repository
        self.users = users
        self.subsonic = subsonic
        self.cache = cache or TtlCache(3600)
        self.gravatar = gravatar or Gravatar(max_bytes=MAX_BYTES)

    def upload(self, user, data_url):
        """Image envoyée par la page (déjà réduite par le navigateur), en « data: » base64."""
        if not isinstance(data_url, str) or "," not in data_url:
            raise InvalidAvatar("avatar.bad_format")
        try:
            data = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        except ValueError:
            raise InvalidAvatar("avatar.bad_format")
        return self._save(user, data)

    def from_gravatar(self, user, email):
        """Copie la photo Gravatar de cette adresse (celle du compte Subsonic si vide). Une copie : un changement fait
        plus tard sur gravatar.com ne suit pas tout seul (on recommence). Les navigateurs ne contactent jamais Gravatar."""
        email = (email if isinstance(email, str) else "").strip() or self.email(user)
        if not email:
            raise InvalidAvatar("avatar.no_email")
        if len(email) > 254 or not EMAIL.match(email):
            raise InvalidAvatar("avatar.bad_email")
        try:
            data = self.gravatar.fetch(email)
        except GravatarUnreachable:
            raise InvalidAvatar("avatar.gravatar_unreachable")
        except TooLarge:
            raise InvalidAvatar("avatar.too_big")
        if data is None:
            raise InvalidAvatar("avatar.gravatar_none")
        return self._save(user, data)

    def _save(self, user, data):
        if len(data) > MAX_BYTES:
            raise InvalidAvatar("avatar.too_big")
        mime = image_type(data)
        if mime is None:
            raise InvalidAvatar("avatar.bad_type")
        return self.repository.save(user.id, mime, data)

    def remove(self, user):
        self.repository.delete(user.id)

    def email(self, user):
        """Adresse e-mail du compte Subsonic (getUser sur soi-même), vide si inconnue ou si Subsonic ne répond pas."""
        try:
            info = self.subsonic.call(Credentials.of(user), "getUser", [("username", user.username)]).get("user") or {}
        except (SubsonicError, SubsonicUnreachable):
            return ""
        return info.get("email") or ""

    def account(self, user):
        """Ce que la page « Mon compte » montre de la photo : d'où elle vient (« site », « subsonic » ou None)."""
        source = "site" if self.repository.get(user.id) else "subsonic" if self._subsonic_image(user) else None
        return {"source": source, "email": self.email(user)}

    def image(self, viewer, username):
        """(type, octets) ou None."""
        target = self.users.by_name(username or "")
        if target is None:
            return None
        own = self.repository.get(target.id)
        if own:
            return own[0], own[1]
        return self._subsonic_image(target)

    def _subsonic_image(self, target):
        return self.cache.get(("subsonic-avatar", target.username), lambda: self._from_subsonic(target))

    def _from_subsonic(self, target):
        try:
            response = self.subsonic.open(Credentials.of(target), "getAvatar", [("username", target.username)])
        except SubsonicUnreachable:
            return None
        try:
            mime = (response.headers.get("Content-Type") or "").split(";")[0]
            data = response.read(MAX_BYTES + 1)
        finally:
            response.close()
        if getattr(response, "status", 200) != 200 or not mime.startswith("image/") or len(data) > MAX_BYTES:
            return None
        return mime, data

    def versions(self):
        """{nom: version} de chaque personne qui a une photo (sur le site ou dans Subsonic) : la page ne demande
        l'image que pour elles, et la version change avec la photo (le navigateur recharge l'image)."""
        own = self.repository.versions()
        versions = {}
        for target in self.users.by_priority():
            if target.username in own:
                versions[target.username] = str(own[target.username])
            else:
                image = self._subsonic_image(target)
                if image:
                    versions[target.username] = "s" + hashlib.sha1(image[1]).hexdigest()[:10]
        return versions
