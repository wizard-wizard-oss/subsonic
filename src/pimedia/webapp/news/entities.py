"""Flux suivis, articles et résultats de consultation de la presse."""
from dataclasses import dataclass
from typing import Optional
import hashlib


@dataclass
class NewsFeed:
    """Flux RSS ou Atom d'un webzine, suivi par tout le site (page Actualité, articles d'un artiste)."""
    id: int
    url: str
    title: str
    site_url: str
    added_by: Optional[int]
    added_at: int
    checked_at: Optional[int] = None
    error: str = ""                  # dernier problème de lecture (vide si le flux a été lu)
    articles: int = 0

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["url"], row["title"], row["site_url"], row["added_by"], row["added_at"],
                   row["checked_at"], row["error"], row["articles"])

    def to_api(self, can_remove=False, shown=True):
        return {"id": self.id, "url": self.url, "title": self.title, "siteUrl": self.site_url,
                "checkedAt": self.checked_at, "error": self.error, "articles": self.articles, "canRemove": can_remove,
                "shown": shown}


@dataclass
class NewsArticle:
    """Un article d'un flux : seulement de quoi faire un lien (rien n'est copié à part le début du résumé)."""
    id: int
    feed_id: int
    feed_title: str
    link: str
    title: str
    summary: str
    published_at: int
    image_url: str = ""

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["feed_id"], row["feed_title"], row["link"], row["title"], row["summary"],
                   row["published_at"], row["image_url"])

    def to_api(self):
        return {"id": self.id, "feedId": self.feed_id, "feed": self.feed_title, "link": self.link, "title": self.title,
                "summary": self.summary, "publishedAt": self.published_at,
                "imageUrl": self.image_api_url()}


    def image_api_url(self):
        if not self.image_url:
            return ""
        version = hashlib.sha256(self.image_url.encode()).hexdigest()[:12]
        return "/api/news/image?id=%s&v=%s" % (self.id, version)


@dataclass(frozen=True)
class NewsArticles:
    articles: tuple

    def to_api(self):
        return {"articles": [article.to_api() for article in self.articles]}


@dataclass(frozen=True)
class NewsPage(NewsArticles):
    more: bool

    def to_api(self):
        return dict(super().to_api(), more=self.more)


@dataclass(frozen=True)
class NewsFeedView:
    feed: NewsFeed
    can_remove: bool
    shown: bool = True

    def to_api(self):
        return self.feed.to_api(self.can_remove, self.shown)


@dataclass(frozen=True)
class NewsFeeds:
    feeds: tuple

    def to_api(self):
        return {"feeds": [feed.to_api() for feed in self.feeds]}
