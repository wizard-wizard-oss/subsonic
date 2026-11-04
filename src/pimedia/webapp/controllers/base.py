"""Ce qui est commun aux contrôleurs : utilisateur connecté, protection des écritures, nombres dans l'adresse."""
import http.cookies

from ...server.transport import Reply

COOKIE = "pmw_session"
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "pmw"


class Unauthorized(Exception):
    pass


class Forbidden(Exception):
    pass


class MissingRight(Forbidden):
    """Le compte Subsonic n'a pas ce droit (télécharger, écouter, playlists, noter et commenter…)."""


def session_token(request):
    cookie = http.cookies.SimpleCookie()
    try:
        cookie.load(request.header("Cookie"))
    except http.cookies.CookieError:
        return ""
    morsel = cookie.get(COOKIE)
    return morsel.value if morsel else ""


def client_address(request, trust_proxy):
    """Adresse de la personne. Derrière Apache ou nginx, toutes les requêtes viennent du proxy : on prend alors la
    dernière adresse de X-Forwarded-For, celle que le proxy a ajoutée (les précédentes viennent du navigateur)."""
    if trust_proxy:
        forwarded = [part.strip() for part in request.header("X-Forwarded-For").split(",") if part.strip()]
        if forwarded:
            return forwarded[-1]
    return request.peer


def session_cookie(token, max_age, secure):
    parts = ["%s=%s" % (COOKIE, token), "Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=%d" % max_age]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def int_param(request, name):
    value = request.param(name)
    try:
        return int(value) if value else None
    except ValueError:
        return None


class Guard:
    """Toutes les routes /api (sauf la connexion) demandent une session ; les écritures demandent en plus
    l'en-tête X-Requested-With, qu'une page d'un autre site ne peut pas ajouter (protection CSRF)."""

    def __init__(self, accounts, users):
        self.accounts = accounts
        self.users = users

    def user(self, request):
        user = self.accounts.user_for(session_token(request))
        if user is None:
            raise Unauthorized()
        return user

    @staticmethod
    def check_write(request):
        if request.header(CSRF_HEADER) != CSRF_VALUE:
            raise Forbidden()

    @staticmethod
    def check_right(user, right):
        if right and not user.can(right):
            raise MissingRight(right)

    def reader(self, handler, right=None):
        """Route de lecture : handler(request, user). right : droit Subsonic exigé (« download »…)."""
        def route(request):
            user = self.user(request)
            self.check_right(user, right)
            return handler(request, user)
        return route

    def writer(self, handler, body_limit=16384, right=None):
        """Route d'écriture : handler(request, user, corps JSON)."""
        def route(request):
            self.check_write(request)
            user = self.user(request)
            self.check_right(user, right)
            return handler(request, user, request.json_body(limit=body_limit))
        return route

    def raw_writer(self, handler, right=None):
        """Route d'écriture dont le corps n'est pas du JSON (un fichier) : handler(request, user), qui le lit lui-même."""
        def route(request):
            self.check_write(request)
            user = self.user(request)
            self.check_right(user, right)
            return handler(request, user)
        return route


def ok(data=None):
    return Reply.json(data if data is not None else {"ok": True})
