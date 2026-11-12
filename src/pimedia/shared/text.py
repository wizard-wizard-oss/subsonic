"""Comparaison des noms musicaux, sans modifier les textes affichés ni les noms de fichiers."""
import unicodedata

LIGATURES = str.maketrans({"æ": "ae", "œ": "oe"})


def normalize(value):
    """Clé commune : casse, accents, ligatures, espaces et ponctuation sont indifférents.

    Les lettres de tous les alphabets et les chiffres sont conservés. Un nom composé seulement
    de signes reste distinct (« !!! » n'est pas « ?! »).
    """
    text = str(value if value is not None else "").casefold().translate(LIGATURES)
    plain = "".join(c for c in unicodedata.normalize("NFKD", text)
                    if not unicodedata.combining(c)).strip()
    return "".join(c for c in plain if c.isalnum()) or plain
