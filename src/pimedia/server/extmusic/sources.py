"""Musique « ailleurs » : Jamendo (musique libre, streaming direct) et YouTube (lecteur officiel intégré ; recherche par
YouTube Music, voir ytmusic.py, ou par l'API officielle)."""
import html
import re
import urllib.parse

from ..podcasts.directories import DirectoryError

JAMENDO_TRACKS = "https://api.jamendo.com/v3.0/tracks/"
YOUTUBE_SEARCH = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"          # 1 unité de quota pour 50 vidéos
YOUTUBE_PLAYLIST_ITEMS = "https://www.googleapis.com/youtube/v3/playlistItems"   # 1 unité par page de 50
MAX_RESULTS = 20


# ---------- fonctions pures ----------
def jamendo_track(item):
    """Un morceau Jamendo, au format commun de l'interface. None s'il n'a pas d'adresse de lecture."""
    if not item.get("audio") or not item.get("id"):
        return None
    return {"id": "jamendo-" + str(item["id"]), "title": item.get("name") or "Sans titre",
            "artist": item.get("artist_name") or "", "album": item.get("album_name") or "",
            "duration": int(item.get("duration") or 0), "streamUrl": item["audio"],
            "imageUrl": item.get("image") or item.get("album_image") or "", "ext": "jamendo"}


def clean_channel(name):
    """« Artiste - Topic » (chaînes automatiques de YouTube) -> « Artiste »."""
    return re.sub(r"\s*-\s*Topic$", "", name or "").strip()


# Versions qui ne sont pas l'enregistrement original : live, reprises, remix, karaoké…
# Prudence avec « live » : « Live Forever » ou « Oasis - Live Forever » sont de vrais titres.
ALTERNATE_VERSION = re.compile(
    r"[(\[][^)\]]*\b(live|tour|concert|session|cover|remix|acoustic|acoustique|instrumental|karaok[eé]|demo|unplugged)\b"
    r"|\blive\s+(at|from|in|on|à|au|aux|@)\b|\blive\s*\d{4}\b|\blive$"
    r"|\b(en concert|in concert|unplugged|karaok[eé]|nightcore|sped up|slowed|8d audio)\b"
    r"|\|\s*(live|cover|remix|karaok)", re.IGNORECASE)


def is_alternate_version(title):
    return bool(ALTERNATE_VERSION.search((title or "").strip()))


def song_parts(title, artist=""):
    """« Britney Spears - Toxic (Official HD Video) » -> ("Britney Spears", "Toxic") : de quoi chercher une autre version."""
    core = re.sub(r"[(\[][^)\]]*[)\]]", " ", title or "")            # parenthèses et crochets
    core = re.sub(r"\b(official|officiel|video|vidéo|clip|audio|lyrics?|paroles|hd|4k)\b", " ", core, flags=re.I)
    if " - " in core:
        artist, core = core.split(" - ", 1)
    return " ".join((artist or "").split()), " ".join(core.replace("|", " ").split())


def is_topic_channel(item):
    """Chaîne « Artiste - Topic » : version audio officielle générée par YouTube, presque toujours intégrable."""
    return ((item.get("snippet") or {}).get("channelTitle") or "").endswith("- Topic")


def topic_first(items):
    """Les chaînes « Topic » d'abord (l'ordre de YouTube est conservé dans chaque groupe) : les clips officiels
    des grands artistes interdisent souvent la lecture hors de YouTube."""
    return sorted(items, key=lambda item: not is_topic_channel(item))


def parse_iso_duration(text):
    """« PT3M25S » -> 205 secondes."""
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text or "")
    if not match:
        return 0
    days, hours, minutes, seconds = (int(x or 0) for x in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def playable_details(video, region):
    """Durée en secondes si la vidéo est lisible dans notre lecteur intégré depuis ce pays, sinon None.
    (Intégration interdite, vidéo non publique, ou bloquée dans le pays.)"""
    status = video.get("status") or {}
    if not status.get("embeddable") or status.get("privacyStatus") not in (None, "public", "unlisted"):
        return None
    restriction = (video.get("contentDetails") or {}).get("regionRestriction") or {}
    if region in (restriction.get("blocked") or []):
        return None
    if "allowed" in restriction and region not in restriction["allowed"]:
        return None
    return parse_iso_duration((video.get("contentDetails") or {}).get("duration"))


def youtube_track(item):
    video = (item.get("id") or {}).get("videoId")
    snippet = item.get("snippet") or {}
    if not video:
        return None
    thumbs = snippet.get("thumbnails") or {}
    image = (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
    return {"id": "yt-" + video, "youtubeId": video, "title": html.unescape(snippet.get("title") or "Sans titre"),
            "artist": clean_channel(html.unescape(snippet.get("channelTitle") or "")), "album": "",
            "duration": 0, "imageUrl": image, "ext": "youtube"}


def video_track(video, region):
    """Une vidéo relue par videos.list (snippet, status, contentDetails) ; None si elle n'est plus lisible ici."""
    duration = playable_details(video or {}, region)
    track = youtube_track({"id": {"videoId": video.get("id")}, "snippet": video.get("snippet")}) if duration is not None else None
    return dict(track, duration=duration) if track else None


# ---------- sources ----------
class JamendoSource:
    name = "jamendo"

    def __init__(self, http, config):
        self.http = http
        self.config = config

    @property
    def configured(self):
        return bool(self.config.get("ext_jamendo_id"))

    def search(self, term):
        query = urllib.parse.urlencode([
            ("client_id", self.config.get("ext_jamendo_id")), ("format", "json"), ("limit", MAX_RESULTS),
            ("search", term), ("audioformat", "mp32"), ("imagesize", 300), ("type", "single albumtrack")])
        data = self.http.get(JAMENDO_TRACKS + "?" + query)
        headers = data.get("headers") or {}
        if headers.get("status") not in (None, "success"):
            raise DirectoryError(headers.get("error_message") or "Jamendo a refusé la demande")
        return [t for t in (jamendo_track(i) for i in data.get("results", [])) if t]


class YouTubeSource:
    name = "youtube"

    def __init__(self, http, config, music=None, official_guard=None):
        """music : YouTubeMusicSearch (recherche sans quota), None pour l'API officielle seulement ;
        official_guard() : appelé avant chaque recherche par l'API officielle (100 unités), peut la refuser."""
        self.http = http
        self.config = config
        self.music = music
        self.official_guard = official_guard

    @property
    def configured(self):
        return bool(self.config.get("ext_youtube_key"))

    def search(self, term):
        """YouTube Music d'abord ; s'il est absent ou en panne, l'API officielle. Dans les deux cas, les vidéos
        sont vérifiées (1 unité pour 50) : on ne propose que ce que le lecteur intégré pourra lire."""
        try:
            if self.music is None:
                raise DirectoryError("YouTube Music non utilisé")
            tracks = self.music.search(term, MAX_RESULTS, self.region)
        except DirectoryError:
            tracks = self._official_search(term)
        return self._keep_playable(tracks)

    def _official_search(self, term):
        if self.official_guard:
            self.official_guard()
        query = urllib.parse.urlencode([
            ("part", "snippet"), ("type", "video"), ("videoCategoryId", "10"), ("videoEmbeddable", "true"),
            ("maxResults", MAX_RESULTS), ("q", term), ("key", self.config.get("ext_youtube_key"))])
        data = self.http.get(YOUTUBE_SEARCH + "?" + query)
        return [t for t in (youtube_track(i) for i in topic_first(data.get("items", []))) if t]

    def _keep_playable(self, tracks):
        """Vérifie avant l'affichage ce que le lecteur intégré pourra lire. Si cette vérification échoue,
        on garde la liste telle quelle : mieux vaut un titre peut-être illisible que plus de résultats."""
        if not tracks:
            return tracks
        try:
            details = self.details([t["youtubeId"] for t in tracks])
        except DirectoryError:
            return tracks
        kept = []
        for track in tracks:
            duration = playable_details(details.get(track["youtubeId"]) or {}, self.region)
            if duration is not None:
                kept.append(dict(track, duration=duration))
        return kept

    @property
    def region(self):
        return (self.config.get("ext_youtube_region") or "FR").upper()

    def details(self, video_ids):
        """{vidéo: fiche YouTube} pour au plus 50 vidéos (1 unité de quota) ; une vidéo supprimée ou privée manque."""
        query = urllib.parse.urlencode([("part", "snippet,status,contentDetails"), ("key", self.config.get("ext_youtube_key")),
                                        ("id", ",".join(list(video_ids)[:50]))])
        return {v.get("id"): v for v in self.http.get(YOUTUBE_VIDEOS + "?" + query).get("items", [])}

    def playlist_video_ids(self, playlist_id, limit=500):
        """Vidéos d'une playlist publique ou non répertoriée, dans son ordre (sans doublon), au plus `limit`.
        Une playlist privée, dont « J'aime », est refusée par YouTube (DirectoryError) : il faudrait le compte."""
        ids, token = [], ""
        while len(ids) < limit:
            params = [("part", "contentDetails"), ("maxResults", 50), ("playlistId", playlist_id),
                      ("key", self.config.get("ext_youtube_key"))]
            data = self.http.get(YOUTUBE_PLAYLIST_ITEMS + "?" + urllib.parse.urlencode(params + ([("pageToken", token)] if token else [])))
            for item in data.get("items", []):
                video = (item.get("contentDetails") or {}).get("videoId")
                if video and video not in ids:
                    ids.append(video)
            token = data.get("nextPageToken") or ""
            if not token:
                break
        return ids[:limit]

    def recheck(self, video_ids):
        """Relit des vidéos déjà trouvées : (pistes encore lisibles ici, vidéos à oublier)."""
        details = self.details(video_ids)
        tracks, gone = [], []
        for video_id in video_ids:
            track = video_track(details[video_id], self.region) if video_id in details else None
            if track:
                tracks.append(track)
            else:
                gone.append(video_id)
        return tracks, gone
