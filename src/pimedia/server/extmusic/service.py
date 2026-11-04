"""Musique d'ailleurs : réglages (chaque source est désactivée par défaut), recherche, playlists locales."""
from ..podcasts.directories import DirectoryError
from ..podcasts.feeds import TtlCache
from ..podcasts.relevance import normalize, words_of
from .sources import is_alternate_version, song_parts


class ExtMusicService:
    SOURCE_KEYS = {"jamendo": ("ext_jamendo_on", "ext_jamendo_id"), "youtube": ("ext_youtube_on", "ext_youtube_key")}

    def __init__(self, config, sources, playlists, unplayable):
        self.config = config
        self.sources = {s.name: s for s in sources}
        self.playlists = playlists
        self.unplayable = unplayable
        self.cache = TtlCache(1800)

    # ---------- réglages ----------
    def status(self):
        """État de chaque source. Les clés elles-mêmes ne sont jamais renvoyées."""
        status = {name: {"configured": src.configured, "on": self._on(name), "enabled": self.enabled(name)}
                  for name, src in self.sources.items()}
        status["studio"] = self.studio_only
        return status

    @property
    def studio_only(self):
        """« Versions originales seulement » (sans live, reprises, remix…) : activé par défaut."""
        return self.config.get("ext_studio_only") is not False

    def _on(self, name):
        return bool(self.config.get(self.SOURCE_KEYS[name][0]))

    def enabled(self, name):
        return self._on(name) and self.sources[name].configured

    def update(self, body):
        """body : {jamendo_on, youtube_on, jamendo_id, youtube_key, studio} (champs facultatifs)."""
        changes = {}
        if "studio" in body:
            changes["ext_studio_only"] = bool(body["studio"])
        for name, (flag, key) in self.SOURCE_KEYS.items():
            if name + "_on" in body:
                changes[flag] = bool(body[name + "_on"])
            secret_field = "jamendo_id" if name == "jamendo" else "youtube_key"
            if secret_field in body:
                changes[key] = str(body[secret_field]).strip()
        for name, (flag, key) in self.SOURCE_KEYS.items():
            if changes.get(flag) and not (changes.get(key) if key in changes else self.config.get(key)):
                raise ValueError("Saisissez d’abord la clé de %s" % name.capitalize())
        self.config.update(**changes)

    # ---------- recherche ----------
    def search(self, source, term):
        term = (term or "").strip()
        if source not in self.sources or not self.enabled(source):
            raise DirectoryError("Source désactivée")
        if len(term) < 2:
            return {"items": []}
        key = source + ":" + term.lower()
        cached = self.cache.get(key)
        if cached is None:
            cached = self.sources[source].search(term)
            self.cache.put(key, cached)
        return {"items": self._filtered(cached)}

    def _filtered(self, items):
        """Filtres appliqués après le cache : un changement de réglage ou une vidéo refusée comptent tout de suite."""
        items = [i for i in items if not (i.get("youtubeId") and i["youtubeId"] in self.unplayable)]
        if self.studio_only:
            items = [i for i in items if not is_alternate_version(i.get("title"))]
        return items

    def alternative(self, video_id, title, artist=""):
        """Une autre vidéo du même titre, quand le lecteur a refusé celle-ci. None si rien de sûr n'est trouvé :
        on préfère passer au titre suivant que jouer une autre chanson."""
        artist, song = song_parts(title, artist)
        words = words_of(song)
        if not words:
            return None
        for item in self.search("youtube", (artist + " " + song).strip())["items"]:
            haystack = normalize(item["title"])
            if item["youtubeId"] != video_id and all(" " + w in haystack for w in words):
                return item
        return None

    def mark_unplayable(self, video_id):
        self.unplayable.add(video_id)
