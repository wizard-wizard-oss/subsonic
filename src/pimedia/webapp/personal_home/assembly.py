"""Assemblage de l’historique et de l’accueil sur les instances existantes du site."""
from ..storage.listening_history import ListeningHistoryRepository
from .catalog import HomeCatalog
from .history import ListeningHistory
from .service import PersonalHome


def build(app, targets):
    history = ListeningHistory(ListeningHistoryRepository(app.db), targets)
    return history, PersonalHome(history, HomeCatalog(app.library, app.listening))
