"""Playlists Subsonic de l'utilisateur (et celles que les autres ont rendues publiques).

Playlist communautaire : une playlist Subsonic de son créateur, rendue publique, où tout le monde peut ajouter.
Subsonic n'autorise que le créateur à écrire : le site écrit avec le jeton du créateur (gardé à sa dernière
connexion) et note de son côté qui a ajouté chaque titre, que Subsonic ne sait pas garder.

Titres d'ailleurs (YouTube, SoundCloud, Jamendo) : Subsonic ne peut pas les garder. Le site les garde à côté et les
montre à leur place ; les applications Subsonic ne voient que les titres Subsonic de la playlist."""
from .library import as_list, song_row
from .subsonic import Credentials, SubsonicError

BAD_CREDENTIALS = 40


MAX_EXT_TRACKS = 500
MAX_SONGS = 500                       # titres Subsonic donnés d'un coup à createPlaylist


class PlaylistError(ValueError):
    pass


def playlist_card(raw, me, community=False):
    owner = raw.get("owner", "")
    return {"id": raw.get("id"), "name": raw.get("name", "?"), "owner": owner,
            "mine": owner == me, "public": bool(raw.get("public")), "songCount": raw.get("songCount", 0),
            "duration": raw.get("duration", 0), "coverId": raw.get("coverArt", ""), "comment": raw.get("comment", ""),
            "community": community, "canAdd": owner == me or community}


class Playlists:
    def __init__(self, subsonic, community, users, ext_tracks, ext_check):
        """ext_tracks : PlaylistExtRepository ; ext_check : ExtFavorites (vérifie un titre d'ailleurs envoyé par la page)."""
        self.subsonic = subsonic
        self.community = community
        self.users = users
        self.ext_tracks = ext_tracks
        self.ext_check = ext_check

    def _call(self, user, endpoint, params=(), post=False):
        return self.subsonic.call(Credentials.of(user), endpoint, params, post=post)

    def _raw(self, user, playlist_id):
        return self._call(user, "getPlaylist", [("id", playlist_id)]).get("playlist") or {}

    def all(self, user):
        raw = as_list((self._call(user, "getPlaylists").get("playlists") or {}).get("playlist"))
        community, ext = self.community.community_ids(), self.ext_tracks.counts()
        cards = [playlist_card(p, user.username, p.get("id") in community) for p in raw]
        for card in cards:
            card["songCount"] += ext.get(card["id"], 0)
        return sorted(cards, key=lambda p: (not p["mine"], p["name"].lower()))

    def get(self, user, playlist_id):
        raw = self._raw(user, playlist_id)
        card = playlist_card(raw, user.username, self.community.owner_id(playlist_id) is not None)
        authors = self.community.authors(playlist_id) if card["community"] else {}
        songs = [dict(song_row(s), position=i, addedBy=authors.get(s.get("id"), card["owner"]) if card["community"] else "")
                 for i, s in enumerate(as_list(raw.get("entry")))]
        card["songs"] = self._with_ext(songs, self.ext_tracks.of_playlist(playlist_id), card["owner"])
        return card

    @staticmethod
    def _with_ext(songs, ext, owner):
        """Titres Subsonic (position : leur rang chez Subsonic) et titres d'ailleurs à leur place."""
        merged, ext = [], list(ext)
        for i, song in enumerate(songs + [None]):
            while ext and (ext[0].after_songs <= i or song is None):
                merged.append(dict(ext.pop(0).to_api(), position=None))
            if song is not None:
                merged.append(song)
        for item in merged:
            if item.get("ext") and not item["addedBy"]:
                item["addedBy"] = owner                          # ajouté par une personne qui n'a plus de compte
        return merged

    @staticmethod
    def _name(name):
        name = (name or "").strip() if isinstance(name, str) else ""
        if not name or len(name) > 100:
            raise PlaylistError("playlist.bad_name")
        return name

    def create(self, user, name, song_ids=(), community=False):
        params = [("name", self._name(name))] + [("songId", s) for s in list(song_ids)[:MAX_SONGS]]
        raw = self._call(user, "createPlaylist", params).get("playlist")
        if not raw:                                 # Subsonic avant 1.14 ne renvoie pas la playlist créée
            mine = [p for p in self.all(user) if p["mine"] and p["name"] == params[0][1]]
            raw = mine[-1] if mine else None
        if raw is None:
            return {"name": params[0][1]}
        card = playlist_card(raw, user.username)
        if community:
            self._open_to_all(user, card["id"])
            self.community.record(card["id"], list(song_ids)[:500], user.id)
            card.update(community=True, public=True)
        return card

    def create_mixed(self, user, name, song_ids, extras):
        """Nouvelle playlist (import) : titres Subsonic dans l'ordre, et titres d'ailleurs déjà vérifiés,
        extras = [(nombre de titres Subsonic avant lui, (source, titre))], chacun à sa place."""
        card = self.create(user, name, song_ids)
        if card.get("id"):
            for after_songs, track in extras:
                self.ext_tracks.add(card["id"], after_songs, [track], user.id)
            card["songCount"] = len(song_ids) + len(extras)
        return card

    def _open_to_all(self, user, playlist_id):
        """Publique pour que les autres la voient, et notée communautaire pour qu'ils puissent y ajouter."""
        self._call(user, "updatePlaylist", [("playlistId", playlist_id), ("public", "true")])
        self.community.enable(playlist_id, user.id)

    def set_community(self, user, playlist_id, on):
        if self._raw(user, playlist_id).get("owner") != user.username:
            raise PlaylistError("playlist.not_owner")
        if on:
            self._open_to_all(user, playlist_id)
        else:
            self.community.disable(playlist_id)

    def _writer(self, user, playlist_id):
        """Qui écrit dans la playlist : son créateur lui-même, ou, si elle est communautaire, le site avec le jeton du
        créateur. Renvoie (identité Subsonic à utiliser, playlist, communautaire ?)."""
        raw = self._raw(user, playlist_id)
        community_owner = self.community.owner_id(playlist_id)
        if raw.get("owner") == user.username:
            return user, raw, community_owner is not None
        owner = self.users.get(community_owner) if community_owner is not None else None
        if owner is None or owner.username != raw.get("owner"):
            raise PlaylistError("playlist.not_community")
        return owner, raw, True

    def _write(self, owner, playlist_id, params):
        try:
            self._call(owner, "updatePlaylist", [("playlistId", playlist_id)] + params)
        except SubsonicError as error:
            if error.code == BAD_CREDENTIALS:        # le créateur a changé son mot de passe depuis sa dernière visite
                raise PlaylistError("playlist.owner_unavailable")
            raise

    def add(self, user, playlist_id, song_ids):
        """Nombre de titres ajoutés. Dans une communautaire un titre n'est ajouté qu'une fois : l'auteur de chaque
        titre est ainsi sans ambiguïté."""
        owner, raw, community = self._writer(user, playlist_id)
        song_ids = list(song_ids[:500])
        if community:
            present = {s.get("id") for s in as_list(raw.get("entry"))}
            song_ids = [s for s in dict.fromkeys(song_ids) if s not in present]
        if not song_ids:
            return 0
        self._write(owner, playlist_id, [("songIdToAdd", s) for s in song_ids])
        if community:
            self.community.record(playlist_id, song_ids, user.id)
        return len(song_ids)

    def add_ext(self, user, playlist_id, items):
        """Titres d'ailleurs (au format de la page) mis à la fin de la playlist ; mêmes droits que pour les titres
        Subsonic. Un titre déjà dans la playlist n'y est pas remis. Renvoie le nombre de titres ajoutés."""
        _owner, raw, _community = self._writer(user, playlist_id)
        tracks = [self.ext_check.checked(item) for item in items[:MAX_EXT_TRACKS]]
        if len(self.ext_tracks.of_playlist(playlist_id)) + len(tracks) > MAX_EXT_TRACKS:
            raise PlaylistError("playlist.too_many_ext")
        return self.ext_tracks.add(playlist_id, len(as_list(raw.get("entry"))), tracks, user.id)

    def remove_ext(self, user, playlist_id, row_ids):
        """Le créateur retire ce qu'il veut ; les autres (playlist communautaire) seulement ce qu'ils ont ajouté."""
        owner, _raw, _community = self._writer(user, playlist_id)
        authors = self.ext_tracks.added_by(playlist_id, row_ids)
        if owner is not user and any(authors.get(r, -1) != user.id for r in row_ids):
            raise PlaylistError("playlist.not_yours")
        self.ext_tracks.remove(playlist_id, row_ids)

    def remove_positions(self, user, playlist_id, positions):
        """Le créateur retire ce qu'il veut ; les autres seulement ce qu'ils ont ajouté eux-mêmes."""
        positions = [p for p in positions if isinstance(p, int) and p >= 0]
        owner, raw, community = self._writer(user, playlist_id)
        songs = [s.get("id") for s in as_list(raw.get("entry"))]
        if owner is not user:
            authors = self.community.authors(playlist_id)
            if any(p >= len(songs) or authors.get(songs[p]) != user.username for p in positions):
                raise PlaylistError("playlist.not_yours")
        self._write(owner, playlist_id, [("songIndexToRemove", p) for p in positions])
        if community:                                # plus de trace des titres qui ne sont plus dans la playlist
            removed = set(positions)
            left = {s for i, s in enumerate(songs) if i not in removed}
            self.community.forget_songs(playlist_id, {songs[p] for p in removed if p < len(songs)} - left)

    def reorder(self, user, playlist_id, order):
        """Nouvel ordre choisi par le créateur : order = [{"position": rang chez Subsonic} | {"extId": ligne}], chaque
        titre une fois. Subsonic ne sait pas déplacer : on retire la fin à partir du premier titre qui bouge et on la
        remet dans le nouvel ordre (un seul updatePlaylist). Les titres d'ailleurs gardent leur place chez le site.
        La playlist a changé depuis que la page l'a lue (ajout, retrait) : PlaylistError, rien n'est touché."""
        raw = self._raw(user, playlist_id)
        if raw.get("owner") != user.username:
            raise PlaylistError("playlist.not_owner")
        songs = [s.get("id") for s in as_list(raw.get("entry"))]
        positions = [item["position"] for item in order if "position" in item]
        rows = [item["extId"] for item in order if "extId" in item]
        shown = {track.row_id for track in self.ext_tracks.of_playlist(playlist_id)}
        if sorted(positions) != list(range(len(songs))) or len(rows) != len(shown) or set(rows) != shown:
            raise PlaylistError("playlist.changed")
        first = next((i for i, p in enumerate(positions) if p != i), len(songs))
        if first < len(songs):
            try:
                self._call(user, "updatePlaylist", [("playlistId", playlist_id)]
                           + [("songIndexToRemove", i) for i in range(first, len(songs))]
                           + [("songIdToAdd", songs[p]) for p in positions[first:]], post=True)
            except SubsonicError:
                raise PlaylistError("playlist.reorder_failed")
        places, before = [], 0
        for item in order:
            if "position" in item:
                before += 1
            else:
                places.append((item["extId"], before))
        self.ext_tracks.place(playlist_id, places)

    def rename(self, user, playlist_id, name):
        self._call(user, "updatePlaylist", [("playlistId", playlist_id), ("name", self._name(name))])

    def delete(self, user, playlist_id):
        self._call(user, "deletePlaylist", [("id", playlist_id)])
        self.community.forget(playlist_id)
        self.ext_tracks.forget(playlist_id)
