"""Disques regroupés et catalogue musical : utilisables pour un artiste comme pour un label."""
from dataclasses import dataclass

from .discogs_entities import DiscogsIdentity


@dataclass(frozen=True)
class CatalogAlbum:
    id: str
    title: str
    artist: str
    year: int
    editions: tuple
    format: str = ""
    image: str = ""
    role: str = "Main"

    def to_api(self):
        return dict(id=self.id, title=self.title, artist=self.artist, year=self.year,
                    editions=[e.id for e in self.editions], format=self.format, image=self.image, role=self.role)


@dataclass
class MusicCatalog:
    identity: DiscogsIdentity
    albums: list
    total: int
    pages: int
    page: int

    def to_api(self):
        return dict(identity=self.identity.to_api(), albums=[a.to_api() for a in self.albums],
                    total=self.total, pages=self.pages, page=self.page, complete=self.page >= self.pages)
