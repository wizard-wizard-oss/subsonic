"""Assemblage de l'édition PC : base, dépôts, services, contrôleurs et routes. Seul endroit où tout se connaît."""
import os
import threading
import types

from ..i18n import Texts
from ..server.transport import Reply, Router, HttpApp, ThreadedServer, make_request_handler
from ..server.webfiles import WebFiles
from ..shared.providers.deezer import Deezer
from ..shared.providers.http import HttpClient
from ..shared.providers.lyrics import LyricsFinder
from ..shared.providers.wikipedia import Wikipedia
from ..storage.database import Database
from .accounts import Accounts
from .tags.service import AlbumTags
from .notifications.service import Notifications
from .storage.notifications import NotificationRepository
from .controllers.notifications import NotificationController
from .tags.audio import AudioTags
from .library.artists import ArtistIndexes
from .artist_discogs import ArtistDiscogsLinks
from .artist_portraits import ArtistPortraits
from .avatars import Avatars
from .chat import Chat
from .covers import MAX_IMAGE_BYTES, Covers
from .config import WebConfig, default_data_dir
from .controllers.auth import AuthController
from .controllers.base import Guard
from .controllers.replies import error_reply
from .controllers.chat import ChatController
from .controllers.covers import CoverController
from .controllers.tags import TagController
from .controllers.library import LibraryController
from .controllers.extmusic import ExtMusicController
from .controllers.imports import ImportController
from .controllers.facts import FactsController
from .controllers.exploration import ExplorationController
from .controllers.discogs import DiscogsController
from .controllers.listening import ListeningController
from .controllers.listen_later import ListenLaterController
from .controllers.lyrics import LyricsController
from .controllers.mixes import MixController
from .controllers.news import NewsController
from .controllers.weekly_releases import WeeklyReleasesController
from .weekly_releases.service import WeeklyReleases
from .storage.weekly_releases import ReleaseSubscriptions
from .controllers.playlists import PlaylistController
from .controllers.uploads import UploadController
from .controllers.profile import ProfileController
from .events import EventHub
from .ext_favorites import ExtFavorites
from .extmusic import KEPT_SECONDS, ExternalMusic, SearchMemory
from .import_readers import DeezerReader
from .playlist_import import PlaylistImport
from .facts import Facts
from .exploration import Exploration
from ..shared.providers.musicbrainz import MusicBrainz
from .providers.discogs import Discogs
from .discogs_catalogs import DiscogsCatalogs
from .discogs_exploration import DiscogsExploration
from .providers.lastfm import LastFm
from .label_discovery import LabelDiscovery
from .youtube_versions import YouTubeVersions
from .tags.sources import TagSources
from .library_scan import LibraryScan
from .storage.exploration import ExplorationRepository
from .library.folders import Folders
from .library.catalog import Library
from .library.statistics import SubsonicStatistics
from .listening import Listening
from .listen_later.service import ListenLater
from .recommendations.service import Recommendations
from .listen_later.targets import ListeningTargets
from .storage.listen_later import ListenLaterRepository
from .storage.recommendations import RecommendationRepository
from .storage.recommendation_comments import RecommendationCommentRepository
from .lyrics import Lyrics
from .mixes import Mixes
from .news import News
from .playlists import Playlists
from .preferences import Preferences
from .radios import Radios
from .ratings import Ratings
from .schema import MIGRATIONS
from .storage.artist_index import ArtistIndexRepository
from .storage.artist_links import ArtistLinkRepository
from .storage.avatars import AvatarRepository
from .storage.community import CommunityRepository
from .storage.ext_favorites import ExtFavoriteRepository, PlaylistExtRepository
from .storage.youtube import ExtSearchRepository, YouTubeVideoRepository
from .storage.messages import MessageRepository
from .storage.news import NewsRepository
from .storage.preferences import PreferenceRepository
from .storage.uploads import UploadRepository
from .storage.users import SessionRepository, UserRepository
from .library.incoming import IncomingSorter
from .library.files import LibraryFiles
from .upload_attribution import UploadAttribution
from .uploads import Uploads, incoming_dir
from .versions import read_releases
from .subsonic import SubsonicError, SubsonicServer, SubsonicUnreachable

# Seules exceptions : les lecteurs officiels YouTube et SoundCloud (script et cadre), leurs vignettes, le son et les
# pochettes de Jamendo, les photos de Wikipédia (upload. et thumb.wikimedia.org) et les pochettes proposées par Last.fm.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; "
                               "img-src 'self' data: https://i.ytimg.com https://*.jamendo.com https://*.sndcdn.com "
                               "https://upload.wikimedia.org https://thumb.wikimedia.org https://lastfm-img.freetls.fastly.net "
                               "https://lastfm.freetls.fastly.net "
                               "https://i.discogs.com https://coverartarchive.org https://archive.org https://*.archive.org; "
                               "media-src 'self' https://*.jamendo.com; style-src 'self'; "
                               "script-src 'self' https://www.youtube.com https://w.soundcloud.com; "
                               "frame-src https://www.youtube-nocookie.com https://www.youtube.com https://w.soundcloud.com; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}




class WebApplication:
    def __init__(self, code_dir, environ=None, data_dir=None, subsonic=None):
        environ = os.environ if environ is None else environ
        self.code_dir = code_dir
        self.data_dir = data_dir or default_data_dir(environ)
        os.makedirs(self.data_dir, exist_ok=True)
        self.config = WebConfig.load(self.data_dir, environ)
        self.texts = Texts(os.path.join(code_dir, "i18n"), self.config.language)
        self.db = Database(os.path.join(self.data_dir, "webapp.db"), MIGRATIONS)
        self.subsonic = subsonic

        self.releases = read_releases(os.path.join(code_dir, "i18n", "versions.yaml"))
        self._build_accounts()
        self._build_providers()
        self._build_files()
        self._build_music()
        self._build_listening_lists()

        web_dir = os.path.join(code_dir, "web-pc")
        self.files = WebFiles(types.SimpleNamespace(web_dir=web_dir, static_dir=os.path.join(web_dir, "static")))
        self.http = HttpApp(self._routes(), error_reply, SECURITY_HEADERS)

    def _build_accounts(self):
        """Comptes, sessions, temps réel et lecture de la bibliothèque Subsonic."""
        self.users = UserRepository(self.db)
        self.sessions = SessionRepository(self.db, self.config.session_days)
        self.messages = MessageRepository(self.db)
        self.subsonic = self.subsonic or SubsonicServer(self.config.subsonic_url)
        self.hub = EventHub()
        self.notifications = Notifications(NotificationRepository(self.db), self.users, self.hub)
        self.accounts = Accounts(self.subsonic, self.users, self.sessions)
        self.preferences = Preferences(PreferenceRepository(self.db))
        self.ratings = Ratings(self.subsonic)
        self.artist_indexes = ArtistIndexes(self.subsonic, ArtistIndexRepository(self.db), self.users, self.hub,
                                            hidden=(self.config.incoming_name,),
                                            shortcuts=[n.strip() for n in self.config.shortcut_folders.split(",") if n.strip()])
        self.library = Library(self.subsonic, self.ratings, self.messages, artist_indexes=self.artist_indexes)
        self.library_statistics = SubsonicStatistics(self.config.subsonic_statistics_file)
        self.folders = Folders(self.subsonic, self.library, self.ratings)

    def _build_providers(self):
        """Une seule instance par service externe, toutes sur le même cache de métadonnées et le même transport."""
        metadata, self.external_http = ExplorationRepository(self.db), HttpClient()
        self.musicbrainz = MusicBrainz(metadata, self.external_http)
        self.discogs = Discogs(metadata, self.config.discogs_api_key, self.external_http)
        self.lastfm = LastFm(metadata, self.config.lastfm_api_key, self.external_http)
        self.exploration = Exploration(self.musicbrainz, self.folders, self.library)
        self.tag_sources = TagSources(self.musicbrainz, self.discogs)
        self.discogs_catalogs = DiscogsCatalogs(self.discogs)
        self.discogs_exploration = DiscogsExploration(self.discogs, self.folders)
        self.artist_discogs = ArtistDiscogsLinks(ArtistLinkRepository(self.db), self.folders, self.artist_indexes,
                                               self.discogs, self.discogs_catalogs, self.config.subsonic_url)
        self.lyrics = Lyrics(LyricsFinder(self.external_http, lambda artist, title: ""))    # sans Subsonic
        self.facts = Facts(self.subsonic, self.musicbrainz, Wikipedia(self.external_http))
        self.artist_portraits = ArtistPortraits(self.artist_discogs, self.discogs, self.subsonic, self.facts.wikipedia)

    def _build_files(self):
        """Fichiers de la musique : envois, rangement d'Incoming, pochettes et tags."""
        library_files = LibraryFiles(self.config.music_dir, incoming_dir(self.config.music_dir, self.config.incoming_name))
        self.library_scan = LibraryScan(self.subsonic, self.users)
        self.uploads = Uploads(self.subsonic, self.users, library_files, UploadRepository(self.db), self.library_scan)
        self.upload_attribution = UploadAttribution(self.uploads, self.subsonic)
        self.covers = Covers(self.folders, self.config.music_dir, self.lastfm, HttpClient(max_bytes=MAX_IMAGE_BYTES))
        self.incoming = IncomingSorter(library_files, self.config.incoming_wait_hours, self.uploads.scan_as_admin)
        self.audio_tags = AudioTags(self.config.music_dir, os.path.join(self.data_dir, "audio-tag-backups"))
        self.album_tags = AlbumTags(self.folders, self.subsonic, self.audio_tags, self.tag_sources,
                                   self.library_scan, self._refresh_tags)

    def _build_music(self):
        """Salon, mix, écoute, profils, musique d'ailleurs, playlists, découverte par label et actualité."""
        self.chat = Chat(self.messages, self.users, self.hub, self._album_info)
        self.mixes = Mixes(self.subsonic)
        self.listening = Listening(self.subsonic)
        self.avatars = Avatars(AvatarRepository(self.db), self.users, self.subsonic)
        self.radios = Radios(self.subsonic)
        videos = YouTubeVideoRepository(self.db, KEPT_SECONDS)
        self.extmusic = ExternalMusic(self.config, SearchMemory(ExtSearchRepository(self.db, KEPT_SECONDS),
                                                                ExtSearchRepository(self.db, None), videos), videos)
        self.ext_favorites = ExtFavorites(ExtFavoriteRepository(self.db), self.extmusic)
        self.playlists = Playlists(self.subsonic, CommunityRepository(self.db), self.users,
                                   PlaylistExtRepository(self.db), self.ext_favorites)
        self.imports = PlaylistImport(self.subsonic, self.extmusic, self.playlists, self.ext_favorites,
                                      DeezerReader(Deezer(self.external_http)))
        self.youtube_versions = YouTubeVersions(self.extmusic)
        self.label_discovery = LabelDiscovery(self.discogs_catalogs, self.discogs, self.lastfm, self.imports,
                                               youtube_versions=self.youtube_versions)
        self.news = News(NewsRepository(self.db))

    def _build_listening_lists(self):
        """« À écouter » et recommandations, sur des cibles partagées."""
        targets = ListeningTargets(self.folders, self.discogs, self.artist_discogs.library_key, self.library)
        self.listen_later = ListenLater(ListenLaterRepository(self.db), targets)
        self.recommendations = Recommendations(RecommendationRepository(self.db), RecommendationCommentRepository(self.db),
                                             targets, self.users, self.hub)

    def _album_info(self, user, album_id):
        try:
            return self.library.album_brief(user, album_id)
        except (SubsonicError, SubsonicUnreachable):
            return {}

    def _refresh_tags(self):
        """Une écriture de tags invalide les lectures indexées, pour tous les comptes concernés."""
        for cache in (self.library.cache, self.library.top_cache, self.folders.cache, self.ratings.cache,
                      self.upload_attribution.paths):
            cache.clear()

    def _routes(self):
        router, guard = Router(), Guard(self.accounts, self.users)
        router.add("GET", "/", self._page)
        router.add("GET", "/health", lambda r: Reply.json({"ok": True}))
        router.add_prefix("GET", "/static/", self._static)
        router.add("GET", "/api/texts", lambda r: Reply.json(self.texts.section("webapp.")))
        router.add("GET", "/api/versions",
                   lambda r: Reply.json({"releases": [release.to_api() for release in self.releases]}))
        for controller in self._controllers():
            for route in controller.routes():
                router.add(route.method, route.path, guard.wrap(route))
        return router

    def _controllers(self):
        """Chaque contrôleur déclare ses routes (méthode, chemin, droit, limite) ; app.py ne fait qu'assembler."""
        auth = AuthController(self.accounts, self.preferences, self.chat, self.users, self.config.secure_cookie,
                              self.config.trust_proxy)
        library = LibraryController(self.library, self.folders, self.artist_indexes, self.ratings, self.subsonic,
                                    self.library_statistics, self.upload_attribution)
        chat = ChatController(self.chat, self.hub)
        mixes = MixController(self.mixes)
        playlists = PlaylistController(self.playlists)
        listening = ListeningController(self.listening)
        listen_later = ListenLaterController(self.listen_later, self.recommendations)
        profile = ProfileController(self.avatars, self.radios, self.config.subsonic_public_url)
        lyrics = LyricsController(self.lyrics)
        facts = FactsController(self.facts, self.artist_portraits)
        exploration = ExplorationController(self.exploration)
        discogs = DiscogsController(self.discogs, self.discogs_catalogs, self.label_discovery, self.discogs_exploration,
                                   self.artist_discogs)
        extmusic = ExtMusicController(self.extmusic, self.ext_favorites)
        uploads = UploadController(self.uploads)
        news = NewsController(self.news)
        releases = WeeklyReleasesController(WeeklyReleases(self.musicbrainz, ReleaseSubscriptions(self.db)))
        covers = CoverController(self.covers)
        tags = TagController(self.album_tags)
        notifications = NotificationController(self.notifications)
        imports = ImportController(self.imports)
        return (auth, library, chat, mixes, playlists, listening, listen_later, profile, lyrics, facts, exploration,
                discogs, extmusic, uploads, news, releases, covers, tags, notifications, imports)

    def _page(self, request):
        return Reply.from_web_file(self.files.index(request.header("If-None-Match")))

    def _static(self, request):
        return Reply.from_web_file(self.files.static(request.path, request.query_string,
                                                     request.header("If-None-Match"),
                                                     request.header("Accept-Encoding")))

    def make_server(self, bind=None, port=None):
        return ThreadedServer((bind or self.config.bind, self.config.port if port is None else port),
                              make_request_handler(self.http))

    def run(self):
        server = self.make_server()
        # liste des artistes prête avant la première visite, puis comparée à Subsonic toutes les 10 minutes
        threading.Thread(target=self.artist_indexes.run, daemon=True).start()
        if self.incoming.enabled:                      # Incoming corrigé à la main : rangé, vérifié toutes les 10 minutes
            threading.Thread(target=self.incoming.run, daemon=True).start()
        if self.extmusic.status()["youtube"]:          # vidéos YouTube gardées : relues tous les 30 jours
            threading.Thread(target=self.extmusic.run, daemon=True).start()
        threading.Thread(target=self.news.run, daemon=True).start()     # flux de l'Actualité : relus toutes les heures
        print("Édition PC : http://%s:%d/ (Subsonic : %s)" % (self.config.bind, self.config.port,
                                                               self.config.subsonic_url or "non réglé"))
        server.serve_forever()
