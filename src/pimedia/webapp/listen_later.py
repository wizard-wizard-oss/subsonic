"""Personal artist and album bookmarks; playback stays in its existing services."""
import time

from .listening_targets import entry_id


class ListenLater:
    def __init__(self, repository, targets, clock=time.time):
        self.repository, self.targets, self.clock = repository, targets, clock

    def all(self, user):
        return self.repository.all(user.id, self.targets.library_key)

    def add(self, user, kind, source, source_id):
        target = self.targets.resolve(user, kind, source, source_id)
        return self.repository.add(user.id, target, int(self.clock()))

    def remove(self, user, identity):
        return self.repository.remove(user.id, entry_id(identity))
