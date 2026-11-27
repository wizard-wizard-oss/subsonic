"""Tendances d'un compte, calculées pendant la synchronisation : artistes, labels et styles d'après ses favoris et
ses marque-pages, puis découvertes (artistes proches selon Last.fm, absents de sa bibliothèque).

Seuls des signaux propres au compte servent : la liste « plus écoutés » de Subsonic est commune au serveur.
Chaque étape dit si elle est allée au bout : après une panne, on ajoute ce qui a été trouvé mais on ne retire rien,
et le profil de goûts déjà calculé est gardé."""
import time

from ...shared.providers.metadata import ProviderUnavailable
from ...shared.providers.musicbrainz.parsing import mbid as valid_mbid
from ...shared.text import normalize
from ..subsonic import Credentials, SubsonicError, SubsonicUnreachable
from .limits import (ARTIST, DISCOVERIES_PER_USER, DISCOVERY, LABEL, SIMILAR, SIMILAR_PER_ARTIST, STYLE, TRENDS,
                     TREND_ARTISTS, TREND_LABEL_ALBUMS, TREND_RESOLVE_ATTEMPTS, TREND_STYLES)

SERVICE_ERRORS = (ProviderUnavailable, OSError, ValueError, KeyError, TypeError)


class Incomplete(Exception):
    """Un service n'a pas répondu : le résultat partiel ne doit pas servir à retirer des sources."""


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
        self._attempts = 0

    def refresh(self, user):
        """Recalcule les sources automatiques du compte ; une source masquée par la personne le reste."""
        try:
            starred = self.subsonic.call(Credentials.of(user), "getStarred2").get("starred2") or {}
        except (SubsonicError, SubsonicUnreachable):
            return                                    # sans favoris lisibles, on garde les tendances d'avant
        self._attempts = 0
        artists, complete = self._artists(user, starred)
        self._replace(user, TRENDS, ARTIST, [(identity, name, None) for identity, name in artists], complete)
        labels, complete = self._labels(starred)
        self._replace(user, TRENDS, LABEL, [(identity, name, None) for identity, name in labels], complete)
        profile = self._profile(user, artists)
        styles, complete = self._styles(profile)
        self._replace(user, TRENDS, STYLE, [(name, name, None) for name in styles], complete)
        discoveries, complete = self._discoveries(user, artists)
        self._replace(user, DISCOVERY, SIMILAR, discoveries, complete)

    def _replace(self, user, origin, kind, found, complete):
        for identity, name, via in found:
            self.sources.add(user.id, kind, identity, name, origin, via)
        if complete:
            self.sources.prune(user.id, origin, kind, {identity for identity, _, _ in found})

    # ---------- artistes ----------
    def _artists(self, user, starred):
        """([(MBID, nom)], complet) : artistes favoris, puis ceux des albums et morceaux favoris, puis des marque-pages."""
        candidates = [(a.get("name"), a.get("musicBrainzId")) for a in _items(starred, "artist")]
        candidates += [(item.get("artist"), None) for kind in ("album", "song") for item in _items(starred, kind)]
        candidates += [(b.title if b.kind == ARTIST else b.artist, None) for b in self.bookmarks(user)]
        found, seen, complete = [], set(), True
        for name, identity in candidates:
            if not isinstance(name, str) or not name.strip() or normalize(name) in seen:
                continue
            seen.add(normalize(name))
            try:
                identity = _mbid_or_none(identity) or self._resolve(name)
            except Incomplete:
                complete = False
                continue
            if identity:
                found.append((identity, name.strip()))
            if len(found) >= TREND_ARTISTS:
                break
        return found, complete

    def _resolve(self, name):
        """MBID de l'unique artiste MusicBrainz qui porte exactement ce nom ; None s'il y en a zéro ou plusieurs
        (deux « Air » : on ne devine pas). Le nombre de recherches par calcul est plafonné."""
        if self._attempts >= TREND_RESOLVE_ATTEMPTS:
            return None
        self._attempts += 1
        try:
            artists = self.musicbrainz.search_artists(name).value
        except SERVICE_ERRORS:
            raise Incomplete() from None
        matches = {artist.id for artist in artists if normalize(artist.name) == normalize(name)}
        return matches.pop() if len(matches) == 1 else None

    # ---------- labels ----------
    def _labels(self, starred):
        """([(MBID, nom)], complet) des labels des albums favoris ; un album n'est cherché qu'une fois."""
        found, lookups, complete = {}, 0, True
        for album in _items(starred, "album"):
            if not album.get("id") or not album.get("name"):
                continue
            known = self.album_labels.get(album["id"])
            if known is None and lookups < TREND_LABEL_ALBUMS:
                lookups += 1
                try:
                    known = self._look_up_label(album)
                except Incomplete:
                    complete = False
            if known and known["label_id"]:
                found.setdefault(known["label_id"], known["label_name"])
        return list(found.items()), complete

    def _look_up_label(self, album):
        try:
            found = self.musicbrainz.release_label(album["name"], album.get("artist") or "")
        except SERVICE_ERRORS:
            raise Incomplete() from None              # nouvel essai la nuit suivante
        label = (found.label.id, found.label.name, found.release_id) if found else (None, None, None)
        self.album_labels.save(album["id"], *label, self.clock())
        return self.album_labels.get(album["id"])

    # ---------- goûts et styles ----------
    def _profile(self, user, artists):
        """Tags pondérés : chaque artiste apporte 1 à son premier tag, 1/2 au deuxième, 1/3 au troisième…
        Si MusicBrainz ne répond pas, le profil déjà enregistré est gardé tel quel."""
        weights = {}
        try:
            for identity, _ in artists:
                for index, tag in enumerate(self.musicbrainz.artist_tags(identity)):
                    weights[tag] = weights.get(tag, 0) + 1 / (index + 1)
        except SERVICE_ERRORS:
            return self.profiles.get(user.id)[0]
        profile = {tag: round(weight, 3) for tag, weight in weights.items()}
        self.profiles.save_tags(user.id, profile, self.clock())
        return profile

    def _styles(self, profile):
        try:
            catalog = {genre.name for genre in self.musicbrainz.release_genres()}
        except SERVICE_ERRORS:
            return [], False
        ranked = sorted((tag for tag in profile if tag in catalog), key=lambda tag: (-profile[tag], tag))
        return ranked[:TREND_STYLES], True

    # ---------- découvertes ----------
    def _discoveries(self, user, artists):
        """([(MBID, nom, « proche de »)], complet) : proches absents de la bibliothèque et des artistes suivis."""
        if not self.lastfm.enabled or not self.profiles.get(user.id)[1]:
            return [], True
        known = self.library_artists(user) | {normalize(name) for _, name in artists}
        followed, found = {identity for identity, _ in artists}, {}
        try:
            for _, origin in artists:
                for similar in self._similar(origin, known):
                    identity = similar.mbid or self._resolve(similar.name)
                    if identity and identity not in followed and identity not in found:
                        found[identity] = (identity, similar.name, origin)
                    if len(found) >= DISCOVERIES_PER_USER:
                        return list(found.values()), True
        except Incomplete:
            return list(found.values()), False
        return list(found.values()), True

    def _similar(self, name, known):
        try:
            similar = self.lastfm.similar_artists(name, SIMILAR_PER_ARTIST * 2)
        except SERVICE_ERRORS:
            raise Incomplete() from None
        return [artist for artist in similar if normalize(artist.name) not in known][:SIMILAR_PER_ARTIST]
