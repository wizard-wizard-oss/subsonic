"""Radar des sorties d'un compte, lu en base : aucune requête MusicBrainz à l'affichage ni au changement de semaine.
« Mes artistes » rapproche par MBID les sorties ListenBrainz gardées ; « Autour de… » y cherche les proches qu'indique
Last.fm (une requête). Les sources se gèrent ici ; la synchronisation (ReleaseSync) remplit la base."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from ...shared.providers.musicbrainz.parsing import mbid as valid_mbid
from ...shared.text import normalize
from ..library.cache import TtlCache
from ..subsonic import SubsonicError, SubsonicUnreachable
from .entities import RadarCard, RadarError, RadarFilter, RadarRefresh, RadarSearch, RadarSettings, RadarSource, RadarWeek
from .limits import (ARTIST, AROUND_SIMILAR, FRESH, FRESH_IDENTITY, KINDS, LABEL, LOCAL_CACHE_SECONDS,
                     LOCAL_LOOKUPS_IN_PARALLEL, MANUAL, MANUAL_KINDS, MAX_NAME, RADAR_PAGE, REFRESH_COOLDOWN,
                     SEARCH_KINDS, STYLE, WINDOW_AFTER, WINDOW_BEFORE)

STYLE_FILTER = STYLE + ":"
FILTER_KINDS = {"labels": LABEL, "artists": ARTIST}
AROUND = "around"


def _text(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= MAX_NAME:
        raise ValueError("radar")
    return value.strip()


class RadarService:
    def __init__(self, musicbrainz, lastfm, sources, releases, profiles, sync, styles, local, today=date.today,
                 clock=time.time):
        self.musicbrainz, self.lastfm, self.sources, self.releases = musicbrainz, lastfm, sources, releases
        self.profiles, self.sync, self.styles, self.local = profiles, sync, styles, local
        self.today, self.clock = today, clock
        self.local_cache = TtlCache(LOCAL_CACHE_SECONDS, clock)

    # ---------- la semaine ----------
    def _monday(self, start, offset):
        monday = date.fromisoformat(start or "")
        if monday.weekday() or not isinstance(offset, int) or offset < 0 or offset % RADAR_PAGE:
            raise ValueError("week")
        return monday

    def _in_window(self, monday):
        today = self.today()
        return monday + timedelta(days=6) >= today - WINDOW_BEFORE and monday <= today + WINDOW_AFTER

    def week(self, user, start, selected="all", offset=0):
        """Une semaine du radar. Dans la fenêtre synchronisée : lue en base. Plus ancienne : cherchée d'abord à la
        demande pour les sources du compte (quelques dizaines de secondes, une fois par jour). Trop loin dans le
        futur : consultation par style."""
        monday = self._monday(start, offset)
        older = monday + timedelta(days=6) < self.today() - WINDOW_BEFORE
        if not older and not self._in_window(monday):
            return RadarWeek(monday, out_of_window=True, default_style=self.styles.DEFAULT_GENRE)
        sources = self.sources.for_user(user.id)
        if not sources:
            return RadarWeek(monday, empty="no-sources", default_style=self.styles.DEFAULT_GENRE)
        if older and not offset:
            self.sync.sync_week(user, monday)
        cards = self._cards(sources, monday, monday + timedelta(days=6))
        filters = self._filters(sources, cards)
        if selected not in {f.key for f in filters}:
            raise ValueError("filter")
        shown = [card for card in cards if self._matches(card, selected)]
        keys = {s.key for s in sources} | ({(FRESH, FRESH_IDENTITY)} if any(s.kind == ARTIST for s in sources) else set())
        return RadarWeek(monday, tuple(self._with_local(user, shown[offset:offset + RADAR_PAGE])), tuple(filters),
                         selected, self._next(offset, shown), self.releases.last_synced(keys),
                         self._refresh_after(user), default_style=self.styles.DEFAULT_GENRE,
                         basis=self.profiles.basis(user.id))

    @staticmethod
    def _next(offset, shown):
        return offset + RADAR_PAGE if offset + RADAR_PAGE < len(shown) else None

    def _cards(self, sources, monday, sunday):
        """Sorties des styles et labels suivis (liens gardés par la synchronisation) et des artistes suivis
        (rapprochement par MBID avec les sorties ListenBrainz), par date puis par titre."""
        by_key, reasons, releases = {s.key: s for s in sources}, {}, {}
        for release, kind, identity in self.releases.for_sources(set(by_key), monday, sunday):
            releases[release.id] = release
            reasons.setdefault(release.id, []).append(by_key[(kind, identity)])
        artists = {s.identity: s for s in sources if s.kind == ARTIST}
        for release in self.releases.window(monday, sunday):
            for artist_id in set(release.artist_ids) & set(artists):
                releases[release.id] = release
                reasons.setdefault(release.id, []).append(artists[artist_id])
        return _by_date([RadarCard(release, tuple(reasons[release.id])) for release in releases.values()])

    @staticmethod
    def _matches(card, selected):
        if selected == "all":
            return True
        if selected.startswith(STYLE_FILTER):
            return any(r.kind == STYLE and r.identity == selected[len(STYLE_FILTER):] for r in card.reasons)
        return any(r.kind == FILTER_KINDS[selected] for r in card.reasons)

    def _filters(self, sources, cards):
        styles = sorted((s for s in sources if s.kind == STYLE), key=lambda s: s.name.casefold())
        keys = ["all"] + [STYLE_FILTER + s.identity for s in styles] + ["labels", "artists"]
        return [RadarFilter(key, sum(1 for card in cards if self._matches(card, key)),
                            key[len(STYLE_FILTER):] if key.startswith(STYLE_FILTER) else None) for key in keys]

    # ---------- autour d'un artiste ----------
    def around(self, user, name, artist_id, start, offset=0):
        """Sorties de la semaine des proches d'un artiste selon Last.fm, cherchées parmi les sorties ListenBrainz
        gardées : par MBID quand Last.fm le donne, sinon par nom normalisé."""
        name, monday = _text(name), self._monday(start, offset)
        if not self.lastfm.enabled:
            raise RadarError("weekly.around_unavailable", 503)
        if not self._in_window(monday):
            return RadarWeek(monday, out_of_window=True, around=name, default_style=self.styles.DEFAULT_GENRE)
        neighbours = [s for s in self.lastfm.similar_artists(name, AROUND_SIMILAR)
                      if s.mbid != artist_id and normalize(s.name) != normalize(name)]
        by_id = {s.mbid: s for s in neighbours if s.mbid}
        by_name = {normalize(s.name): s for s in neighbours}
        cards = []
        for release in self.releases.window(monday, monday + timedelta(days=6)):
            found = [by_id[i] for i in release.artist_ids if i in by_id] or \
                [by_name[key] for key in [normalize(release.artist)] if key in by_name]
            if found:
                reasons = tuple(RadarSource(0, ARTIST, s.mbid or normalize(s.name), s.name, MANUAL, via=name)
                                for s in found)
                cards.append(RadarCard(release, reasons))
        shown = _by_date(cards)
        return RadarWeek(monday, tuple(self._with_local(user, shown[offset:offset + RADAR_PAGE])), (), AROUND,
                         self._next(offset, shown), self.releases.last_synced({(FRESH, FRESH_IDENTITY)}),
                         self._refresh_after(user), around=name, default_style=self.styles.DEFAULT_GENRE)

    def _with_local(self, user, cards):
        with ThreadPoolExecutor(LOCAL_LOOKUPS_IN_PARALLEL) as pool:
            found = list(pool.map(lambda card: self._local_copy(user, card.release), cards))
        return [RadarCard(card.release, card.reasons, local) for card, local in zip(cards, found)]

    def _local_copy(self, user, release):
        """L'album de la bibliothèque quand il y en a exactement un de ce titre et de cet artiste."""
        def look_up():
            try:
                albums = self.local(user, release.title, release.artist)["albums"]
            except (SubsonicError, SubsonicUnreachable, ValueError, LookupError):
                return None                           # cette carte garde « Écouter » ; la semaine s'affiche quand même
            if len(albums) != 1:
                return None
            return {key: albums[0].get(key) for key in ("id", "coverId", "folderId")}
        return self.local_cache.get((user.id, release.id), look_up)

    def _refresh_after(self, user):
        last = self.profiles.refresh_requested_at(user.id)
        return last + REFRESH_COOLDOWN if last is not None else None

    # ---------- sources et réglages ----------
    def settings(self, user):
        return RadarSettings(tuple(self.sources.for_user(user.id)), bool(self.lastfm.enabled), REFRESH_COOLDOWN,
                             KINDS, MANUAL_KINDS, self.profiles.basis(user.id), self._refresh_after(user))

    def add_source(self, user, kind, identity, name):
        if kind not in MANUAL_KINDS:
            raise ValueError("source")
        if kind == STYLE:
            identity = name = self.styles.genre(identity).name
        else:
            identity, name = valid_mbid(identity), _text(name)
        source = self.sources.add(user.id, kind, identity, name, MANUAL)
        self.sync.sync_new_source(source)
        return source

    def hide_source(self, user, source_id):
        if not isinstance(source_id, int) or isinstance(source_id, bool):
            raise ValueError("source")
        self.sources.hide(user.id, source_id)

    def search(self, kind, query):
        if kind not in SEARCH_KINDS:
            raise ValueError("search")
        query = _text(query)
        result = self.musicbrainz.search_labels(query) if kind == LABEL else self.musicbrainz.search_artists(query)
        return RadarSearch(tuple(result.value), result.stale)

    def refresh(self, user):
        return RadarRefresh(self.sync.refresh_user(user))


def _by_date(cards):
    return sorted(cards, key=lambda card: (card.release.released_on, card.release.title.casefold(), card.release.id))
