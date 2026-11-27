"""Synchronisation de fond du radar : les appels MusicBrainz se font ici (au démarrage si la dernière synchronisation
complète date de plus de 24 h, puis chaque nuit), jamais à l'affichage de la page.

Une source suivie par plusieurs comptes ne coûte qu'une requête. Les sorties des artistes viennent de ListenBrainz :
deux requêtes pour tout le site, puis rapprochement local par MBID (« Mes artistes », « Autour de… »)."""
import threading
import time
from datetime import date, datetime, time as day_time, timedelta

from ...shared.providers.musicbrainz.client import MAX_LIMIT
from .entities import RadarError, RadarRelease
from .limits import (ARTIST, COVER_LOOKUPS, FRESH, FRESH_IDENTITY, FULL_SYNC_EVERY, LABEL, NIGHT_HOUR, PURGE_AFTER,
                     REFRESH_COOLDOWN, RETRY_FAILED_AFTER, STYLE, STYLE_PAGES_PER_WEEK, SYNC_CHECK_EVERY, WINDOW_AFTER, WINDOW_BEFORE)
from .trends import SERVICE_ERRORS


def radar_release(album):
    return RadarRelease(album.id, album.title, album.artist, album.released_on, album.kind, album.tags,
                        album.artist_ids, album.cover)


def _spawn(work):
    threading.Thread(target=work, daemon=True).start()


def _log(text):
    print(text, flush=True)


class ReleaseSync:
    def __init__(self, musicbrainz, listenbrainz, trends, sources, releases, profiles, users, lastfm=None,
                 today=date.today, clock=time.time, sleep=time.sleep, spawn=_spawn, log=_log):
        self.musicbrainz, self.listenbrainz, self.trends, self.sources = musicbrainz, listenbrainz, trends, sources
        self.lastfm = lastfm
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
        """Synchronise si c'est l'heure ; sinon réessaie les sources en échec depuis RETRY_FAILED_AFTER secondes.
        True si une synchronisation complète a eu lieu."""
        if self.due():
            return self.sync_all()
        self.retry_failed()
        return False

    def retry_failed(self):
        failing = self.releases.failing_since(self.clock() - RETRY_FAILED_AFTER)
        sources = [source for source in self.sources.active_union() if source[:2] in failing]
        fresh = (FRESH, FRESH_IDENTITY) in failing
        if not (sources or fresh) or not self._running.acquire(blocking=False):
            return                                    # rien à reprendre, ou une synchronisation complète tourne
        try:
            if fresh:
                self.sync_fresh()
            self.sync_sources(sources)
        finally:
            self._running.release()

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
            self.sync_fresh()
            self.fill_covers()                        # les pochettes arrivent tôt ; le reste est complété à la fin
            for user in self.users():
                self._refresh_trends(user)
            known = {source[:2] for source in existing}
            self.sync_sources([source for source in self.sources.active_union() if source[:2] not in known])
            self.fill_covers()
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
            self.sync_fresh()
            self._refresh_trends(user)
            self.sync_sources([(s.kind, s.identity, s.name) for s in self.sources.for_user(user.id)])
        self._enqueue(("user", user.id), work)
        return now + REFRESH_COOLDOWN

    def sync_sources(self, sources):
        """Styles et labels : une requête MusicBrainz chacun. Un artiste n'a rien à demander : ses sorties viennent
        de la lecture ListenBrainz commune (sync_fresh)."""
        start, end = self.window()
        for kind, identity, name in sources:
            if kind == STYLE:
                self._guarded([(kind, identity)], name, lambda: self._style(identity, start, end))
            elif kind == LABEL:
                self._guarded([(kind, identity)], name, lambda: self._label(identity, start, end))

    def sync_fresh(self):
        """Toutes les sorties récentes et à venir (ListenBrainz), gardées avec leurs artistes crédités."""
        start, end = self.window()
        artists = [(kind, identity) for kind, identity, _ in self.sources.active_union() if kind == ARTIST]
        self._guarded([(FRESH, FRESH_IDENTITY)] + artists, "ListenBrainz", lambda: self._fresh(start, end))

    def fill_covers(self):
        """Pochettes absentes de Cover Art Archive (selon ListenBrainz) ou inconnues : une recherche Last.fm par
        sortie, une seule fois (le résultat, même vide, est gardé)."""
        if self.lastfm is None or not self.lastfm.enabled:
            return
        start, end = self.window()
        for release in self.releases.without_cover(start, end, COVER_LOOKUPS):
            try:
                cover = self.lastfm.album_cover(release.artist, release.title)
            except SERVICE_ERRORS as error:
                self.log("Radar des sorties : pochette de %s introuvable pour l'instant (%r)" % (release.title, error))
                continue
            self.releases.set_cover(release.id, cover, self.clock())

    def _guarded(self, keys, names, work):
        """Une panne n'efface rien : la source garde ses sorties, l'échec et sa raison sont notés, et la source est
        réessayée RETRY_FAILED_AFTER secondes plus tard."""
        try:
            work()
        except SERVICE_ERRORS as error:
            self.log("Radar des sorties : %s en échec (%r)" % (names, error))
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

    def _fresh(self, start, end):
        releases = self.listenbrainz.fresh_releases(self.today(), start, end)
        self.releases.save(FRESH, FRESH_IDENTITY, [radar_release(a) for a in releases], start, end)
