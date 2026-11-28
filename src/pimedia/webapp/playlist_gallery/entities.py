"""Projections du catalogue ; aucun contenu complet des playlists dans les cartes."""
from dataclasses import dataclass

PAGE_SIZE = 12
SORTS = ("name", "recent")
DEFAULT_SORT = SORTS[0]


@dataclass(frozen=True)
class PlaylistCard:
    id: str
    name: str
    owner: str
    mine: bool
    community: bool
    can_add: bool
    song_count: int
    duration: int
    cover_ids: list

    @classmethod
    def of(cls, detail):
        return cls(str(detail["id"]), detail["name"], detail["owner"], detail["mine"],
                   bool(detail.get("community")), bool(detail.get("canAdd")), detail["songCount"],
                   detail["duration"], detail["coverIds"])

    def to_api(self):
        return dict(id=self.id, name=self.name, owner=self.owner, mine=self.mine, community=self.community,
                    canAdd=self.can_add, songCount=self.song_count, duration=self.duration, coverIds=self.cover_ids)


@dataclass(frozen=True)
class PlaylistPage:
    playlists: list
    page: int
    has_more: bool
    sort: str

    def to_api(self):
        return dict(playlists=[card.to_api() for card in self.playlists], page=self.page,
                    hasMore=self.has_more, sort=self.sort, sorts=list(SORTS))
