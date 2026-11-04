"""Lecture d'une playlist venue d'ailleurs : lien Deezer (API publique, sans clé), fichier CSV (Spotify par Exportify,
TuneMyMusic, Soundiiz…), export XML d'Apple Music (Fichier → Bibliothèque → Exporter la playlist), M3U ou simple
texte « Artiste - Titre ». Fonctions pures, sauf DeezerReader. Erreurs : ImportFailed avec une clé de texte."""
import csv
import io
import plistlib
import re
import urllib.parse
import urllib.request

from ..server.podcasts.directories import DirectoryError
from .entities import ImportedTrack

MAX_TRACKS = 1000
DEEZER_API = "https://api.deezer.com/playlist/"
DEEZER_LINK = re.compile(r"^https?://(?:www\.)?deezer\.com/(?:[a-z]{2}/)?playlist/(\d{1,20})(?:[/?#].*)?$")
# Lien court donné par « Partager » dans l'application : il renvoie vers la vraie adresse de la playlist.
DEEZER_SHORT = re.compile(r"^https://(?:link\.deezer\.com/s/|deezer\.page\.link/)[\w-]{1,64}$")

# Colonnes reconnues dans un CSV (en minuscules) : Exportify d'abord, puis les autres outils d'export courants.
CSV_COLUMNS = {
    "title": ("track name", "title", "track", "titre", "name", "song", "song name"),
    "artist": ("artist name(s)", "artist name", "artist", "artists", "artiste", "artist(s)"),
    "album": ("album name", "album", "album title"),
    "duration_ms": ("duration (ms)", "duration_ms", "track duration (ms)"),
    "duration": ("duration", "durée", "length"),
}


class ImportFailed(ValueError):
    """Playlist illisible (clé de texte i18n)."""


class NeedsChoice(Exception):
    """Le fichier contient plusieurs playlists : playlists = [{index, name, count}] à proposer."""

    def __init__(self, playlists):
        super().__init__("import.choose")
        self.playlists = playlists


def _tracks(rows):
    """ImportedTrack valides, sans les lignes vides, au plus MAX_TRACKS."""
    tracks = []
    for title, artist, album, duration in rows:
        title = " ".join(str(title or "").split())
        if title:
            tracks.append(ImportedTrack(title[:300], " ".join(str(artist or "").split())[:300],
                                        " ".join(str(album or "").split())[:300], max(0, int(duration or 0))))
        if len(tracks) >= MAX_TRACKS:
            break
    if not tracks:
        raise ImportFailed("import.empty")
    return tracks


def seconds(text):
    """« 3:25 », « 205 », « 1:02:03 » -> secondes ; 0 si illisible."""
    parts = str(text or "").strip().split(":")
    if not all(p.isdigit() for p in parts) or len(parts) > 3:
        return 0
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total


# ---------- fichiers ----------
def read_file(name, content, playlist=None):
    """(nom proposé, titres) d'un fichier envoyé par la page ; le format se reconnaît au contenu. playlist : rang de
    la playlist choisie quand le fichier en contient plusieurs (sinon NeedsChoice)."""
    base = re.sub(r"\.(csv|xml|m3u8?|txt)$", "", (name or "").strip(), flags=re.I)[:100] or "Playlist importée"
    text = (content or "").lstrip("﻿")
    head = text[:2000].lower()
    if "<plist" in head:
        return read_apple(text, base, playlist)
    if head.startswith("#extm3u") or "#extinf" in head:
        return base, read_m3u(text)
    first = text.split("\n", 1)[0].lower()
    if any(column in first for column in CSV_COLUMNS["title"]) and ("," in first or ";" in first or "\t" in first):
        return base, read_csv(text)
    return base, read_lines(text)


def _column(header, kind):
    names = [h.strip().lower() for h in header]
    for wanted in CSV_COLUMNS[kind]:
        if wanted in names:
            return names.index(wanted)
    return None


def read_csv(text):
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        raise ImportFailed("import.empty")
    header, rows = rows[0], rows[1:]
    columns = {kind: _column(header, kind) for kind in CSV_COLUMNS}
    if columns["title"] is None:
        raise ImportFailed("import.unknown_format")

    def cell(row, kind):
        index = columns[kind]
        return row[index] if index is not None and index < len(row) else ""

    def duration(row):
        if cell(row, "duration_ms").strip().isdigit():
            return int(cell(row, "duration_ms")) // 1000
        return seconds(cell(row, "duration"))

    # Exportify sépare plusieurs artistes par des virgules : le premier suffit pour chercher.
    return _tracks((cell(r, "title"), cell(r, "artist").split(",")[0], cell(r, "album"), duration(r)) for r in rows)


def apple_playlists(data):
    """Playlists d'un export Apple Music qui ont des titres : les siennes d'abord, puis celles d'Apple (« Musique »,
    « Téléchargé »…) ; jamais la bibliothèque entière (« Master ») ni les dossiers."""
    found = [p for p in data.get("Playlists") or [] if isinstance(p, dict) and p.get("Playlist Items")
             and not p.get("Master") and not p.get("Folder")]
    return sorted(found, key=lambda p: bool(p.get("Distinguished Kind")))


def read_apple(text, fallback_name, choice=None):
    """Export XML d'Apple Music (ou iTunes). Une seule playlist : lue directement. Plusieurs (export de toute la
    bibliothèque) : choice est son rang dans apple_playlists ; sans choix, NeedsChoice avec la liste à proposer."""
    try:
        data = plistlib.loads(text.encode("utf-8"))
    except Exception:                                  # plistlib lève des erreurs variées sur un fichier abîmé
        raise ImportFailed("import.unknown_format")
    library = data.get("Tracks") if isinstance(data, dict) else None
    playlists = apple_playlists(data) if isinstance(library, dict) else []
    if not playlists:
        raise ImportFailed("import.empty")
    if len(playlists) > 1 and choice is None:
        raise NeedsChoice([{"index": i, "name": str(p.get("Name") or "?")[:100], "count": len(p["Playlist Items"])}
                           for i, p in enumerate(playlists)])
    if choice is not None and not (isinstance(choice, int) and 0 <= choice < len(playlists)):
        raise ImportFailed("request.invalid")
    chosen = playlists[choice or 0]
    rows = []
    for item in chosen["Playlist Items"]:
        song = library.get(str(item.get("Track ID"))) or {}
        rows.append((song.get("Name"), song.get("Artist") or song.get("Album Artist"), song.get("Album"),
                     int(song.get("Total Time") or 0) // 1000))
    return (str(chosen.get("Name") or fallback_name)[:100], _tracks(rows))


def split_artist_title(line):
    """« Artiste - Titre » -> (artiste, titre) ; sans tiret, tout est le titre."""
    if " - " in line:
        artist, title = line.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", line.strip()


def read_m3u(text):
    rows = []
    for line in text.splitlines():
        match = re.match(r"#EXTINF:\s*(-?\d+)[^,]*,(.*)$", line.strip(), re.I)
        if match:
            artist, title = split_artist_title(match.group(2))
            rows.append((title, artist, "", max(0, int(match.group(1)))))
    return _tracks(rows)


def read_lines(text):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            artist, title = split_artist_title(line)
            rows.append((title, artist, "", 0))
    return _tracks(rows)


# ---------- Deezer ----------
def deezer_playlist_id(link):
    match = DEEZER_LINK.match((link or "").strip())
    if not match:
        raise ImportFailed("import.bad_link")
    return match.group(1)


def follow_short_link(link, timeout=10):
    """Adresse finale d'un lien court Deezer (on ne suit que les liens courts de Deezer, rien d'autre)."""
    request = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0 (pimedia)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.geturl()
    except OSError:
        raise ImportFailed("import.unreachable")


class DeezerReader:
    """Playlist publique de Deezer : nom et titres, par pages de 100."""

    def __init__(self, http, follow=follow_short_link):
        """follow(lien court) -> adresse finale ; remplaçable dans les tests."""
        self.http = http
        self.follow = follow

    def _get(self, url):
        try:
            data = self.http.get(url)
        except DirectoryError:
            raise ImportFailed("import.unreachable")
        if data.get("error"):                         # Deezer répond 200 avec une erreur : privée ou inexistante
            raise ImportFailed("import.not_found")
        return data

    def read(self, link):
        link = (link or "").strip()
        if DEEZER_SHORT.match(link):
            link = self.follow(link)
        playlist_id = deezer_playlist_id(link)
        name = str(self._get(DEEZER_API + playlist_id).get("title") or "Deezer")[:100]
        rows, index = [], 0
        while len(rows) < MAX_TRACKS:
            page = self._get(DEEZER_API + playlist_id + "/tracks?" + urllib.parse.urlencode([("index", index), ("limit", 100)]))
            items = page.get("data") or []
            rows += [(t.get("title"), (t.get("artist") or {}).get("name"), (t.get("album") or {}).get("title"),
                      int(t.get("duration") or 0)) for t in items]
            index += len(items)
            if not items or not page.get("next"):
                break
        return name, _tracks(rows)
