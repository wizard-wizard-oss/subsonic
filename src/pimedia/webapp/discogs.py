"""Service Discogs : identités explicites, catalogues paginés et éditions. Aucun choix musical ici."""
import re
import urllib.parse

from ..shared.external import query_url
from ..shared.text import normalize
from .discogs_entities import (DiscogsArtist, DiscogsCredit, DiscogsEdition, DiscogsIdentity, DiscogsLabel, DiscogsMatches, DiscogsPage,
                              DiscogsRelease, DiscogsTrack, DiscogsVideo)
from .external_links import parse_link
from .extmusic import ExtMusicError
from .music_metadata import PublicMetadata

PAGE_SIZE = 100
MAX_PAGES = 1000
KINDS = ("label", "artist")


def discogs_id(value):
    value = str(value)
    if not re.fullmatch(r"[1-9][0-9]{0,14}", value):
        raise ValueError("Discogs ID")
    return value


def musical_name(value):
    """Suffixes d'homonymie de Discogs retirés pour rechercher la musique, jamais pour identifier une personne."""
    return re.sub(r"\s+\([0-9]+\)$", "", str(value or "")).strip()


def image_url(value):
    value = str(value or "")
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return ""
    return value if (len(value) <= 4096 and parsed.scheme == "https" and parsed.hostname == "i.discogs.com"
                     and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment) else ""


class Discogs(PublicMetadata):
    prefix = "discogs:"
    interval = 1.1
    base = "https://api.discogs.com/"

    def _get(self, path, params, project, cached=False, cache_version=1, refresh=False):
        url = query_url(path, sorted(params.items()))
        key = url if cache_version == 1 else url + "|v" + str(cache_version)
        if cached:
            return self.cached(key)
        return self.read(key, self.base + url, {"Authorization": "Discogs token=" + self.api_key}, project, refresh)

    @staticmethod
    def _kind(kind):
        if kind not in KINDS:
            raise ValueError("Discogs kind")
        return kind + "s/"

    def search(self, kind, name):
        self._kind(kind)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 300:
            raise ValueError("name")
        def project(raw):
            return dict(identities=[dict(id=discogs_id(i["id"]), name=str(i["title"])[:300], kind=kind)
                                    for i in raw.get("results", []) if i.get("type") == kind],
                        more=int((raw.get("pagination") or {}).get("pages") or 1) > 1)
        data = self._get("database/search", dict(q=name.strip(), type=kind, per_page=PAGE_SIZE), project)
        return DiscogsMatches(tuple(DiscogsIdentity(**i) for i in data["identities"]), data["more"])

    def identity(self, kind, identity):
        self._kind(kind)
        if kind == "artist":
            return self.artist(identity).identity
        return self.label(identity).identity

    def label(self, identity):
        data = self._get("labels/" + discogs_id(identity), {}, self._label_data, cache_version=2)
        return DiscogsLabel(DiscogsIdentity(data["id"], data["name"], "label"), data["company_only"],
                            tuple(DiscogsIdentity(**l) for l in data["labels"]))

    @classmethod
    def _label_data(cls, raw):
        profile = str(raw.get("profile") or "")
        company_only = bool(re.search(r"\buse\s+only\s+as\s+(?:a\s+)?company\b", profile, re.I))
        return dict(id=discogs_id(raw["id"]), name=str(raw["name"])[:300], company_only=company_only,
                    labels=cls._label_links(raw, profile) if company_only else [])

    @staticmethod
    def _label_links(raw, profile):
        """Seulement des identités liées par Discogs ; aucun rapprochement arbitraire avec un homonyme."""
        related = [dict(id=discogs_id(l["id"]), name=str(l["name"])[:300], kind="label")
                   for l in raw.get("sublabels") or [] if l.get("id") and l.get("name")]
        mentions = re.findall(r"\[l(?:=([^\]]+)|([0-9]+))\]", profile, flags=re.I)
        names = {normalize(name) for name, _ in mentions if name}
        identities = {identity for _, identity in mentions if identity}
        referenced = [l for l in related if normalize(l["name"]) in names or l["id"] in identities]
        return referenced or related

    @staticmethod
    def _related(raw):
        return [dict(id=discogs_id(i["id"]), name=str(i["name"])[:300], kind="artist")
                for i in raw or [] if i.get("id") and i.get("name")]

    @classmethod
    def _artist_data(cls, raw):
        return dict(id=discogs_id(raw["id"]), name=str(raw["name"])[:300], kind="artist",
                    members=cls._related(raw.get("members")), groups=cls._related(raw.get("groups")),
                    image=cls._artist_image(raw.get("images") or []),
                    wikipedia_url=next((u for u in raw.get("urls") or [] if isinstance(u, str) and len(u) <= 2048
                                        and re.fullmatch(r"https://[a-z]{2,3}\.wikipedia\.org/wiki/[^?#]+", u)), ""))

    @staticmethod
    def _artist_image(images):
        ordered = sorted(images, key=lambda i: i.get("type") != "primary")
        return next((url for i in ordered if (url := image_url(i.get("uri")))), "")

    def artist(self, identity):
        data = self._get("artists/" + discogs_id(identity), {}, self._artist_data, cache_version=2)
        person = DiscogsIdentity(data["id"], data["name"], "artist")
        return DiscogsArtist(person, tuple(DiscogsIdentity(**i) for i in data["members"]),
                             tuple(DiscogsIdentity(**i) for i in data["groups"]), data["image"], data["wikipedia_url"])

    def editions(self, artist, title):
        params = dict(type="release", artist=artist, release_title=title, per_page=PAGE_SIZE)
        data = self._get("database/search", params, lambda raw: self._edition_matches(raw, artist, title))
        return tuple(DiscogsEdition(**e) for e in data["editions"])

    @classmethod
    def _edition_matches(cls, raw, artist, title):
        found = []
        for result in raw.get("results", []):
            names = str(result.get("title") or "").split(" - ", 1)
            if len(names) == 2 and normalize(musical_name(names[0])) == normalize(artist) and normalize(names[1]) == normalize(title):
                found.append(cls._edition(dict(result, artist=names[0], title=names[1])))
        return {"editions": found}

    def catalog(self, kind, identity, page=1, cached=False, refresh=False):
        path = self._kind(kind) + discogs_id(identity) + "/releases"
        if type(page) is not int or not 1 <= page <= MAX_PAGES:
            raise ValueError("page")
        if refresh and (kind != "artist" or page != 1 or cached):
            raise ValueError("refresh")
        params = dict(page=page, per_page=PAGE_SIZE, sort="year", sort_order="asc")
        data = self._get(path, params, self._catalog_data, cached, refresh=refresh)
        if data is None:
            return None
        if refresh:
            self.repository.discard(self.prefix + path + "?", self.prefix + query_url(path, sorted(params.items())))
        return DiscogsPage(tuple(DiscogsEdition(**e) for e in data["editions"]), page, data["pages"], data["total"])

    @staticmethod
    def _edition(raw):
        master = raw.get("id") if raw.get("type") == "master" else raw.get("master_id")
        edition = raw.get("main_release") if raw.get("type") == "master" else raw.get("id")
        format = raw.get("format") or ""
        return dict(id=discogs_id(edition), master=discogs_id(master) if master else "",
                    title=str(raw.get("title") or "")[:300], artist=musical_name(raw.get("artist"))[:300],
                    year=int(raw.get("year") or 0), format=(", ".join(format) if isinstance(format, list) else str(format))[:200],
                    image=image_url(raw.get("thumb")), role=str(raw.get("role") or "Main")[:100])

    @classmethod
    def _catalog_data(cls, raw):
        pagination = raw["pagination"]
        return dict(pages=int(pagination["pages"]), total=int(pagination["items"]),
                    editions=[cls._edition(r) for r in raw.get("releases", [])
                              if r.get("id") and (r.get("type") != "master" or r.get("main_release"))])

    def release(self, identity, cached=False):
        data = self._get("releases/" + discogs_id(identity), {}, self._release_data, cached, cache_version=3)
        if data is None:
            return None
        return DiscogsRelease(data["id"], data["title"], data["artist"],
                              tuple(DiscogsIdentity(**i) for i in data["labels"]), data["rating"], data["votes"],
                              tuple(self._track(t) for t in data["tracks"]), tuple(DiscogsCredit(**c) for c in data["credits"]),
                              tuple(DiscogsVideo(**v) for v in data["videos"]), data["image"])

    @staticmethod
    def _artists(raw):
        return ", ".join(musical_name(a.get("anv") or a.get("name")) for a in raw or [])[:300]

    @classmethod
    def _track_data(cls, raw):
        return dict(title=str(raw.get("title") or "")[:300], artist=cls._artists(raw.get("artists")),
                    duration=str(raw.get("duration") or "")[:20], kind=raw.get("type_") or "track",
                    children=[cls._track_data(t) for t in raw.get("sub_tracks") or []])

    @classmethod
    def _track(cls, data):
        return DiscogsTrack(data["title"], data["artist"], data["duration"], data["kind"],
                            tuple(cls._track(t) for t in data["children"]))

    @classmethod
    def _release_data(cls, raw):
        rating = (raw.get("community") or {}).get("rating") or {}
        return dict(id=discogs_id(raw["id"]), title=str(raw.get("title") or "")[:300],
                    artist=cls._artists(raw.get("artists")), labels=[dict(id=discogs_id(l["id"]), name=str(l.get("name") or ""),
                                                                       kind="label") for l in raw.get("labels") or []],
                    rating=float(rating.get("average") or 0), votes=int(rating.get("count") or 0),
                    tracks=[cls._track_data(t) for t in raw.get("tracklist") or []], credits=cls._credits(raw),
                    videos=cls._videos(raw.get("videos") or []), image=cls._artist_image(raw.get("images") or []))

    @staticmethod
    def _videos(raw):
        found = {}
        for video in raw[:50]:
            try:
                kind, identity = parse_link(str(video.get("uri") or ""))
            except ExtMusicError:
                continue
            if kind == "youtube_video":
                duration = video.get("duration")
                found[identity] = dict(youtube_id=identity, title=str(video.get("title") or "")[:300],
                                       duration=duration if type(duration) is int and 0 <= duration < 86400 else 0)
        return list(found.values())

    @classmethod
    def _credits(cls, raw):
        credits = [dict(c, role="artist") for c in raw.get("artists") or []]
        credits += raw.get("extraartists") or []
        credits += list(cls._track_credits(raw.get("tracklist") or []))
        found = {}
        for credit in credits:
            if credit.get("id") and credit.get("name"):
                item = dict(id=discogs_id(credit["id"]), name=str(credit.get("anv") or credit["name"])[:300],
                            role=str(credit.get("role") or "artist")[:300], tracks=str(credit.get("tracks") or "")[:100])
                found[(item["id"], item["role"], item["tracks"])] = item
        return list(found.values())

    @classmethod
    def _track_credits(cls, tracks):
        for track in tracks:
            for credit in track.get("extraartists") or []:
                yield dict(credit, tracks=track.get("position") or "")
            yield from cls._track_credits(track.get("sub_tracks") or [])
