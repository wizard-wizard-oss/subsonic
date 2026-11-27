"""Correspondances certaines entre pistes locales et édition choisie, sans dépendance réseau ou disque."""
from collections import Counter

from ...shared.text import normalize

DURATION_TOLERANCE = 3


def rank_candidates(candidates, artist, album, year=None):
    """Les correspondances exactes et la même année passent devant ; l'utilisateur choisit l'édition."""
    artist_key, album_key = normalize(artist), normalize(album)
    expected_year = str(year or "")[:4]

    def relevance(candidate):
        same_artist = normalize(candidate.artist) == artist_key
        same_album = normalize(candidate.title) == album_key
        same_year = bool(expected_year) and str(candidate.date or "")[:4] == expected_year
        return same_artist and same_album, same_album, same_artist, same_year

    return tuple(sorted(candidates, key=relevance, reverse=True))


def _number(value):
    value = str(value or "")
    return int(value) if value.isascii() and value.isdigit() and int(value) > 0 else None


def _duration(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if value > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _row(tags, duration):
    return (normalize(tags.title), _number(tags.track), _number(tags.disc), _duration(duration))


def propose_mapping(local_tracks, source_tracks):
    """Indices de source alignés sur les pistes locales ; toute ambiguïté reste une sélection manuelle."""
    local = tuple(_row(track.tags, track.duration) for track in local_tracks)
    source = tuple(_row(track, track.duration) for track in source_tracks)
    local_titles = Counter(row[0] for row in local if row[0])
    source_titles = Counter(row[0] for row in source if row[0])
    candidates = []
    for title, track, disc, duration in local:
        matches = set()
        for index, (other_title, other_track, other_disc, other_duration) in enumerate(source):
            same_title = bool(title) and title == other_title
            comparable = duration is not None and other_duration is not None
            close = comparable and abs(duration - other_duration) <= DURATION_TOLERANCE
            same_numbers = track is not None and disc is not None and (track, disc) == (other_track, other_disc)
            unique_title = same_title and local_titles[title] == source_titles[title] == 1
            if (same_numbers and (same_title or close)) or (unique_title and (not comparable or close)):
                matches.add(index)
        candidates.append(matches)
    # Une source réclamée par une autre piste reste ambiguë, même si cette autre piste a plusieurs candidates.
    claims = Counter(index for matches in candidates for index in matches)
    return tuple(next(iter(matches)) if len(matches) == 1 and claims[next(iter(matches))] == 1 else None
                 for matches in candidates)
