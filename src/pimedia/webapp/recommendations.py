"""Send, group and dismiss recommendations without creating personal bookmarks."""
import re
import time

from .listen_later_entities import RecommendationGroup
from .listening_targets import ListenLaterError


READ_BATCH_SIZE = 200


class Recommendations:
    def __init__(self, repository, targets, users, hub, clock=time.time):
        self.repository, self.targets, self.users, self.hub, self.clock = repository, targets, users, hub, clock

    def received(self, user):
        groups = {}
        for recommendation in self.repository.received(user.id, self.targets.library_key):
            groups.setdefault(recommendation.target.key, []).append(recommendation)
        return [RecommendationGroup(items[0].target, tuple(items)) for items in groups.values()]

    def send(self, sender, recipient_name, kind, source, source_id):
        if not isinstance(recipient_name, str) or not 1 <= len(recipient_name) <= 200:
            raise ValueError("recipient")
        recipient = self.users.by_name(recipient_name)
        if recipient is None:
            raise ListenLaterError("listen_later.recipient_unknown")
        if recipient.id == sender.id:
            raise ListenLaterError("listen_later.self_recommendation")
        target = self.targets.resolve(sender, kind, source, source_id)
        if target.source == "subsonic":
            # Use the recipient's own access before exposing a library item to them.
            target = self.targets.resolve(recipient, kind, source, target.source_id)
        recommendation = self.repository.add(sender.id, recipient.id, target, int(self.clock()))
        self.hub.publish("recommendations", {}, to_user_id=recipient.id)
        return recommendation

    def remove(self, user, kind, source, source_id):
        removed = self.repository.remove(user.id, self.targets.key(kind, source, source_id))
        if removed:
            self.hub.publish("recommendations", {}, to_user_id=user.id)
        return removed

    def has_unread(self, user):
        return self.repository.has_unread(user.id, self.targets.library_key)

    def mark_read(self, user, tokens):
        if not isinstance(tokens, list) or not 1 <= len(tokens) <= READ_BATCH_SIZE:
            raise ValueError("read batch")
        if any(not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token) for token in tokens):
            raise ValueError("unread token")
        updated = self.repository.mark_read(user.id, self.targets.library_key, tokens)
        if updated:
            self.hub.publish("recommendations", {}, to_user_id=user.id)
        return self.has_unread(user)
