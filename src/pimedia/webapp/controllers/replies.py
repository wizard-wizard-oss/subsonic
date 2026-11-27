"""Traduction des erreurs en réponses JSON {"error": clé de texte} : la seule correspondance erreur -> statut HTTP."""
import sqlite3

from ...server.transport import Reply
from ...shared.providers.metadata import ProviderUnavailable
from ..avatars import InvalidAvatar
from ..chat import ChatError
from ..covers import CoverError
from ..discogs_catalogs import CatalogError
from ..errors import Forbidden, MissingRight, Unauthorized
from ..extmusic import ExtMusicError
from ..import_readers import ImportFailed
from ..library.folders import FolderNotFound
from ..listen_later.targets import ListenLaterError
from ..mixes import MixError
from ..news import NewsError
from ..notifications.entities import NotificationError
from ..playlists import PlaylistError
from ..preferences import InvalidPreference
from ..ratings import InvalidRating
from ..recommendations.entities import RecommendationError
from ..subsonic import SubsonicError, SubsonicUnreachable
from ..tags.audio import AudioTagError
from ..tags.entities import TagError
from ..uploads import UploadError
from ..weekly_releases.entities import RadarError


def error_reply(error):
    """Toute erreur devient une réponse JSON {"error": clé de texte}."""
    if isinstance(error, sqlite3.IntegrityError):
        return Reply.error(400, "request.invalid")          # une contrainte de la base : jamais une erreur serveur
    if isinstance(error, NotificationError):
        return Reply.error(400, str(error))
    if isinstance(error, TagError):
        return Reply.error(error.status, error.code)
    if isinstance(error, AudioTagError):
        return Reply.error(409 if error.args and error.args[0] == "tags.conflict" else 400,
                           error.args[0] if error.args else "tags.write_failed")
    if isinstance(error, ProviderUnavailable):
        return Reply.error(429 if error.args[0] == "discovery.rate_limited" else 503, error.args[0])
    if isinstance(error, CatalogError):
        return Reply.error(400, error.args[0])
    if isinstance(error, Unauthorized):
        return Reply.error(401, "auth.required")
    if isinstance(error, MissingRight):
        return Reply.error(403, "auth.missing_right")
    if isinstance(error, Forbidden):
        return Reply.error(403, "auth.forbidden")
    if isinstance(error, (ChatError, RecommendationError, RadarError)):
        return Reply.error(error.status, error.code)
    if isinstance(error, FolderNotFound):
        return Reply.error(404, "subsonic.error")
    if isinstance(error, SubsonicError):
        return Reply.error(404 if error.code == 70 else 502, "subsonic.error")
    if isinstance(error, SubsonicUnreachable):
        return Reply.error(503, "subsonic.unreachable")
    if isinstance(error, (MixError, PlaylistError, InvalidAvatar, ExtMusicError, UploadError, NewsError, ImportFailed, CoverError, ListenLaterError)) and error.args:
        return Reply.error(400, error.args[0])             # clé de texte précise (« mix.no_lastfm »…)
    if isinstance(error, (InvalidRating, InvalidPreference, ValueError)):
        return Reply.error(400, "request.invalid")
    import traceback
    traceback.print_exc()
    return Reply.error(500, "server.error")
