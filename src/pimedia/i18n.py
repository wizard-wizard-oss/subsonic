"""Textes affichés : i18n/<langue>.yaml, organisés par clés anglaises (« player.next: Titre suivant »).

t("podcasts.unknown_theme") renvoie le texte ; une clé absente renvoie la clé elle-même (repérable à l'écran)."""
import os

try:
    import yaml
except ImportError:            # python3-yaml absent : les clés s'affichent telles quelles, rien ne plante
    yaml = None

DEFAULT_LANGUAGE = "fr"


def flatten(tree, prefix=""):
    """{"player": {"next": "Titre suivant"}} -> {"player.next": "Titre suivant"}"""
    flat = {}
    for key, value in (tree or {}).items():
        name = prefix + str(key)
        if isinstance(value, dict):
            flat.update(flatten(value, name + "."))
        elif isinstance(value, list):              # ex. noms des jours
            flat[name] = [str(item) for item in value]
        else:
            flat[name] = str(value)
    return flat


class Texts:
    def __init__(self, directory, language=DEFAULT_LANGUAGE):
        self.directory = directory
        self.language = language or DEFAULT_LANGUAGE
        self.strings = self._load()

    def _load(self):
        path = os.path.join(self.directory, self.language + ".yaml")
        if yaml is None or not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return flatten(yaml.safe_load(f))

    def t(self, key, **params):
        text = self.strings.get(key, key)
        return text.format(**params) if params else text

    def words(self, key):
        """Liste de textes (jours, mois…) ; liste vide si la clé manque."""
        value = self.strings.get(key)
        return value if isinstance(value, list) else []

    def section(self, prefix):
        """Les textes d'une partie (« web. » pour la page), clés sans le préfixe."""
        return {k[len(prefix):]: v for k, v in self.strings.items() if k.startswith(prefix)}
