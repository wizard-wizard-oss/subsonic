"""Tendances d'un compte, calculées pendant la synchronisation, d'après ses favoris seulement (artistes, albums,
morceaux) : ses artistes, les labels de ses albums favoris et ses styles dominants.

Styles dominants : chaque artiste apporte ses STYLES_PER_ARTIST premiers tags du catalogue ; un style porté par moins de
MIN_STYLE_ARTISTS artistes est écarté ; les TREND_STYLES premiers sont proposés. Sans favori, les styles viennent des
albums les plus écoutés du sub (liste commune au serveur, voulue ici) et aucun artiste n'est attribué au compte.

Chaque étape dit si elle est allée au bout : après une panne, on ajoute ce qui a été trouvé mais on ne retire rien."""
import time

from ...shared.providers.metadata import ProviderUnavailable
from ...shared.providers.musicbrainz.client import IDS_PER_QUERY
from ...shared.providers.musicbrainz.parsing import mbid as valid_mbid
from ...shared.text import normalize
from ..subsonic import Credentials, SubsonicError, SubsonicUnreachable
from .limits import (ARTIST, FAVORITES, LABEL, MIN_STYLE_ARTISTS, RESOLVE_AGAIN_AFTER, SITE, SITE_ALBUMS, STYLE,
                     STYLES_PER_ARTIST, TREND_ARTISTS, TREND_LABEL_ALBUMS, TREND_RESOLVE_ATTEMPTS, TREND_STYLES,
                     TRENDS)

SERVICE_ERRORS = (ProviderUnavailable, OSError, ValueError, KeyError, TypeError)
SUBSONIC_ERRORS = (SubsonicError, SubsonicUnreachable)


class Incomplete(Exception):
    """Un service n'a pas répondu : le résultat partiel ne doit pas servir à retirer des sources."""


def _items(container, kind):
    found = (container or {}).get(kind) or []
    return [found] if isinstance(found, dict) else [item for item in found if isinstance(item, dict)]


def _mbid_or_none(value):
    try:
        return valid_mbid(value)
    except ValueError:
        return None


class Trends:
    def __init__(self, subsonic, musicbrainz, sources, album_labels, profiles, names, clock=time.time):
        self.subsonic, self.musicbrainz, self.sources = subsonic, musicbrainz, sources
        self.album_labels, self.profiles, self.names, self.clock = album_labels, profiles, names, clock
        self._attempts = 0

    def refresh(self, user):
        """Recalcule les sources automatiques du compte ; une source masquée par la personne le reste."""
        try:
            starred = self.subsonic.call(Credentials.of(user), "getStarred2").get("starred2") or {}
        except SUBSONIC_ERRORS:
            return                                    # sans favoris lisibles, on garde les tendances d'avant
        self._attempts = 0
        favorites = self._names(starred)
        if favorites:
            artists, complete = self._resolve_all(favorites)
            self._replace(user, ARTIST, [(identity, name) for identity, name in artists], complete)
            labels, complete = self._labels(starred)
            self._replace(user, LABEL, labels, complete)
            basis = FAVORITES
        else:
            artists = self._site_artists(user)
            self._replace(user, ARTIST, [], True)
            self._replace(user, LABEL, [], True)
            basis = SITE
        styles, complete = self._dominant_styles([identity for identity, _ in artists])
        self._replace(user, STYLE, [(name, name) for name in styles], complete)
        self.profiles.set_basis(user.id, basis)

    def _replace(self, user, kind, found, complete):
        for identity, name in found:
            self.sources.add(user.id, kind, identity, name, TRENDS)
        if complete:
            self.sources.prune(user.id, TRENDS, kind, {identity for identity, _ in found})

    # ---------- artistes ----------
    @staticmethod
    def _names(starred):
        """[(nom, MBID ou None)] : artistes favoris, puis artistes des albums et morceaux favoris."""
        found = [(a.get("name"), a.get("musicBrainzId")) for a in _items(starred, "artist")]
        return found + [(item.get("artist"), None) for kind in ("album", "song") for item in _items(starred, kind)]

    def _site_artists(self, user):
        """Artistes des albums les plus écoutés du sub (sans favori) : servent seulement aux styles génériques."""
        try:
            raw = self.subsonic.call(Credentials.of(user), "getAlbumList2", [("type", "frequent"),
                                                                              ("size", SITE_ALBUMS)])
        except SUBSONIC_ERRORS:
            return []
        return self._resolve_all([(album.get("artist"), None) for album in _items(raw.get("albumList2"), "album")])[0]

    def _resolve_all(self, candidates):
        """([(MBID, nom)], complet), sans doublon, TREND_ARTISTS au plus."""
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
        """MBID de l'unique artiste MusicBrainz qui porte exactement ce nom, mémorisé en base. Aucun ou plusieurs
        (deux « Air ») : None, et le nom n'est recherché de nouveau qu'après RESOLVE_AGAIN_AFTER secondes."""
        key = normalize(name)
        known = self.names.get(key)
        if known and (known[0] or self.clock() - known[1] < RESOLVE_AGAIN_AFTER):
            return known[0]
        if self._attempts >= TREND_RESOLVE_ATTEMPTS:
            return None
        self._attempts += 1
        try:
            artists = self.musicbrainz.search_artists(name).value
        except SERVICE_ERRORS:
            raise Incomplete() from None
        matches = {artist.id for artist in artists if normalize(artist.name) == key}
        identity = matches.pop() if len(matches) == 1 else None
        self.names.save(key, identity, self.clock())
        return identity

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
            raise Incomplete() from None              # nouvel essai à la prochaine synchronisation
        label = (found.label.id, found.label.name, found.release_id) if found else (None, None, None)
        self.album_labels.save(album["id"], *label, self.clock())
        return self.album_labels.get(album["id"])

    # ---------- styles dominants ----------
    def _dominant_styles(self, artist_ids):
        """([style], complet) : les styles portés par le plus d'artistes (au moins MIN_STYLE_ARTISTS)."""
        if not artist_ids:
            return [], True
        try:
            catalog = {genre.name for genre in self.musicbrainz.release_genres()}
        except SERVICE_ERRORS:
            return [], False
        counts, complete = {}, True
        for index in range(0, len(artist_ids), IDS_PER_QUERY):
            try:
                tags = self.musicbrainz.artists_tags(artist_ids[index:index + IDS_PER_QUERY])
            except SERVICE_ERRORS:
                complete = False                      # les autres lots comptent quand même
                continue
            for artist_tags in tags.values():
                for style in [tag for tag in artist_tags if tag in catalog][:STYLES_PER_ARTIST]:
                    counts[style] = counts.get(style, 0) + 1
        ranked = sorted((style for style, count in counts.items() if count >= MIN_STYLE_ARTISTS),
                        key=lambda style: (-counts[style], style))
        return ranked[:TREND_STYLES], complete
