"""Demandes de réindexation Subsonic partagées par les envois et l'édition de tags."""
import threading
import time

from .subsonic import Credentials, SubsonicError, SubsonicUnreachable

NOT_AUTHORIZED = 50
BAD_CREDENTIALS = 40


class LibraryScan:
    def __init__(self, subsonic, users, clock=time.monotonic, sleep=time.sleep):
        self.subsonic, self.users = subsonic, users
        self.clock, self.sleep = clock, sleep
        self._lock = threading.Lock()
        self._cycle_lock = threading.Lock()

    def _accounts(self, user):
        admins = [u for u in self.users.by_priority() if u.is_admin and u.id != user.id][:3]
        return [user] + admins

    def scan(self, user):
        return self._start_with(self._accounts(user)) is not None

    def scan_as_admin(self):
        return self._start_with([u for u in self.users.by_priority() if u.is_admin][:3]) is not None

    def _start_with(self, accounts):
        # Une demande par lot ; les contrôles de fin sont séparés pour les appelants qui les demandent.
        with self._lock:
            for user in accounts:
                try:
                    self.subsonic.call(Credentials.of(user), "startScan")
                    return user
                except SubsonicError as error:
                    if error.code not in (NOT_AUTHORIZED, BAD_CREDENTIALS):
                        return None
                except SubsonicUnreachable:
                    return None
        return None

    def synchronize(self, user):
        """Attendre le scan précédent avant d'en lancer un couvrant les fichiers qui viennent d'être écrits."""
        accounts = self._accounts(user)
        with self._cycle_lock:
            observer, scanning = self._observer(accounts)
            if scanning is True and not self.wait(observer):
                return None
            starter = self._start_with(accounts)
            if starter is None:
                return False
            return True if self.wait(starter) else None

    def _observer(self, accounts):
        """Un droit d'édition n'autorise pas forcément l'observation des scans Subsonic."""
        for account in accounts:
            try:
                return account, self._status(account)
            except SubsonicError as error:
                if error.code not in (NOT_AUTHORIZED, BAD_CREDENTIALS):
                    return None, None
            except SubsonicUnreachable:
                return None, None
        return None, None

    def _status(self, user):
        raw = self.subsonic.call(Credentials.of(user), "getScanStatus").get("scanStatus")
        return raw["scanning"] if isinstance(raw, dict) and type(raw.get("scanning")) is bool else None

    def _scanning(self, user):
        try:
            return self._status(user)
        except (SubsonicError, SubsonicUnreachable):
            return None

    def wait(self, user, timeout=90):
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            scanning = self._scanning(user)
            if scanning is None:
                return False
            if not scanning:
                return True
            self.sleep(1)
        return False
