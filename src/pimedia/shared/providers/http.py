"""Seul transport HTTP des services externes : User-Agent, délai, taille maximale et adresses publiques."""
import ipaddress
import json
import socket
import urllib.parse
import urllib.request

from ..external import USER_AGENT

MAX_BYTES = 8 * 1024 * 1024


class TooLarge(ValueError):
    """Réponse plus grosse que la taille maximale du client."""


class NotPublic(ValueError):
    """Adresse (ou redirection) qui n'est pas en http(s) vers des adresses publiques."""


def is_public_host(host, resolve=socket.getaddrinfo):
    """Le nom ne désigne que des adresses publiques (ni privée, ni boucle locale, ni lien local, ni réservée)."""
    try:
        addresses = {ipaddress.ip_address(info[4][0]) for info in resolve(host, None)}
    except (OSError, ValueError):
        return False
    return bool(addresses) and all(a.is_global and not a.is_multicast for a in addresses)


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Chaque redirection est vérifiée comme l'adresse de départ."""

    def __init__(self, check):
        self.check = check

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpClient:
    def __init__(self, opener=urllib.request.urlopen, timeout=10, max_bytes=MAX_BYTES, resolve=socket.getaddrinfo):
        self.opener, self.timeout, self.max_bytes, self.resolve = opener, timeout, max_bytes, resolve

    def _read(self, url, headers, accept, opener=None):
        request = urllib.request.Request(url, headers=dict(headers or {}, **{"User-Agent": USER_AGENT, "Accept": accept}))
        with (opener or self.opener)(request, timeout=self.timeout) as response:
            body = response.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise TooLarge("Response too large")
            return body, response.headers.get_content_type()

    def get_json(self, url, headers=None):
        body, _ = self._read(url, headers, "application/json")
        return json.loads(body.decode("utf-8", "replace"))

    def get_text(self, url, headers=None):
        body, content_type = self._read(url, headers, "text/plain")
        if content_type != "text/plain":
            raise ValueError("Expected plain text")
        return body.decode("utf-8")

    def check_public(self, url):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or not is_public_host(parts.hostname, self.resolve):
            raise NotPublic("Not a public http(s) address")

    def public_redirects(self):
        return _PublicRedirects(self.check_public)

    def final_url(self, url, headers=None):
        """Adresse atteinte après les redirections (liens courts), sans lire la réponse."""
        request = urllib.request.Request(url, headers=dict(headers or {}, **{"User-Agent": USER_AGENT}))
        with self.opener(request, timeout=self.timeout) as response:
            return response.geturl()

    def get_bytes(self, url, headers=None, accept="*/*", public_only=False):
        """Octets d'une adresse ; avec public_only, l'adresse et chaque redirection doivent être publiques."""
        if not public_only:
            return self._read(url, headers, accept)[0]
        self.check_public(url)
        opener = urllib.request.build_opener(self.public_redirects()).open
        return self._read(url, headers, accept, opener)[0]
