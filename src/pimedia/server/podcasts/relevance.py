"""Pertinence de la recherche : les annuaires renvoient aussi des résultats « approchants » (un seul des mots).
On ne garde que les podcasts qui contiennent TOUS les mots tapés, titre et auteur d'abord."""
import re
import unicodedata


def normalize(text):
    """Minuscules, sans accents ni ponctuation."""
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return " " + re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip() + " "


def words_of(term):
    return [w for w in normalize(term).split() if w]


def _contains_all(haystack, words):
    return all(" " + w in haystack for w in words)        # début de mot : « hist » trouve « histoire »


def rank(cards, term):
    """Cartes contenant tous les mots, classées : phrase exacte dans le titre, mots dans le titre ou l'auteur,
    puis mots dans la description ou le genre."""
    words = words_of(term)
    if not words:
        return cards
    phrase = " " + " ".join(words)
    scored = []
    for position, card in enumerate(cards):
        title = normalize(card["title"])
        headline = title + normalize(card.get("author"))
        everything = headline + normalize(card.get("desc")) + normalize(card.get("genre"))
        if phrase in title:
            level = 0
        elif _contains_all(headline, words):
            level = 1
        elif _contains_all(everything, words):
            level = 2
        else:
            continue
        scored.append((level, position, card))
    return [card for _, _, card in sorted(scored, key=lambda t: t[:2])]
