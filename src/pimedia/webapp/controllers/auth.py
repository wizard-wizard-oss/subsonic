"""Connexion, déconnexion, « qui suis-je »."""
from ...server.transport import Reply
from ..accounts import LoginRefused, TooManyAttempts
from ..chat import REACTIONS
from .base import Guard, client_address, ok, session_cookie, session_token


class AuthController:
    def __init__(self, accounts, preferences, chat, users, secure_cookie, trust_proxy=False):
        self.accounts = accounts
        self.preferences = preferences
        self.chat = chat
        self.users = users
        self.secure_cookie = secure_cookie
        self.trust_proxy = trust_proxy

    def login(self, request):
        Guard.check_write(request)
        body = request.json_body()
        address = client_address(request, self.trust_proxy)
        try:
            user, token = self.accounts.login(body.get("username"), body.get("password"), address)
        except LoginRefused:
            return Reply.error(401, "auth.refused")
        except TooManyAttempts:
            return Reply.error(429, "auth.too_many")
        reply = Reply.json({"user": user.to_api()})
        reply.headers["Set-Cookie"] = session_cookie(token, self.accounts.sessions.max_age, self.secure_cookie)
        return reply

    def logout(self, request):
        Guard.check_write(request)
        self.accounts.logout(session_token(request))
        reply = ok()
        reply.headers["Set-Cookie"] = session_cookie("", 0, self.secure_cookie)
        return reply

    def me(self, request, user):
        user = self.accounts.refresh_roles(user)              # un administrateur a pu changer ses droits
        return ok({"user": user.to_api(), "preferences": self.preferences.of(user), "reactions": list(REACTIONS),
                   "unread": self.chat.unread(user), "usernames": self.users.usernames()})

    def save_preferences(self, request, user, body):
        return ok({"preferences": self.preferences.update(user, body.get("changes"))})
