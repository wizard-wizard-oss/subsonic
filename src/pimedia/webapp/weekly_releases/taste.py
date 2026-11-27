"""Ressemblance d'une sortie avec les goûts d'un compte (tags pondérés) : fonctions pures."""
import math


def score(release_tags, profile):
    """Cosinus entre les tags de la sortie (poids 1 chacun) et le profil ; 0 si l'un des deux est vide."""
    tags = set(release_tags)
    if not tags or not profile:
        return 0.0
    dot = sum(profile.get(tag, 0) for tag in tags)
    return dot / (math.sqrt(len(tags)) * math.sqrt(sum(weight * weight for weight in profile.values())))


def rank(cards):
    """Les plus proches des goûts d'abord ; à égalité, par date puis par titre."""
    return sorted(cards, key=lambda card: (-card.score, card.release.released_on, card.release.title.casefold()))
