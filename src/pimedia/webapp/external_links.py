"""Lecture des liens musicaux publics, commune aux favoris et aux vidéos associées par Discogs."""
import re
import urllib.parse

from .extmusic import VIDEO_ID, ExtMusicError

SOUNDCLOUD_HOSTS = ("soundcloud.com", "m.soundcloud.com", "on.soundcloud.com")
YOUTUBE_HOSTS = ("youtube.com", "m.youtube.com", "music.youtube.com")
PLAYLIST_ID = re.compile(r"^[\w-]{10,64}$")
PRIVATE_PLAYLISTS = ("LL", "LM", "WL")


def parse_link(text):
    """Lien -> (type, identifiant). Un lien watch avec une playlist désigne la vidéo."""
    text = (text or "").strip()[:500]
    if text and "://" not in text:
        text = "https://" + text
    try:
        parts = urllib.parse.urlsplit(text)
        host = (parts.hostname or "").lower().removeprefix("www.")
    except ValueError:
        raise ExtMusicError("ext.link_unknown")
    path = [p for p in parts.path.split("/") if p]
    query = urllib.parse.parse_qs(parts.query)
    if parts.scheme not in ("http", "https") or parts.username or parts.password:
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
        return "soundcloud", "https://%s/%s" % (host if host == "on.soundcloud.com" else "soundcloud.com",
                                                "/".join(urllib.parse.quote(p, safe="%-_.~") for p in path))
    raise ExtMusicError("ext.link_unknown")


def _video(video_id):
    if not VIDEO_ID.fullmatch(video_id):
        raise ExtMusicError("ext.link_unknown")
    return "youtube_video", video_id


def _playlist(playlist_id):
    if playlist_id in PRIVATE_PLAYLISTS:
        raise ExtMusicError("ext.playlist_private")
    if playlist_id.startswith("RD"):
        raise ExtMusicError("ext.playlist_mix")
    if not PLAYLIST_ID.fullmatch(playlist_id):
        raise ExtMusicError("ext.link_unknown")
    return "youtube_playlist", playlist_id
