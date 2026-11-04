"""Format commun d'un titre (Subsonic, Jamendo, YouTube…), tel que la page l'utilise et tel qu'on le stocke."""
import urllib.parse

TRACK_KEYS = ("id", "title", "artist", "album", "albumId", "artistId", "coverArt", "duration", "track", "suffix",
              "bitRate", "bitDepth", "samplingRate", "streamUrl", "youtubeId", "imageUrl", "ext")


PHONE_FILES_PREFIX = "/phone-files/"     # fichiers envoyés depuis un téléphone, servis par le Pi lui-même


def is_allowed_address(value, local_files=False):
    """Adresse web (http/https), ou fichier envoyé par un téléphone (/phone-files/…) pour une adresse de lecture."""
    parts = urllib.parse.urlsplit(value)
    if parts.scheme in ("http", "https") and parts.netloc:
        return True
    return local_files and not parts.scheme and not parts.netloc and parts.path.startswith(PHONE_FILES_PREFIX) \
        and ".." not in parts.path


def clean_track(raw):
    """Ne garde que les champs connus ; refuse un titre sans identifiant ou avec une adresse de lecture étrangère."""
    if not isinstance(raw, dict) or not raw.get("id") or not raw.get("title"):
        raise ValueError("titre invalide")
    track = {k: raw[k] for k in TRACK_KEYS if k in raw and isinstance(raw[k], (str, int, float))}
    for key in ("streamUrl", "imageUrl"):
        value = str(track.get(key) or "")
        if value and not is_allowed_address(value, local_files=(key == "streamUrl")):
            raise ValueError("adresse invalide")
    track["id"], track["title"] = str(track["id"]), str(track["title"])[:300]
    return track
