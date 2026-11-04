"""Rattrapage d'Incoming : ce qui y attend (envoyé hors nomenclature, ou déposé à la main) et qu'on a corrigé sur place en
Incoming/Artiste/Album prend sa place dans la bibliothèque (layout.MusicTree), sans attendre un nouvel envoi. Un album n'est
rangé qu'une fois resté sans changement pendant le délai réglé (on est peut-être encore en train de le renommer).
Après un rangement, Subsonic scanne."""
import os
import time

CHECK_EVERY = 600
HOUR = 3600
JUNK = ("__MACOSX",)                             # restes du Finder de macOS, jamais rangés


class IncomingSorter:
    def __init__(self, library, wait_hours, scanner, clock=time.time, log=print):
        self.library = library
        self.incoming = library.incoming
        self.wait_hours = wait_hours
        self.scanner = scanner                   # lance startScan avec un administrateur ; True si lancé
        self.clock = clock
        self.log = log

    @property
    def enabled(self):
        return bool(self.incoming) and self.wait_hours > 0

    def run(self, every=CHECK_EVERY):
        while True:
            try:
                self.sort()
            except OSError as error:
                self.log("Incoming : rangement impossible (%s)" % error)
            time.sleep(every)

    def sort(self):
        """Range les albums prêts ; renvoie leurs places (« Artiste/Album ») et fait scanner Subsonic s'il y en a."""
        if not self.enabled or not os.path.isdir(self.incoming):
            return []
        placed = []
        for artist in self._folders(self.incoming):
            for album in self._folders(os.path.join(self.incoming, artist)):
                folder = os.path.join(self.incoming, artist, album)
                if self.clock() - self._last_change(folder) >= self.wait_hours * HOUR:
                    where = self.library.place(folder, artist, album)
                    if where:
                        placed.append(where)
            self._remove_if_empty(os.path.join(self.incoming, artist))
        if placed:
            self.log("Incoming : rangé dans la bibliothèque : " + ", ".join(placed))
            self.scanner()
        return placed

    @staticmethod
    def _folders(path):
        return sorted(name for name in os.listdir(path)
                      if not name.startswith(".") and name not in JUNK and os.path.isdir(os.path.join(path, name)))

    @staticmethod
    def _last_change(folder):
        """Date de la dernière modification dans l'album (fichiers et dossiers)."""
        return max([os.stat(folder).st_mtime] + [os.stat(os.path.join(root, name)).st_mtime
                                                 for root, dirs, files in os.walk(folder) for name in dirs + files])

    @staticmethod
    def _remove_if_empty(folder):
        """Un dossier d'artiste vidé quitte Incoming (avec ses restes cachés, comme .DS_Store)."""
        entries = os.listdir(folder)
        if all(name.startswith(".") and os.path.isfile(os.path.join(folder, name)) for name in entries):
            for name in entries:
                os.unlink(os.path.join(folder, name))
            os.rmdir(folder)
