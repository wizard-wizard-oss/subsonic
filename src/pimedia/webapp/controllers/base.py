"""Ce qui est commun aux contrôleurs : utilisateur connecté, protection des écritures, nombres dans l'adresse."""
import http.cookies
from dataclasses import dataclass

from ...server.transport import Reply
from ..errors import Forbidden, MissingRight, Unauthorized  # noqa: F401  (réexportées pour les contrôleurs)

COOKIE = "pmw_session"
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "pmw"
DEFAULT_BODY_LIMIT = 16384


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


def int_param(request, name, strict=False):
    value = request.param(name)
    try:
        return int(value) if value else None
    except ValueError:
        if strict:
            raise
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

    def writer(self, handler, body_limit=DEFAULT_BODY_LIMIT, right=None):
        """Route d'écriture : handler(request, user, corps JSON)."""
        def route(request):
            self.check_write(request)
            user = self.user(request)
            self.check_right(user, right)
            return handler(request, user, request.json_body(limit=body_limit))
        return route

    def wrap(self, route):
        if route.guard == "open":
            return route.handler
        if route.guard == "write":
            return self.writer(route.handler, route.body_limit, route.right)
        if route.guard == "raw":
            return self.raw_writer(route.handler, route.right)
        return self.reader(route.handler, route.right)

    def raw_writer(self, handler, right=None):
        """Route d'écriture dont le corps n'est pas du JSON (un fichier) : handler(request, user), qui le lit lui-même."""
        def route(request):
            self.check_write(request)
            user = self.user(request)
            self.check_right(user, right)
            return handler(request, user)
        return route


@dataclass(frozen=True)
class Route:
    """Une route déclarée par son contrôleur ; la garde (session, CSRF, droit) est posée par Guard.wrap."""
    method: str
    path: str
    handler: object
    guard: str = "read"                     # read, write, raw (corps brut) ou open (sans session)
    right: str | None = None
    body_limit: int = DEFAULT_BODY_LIMIT


def get(path, handler, right=None):
    return Route("GET", path, handler, "read", right)


def post(path, handler, right=None, body_limit=DEFAULT_BODY_LIMIT):
    return Route("POST", path, handler, "write", right, body_limit)


def post_raw(path, handler, right=None):
    return Route("POST", path, handler, "raw", right)


def public(method, path, handler):
    return Route(method, path, handler, "open")


def ok(data=None):
    return Reply.json(data if data is not None else {"ok": True})
