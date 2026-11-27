"""Styles suivis par compte : les sources « style » du radar (table release_sources), identifiées par leur nom exact."""
from .release_radar import ReleaseSources

STYLE = "style"


class ReleaseSubscriptions:
    def __init__(self, db):
        self.sources = ReleaseSources(db)

    def for_user(self, user_id):
        return [source.identity for source in self.sources.for_user(user_id) if source.kind == STYLE]

    def follow(self, user_id, genre):
        self.sources.add(user_id, STYLE, genre, genre, "manual")

    def unfollow(self, user_id, genre):
        self.sources.hide_identity(user_id, STYLE, genre)
