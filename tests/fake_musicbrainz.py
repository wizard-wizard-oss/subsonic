"""MusicBrainz simulé : plusieurs éditions, crédits d'album et de piste, groupe et catalogue paginé."""
import copy
import urllib.parse


def identity(number):
    return "00000000-0000-4000-8000-%012d" % number


RELEASE, OTHER_RELEASE, GROUP, PRODUCER, MEMBER, LABEL, RECORDING, WORK = [identity(n) for n in range(1, 9)]
SIDE_GROUP = identity(9)
ARTIST_CREDIT = [{"name": "ABBA", "artist": {"id": GROUP, "name": "ABBA"}}]
RELATION = {"type": "producer", "artist": {"id": PRODUCER, "name": "Producteur test"}}
EDITION = {"id": RELEASE, "title": "Arrival", "artist-credit": ARTIST_CREDIT, "date": "1976-10-11", "country": "SE",
           "media": [{"format": "Vinyl"}], "label-info": [{"label": {"id": LABEL, "name": "Polar"}}]}


class FakeMusicBrainz:
    def __init__(self):
        self.urls = []
        self.down = False
        self.failures = []
        self.editions = [EDITION, dict(EDITION, id=OTHER_RELEASE, date="2001", country="GB")]
        self.artists = [{"id": GROUP, "name": "ABBA", "type": "Group", "country": "SE"},
                        {"id": PRODUCER, "name": "ABBA", "type": "Person", "disambiguation": "homonyme"}]

    def get(self, url, timeout=8):
        self.urls.append(url)
        if self.failures:
            raise self.failures.pop(0)
        if self.down:
            raise OSError("source unavailable")
        path = urllib.parse.urlsplit(url).path.removeprefix("/ws/2/")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if path == "release" and "query" in query:
            return copy.deepcopy({"releases": self.editions, "release-count": len(self.editions)})
        if path == "artist" and "query" in query:
            return copy.deepcopy({"artists": self.artists})
        if path.startswith("release/"):
            return copy.deepcopy(dict(EDITION, relations=[RELATION], media=[{"tracks": [{"recording": {
                "relations": [RELATION, {"type": "instrument", "attributes": ["guitar"],
                                         "artist": {"id": MEMBER, "name": "Musicien test"}}]}}]}]))
        if path == "label/" + LABEL:
            return {"id": LABEL, "name": "Polar", "disambiguation": "label suédois"}
        if path.startswith("artist/"):
            current = path.rsplit("/", 1)[-1]
            is_group = current in (GROUP, SIDE_GROUP)
            relation = {"type": "member of band", "direction": "backward" if is_group else "forward",
                        "artist": {"id": MEMBER if is_group else GROUP,
                                   "name": "Musicien test" if is_group else "ABBA"},
                        "begin": "1972", "end": "1982", "ended": True}
            others = [] if is_group else [
                {"type": "member of band", "direction": "forward", "begin": "1980", "end": "1985", "ended": True,
                 "artist": {"id": SIDE_GROUP, "name": "Autre groupe"}},
                {"type": "member of band", "direction": "forward", "begin": "1990", "ended": False,
                 "artist": {"id": SIDE_GROUP, "name": "Autre groupe"}}]
            name = "ABBA" if current == GROUP else "Autre groupe" if current == SIDE_GROUP else "Musicien test"
            return {"id": current, "name": name,
                    "relations": [relation, *others, {"type": "producer", "recording": {
                        "id": RECORDING, "title": "Dancing Queen", "artist-credit": ARTIST_CREDIT}}]}
        if path == "release":
            return {"releases": [copy.deepcopy(EDITION)], "release-count": 2}
        if path == "release-group":
            return {"release-groups": [{"id": WORK, "title": "Arrival", "artist-credit": ARTIST_CREDIT,
                                         "first-release-date": "1976"}], "release-group-count": 1}
        raise AssertionError("Requête MusicBrainz inattendue : " + url)
