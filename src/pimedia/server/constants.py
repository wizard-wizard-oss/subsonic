"""Constantes partagées par tout le programme."""

API_VERSION = "1.16.1"
CLIENT_NAME = "pi-media"

# Durées de validité du cache, en secondes
FOREVER = 10 * 365 * 86400      # pochettes, bios, paroles : ne changent pas
LIBRARY_TTL = 30 * 86400        # bibliothèque : renouvelée seulement quand de nouveaux albums arrivent
SHORT_TTL = 300                 # favoris, playlists, recherche
STALE_WHILE_REVALIDATE_MIN_TTL = 3600   # au-delà : on sert l'ancienne version tout de suite et on rafraîchit en fond

# Paramètres d'authentification que le relais ajoute lui-même (le navigateur ne les envoie jamais)
AUTH_PARAMS = frozenset(("u", "t", "s", "p", "v", "c"))

# Appels qui renvoient du binaire (pas de cache JSON)
BINARY_ENDPOINTS = frozenset(("stream", "download", "hls", "getCoverArt", "getAvatar"))

# Appels qui modifient des données : le cache concerné est invalidé après coup
WRITE_ENDPOINTS = frozenset(("star", "unstar", "createPlaylist", "updatePlaylist", "deletePlaylist", "scrobble"))
STAR_AFFECTED = frozenset(("getStarred2", "getAlbum", "getPlaylist", "getTopSongs", "search3"))
PLAYLIST_AFFECTED = frozenset(("getPlaylists", "getPlaylist"))

# Appels « bibliothèque » (vidés quand de nouveaux albums arrivent ou sur demande)
LIBRARY_ENDPOINTS = frozenset(("getArtists", "getArtist", "getAlbum", "getGenres",
                               "getAlbumList2", "search3", "getStarred2"))
# Appels ID3 traduits en parcours par dossiers quand ce mode est choisi
FOLDER_ENDPOINTS = frozenset(("getArtists", "getArtist", "getAlbum", "getAlbumList2", "getStarred2",
                              "search3", "getArtistInfo2", "getSimilarSongs2"))

BROWSE_MODES = ("folders", "tags")

# Sécurité : les écritures demandent cet en-tête, qu'une page d'un autre site ne peut pas ajouter
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "pm"
LOOPBACK = ("127.0.0.1", "::1")
