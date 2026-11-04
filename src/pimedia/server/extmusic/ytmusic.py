"""Recherche YouTube par YouTube Music (bibliothèque non officielle ytmusicapi) : sans clé ni quota, et des résultats
propres (titre, artistes, album). Décision du 27/10/2026 : la recherche peut contourner l'API officielle, pas la
lecture (toujours le lecteur officiel). La bibliothèque peut casser quand YouTube change : toute erreur devient une
DirectoryError, et YouTubeSource se rabat alors sur l'API officielle. Sans ytmusicapi installé, même repli."""
from concurrent.futures import ThreadPoolExecutor

from ..podcasts.directories import DirectoryError

try:
    import requests
    from ytmusicapi import YTMusic
except ImportError:                     # Pi ou poste sans la bibliothèque : API officielle seulement
    YTMusic = None

TIMEOUT = 10
VIDEO_SLOTS = 6                         # places gardées aux vidéos (concerts, clips, titres absents des « titres »)


def music_track(item):
    """Un résultat YouTube Music (« titre » ou « vidéo »), au format commun de l'interface ; None sans vidéo."""
    video = item.get("videoId")
    if not video:
        return None
    # Les compteurs (« 1,9 Md lectures ») arrivent comme de faux artistes, sans identifiant.
    artists = [a["name"] for a in item.get("artists") or [] if a.get("id") and a.get("name")]
    return {"id": "yt-" + video, "youtubeId": video, "title": item.get("title") or "Sans titre",
            "artist": ", ".join(artists), "album": (item.get("album") or {}).get("name") or "",
            "duration": int(item.get("duration_seconds") or 0),
            # Les pochettes des « titres » sont sur googleusercontent.com, refusé par la page : vignette de la vidéo.
            "imageUrl": "https://i.ytimg.com/vi/%s/mqdefault.jpg" % video, "ext": "youtube"}


def mix(songs, videos, limit):
    """Les « titres » d'abord, mais quelques places pour les vidéos ; sans doublon, au plus `limit`."""
    picked = songs[:limit - VIDEO_SLOTS] + videos + songs[limit - VIDEO_SLOTS:]
    seen, result = set(), []
    for track in picked:
        if track["youtubeId"] not in seen:
            seen.add(track["youtubeId"])
            result.append(track)
    return result[:limit]


if YTMusic:
    class TimeoutSession(requests.Session):
        """ytmusicapi ne fixe aucun délai : une demande bloquée ne doit pas bloquer la page."""

        def request(self, *args, **kwargs):
            kwargs.setdefault("timeout", TIMEOUT)
            return super().request(*args, **kwargs)


class YouTubeMusicSearch:
    def __init__(self, client_factory=None):
        """client_factory(region) -> objet avec search(term, filter=, limit=) ; par défaut ytmusicapi."""
        self.client_factory = client_factory or self._ytmusic
        self._clients = {}

    @staticmethod
    def _ytmusic(region):
        if not YTMusic:
            raise DirectoryError("ytmusicapi n'est pas installé")
        return YTMusic(language="fr", location=region, requests_session=TimeoutSession())

    def search(self, term, limit, region):
        """« titres » et « vidéos » demandés en même temps (environ 0,4 s chacun), un client par recherche."""
        with ThreadPoolExecutor(2) as pool:
            songs, videos = pool.map(lambda kind: self._search(term, kind, limit, region), ("songs", "videos"))
        return mix(songs, videos, limit)

    def _search(self, term, kind, limit, region):
        try:
            key = (region, kind)
            client = self._clients.get(key) or self._clients.setdefault(key, self.client_factory(region))
            return self._tracks(client.search(term, filter=kind, limit=limit))
        except DirectoryError:
            raise
        except Exception as error:      # format changé, réseau, refus : on ne sait pas d'avance ce que lèvera la bibliothèque
            raise DirectoryError("YouTube Music : %s" % error.__class__.__name__) from error

    @staticmethod
    def _tracks(items):
        return [t for t in (music_track(i) for i in items or []) if t]
