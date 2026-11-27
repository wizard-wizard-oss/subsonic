"""MusicBrainz : une seule classe pour toutes les recherches, des entités pour les appelants."""
from .client import MusicBrainz
from .parsing import mbid

__all__ = ["MusicBrainz", "mbid"]
