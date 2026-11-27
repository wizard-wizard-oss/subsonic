"""Lecture des réponses MusicBrainz : fonctions pures, du JSON vers les entités."""
import re
from datetime import date
from uuid import UUID

from .entities import Edition, MusicLink, MusicWork, Track, WeeklyRelease

ROLES = {"producer": "producer", "executive producer": "producer", "co-producer": "producer",
         "instrument": "musician", "vocal": "vocals", "performer": "musician", "guest performer": "musician",
         "composer": "composer", "writer": "composer", "lyricist": "lyricist", "conductor": "conductor",
         "mix": "mix", "recording": "engineer", "engineer": "engineer", "mastering": "mastering"}
CONNECTIONS = {"member of band": ("group", "member"), "collaboration": ("project", "collaborator"),
               "subgroup": ("parent_group", "subgroup"),
               "instrumental supporting musician": ("supporting_for", "supporting_member"),
               "vocal supporting musician": ("supporting_for", "supporting_member")}


def mbid(value):
    try:
        parsed = str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("MusicBrainz ID") from None
    if str(value).lower() != parsed:
        raise ValueError("MusicBrainz ID")
    return parsed


def artist_name(raw):
    return "".join((c.get("name") or c.get("artist", {}).get("name", "")) + c.get("joinphrase", "")
                   for c in raw.get("artist-credit") or [] if isinstance(c, dict))


def artist_names(raw):
    """Noms canoniques et crédit complet, qui peut employer des noms d'usage."""
    credits = raw.get("artist-credit") or []
    names = [c.get("artist", {}).get("name", c.get("name", "")) for c in credits if isinstance(c, dict)]
    credit = artist_name(raw) if credits else ""
    return [*names, credit] if credit else names


def search_phrase(text):
    """Expression littérale MusicBrainz, sans guillemet ni échappement fourni par le nom."""
    return '"' + re.sub(r'["\\]', " ", str(text))[:300] + '"'


def search_terms(value):
    # Les mots seuls évitent les opérateurs Lucene fournis par l'entrée ; une faute reste une suggestion possible.
    words = re.findall(r"[^\W_]+", str(value), re.UNICODE)
    return " ".join(word + "~1" if len(word) > 3 else '"' + word + '"' for word in words) or search_phrase(value)


def number(value, zero=False):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
        return parsed if parsed >= (0 if zero else 1) else None
    except (TypeError, ValueError, OverflowError):
        return None


def formats(media):
    return ", ".join(dict.fromkeys(str(m["format"]) for m in media if m.get("format")))[:300]


def genres(raw):
    ranked = []
    for genre in raw.get("genres") or []:
        if not isinstance(genre, dict) or not isinstance(genre.get("name"), str) or not genre["name"].strip():
            continue
        count = number(genre.get("count"), zero=True)
        if count is not None:
            ranked.append((count, genre["name"].strip()[:100]))
    ranked.sort(key=lambda item: -item[0])
    return tuple(dict.fromkeys(name for _, name in ranked))


def edition(raw):
    media = raw.get("media") or []
    count = number(raw.get("track-count")) or sum(number(m.get("track-count")) or 0 for m in media)
    labels = tuple(i.get("label", {}).get("name", "") for i in raw.get("label-info") or [] if i.get("label"))
    return Edition(mbid(raw["id"]), str(raw["title"])[:1000], artist_name(raw)[:1000],
                   str(raw.get("date") or "")[:20], str(raw.get("country") or "")[:100], formats(media), count, labels)


def tracks(raw, album_artist):
    found = []
    for medium_index, medium in enumerate(raw.get("media") or [], 1):
        disc = number(medium.get("position")) or medium_index
        for item in medium.get("tracks") or []:
            recording = item.get("recording") or {}
            length = item.get("length") if item.get("length") is not None else recording.get("length")
            length = number(length, zero=True)
            found.append(Track(str(item.get("number") or item.get("position") or "")[:30], number(item.get("position")),
                               disc, str(item.get("title") or recording.get("title") or "")[:1000],
                               (artist_name(item) or artist_name(recording) or album_artist)[:1000],
                               round(length / 1000) if length is not None else None))
    return tuple(found)


def weekly_group(row):
    """Groupe de sortie daté du jour exact, sinon None (date partielle ou invalide)."""
    value = row.get("first-release-date")
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        released_on = date.fromisoformat(value)
    except ValueError:
        return None
    return WeeklyRelease(mbid(row["id"]), row["title"], artist_name(row), released_on, row.get("primary-type", ""))


def connections(raw):
    """Relations musicales explicites uniquement ; conserver les périodes, dédupliquer les doublons exacts."""
    found = {}
    for relation in raw.get("relations", []):
        artist = relation.get("artist") or {}
        if not artist.get("id") or relation.get("type") not in CONNECTIONS:
            continue
        forward, backward = CONNECTIONS[relation["type"]]
        role = backward if relation.get("direction") == "backward" else forward
        link = MusicLink(mbid(artist["id"]), artist["name"], "artist", role,
                         ", ".join(sorted(relation.get("attributes") or [])),
                         relation.get("begin") or "", relation.get("end") or "", bool(relation.get("ended")))
        found[(link.id, link.role, link.detail, link.begin, link.end, link.ended)] = link
    return sorted(found.values(), key=lambda link: (link.name.casefold(), link.role, link.begin, link.end))


def credits(raw, people):
    for relation in raw.get("relations", []):
        artist = relation.get("artist") or {}
        role = ROLES.get(relation.get("type"))
        if artist.get("id") and role:
            detail = ", ".join(relation.get("attributes") or [])
            people[(artist["id"], role, detail)] = MusicLink(mbid(artist["id"]), artist["name"], "artist", role, detail)


def release_people(raw):
    """Artistes crédités sur l'édition, ses enregistrements et leurs relations."""
    people = {}
    for credit in raw.get("artist-credit", []):
        if isinstance(credit, dict) and credit.get("artist", {}).get("id"):
            person = credit["artist"]
            people[(person["id"], "artist", "")] = MusicLink(mbid(person["id"]), person["name"])
    credits(raw, people)
    for medium in raw.get("media", []):
        for track in medium.get("tracks", []):
            credits(track.get("recording") or {}, people)
    return sorted(people.values(), key=lambda p: (p.role, p.name.casefold(), p.detail))


def release_labels(raw):
    return list({i["label"]["id"]: MusicLink(mbid(i["label"]["id"]), i["label"]["name"], "label", "label",
                                             i.get("catalog-number", ""))
                 for i in raw.get("label-info", []) if i.get("label", {}).get("id")}.values())


def credited_works(raw):
    """Sorties et enregistrements où l'artiste est crédité (production, instrument…), hors catalogue principal."""
    works = {}
    for relation in raw.get("relations", []):
        for target in ("recording", "release"):
            item = relation.get(target) or {}
            if item.get("id") and relation.get("type") in ROLES:
                key = (item["id"], ROLES[relation["type"]])
                works[key] = MusicWork(mbid(item["id"]), item["title"], artist_name(item), target,
                                       item.get("date", ""), key[1])
    return sorted(works.values(), key=lambda w: (w.date, w.title, w.role))
