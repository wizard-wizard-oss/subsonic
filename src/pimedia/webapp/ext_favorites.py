"""Favoris d'ailleurs, propres à chaque personne : vidéos YouTube, titres SoundCloud et Jamendo. On les ajoute avec le
cœur d'un résultat de recherche, ou en collant un lien : une vidéo ou une playlist YouTube (publique ou non
répertoriée : « J'aime » est privée, il faudrait le compte Google), un titre SoundCloud. Rien n'est contourné :
YouTube se lit dans son lecteur officiel, SoundCloud dans le sien (son « widget »), et les titres SoundCloud sont
décrits par son oEmbed public, sans clé."""
import re
import time
import urllib.parse

from ..server.podcasts.directories import DirectoryError, JsonHttp
from .extmusic import VIDEO_ID, ExtMusicError, SearchBudget

SOUNDCLOUD_OEMBED = "https://soundcloud.com/oembed"
SOUNDCLOUD_HOSTS = ("soundcloud.com", "m.soundcloud.com", "on.soundcloud.com")
YOUTUBE_HOSTS = ("youtube.com", "m.youtube.com", "music.youtube.com")
PLAYLIST_ID = re.compile(r"^[\w-]{10,64}$")
PRIVATE_PLAYLISTS = ("LL", "LM", "WL")       # J'aime (YouTube, YouTube Music), À regarder plus tard : jamais lisibles
LINKS_PER_HOUR = 30
MAX_FAVORITES = 5000
PLAYLIST_LIMIT = 500
JAMENDO_URL = re.compile(r"^https://[\w.-]+\.jamendo\.com/")
SOUNDCLOUD_IMAGE = re.compile(r"^https://[\w.-]+\.sndcdn\.com/")
SOURCES = ("youtube", "soundcloud", "jamendo")


# ---------- lecture d'un lien (fonctions pures) ----------
def parse_link(text):
    """Lien collé -> ("youtube_video", id) | ("youtube_playlist", id) | ("soundcloud", adresse de la page).
    Une adresse « watch » avec une playlist (lancée depuis une playlist) désigne la vidéo : c'est la convention de
    YouTube ; pour toute la playlist, il faut son lien « playlist?list= »."""
    text = (text or "").strip()[:500]
    if text and "://" not in text:
        text = "https://" + text
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        raise ExtMusicError("ext.link_unknown")
    host = (parts.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = [p for p in parts.path.split("/") if p]
    query = urllib.parse.parse_qs(parts.query)
    if parts.scheme not in ("http", "https"):
        raise ExtMusicError("ext.link_unknown")
    if host == "youtu.be" and path:
        return _video(path[0])
    if host in YOUTUBE_HOSTS:
        if path[:1] == ["watch"] and query.get("v"):
            return _video(query["v"][0])
        if len(path) == 2 and path[0] in ("shorts", "embed", "live"):
            return _video(path[1])
        if path[:1] == ["playlist"] and query.get("list"):
            return _playlist(query["list"][0])
    if host in SOUNDCLOUD_HOSTS and len(path) >= (1 if host == "on.soundcloud.com" else 2):
        if host != "on.soundcloud.com" and "sets" in path[1:2]:
            raise ExtMusicError("ext.soundcloud_not_track")
        return "soundcloud", "https://%s/%s" % ("on.soundcloud.com" if host == "on.soundcloud.com" else "soundcloud.com",
                                                "/".join(urllib.parse.quote(p, safe="%-_.~") for p in path))
    raise ExtMusicError("ext.link_unknown")


def _video(video_id):
    if not VIDEO_ID.match(video_id):
        raise ExtMusicError("ext.link_unknown")
    return "youtube_video", video_id


def _playlist(playlist_id):
    if playlist_id in PRIVATE_PLAYLISTS:
        raise ExtMusicError("ext.playlist_private")
    if playlist_id.startswith("RD"):                 # « Mix » calculé par YouTube pour chacun : pas une vraie playlist
        raise ExtMusicError("ext.playlist_mix")
    if not PLAYLIST_ID.match(playlist_id):
        raise ExtMusicError("ext.link_unknown")
    return "youtube_playlist", playlist_id


def soundcloud_track(oembed, page_url):
    """Réponse oEmbed de SoundCloud -> titre à garder, ou None si ce n'est pas un titre (playlist, profil…).
    Le numéro du titre est dans l'adresse de son lecteur (« …tracks/123… » ou « soundcloud:tracks:123 »)."""
    found = re.search(r"tracks(?:%2F|/|%3A|:)(\d+)", oembed.get("html") or "", re.I)
    if not found:
        return None
    artist = str(oembed.get("author_name") or "").strip()[:200]
    title = str(oembed.get("title") or "").strip()
    if artist and title.endswith(" by " + artist):           # « Titre by Artiste »
        title = title[:-len(" by " + artist)]
    image = str(oembed.get("thumbnail_url") or "")
    return {"itemId": found.group(1), "title": title[:300] or "SoundCloud", "artist": artist,
            "imageUrl": image if SOUNDCLOUD_IMAGE.match(image) else "", "duration": 0,
            "playUrl": "https://api.soundcloud.com/tracks/" + found.group(1), "pageUrl": page_url}


def jamendo_favorite(item):
    """Titre Jamendo venu d'un résultat de recherche (envoyé par la page) : vérifié avant d'être gardé."""
    found = re.match(r"^jamendo-(\d{1,15})$", str(item.get("id") or ""))
    stream, image = str(item.get("streamUrl") or ""), str(item.get("imageUrl") or "")
    if not found or not JAMENDO_URL.match(stream) or (image and not JAMENDO_URL.match(image)):
        raise ExtMusicError("request.invalid")
    duration = item.get("duration")
    return {"itemId": found.group(1), "title": str(item.get("title") or "")[:300] or "Jamendo",
            "artist": str(item.get("artist") or "")[:200], "imageUrl": image,
            "duration": duration if isinstance(duration, int) and 0 <= duration < 86400 else 0,
            "playUrl": stream[:1000], "pageUrl": ""}


def soundcloud_item(item):
    """Titre SoundCloud venu de la page (un favori déjà décrit par oEmbed) : vérifié avant d'être gardé ailleurs."""
    found = re.match(r"^sc-(\d{1,15})$", str(item.get("id") or ""))
    image = str(item.get("imageUrl") or "")
    if not found or item.get("soundcloudUrl") != "https://api.soundcloud.com/tracks/" + found.group(1) \
            or (image and not SOUNDCLOUD_IMAGE.match(image)):
        raise ExtMusicError("request.invalid")
    kind, page = parse_link(str(item.get("pageUrl") or ""))
    if kind != "soundcloud":
        raise ExtMusicError("request.invalid")
    return {"itemId": found.group(1), "title": str(item.get("title") or "")[:300] or "SoundCloud",
            "artist": str(item.get("artist") or "")[:200], "imageUrl": image, "duration": 0,
            "playUrl": item["soundcloudUrl"], "pageUrl": page}


def item_id_of(source, item):
    """Identifiant chez la source d'un titre au format de la page (« yt-… », « sc-… », « jamendo-… »)."""
    prefix = {"youtube": "yt-", "soundcloud": "sc-", "jamendo": "jamendo-"}[source]
    value = str(item.get("id") or "")
    if not value.startswith(prefix) or not re.match(r"^[\w-]{1,40}$", value[len(prefix):]):
        raise ExtMusicError("request.invalid")
    return value[len(prefix):]


class ExtFavorites:
    def __init__(self, repository, extmusic, http=None, clock=time.time):
        """repository : ExtFavoriteRepository ; extmusic : ExternalMusic (clé et vidéos YouTube du site)."""
        self.repository, self.extmusic = repository, extmusic
        self.http = http or JsonHttp()
        self.budget = SearchBudget(LINKS_PER_HOUR, clock, "ext.too_many_links")

    def all(self, user):
        return [f.to_api() for f in self.repository.all(user.id)]

    def add_link(self, user, link):
        """Lien collé -> {"kind": "video"|"playlist"|"track", "added", "already", "skipped"} (skipped : vidéos de la
        playlist que le lecteur intégré ne pourra pas lire ici, ou supprimées)."""
        kind, value = parse_link(link)
        if kind != "soundcloud" and not self.extmusic.status()["youtube"]:
            raise ExtMusicError("ext.disabled")
        self.budget.spend(user.username)
        if kind == "soundcloud":
            return self._save(user, "soundcloud", "track", [self._soundcloud(value)])
        if kind == "youtube_video":
            tracks = self._youtube([value])
            if not tracks:
                raise ExtMusicError("ext.video_unplayable")
            return self._save(user, "youtube", "video", tracks)
        try:
            ids = self.extmusic.youtube.playlist_video_ids(value, PLAYLIST_LIMIT)
        except DirectoryError as error:
            raise ExtMusicError(_refused_or_unreachable(error, "ext.playlist_private"))
        if not ids:
            raise ExtMusicError("ext.playlist_empty")
        return self._save(user, "youtube", "playlist", self._youtube(ids), len(ids))

    def set(self, user, item, on):
        """Cœur d'un titre d'ailleurs (au format de la page) : ajouté ou retiré des favoris de la personne."""
        if not isinstance(on, bool):
            raise ExtMusicError("request.invalid")
        if not on:
            source = self.source_of(item)
            self.repository.remove(user.id, source, item_id_of(source, item))
            return
        source, track = self.checked(item)
        self._save(user, source, "track", [track])

    @staticmethod
    def source_of(item):
        if not isinstance(item, dict) or item.get("ext") not in SOURCES:
            raise ExtMusicError("request.invalid")
        return item["ext"]

    def checked(self, item):
        """Titre d'ailleurs envoyé par la page (cœur, ajout à une playlist) -> (source, titre à garder), vérifié :
        rien de ce que la page envoie n'est gardé tel quel (adresses de lecture comprises)."""
        source = self.source_of(item)
        if source == "soundcloud":
            return source, soundcloud_item(item)
        if source == "jamendo":
            return source, jamendo_favorite(item)
        tracks = self._youtube([item_id_of("youtube", item)])
        if not tracks:
            raise ExtMusicError("ext.video_unplayable")
        return source, tracks[0]

    # ---------- sources ----------
    def _youtube(self, ids):
        """Vidéos lisibles ici, dans l'ordre demandé : déjà connues du site (sans quota), sinon lues chez YouTube
        (1 unité de quota par lot de 50) et gardées dans youtube_videos, relues ensuite tous les 30 jours."""
        videos = self.extmusic.videos
        known = {}
        for start in range(0, len(ids), 200):
            known.update((t["youtubeId"], t) for t in videos.tracks(ids[start:start + 200]))
        unknown = [v for v in ids if v not in known]
        for start in range(0, len(unknown), 50):
            try:
                tracks, _gone = self.extmusic.youtube.recheck(unknown[start:start + 50])
            except DirectoryError:
                raise ExtMusicError("ext.unreachable")
            videos.remember(tracks)
            known.update((t["youtubeId"], t) for t in tracks)
        return [{"itemId": v} for v in ids if v in known]

    def _soundcloud(self, page_url):
        query = urllib.parse.urlencode([("format", "json"), ("url", page_url)])
        try:
            track = soundcloud_track(self.http.get(SOUNDCLOUD_OEMBED + "?" + query), page_url)
        except DirectoryError as error:
            raise ExtMusicError(_refused_or_unreachable(error, "ext.link_not_found"))
        if track is None:
            raise ExtMusicError("ext.soundcloud_not_track")
        return track

    def _save(self, user, source, kind, tracks, found=None):
        if self.repository.count(user.id) + len(tracks) > MAX_FAVORITES:
            raise ExtMusicError("ext.too_many_favorites")
        added = self.repository.add(user.id, source, tracks)
        return {"kind": kind, "added": added, "already": len(tracks) - added,
                "skipped": (found or len(tracks)) - len(tracks)}


def _refused_or_unreachable(error, refused_key):
    """La source répond « introuvable » ou « interdit » (privé, supprimé) : refused_key ; sinon elle est injoignable."""
    text = str(error)
    return refused_key if any(word in text for word in ("Not Found", "Forbidden", "404", "403", "401")) else "ext.unreachable"
