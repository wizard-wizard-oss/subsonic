"""Actualité : flux RSS ou Atom de webzines, ajoutés par n'importe qui, lus toutes les heures par le site.
Chaque article est gardé (titre, lien, date, début du résumé) : la page Actualité les montre tous, la page d'un artiste
ceux dont le titre contient son nom. Le site ne montre que des liens : l'article se lit chez le webzine."""
import html.parser
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

from ...server.podcasts.feeds import parse_date, plain_text
from .images import article_image

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
                             "summary": _summary(item), "image": article_image(item, link),
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


