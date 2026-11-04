"""Liste des artistes de la barre de gauche, une pour tout le site.

Elle suit les DOSSIERS de la bibliothèque (getIndexes : un dossier par artiste), pas les tags ID3 : « Dälek » n'y apparaît
qu'une fois même si certains titres disent « Dalek ». Les identifiants sont ceux des dossiers (« f123 », voir folders.py).
Le dossier Incoming (musique pas encore rangée) n'y figure pas.

Subsonic peut mettre longtemps à la calculer (getIndexes : 19 s sur music.foos.fr). Le site la calcule donc une fois, la
garde en base (elle survit aux redémarrages) et la sert à tout le monde tout de suite. Pour savoir s'il faut la
recalculer, il demande à Subsonic si un scan a eu lieu depuis (getIndexes avec ifModifiedSince : 0,1 s quand rien n'a
changé). Subsonic peut limiter les dossiers de musique d'un compte : il y a une liste par ensemble de dossiers visibles
(presque toujours une seule)."""
import threading
import time

from .entities import ArtistIndex
from .folders import folder_ref
from .library import TtlCache, as_list, mac_leftover, text
from .subsonic import SLOW_TIMEOUT, Credentials, SubsonicError, SubsonicUnreachable

# Marge pour la première comparaison : l'horloge de Subsonic peut avoir un peu d'avance sur la nôtre.
CLOCK_MARGIN_MS = 10 * 60 * 1000
CHECK_EVERY = 600


def parse_index(raw, hidden=()):
    """Réponse de getIndexes -> lettres et dossiers d'artistes, sans rien de propre à un compte (ni favoris ni notes).
    hidden : noms de dossiers à ne pas montrer (Incoming), majuscules mises à part ; ni les restes de macOS (__MACOSX)."""
    hidden = {name.casefold() for name in hidden}
    groups = [{"letter": text(group.get("name"), "#"),
               "artists": [{"id": folder_ref(a["id"]), "name": text(a.get("name"), "?")}
                           for a in as_list(group.get("artist"))
                           if text(a.get("name")).casefold() not in hidden and not mac_leftover(a)]}
              for group in as_list((raw.get("indexes") or {}).get("index"))]
    return [group for group in groups if group["artists"]]


class ArtistIndexes:
    def __init__(self, subsonic, repository, users, hub, hidden=(), shortcuts=(), clock=time.time):
        self.subsonic, self.repository, self.users, self.hub, self.clock = subsonic, repository, users, hub, clock
        self.hidden = hidden
        self.shortcut_names = shortcuts
        self.folder_cache = TtlCache(600)
        self._building = {}                      # dossiers -> verrou : un seul calcul à la fois par liste
        self._lock = threading.Lock()

    def shortcuts(self, index):
        """Dossiers épinglés en haut de la barre (« Compilations ») qui existent dans cette liste, dans l'ordre réglé."""
        found = {a["name"].casefold(): a for group in index for a in group["artists"]}
        return [found[name.casefold()] for name in self.shortcut_names if name.casefold() in found]

    def for_user(self, user):
        """La liste que voit ce compte. Seul le tout premier calcul (rien en base) fait attendre."""
        folders = self.folders(user)
        found = self.repository.get(folders)
        if found:
            return found.artists
        with self._building_lock(folders):
            found = self.repository.get(folders)          # calculée pendant qu'on attendait
            if found:
                return found.artists
            return self._build(user, folders, self._now_ms() - CLOCK_MARGIN_MS).artists

    def folders(self, user):
        def load():
            raw = self.subsonic.call(Credentials.of(user), "getMusicFolders").get("musicFolders") or {}
            return ",".join(sorted(str(f.get("id")) for f in as_list(raw.get("musicFolder"))))
        return self.folder_cache.get(("folders", user.username), load)

    # --- au démarrage, puis toutes les 10 minutes ---
    def warm_up(self):
        """Rien en base : calcule la liste avec un compte connu (administrateur d'abord). Sinon : compare."""
        if self.repository.all():
            return self.refresh()
        for user in self.users.by_priority():
            try:
                self.for_user(user)
                return
            except (SubsonicError, SubsonicUnreachable):
                continue                                   # jeton refusé (mot de passe changé…) : compte suivant

    def refresh(self):
        """Recalcule chaque liste gardée seulement si Subsonic a scanné la bibliothèque depuis."""
        for index in self.repository.all():
            try:
                self._refresh(index)
            except (SubsonicError, SubsonicUnreachable):
                continue

    def run(self, every=CHECK_EVERY):
        while True:
            try:
                self.warm_up()
            except (SubsonicError, SubsonicUnreachable):
                pass
            time.sleep(every)

    def _refresh(self, index):
        user = self._account_for(index.folders)
        if user is None:
            return
        raw = self.subsonic.call(Credentials.of(user), "getIndexes", [("ifModifiedSince", index.since)])
        scanned = (raw.get("indexes") or {}).get("lastModified")
        if not scanned:
            return                                          # rien de neuf
        with self._building_lock(index.folders):
            built = self._build(user, index.folders, int(scanned))
        if built.artists != index.artists:
            self.hub.publish("artists", {"folders": index.folders})     # les barres ouvertes se rechargent

    def _account_for(self, folders):
        for user in self.users.by_priority():
            try:
                if self.folders(user) == folders:
                    return user
            except (SubsonicError, SubsonicUnreachable):
                continue
        return None

    def _build(self, user, folders, since):
        raw = self.subsonic.call(Credentials.of(user), "getIndexes", timeout=SLOW_TIMEOUT)
        since = int((raw.get("indexes") or {}).get("lastModified") or since)
        index = ArtistIndex(folders, parse_index(raw, self.hidden), since, int(self.clock()))
        self.repository.save(index)
        return index

    def _building_lock(self, folders):
        with self._lock:
            return self._building.setdefault(folders, threading.Lock())

    def _now_ms(self):
        return int(self.clock() * 1000)
