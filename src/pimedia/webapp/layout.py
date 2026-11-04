"""Nomenclature de la bibliothèque et rangement d'un album à sa place : <racine>/Artiste/Album/titre (ou
Artiste/Album/CD1/titre pour un album en plusieurs disques), l'artiste et l'album commençant par une majuscule.
Un seul dossier par artiste : un artiste déjà présent est retrouvé sans tenir compte des majuscules, des accents, des
espaces ni de la ponctuation (« Dalek » rejoint « Dälek », « A.A.Williams » rejoint « A.A. Williams »), et son nom de
dossier est gardé. Rien n'est jamais écrasé : un album déjà présent (même nom, aux mêmes détails près) n'est pas rangé."""
import os
import re
import unicodedata

EXTENSIONS = ("mp3", "flac", "m4a", "aac", "ogg", "oga", "opus", "wav", "aiff", "aif")
DISC = re.compile(r"(cd|dis[ck]|disque)\s*\d+", re.IGNORECASE)


def extension_of(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_disc(name):
    """Sous-dossier d'un album en plusieurs disques : « CD1 », « CD 2 », « Disc 1 », « Disque 2 »."""
    return bool(DISC.fullmatch(name.strip()))


def capitalised(name):
    """Commence par une majuscule (ou un chiffre, un signe : « 38 Spesh », « ...Et Après »)."""
    return bool(name) and (not name[0].isalpha() or name[0].isupper())


def normalised(name):
    """Pour comparer deux noms : sans majuscules, accents, espaces ni ponctuation (« A.A.Williams » = « A.A. Williams »,
    « AC/DC » = « Ac-Dc ») ; un nom fait seulement de signes (« !!! ») les garde."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)).casefold().strip()
    return "".join(c for c in plain if c.isalnum()) or plain


def tracks_fit(album):
    """Les titres de l'album sont dedans, ou dans des dossiers de disques ; aucun ailleurs, et au moins un."""
    depths = [os.path.relpath(os.path.join(root, name), album).split(os.sep)
              for root, _, names in os.walk(album) for name in names if extension_of(name) in EXTENSIONS]
    return bool(depths) and all(len(parts) == 1 or (len(parts) == 2 and is_disc(parts[0])) for parts in depths)


def find_albums(root):
    """Dossiers d'albums sous root : ceux qui contiennent des titres (le dossier au-dessus pour un dossier de disque)."""
    albums = set()
    for folder, _, names in os.walk(root):
        if any(extension_of(name) in EXTENSIONS for name in names):
            albums.add(os.path.dirname(folder) if is_disc(os.path.basename(folder)) else folder)
    return sorted(albums)


class MusicTree:
    """La racine de la musique, où les albums prennent leur place (Incoming est dedans, mais n'est pas un artiste)."""

    def __init__(self, music_dir, incoming):
        self.music_dir = music_dir
        self.incoming = incoming

    def place(self, folder, artist, album):
        """Déplace folder en <racine>/Artiste/Album ; renvoie « Artiste/Album », ou None s'il ne peut pas y aller
        (nomenclature non respectée, album déjà présent)."""
        if not (capitalised(artist) and capitalised(album) and tracks_fit(folder)):
            return None
        if normalised(artist) == normalised(os.path.basename(self.incoming)):
            return None                                         # un artiste nommé comme Incoming : à la main
        artist_dir = os.path.join(self.music_dir, self._same(self.music_dir, artist) or artist)
        if os.path.isdir(artist_dir) and self._same(artist_dir, album):
            return None
        if not os.path.isdir(artist_dir):
            os.mkdir(artist_dir)
            os.chmod(artist_dir, 0o775)
        os.replace(folder, os.path.join(artist_dir, album))
        return os.path.basename(artist_dir) + "/" + album

    def is_artist(self, name):
        """Un dossier d'artiste de ce nom existe déjà (majuscules et accents mis à part)."""
        return self._same(self.music_dir, name) is not None

    def _same(self, parent, name):
        """Dossier de parent qui porte ce nom, majuscules et accents mis à part (Incoming exclu)."""
        wanted = normalised(name)
        return next((entry for entry in sorted(os.listdir(parent))
                     if normalised(entry) == wanted and not entry.startswith(".")
                     and os.path.join(parent, entry) != self.incoming), None)
