"""Câblage des sorties de la semaine (consultation par style, radar, tendances, synchronisation de fond)."""
from ...shared.text import normalize
from ..storage.release_radar import AlbumLabels, RadarProfiles, RadarReleases, ReleaseSources
from ..storage.weekly_releases import ReleaseSubscriptions
from ..subsonic import SubsonicError, SubsonicUnreachable
from .radar import RadarService
from .service import WeeklyReleases
from .sync import ReleaseSync
from .trends import Trends


def build(app):
    """(consultation par style, radar, synchronisation de fond) à partir des services de l'application."""
    sources, releases, profiles = ReleaseSources(app.db), RadarReleases(app.db), RadarProfiles(app.db)
    trends = Trends(app.subsonic, app.musicbrainz, app.lastfm, sources, AlbumLabels(app.db), profiles,
                    bookmarks=lambda user: [entry.target for entry in app.listen_later.all(user)],
                    library_artists=lambda user: _library_artists(app.artist_indexes, user))
    sync = ReleaseSync(app.musicbrainz, trends, sources, releases, profiles, users=app.users.by_priority)
    styles = WeeklyReleases(app.musicbrainz, ReleaseSubscriptions(app.db))
    radar = RadarService(app.musicbrainz, app.lastfm, sources, releases, profiles, sync, styles,
                         local=app.exploration.local)
    return styles, radar, sync


def _library_artists(artist_indexes, user):
    """Noms normalisés des artistes de la bibliothèque visibles par ce compte."""
    try:
        index = artist_indexes.for_user(user)
    except (SubsonicError, SubsonicUnreachable):
        return set()
    return {normalize(artist["name"]) for group in index for artist in group["artists"]}
