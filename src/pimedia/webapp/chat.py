"""Salon global (tout le monde y poste) et commentaires sous chaque album. Pas de messages privés."""
import re
import time

from .entities import GENERAL_TOPIC, Attachment, album_of_topic

MAX_LENGTH = 2000
REACTIONS = ("👍", "❤️", "😂", "😮", "😢", "🔥", "🎵", "👏")
MENTION = re.compile(r"(?<![\w@])@([\w.+-]{1,64})")
ALBUM_ID = re.compile(r"^[\w-]{1,100}$")
EDIT_DELAY = 24 * 3600            # on peut corriger son message pendant 24 h


class ChatError(Exception):
    """Refus expliqué à la page : code (clé de texte i18n) et statut HTTP."""

    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def valid_topic(topic):
    if topic == GENERAL_TOPIC:
        return True
    album_id = album_of_topic(topic or "")
    return bool(album_id and ALBUM_ID.match(album_id))


def mentioned_names(body):
    return list(dict.fromkeys(m.group(1).rstrip(".") for m in MENTION.finditer(body or "")))


class SpamGuard:
    """Au plus LIMIT messages par WINDOW secondes et par personne."""

    LIMIT = 8
    WINDOW = 20

    def __init__(self, messages, clock=time.time):
        self.messages = messages
        self.clock = clock

    def check(self, user):
        if self.messages.recent_count(user.id, int(self.clock()) - self.WINDOW) >= self.LIMIT:
            raise ChatError("chat.too_fast", 429)


class Chat:
    def __init__(self, messages, users, hub, album_info, clock=time.time):
        self.messages = messages
        self.users = users
        self.hub = hub
        self.album_info = album_info        # (utilisateur, album_id) -> {"name", "artist", "coverId"}
        self.clock = clock
        self.guard = SpamGuard(messages, clock)

    # --- règles communes ---
    def _topic(self, topic):
        if not valid_topic(topic):
            raise ChatError("chat.bad_topic")
        return topic

    def _body(self, body, allow_empty=False):
        body = (body or "").strip() if isinstance(body, str) else ""
        body = "\n".join(line.rstrip() for line in body.splitlines())
        body = re.sub(r"\n{3,}", "\n\n", body)
        if len(body) > MAX_LENGTH:
            raise ChatError("chat.too_long")
        if not body and not allow_empty:
            raise ChatError("chat.empty")
        return body

    def _message(self, message_id):
        message = self.messages.get(message_id) if isinstance(message_id, int) else None
        if message is None:
            raise ChatError("chat.not_found", 404)
        return message

    def _mentions(self, author, body):
        return [u for u in self.users.by_names(mentioned_names(body)) if u.id != author.id]

    def _broadcast(self, kind, message):
        self.hub.publish(kind, message.to_api())

    # --- actions ---
    def post(self, user, topic, body, reply_to_id=None, attachment=None):
        topic = self._topic(topic)
        if album_of_topic(topic) and not user.can("comment"):
            raise ChatError("auth.missing_right", 403)             # droit Subsonic « commentaires et notes »
        attachment = Attachment.parse(attachment)
        body = self._body(body, allow_empty=attachment is not None)
        self.guard.check(user)
        if reply_to_id is not None:
            replied = self._message(reply_to_id)
            if replied.topic != topic:
                raise ChatError("chat.bad_reply")
        mentioned = self._mentions(user, body)
        message_id = self.messages.add(topic, user.id, body, reply_to_id, attachment, [u.id for u in mentioned],
                                       now=self.clock())
        album_id = album_of_topic(topic)
        if album_id:
            info = self.album_info(user, album_id)
            self.messages.touch_album(album_id, info.get("name", ""), info.get("artist", ""), info.get("coverId", ""),
                                      now=self.clock())
        self.messages.mark_read(user.id, topic, message_id)
        message = self.messages.get(message_id)
        self._broadcast("message", message)
        for target in mentioned:
            self.hub.publish("mention", message.to_api(), to_user_id=target.id)
        return message

    def edit(self, user, message_id, body):
        message = self._message(message_id)
        if message.user_id != user.id or message.deleted:
            raise ChatError("chat.forbidden", 403)
        if self.clock() - message.created_at > EDIT_DELAY:
            raise ChatError("chat.too_late", 403)
        body = self._body(body, allow_empty=message.attachment is not None)
        if body == message.body:
            return message
        self.messages.edit(message_id, body, [u.id for u in self._mentions(user, body)], now=self.clock())
        message = self.messages.get(message_id)
        self._broadcast("message_updated", message)
        return message

    def delete(self, user, message_id):
        """Son propre message, ou n'importe lequel pour un administrateur (modération)."""
        message = self._message(message_id)
        if message.deleted:
            return message
        if message.user_id != user.id and not user.is_admin:
            raise ChatError("chat.forbidden", 403)
        self.messages.delete(message_id, user.id, now=self.clock())
        message = self.messages.get(message_id)
        self._broadcast("message_updated", message)
        return message

    def react(self, user, message_id, emoji):
        if emoji not in REACTIONS:
            raise ChatError("chat.bad_reaction")
        message = self._message(message_id)
        if message.deleted:
            raise ChatError("chat.not_found", 404)
        self.messages.toggle_reaction(message_id, user.id, emoji, now=self.clock())
        message = self.messages.get(message_id)
        self._broadcast("message_updated", message)
        return message

    def typing(self, user, topic):
        return self.hub.typing(user, self._topic(topic))

    # --- lecture ---
    def history(self, user, topic, before_id=None, after_id=None, limit=50):
        topic = self._topic(topic)
        page = self.messages.page(topic, before_id, after_id, limit)
        return {"topic": topic, "messages": [m.to_api() for m in page],
                "lastRead": self.messages.last_read(user.id, topic), "hasMore": len(page) >= limit and not after_id}

    def search(self, user, topic, text):
        words = (text or "").split()[:5]
        if len("".join(words)) < 2:
            return []
        return [m.to_api() for m in self.messages.search(self._topic(topic), words)]

    def mentions(self, user):
        return [m.to_api() for m in self.messages.mentions_of(user.id)]

    def mark_read(self, user, topic, message_id):
        if not isinstance(message_id, int) or message_id < 0:
            raise ChatError("chat.not_found")
        self.messages.mark_read(user.id, self._topic(topic), message_id)
        return self.messages.unread(user.id, topic)

    def unread(self, user):
        return {"general": self.messages.unread(user.id, GENERAL_TOPIC)}
