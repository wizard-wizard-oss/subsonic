"""Thèmes proposés dans la page Podcasts, avec de quoi les chercher dans chaque annuaire."""


class Theme:
    def __init__(self, key, label, hue, index_category, search_terms):
        self.key = key
        self.label = label
        self.hue = hue                          # teinte de la vignette (0-360)
        self.index_category = index_category    # catégorie Podcast Index (en anglais)
        self.search_terms = search_terms        # recherche iTunes, en français

    def describe(self):
        return {"key": self.key, "label": self.label, "hue": self.hue}


THEMES = (
    Theme("actualite", "Actualité", 8, "News", "actualité informations"),
    Theme("histoire", "Histoire", 35, "History", "histoire"),
    Theme("science", "Science", 190, "Science", "science"),
    Theme("culture", "Culture", 280, "Arts", "culture littérature cinéma"),
    Theme("humour", "Humour", 50, "Comedy", "humour"),
    Theme("societe", "Société", 320, "Society & Culture", "société débat"),
    Theme("crime", "Faits divers", 0, "True Crime", "affaires criminelles faits divers"),
    Theme("musique", "Musique", 140, "Music", "musique"),
    Theme("tech", "Technologie", 210, "Technology", "technologie numérique"),
    Theme("eco", "Économie", 100, "Business", "économie entreprise"),
    Theme("sante", "Santé & bien-être", 160, "Health & Fitness", "santé bien-être"),
    Theme("sport", "Sport", 25, "Sports", "sport"),
    Theme("fiction", "Fiction", 260, "Fiction", "fiction histoires"),
    Theme("enfants", "Enfants", 80, "Kids & Family", "enfants histoires pour enfants"),
)

# Rangées de l'accueil : recherches que l'on peut modifier dans config.json (clé « podcast_home »)
DEFAULT_HOME_QUERIES = ("France Culture", "France Inter", "Radio France", "Arte Radio")


def find_theme(key):
    for theme in THEMES:
        if theme.key == key:
            return theme
    return None
