"""Gravatar : la photo d'une adresse e-mail, lue par le serveur (les navigateurs ne contactent jamais Gravatar)."""
import hashlib
import urllib.error

from ...shared.providers.http import HttpClient, TooLarge

GRAVATAR = "https://gravatar.com/avatar/%s?s=256&d=404"     # d=404 : pas de dessin par défaut si l'adresse n'a pas de photo


class GravatarUnreachable(Exception):
    pass


def gravatar_url(email):
    """Adresse de la photo Gravatar : empreinte SHA-256 de l'adresse e-mail, sans espaces, en minuscules."""
    return GRAVATAR % hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


class Gravatar:
    """Lit une photo sur gravatar.com. None : l'adresse n'a pas de photo ; GravatarUnreachable : site injoignable ;
    TooLarge : photo plus grosse que max_bytes."""

    def __init__(self, http=None, max_bytes=300 * 1024):
        self.http = http or HttpClient(timeout=8, max_bytes=max_bytes)

    def fetch(self, email):
        try:
            return self.http.get_bytes(gravatar_url(email), accept="image/*")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise GravatarUnreachable() from error
        except TooLarge:
            raise
        except (OSError, ValueError) as error:
            raise GravatarUnreachable() from error
