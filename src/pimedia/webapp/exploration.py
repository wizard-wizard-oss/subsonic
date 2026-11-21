"""Labels et collaborations MusicBrainz. Aucun enrichissement ne modifie la bibliothèque.

Les éditions sont proposées par titre ET artiste exacts ; plusieurs éditions restent un choix explicite.
Les métadonnées publiques sont partagées, les recherches Subsonic sont toujours faites au nom du lecteur.
"""
import re

from ..shared.text import normalize
from .musicbrainz import (ExplorationUnavailable, MetadataResult, MusicBrainzMetadata, artist_name, artist_names,
                          mbid, search_phrase)
from .exploration_entities import (AlbumCredits, ArtistConnections, ArtistMatches, MusicArtist, MusicEdition,
                                   MusicLink, MusicProfile, MusicWork)

PAGE_SIZE = 25
ROLES = {"producer": "producer", "executive producer": "producer", "co-producer": "producer",
         "instrument": "musician", "vocal": "vocals", "performer": "musician", "guest performer": "musician",
         "composer": "composer", "writer": "composer", "lyricist": "lyricist", "conductor": "conductor",
         "mix": "mix", "recording": "engineer", "engineer": "engineer", "mastering": "mastering"}


class Exploration:
    def __init__(self, metadata, folders, library):
        self.metadata, self.folders, self.library = metadata, folders, library

    def artists(self, name):
        """Identités exactes, sans choisir un homonyme à la place de la personne."""
        name = str(name or "").strip()
        if not name or len(name) > 300:
            raise ValueError("artist")
        name_key = normalize(name)
        response = self.metadata.get("artist", query="artist:" + search_phrase(name), limit=25)
        artists = [MusicArtist(mbid(a["id"]), a["name"], a.get("type") or "", a.get("country") or "",
                               a.get("disambiguation") or "") for a in response.data.get("artists", [])
                   if normalize(a.get("name", "")) == name_key]
        return ArtistMatches(artists, response.stale)

    @staticmethod
    def _connections(raw):
        """Relations musicales explicites uniquement ; conserver les périodes, dédupliquer les doublons exacts."""
        roles = {"member of band": ("group", "member"), "collaboration": ("project", "collaborator"),
                 "subgroup": ("parent_group", "subgroup"),
                 "instrumental supporting musician": ("supporting_for", "supporting_member"),
                 "vocal supporting musician": ("supporting_for", "supporting_member")}
        found = {}
        for relation in raw.get("relations", []):
            artist = relation.get("artist") or {}
            if not artist.get("id") or relation.get("type") not in roles:
                continue
            forward, backward = roles[relation["type"]]
            role = backward if relation.get("direction") == "backward" else forward
            link = MusicLink(mbid(artist["id"]), artist["name"], "artist", role,
                             ", ".join(sorted(relation.get("attributes") or [])),
                             relation.get("begin") or "", relation.get("end") or "", bool(relation.get("ended")))
            found[(link.id, link.role, link.detail, link.begin, link.end, link.ended)] = link
        return sorted(found.values(), key=lambda link: (link.name.casefold(), link.role, link.begin, link.end))

    def connections(self, identity):
        """Un seul appel léger, sans catalogue : chargé à la demande pour chaque musicien."""
        identity = mbid(identity)
        response = self.metadata.get("artist/" + identity, inc="artist-rels")
        return ArtistConnections(identity, response.data.get("name", ""), self._connections(response.data), response.stale)

    def album(self, user, album_id, release=""):
        # Les noms viennent de l'album accessible par ce compte, pas d'un nom fourni par le navigateur.
        album = self.folders.album(user, album_id)
        title, artist = album["name"], album["artist"]
        response = self.metadata.get("release", query='release:%s AND artist:%s' % (search_phrase(title), search_phrase(artist)),
                                     limit=100)
        data = response.data
        title_key, artist_key = normalize(title), normalize(artist)
        candidates = [r for r in data.get("releases", []) if normalize(r.get("title", "")) == title_key
                      and artist_key in {normalize(a) for a in artist_names(r)}]
        editions = [MusicEdition(mbid(r["id"]), r["title"], artist_name(r), r.get("date", ""),
                                r.get("country", ""), ", ".join(m.get("format", "") for m in r.get("media", [])),
                                tuple(i.get("label", {}).get("name", "") for i in r.get("label-info", [])
                                      if i.get("label"))) for r in candidates]
        result = AlbumCredits(editions=editions, stale=response.stale)
        if not release:
            return result
        release = mbid(release)
        if release not in {e.id for e in editions}:
            raise ValueError("edition")
        details = self.metadata.get("release/" + release,
                                    inc="labels+artist-credits+recordings+artist-rels+recording-level-rels")
        raw = details.data
        result.stale = result.stale or details.stale
        result.selected = release
        result.labels = list({i["label"]["id"]: MusicLink(mbid(i["label"]["id"]), i["label"]["name"], "label",
                                                        "label", i.get("catalog-number", ""))
                              for i in raw.get("label-info", []) if i.get("label", {}).get("id")}.values())
        people = {}
        for credit in raw.get("artist-credit", []):
            if isinstance(credit, dict) and credit.get("artist", {}).get("id"):
                a = credit["artist"]
                people[(a["id"], "artist", "")] = MusicLink(mbid(a["id"]), a["name"])
        self._credits(raw, people)
        for medium in raw.get("media", []):
            for track in medium.get("tracks", []):
                self._credits(track.get("recording") or {}, people)
        result.people = sorted(people.values(), key=lambda p: (p.role, p.name.casefold(), p.detail))
        return result

    @staticmethod
    def _credits(raw, people):
        for relation in raw.get("relations", []):
            artist = relation.get("artist") or {}
            role = ROLES.get(relation.get("type"))
            if artist.get("id") and role:
                detail = ", ".join(relation.get("attributes") or [])
                key = (artist["id"], role, detail)
                people[key] = MusicLink(mbid(artist["id"]), artist["name"], "artist", role, detail)

    def profile(self, kind, identity, offset=0):
        if kind not in ("artist", "label") or not 0 <= offset <= 25000:
            raise ValueError("profile")
        identity = mbid(identity)
        identity_response = self.metadata.get(kind + "/" + identity, **({"inc": "artist-rels+release-rels+recording-rels"}
                                                                        if kind == "artist" else {}))
        raw = identity_response.data
        relations, works = self._connections(raw), {}
        for relation in raw.get("relations", []):
            for target in ("recording", "release"):
                item = relation.get(target) or {}
                if item.get("id") and relation.get("type") in ROLES:
                    key = (item["id"], ROLES[relation["type"]])
                    works[key] = MusicWork(mbid(item["id"]), item["title"], artist_name(item), target,
                                           item.get("date", ""), key[1])
        endpoint = "release" if kind == "label" else "release-group"
        catalog_response = self.metadata.get(endpoint, **{kind: identity, "inc": "artist-credits", "limit": PAGE_SIZE,
                                                         "offset": offset})
        data = catalog_response.data
        catalog = [MusicWork(mbid(r["id"]), r["title"], artist_name(r), endpoint,
                             r.get("first-release-date", r.get("date", ""))) for r in data.get(endpoint + "s", [])]
        # Les crédits sont séparés du catalogue principal : produire un disque n'en fait pas son artiste principal.
        all_works = catalog + (sorted(works.values(), key=lambda w: (w.date, w.title, w.role)) if offset == 0 else [])
        # MusicBrainz peut renvoyer moins que la limite (plafond du nombre de pistes par réponse).
        next_offset = offset + len(catalog)
        return MusicProfile(identity, raw.get("name", ""), kind, raw.get("disambiguation", ""), relations,
                            all_works, bool(catalog) and data.get(endpoint + "-count", 0) > next_offset,
                            offset, next_offset, stale=identity_response.stale or catalog_response.stale)

    def local(self, user, title, artist=""):
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 300 or len(artist) > 300:
            raise ValueError("search")
        # Recherche limitée aux résultats autorisés pour cette personne. Pas de cache public de disponibilité.
        found = self.library.search(user, title)
        title_key, artist_key = normalize(title), normalize(artist)
        return {"albums": [a for a in found["albums"] if normalize(a["name"]) == title_key
                           and (not artist or normalize(a["artist"]) == artist_key)],
                "songs": [s for s in found["songs"] if normalize(s["title"]) == title_key
                          and (not artist or normalize(s["artist"]) == artist_key)]}
