"""Règles de suivi et de consultation de la presse."""
import time
import urllib.parse

from ...shared.providers.feeds import FeedError, FeedFetcher
from .parsing import MAX_FEEDS, PAGE_SIZE, REFRESH_EVERY, NewsError, clean_address, feed_links_in_page, parse_articles
from .entities import NewsPage, NewsArticles, NewsFeeds, NewsFeedView


# ---------- service ----------
class News:
    def __init__(self, repository, fetcher=None):
        self.repository = repository
        self.fetcher = fetcher or FeedFetcher()

    @staticmethod
    def can_remove(user, feed):
        """L'admin, ou la personne qui a ajouté le flux (ceux du départ : l'admin seulement)."""
        return user.is_admin or (feed.added_by is not None and feed.added_by == user.id)

    def feeds(self, user):
        """Tous les flux du site ; shown : faux pour ceux que la personne a masqués."""
        hidden = self.repository.hidden(user.id)
        return NewsFeeds(tuple(NewsFeedView(f, self.can_remove(user, f), f.id not in hidden)
                               for f in self.repository.feeds()))

    def show(self, user, feed_id, shown):
        """Chacun choisit les flux qu'il voit (dans « Tout » et sur les pages artistes) ; le flux reste à tout le monde."""
        if self.repository.feed(feed_id) is None:
            raise NewsError("news.unknown_feed")
        self.repository.set_hidden(user.id, feed_id, not shown)

    def latest(self, user, feed_id=None, before=None):
        """{"articles": [...], "more": bool} ; before : (date, id) du dernier article déjà affiché."""
        articles = self.repository.latest(user.id, feed_id, before, PAGE_SIZE + 1)
        return NewsPage(tuple(articles[:PAGE_SIZE]), len(articles) > PAGE_SIZE)

    def about(self, user, name, limit=8):
        """Articles qui parlent d'un artiste (son nom dans le titre)."""
        name = (name or "").strip()
        if not name or len(name) > 300:
            raise ValueError(name)
        return NewsArticles(tuple(self.repository.mentioning(user.id, name, limit)))

    def add(self, user, address):
        """Adresse d'un flux, ou d'un site qui annonce son flux. Le flux est lu tout de suite."""
        url, feed = self._find_feed(clean_address(address))
        if self.repository.has_url(url):
            raise NewsError("news.already_followed")
        if self.repository.count() >= MAX_FEEDS:
            raise NewsError("news.too_many")
        title = feed["title"] or urllib.parse.urlsplit(url).hostname
        added = self.repository.add_feed(url, title, feed["site"], user.id)
        self.repository.add_articles(added.id, feed["articles"])
        self.repository.checked(added.id)
        return NewsFeedView(self.repository.feed(added.id), True)

    def image(self, user, article_id):
        article = self.repository.article(article_id)
        if article is None or not article.image_url:
            return None
        try:
            return self.fetcher.image(article.image_url)
        except FeedError:
            return None

    def remove(self, user, feed_id):
        feed = self.repository.feed(feed_id)
        if feed is None:
            raise NewsError("news.unknown_feed")
        if not self.can_remove(user, feed):
            raise NewsError("news.not_yours")
        self.repository.remove_feed(feed_id)

    def refresh(self):
        """Lit chaque flux et garde les nouveaux articles ; un flux en panne note son problème et sera relu."""
        added = 0
        for feed in self.repository.feeds():
            try:
                read = parse_articles(self._fetch(feed.url))
            except NewsError as error:
                self.repository.checked(feed.id, error.args[0])
                continue
            added += self.repository.add_articles(feed.id, read["articles"])
            self.repository.checked(feed.id)
        return added

    def run(self, every=REFRESH_EVERY):
        while True:
            self.refresh()
            time.sleep(every)

    def _find_feed(self, url):
        """(adresse du flux, flux lu) : l'adresse donnée si c'est un flux, sinon le flux annoncé par la page."""
        data = self._fetch(url)
        try:
            return url, parse_articles(data)
        except NewsError:
            pass
        for link in feed_links_in_page(data, url)[:3]:
            try:
                return link, parse_articles(self._fetch(link))
            except NewsError:
                continue
        raise NewsError("news.no_feed_found")

    def _fetch(self, url):
        try:
            return self.fetcher.fetch(url)
        except FeedError:
            raise NewsError("news.unreachable")
