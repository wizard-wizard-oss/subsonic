"""Lien partagé depuis une appli de musique -> titre à ajouter à la file.

On ne lit jamais l'adresse donnée par le téléphone : on reconnaît le service et l'identifiant, puis on interroge
une adresse publique fixe (oEmbed, API Deezer, iTunes). Le titre trouvé est cherché d'abord dans la bibliothèque
(qualité d'origine), puis sur YouTube."""
import re
import urllib.parse

from ..entities import Track
from .extmusic.sources import song_parts
from .podcasts.directories import DirectoryError
from .podcasts.relevance import normalize, words_of

YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class LinkError(Exception):
    pass


class SongInfo:
    """Ce qu'un lien nous apprend : titre, artiste, et l'identifiant YouTube s'il s'agit d'une vidéo."""

    def __init__(self, title, artist="", youtube_id="", image=""):
        self.title = title
        self.artist = artist
        self.youtube_id = youtube_id
        self.image = image


def youtube_id_of(parts):
    host = parts.hostname or ""
    if host.endswith("youtu.be"):
        candidate = parts.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        query = urllib.parse.parse_qs(parts.query)
        candidate = (query.get("v") or [""])[0]
        if not candidate and parts.path.startswith(("/shorts/", "/live/")):
            candidate = parts.path.split("/")[2]
    else:
        return None
    return candidate if YOUTUBE_ID.match(candidate or "") else None


def numeric_id_after(path, marker):
    match = re.search(r"/%s/(\d+)" % marker, path)
    return match.group(1) if match else None


class LinkResolver:
    def __init__(self, http, search_library, search_youtube):
        self.http = http                         # JsonHttp : get(url) -> JSON
        self.search_library = search_library     # texte -> [Track]
        self.search_youtube = search_youtube     # texte -> [Track] (vide si YouTube n'est pas activé)

    # --- ce que dit le lien ---
    def identify(self, url):
        parts = urllib.parse.urlsplit((url or "").strip())
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise LinkError("Ce n'est pas un lien")
        host = parts.hostname.lower()
        video = youtube_id_of(parts)
        if video:
            return self._youtube(video)
        if host.endswith("deezer.com") and numeric_id_after(parts.path, "track"):
            return self._deezer(numeric_id_after(parts.path, "track"))
        if host.endswith("music.apple.com"):
            track_id = (urllib.parse.parse_qs(parts.query).get("i") or [""])[0] or numeric_id_after(parts.path, "song")
            if track_id and track_id.isdigit():
                return self._apple(track_id)
        if host.endswith("open.spotify.com") and "/track/" in parts.path:
            return self._spotify(parts)
        raise LinkError("Lien non reconnu (YouTube, Deezer, Apple Music ou Spotify)")

    def _get(self, url):
        try:
            return self.http.get(url)
        except DirectoryError:
            raise LinkError("Service injoignable pour le moment")

    def _youtube(self, video):
        data = self._get("https://www.youtube.com/oembed?format=json&url=" +
                         urllib.parse.quote("https://www.youtube.com/watch?v=" + video, safe=""))
        artist = re.sub(r"\s*-\s*Topic$", "", data.get("author_name") or "").replace("VEVO", "").strip()
        return SongInfo(data.get("title") or "Vidéo YouTube", artist, video, data.get("thumbnail_url") or "")

    def _deezer(self, track_id):
        data = self._get("https://api.deezer.com/track/" + track_id)
        if not data.get("title"):
            raise LinkError("Titre Deezer introuvable")
        return SongInfo(data["title"], (data.get("artist") or {}).get("name", ""), image=(data.get("album") or {}).get("cover_medium", ""))

    def _apple(self, track_id):
        results = self._get("https://itunes.apple.com/lookup?id=" + track_id).get("results") or []
        if not results:
            raise LinkError("Titre Apple Music introuvable")
        return SongInfo(results[0].get("trackName", ""), results[0].get("artistName", ""), image=results[0].get("artworkUrl100", ""))

    def _spotify(self, parts):
        clean = urllib.parse.urlunsplit(("https", "open.spotify.com", parts.path, "", ""))
        data = self._get("https://open.spotify.com/oembed?url=" + urllib.parse.quote(clean, safe=""))
        if not data.get("title"):
            raise LinkError("Titre Spotify introuvable")
        return SongInfo(data["title"], image=data.get("thumbnail_url") or "")    # Spotify ne donne pas l'artiste

    # --- le titre à jouer ---
    def resolve(self, url):
        """Renvoie (Track, source) : source = « library » ou « youtube ». LinkError si rien de sûr."""
        info = self.identify(url)
        artist, song = song_parts(info.title, info.artist) if info.youtube_id else (info.artist, info.title)
        words = words_of(song)
        if words:
            for track in self.search_library((artist + " " + song).strip()) or self.search_library(song):
                if all(" " + w in normalize(track.title) for w in words):
                    return track, "library"
        if info.youtube_id:
            return Track.from_api({"id": "yt-" + info.youtube_id, "youtubeId": info.youtube_id, "title": info.title,
                                   "artist": info.artist, "imageUrl": info.image, "ext": "youtube"}), "youtube"
        for track in self.search_youtube((artist + " " + song).strip()):
            if all(" " + w in normalize(track.title) for w in words):
                return track, "youtube"
        raise LinkError("« %s » introuvable dans la bibliothèque%s" % (song, " ni sur YouTube" if words else ""))
