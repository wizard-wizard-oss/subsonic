"""Recherche précise d'un morceau : liens du catalogue, puis une recherche YouTube, trois choix au maximum."""
from dataclasses import dataclass

from .extmusic import ExtMusicError
from .youtube_matching import match_score, search_query

MAX_VERSIONS = 3
MAX_LINKS = 12


@dataclass(frozen=True)
class YouTubeVersionsResult:
    items: tuple
    warning: str = ""

    def to_api(self):
        return dict(items=list(self.items), warning=self.warning)


def ranked_versions(track, items, linked=(), labels=()):
    linked = set(linked)
    found = {}
    for item in items:
        identity = item["youtubeId"]
        score = match_score(track, item, identity in linked, labels)
        if score:
            found[identity] = dict(item, score=score, discoverySource="discogs" if identity in linked else "youtube")
    ranked = sorted(found.values(), key=lambda i: (-i["score"], i["discoverySource"] != "discogs", -i.get("playedHere", 0)))
    return tuple(ranked[:MAX_VERSIONS])


class YouTubeVersions:
    def __init__(self, external_music):
        self.external_music = external_music

    def find(self, user, track, videos=(), labels=()):
        ids = [v.youtube_id for v in videos if match_score(track, {"title": v.title, "duration": v.duration},
                                                         linked=True, labels=labels)][:MAX_LINKS]
        warning = ""
        if ids:
            try:
                found = ranked_versions(track, self.external_music.linked(user, ids), ids, labels)
                if found:
                    return YouTubeVersionsResult(found)
            except ExtMusicError as error:
                if error.args[0] != "ext.unreachable":
                    raise
                warning = "discovery.youtube_links_unavailable"
        items = self.external_music.search(user, "youtube", search_query(track), allow_versions=True)
        return YouTubeVersionsResult(ranked_versions(track, items, labels=labels), warning)
