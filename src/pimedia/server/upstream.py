"""Accès HTTP au serveur Subsonic."""
import hashlib
import secrets
import urllib.error
import urllib.parse
import urllib.request

from .constants import API_VERSION, AUTH_PARAMS, BINARY_ENDPOINTS, CLIENT_NAME


class NotConfigured(Exception):
    """Aucun serveur Subsonic ou aucun utilisateur configuré : impossible d'appeler Subsonic."""


def make_token(password):
    """Jeton d'authentification Subsonic : (sel, md5(mot de passe + sel))."""
    salt = secrets.token_hex(8)
    return salt, hashlib.md5((password + salt).encode()).hexdigest()


class SubsonicClient:
    def __init__(self, config):
        self.config = config

    # --- identité : le compte Subsonic du .env ---
    def credentials(self):
        """(utilisateur, sel, jeton) pour la requête."""
        user, password = self.config.get("subsonic_user", ""), self.config.get("subsonic_pass", "")
        if not user:
            raise NotConfigured()
        salt, token = make_token(password)
        return user, salt, token

    # --- requêtes ---
    def build_url(self, endpoint, params, credentials):
        user, salt, token = credentials
        items = [(k, v) for k, v in params if k not in AUTH_PARAMS and not k.startswith("_")]
        items += [("u", user), ("t", token), ("s", salt), ("v", API_VERSION), ("c", CLIENT_NAME)]
        if endpoint not in BINARY_ENDPOINTS and "f" not in dict(items):
            items.append(("f", "json"))
        return "%s/rest/%s.view?%s" % (self.config.subsonic_url, endpoint, urllib.parse.urlencode(items))

    def open(self, endpoint, params, headers=None, timeout=30):
        """Ouvre une réponse Subsonic (une réponse d'erreur HTTP est retournée comme les autres)."""
        if not self.config.subsonic_url:
            raise NotConfigured()
        request = urllib.request.Request(self.build_url(endpoint, params, self.credentials()))
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            return error

    def trigger_scan(self):
        """Demande à Subsonic de scanner sa bibliothèque (réservé parfois aux administrateurs)."""
        try:
            response = self.open("startScan", [], timeout=30)
            response.read()
            response.close()
        except Exception:
            pass
