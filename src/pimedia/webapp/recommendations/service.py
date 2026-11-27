"""Send, group and dismiss recommendations without creating personal bookmarks."""
import re
import secrets
import time

from .entities import (COMMENT_MAX_LENGTH, DISCUSSION_PAGE_SIZE, ReceivedRecommendations,
                                      RecommendationDiscussion, RecommendationError, RecommendationGroup,
                                      RecommendationStatus)
from ..listen_later.targets import ListenLaterError, entry_id


READ_BATCH_SIZE = 200
RECEIVED_LIMIT = 200


class Recommendations:
    def __init__(self, repository, comments, targets, users, hub, clock=time.time):
        self.repository, self.comments = repository, comments
        self.targets, self.users, self.hub, self.clock = targets, users, hub, clock

    def received(self, user):
        page = self.repository.received(user.id, self.targets.library_key, RECEIVED_LIMIT)
        groups = {}
        for recommendation in page.recommendations:
            groups.setdefault(recommendation.target.key, []).append(recommendation)
        return ReceivedRecommendations(tuple(RecommendationGroup(items[0].target, tuple(items))
                                             for items in groups.values()), page.has_more)

    def send(self, sender, recipient_name, kind, source, source_id, comment=""):
        comment = self._comment_body(comment, optional=True)
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
        delivery = self.repository.add(sender.id, recipient.id, target, int(self.clock()), comment)
        if delivery.created:
            self.hub.publish("recommendations", {}, to_user_id=recipient.id)
        return delivery

    def archive(self, user, kind, source, source_id):
        removed = self.repository.archive(user.id, self.targets.key(kind, source, source_id), int(self.clock()))
        if removed:
            self.hub.publish("recommendations", {}, to_user_id=user.id)
        return removed

    def status(self, user):
        discussion = self.repository.unread_discussion(user.id, self.targets.library_key)
        return RecommendationStatus(discussion is not None or self.has_unread(user), discussion)

    def has_unread(self, user):
        return self.repository.has_unread(user.id, self.targets.library_key)

    def mark_read(self, user, ids):
        if not isinstance(ids, list) or not 1 <= len(ids) <= READ_BATCH_SIZE:
            raise ValueError("read batch")
        ids = [entry_id(identity) for identity in ids]
        updated = self.repository.mark_read(user.id, self.targets.library_key, ids, int(self.clock()))
        if updated:
            self.hub.publish("recommendations", {}, to_user_id=user.id)
        return self.has_unread(user)

    def discussions(self, user, scope, before=None):
        if scope not in ("sent", "archived"):
            raise ValueError("scope")
        before = entry_id(before) if before is not None else None
        return self.repository.page(user.id, self.targets.library_key, scope, before, DISCUSSION_PAGE_SIZE)

    def _discussion(self, user, identity):
        recommendation = self.repository.get(user.id, entry_id(identity), self.targets.library_key)
        if recommendation is None:
            raise RecommendationError("listen_later.discussion_not_found", 404)
        return recommendation

    @staticmethod
    def _comment_body(body, optional=False):
        if not isinstance(body, str):
            raise RecommendationError("listen_later.comment_invalid")
        body = body.strip()
        if len(body) > COMMENT_MAX_LENGTH:
            raise RecommendationError("listen_later.comment_too_long")
        if not body and not optional:
            raise RecommendationError("listen_later.comment_empty")
        return body

    def discussion(self, user, identity, before=None, after=None):
        recommendation = self._discussion(user, identity)
        before = entry_id(before) if before is not None else None
        after = entry_id(after) if after is not None else None
        if before is not None and after is not None:
            raise ValueError("comment cursors")
        page = self.comments.page(recommendation.id, before, after, DISCUSSION_PAGE_SIZE)
        return RecommendationDiscussion(recommendation, page)

    def comment(self, user, identity, body, client_token=None):
        recommendation = self._discussion(user, identity)
        body = self._comment_body(body)
        if client_token is None:
            client_token = secrets.token_hex(16)
        if not isinstance(client_token, str) or not re.fullmatch(r"[0-9a-f]{32}", client_token):
            raise ValueError("comment request token")
        comment = self.comments.add(recommendation.id, user.id, body, int(self.clock()), client_token)
        if comment is None:
            raise RecommendationError("listen_later.discussion_not_found", 404)
        if comment.body != body:
            raise RecommendationError("listen_later.comment_conflict", 409)
        for participant in (recommendation.sender_id, recommendation.recipient_id):
            self.hub.publish("recommendations", dict(discussionId=recommendation.id), to_user_id=participant)
        return comment

    def mark_comments_read(self, user, identity, comment_id):
        recommendation = self._discussion(user, identity)
        changed = self.comments.mark_read(recommendation.id, user.id, entry_id(comment_id), int(self.clock()))
        if changed:
            self.hub.publish("recommendations", dict(discussionId=recommendation.id), to_user_id=user.id)
        return self.has_unread(user)
