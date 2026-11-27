"""Nomenclature des dossiers musicaux et clés communes de comparaison de leurs noms."""
import posixpath
import re
import unicodedata

from anyascii import anyascii

from ...shared.text import normalize

DISC = re.compile(r"(cd|dis[ck]|disque)\s*\d+", re.IGNORECASE)
_WORD_INITIAL = re.compile(r"(^|[\s-])([^\w\s-]*)([^\W\d_])")


def _normalize_folder_name(name):
    """Initiales majuscules, sans modifier la ponctuation ni la casse restante."""
    return _WORD_INITIAL.sub(lambda match: match[1] + match[2] + match[3].upper(), name)


class LibraryNaming:
    """Règles de nommage des nouveaux dossiers ; la comparaison ne modifie aucun nom."""

    @staticmethod
    def normalize_artist(name):
        return _normalize_folder_name(name)

    @staticmethod
    def normalize_album(name):
        return _normalize_folder_name(name)

    @staticmethod
    def comparison_key(name, *, latin_aliases=True):
        """Clé native, complétée si demandé par les équivalents ASCII des seules lettres latines."""
        key = normalize(name)
        if not latin_aliases:
            return key
        letters = []
        for character in key:
            replacement = (anyascii(character) if character.isalpha()
                           and "LATIN" in unicodedata.name(character, "") else character)
            letters.append(replacement if any(letter.isalnum() for letter in replacement) else character)
        return normalize("".join(letters))


def is_disc(name):
    """Sous-dossier d'un album en plusieurs disques : « CD1 », « CD 2 », « Disc 1 », « Disque 2 »."""
    return bool(DISC.fullmatch(name.strip()))


def album_folder(paths):
    """Dossier d'un album (« Artiste/Album ») d'après les chemins Subsonic de ses titres ou de ses dossiers de disques :
    le parent du premier chemin, sans le dossier de disque (« CD1 »). Vide si aucun chemin n'en donne un."""
    for path in paths:
        folder = posixpath.dirname(str(path or "").replace("\\", "/").strip("/"))
        if is_disc(posixpath.basename(folder)):
            folder = posixpath.dirname(folder)
        if folder:
            return folder
    return ""
