"""Choix d'identité et visuels d'artistes : décisions privées et métadonnées publiques distinctes."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ArtistDiscogsLink:
    user_id: int
    library_key: str
    artist_id: str
    discogs_artist_id: str
    selected_at: int

    def to_api(self):
        return dict(artistId=self.artist_id, discogsArtistId=self.discogs_artist_id, selectedAt=self.selected_at)


@dataclass(frozen=True)
class ArtistImage:
    image_url: str = ""
    source: str = ""
    source_url: str = ""

    def to_api(self):
        return dict(imageUrl=self.image_url, source=self.source, sourceUrl=self.source_url)


@dataclass(frozen=True)
class ArtistContext:
    id: str
    name: str
    id3_id: str
    link: ArtistDiscogsLink | None
