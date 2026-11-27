"""Cache mémoire à durée de vie limitée pour les lectures de la bibliothèque."""
import threading
import time


class TtlCache:
    """Petit cache mémoire pour réutiliser une lecture jusqu'à son expiration."""

    def __init__(self, seconds, clock=time.time):
        self.seconds, self.clock = seconds, clock
        self._items = {}
        self._lock = threading.Lock()

    def get(self, key, compute):
        now = self.clock()
        with self._lock:
            hit = self._items.get(key)
            if hit and now - hit[0] < self.seconds:
                return hit[1]
        value = compute()
        with self._lock:
            self._items[key] = (now, value)
            if len(self._items) > 2000:
                self._items.clear()
        return value

    def forget(self, prefix):
        with self._lock:
            for key in [k for k in self._items if k[0] == prefix]:
                del self._items[key]

    def clear(self):
        with self._lock:
            self._items.clear()
