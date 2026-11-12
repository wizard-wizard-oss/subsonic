"""Visuels d'artistes indépendants de la biographie, depuis des identités et des sources connues."""
import urllib.parse

from .artist_entities import ArtistImage
from .lastfm import LASTFM_BLANK
from .library import TtlCache
from .music_metadata import MusicSourceError
from .subsonic import Credentials, SubsonicError, SubsonicUnreachable

IMAGE_HOSTS = frozenset(("lastfm-img.freetls.fastly.net", "lastfm.freetls.fastly.net",
                         "upload.wikimedia.org", "thumb.wikimedia.org"))


def public_image(value):
    value = str(value or "")
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return ""
    return value if (len(value) <= 4096 and parsed.scheme == "https" and parsed.hostname in IMAGE_HOSTS
                     and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                     and LASTFM_BLANK not in value) else ""


class ArtistPortraits:
    def __init__(self, links, discogs, subsonic, wikipedia, cache=None):
        self.links, self.discogs, self.subsonic, self.wikipedia = links, discogs, subsonic, wikipedia
        self.cache = cache or TtlCache(3600)

    def get(self, user, identity):
        artist = self.links.context(user, identity)
        key = (user.id, artist.id, artist.link.discogs_artist_id if artist.link else "")
        return self.cache.get(key, lambda: self._find(user, artist))

    def _find(self, user, artist):
        link = artist.link
        person = self._discogs(link)
        if person and person.image:
            return ArtistImage(person.image, "discogs", "https://www.discogs.com/artist/" + person.identity.id)
        image = self._subsonic(user, artist.id3_id)
        if image.image_url:
            return image
        if link:
            return self._linked_wikipedia(person.wikipedia_url) if person and person.wikipedia_url else ArtistImage()
        return self._wikipedia(artist.name)

    def _discogs(self, link):
        try:
            return self.discogs.artist(link.discogs_artist_id) if link else None
        except MusicSourceError:
            return None

    def _subsonic(self, user, identity):
        if not identity:
            return ArtistImage()
        try:
            info = self.subsonic.call(Credentials.of(user), "getArtistInfo2", [("id", identity)]).get("artistInfo2") or {}
        except (SubsonicError, SubsonicUnreachable):
            return ArtistImage()
        url = next((url for key in ("largeImageUrl", "mediumImageUrl", "smallImageUrl")
                    if (url := public_image(info.get(key)))), "")
        return ArtistImage(url, "subsonic") if url else ArtistImage()

    def _linked_wikipedia(self, url):
        parsed = urllib.parse.urlsplit(url)
        return self._wikipedia(urllib.parse.unquote(parsed.path[len("/wiki/"):]), parsed.hostname.split(".")[0])

    def _wikipedia(self, name, language=None):
        for lang in (language,) if language else self.wikipedia.LANGUAGES:
            page = self.wikipedia.artist_page(name, lang)
            url = public_image((page.get("thumbnail") or {}).get("source"))
            if url:
                return ArtistImage(url, "wikipedia", "https://" + lang + ".wikipedia.org/wiki/" +
                                   urllib.parse.quote(name.replace(" ", "_"), safe=""))
        return ArtistImage()
