"""Câblage des sorties de la semaine (consultation par style, radar, tendances, synchronisation de fond)."""
from ..providers.listenbrainz import ListenBrainz
from ..storage.exploration import ExplorationRepository
from ..storage.release_radar import AlbumLabels, ArtistResolutions, RadarProfiles, RadarReleases, ReleaseSources
from ..storage.weekly_releases import ReleaseSubscriptions
from .radar import RadarService
from .service import WeeklyReleases
from .sync import ReleaseSync
from .trends import Trends


def build(app):
    """(consultation par style, radar, synchronisation de fond) à partir des services de l'application."""
    sources, releases, profiles = ReleaseSources(app.db), RadarReleases(app.db), RadarProfiles(app.db)
    trends = Trends(app.subsonic, app.musicbrainz, sources, AlbumLabels(app.db), profiles, ArtistResolutions(app.db))
    listenbrainz = ListenBrainz(ExplorationRepository(app.db), app.external_http)
    sync = ReleaseSync(app.musicbrainz, listenbrainz, trends, sources, releases, profiles, users=app.users.by_priority)
    styles = WeeklyReleases(app.musicbrainz, ReleaseSubscriptions(app.db))
    radar = RadarService(app.musicbrainz, app.lastfm, sources, releases, profiles, sync, styles,
                         local=app.exploration.local)
    return styles, radar, sync

