"""Recherche et pagination du catalogue visible par le compte Subsonic courant."""
from ...shared.text import normalize
from .entities import DEFAULT_SORT, PAGE_SIZE, SORTS, PlaylistCard, PlaylistPage


class PlaylistGallery:
    def __init__(self, playlists):
        self.playlists = playlists

    def page(self, user, page=None, query="", sort=""):
        page = 0 if page is None else page
        sort = sort or DEFAULT_SORT
        if not isinstance(page, int) or isinstance(page, bool) or page < 0:
            raise ValueError("page")
        if sort not in SORTS or not isinstance(query, str):
            raise ValueError("request.invalid")
        key = normalize(query.strip())
        # getPlaylists n'a pas d'offset : filtrer les résumés avant de lire les seuls contenus affichés.
        cards = [card for card in self.playlists.all(user) if not key or key in normalize(card["name"])]
        cards.sort(key=lambda card: (normalize(card["name"]), str(card["id"])))
        if sort == "recent":
            cards.sort(key=lambda card: card.get("changed") or "", reverse=True)
        start, end = page * PAGE_SIZE, (page + 1) * PAGE_SIZE
        shown = [PlaylistCard.of(self.playlists.get(user, card["id"])) for card in cards[start:end]]
        return PlaylistPage(shown, page, len(cards) > end, sort)
