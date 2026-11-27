"""La seule classe MusicBrainz : connexion, cadence, cache et toutes les recherches (anecdotes, exploration,
tags, sorties de la semaine). Les appelants reçoivent des entités, jamais le JSON du service."""
import re
import time
from dataclasses import replace
from urllib.parse import urlencode

from ...text import normalize
from ..metadata import ProviderUnavailable, PublicMetadata
from . import parsing
from .entities import (AlbumLabel, ArtistConnections, MusicArtist, MusicProfile, MusicWork, Release, ReleaseGenre,
                       Result, WeeklyReleasePage)

BASE = "https://musicbrainz.org/ws/2/"
GENRE_CATALOG_TTL = 86400
WEEKLY_TTL = 3600
SEARCH_LIMIT = 25
PAGE_SIZE = 25
MAX_LIMIT = 100                 # plus grande page acceptée par la recherche MusicBrainz
IDS_PER_QUERY = 20              # identifiants regroupés dans une même recherche
MAX_TAGS = 10
ALBUM_OR_EP = "(primarytype:album OR primarytype:ep)"


class MusicBrainz(PublicMetadata):
    prefix = "musicbrainz:"
    interval = 1.05
    ttl = 7 * 86400
    unavailable_code = "explore.unavailable"

    def _get(self, path, *, ttl=None, fmt="json", read=None, **params):
        query = urlencode(sorted(dict(params, fmt=fmt).items()))
        return self.fetch(path + "?" + query, BASE + path + "?" + query, read=read, ttl=ttl)

    # ---------- anecdotes et genres (Pi et site) ----------
    def genres(self, artist):
        """Genres d'après MusicBrainz (vocabulaire commun, plus fiable que les tags des fichiers)."""
        data = self._get("artist", query='artist:"%s"' % artist.replace('"', ""), limit=3).data
        for found in data.get("artists", []):
            if found.get("score", 0) >= 90:
                tags = sorted(found.get("tags", []), key=lambda t: -t.get("count", 0))
                names = [t["name"] for t in tags if t.get("count", 0) >= 1][:8]
                if names:
                    return {"genres": names}
        return {}

    def release_fact(self, artist, album):
        """« Album X, sorti en 1999 (il y a N ans) » d'après le groupe de sorties, ou None."""
        if not album:
            return None
        query = 'releasegroup:"%s" AND artist:"%s"' % (album.replace('"', ""), artist.replace('"', ""))
        try:
            data = self._get("release-group", query=query, limit=3).data
        except (ProviderUnavailable, OSError, ValueError):
            return None
        for group in data.get("release-groups", []):
            year = re.match(r"(\d{4})", group.get("first-release-date") or "")
            if group.get("score", 0) >= 90 and year:
                return describe_release(group.get("title") or album, int(year.group(1)))
        return None

    # ---------- exploration ----------
    def search_artists(self, name):
        response = self._get("artist", query="artist:" + parsing.search_phrase(name), limit=25)
        artists = tuple(MusicArtist(parsing.mbid(a["id"]), a["name"], a.get("type") or "", a.get("country") or "",
                                    a.get("disambiguation") or "") for a in response.data.get("artists", []))
        return Result(artists, response.stale)

    def artist_connections(self, identity):
        """Un seul appel léger, sans catalogue : chargé à la demande pour chaque musicien."""
        identity = parsing.mbid(identity)
        response = self._get("artist/" + identity, inc="artist-rels")
        return ArtistConnections(identity, response.data.get("name", ""), parsing.connections(response.data),
                                 response.stale)

    def find_releases(self, title, artist, limit=100):
        """Éditions candidates (le choix d'une édition reste à l'appelant), avec leurs noms d'artiste crédités."""
        query = "release:%s AND artist:%s" % (parsing.search_phrase(title), parsing.search_phrase(artist))
        response = self._get("release", query=query, limit=limit)
        found = tuple((parsing.edition(raw), tuple(parsing.artist_names(raw)))
                      for raw in response.data.get("releases", []) if raw.get("id") and raw.get("title"))
        return Result(found, response.stale)

    def release_credits(self, identity):
        """Labels et personnes créditées d'une édition."""
        identity = parsing.mbid(identity)
        response = self._get("release/" + identity,
                             inc="labels+artist-credits+recordings+artist-rels+recording-level-rels")
        return Result((parsing.release_labels(response.data), parsing.release_people(response.data)), response.stale)

    def profile(self, kind, identity, offset=0):
        """Fiche d'un artiste ou d'un label : relations, catalogue paginé, puis crédits (première page)."""
        identity = parsing.mbid(identity)
        inc = {"inc": "artist-rels+release-rels+recording-rels"} if kind == "artist" else {}
        identity_response = self._get(kind + "/" + identity, **inc)
        raw = identity_response.data
        endpoint = "release" if kind == "label" else "release-group"
        catalog_response = self._get(endpoint, **{kind: identity, "inc": "artist-credits", "limit": PAGE_SIZE,
                                                  "offset": offset})
        data = catalog_response.data
        catalog = [MusicWork(parsing.mbid(r["id"]), r["title"], parsing.artist_name(r), endpoint,
                             r.get("first-release-date", r.get("date", ""))) for r in data.get(endpoint + "s", [])]
        # Les crédits sont séparés du catalogue principal : produire un disque n'en fait pas son artiste principal.
        works = catalog + (parsing.credited_works(raw) if offset == 0 else [])
        # MusicBrainz peut renvoyer moins que la limite (plafond du nombre de pistes par réponse).
        next_offset = offset + len(catalog)
        return MusicProfile(identity, raw.get("name", ""), kind, raw.get("disambiguation", ""),
                            parsing.connections(raw), works,
                            bool(catalog) and data.get(endpoint + "-count", 0) > next_offset, offset, next_offset,
                            stale=identity_response.stale or catalog_response.stale)

    # ---------- tags ----------
    def search_releases(self, artist, album):
        """Candidats classés par MusicBrainz, sans imposer une égalité des tags à réparer."""
        query = "release:(%s) AND artist:(%s)" % (parsing.search_terms(album), parsing.search_terms(artist))
        response = self._get("release", query=query, limit=SEARCH_LIMIT)
        return tuple(parsing.edition(raw) for raw in response.data.get("releases", [])
                     if raw.get("id") and raw.get("title"))

    def release(self, identity):
        identity = parsing.mbid(identity)
        raw = self._get("release/" + identity, inc="artist-credits+recordings+release-groups+genres").data
        if parsing.mbid(raw.get("id")) != identity:
            raise ValueError("MusicBrainz release")
        artist = parsing.artist_name(raw)[:1000]
        media = raw.get("media") or []
        return Release(identity, str(raw.get("title") or "")[:1000], artist, str(raw.get("date") or "")[:20],
                       str(raw.get("country") or "")[:100], parsing.formats(media), self._release_genres(raw),
                       parsing.tracks(raw, artist))

    def _release_genres(self, raw):
        found = parsing.genres(raw)
        group = raw.get("release-group") or {}
        if found or not isinstance(group, dict):
            return found
        found = parsing.genres(group)
        if found:
            return found
        try:
            identity = parsing.mbid(group.get("id"))
            details = self._get("release-group/" + identity, inc="genres").data
            if parsing.mbid(details.get("id")) == identity:
                return parsing.genres(details)
        except (ProviderUnavailable, OSError, ValueError, TypeError, AttributeError):
            # Le genre complète l'édition : une panne de cet enrichissement ne doit pas retirer ses pistes.
            pass
        return ()

    # ---------- sorties de la semaine ----------
    def release_genres(self):
        result = self._get("genre/all", ttl=GENRE_CATALOG_TTL, fmt="txt", read=self._read_genre_catalog)
        return tuple(ReleaseGenre(name) for name in result.data["names"])

    def _read_genre_catalog(self, url):
        names = dict.fromkeys(name.strip() for name in self.http.get_text(url).splitlines())
        names.pop("", None)
        if not names:
            raise ValueError("Empty MusicBrainz genre catalog")
        return {"names": list(names)}

    def weekly_groups(self, genre, monday, sunday, limit, offset):
        return self._groups(f"tag:{parsing.search_phrase(genre)}", monday, sunday, limit, offset)

    def _groups(self, selection, start, end, limit=MAX_LIMIT, offset=0):
        """Albums et EP dont la première sortie tombe entre start et end, parmi la sélection donnée."""
        query = f"{selection} AND {ALBUM_OR_EP} AND firstreleasedate:[{start} TO {end}]"
        response = self._get("release-group", ttl=WEEKLY_TTL, query=query, limit=limit, offset=offset)
        rows = response.data["release-groups"]
        albums = tuple(album for album in map(parsing.weekly_group, rows) if album is not None)
        last = offset + len(rows)
        return WeeklyReleasePage(albums, last if rows and last < response.data["count"] else None, response.stale)

    # ---------- radar des sorties ----------
    def groups_by_artists(self, artist_ids, start, end, offset=0):
        """Sorties de plusieurs artistes en une requête (IDS_PER_QUERY au plus)."""
        ids = [parsing.mbid(identity) for identity in artist_ids][:IDS_PER_QUERY]
        return self._groups("(" + " OR ".join("arid:" + identity for identity in ids) + ")", start, end,
                            offset=offset)

    def release_label(self, title, artist):
        """Label de l'album d'après la première édition de ce titre et de cet artiste qui en indique un."""
        query = "release:%s AND artist:%s" % (parsing.search_phrase(title), parsing.search_phrase(artist))
        for raw in self._get("release", query=query, limit=SEARCH_LIMIT).data.get("releases", []):
            if normalize(raw.get("title")) != normalize(title) or \
                    normalize(artist) not in map(normalize, parsing.artist_names(raw)):
                continue
            for info in raw.get("label-info") or []:
                found = parsing.label(info.get("label") or {})
                if found:
                    return AlbumLabel(found, parsing.mbid(raw["id"]))
        return None

    def label_groups(self, label_id, start, end):
        """Nouveautés d'un label : ses éditions de la période, gardées si leur groupe sort pour la première fois."""
        query = (f"laid:{parsing.mbid(label_id)} AND {ALBUM_OR_EP} AND date:[{start} TO {end}]")
        response = self._get("release", ttl=WEEKLY_TTL, query=query, limit=MAX_LIMIT)
        groups = [(r.get("release-group") or {}) for r in response.data.get("releases", [])]
        ids = list(dict.fromkeys(g["id"] for g in groups
                                 if g.get("id") and str(g.get("primary-type", "")).lower() in ("album", "ep")))
        albums, stale = [], response.stale
        for index in range(0, len(ids), IDS_PER_QUERY):
            chunk = [parsing.mbid(identity) for identity in ids[index:index + IDS_PER_QUERY]]
            page = self._groups("(" + " OR ".join("rgid:" + identity for identity in chunk) + ")", start, end)
            albums += page.albums
            stale = stale or page.stale
        return WeeklyReleasePage(tuple(albums), None, stale)

    def search_labels(self, name):
        response = self._get("label", query="label:" + parsing.search_phrase(name), limit=SEARCH_LIMIT)
        found = (parsing.label(raw) for raw in response.data.get("labels", []))
        return Result(tuple(label for label in found if label is not None), response.stale)

    def artists_tags(self, artist_ids):
        """{MBID: tags votés, du plus voté au moins voté} de plusieurs artistes en une recherche (IDS_PER_QUERY au plus).
        Un artiste absent de la réponse a des tags vides."""
        ids = [parsing.mbid(identity) for identity in artist_ids][:IDS_PER_QUERY]
        query = "(" + " OR ".join("arid:" + identity for identity in ids) + ")"
        found = {identity: () for identity in ids}
        for raw in self._get("artist", ttl=WEEKLY_TTL, query=query, limit=MAX_LIMIT).data.get("artists", []):
            if raw.get("id") in found:
                found[raw["id"]] = parsing.tags(raw)[:MAX_TAGS]
        return found

    def artist_tags(self, artist_id):
        """Tags votés d'un artiste, du plus voté au moins voté (gardés 7 jours)."""
        return parsing.tags(self._get("artist/" + parsing.mbid(artist_id), inc="tags").data)[:MAX_TAGS]


def describe_release(title, year):
    text = "Album « %s », sorti en %d" % (title, year)
    age = time.localtime().tm_year - year
    if age > 0:
        text += " (il y a %d an%s)" % (age, "s" if age > 1 else "")
    return text + "."
