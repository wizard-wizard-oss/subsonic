"""Spotify : titre et image d'un morceau partagé, par l'oEmbed public (Spotify ne donne pas l'artiste)."""
import urllib.parse

from .http import HttpClient
from .metadata import ProviderUnavailable

OEMBED = "https://open.spotify.com/oembed?url="


class Spotify:
    def __init__(self, http=None):
        self.http = http or HttpClient(timeout=12)

    def track(self, path):
        """(titre, image) du morceau à l'adresse open.spotify.com/track/…, ou LookupError."""
        clean = urllib.parse.urlunsplit(("https", "open.spotify.com", path, "", ""))
        try:
            data = self.http.get_json(OEMBED + urllib.parse.quote(clean, safe=""))
        except (OSError, ValueError) as error:
            raise ProviderUnavailable("spotify.unavailable") from error
        if not isinstance(data, dict) or not data.get("title"):
            raise LookupError(path)
        return data["title"], data.get("thumbnail_url") or ""
