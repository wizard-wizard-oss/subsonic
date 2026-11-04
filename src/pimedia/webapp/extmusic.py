"""Musique d'ailleurs sur le site : Jamendo (musique libre, son direct) et YouTube (lecteur officiel intégré).
UNE clé par source, réglée dans le .env du site (pas de clé par personne : elle ne change ni les résultats ni la
publicité, seulement le quota). Recherche, versions originales seulement, vidéos lisibles et « autre version » :
le service du Pi, réutilisé tel quel. La recherche passe par YouTube Music, sans quota ; l'API officielle (environ
100 recherches par jour pour tout le site) ne sert plus que de repli, limitée pour tout le site. En plus ici :
recherches gardées en base (YouTube sans limite, relues tous les 30 jours), limite par personne (contre les abus et
pour que YouTube ne bloque pas le serveur), vidéos refusées gardées (avec le code d'erreur), vidéos réellement lues
mises en tête des résultats, et vidéos déjà trouvées retrouvées sans quota."""
import re
import threading
import time
from collections import deque

from ..server.extmusic.service import ExtMusicService
from ..server.extmusic.sources import JamendoSource, YouTubeSource
from ..server.extmusic.ytmusic import YouTubeMusicSearch
from ..server.podcasts.directories import DirectoryError, JsonHttp

YOUTUBE_SEARCHES_PER_HOUR = 120          # par personne ; YouTube Music n'a pas de quota
OFFICIAL_SEARCHES_PER_HOUR = 20          # pour tout le site, quand YouTube Music est en panne (100 unités chacune)
SITE = ""                                 # « personne » du budget commun à tout le site
KEPT_SECONDS = 90 * 86400             # recherche Jamendo réutilisée, vidéo refusée réessayée : 90 jours
RECHECK_SECONDS = 30 * 86400          # vidéo YouTube gardée : relue (ou oubliée) au bout de 30 jours, règle de YouTube
RECHECK_EVERY = 3600
VIDEO_ID = re.compile(r"^[\w-]{6,20}$")
# Codes du lecteur intégré qui ne disent rien de la vidéo : paramètre invalide (2), lecteur HTML5 (5), lecteur mal
# réglé chez nous, sans en-tête Referer (153), YouTube injoignable. Les autres (100 : supprimée, 101 / 150 :
# intégration interdite par son propriétaire) disent que CETTE vidéo ne se lira pas ici.
NOT_THE_VIDEO = {"2", "5", "153", "youtube-unreachable"}


class ExtMusicError(ValueError):
    """Demande impossible (clé de texte i18n)."""


class SearchBudget:
    """Au plus `limit` recherches (ou ajouts par lien) par personne sur une heure glissante ; error : clé de texte."""

    def __init__(self, limit, clock=time.time, error="ext.too_many_searches"):
        self.limit, self.clock, self.error = limit, clock, error
        self._calls = {}
        self._lock = threading.Lock()

    def spend(self, username):
        now = self.clock()
        with self._lock:
            calls = self._calls.setdefault(username, deque())
            while calls and now - calls[0] > 3600:
                calls.popleft()
            if len(calls) >= self.limit:
                raise ExtMusicError(self.error)
            calls.append(now)


class SearchMemory:
    """Recherches déjà faites, à la place du cache du service. Jamendo : résultats gardés 90 jours tels quels.
    YouTube : gardé sans limite, mais seulement la liste des vidéos ; leurs titres sont dans `videos`, relus tous
    les 30 jours. Une recherche dont toutes les vidéos ont disparu est refaite."""

    def __init__(self, recent, forever, videos):
        """recent, forever : ExtSearchRepository (90 jours, sans limite) ; videos : YouTubeVideoRepository."""
        self.recent, self.forever, self.videos = recent, forever, videos

    def get(self, key):
        if not key.startswith("youtube:"):
            return self.recent.get(key)
        ids = self.forever.get(key)
        if not ids:
            return ids
        if isinstance(ids[0], dict):                   # gardée avant la migration 9 : titres complets, à relire
            self.videos.remember(ids, checked_at=0)
            ids = [i["youtubeId"] for i in ids]
            self.forever.put(key, ids)
        tracks = self.videos.tracks(ids)
        if not tracks:
            return None
        if len(tracks) < len(ids):
            self.forever.put(key, [t["youtubeId"] for t in tracks])
        return tracks

    def put(self, key, items):
        if not key.startswith("youtube:"):
            self.recent.put(key, items)
            return
        self.videos.remember(items)
        self.forever.put(key, [i["youtubeId"] for i in items])


class ExternalMusic:
    def __init__(self, config, searches, videos, http=None, clock=time.time):
        """searches : SearchMemory ; videos : YouTubeVideoRepository (storage/youtube.py)."""
        settings = {"ext_jamendo_id": config.ext_jamendo_id, "ext_youtube_key": config.ext_youtube_key,
                    "ext_youtube_region": config.ext_youtube_region, "ext_jamendo_on": True, "ext_youtube_on": True,
                    "ext_studio_only": True}
        http = http or JsonHttp()
        self.official_budget = SearchBudget(OFFICIAL_SEARCHES_PER_HOUR, clock)
        youtube = YouTubeSource(http, settings, YouTubeMusicSearch(), lambda: self.official_budget.spend(SITE))
        self.service = ExtMusicService(settings, [JamendoSource(http, settings), youtube], None, videos)
        self.service.cache = searches          # en base : une recherche refaite (par n'importe qui) est gratuite
        self.youtube = self.service.sources["youtube"]
        self.videos = videos
        self.budget = SearchBudget(YOUTUBE_SEARCHES_PER_HOUR, clock)

    def status(self):
        """Sources utilisables (clé présente dans le .env) ; les clés ne sont jamais renvoyées."""
        return {name: self.service.enabled(name) for name in ("jamendo", "youtube")}

    def search(self, user, source, term):
        term = (term or "").strip()[:200]
        if source not in ("jamendo", "youtube") or not self.service.enabled(source):
            raise ExtMusicError("ext.disabled")
        if source == "youtube" and len(term) >= 2 and self.service.cache.get("youtube:" + term.lower()) is None:
            self.budget.spend(user.username)          # une recherche déjà faite (par n'importe qui) ne coûte rien
        try:
            items = self.service.search(source, term)["items"]
        except DirectoryError:
            raise ExtMusicError("ext.unreachable")
        return self._played_first(items) if source == "youtube" else items

    def known(self, term):
        """Vidéos déjà trouvées sur le site (par n'importe qui) qui répondent à ces mots : sans quota."""
        if not self.service.enabled("youtube"):
            return []
        return self._played_first(self.service._filtered(self.videos.find((term or "").strip()[:200])))

    def recheck(self, batches=20):
        """Relit les vidéos gardées depuis 30 jours (1 unité de quota par lot de 50) : titres mis à jour,
        vidéos supprimées, privées ou devenues illisibles oubliées. Renvoie le nombre de vidéos oubliées."""
        forgotten = 0
        for _ in range(batches):
            ids = self.videos.stale(RECHECK_SECONDS, 50)
            if not ids or not self.service.enabled("youtube"):
                break
            tracks, gone = self.youtube.recheck(ids)
            self.videos.remember(tracks)
            self.videos.forget(gone)
            forgotten += len(gone)
        return forgotten

    def run(self, every=RECHECK_EVERY):
        while True:
            try:
                self.recheck()
            except DirectoryError:
                pass                                   # YouTube injoignable ou quota épuisé : on réessaiera
            time.sleep(every)

    def _played_first(self, items):
        """Les vidéos déjà lues sur le site d'abord (les plus lues en tête) : on sait qu'elles marchent."""
        plays = self.videos.plays(i["youtubeId"] for i in items)
        items = [dict(i, playedHere=plays.get(i["youtubeId"], 0)) for i in items]
        return sorted(items, key=lambda i: -i["playedHere"])

    def alternative(self, user, video_id, title, artist="", code=""):
        """Autre vidéo du même titre quand le lecteur a refusé celle-ci ; None si rien de sûr. Une erreur qui ne
        tient pas à la vidéo (lecteur mal réglé, navigateur, YouTube injoignable) ne la marque pas refusée pour tout
        le site, et ne lance pas de recherche : une autre vidéo échouerait pareil."""
        if not self.service.enabled("youtube"):
            raise ExtMusicError("ext.disabled")
        self._video(video_id)
        if str(code or "") in NOT_THE_VIDEO:
            return None
        self.mark_unplayable(video_id, code)
        self.budget.spend(user.username)
        try:
            return self.service.alternative(video_id, str(title or "")[:300], str(artist or "")[:200])
        except DirectoryError:
            raise ExtMusicError("ext.unreachable")

    def mark_unplayable(self, video_id, code=""):
        """Vidéo refusée par le lecteur intégré (code d'erreur de YouTube gardé) : plus proposée à personne, sauf si
        l'erreur ne tient pas à la vidéo (NOT_THE_VIDEO)."""
        video_id = self._video(video_id)
        if str(code or "") not in NOT_THE_VIDEO:
            self.videos.add(video_id, str(code or ""))

    def mark_played(self, video_id):
        """Vidéo réellement lue sur le site : elle passera en tête des résultats, et n'est plus « refusée »."""
        self.videos.played(self._video(video_id))

    @staticmethod
    def _video(video_id):
        if not isinstance(video_id, str) or not VIDEO_ID.match(video_id):
            raise ExtMusicError("request.invalid")
        return video_id
