"""Radar des sorties d'un compte, lu en base : aucune requête MusicBrainz à l'affichage ni au changement de semaine.
Les sources se gèrent ici ; la synchronisation (ReleaseSync) remplit la base."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from ...shared.providers.musicbrainz.parsing import mbid as valid_mbid
from ..library.cache import TtlCache
from ..subsonic import SubsonicError, SubsonicUnreachable
from . import taste
from .entities import RadarCard, RadarFilter, RadarRefresh, RadarSearch, RadarSettings, RadarWeek
from .limits import (ARTIST, KINDS, LABEL, LOCAL_CACHE_SECONDS, LOCAL_LOOKUPS_IN_PARALLEL, MANUAL, MANUAL_KINDS,
                     MAX_NAME, RADAR_PAGE, REFRESH_COOLDOWN, SEARCH_KINDS, SIMILAR, STYLE, WINDOW_AFTER, WINDOW_BEFORE)

STYLE_FILTER = STYLE + ":"
FILTER_KINDS = {"labels": LABEL, "artists": ARTIST, "discoveries": SIMILAR}


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
    def week(self, user, start, selected="all", offset=0):
        monday = date.fromisoformat(start or "")
        if monday.weekday() or not isinstance(offset, int) or offset < 0 or offset % RADAR_PAGE:
            raise ValueError("week")
        sunday, today = monday + timedelta(days=6), self.today()
        if sunday < today - WINDOW_BEFORE or monday > today + WINDOW_AFTER:
            return RadarWeek(monday, out_of_window=True, default_style=self.styles.DEFAULT_GENRE)
        sources = self._visible_sources(user)
        if not sources:
            return RadarWeek(monday, empty="no-sources", default_style=self.styles.DEFAULT_GENRE)
        cards = self._cards(user, sources, monday, sunday)
        filters = self._filters(sources, cards, self.discoveries_on(user))
        if selected not in {f.key for f in filters}:
            raise ValueError("filter")
        shown = [card for card in cards if self._matches(card, selected)]
        page = shown[offset:offset + RADAR_PAGE]
        return RadarWeek(monday, tuple(self._with_local(user, page)), tuple(filters), selected,
                         offset + RADAR_PAGE if offset + RADAR_PAGE < len(shown) else None,
                         self.releases.last_synced({s.key for s in sources}), self._refresh_after(user),
                         default_style=self.styles.DEFAULT_GENRE)

    def _visible_sources(self, user):
        sources = self.sources.for_user(user.id)
        if self.discoveries_on(user):
            return sources
        return [source for source in sources if source.kind != SIMILAR]

    def discoveries_on(self, user):
        return self.discoveries_available and self.profiles.get(user.id)[1]

    def _cards(self, user, sources, monday, sunday):
        by_key, reasons, releases = {s.key: s for s in sources}, {}, {}
        for release, kind, identity in self.releases.for_sources(set(by_key), monday, sunday):
            releases[release.id] = release
            reasons.setdefault(release.id, []).append(by_key[(kind, identity)])
        profile = self.profiles.get(user.id)[0]
        return taste.rank([RadarCard(release, tuple(reasons[release.id]), taste.score(release.tags, profile))
                           for release in releases.values()])

    @staticmethod
    def _matches(card, selected):
        if selected == "all":
            return True
        if selected.startswith(STYLE_FILTER):
            return any(r.kind == STYLE and r.identity == selected[len(STYLE_FILTER):] for r in card.reasons)
        return any(r.kind == FILTER_KINDS[selected] for r in card.reasons)

    def _filters(self, sources, cards, discoveries):
        styles = sorted((s for s in sources if s.kind == STYLE), key=lambda s: s.name.casefold())
        keys = ["all"] + [STYLE_FILTER + s.identity for s in styles] + ["labels", "artists"]
        keys += ["discoveries"] if discoveries else []
        return [RadarFilter(key, sum(1 for card in cards if self._matches(card, key)),
                            key[len(STYLE_FILTER):] if key.startswith(STYLE_FILTER) else None) for key in keys]

    @property
    def discoveries_available(self):
        return bool(self.lastfm.enabled)

    def _with_local(self, user, cards):
        with ThreadPoolExecutor(LOCAL_LOOKUPS_IN_PARALLEL) as pool:
            found = list(pool.map(lambda card: self._local_copy(user, card.release), cards))
        return [RadarCard(card.release, card.reasons, card.score, local) for card, local in zip(cards, found)]

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
        return RadarSettings(tuple(self.sources.for_user(user.id)), self.profiles.get(user.id)[1],
                             self.discoveries_available, REFRESH_COOLDOWN, KINDS, MANUAL_KINDS,
                             self._refresh_after(user))

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

    def set_discoveries(self, user, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("discoveries")
        self.profiles.set_discoveries(user.id, enabled)

    def search(self, kind, query):
        if kind not in SEARCH_KINDS:
            raise ValueError("search")
        query = _text(query)
        result = self.musicbrainz.search_labels(query) if kind == LABEL else self.musicbrainz.search_artists(query)
        return RadarSearch(tuple(result.value), result.stale)

    def refresh(self, user):
        return RadarRefresh(self.sync.refresh_user(user))
