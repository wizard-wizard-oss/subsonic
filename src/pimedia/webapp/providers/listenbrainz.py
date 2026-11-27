"""La seule classe ListenBrainz du site : sorties récentes et à venir (radar des sorties).

Lecture en direct, sans cache : la synchronisation de nuit garde ce qu'il faut dans les tables du radar."""
from datetime import date
from urllib.parse import urlencode

from ...shared.providers.metadata import ProviderUnavailable, PublicMetadata
from ...shared.providers.musicbrainz.entities import WeeklyRelease
from ...shared.providers.musicbrainz.parsing import mbid

FRESH_RELEASES = "https://api.listenbrainz.org/1/explore/fresh-releases/"
COVER_ART_ARCHIVE = "https://coverartarchive.org"
KINDS = {"album": "Album", "ep": "EP"}          # les singles et compilations sans type ne sont pas gardés


class ListenBrainz(PublicMetadata):
    prefix = "listenbrainz:"
    interval = 1.0
    unavailable_code = "explore.unavailable"

    def fresh_releases(self, today, start, end):
        """Albums et EP sortis entre start et aujourd'hui, ou annoncés d'aujourd'hui à end : deux requêtes.
        Un groupe de sorties vu plusieurs fois (plusieurs éditions) garde sa date la plus ancienne."""
        found = {}
        windows = ({"release_date": today.isoformat(), "days": (today - start).days, "past": "true",
                    "future": "false"},
                   {"release_date": today.isoformat(), "days": (end - today).days, "past": "false",
                    "future": "true"})
        for params in windows:
            for raw in self._releases(params):
                release = _release(raw)
                if release and (release.id not in found or release.released_on < found[release.id].released_on):
                    found[release.id] = release
        return tuple(found.values())

    def _releases(self, params):
        try:
            data = self._attempts(FRESH_RELEASES + "?" + urlencode(params), self.http.get_json)
        except (OSError, ValueError):
            raise ProviderUnavailable(self.unavailable_code) from None
        releases = (data.get("payload") or {}).get("releases") or []
        return [raw for raw in releases if isinstance(raw, dict)]


def _release(raw):
    """Entité commune aux sorties MusicBrainz (mêmes identifiants), ou None si incomplète ou d'un autre type."""
    kind = KINDS.get(str(raw.get("release_group_primary_type") or "").lower())
    try:
        identity, released_on = mbid(raw.get("release_group_mbid")), date.fromisoformat(raw.get("release_date") or "")
    except (ValueError, TypeError):
        return None
    if not kind:
        return None
    artists = []
    for value in raw.get("artist_mbids") or []:
        try:
            artists.append(mbid(value))
        except ValueError:
            continue
    tags = tuple(tag for tag in raw.get("release_tags") or [] if isinstance(tag, str) and tag)
    return WeeklyRelease(identity, str(raw.get("release_name") or "")[:1000],
                         str(raw.get("artist_credit_name") or "")[:1000], released_on, kind, tags,
                         tuple(dict.fromkeys(artists)), _cover(raw))


def _cover(raw):
    """Image exacte de l'édition qui a une pochette chez Cover Art Archive (connue de ListenBrainz), ou ""."""
    try:
        release, image = mbid(raw.get("caa_release_mbid")), int(raw.get("caa_id"))
    except (ValueError, TypeError):
        return ""
    return "%s/release/%s/%d-250.jpg" % (COVER_ART_ARCHIVE, release, image)
