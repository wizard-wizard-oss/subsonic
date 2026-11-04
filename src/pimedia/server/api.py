"""Appels à Subsonic avec cache : réponses JSON et pochettes."""
import json
import threading
from collections import namedtuple

from .constants import STALE_WHILE_REVALIDATE_MIN_TTL
from .tasks import in_background

ApiResult = namedtuple("ApiResult", "status ctype body state")


def is_ok(body):
    """Vrai si le corps est une réponse Subsonic de statut « ok »."""
    try:
        return json.loads(body)["subsonic-response"]["status"] == "ok"
    except (ValueError, KeyError, TypeError):
        return False


class _Job:
    def __init__(self):
        self.event = threading.Event()
        self.result = None
        self.error = None


class SharedCalls:
    """Si le même appel est déjà en cours (ex. : préchargement), on attend son résultat
    au lieu de relancer une requête sur un serveur déjà occupé."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}

    def run(self, key, func, wait_seconds):
        job, leader = self._join(key)
        if leader:
            self._execute(key, job, func)
        else:
            job.event.wait(wait_seconds)
        if job.error is not None:
            raise job.error
        if job.result is None:
            raise TimeoutError("délai dépassé")
        return job.result

    def _join(self, key):
        with self._lock:
            job = self._jobs.get(key)
            if job is not None:
                return job, False
            job = self._jobs[key] = _Job()
            return job, True

    def _execute(self, key, job, func):
        try:
            job.result = func()
        except Exception as error:      # noqa: BLE001 - relancée chez tous ceux qui attendent
            job.error = error
        finally:
            with self._lock:
                self._jobs.pop(key, None)
            job.event.set()


class CachedApi:
    """Appels JSON à Subsonic : cache, version périmée servie le temps d'un rafraîchissement,
    appels identiques regroupés, et traduction en parcours par dossiers quand ce mode est choisi."""

    HEAVY_TIMEOUTS = {"getArtists": 300, "getIndexes": 300, "getAlbumList2": 180, "getGenres": 180, "search3": 120}
    DEFAULT_TIMEOUT = 60

    def __init__(self, client, cache, policy, keys, browse):
        self.client = client
        self.cache = cache
        self.policy = policy
        self.keys = keys
        self.browse = browse
        self.shared = SharedCalls()
        self.folders = None             # FolderAdapter, branché par l'application (dépendance circulaire)

    def timeout_for(self, endpoint):
        return self.HEAVY_TIMEOUTS.get(endpoint, self.DEFAULT_TIMEOUT)

    # --- appels publics ---
    def call(self, endpoint, params):
        """Appel JSON avec cache. params : liste de couples (nom, valeur)."""
        ttl = self.policy.ttl_for(endpoint, dict(params))
        key = self.keys.for_call(endpoint, params)
        if ttl <= 0:
            return self._fetch(endpoint, params, key, 0)
        entry = self.cache.get(key)
        if entry:
            return ApiResult(200, entry.ctype, entry.body, "HIT")
        stale = self.cache.get(key, allow_stale=True)
        if stale and ttl >= STALE_WHILE_REVALIDATE_MIN_TTL:
            in_background(self._fetch_shared, endpoint, params, key, ttl)
            return ApiResult(200, stale.ctype, stale.body, "STALE")
        return self._fetch_shared(endpoint, params, key, ttl)

    def call_json(self, endpoint, params=()):
        """Comme call, mais retourne le contenu de « subsonic-response » (erreur si le statut n'est pas ok)."""
        result = self.call(endpoint, list(params))
        response = json.loads(result.body)["subsonic-response"]
        if response.get("status") != "ok":
            raise RuntimeError((response.get("error") or {}).get("message", "Erreur Subsonic"))
        return response

    def call_fresh(self, endpoint, params):
        """Appel sans lire ni écrire le cache (détection de nouveautés)."""
        return self._fetch(endpoint, params, self.keys.for_call(endpoint, params), 0)

    # --- coulisses ---
    def _fetch_shared(self, endpoint, params, key, ttl):
        return self.shared.run(key, lambda: self._fetch(endpoint, params, key, ttl),
                               self.timeout_for(endpoint) + 10)

    def _fetch(self, endpoint, params, key, ttl):
        try:
            status, ctype, body = self._remote(endpoint, params)
        except Exception:
            stale = self.cache.get(key, allow_stale=True) if ttl > 0 else None
            if stale:
                return ApiResult(200, stale.ctype, stale.body, "STALE")
            raise
        if status == 200 and is_ok(body):
            self._store(endpoint, params, key, ttl, ctype, body)
        return ApiResult(status, ctype, body, "MISS")

    def _remote(self, endpoint, params):
        """Un appel réel : directement à Subsonic, ou traduit en parcours par dossiers."""
        if self.browse.uses_folders(endpoint):
            payload = {"subsonic-response": self.folders.translate(endpoint, params)}
            return 200, "application/json", json.dumps(payload, ensure_ascii=False).encode("utf-8")
        response = self.client.open(endpoint, params, timeout=self.timeout_for(endpoint))
        try:
            status = getattr(response, "status", None) or response.code
            return status, response.headers.get("Content-Type", "application/json"), response.read()
        finally:
            response.close()

    def _store(self, endpoint, params, key, ttl, ctype, body):
        if ttl > 0:
            self.cache.put(key, endpoint, params, ttl, ctype, body)
        if self.policy.is_write(endpoint):
            self._invalidate_after_write(endpoint, params)

    def _invalidate_after_write(self, endpoint, params):
        rule = self.policy.stale_rule(endpoint, dict(params))
        if rule:
            self.cache.invalidate(rule)


class CoverService:
    """Pochettes : cache disque de longue durée, version ancienne servie si Subsonic est injoignable."""

    def __init__(self, client, covers, keys):
        self.client = client
        self.covers = covers
        self.keys = keys

    def get(self, params):
        key = self.keys.for_call("getCoverArt", params)
        cached = self.covers.get(key)
        if cached:
            return ApiResult(200, cached[0], cached[1], "HIT")
        try:
            status, ctype, body = self._download(params)
        except Exception:
            old = self.covers.get(key, allow_stale=True)
            if old:
                return ApiResult(200, old[0], old[1], "HIT")
            raise
        if status == 200 and ctype.startswith("image/"):
            self.covers.put(key, ctype, body)
        return ApiResult(status, ctype, body, "MISS")

    def _download(self, params):
        response = self.client.open("getCoverArt", params)
        try:
            status = getattr(response, "status", None) or response.code
            return status, response.headers.get("Content-Type", "image/jpeg"), response.read()
        finally:
            response.close()
