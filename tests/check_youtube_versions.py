"""Sonde facultative des sources réelles : édition en argument, configuration serveur et base temporaire.

Vérifie les métadonnées et le cache, sans compte Subsonic, lecture audio ni écriture de playlist.
"""
import argparse
import json
import os
import tempfile
from types import SimpleNamespace

from pimedia.storage.database import Database
from pimedia.webapp.config import WebConfig
from pimedia.webapp.discogs import Discogs
from pimedia.webapp.extmusic import KEPT_SECONDS, ExternalMusic, SearchMemory
from pimedia.webapp.label_discovery import LabelDiscovery, playable_tracks
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.exploration import ExplorationRepository
from pimedia.webapp.storage.youtube import ExtSearchRepository, YouTubeVideoRepository
from pimedia.webapp.youtube_versions import MAX_VERSIONS, YouTubeVersions


class CountedHttp:
    def __init__(self, http):
        self.http, self.calls = http, 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return self.http.get(*args, **kwargs)


def probe(config, db, release_id, limit):
    discogs = Discogs(ExplorationRepository(db), config.discogs_api_key)
    edition = discogs.release(release_id)
    videos = YouTubeVideoRepository(db, KEPT_SECONDS)
    memory = SearchMemory(ExtSearchRepository(db, KEPT_SECONDS), ExtSearchRepository(db, None), videos)
    external = ExternalMusic(config, memory, videos)
    external.youtube.http = CountedHttp(external.youtube.http)
    service = YouTubeVersions(external)
    user = SimpleNamespace(username=str(release_id))  # Clé de budget temporaire, aucun compte de bibliothèque.
    print(json.dumps(dict(album=edition.title, links=len(edition.videos)), ensure_ascii=False), flush=True)
    for raw in list(playable_tracks(edition.tracks))[:limit]:
        track = LabelDiscovery._imported_track(raw, edition)
        labels = tuple(label.name for label in edition.labels)
        result = service.find(user, track, edition.videos, labels=labels)
        calls = external.youtube.http.calls
        again = service.find(user, track, edition.videos, labels=labels)
        assert len(result.items) <= MAX_VERSIONS
        assert [v["id"] for v in again.items] == [v["id"] for v in result.items]
        assert external.youtube.http.calls == calls, "La seconde demande doit utiliser le cache"
        print(json.dumps(dict(track=track.title, wantedDuration=track.duration, choices=[
            dict(title=v["title"], duration=v["duration"], source=v["discoverySource"]) for v in result.items],
            cached=True), ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--limit", type=int, choices=range(1, 6), default=4)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="youtube-probe-") as directory:
        db = Database(os.path.join(directory, "metadata.db"), MIGRATIONS)
        try:
            probe(WebConfig.load(directory, os.environ), db, args.release, args.limit)
        finally:
            db.close()


if __name__ == "__main__":
    main()
