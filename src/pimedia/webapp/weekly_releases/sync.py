"""Synchronisation de fond du radar : les appels MusicBrainz se font ici (au démarrage si la dernière synchronisation
complète date de plus de 24 h, puis chaque nuit), jamais à l'affichage de la page.

Une source suivie par plusieurs comptes ne coûte qu'une requête ; les artistes sont interrogés par lots."""
import threading
import time
from datetime import date, datetime, time as day_time, timedelta

from ...shared.providers.musicbrainz.client import IDS_PER_QUERY, MAX_LIMIT
from .entities import RadarError, RadarRelease
from .limits import (ARTIST_PAGES, FULL_SYNC_EVERY, NIGHT_HOUR, PURGE_AFTER, REFRESH_COOLDOWN, STYLE_PAGES_PER_WEEK,
                     SYNC_CHECK_EVERY, WINDOW_AFTER, WINDOW_BEFORE)
from .trends import SERVICE_ERRORS

ARTIST_KINDS = ("artist", "similar")


def radar_release(album):
    return RadarRelease(album.id, album.title, album.artist, album.released_on, album.kind, album.tags)


def _spawn(work):
    threading.Thread(target=work, daemon=True).start()


class ReleaseSync:
    def __init__(self, musicbrainz, trends, sources, releases, profiles, users, today=date.today, clock=time.time,
                 sleep=time.sleep, spawn=_spawn):
        self.musicbrainz, self.trends, self.sources = musicbrainz, trends, sources
        self.releases, self.profiles, self.users = releases, profiles, users
        self.today, self.clock, self.sleep, self.spawn = today, clock, sleep, spawn
        self._running = threading.Lock()

    def window(self):
        today = self.today()
        return today - WINDOW_BEFORE, today + WINDOW_AFTER

    # ---------- quand synchroniser ----------
    def run(self):
        while True:
            self.tick()
            self.sleep(SYNC_CHECK_EVERY)

    def tick(self):
        """Synchronise si c'est l'heure ; True si une synchronisation complète a eu lieu."""
        if not self.due():
            return False
        return self.sync_all()

    def due(self):
        last, now = self.releases.last_full_sync(), self.clock()
        if last is None or now - last >= FULL_SYNC_EVERY:
            return True
        night = datetime.combine(datetime.fromtimestamp(now).date(), day_time(NIGHT_HOUR)).timestamp()
        return last < night <= now

    # ---------- quoi synchroniser ----------
    def sync_all(self):
        if not self._running.acquire(blocking=False):
            return False                              # une synchronisation complète tourne déjà
        try:
            for user in self.users():
                self.trends.refresh(user)
            self.sync_sources(self.releases.oldest_first(self.sources.active_union()))
            self.releases.purge(self.today() - PURGE_AFTER)
            self.releases.mark_full_sync(self.clock())
            return True
        finally:
            self._running.release()

    def sync_new_source(self, source):
        self.spawn(lambda: self.sync_sources([(source.kind, source.identity, source.name)]))

    def refresh_user(self, user):
        """« Actualiser » : tendances et sources du compte, au plus une fois toutes les REFRESH_COOLDOWN secondes.
        Renvoie l'heure à partir de laquelle on pourra recommencer."""
        now, last = int(self.clock()), self.profiles.refresh_requested_at(user.id)
        if last is not None and now - last < REFRESH_COOLDOWN:
            raise RadarError("weekly.refresh_too_soon", 429)
        self.profiles.request_refresh(user.id, now)

        def work():
            self.trends.refresh(user)
            self.sync_sources([(s.kind, s.identity, s.name) for s in self.sources.for_user(user.id)])
        self.spawn(work)
        return now + REFRESH_COOLDOWN

    def sync_sources(self, sources):
        start, end = self.window()
        artists = [source for source in sources if source[0] in ARTIST_KINDS]
        for kind, identity, name in sources:
            if kind == "style":
                self._guarded([(kind, identity)], lambda: self._style(identity, start, end))
            elif kind == "label":
                self._guarded([(kind, identity)], lambda: self._label(identity, start, end))
        for index in range(0, len(artists), IDS_PER_QUERY):
            chunk = [(kind, identity) for kind, identity, _ in artists[index:index + IDS_PER_QUERY]]
            self._guarded(chunk, lambda: self._artists(chunk, start, end))

    def _guarded(self, keys, work):
        """Une panne n'efface rien : la source garde ses sorties, l'échec est noté, la nuit suivante réessaie."""
        try:
            work()
        except SERVICE_ERRORS:
            for kind, identity in keys:
                self.releases.mark_failed(kind, identity, self.clock())
            return
        for kind, identity in keys:
            self.releases.mark_synced(kind, identity, self.clock())

    # ---------- requêtes ----------
    def _style(self, name, start, end):
        """Une requête par semaine : un style large dépasserait tout plafond sur toute la fenêtre."""
        monday = start - timedelta(days=start.weekday())
        while monday <= end:
            sunday, found = monday + timedelta(days=6), []
            for page in range(STYLE_PAGES_PER_WEEK):
                result = self.musicbrainz.weekly_groups(name, monday, sunday, MAX_LIMIT, page * MAX_LIMIT)
                found += result.albums
                if result.next_offset is None:
                    break
            self.releases.save("style", name, [radar_release(a) for a in found], monday, sunday)
            monday += timedelta(days=7)

    def _label(self, identity, start, end):
        page = self.musicbrainz.label_groups(identity, start, end)
        self.releases.save("label", identity, [radar_release(a) for a in page.albums], start, end)

    def _artists(self, keys, start, end):
        ids, found, offset = list(dict.fromkeys(identity for _, identity in keys)), [], 0
        for _ in range(ARTIST_PAGES):
            page = self.musicbrainz.groups_by_artists(ids, start, end, offset)
            found += page.albums
            if page.next_offset is None:
                break
            offset = page.next_offset
        for kind, identity in keys:
            mine = [radar_release(a) for a in found if identity in a.artist_ids]
            self.releases.save(kind, identity, mine, start, end)
