"""Connexion avec son compte Subsonic, sessions, limitation des essais."""
import dataclasses
import re
import threading
import time

from .subsonic import Credentials, SubsonicError, SubsonicUnreachable

USERNAME = re.compile(r"^[\w.@+-]{1,64}$")


class LoginRefused(Exception):
    """Mauvais identifiants (le message reste vague exprès)."""


class TooManyAttempts(Exception):
    pass


class LoginThrottle:
    """Au plus MAX_FAILURES échecs par adresse et par fenêtre de WINDOW secondes."""

    MAX_FAILURES = 8
    WINDOW = 600

    def __init__(self, clock=time.time):
        self.clock = clock
        self._failures = {}
        self._lock = threading.Lock()

    def _recent(self, key):
        now = self.clock()
        self._failures[key] = [t for t in self._failures.get(key, []) if now - t < self.WINDOW]
        return self._failures[key]

    def blocked(self, key):
        with self._lock:
            return len(self._recent(key)) >= self.MAX_FAILURES

    def failed(self, key):
        with self._lock:
            self._recent(key).append(self.clock())
            if len(self._failures) > 5000:            # mémoire bornée
                self._failures = {k: v for k, v in self._failures.items() if v}

    def reset(self, key):
        with self._lock:
            self._failures.pop(key, None)


class Accounts:
    def __init__(self, subsonic, users, sessions, throttle=None):
        self.subsonic = subsonic
        self.users = users
        self.sessions = sessions
        self.throttle = throttle or LoginThrottle()

    def login(self, username, password, address):
        """Renvoie (utilisateur, jeton de session). LoginRefused / TooManyAttempts / SubsonicUnreachable."""
        username = (username or "").strip()
        if self.throttle.blocked(address):
            raise TooManyAttempts()
        if not USERNAME.match(username) or not password:
            self.throttle.failed(address)
            raise LoginRefused()
        credentials = Credentials.from_password(username, password)
        valid, roles = self.subsonic.check_login(credentials)
        if not valid:
            self.throttle.failed(address)
            raise LoginRefused()
        self.throttle.reset(address)
        user = self.users.save_login(username, credentials.salt, credentials.token, roles)
        return user, self.sessions.create(user.id)

    def user_for(self, session_token):
        user_id = self.sessions.user_id(session_token)
        return self.users.get(user_id) if user_id else None

    def refresh_roles(self, user):
        """Droits relus dans Subsonic (un administrateur a pu les changer) ; gardés tels quels s'il ne répond pas."""
        try:
            roles = self.subsonic.roles(Credentials.of(user))
        except (SubsonicError, SubsonicUnreachable):
            return user
        if roles != user.roles:
            self.users.save_roles(user.id, roles)
            user = dataclasses.replace(user, roles=roles, is_admin="admin" in roles)
        return user

    def logout(self, session_token):
        self.sessions.delete(session_token)
