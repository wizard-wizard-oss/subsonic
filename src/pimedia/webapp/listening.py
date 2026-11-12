"""Ce qui suit l'écoute de chacun, avec son compte Subsonic :
- scrobble : « en cours » puis écoute comptée (Subsonic l'envoie à Last.fm si la personne l'a relié
  dans Paramètres → Personnel) ;
- en écoute maintenant (getNowPlaying) : qui écoute quoi sur le serveur ;
- marque-pages (getBookmarks…) : positions gardées par les applis de téléphone, et par ce site ;
- file d'attente retrouvée (getPlayQueue / savePlayQueue), partagée avec les applis qui la gèrent."""
import time

from .library import as_list, song_row
from .subsonic import Credentials

MAX_QUEUE_SONGS = 5000


class Listening:
    def __init__(self, subsonic, clock=time.time):
        self.subsonic = subsonic
        self.clock = clock

    def _call(self, user, endpoint, params=()):
        return self.subsonic.call(Credentials.of(user), endpoint, params)

    # --- scrobble ---
    def scrobble(self, user, song_id, submission):
        """submission False : « en cours » ; True : écoute comptée (après la moitié du titre ou 4 minutes)."""
        params = [("id", song_id), ("submission", "true" if submission else "false")]
        if submission:
            params.append(("time", int(self.clock() * 1000)))
        self._call(user, "scrobble", params)

    # --- en écoute ---
    def now_playing(self, user):
        entries = as_list((self._call(user, "getNowPlaying").get("nowPlaying") or {}).get("entry"))
        return [dict(song_row(e), username=e.get("username", ""), minutesAgo=e.get("minutesAgo", 0),
                     player=e.get("playerName", "")) for e in entries]

    # --- marque-pages ---
    def bookmarks(self, user):
        raw = as_list((self._call(user, "getBookmarks").get("bookmarks") or {}).get("bookmark"))
        result = []
        for bookmark in raw:
            entry = bookmark.get("entry") or {}
            if isinstance(entry, list):
                entry = entry[0] if entry else {}
            if not entry.get("id"):
                continue
            result.append({"song": song_row(entry), "position": (bookmark.get("position") or 0) / 1000,
                           "comment": bookmark.get("comment", ""), "changed": bookmark.get("changed", "")})
        return sorted(result, key=lambda b: b["changed"], reverse=True)

    def save_bookmark(self, user, song_id, position_seconds, comment=""):
        if not isinstance(position_seconds, (int, float)) or position_seconds < 0:
            raise ValueError("position")
        self._call(user, "createBookmark", [("id", song_id), ("position", int(position_seconds * 1000)),
                                            ("comment", str(comment or "")[:200])])

    def delete_bookmark(self, user, song_id):
        self._call(user, "deleteBookmark", [("id", song_id)])

    # --- file d'attente partagée avec les applis ---
    def play_queue(self, user):
        raw = self._call(user, "getPlayQueue").get("playQueue") or {}
        songs = [song_row(e) for e in as_list(raw.get("entry"))]
        current = str(raw.get("current", ""))
        index = next((i for i, s in enumerate(songs) if str(s["id"]) == current), 0)
        return {"songs": songs, "index": index, "position": (raw.get("position") or 0) / 1000,
                "changedBy": raw.get("changedBy", ""), "changed": raw.get("changed", "")}

    def save_play_queue(self, user, song_ids, current_id, position_seconds):
        ids = [str(s) for s in song_ids]
        params = [("id", s) for s in ids]
        if current_id and str(current_id) in ids:
            params += [("current", current_id), ("position", int(max(0, position_seconds or 0) * 1000))]
        self.subsonic.call(Credentials.of(user), "savePlayQueue", params, post=True)
