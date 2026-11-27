"""Limites et valeurs du radar des sorties : seule définition, envoyée au front quand il en a besoin."""
from datetime import timedelta

WINDOW_BEFORE = timedelta(days=14)        # sorties gardées en base avant aujourd'hui
WINDOW_AFTER = timedelta(days=60)         # … et annoncées après aujourd'hui
PURGE_AFTER = timedelta(days=30)          # une sortie plus ancienne que ça quitte la base
FULL_SYNC_EVERY = 86400                   # synchronisation complète au plus tard toutes les 24 h
NIGHT_HOUR = 4                            # heure locale de la synchronisation de nuit
REFRESH_COOLDOWN = 600                    # « Actualiser » : une fois toutes les 10 min par compte
STYLE_PAGES_PER_WEEK = 2                  # pages MusicBrainz lues par style et par semaine
SYNC_CHECK_EVERY = 300                    # la tâche de fond regarde toutes les 5 min s'il faut synchroniser
RETRY_FAILED_AFTER = 600                  # une source en échec est réessayée 10 min plus tard, sans attendre la nuit
TREND_ARTISTS = 500                       # artistes des favoris suivis par compte (rapprochement local, presque gratuit)
TREND_RESOLVE_ATTEMPTS = 60               # recherches MusicBrainz d'un nom d'artiste sans MBID, par compte et par calcul
TREND_LABEL_ALBUMS = 30                   # albums dont on cherche le label, par compte et par nuit
TREND_STYLES = 5                          # styles dominants proposés par compte
STYLES_PER_ARTIST = 3                     # styles d'un artiste pris en compte (ses 3 tags les plus votés du catalogue)
MIN_STYLE_ARTISTS = 3                     # un style porté par moins de 3 artistes n'est pas dominant
SITE_ALBUMS = 50                          # sans favori : albums les plus écoutés du sub pris pour les styles génériques
RESOLVE_AGAIN_AFTER = 30 * 86400          # un nom d'artiste introuvable est recherché de nouveau après 30 jours
COVER_LOOKUPS = 300                       # pochettes cherchées sur Last.fm par synchronisation complète
AROUND_SIMILAR = 30                       # « Autour de… » : proches demandés à Last.fm pour un artiste

RADAR_PAGE = 48                           # cartes par page de la semaine
LOCAL_CACHE_SECONDS = 300                 # « Dans ta bibliothèque » gardé 5 min par compte et par sortie
LOCAL_LOOKUPS_IN_PARALLEL = 4
MAX_NAME = 300                            # longueur maximale d'un nom de source ou d'une recherche

# Types de source : un style (nom exact du catalogue), un label, un artiste suivi.
STYLE, LABEL, ARTIST = "style", "label", "artist"
KINDS = (STYLE, LABEL, ARTIST)
MANUAL_KINDS = KINDS                      # tout se suit aussi à la main
SEARCH_KINDS = (LABEL, ARTIST)
# Sorties lues chez ListenBrainz pour tout le site (pas une source d'un compte) : « Mes artistes » et « Autour de… ».
FRESH, FRESH_IDENTITY = "fresh", "listenbrainz"
# Origine d'une source : ajoutée par la personne ou calculée d'après ses favoris.
MANUAL, TRENDS = "manual", "trends"
ORIGINS = (MANUAL, TRENDS)
# D'où viennent les styles proposés : les favoris du compte ou, sans favori, le sub entier.
FAVORITES, SITE = "favorites", "site"
