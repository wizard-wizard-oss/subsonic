"""Nomenclature de la bibliothèque et rangement d'un album à sa place : <racine>/Artiste/Album/titre (ou
Artiste/Album/CD1/titre pour un album en plusieurs disques). Les mots des nouveaux dossiers d'artistes et d'albums
reçoivent une initiale majuscule, sans modifier les accents ni la casse du reste des mots.
Un seul dossier par artiste : un artiste déjà présent est retrouvé sans tenir compte des majuscules, des accents, des
espaces ni de la ponctuation (« Dalek » rejoint « Dälek », « A.A.Williams » rejoint « A.A. Williams »), et son nom de
dossier est gardé. Rien n'est jamais écrasé : un album déjà présent (même nom, aux mêmes détails près) n'est pas rangé."""
import os

from .naming import LibraryNaming, is_disc

EXTENSIONS = ("mp3", "flac", "m4a", "aac", "ogg", "oga", "opus", "wav", "aiff", "aif")


class AmbiguousFolder(LookupError):
    """Plusieurs dossiers correspondent à la même recherche : aucun n'est choisi."""


def extension_of(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


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


class LibraryFiles:
    """La racine de la musique, où les albums prennent leur place (Incoming est dedans, mais n'est pas un artiste)."""

    def __init__(self, music_dir, incoming, naming=None):
        self.music_dir = music_dir
        self.incoming = incoming
        self.naming = naming if naming is not None else LibraryNaming()

    def place(self, folder, artist, album):
        """Déplace folder en <racine>/Artiste/Album ; renvoie « Artiste/Album », ou None s'il ne peut pas y aller
        (nomenclature non respectée, album déjà présent)."""
        if not (artist and album and tracks_fit(folder)):
            return None
        artist_name = self.naming.normalize_artist(artist)
        incoming_key = self.naming.comparison_key(os.path.basename(self.incoming))
        if incoming_key in {self.naming.comparison_key(artist), self.naming.comparison_key(artist_name)}:
            return None                                         # un artiste nommé comme Incoming : à la main
        album_name = self.naming.normalize_album(album)
        try:
            artist_dir = os.path.join(self.music_dir, self.find_matching_folder(self.music_dir, artist, artist_name)
                                      or artist_name)
            if os.path.isdir(artist_dir) and self.find_matching_folder(artist_dir, album, album_name):
                return None
        except AmbiguousFolder:
            return None
        destination = os.path.join(artist_dir, album_name)
        if os.path.lexists(destination) or (os.path.lexists(artist_dir) and not os.path.isdir(artist_dir)):
            return None
        if not os.path.isdir(artist_dir):
            os.mkdir(artist_dir)
            os.chmod(artist_dir, 0o775)
        os.replace(folder, destination)
        return os.path.basename(artist_dir) + "/" + album_name

    def is_artist(self, name):
        """Un dossier d'artiste de ce nom existe déjà (majuscules et accents mis à part)."""
        try:
            return self.find_matching_folder(self.music_dir, name) is not None
        except AmbiguousFolder:
            return True                                         # un dossier englobant connu reste un garde-fou

    def find_matching_folder(self, parent, *names):
        """Priorité aux noms exacts, puis aux clés natives et latines ; toute ambiguïté fait attendre."""
        with os.scandir(parent) as entries:
            folders = {entry.name for entry in entries if not entry.name.startswith(".")
                       and entry.path != self.incoming and entry.is_dir()}
        for name in names:
            if name in folders:
                return name
        for latin_aliases in (False, True):
            wanted = {self.naming.comparison_key(name, latin_aliases=latin_aliases) for name in names}
            matches = [folder for folder in folders
                       if self.naming.comparison_key(folder, latin_aliases=latin_aliases) in wanted]
            if len(matches) > 1:
                raise AmbiguousFolder(names)
            if matches:
                return matches[0]
        return None
