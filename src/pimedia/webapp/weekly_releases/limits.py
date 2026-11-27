"""Limites et valeurs du radar des sorties : seule définition, envoyée au front quand il en a besoin."""
from datetime import timedelta

WINDOW_BEFORE = timedelta(days=14)        # sorties gardées en base avant aujourd'hui
WINDOW_AFTER = timedelta(days=60)         # … et annoncées après aujourd'hui
PURGE_AFTER = timedelta(days=30)          # une sortie plus ancienne que ça quitte la base
FULL_SYNC_EVERY = 86400                   # synchronisation complète au plus tard toutes les 24 h
NIGHT_HOUR = 4                            # heure locale de la synchronisation de nuit
REFRESH_COOLDOWN = 600                    # « Actualiser » : une fois toutes les 10 min par compte
STYLE_PAGES_PER_WEEK = 2                  # pages MusicBrainz lues par style et par semaine
ARTIST_PAGES = 3                          # pages MusicBrainz lues par lot d'artistes
SYNC_CHECK_EVERY = 900                    # la tâche de fond regarde toutes les 15 min s'il faut synchroniser
TREND_ARTISTS = 30                        # artistes des tendances par compte
TREND_RESOLVE_ATTEMPTS = 60               # recherches MusicBrainz d'un nom d'artiste sans MBID, par compte et par calcul
TREND_LABEL_ALBUMS = 30                   # albums dont on cherche le label, par compte et par nuit
TREND_STYLES = 5                          # styles des tendances par compte
SIMILAR_PER_ARTIST = 5                    # proches Last.fm gardés par artiste des tendances
DISCOVERIES_PER_USER = 60                 # proches (découvertes) par compte

RADAR_PAGE = 48                           # cartes par page de la semaine
LOCAL_CACHE_SECONDS = 300                 # « Dans ta bibliothèque » gardé 5 min par compte et par sortie
LOCAL_LOOKUPS_IN_PARALLEL = 4
MAX_NAME = 300                            # longueur maximale d'un nom de source ou d'une recherche

# Types de source : un style (nom exact du catalogue), un label, un artiste suivi, un proche (découverte).
STYLE, LABEL, ARTIST, SIMILAR = "style", "label", "artist", "similar"
KINDS = (STYLE, LABEL, ARTIST, SIMILAR)
MANUAL_KINDS = (STYLE, LABEL, ARTIST)     # ce qu'on ajoute soi-même ; les proches viennent des découvertes
SEARCH_KINDS = (LABEL, ARTIST)
ARTIST_KINDS = (ARTIST, SIMILAR)          # interrogés par lots d'identifiants d'artistes
# Origine d'une source : ajoutée par la personne, calculée d'après ses favoris, proposée comme découverte.
MANUAL, TRENDS, DISCOVERY = "manual", "trends", "discovery"
ORIGINS = (MANUAL, TRENDS, DISCOVERY)
