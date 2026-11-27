"""Limites et formats communs, définis une seule fois et réutilisés par la validation de chaque service."""
import re

USERNAME_MAX_LENGTH = 200
REQUEST_ID = re.compile(r"[0-9a-f]{32}")     # jeton d'une requête rejouable, fabriqué par App.requestId() (core.js)


def is_request_id(value):
    return isinstance(value, str) and REQUEST_ID.fullmatch(value) is not None


def is_username(value):
    return isinstance(value, str) and 1 <= len(value) <= USERNAME_MAX_LENGTH
