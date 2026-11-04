"""Actualité : flux RSS ou Atom de webzines, ajoutés par n'importe qui, lus toutes les heures par le site.
Chaque article est gardé (titre, lien, date, début du résumé) : la page Actualité les montre tous, la page d'un artiste
ceux dont le titre contient son nom. Le site ne montre que des liens : l'article se lit chez le webzine."""
import html.parser
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

from ..server.podcasts.feeds import FeedError, FeedFetcher, parse_date, plain_text

MAX_FEEDS = 200
MAX_ARTICLES_READ = 100                    # par lecture d'un flux
REFRESH_EVERY = 3600
PAGE_SIZE = 40
FEED_TYPES = ("application/rss+xml", "application/atom+xml")


class NewsError(Exception):
    """args[0] : clé de texte montrée à la personne (« news.not_a_feed »…)."""


# ---------- lecture d'un flux (fonctions pures) ----------
def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(node, *names):
    for child in node:
        if _local(child.tag) in names:
            return child
    return None


def _text(node, *names):
    child = _child(node, *names)
    return "".join(child.itertext()).strip() if child is not None else ""


def _link(node):
    """<link>adresse</link> (RSS) ou <link rel="alternate" href="adresse"/> (Atom)."""
    for child in node:
        if _local(child.tag) != "link":
            continue
        if child.get("href") and child.get("rel", "alternate") == "alternate":
            return child.get("href").strip()
        if (child.text or "").strip():
            return child.text.strip()
    return ""


def _date(text):
    """RFC 822 (RSS) ou ISO 8601 (Atom, dc:date) -> secondes depuis 1970 (0 si illisible)."""
    seconds = parse_date(text)
    if seconds or not text:
        return seconds
    try:
        return int(datetime.fromisoformat(text.strip().replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


# « Cet article … est apparu en premier sur Mowno. » / « The post … appeared first on … » : rien à montrer
BOILERPLATE = re.compile(r"^(cet article .* est apparu en premier sur|the post .* appeared first on)", re.I)


def _summary(item):
    text = plain_text(_text(item, "description", "summary", "content"), 280)
    return "" if BOILERPLATE.match(text) else text


def _web_address(url):
    return url if re.match(r"^https?://[^\s]+$", url or "", re.I) else ""


def _without_undeclared_prefixes(data):
    """Beaucoup de flux WordPress utilisent « media: » sans le déclarer : le XML est alors refusé. On retire les
    préfixes (balises et attributs) pour lire le reste, dont on n'a pas besoin de l'espace de noms."""
    data = re.sub(rb"<(/?)([A-Za-z_][\w.-]*):", rb"<\1\2_", data)
    return re.sub(rb"(\s)(?!xmlns)([A-Za-z_][\w.-]*):([A-Za-z_][\w.-]*\s*=)", rb"\1\2_\3", data)


def parse_articles(data):
    """Octets d'un flux RSS (0.9x, 1.0, 2.0) ou Atom -> {"title", "site", "articles": [{"title", "link", "summary",
    "date"}]}. Seuls les articles avec un titre et une adresse web sont gardés."""
    if b"<!ENTITY" in data:                    # entités définies par le flux : risque d'explosion de mémoire
        raise NewsError("news.not_a_feed")
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        try:
            root = ET.fromstring(_without_undeclared_prefixes(data))
        except ET.ParseError:
            raise NewsError("news.not_a_feed")
    if _local(root.tag) not in ("rss", "feed", "RDF"):
        raise NewsError("news.not_a_feed")
    channel = _child(root, "channel") if _local(root.tag) != "feed" else root
    channel = root if channel is None else channel
    articles = []
    for item in root.iter():
        if _local(item.tag) not in ("item", "entry"):
            continue
        title, link = plain_text(_text(item, "title"), 300), _web_address(_link(item))
        if title and link:
            articles.append({"title": title, "link": link,
                             "summary": _summary(item),
                             "date": _date(_text(item, "pubDate", "published", "updated", "date"))})
        if len(articles) >= MAX_ARTICLES_READ:
            break
    return {"title": plain_text(_text(channel, "title"), 120), "site": _web_address(_link(channel)),
            "articles": articles}


class _FeedLinks(html.parser.HTMLParser):
    """<link rel="alternate" type="application/rss+xml" href="…"> d'une page web."""

    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and "alternate" in (attrs.get("rel") or "").lower().split() \
                and (attrs.get("type") or "").lower() in FEED_TYPES and attrs.get("href"):
            self.found.append(attrs["href"])


def feed_links_in_page(page, base_url):
    """Adresses des flux annoncés par une page web : d'abord celui de la rubrique collée (lesinrocks.com/musique/ ->
    son flux Musique plutôt que celui du site entier), les flux des commentaires en dernier."""
    parser = _FeedLinks()
    parser.feed(page.decode("utf-8", "replace"))
    links = [urllib.parse.urljoin(base_url, href) for href in parser.found]
    section = urllib.parse.urlsplit(base_url).path.rstrip("/")

    def order(link):
        in_section = bool(section) and urllib.parse.urlsplit(link).path.startswith(section + "/")
        return "comment" in link.lower(), not in_section
    return sorted(links, key=order)


def clean_address(text):
    """Ce que la personne a collé -> adresse web (https:// ajouté s'il manque)."""
    text = (text or "").strip()
    if not text or len(text) > 500 or any(c.isspace() for c in text):
        raise NewsError("news.invalid_address")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.I):
        text = "https://" + text
    parts = urllib.parse.urlsplit(text)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise NewsError("news.invalid_address")
    return text


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
        return [f.to_api(self.can_remove(user, f), f.id not in hidden) for f in self.repository.feeds()]

    def show(self, user, feed_id, shown):
        """Chacun choisit les flux qu'il voit (dans « Tout » et sur les pages artistes) ; le flux reste à tout le monde."""
        if self.repository.feed(feed_id) is None:
            raise NewsError("news.unknown_feed")
        self.repository.set_hidden(user.id, feed_id, not shown)

    def latest(self, user, feed_id=None, before=None):
        """{"articles": [...], "more": bool} ; before : (date, id) du dernier article déjà affiché."""
        articles = self.repository.latest(user.id, feed_id, before, PAGE_SIZE + 1)
        return {"articles": [a.to_api() for a in articles[:PAGE_SIZE]], "more": len(articles) > PAGE_SIZE}

    def about(self, user, name, limit=8):
        """Articles qui parlent d'un artiste (son nom dans le titre)."""
        name = (name or "").strip()
        if not name or len(name) > 300:
            raise ValueError(name)
        return [a.to_api() for a in self.repository.mentioning(user.id, name, limit)]

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
        return self.repository.feed(added.id).to_api(True)

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
