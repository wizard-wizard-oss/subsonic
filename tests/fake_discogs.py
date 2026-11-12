"""Catalogue public simulé : homonymes, master réédité sur deux pages, pistes locales et manquantes."""
import copy
import urllib.parse


def edition(identity, master, title, artist, year, **extras):
    return dict(id=identity, master_id=master, title=title, artist=artist, year=year, format="CD, Album", **extras)


EDITIONS = [edition(101, 11, "Arrival", "ABBA", 1976), edition(103, 12, "Discovery", "Daft Punk", 2001),
            edition(104, 0, "Rare", "Artiste discret", 1982), edition(102, 11, "Arrival", "ABBA", 2020)]


class FakeDiscogs:
    def __init__(self):
        self.calls = []
        self.fail = None
        self.editions = copy.deepcopy(EDITIONS)
        self.page_size = 2

    def get(self, url, headers):
        self.calls.append((url, headers))
        if self.fail:
            raise self.fail
        parsed = urllib.parse.urlsplit(url)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path == "/database/search":
            kind = query["type"][0]
            if kind == "release":
                return {"results": [dict(e, title=e["artist"] + " - " + e["title"], type="release") for e in self.editions]}
            name = "Polar" if kind == "label" else "ABBA"
            return {"results": [{"id": i, "title": name, "type": kind} for i in (7, 8)], "pagination": {"pages": 1}}
        if path.endswith("/releases"):
            page = int(query["page"][0])
            rows = self.editions[(page - 1) * self.page_size:page * self.page_size]
            return {"releases": rows, "pagination": {"pages": (len(self.editions) + self.page_size - 1) // self.page_size,
                                                       "items": len(self.editions)}}
        if path.startswith(("/labels/", "/artists/")):
            identity = int(path.split("/")[-1])
            raw = {"id": identity, "name": "Polar" if path.startswith("/labels/") else "Musicien test" if identity == 9 else "ABBA",
                    "contact_info": "excluded", "profile": "excluded",
                    "members": [{"id": 9, "name": "Musicien test"}] if identity == 7 else [],
                    "groups": [{"id": 7, "name": "ABBA"}] if identity == 9 else []}
            if path.startswith("/labels/") and identity == 8:
                raw.update(name="Polar Records", profile="Parent of the label [l=Polar]. Use only as a company, not as a label.",
                           sublabels=[{"id": 7, "name": "Polar"}, {"id": 9, "name": "Polar Publishing"}])
            if path.startswith("/artists/") and identity == 7:
                raw.update(images=[{"type": "primary", "uri": "https://i.discogs.com/artist-test.jpg"}])
            return raw
        if path.startswith("/releases/"):
            return self.release(int(path.split("/")[-1]))
        raise AssertionError(path)

    def release(self, identity):
        raw = next(e for e in self.editions if e["id"] == identity)
        titles = {101: ["Dancing Queen", "Knowing Me"], 103: ["One More Time"]}.get(identity, [raw["title"]])
        return dict(id=identity, title=raw["title"], artists=[{"id": 7, "name": raw["artist"]}], labels=[{"id": 7, "name": "Polar"}],
                    extraartists=[{"id": 9, "name": "Musicien test", "role": "Drums"}],
                    community={"rating": {"average": 5 if identity == 102 else 4, "count": 0 if identity == 104 else 20}},
                    tracklist=[{"type_": "heading", "title": "Face A"}] +
                              [{"type_": "track", "title": title, "duration": "5:20" if identity == 103 else "3:50"} for title in titles],
                    videos=[{"uri": "https://www.youtube.com/watch?v=" + identity, "title": "Daft Punk - One More Time",
                             "duration": 320} for identity in ("abc123def45", "otherone123")] if identity == 103 else [],
                    images=[{"uri": "excluded"}], notes="excluded")


class FakeLastFm:
    def __init__(self):
        self.calls = []
        self.fail = None

    def get(self, url, headers):
        self.calls.append((url, headers))
        if self.fail:
            raise self.fail
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        title = query["album"][0]
        return {"album": {"name": title, "artist": query["artist"][0],
                          "listeners": "500" if title == "Discovery" else "100",
                          "playcount": "1000" if title == "Discovery" else "2000", "wiki": {"content": "excluded"}}}
