"""Radios Internet enregistrées dans Subsonic. Le flux passe par le site : la page reste en HTTPS
et seules les adresses de la liste Subsonic sont relayées (rien d'autre ne peut être demandé)."""
import urllib.parse
import urllib.request

from .library import as_list
from .subsonic import Credentials


class Radios:
    def __init__(self, subsonic, opener=urllib.request.urlopen):
        self.subsonic = subsonic
        self.opener = opener

    def stations(self, user):
        raw = (self.subsonic.call(Credentials.of(user), "getInternetRadioStations").get("internetRadioStations") or {})
        return [{"id": str(s.get("id")), "name": s.get("name", "?"), "homePage": s.get("homePageUrl", "")}
                for s in as_list(raw.get("internetRadioStation"))
                if urllib.parse.urlsplit(s.get("streamUrl", "")).scheme in ("http", "https")]

    def open_stream(self, user, station_id):
        raw = (self.subsonic.call(Credentials.of(user), "getInternetRadioStations").get("internetRadioStations") or {})
        for station in as_list(raw.get("internetRadioStation")):
            url = station.get("streamUrl", "")
            if str(station.get("id")) == str(station_id) and urllib.parse.urlsplit(url).scheme in ("http", "https"):
                request = urllib.request.Request(url, headers={"User-Agent": "pi-media-web", "Icy-MetaData": "0"})
                return self.opener(request, timeout=20)
        return None
