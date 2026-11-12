"""Sonde réseau facultative, dans l'image web : noms en arguments, configuration du conteneur, base temporaire.

N'affiche que des compteurs de métadonnées publiques. Aucun compte Subsonic ni écriture de playlist.
"""
import argparse
import os
import tempfile

from pimedia.storage.database import Database
from pimedia.webapp.config import WebConfig
from pimedia.webapp.discogs import Discogs
from pimedia.webapp.discogs_catalogs import DiscogsCatalogs
from pimedia.webapp.label_discovery import LabelDiscovery
from pimedia.webapp.lastfm import LastFm
from pimedia.webapp.music_metadata import MusicSourceError
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.exploration import ExplorationRepository


def probe(config, repository, label, artist, album="", full=False):
    discogs = Discogs(repository, config.discogs_api_key)
    lastfm = LastFm(repository, config.lastfm_api_key)
    catalogs = DiscogsCatalogs(discogs)
    identities = discogs.search("label", label).identities
    print("Label identities:", len(identities), flush=True)
    if not identities:
        raise ValueError("No label found")
    identity = identities[0]
    page = catalogs.page("label", identity.id, 1)
    print("First label page:", len(page.albums), "albums;", page.pages, "pages", flush=True)
    release = discogs.release(page.albums[0].editions[0].id)
    print("Release tracks:", len(release.tracks), "; rating votes:", release.votes, flush=True)
    if page.pages == 1:
        discovery = LabelDiscovery(catalogs, discogs, lastfm, None)
        print("Discovery albums:", len(discovery.discover(identity.id)), flush=True)
        ranking = discovery.ranking(identity.id, "discogs", 0)
        while full and ranking.analyzed < ranking.total and ranking.total <= 100:
            ranking = discovery.ranking(identity.id, "discogs", ranking.analyzed)
        print("Discogs ranking:", ranking.analyzed, "analyzed;", len(ranking.scores), "ranked;",
              ranking.excluded, "unconfirmed label associations", flush=True)
    if lastfm.enabled:
        popularity = lastfm.album(page.albums[0].artist, page.albums[0].title)
        print("Last.fm:", popularity.listeners, "listeners;", popularity.plays, "plays", flush=True)
    else:
        print("Last.fm not configured", flush=True)
    identities = discogs.search("artist", artist).identities
    print("Artist identities:", len(identities), flush=True)
    if identities:
        page = catalogs.page("artist", identities[0].id, 1)
        print("Artist discography:", len(page.albums), "albums on first page", flush=True)
    if album:
        editions = discogs.editions(artist, album)
        print("Matching Discogs editions:", len(editions), flush=True)
        if editions:
            release = discogs.release(editions[0].id)
            print("Edition credits:", len(release.credits), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--artist", required=True)
    parser.add_argument("--album", default="")
    parser.add_argument("--full-ranking", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="discovery-probe-") as temporary:
        config = WebConfig.load(temporary, os.environ)
        db = Database(os.path.join(temporary, "metadata.db"), MIGRATIONS)
        try:
            probe(config, ExplorationRepository(db), args.label, args.artist, args.album, args.full_ranking)
        except MusicSourceError as error:
            print("Source:", error.args[0], flush=True)
            raise SystemExit(1) from None
        finally:
            db.close()


if __name__ == "__main__":
    main()
