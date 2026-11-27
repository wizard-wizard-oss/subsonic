"""Synchronisation de fond du radar : les appels MusicBrainz se font ici (au démarrage si la dernière synchronisation
complète date de plus de 24 h, puis chaque nuit), jamais à l'affichage de la page.

Une source suivie par plusieurs comptes ne coûte qu'une requête ; les artistes sont interrogés par lots."""
import threading
import time
from datetime import date, datetime, time as day_time, timedelta

from ...shared.providers.musicbrainz.client import IDS_PER_QUERY, MAX_LIMIT
from .entities import RadarError, RadarRelease
from .limits import (ARTIST_KINDS, ARTIST_PAGES, FULL_SYNC_EVERY, LABEL, NIGHT_HOUR, PURGE_AFTER, REFRESH_COOLDOWN,
                     STYLE, STYLE_PAGES_PER_WEEK, SYNC_CHECK_EVERY, WINDOW_AFTER, WINDOW_BEFORE)
from .trends import SERVICE_ERRORS


def radar_release(album):
    return RadarRelease(album.id, album.title, album.artist, album.released_on, album.kind, album.tags)


def _spawn(work):
    threading.Thread(target=work, daemon=True).start()


def _log(text):
    print(text, flush=True)


class ReleaseSync:
    def __init__(self, musicbrainz, trends, sources, releases, profiles, users, today=date.today, clock=time.time,
                 sleep=time.sleep, spawn=_spawn, log=_log):
        self.musicbrainz, self.trends, self.sources = musicbrainz, trends, sources
        self.releases, self.profiles, self.users = releases, profiles, users
        self.today, self.clock, self.sleep, self.spawn, self.log = today, clock, sleep, spawn, log
        self._running = threading.Lock()
        self._queue, self._queue_lock, self._worker = [], threading.Lock(), False

    def window(self):
        today = self.today()
        return today - WINDOW_BEFORE, today + WINDOW_AFTER

    # ---------- quand synchroniser ----------
    def run(self):
        """Ne s'arrête jamais : une erreur imprévue est journalisée et la vérification suivante a lieu quand même."""
        while True:
            try:
                self.tick()
            except Exception as error:                  # le fil de fond doit survivre à tout
                self.log("Radar des sorties : synchronisation interrompue (%r)" % (error,))
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
            # d'abord ce que les comptes suivent déjà (la page se remplit vite après une mise en production),
            # puis les tendances, puis les sources qu'elles viennent d'ajouter
            existing = self.releases.oldest_first(self.sources.active_union())
            self.sync_sources(existing)
            for user in self.users():
                self._refresh_trends(user)
            known = {source[:2] for source in existing}
            self.sync_sources([source for source in self.sources.active_union() if source[:2] not in known])
            self.releases.purge(self.today() - PURGE_AFTER)
            self.releases.mark_full_sync(self.clock())
            return True
        finally:
            self._running.release()

    def _refresh_trends(self, user):
        try:
            self.trends.refresh(user)
        except Exception as error:                      # un compte en erreur n'empêche pas les autres
            self.log("Radar des sorties : tendances du compte %s non calculées (%r)" % (user.id, error))

    # ---------- travail demandé depuis la page : une seule file, sans doublon ----------
    def _enqueue(self, key, work):
        with self._queue_lock:
            if any(queued == key for queued, _ in self._queue):
                return
            self._queue.append((key, work))
            start, self._worker = not self._worker, True
        if start:
            self.spawn(self._drain)

    def _drain(self):
        while True:
            with self._queue_lock:
                if not self._queue:
                    self._worker = False
                    return
                key, work = self._queue.pop(0)
            try:
                work()
            except Exception as error:
                self.log("Radar des sorties : %s interrompu (%r)" % (key, error))

    def sync_new_source(self, source):
        self._enqueue(("source", source.kind, source.identity),
                      lambda: self.sync_sources([(source.kind, source.identity, source.name)]))

    def refresh_user(self, user):
        """« Actualiser » : tendances et sources du compte, au plus une fois toutes les REFRESH_COOLDOWN secondes.
        Renvoie l'heure à partir de laquelle on pourra recommencer."""
        now, last = int(self.clock()), self.profiles.refresh_requested_at(user.id)
        if last is not None and now - last < REFRESH_COOLDOWN:
            raise RadarError("weekly.refresh_too_soon", 429)
        self.profiles.request_refresh(user.id, now)

        def work():
            self._refresh_trends(user)
            self.sync_sources([(s.kind, s.identity, s.name) for s in self.sources.for_user(user.id)])
        self._enqueue(("user", user.id), work)
        return now + REFRESH_COOLDOWN

    def sync_sources(self, sources):
        start, end = self.window()
        artists = [source for source in sources if source[0] in ARTIST_KINDS]
        for kind, identity, name in sources:
            if kind == STYLE:
                self._guarded([(kind, identity)], lambda: self._style(identity, start, end))
            elif kind == LABEL:
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
            self.releases.save(STYLE, name, [radar_release(a) for a in found], monday, sunday)
            monday += timedelta(days=7)

    def _label(self, identity, start, end):
        page = self.musicbrainz.label_groups(identity, start, end)
        self.releases.save(LABEL, identity, [radar_release(a) for a in page.albums], start, end)

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
