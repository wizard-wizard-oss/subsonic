"""Objets publics Discogs nécessaires aux catalogues, éditions et discographies."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DiscogsIdentity:
    id: str
    name: str
    kind: str

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class DiscogsLabel:
    identity: DiscogsIdentity
    company_only: bool = False
    labels: tuple = ()

    def to_api(self):
        return dict(**self.identity.to_api(), companyOnly=self.company_only, labels=[l.to_api() for l in self.labels])


@dataclass(frozen=True)
class DiscogsMatches:
    identities: tuple
    more: bool

    def to_api(self):
        return dict(identities=[i.to_api() for i in self.identities], more=self.more)


@dataclass(frozen=True)
class DiscogsEdition:
    id: str
    master: str
    title: str
    artist: str
    year: int
    format: str
    image: str
    role: str = "Main"

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class DiscogsPage:
    editions: tuple
    page: int
    pages: int
    total: int


@dataclass(frozen=True)
class DiscogsTrack:
    title: str
    artist: str
    duration: str
    kind: str
    children: tuple = ()


@dataclass(frozen=True)
class DiscogsRelease:
    id: str
    title: str
    artist: str
    labels: tuple
    rating: float
    votes: int
    tracks: tuple
    credits: tuple = ()
    videos: tuple = ()
    image: str = ""


@dataclass(frozen=True)
class DiscogsVideo:
    youtube_id: str
    title: str
    duration: int = 0


@dataclass(frozen=True)
class DiscogsCredit:
    id: str
    name: str
    role: str
    tracks: str = ""

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class DiscogsArtist:
    identity: DiscogsIdentity
    members: tuple
    groups: tuple
    image: str = ""
    wikipedia_url: str = ""

    def to_api(self):
        return dict(**self.identity.to_api(), members=[i.to_api() for i in self.members],
                    groups=[i.to_api() for i in self.groups], image=self.image)


@dataclass(frozen=True)
class DiscogsAlbumCredits:
    editions: tuple
    selected: str = ""
    labels: tuple = ()
    people: tuple = ()

    def to_api(self):
        return dict(editions=[e.to_api() for e in self.editions], selected=self.selected,
                    labels=[l.to_api() for l in self.labels], people=[p.to_api() for p in self.people])
