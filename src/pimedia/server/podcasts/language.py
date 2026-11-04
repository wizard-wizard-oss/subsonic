"""Filtre « français » : la langue est donnée par Podcast Index ; pour iTunes (qui ne la donne pas), on la lit
dans le flux lui-même, en parallèle, une seule fois par podcast."""
from concurrent.futures import ThreadPoolExecutor, wait

from .feeds import FeedError

WORKERS = 8
DEADLINE_SECONDS = 8


def is_french(code):
    return code == "fr" or code.startswith("fr-") or code.startswith("fr_")


class LanguageResolver:
    def __init__(self, reader):
        self.reader = reader
        self.known = {}                 # adresse du flux -> code langue ("" si le flux n'en déclare pas)

    def french_only(self, cards):
        """Garde les podcasts français. Langue inconnue (flux illisible ou trop lent) : on garde, par prudence."""
        self._resolve([c for c in cards if not c.get("lang") and c["feed"] not in self.known])
        return [c for c in cards if self._keep(c)]

    def _keep(self, card):
        code = card.get("lang") or self.known.get(card["feed"], "")
        return not code or is_french(code)

    def _resolve(self, cards):
        if not cards:
            return
        pool = ThreadPoolExecutor(WORKERS)
        futures = {pool.submit(self._language_of, c["feed"]): c["feed"] for c in cards}
        done, _ = wait(futures, timeout=DEADLINE_SECONDS)
        for future in done:
            self.known[futures[future]] = future.result()
        pool.shutdown(wait=False)

    def _language_of(self, feed):
        try:
            return self.reader.read(feed).get("language", "")
        except FeedError:
            return ""
