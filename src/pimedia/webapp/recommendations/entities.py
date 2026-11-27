"""Private recommendations and their chronological comments."""
from dataclasses import dataclass

from ..listen_later.entities import ListeningTarget


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
    """Un conseil vu par une personne : unread_comments compte les commentaires qu'elle n'a pas lus."""
    id: int
    sender_id: int
    sender_name: str
    recipient_id: int
    recipient_name: str
    target: ListeningTarget
    created_at: int
    read_at: int | None
    archived_at: int | None
    comment_count: int
    comment_preview: str
    unread_comments: int

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["sender_id"], row["sender_name"], row["recipient_id"], row["recipient_name"],
                   ListeningTarget.from_row(row), row["created_at"], row["read_at"], row["archived_at"],
                   row["comment_count"], row["comment_preview"], row["unread_comments"])

    def to_api(self):
        return dict(id=self.id, sender=self.sender_name, senderId=self.sender_id,
                    recipient=self.recipient_name, recipientId=self.recipient_id,
                    target=self.target.to_api(), createdAt=self.created_at,
                    archivedAt=self.archived_at, commentCount=self.comment_count,
                    commentPreview=self.comment_preview, commentsUnread=self.unread_comments > 0)


@dataclass(frozen=True)
class RecommendationDelivery:
    recommendation: Recommendation
    created: bool

    def to_api(self):
        return dict(recommendation=self.recommendation.to_api(), created=self.created)


@dataclass(frozen=True)
class RecommendationGroup:
    target: ListeningTarget
    recommendations: tuple[Recommendation, ...]

    def to_api(self):
        return dict(target=self.target.to_api(),
                    unreadIds=[r.id for r in self.recommendations if r.read_at is None],
                    senders=[dict(id=r.sender_id, username=r.sender_name) for r in self.recommendations],
                    recommendations=[r.to_api() for r in self.recommendations],
                    createdAt=max(r.created_at for r in self.recommendations))


@dataclass(frozen=True)
class RecommendationPage:
    recommendations: tuple[Recommendation, ...]
    has_more: bool

    def to_api(self):
        return dict(recommendations=[r.to_api() for r in self.recommendations], hasMore=self.has_more)


@dataclass(frozen=True)
class ReceivedRecommendations:
    """Conseils reçus et actifs, regroupés par cible ; has_more signale des conseils plus anciens non affichés."""
    groups: tuple[RecommendationGroup, ...]
    has_more: bool


@dataclass(frozen=True)
class RecommendationCommentPage:
    comments: tuple[RecommendationComment, ...]
    has_more: bool


@dataclass(frozen=True)
class RecommendationDiscussion:
    recommendation: Recommendation
    page: RecommendationCommentPage

    def to_api(self):
        return dict(recommendation=self.recommendation.to_api(),
                    comments=[comment.to_api() for comment in self.page.comments], hasMore=self.page.has_more,
                    maxLength=COMMENT_MAX_LENGTH, pageSize=DISCUSSION_PAGE_SIZE)


@dataclass(frozen=True)
class RecommendationStatus:
    unread: bool
    discussion: Recommendation | None

    def to_api(self):
        return dict(unread=self.unread, unreadDiscussion=self.discussion.to_api() if self.discussion else None)
