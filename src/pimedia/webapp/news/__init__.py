"""Presse : API interne conservée après séparation du lecteur XML et du service."""
from .parsing import NewsError, clean_address, feed_links_in_page, parse_articles
from .service import News
