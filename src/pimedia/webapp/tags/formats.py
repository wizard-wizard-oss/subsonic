"""Formats audio : lecture et écriture des tags dans chaque conteneur (ID3, MP4, Vorbis), sans accès aux fichiers
voisins ni journal. Le numéro total de pistes et la date complète déjà présents sont conservés."""
import mutagen
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TCON, TDRC, TPE1, TPE2, TIT2, TRCK, TPOS, TYER
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from .entities import TAG_FIELDS, AudioTagError, TagError, tag_value

SUPPORTED_FORMATS = ("mp3", "flac", "m4a", "ogg", "opus", "wav", "aiff")
FIELDS = TAG_FIELDS
_ID3_FIELDS = {"title": TIT2, "artist": TPE1, "albumArtist": TPE2, "album": TALB,
               "genre": TCON, "track": TRCK, "disc": TPOS}
_COMMENT_FIELDS = {"title": "title", "artist": "artist", "albumArtist": "albumartist", "album": "album",
                   "year": "date", "genre": "genre", "track": "tracknumber", "disc": "discnumber"}
_MP4_FIELDS = {"title": "\xa9nam", "artist": "\xa9ART", "albumArtist": "aART", "album": "\xa9alb",
               "year": "\xa9day", "genre": "\xa9gen", "track": "trkn", "disc": "disk"}


def _text(values):
    return "; ".join(str(value) for value in (values or []) if str(value))


def _number(value):
    return str(value or "").split("/", 1)[0].strip()


def _date(value):
    value = str(value or "")
    return value[:4] if len(value) >= 4 and value[:4].isdigit() else value


def _with_total(value, previous):
    """Le champ numéro n'efface pas le nombre total de pistes/disques déjà présent."""
    parts = str(previous or "").split("/", 1)
    return value + "/" + parts[1] if value and len(parts) == 2 and parts[1].isdigit() else value


def _with_date(value, previous):
    previous = str(previous or "")
    return value + previous[4:] if value and len(previous) > 4 and previous[:4].isdigit() else value


def validate_changes(changes):
    if not isinstance(changes, dict) or not changes or any(key not in FIELDS for key in changes):
        raise AudioTagError("tags.invalid_changes")
    try:
        return {key: tag_value(key, value) for key, value in changes.items()}
    except TagError as error:
        raise AudioTagError(str(error)) from None


def _discard(tags, name):
    if name in tags:
        del tags[name]


def _load(path):
    audio = mutagen.File(path)
    if isinstance(audio, MP3):
        try:
            tags = ID3(path, translate=False)
        except ID3NoHeaderError:
            tags = ID3()
        return "mp3", tags
    for audio_type, kind in ((FLAC, "flac"), (MP4, "m4a"), (OggVorbis, "ogg"), (OggOpus, "opus"),
                             (WAVE, "wav"), (AIFF, "aiff")):
        if isinstance(audio, audio_type):
            if audio.tags is None:
                audio.add_tags()
            elif isinstance(audio.tags, ID3):
                # Les sous-classes WAVE/AIFF connaissent leur conteneur ; préserver ID3v2.3 à la lecture.
                audio.tags = type(audio.tags)(path, translate=False)
            return kind, audio
    raise AudioTagError("tags.unsupported_format")


def _read(kind, document):
    tags = document if kind == "mp3" else document.tags
    result = dict.fromkeys(FIELDS, "")
    if isinstance(tags, ID3):
        for key, frame in _ID3_FIELDS.items():
            result[key] = _text(value for item in tags.getall(frame.__name__) for value in item.text)
        year = tags.get("TDRC") or tags.get("TYER")
        result["year"] = _date(str(year)) if year else ""
    elif kind == "m4a":
        for key, atom in _MP4_FIELDS.items():
            values = tags.get(atom) or []
            result[key] = str(values[0][0]) if key in ("track", "disc") and values else _text(values)
        result["year"] = _date(result["year"])
    else:
        for key, name in _COMMENT_FIELDS.items():
            result[key] = _text(tags.get(name) or (tags.get("year") if key == "year" else []))
        result["year"] = _date(result["year"])
    result["track"], result["disc"] = _number(result["track"]), _number(result["disc"])
    return result



def _write_id3(tags, changes):
    version = 3 if tags.version[1] == 3 else 4
    for key, value in changes.items():
        if key == "year":
            old = tags.get("TYER" if version == 3 else "TDRC")
            for name in ("TYER", "TDRC"):
                tags.delall(name)
            if value:
                frame = TYER if version == 3 else TDRC
                tags.add(frame(encoding=1 if version == 3 else 3, text=[_with_date(value, str(old or ""))]))
            continue
        frame = _ID3_FIELDS[key]
        old = tags.get(frame.__name__)
        tags.delall(frame.__name__)
        if value:
            text = _with_total(value, str(old or "")) if key in ("track", "disc") else value
            tags.add(frame(encoding=1 if version == 3 else 3, text=[text]))
    return version


def _write_mp4(tags, changes):
    for key, value in changes.items():
        atom = _MP4_FIELDS[key]
        old = tags.get(atom) or []
        if not value:
            _discard(tags, atom)
        elif key in ("track", "disc"):
            tags[atom] = [(int(value), old[0][1] if old else 0)]
        else:
            tags[atom] = [_with_date(value, old[0] if old else "") if key == "year" else value]
        if key == "genre":
            _discard(tags, "gnre")


def _write_comments(tags, changes):
    for key, value in changes.items():
        name = _COMMENT_FIELDS[key]
        old = (tags.get(name) or [""])[0]
        if not value:
            _discard(tags, name)
        else:
            tags[name] = [_with_total(value, old) if key in ("track", "disc") else
                          _with_date(value, old) if key == "year" else value]
        if key == "year":
            _discard(tags, "year")


def _write(path, changes):
    kind, document = _load(path)
    tags = document if kind == "mp3" else document.tags
    if isinstance(tags, ID3):
        version = _write_id3(tags, changes)
        if kind == "mp3":
            tags.save(path, v2_version=version, v1=1)
        else:
            document.save(v2_version=version)
        return
    if kind == "m4a":
        _write_mp4(tags, changes)
    else:
        _write_comments(tags, changes)
    document.save()


def is_supported_id3(kind, document):
    """Un ID3 qu'on sait réécrire (v2.3 ou v2.4), ou un autre conteneur."""
    tags = document if kind == "mp3" else document.tags
    return not isinstance(tags, ID3) or tags.version[1] in (3, 4)


load, read, write = _load, _read, _write
