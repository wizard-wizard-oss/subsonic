"""Private recommendations and their chronological comments."""
from dataclasses import dataclass

from .listen_later_entities import ListeningTarget


COMMENT_MAX_LENGTH = 1000
DISCUSSION_PAGE_SIZE = 50


class RecommendationError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


@dataclass(frozen=True)
class RecommendationComment:
    id: int
    recommendation_id: int
    author_id: int
    author_name: str
    body: str
    created_at: int

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["recommendation_id"], row["author_id"], row["author_name"],
                   row["body"], row["created_at"])

    def to_api(self):
        return dict(id=self.id, recommendationId=self.recommendation_id, authorId=self.author_id,
                    author=self.author_name, body=self.body, createdAt=self.created_at)


@dataclass(frozen=True)
class Recommendation:
    id: int
    sender_id: int
    sender_name: str
    recipient_id: int
    recipient_name: str
    target: ListeningTarget
    created_at: int
    unread_token: str | None
    recipient_archived_at: int | None
    sender_last_read_comment_id: int
    recipient_last_read_comment_id: int
    sender_last_comment_id: int
    recipient_last_comment_id: int
    comment_count: int
    comment_preview: str

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["sender_id"], row["sender_name"], row["recipient_id"], row["recipient_name"],
                   ListeningTarget.from_row(row), row["created_at"], row["unread_token"],
                   row["recipient_archived_at"], row["sender_last_read_comment_id"],
                   row["recipient_last_read_comment_id"], row["sender_last_comment_id"],
                   row["recipient_last_comment_id"], row["comment_count"], row["comment_preview"])

    def last_read(self, user_id):
        return self.sender_last_read_comment_id if user_id == self.sender_id else self.recipient_last_read_comment_id

    def unread_comments(self, user_id):
        last_incoming = self.recipient_last_comment_id if user_id == self.sender_id else self.sender_last_comment_id
        return last_incoming > self.last_read(user_id)

    def to_api(self, user_id):
        return dict(id=self.id, sender=self.sender_name, senderId=self.sender_id,
                    recipient=self.recipient_name, recipientId=self.recipient_id,
                    target=self.target.to_api(), createdAt=self.created_at,
                    archivedAt=self.recipient_archived_at, commentCount=self.comment_count,
                    commentPreview=self.comment_preview, commentsUnread=self.unread_comments(user_id))


@dataclass(frozen=True)
class RecommendationDelivery:
    recommendation: Recommendation
    created: bool

    def to_api(self, user_id):
        return dict(recommendation=self.recommendation.to_api(user_id), created=self.created)


@dataclass(frozen=True)
class RecommendationGroup:
    target: ListeningTarget
    recommendations: tuple[Recommendation, ...]

    def to_api(self):
        return dict(target=self.target.to_api(),
                    unreadTokens=[r.unread_token for r in self.recommendations if r.unread_token is not None],
                    senders=[dict(id=r.sender_id, username=r.sender_name) for r in self.recommendations],
                    recommendations=[r.to_api(r.recipient_id) for r in self.recommendations],
                    createdAt=max(r.created_at for r in self.recommendations))


@dataclass(frozen=True)
class RecommendationPage:
    recommendations: tuple[Recommendation, ...]
    has_more: bool

    def to_api(self, user_id):
        return dict(recommendations=[r.to_api(user_id) for r in self.recommendations], hasMore=self.has_more)


@dataclass(frozen=True)
class RecommendationCommentPage:
    comments: tuple[RecommendationComment, ...]
    has_more: bool


@dataclass(frozen=True)
class RecommendationDiscussion:
    recommendation: Recommendation
    page: RecommendationCommentPage

    def to_api(self, user_id):
        return dict(recommendation=self.recommendation.to_api(user_id),
                    comments=[comment.to_api() for comment in self.page.comments], hasMore=self.page.has_more,
                    maxLength=COMMENT_MAX_LENGTH, pageSize=DISCUSSION_PAGE_SIZE)


@dataclass(frozen=True)
class RecommendationStatus:
    unread: bool
    discussion: Recommendation | None

    def to_api(self, user_id):
        return dict(unread=self.unread, unreadDiscussion=self.discussion.to_api(user_id) if self.discussion else None)
