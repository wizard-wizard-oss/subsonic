"""Enregistrement idempotent des écoutes confirmées et lecture de l’historique du compte."""
import time

from ...shared.limits import is_request_id
from ..listen_later.targets import entry_id
from .entities import HistoryPage, PAGE_SIZE


class ListeningHistory:
    def __init__(self, repository, targets, clock=time.time):
        self.repository, self.targets, self.clock = repository, targets, clock

    def record(self, user, song_id, request_id):
        if not is_request_id(request_id):
            raise ValueError("request id")
        target = self.targets.resolve(user, "song", "subsonic", song_id)
        return self.repository.add(user.id, target, request_id, int(self.clock()))

    def page(self, user, before=None):
        if before is not None:
            before = entry_id(before)
        rows = self.repository.recent(user.id, self.targets.library_key, PAGE_SIZE + 1, before)
        return HistoryPage(rows[:PAGE_SIZE], rows[PAGE_SIZE - 1].id if len(rows) > PAGE_SIZE else None)
