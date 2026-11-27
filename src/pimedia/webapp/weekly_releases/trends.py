"""Tendances d'un compte, calculées pendant la synchronisation : artistes, labels et styles d'après ses favoris et
ses marque-pages, puis découvertes (artistes proches selon Last.fm, absents de sa bibliothèque).

Seuls des signaux propres au compte servent : la liste « plus écoutés » de Subsonic est commune au serveur."""
import time

from ...shared.providers.metadata import ProviderUnavailable
from ...shared.providers.musicbrainz.parsing import mbid as valid_mbid
from ...shared.text import normalize
from ..subsonic import Credentials, SubsonicError, SubsonicUnreachable
from .limits import DISCOVERIES_PER_USER, SIMILAR_PER_ARTIST, TREND_ARTISTS, TREND_LABEL_ALBUMS, TREND_STYLES

TRENDS, DISCOVERY = "trends", "discovery"
SERVICE_ERRORS = (ProviderUnavailable, OSError, ValueError, KeyError, TypeError)


def _items(starred, kind):
    found = starred.get(kind) or []
    return [found] if isinstance(found, dict) else [item for item in found if isinstance(item, dict)]


def _mbid_or_none(value):
    try:
        return valid_mbid(value)
    except ValueError:
        return None


class Trends:
    def __init__(self, subsonic, musicbrainz, lastfm, sources, album_labels, profiles, bookmarks, library_artists,
                 clock=time.time):
        self.subsonic, self.musicbrainz, self.lastfm = subsonic, musicbrainz, lastfm
        self.sources, self.album_labels, self.profiles = sources, album_labels, profiles
        self.bookmarks, self.library_artists, self.clock = bookmarks, library_artists, clock

    def refresh(self, user):
        """Recalcule les sources automatiques du compte ; une source masquée par la personne le reste."""
        try:
            starred = self.subsonic.call(Credentials.of(user), "getStarred2").get("starred2") or {}
        except (SubsonicError, SubsonicUnreachable):
            return                                    # sans favoris lisibles, on garde les tendances d'avant
        artists = self._artists(user, starred)
        profile = self._profile(artists)
        self.profiles.save_tags(user.id, profile, self.clock())
        trends = ([("artist", identity, name) for identity, name in artists] +
                  [("label", identity, name) for identity, name in self._labels(starred)] +
                  [("style", name, name) for name in self._styles(profile)])
        self._replace(user, TRENDS, [(kind, identity, name, None) for kind, identity, name in trends])
        self._replace(user, DISCOVERY, self._discoveries(user, artists))

    def _replace(self, user, origin, found):
        for kind, identity, name, via in found:
            self.sources.add(user.id, kind, identity, name, origin, via)
        self.sources.prune(user.id, origin, {(kind, identity) for kind, identity, _, _ in found})

    # ---------- artistes ----------
    def _artists(self, user, starred):
        """[(MBID, nom)] : artistes favoris, puis ceux des albums et morceaux favoris, puis des marque-pages."""
        candidates = [(a.get("name"), a.get("musicBrainzId")) for a in _items(starred, "artist")]
        candidates += [(item.get("artist"), None) for kind in ("album", "song") for item in _items(starred, kind)]
        candidates += [(b.title if b.kind == "artist" else b.artist, None) for b in self.bookmarks(user)]
        found, seen = [], set()
        for name, identity in candidates:
            if not isinstance(name, str) or not name.strip() or normalize(name) in seen:
                continue
            seen.add(normalize(name))
            identity = _mbid_or_none(identity) or self._resolve(name)
            if identity:
                found.append((identity, name.strip()))
            if len(found) >= TREND_ARTISTS:
                break
        return found

    def _resolve(self, name):
        """MBID de l'artiste qui porte exactement ce nom (le premier, MusicBrainz classant par pertinence)."""
        try:
            artists = self.musicbrainz.search_artists(name).value
        except SERVICE_ERRORS:
            return None
        return next((artist.id for artist in artists if normalize(artist.name) == normalize(name)), None)

    # ---------- labels ----------
    def _labels(self, starred):
        """[(MBID, nom)] des labels des albums favoris ; un album n'est cherché qu'une fois (lien gardé en base)."""
        found, lookups = {}, 0
        for album in _items(starred, "album"):
            if not album.get("id") or not album.get("name"):
                continue
            known = self.album_labels.get(album["id"])
            if known is None and lookups < TREND_LABEL_ALBUMS:
                lookups += 1
                known = self._look_up_label(album)
            if known and known["label_id"]:
                found.setdefault(known["label_id"], known["label_name"])
        return list(found.items())

    def _look_up_label(self, album):
        try:
            found = self.musicbrainz.release_label(album["name"], album.get("artist") or "")
        except SERVICE_ERRORS:
            return None                               # nouvel essai la nuit suivante
        label = (found.label.id, found.label.name, found.release_id) if found else (None, None, None)
        self.album_labels.save(album["id"], *label, self.clock())
        return self.album_labels.get(album["id"])

    # ---------- goûts et styles ----------
    def _profile(self, artists):
        """Tags pondérés : chaque artiste apporte 1 à son premier tag, 1/2 au deuxième, 1/3 au troisième…"""
        weights = {}
        for identity, _ in artists:
            try:
                tags = self.musicbrainz.artist_tags(identity)
            except SERVICE_ERRORS:
                continue
            for index, tag in enumerate(tags):
                weights[tag] = weights.get(tag, 0) + 1 / (index + 1)
        return {tag: round(weight, 3) for tag, weight in weights.items()}

    def _styles(self, profile):
        try:
            catalog = {genre.name for genre in self.musicbrainz.release_genres()}
        except SERVICE_ERRORS:
            return []
        ranked = sorted((tag for tag in profile if tag in catalog), key=lambda tag: (-profile[tag], tag))
        return ranked[:TREND_STYLES]

    # ---------- découvertes ----------
    def _discoveries(self, user, artists):
        """[(type, MBID, nom, « proche de »)] : proches absents de la bibliothèque et des artistes déjà suivis."""
        if not self.lastfm.enabled or not self.profiles.get(user.id)[1]:
            return []
        known = self.library_artists(user) | {normalize(name) for _, name in artists}
        followed = {identity for identity, _ in artists}
        found = {}
        for _, origin in artists:
            for similar in self._similar(origin, known):
                identity = similar.mbid or self._resolve(similar.name)
                if identity and identity not in followed and identity not in found:
                    found[identity] = ("similar", identity, similar.name, origin)
                if len(found) >= DISCOVERIES_PER_USER:
                    return list(found.values())
        return list(found.values())

    def _similar(self, name, known):
        try:
            similar = self.lastfm.similar_artists(name, SIMILAR_PER_ARTIST * 2)
        except SERVICE_ERRORS:
            return []
        return [artist for artist in similar if normalize(artist.name) not in known][:SIMILAR_PER_ARTIST]
