"""Assemblage de l'édition PC : base, dépôts, services, contrôleurs et routes. Seul endroit où tout se connaît."""
import os
import threading
import types

from ..i18n import Texts
from ..server.transport import Reply, Router, HttpApp, ThreadedServer, make_request_handler
from ..server.podcasts.directories import JsonHttp
from ..server.webfiles import WebFiles
from ..shared.external import JsonFetcher, LyricsFinder, MusicBrainz, Wikipedia
from ..storage.database import Database
from .accounts import Accounts
from .artist_index import ArtistIndexes
from .avatars import Avatars, InvalidAvatar
from .chat import Chat, ChatError
from .covers import CoverError, Covers, ImageDownloader, LastFmAlbums
from .config import WebConfig, default_data_dir
from .controllers.auth import AuthController
from .controllers.base import Forbidden, Guard, MissingRight, Unauthorized
from .controllers.chat import ChatController
from .controllers.covers import CoverController
from .controllers.library import LibraryController
from .controllers.extmusic import ExtMusicController
from .controllers.imports import ImportController
from .controllers.facts import FactsController
from .controllers.exploration import ExplorationController
from .controllers.listening import ListeningController
from .controllers.lyrics import LyricsController
from .controllers.mixes import MixController
from .controllers.news import NewsController
from .controllers.playlists import PlaylistController
from .controllers.uploads import UploadController
from .controllers.profile import AVATAR_BODY_LIMIT, ProfileController
from .events import EventHub
from .ext_favorites import ExtFavorites
from .extmusic import KEPT_SECONDS, ExternalMusic, ExtMusicError, SearchMemory
from .import_readers import DeezerReader, ImportFailed
from .playlist_import import PlaylistImport
from .facts import Facts
from .exploration import Exploration, ExplorationUnavailable, MusicMetadata
from .storage.exploration import ExplorationRepository
from .folders import FolderNotFound, Folders
from .library import Library
from .listening import Listening
from .lyrics import Lyrics
from .mixes import MixError, Mixes
from .news import News, NewsError
from .playlists import PlaylistError, Playlists
from .preferences import InvalidPreference, Preferences
from .radios import Radios
from .ratings import InvalidRating, Ratings
from .schema import MIGRATIONS
from .storage.artist_index import ArtistIndexRepository
from .storage.avatars import AvatarRepository
from .storage.community import CommunityRepository
from .storage.ext_favorites import ExtFavoriteRepository, PlaylistExtRepository
from .storage.youtube import ExtSearchRepository, YouTubeVideoRepository
from .storage.messages import MessageRepository
from .storage.news import NewsRepository
from .storage.preferences import PreferenceRepository
from .storage.users import SessionRepository, UserRepository
from .incoming import IncomingSorter
from .layout import MusicTree
from .uploads import UploadError, Uploads, incoming_dir
from .versions import read_releases
from .subsonic import SubsonicError, SubsonicServer, SubsonicUnreachable

# Seules exceptions : les lecteurs officiels YouTube et SoundCloud (script et cadre), leurs vignettes, le son et les
# pochettes de Jamendo, les photos de Wikipédia (upload. et thumb.wikimedia.org) et les pochettes proposées par Last.fm.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; "
                               "img-src 'self' data: https://i.ytimg.com https://*.jamendo.com https://*.sndcdn.com "
                               "https://upload.wikimedia.org https://thumb.wikimedia.org https://lastfm-img.freetls.fastly.net; "
                               "media-src 'self' https://*.jamendo.com; style-src 'self'; "
                               "script-src 'self' https://www.youtube.com https://w.soundcloud.com; "
                               "frame-src https://www.youtube-nocookie.com https://www.youtube.com https://w.soundcloud.com; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}


EXT_ITEMS_BODY_LIMIT = 512 * 1024
IMPORT_FILE_LIMIT = 5 * 1024 * 1024          # fichier de playlist lu par la page (export Apple Music : XML bavard)
IMPORT_CREATE_LIMIT = 1024 * 1024


def error_reply(error):
    """Toute erreur devient une réponse JSON {"error": clé de texte}."""
    if isinstance(error, ExplorationUnavailable):
        return Reply.error(503, "explore.unavailable")
    if isinstance(error, Unauthorized):
        return Reply.error(401, "auth.required")
    if isinstance(error, MissingRight):
        return Reply.error(403, "auth.missing_right")
    if isinstance(error, Forbidden):
        return Reply.error(403, "auth.forbidden")
    if isinstance(error, ChatError):
        return Reply.error(error.status, error.code)
    if isinstance(error, FolderNotFound):
        return Reply.error(404, "subsonic.error")
    if isinstance(error, SubsonicError):
        return Reply.error(404 if error.code == 70 else 502, "subsonic.error")
    if isinstance(error, SubsonicUnreachable):
        return Reply.error(503, "subsonic.unreachable")
    if isinstance(error, (MixError, PlaylistError, InvalidAvatar, ExtMusicError, UploadError, NewsError, ImportFailed, CoverError)) and error.args:
        return Reply.error(400, error.args[0])             # clé de texte précise (« mix.no_lastfm »…)
    if isinstance(error, (InvalidRating, InvalidPreference, ValueError)):
        return Reply.error(400, "request.invalid")
    import traceback
    traceback.print_exc()
    return Reply.error(500, "server.error")


class WebApplication:
    def __init__(self, code_dir, environ=None, data_dir=None, subsonic=None):
        environ = os.environ if environ is None else environ
        self.code_dir = code_dir
        self.data_dir = data_dir or default_data_dir(environ)
        os.makedirs(self.data_dir, exist_ok=True)
        self.config = WebConfig.load(self.data_dir, environ)
        self.texts = Texts(os.path.join(code_dir, "i18n"), self.config.language)
        self.db = Database(os.path.join(self.data_dir, "webapp.db"), MIGRATIONS)

        # dépôts
        self.users = UserRepository(self.db)
        self.sessions = SessionRepository(self.db, self.config.session_days)
        self.messages = MessageRepository(self.db)

        # services
        self.subsonic = subsonic or SubsonicServer(self.config.subsonic_url)
        self.hub = EventHub()
        self.accounts = Accounts(self.subsonic, self.users, self.sessions)
        self.preferences = Preferences(PreferenceRepository(self.db))
        self.ratings = Ratings(self.subsonic)
        self.library = Library(self.subsonic, self.ratings, self.messages)
        self.folders = Folders(self.subsonic, self.library, self.ratings)
        self.exploration = Exploration(MusicMetadata(ExplorationRepository(self.db)), self.folders, self.library)
        self.artist_indexes = ArtistIndexes(self.subsonic, ArtistIndexRepository(self.db), self.users, self.hub,
                                            hidden=(self.config.incoming_name,),
                                            shortcuts=[n.strip() for n in self.config.shortcut_folders.split(",") if n.strip()])
        self.chat = Chat(self.messages, self.users, self.hub, self._album_info)
        self.mixes = Mixes(self.subsonic)
        self.listening = Listening(self.subsonic)
        self.avatars = Avatars(AvatarRepository(self.db), self.users, self.subsonic)
        self.radios = Radios(self.subsonic)
        library = MusicTree(self.config.music_dir, incoming_dir(self.config.music_dir, self.config.incoming_name))
        self.uploads = Uploads(self.subsonic, self.users, library)
        self.covers = Covers(self.folders, self.config.music_dir, LastFmAlbums(JsonFetcher(), self.config.lastfm_api_key),
                             ImageDownloader())
        self.incoming = IncomingSorter(library, self.config.incoming_wait_hours, self.uploads.scan_as_admin)
        videos = YouTubeVideoRepository(self.db, KEPT_SECONDS)
        self.extmusic = ExternalMusic(self.config, SearchMemory(ExtSearchRepository(self.db, KEPT_SECONDS),
                                                                ExtSearchRepository(self.db, None), videos), videos)
        self.ext_favorites = ExtFavorites(ExtFavoriteRepository(self.db), self.extmusic)
        self.playlists = Playlists(self.subsonic, CommunityRepository(self.db), self.users,
                                   PlaylistExtRepository(self.db), self.ext_favorites)
        self.imports = PlaylistImport(self.subsonic, self.extmusic, self.playlists, self.ext_favorites,
                                      DeezerReader(JsonHttp()))
        self.lyrics = Lyrics(LyricsFinder(JsonFetcher(), lambda artist, title: ""))    # sans Subsonic
        fetcher = JsonFetcher()
        self.facts = Facts(self.subsonic, MusicBrainz(fetcher), Wikipedia(fetcher))
        self.news = News(NewsRepository(self.db))
        self.releases = read_releases(os.path.join(code_dir, "i18n", "versions.yaml"))

        web_dir = os.path.join(code_dir, "web-pc")
        self.files = WebFiles(types.SimpleNamespace(web_dir=web_dir, static_dir=os.path.join(web_dir, "static")))
        self.http = HttpApp(self._routes(), error_reply, SECURITY_HEADERS)

    def _album_info(self, user, album_id):
        try:
            return self.library.album_brief(user, album_id)
        except (SubsonicError, SubsonicUnreachable):
            return {}

    def _routes(self):
        router = Router()
        guard = Guard(self.accounts, self.users)
        read, write = guard.reader, guard.writer
        auth = AuthController(self.accounts, self.preferences, self.chat, self.users, self.config.secure_cookie,
                              self.config.trust_proxy)
        library = LibraryController(self.library, self.folders, self.artist_indexes, self.ratings, self.subsonic)
        chat = ChatController(self.chat, self.hub)
        mixes = MixController(self.mixes)
        playlists = PlaylistController(self.playlists)
        listening = ListeningController(self.listening)
        profile = ProfileController(self.avatars, self.radios, self.config.subsonic_public_url)
        lyrics = LyricsController(self.lyrics)
        facts = FactsController(self.facts)
        exploration = ExplorationController(self.exploration)
        extmusic = ExtMusicController(self.extmusic, self.ext_favorites)
        uploads = UploadController(self.uploads)
        news = NewsController(self.news)
        covers = CoverController(self.covers)

        router.add("GET", "/", self._page)
        router.add("GET", "/health", lambda r: Reply.json({"ok": True}))
        router.add_prefix("GET", "/static/", self._static)
        router.add("GET", "/api/texts", lambda r: Reply.json(self.texts.section("webapp.")))
        router.add("GET", "/api/versions",
                   lambda r: Reply.json({"releases": [release.to_api() for release in self.releases]}))

        router.add("POST", "/api/login", auth.login)
        router.add("POST", "/api/logout", auth.logout)
        router.add("GET", "/api/me", read(auth.me))
        router.add("GET", "/api/explore/album", read(exploration.album))
        router.add("GET", "/api/explore/profile", read(exploration.profile))
        router.add("GET", "/api/explore/artists", read(exploration.artists))
        router.add("GET", "/api/explore/connections", read(exploration.connections))
        router.add("GET", "/api/explore/local", read(exploration.local))
        router.add("POST", "/api/preferences", write(auth.save_preferences))

        for path, handler in (("/api/home", library.home), ("/api/artists", library.artists),
                              ("/api/artist", library.artist), ("/api/artist/top", library.top_songs),
                              ("/api/artist/similar", library.similar),
                              ("/api/album", library.album),
                              ("/api/search", library.search), ("/api/starred", library.starred),
                              ("/api/albums", library.albums), ("/api/genres", library.genres),
                              ("/api/cover", library.cover)):
            router.add("GET", path, read(handler))
        # chacun ne fait que ce que son compte Subsonic permet
        router.add("GET", "/api/stream", read(library.stream, right="stream"))
        router.add("GET", "/api/download", read(library.download, right="download"))
        router.add("POST", "/api/favorite", write(library.favorite))
        router.add("POST", "/api/rating", write(library.rate, right="comment"))

        for path, handler in (("/api/chat/history", chat.history), ("/api/chat/search", chat.search),
                              ("/api/chat/mentions", chat.mentions), ("/api/chat/online", chat.online),
                              ("/api/events", chat.events)):
            router.add("GET", path, read(handler))
        for path, handler in (("/api/chat/post", chat.post), ("/api/chat/edit", chat.edit),
                              ("/api/chat/delete", chat.delete), ("/api/chat/react", chat.react),
                              ("/api/chat/typing", chat.typing), ("/api/chat/read", chat.read)):
            router.add("POST", path, write(handler))

        # mix, radios, playlists, écoute, photos de profil, radios Internet
        for path, handler in (("/api/mix", mixes.simple), ("/api/mix/genres", mixes.genres),
                              ("/api/radio/song", mixes.song_radio), ("/api/radio/artist", mixes.artist_radio),
                              ("/api/playlists", playlists.all), ("/api/playlist", playlists.get),
                              ("/api/now-playing", listening.now_playing), ("/api/bookmarks", listening.bookmarks),
                              ("/api/play-queue", listening.play_queue),
                              ("/api/account", profile.account),
                              ("/api/avatar", profile.avatar), ("/api/avatars", profile.avatar_versions),
                              ("/api/radios", profile.stations), ("/api/radios/stream", profile.stream),
                              ("/api/lyrics", lyrics.find), ("/api/facts", facts.song_facts),
                              ("/api/artist/bio", facts.artist_bio),
                              ("/api/ext/status", extmusic.status), ("/api/ext/search", extmusic.search),
                              ("/api/ext/known", extmusic.known), ("/api/ext/favorites", extmusic.favorite_list),
                              ("/api/news", news.latest), ("/api/news/feeds", news.feeds),
                              ("/api/news/artist", news.about)):
            router.add("GET", path, read(handler))
        for path, handler in (("/api/mix/build", mixes.build),
                              ("/api/scrobble", listening.scrobble), ("/api/bookmark/save", listening.save_bookmark),
                              ("/api/bookmark/delete", listening.delete_bookmark),
                              ("/api/play-queue/save", listening.save_play_queue),
                              ("/api/avatar/delete", profile.remove_avatar), ("/api/avatar/gravatar", profile.gravatar),
                              ("/api/ext/alternative", extmusic.alternative), ("/api/ext/unplayable", extmusic.unplayable),
                              ("/api/ext/played", extmusic.played), ("/api/ext/favorite", extmusic.favorite),
                              ("/api/ext/link", extmusic.add_link),
                              ("/api/news/feed/add", news.add), ("/api/news/feed/remove", news.remove),
                              ("/api/news/feed/show", news.show)):
            router.add("POST", path, write(handler))
        router.add("POST", "/api/avatar/upload", write(profile.upload_avatar, AVATAR_BODY_LIMIT))
        # envoi de fichiers dans Incoming (droit Subsonic « upload ») : le fichier (ou un zip) est le corps brut de la requête
        router.add("GET", "/api/upload/status", read(uploads.status, right="upload"))
        router.add("POST", "/api/upload", guard.raw_writer(uploads.upload, right="upload"))
        router.add("POST", "/api/upload/finish", write(uploads.finish, right="upload"))
        # changer la pochette d'un album : écrite dans son dossier de la musique (droit Subsonic « upload »)
        router.add("GET", "/api/cover/status", read(covers.status, right="upload"))
        router.add("GET", "/api/cover/search", read(covers.search, right="upload"))
        router.add("POST", "/api/cover/save", write(covers.save, right="upload"))
        for path, handler in (("/api/playlist/create", playlists.create), ("/api/playlist/add", playlists.add),
                              ("/api/playlist/remove", playlists.remove), ("/api/playlist/rename", playlists.rename),
                              ("/api/playlist/community", playlists.community),
                              ("/api/playlist/remove-ext", playlists.remove_ext),
                              ("/api/playlist/delete", playlists.delete)):
            router.add("POST", path, write(handler, right="playlist"))
        # titres d'ailleurs envoyés complets par la page (vérifiés par le serveur) : jusqu'à 500 d'un coup
        router.add("POST", "/api/playlist/add-ext", write(playlists.add_ext, EXT_ITEMS_BODY_LIMIT, right="playlist"))
        router.add("POST", "/api/playlist/reorder", write(playlists.reorder, EXT_ITEMS_BODY_LIMIT, right="playlist"))
        # import d'une playlist venue d'ailleurs (Deezer, Spotify, Apple Music…)
        imports = ImportController(self.imports)
        router.add("POST", "/api/import/read", write(imports.read, IMPORT_FILE_LIMIT, right="playlist"))
        router.add("POST", "/api/import/match", write(imports.match, 65536, right="playlist"))
        router.add("POST", "/api/import/youtube", write(imports.youtube, 65536, right="playlist"))
        router.add("POST", "/api/import/create", write(imports.create, IMPORT_CREATE_LIMIT, right="playlist"))
        return router

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
