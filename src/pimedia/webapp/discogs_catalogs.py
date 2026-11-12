"""Catalogues de labels et discographies : pagination et regroupement des rééditions."""
from ..shared.text import normalize
from .discogs import MAX_PAGES
from .catalog_entities import CatalogAlbum, MusicCatalog
from .music_metadata import MusicSourceError


class CatalogError(ValueError):
    """Fiche incompatible avec un catalogue musical (société, droits, fabrication)."""


def group_editions(editions):
    """Un master par disque. Sans master, regrouper seulement les titres/artistes exacts sans master concurrent."""
    names, groups = {}, {}
    for edition in editions:
        name = (normalize(edition.artist), normalize(edition.title))
        if edition.master:
            names.setdefault(name, set()).add(edition.master)
    for edition in editions:
        name = (normalize(edition.artist), normalize(edition.title))
        masters = names.get(name, set())
        master = edition.master or (next(iter(masters)) if len(masters) == 1 else "")
        key = ("master", master) if master else ("name", name)
        groups.setdefault(key, {})[edition.id] = edition
    return sorted((_album(list(editions.values())) for editions in groups.values()),
                  key=lambda a: (a.year or 9999, normalize(a.artist), normalize(a.title), a.id))


def _album(editions):
    editions.sort(key=lambda e: (e.year or 9999, int(e.id)))
    first = editions[0]
    master = next((e.master for e in editions if e.master), "")
    identity = "m" + master if master else "r" + min((e.id for e in editions), key=int)
    role = "Main" if any(e.role == "Main" for e in editions) else first.role
    return CatalogAlbum(identity, first.title, first.artist, first.year, tuple(editions), first.format,
                      next((e.image for e in editions if e.image), ""), role)


class DiscogsCatalogs:
    def __init__(self, discogs):
        self.discogs = discogs

    def page(self, kind, identity, page, refresh=False):
        """Charger une seule page réseau, puis reconstruire les pages déjà lues pour consolider les rééditions."""
        if type(page) is not int or not 1 <= page <= MAX_PAGES:
            raise ValueError("page")
        person = self._identity(kind, identity)
        current = self.discogs.catalog(kind, identity, page, refresh=refresh)
        if current.pages > MAX_PAGES:
            raise MusicSourceError("discovery.catalog_large")
        if page > max(1, current.pages):
            raise ValueError("page")
        editions = self._editions(kind, identity, page)
        return MusicCatalog(person, group_editions(editions), current.total, max(1, current.pages), page)

    def _editions(self, kind, identity, pages):
        editions = []
        for page in range(1, pages + 1):
            batch = self.discogs.catalog(kind, identity, page, cached=True)
            if batch is None:
                raise MusicSourceError("discovery.load_catalog")
            editions.extend(batch.editions)
        return editions

    def complete(self, kind, identity):
        if not self.discogs.enabled:
            raise MusicSourceError("discovery.disabled")
        self._identity(kind, identity)
        first = self.discogs.catalog(kind, identity, cached=True)
        if first is None or first.pages > MAX_PAGES:
            raise MusicSourceError("discovery.load_catalog")
        return group_editions(self._editions(kind, identity, max(1, first.pages)))

    def _identity(self, kind, identity):
        if kind == "label":
            details = self.discogs.label(identity)
            if details.company_only:
                raise CatalogError("discovery.company_only")
            return details.identity
        return self.discogs.identity(kind, identity)
