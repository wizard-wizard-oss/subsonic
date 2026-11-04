"""Ce que la page Podcasts demande : accueil, thèmes, recherche, fiche d'un podcast, bibliothèque."""
from .directories import DirectoryError
from .feeds import FeedError, check_feed_url
from .language import LanguageResolver
from .relevance import rank
from .themes import DEFAULT_HOME_QUERIES, THEMES, find_theme


class PodcastService:
    HOME_ROW_SIZE = 14
    NEW_EPISODES_PER_SUB = 3

    def __init__(self, config, hub, reader, library):
        self.config = config
        self.hub = hub
        self.reader = reader
        self.library = library
        self.languages = LanguageResolver(reader)

    # ---------- état ----------
    def status(self):
        return {"sources": self.hub.sources, "themes": [t.describe() for t in THEMES], "french": self.french_only}

    @property
    def french_only(self):
        return self.config.get("podcast_french") is not False

    def set_french_only(self, value):
        self.config.update(podcast_french=bool(value))

    # ---------- découverte ----------
    def home(self):
        """Reprendre l'écoute, abonnements, puis une rangée par recherche choisie."""
        rows = []
        for query in self.config.get("podcast_home") or DEFAULT_HOME_QUERIES:
            row = self._safe_search(query)
            if row:
                rows.append({"title": query, "items": row[:self.HOME_ROW_SIZE]})
        return {"resume": self._resume(), "subs": self._subscriptions(), "rows": rows}

    def theme(self, key):
        theme = find_theme(key)
        if theme is None:
            raise DirectoryError("Thème inconnu")
        return {"theme": theme.describe(), "items": self._visible(self.hub.theme(theme))}

    def search(self, term):
        term = (term or "").strip()
        if len(term) < 2:
            return {"items": []}
        return {"items": rank(self._visible(self.hub.search(term)), term)}

    def similar(self, feed, genre, title):
        """« Dans le même genre » : les annuaires n'offrent pas de vraie similarité, on cherche donc par genre
        (ou par titre s'il est inconnu) et on retire le podcast lui-même."""
        term = (genre or "").split(",")[0].strip() or (title or "").strip()
        if len(term) < 2:
            return {"items": []}
        cards = [c for c in self._visible(self.hub.search(term)) if c["feed"] != feed]
        return {"items": cards[:self.HOME_ROW_SIZE]}

    def _safe_search(self, query):
        try:
            return self._visible(self.hub.search(query))
        except DirectoryError:
            return []

    def _visible(self, cards):
        """Sans les podcasts que l'utilisateur a masqués ; avec l'indication « abonné »."""
        shown = [c for c in cards if not self.library.is_hidden(c["feed"])]
        if self.french_only:
            shown = self.languages.french_only(shown)
        return [dict(c, subscribed=self.library.is_subscribed(c["feed"])) for c in shown]

    # ---------- fiche d'un podcast ----------
    def show(self, feed_url):
        check_feed_url(feed_url)
        feed = self.reader.read(feed_url)
        progress = {k: p.to_api() for k, p in self.library.progress_for_feed(feed_url).items()}
        episodes = [dict(e, pos=self._pos(progress, e), played=self._played(progress, e)) for e in feed["episodes"]]
        return {"feed": feed_url, "title": feed["title"], "author": feed["author"], "image": feed["image"],
                "desc": feed["desc"], "subscribed": self.library.is_subscribed(feed_url), "episodes": episodes}

    @staticmethod
    def _pos(progress, episode):
        return progress.get(episode["id"], {}).get("pos", 0)

    @staticmethod
    def _played(progress, episode):
        return bool(progress.get(episode["id"], {}).get("played"))

    # ---------- bibliothèque ----------
    def library_view(self):
        return {"resume": self._resume(), "subs": self._subscriptions(), "latest": self._latest_from_subscriptions()}

    def _resume(self):
        return [p.to_api() for p in self.library.resume_list()]

    def _subscriptions(self):
        return [s.to_api() for s in self.library.subscriptions()]

    def _latest_from_subscriptions(self):
        """Derniers épisodes des podcasts suivis, tous mélangés, du plus récent au plus ancien."""
        latest = []
        for sub in self._subscriptions():
            try:
                feed = self.reader.read(sub["feed"])
            except FeedError:
                continue
            for episode in feed["episodes"][:self.NEW_EPISODES_PER_SUB]:
                latest.append(dict(episode, feed=sub["feed"], podcast=sub["title"], image=episode["image"] or sub["image"],
                                   played=self._played_id(episode["id"])))
        return sorted(latest, key=lambda e: -e["date"])[:20]

    def _played_id(self, episode_id):
        progress = self.library.progress_of(episode_id)
        return bool(progress and progress.played)

    def subscribe(self, feed, title, image="", author=""):
        check_feed_url(feed)
        self.library.subscribe(feed, title or feed, image, author)

    def unsubscribe(self, feed):
        self.library.unsubscribe(feed)

    def hide(self, feed):
        self.library.hide(feed)

    def save_progress(self, episode):
        if not episode.get("id") or not episode.get("audio"):
            raise ValueError("épisode incomplet")
        self.library.save_progress(episode)

    def forget(self, episode_id):
        self.library.forget(episode_id)

    def mark_played(self, episode_id, played):
        self.library.mark_played(episode_id, played)
