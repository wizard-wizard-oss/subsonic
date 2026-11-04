"""Assemblage de l'édition Pi (un seul utilisateur) : crée les objets, les relie, déclare les routes, lance le serveur.

Toutes les dépendances sont créées ici, une seule fois, et passées aux classes qui en ont besoin
(aucune variable globale) : chaque classe peut être testée seule avec des faux."""
import os

from .api import CachedApi, CoverService
from .cache import CoverCache, JsonCache
from .constants import FOREVER
from .controllers.extmusic import ExtMusicController
from .controllers.history import HistoryController
from .controllers.library import CacheController, InfoController, RestController
from .controllers.pages import PagesController
from .controllers.pi import GuestController, PiController, PiState, SystemVolume
from .controllers.player import PlayerController
from .controllers.podcasts import PodcastController
from .controllers.queue import QueueController
from .controllers.settings import SettingsController
from .external import ExternalInfo, FactsBuilder, JsonFetcher, LyricsFinder, MusicBrainz, Wikipedia
from .extmusic.service import ExtMusicService
from .extmusic.sources import JamendoSource, YouTubeSource
from .extmusic.ytmusic import YouTubeMusicSearch
from .folders import FolderAdapter
from .guests import GuestWatcher
from .keys import BrowseMode, CacheKeys
from .playback import HifiPlayer
from .tasks import in_background
from .podcasts.directories import DirectoryHub, ItunesDirectory, JsonHttp, PodcastIndexDirectory
from .podcasts.feeds import FeedFetcher, FeedReader
from .podcasts.service import PodcastService
from .policy import CachePolicy
from .queue import QueueService
from .links import LinkResolver
from .phone_files import URL_PREFIX as PHONE_FILES_URL, PhoneFiles
from .remote import DEFAULT_PORT as PHONE_PORT, PhoneQueue, PhoneServer, RemoteController, RemoteTyping
from .transport import FileReply, HttpApp, Reply, Router, ThreadedServer, make_request_handler
from .upstream import SubsonicClient
from .watcher import LibraryCache, LibraryWatcher, NewestAlbums
from .webfiles import WebFiles
from ..entities import Track
from ..envfile import EnvFile
from ..i18n import Texts
from ..paths import Paths, default_cache_dir, resolve_data_dir
from ..settings import AppSettingsStore, Settings
from ..storage.database import Database
from ..storage.history import SearchHistory
from ..storage.legacy import LegacyImport
from ..storage.playlists import LocalPlaylists
from ..storage.podcasts import PodcastLibrary
from ..storage.queue import PlayQueue
from ..storage.videos import UnplayableVideos


def read_version(code_dir):
    """Version déployée (fichier VERSION de l'archive) ; « dev » quand on lance depuis les sources."""
    try:
        with open(os.path.join(code_dir, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "dev"
    except OSError:
        return "dev"


class Application:
    def __init__(self, code_dir, environ=None, data_dir=None):
        self.environ = os.environ if environ is None else environ
        data_dir = data_dir or resolve_data_dir(code_dir, self.environ)
        self.paths = Paths(code_dir, data_dir, default_cache_dir(self.environ))
        os.makedirs(data_dir, exist_ok=True)
        self.db = Database(self.paths.db_file)
        env_file = EnvFile(self.paths.env_file)
        store = AppSettingsStore(self.db)
        LegacyImport(self.paths, self.db, env_file, store).run()      # anciens config.json et JSON : une seule fois
        self.config = Settings(store, env_file, self.environ)
        self.texts = Texts(self.paths.i18n_dir, self.config.get("language"))
        self.version = read_version(code_dir)
        self.port = int(self.environ.get("PI_MEDIA_PORT", "8099"))
        self.bound_port = self.port
        self.phone_server = None
        self._build_library_relay()
        router = Router()
        self._add_page_routes(router)
        self._add_library_routes(router)
        self._add_screen_routes(router)
        self._add_player_routes(router)
        self._add_podcast_routes(router)
        self._add_extmusic_routes(router)
        self._add_phone_and_queue_routes(router)
        self.http = HttpApp(router, self._on_error)

    # ---------- relais Subsonic (cache, pochettes, informations) ----------
    def _build_library_relay(self):
        self.client = SubsonicClient(self.config)
        self.cache = JsonCache(self.paths.json_dir)
        self.covers_cache = CoverCache(self.paths.cover_dir, FOREVER)
        self.browse = BrowseMode(self.config)
        self.keys = CacheKeys(self.browse)
        self.api = CachedApi(self.client, self.cache, CachePolicy(), self.keys, self.browse)
        self.api.folders = FolderAdapter(self.api)
        self.covers = CoverService(self.client, self.covers_cache, self.keys)
        self.library = LibraryCache(self.cache)
        self.watcher = LibraryWatcher(self.api, self.library, NewestAlbums(self.paths.newest_file))
        fetcher = JsonFetcher()
        musicbrainz = MusicBrainz(fetcher)
        lyrics = LyricsFinder(fetcher, self._subsonic_lyrics)
        facts = FactsBuilder(musicbrainz, Wikipedia(fetcher), self._artist_biography)
        self.external = ExternalInfo(self.cache, self.keys, lyrics, facts, musicbrainz)

    def _subsonic_lyrics(self, artist, title):
        response = self.api.call_json("getLyrics", [("artist", artist), ("title", title)])
        return response.get("lyrics", {}).get("value", "")

    def _artist_biography(self, artist_id):
        response = self.api.call_json("getArtistInfo2", [("id", artist_id)])
        return response.get("artistInfo2", {}).get("biography", "")

    # ---------- routes ----------
    def _add_page_routes(self, router):
        self.pages = PagesController(WebFiles(self.paths))
        for path in ("/", "/index.html"):
            router.add("GET", path, self.pages.index)
        router.add_prefix("GET", "/static/", self.pages.static)
        router.add("GET", "/i18n.json", lambda request: Reply.json(self.texts.section("web.")))   # textes de la page
        router.add("GET", "/health", lambda request: Reply.json({"ok": True, "version": self.version}))
        router.add("GET", "/settings", SettingsController(self.config, self.browse).page)

    def _add_library_routes(self, router):
        info = InfoController(self.external)
        cache = CacheController(self.cache, self.covers_cache, self.library, self.watcher)
        router.add("GET", "/info/genres", info.genres)
        router.add("GET", "/info/lyrics", info.lyrics)
        router.add("GET", "/info/facts", info.facts)
        router.add("GET", "/cache/refresh", cache.refresh_album)
        router.add("GET", "/cache/clear", cache.clear)
        router.add_prefix("GET", "/rest/", RestController(self.api, self.covers, self.client).handle)

    def _add_screen_routes(self, router):
        """Échanges avec le menu tactile, volume, invités AirPlay/Bluetooth, historique des recherches."""
        pi = PiController(PiState(), SystemVolume(), self.browse)
        for name in ("send", "poll", "awake", "quit", "mode"):
            router.add("GET", "/control/" + name, getattr(pi, name))
        router.add("GET", "/control/volume", pi.set_volume)
        self.guests = GuestWatcher()
        guests = GuestController(self.guests)
        router.add("GET", "/control/guest", guests.state)
        router.add("POST", "/control/guest", guests.hand_over)
        history = HistoryController(SearchHistory(self.db))
        router.add("GET", "/ext/history", history.entries)
        router.add("POST", "/ext/history", history.change)

    def _add_player_routes(self, router):
        """Lecture haute fidélité par mpv."""
        socket_dir = self.environ.get("XDG_RUNTIME_DIR") or self.paths.cache_dir
        self.hifi = HifiPlayer(self.config, os.path.join(socket_dir, "pi-media-mpv.sock"),
                               lambda: "http://127.0.0.1:%d" % self.bound_port)
        player = PlayerController(self.hifi)
        router.add("GET", "/player/state", player.state)
        router.add("POST", "/player/cmd", player.command)

    def _add_podcast_routes(self, router):
        http = JsonHttp()
        hub = DirectoryHub(ItunesDirectory(http), PodcastIndexDirectory(http, self.config))
        self.podcasts = PodcastService(self.config, hub, FeedReader(FeedFetcher()), PodcastLibrary(self.db))
        podcasts = PodcastController(self.config, self.podcasts, self.pages)
        router.add("GET", "/podcasts", podcasts.page)
        for name in ("status", "home", "theme", "search", "show", "similar", "library"):
            router.add("GET", "/podcast-api/" + name, getattr(podcasts, name))
        for name in ("subscribe", "unsubscribe", "hide", "progress", "played", "language", "forget"):
            router.add("POST", "/podcast-api/" + name, getattr(podcasts, name))
        router.add("POST", "/podcast-api/key", podcasts.save_key)

    def _add_extmusic_routes(self, router):
        """Jamendo, YouTube et playlists locales."""
        http = JsonHttp()
        sources = [JamendoSource(http, self.config), YouTubeSource(http, self.config, YouTubeMusicSearch())]
        self.extmusic = ExtMusicService(self.config, sources, LocalPlaylists(self.db), UnplayableVideos(self.db))
        ext = ExtMusicController(self.extmusic)
        for name in ("status", "search", "playlists", "playlist", "favorites", "alternative"):
            router.add("GET", "/ext/" + name, getattr(ext, name))
        for name in ("settings", "create", "add", "remove", "delete", "favorite", "unplayable"):
            router.add("POST", "/ext/" + name, getattr(ext, name))

    def _add_phone_and_queue_routes(self, router):
        """File d'attente commune et saisie depuis le téléphone (côté écran du Pi)."""
        self.queue_service = QueueService(PlayQueue(self.db))
        queue = QueueController(self.queue_service)
        router.add("GET", "/queue/state", queue.state)
        router.add("POST", "/queue/save", queue.save)
        router.add("POST", "/queue/take", queue.take)
        self.remote_typing = RemoteTyping()
        remote = RemoteController(self.remote_typing, lambda: self.phone_server.port if self.phone_server else None)
        router.add("GET", "/ext/remote", remote.state)
        router.add("POST", "/ext/remote", remote.renew)
        router.add("POST", "/ext/remote/artists", remote.artists)
        self.phone_files = PhoneFiles(os.path.join(self.paths.data_dir, "phone-files"))
        router.add_prefix("GET", PHONE_FILES_URL, self._phone_file)

    def _phone_file(self, request):
        """Fichier envoyé depuis un téléphone (lu par la page ou par mpv, avec avance rapide)."""
        name = request.path[len(PHONE_FILES_URL):]
        path = self.phone_files.path_of(name)
        if path is None:
            return Reply.not_found()
        return FileReply(path, self.phone_files.content_type(name), request.header("Range"))

    @staticmethod
    def _on_error(error):
        print("erreur : %r" % (error,), flush=True)
        return Reply.json({"error": "erreur interne"}, 500)

    # ---------- démarrage ----------
    def prepare(self):
        """Charge le cache et lance la tâche de fond (préchauffage, nouveaux albums)."""
        self.cache.load()
        self.watcher.start()
        in_background(self.hifi.watch_forever)      # libère la sortie audio après une pause : l'ampli peut s'endormir

    def make_server(self):
        server = ThreadedServer((self.config.bind_address, self.port), make_request_handler(self.http))
        self.bound_port = server.server_address[1]      # port réel (0 dans les tests : choisi par le système)
        return server

    def start_phone_server(self, port=None):
        """Petit serveur séparé, ouvert sur le réseau local, pour les téléphones (désactivable : PHONE_REMOTE=false)."""
        if self.config.get("phone_remote") is False:
            return None
        try:
            links = LinkResolver(JsonHttp(), self._search_tracks, self._search_youtube)
            phone_queue = PhoneQueue(self.remote_typing, self._search_tracks, self.queue_service, self.phone_files, links)
            self.phone_server = PhoneServer(self.remote_typing, self.paths.web_dir,
                                            port if port is not None else int(self.config.get("phone_port", PHONE_PORT)),
                                            phone_queue=phone_queue)
        except OSError as error:            # port déjà pris : le reste de l'application fonctionne quand même
            print("Saisie depuis le téléphone indisponible :", error, flush=True)
            return None
        return self.phone_server.start()

    def _search_tracks(self, text):
        """Recherche de titres dans la bibliothèque Subsonic (pour les téléphones)."""
        response = self.api.call_json("search3", [("query", text), ("songCount", "20"), ("artistCount", "0"), ("albumCount", "0")])
        tracks = []
        for raw in (response.get("searchResult3") or {}).get("song") or []:
            try:
                tracks.append(Track.from_api(raw))
            except ValueError:
                continue
        return tracks

    def _search_youtube(self, text):
        """Recherche YouTube (si la source est activée dans les réglages), pour les liens partagés."""
        if not self.extmusic.enabled("youtube"):
            return []
        tracks = []
        for raw in self.extmusic.search("youtube", text)["items"]:
            try:
                tracks.append(Track.from_api(raw))
            except ValueError:
                continue
        return tracks

    def run(self):
        self.prepare()
        self.start_phone_server()
        self.make_server().serve_forever()
