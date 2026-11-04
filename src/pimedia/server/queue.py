"""File d'attente commune : ce que l'écran du Pi envoie (sa file) et ce que les téléphones demandent (ajouts)."""
from ..entities import Track

PHONE = "phone"
UPCOMING_FOR_PHONE = 20


class QueueService:
    def __init__(self, queue):
        self.queue = queue

    # --- écran du Pi ---
    def state(self):
        snapshot = self.queue.snapshot()
        return dict(snapshot.to_api(), pending=[r.to_api() for r in self.queue.pending()])

    def save_from_screen(self, body):
        """body : {items: [{track, addedBy}], currentIndex}. Titres invalides écartés sans tout refuser."""
        items = body.get("items")
        if not isinstance(items, list):
            raise ValueError("liste attendue")
        entries, current, kept = [], int(body.get("currentIndex", -1)), 0
        for index, item in enumerate(items):
            try:
                track = Track.from_api((item or {}).get("track"))
            except (ValueError, AttributeError):
                if index < current:
                    current -= 1          # le titre en cours garde sa place malgré l'entrée écartée
                continue
            entries.append((track, str(item.get("addedBy") or "screen")[:20]))
            kept += 1
        return self.queue.replace(entries, current if 0 <= current < kept else -1).to_api()

    def take_for_screen(self):
        return [r.to_api() for r in self.queue.take_requests()]

    # --- téléphones ---
    def request_from_phone(self, track, mode):
        return self.queue.request(track, mode, PHONE)

    def upcoming_for_phone(self):
        """Ce qui va passer (sans le détail technique), et les demandes pas encore prises par l'écran."""
        snapshot = self.queue.snapshot()
        start = snapshot.current_index
        brief = lambda item: {"title": item.track.title, "artist": item.track.fields.get("artist", ""), "addedBy": item.added_by}
        current = snapshot.current
        return {"current": brief(current) if current else None,
                "upcoming": [brief(i) for i in snapshot.items[start + 1:start + 1 + UPCOMING_FOR_PHONE]],
                "pending": [{"title": r.track.title, "artist": r.track.fields.get("artist", ""), "mode": r.mode}
                            for r in self.queue.pending()]}
