"""Radios du menu : (nom, adresse du flux). Si une radio ne démarre plus, son adresse a probablement changé.
Le menu en affiche 9 (grille 3 x 3)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Station:
    name: str
    url: str


STATIONS = (
    Station("FIP", "https://icecast.radiofrance.fr/fip-hifi.aac"),
    Station("France Inter", "https://icecast.radiofrance.fr/franceinter-midfi.mp3"),
    Station("France Musique", "https://icecast.radiofrance.fr/francemusique-midfi.mp3"),
    Station("France Culture", "https://icecast.radiofrance.fr/franceculture-midfi.mp3"),
    Station("TSF Jazz", "https://tsfjazz.ice.infomaniak.ch/tsfjazz-high.mp3"),
    Station("Radio Paradise", "https://stream.radioparadise.com/mp3-192"),
    Station("SomaFM Groove Salad", "https://ice1.somafm.com/groovesalad-128-mp3"),
    Station("KEXP (Seattle)", "https://kexp.streamguys1.com/kexp160.aac"),
    Station("Radio Paradise FLAC", "https://stream.radioparadise.com/flac"),
)
