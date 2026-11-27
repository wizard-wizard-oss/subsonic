"""Envoi administratif et consultation privée des notifications de service."""
import time

from ...shared.limits import is_request_id, is_username
from ..errors import MissingRight
from ..listen_later.targets import entry_id
from .entities import (BODY_MAX_LENGTH, PAGE_SIZE, TITLE_MAX_LENGTH, NotificationError, NotificationPage,
                                    NotificationStatus)


class Notifications:
    def __init__(self, repository, users, hub, clock=time.time):
        self.repository, self.users, self.hub, self.clock = repository, users, hub, clock

    @staticmethod
    def check_admin(user):
        if not user.can("admin"):
            raise MissingRight("admin")

    def recipients(self, user):
        self.check_admin(user)
        return self.users.usernames()

    @staticmethod
    def _text(value, maximum):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum or "\x00" in value:
            raise NotificationError("notifications.invalid_message")
        return value.strip()

    @staticmethod
    def _identity(value):
        try:
            return entry_id(value)
        except ValueError:
            raise NotificationError("notifications.invalid_request") from None

    def send(self, sender, recipient_name, title, body, request_id):
        self.check_admin(sender)
        title = self._text(title, TITLE_MAX_LENGTH)
        body = self._text(body, BODY_MAX_LENGTH)
        if not is_request_id(request_id):
            raise NotificationError("notifications.invalid_request")
        if not is_username(recipient_name):
            raise NotificationError("notifications.unknown_recipient")
        recipient = self.users.by_name(recipient_name)
        if recipient is None:
            raise NotificationError("notifications.unknown_recipient")
        delivery = self.repository.add(sender.id, recipient.id, title, body, request_id, int(self.clock()))
        if (delivery.notification.title, delivery.notification.body) != (title, body):
            raise NotificationError("notifications.request_conflict")
        if delivery.created:
            self.hub.publish("notifications", {}, to_user_id=recipient.id)
        return delivery.notification

    def page(self, user, before=None):
        before = self._identity(before) if before is not None else None
        entries = self.repository.page(user.id, before, PAGE_SIZE + 1)
        return NotificationPage(tuple(entries[:PAGE_SIZE]), entries[PAGE_SIZE - 1].id if len(entries) > PAGE_SIZE else None,
                                self.repository.unread(user.id))

    def status(self, user):
        return NotificationStatus(self.repository.unread(user.id))

    def mark_read(self, user, identity):
        identity = self._identity(identity)
        self.repository.mark_read(user.id, identity, int(self.clock()))
        self.hub.publish("notifications", {}, to_user_id=user.id)
        return self.status(user)
