"""Appels au serveur Subsonic au nom d'un utilisateur du site (son propre jeton : ses étoiles, ses favoris)."""
import json
import urllib.error
import urllib.parse
import urllib.request

from ..server.constants import API_VERSION
from ..server.upstream import make_token
from .entities import roles_of_subsonic

CLIENT_NAME = "pi-media-web"
BINARY = frozenset(("stream", "getCoverArt", "download"))
# Appels que Subsonic met longtemps à calculer sur une grosse bibliothèque (getArtists : 34 s sur music.foos.fr).
SLOW_TIMEOUT = 180


class SubsonicError(Exception):
    """Subsonic a répondu par une erreur (code 40 : identifiants refusés, 70 : introuvable…)."""

    def __init__(self, code, message=""):
        super().__init__(message or str(code))
        self.code = code


class SubsonicUnreachable(Exception):
    pass


class Credentials:
    """Identité pour Subsonic : nom + (sel, jeton). Le mot de passe n'est jamais gardé."""

    def __init__(self, username, salt, token):
        self.username, self.salt, self.token = username, salt, token

    @classmethod
    def from_password(cls, username, password):
        salt, token = make_token(password)
        return cls(username, salt, token)

    @classmethod
    def of(cls, user):
        return cls(user.username, user.subsonic_salt, user.subsonic_token)


class SubsonicServer:
    def __init__(self, base_url, timeout=20, opener=urllib.request.urlopen):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.opener = opener

    def query(self, endpoint, params, credentials):
        items = [(k, v) for k, v in params if v is not None]
        items += [("u", credentials.username), ("t", credentials.token), ("s", credentials.salt),
                  ("v", API_VERSION), ("c", CLIENT_NAME)]
        if endpoint not in BINARY:
            items.append(("f", "json"))
        return urllib.parse.urlencode(items)

    def url(self, endpoint, params, credentials):
        return "%s/rest/%s.view?%s" % (self.base_url, endpoint, self.query(endpoint, params, credentials))

    def call(self, credentials, endpoint, params=(), timeout=None, post=False):
        """Réponse JSON (contenu de « subsonic-response ») ; SubsonicError si Subsonic refuse.
        timeout : attente plus longue pour les appels lents (SLOW_TIMEOUT).
        post : paramètres envoyés dans le corps (formulaire), pour les longues listes de titres qu'une adresse ne
        contiendrait pas ; Subsonic les lit comme ceux de l'adresse (les applis de téléphone font ainsi)."""
        if not self.base_url:
            raise SubsonicUnreachable("adresse Subsonic non réglée")
        target = self.url(endpoint, list(params), credentials)
        if post:
            target = urllib.request.Request("%s/rest/%s.view" % (self.base_url, endpoint),
                                            data=self.query(endpoint, list(params), credentials).encode("ascii"))
        try:
            with self.opener(target, timeout=timeout or self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise SubsonicError(error.code, "HTTP %d" % error.code)
        except (OSError, ValueError) as error:
            raise SubsonicUnreachable(str(error))
        body = data.get("subsonic-response") or {}
        if body.get("status") != "ok":
            error = body.get("error") or {}
            raise SubsonicError(error.get("code", 0), error.get("message", ""))
        return body

    def open(self, credentials, endpoint, params=(), headers=None):
        """Réponse binaire (flux audio, pochette), à relayer par morceaux."""
        request = urllib.request.Request(self.url(endpoint, list(params), credentials))
        for name, value in (headers or {}).items():
            if value:
                request.add_header(name, value)
        try:
            return self.opener(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            return error
        except OSError as error:
            raise SubsonicUnreachable(str(error))

    # --- connexion ---
    def check_login(self, credentials):
        """(valide, droits). Un mauvais mot de passe donne (False, aucun droit)."""
        try:
            self.call(credentials, "ping")
        except SubsonicError as error:
            if error.code in (40, 41, 401):
                return False, frozenset()
            raise
        try:
            return True, self.roles(credentials)
        except SubsonicError:
            return True, frozenset(("stream",))

    def roles(self, credentials):
        """Droits du compte (getUser sur soi-même : permis à tous les comptes)."""
        return roles_of_subsonic(self.call(credentials, "getUser", [("username", credentials.username)]).get("user") or {})
