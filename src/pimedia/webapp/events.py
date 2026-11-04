"""Temps réel : chaque page ouverte reçoit les événements (nouveau message, réaction, présence, « écrit… »)
par une connexion SSE (EventSource). Rien n'est rejoué : après une coupure, la page redemande les messages
arrivés depuis le dernier qu'elle connaît."""
import itertools
import json
import queue
import threading
import time

from ..server.transport import Reply


class Subscriber:
    MAX_PENDING = 500

    def __init__(self, user):
        self.user = user
        self.events = queue.Queue(self.MAX_PENDING)
        self.closed = False

    def push(self, payload):
        """False si la page ne suit plus (trop d'événements en retard) : elle sera déconnectée puis se reconnectera."""
        try:
            self.events.put_nowait(payload)
            return True
        except queue.Full:
            self.closed = True
            return False


class EventHub:
    def __init__(self, clock=time.time):
        self.clock = clock
        self._subscribers = set()
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._typing = {}                        # (user_id, topic) -> dernier envoi

    # --- abonnements ---
    def subscribe(self, user):
        subscriber = Subscriber(user)
        with self._lock:
            first = not any(s.user.id == user.id for s in self._subscribers)
            self._subscribers.add(subscriber)
        if first:
            self.publish("presence", {"online": self.online()})
        return subscriber

    def unsubscribe(self, subscriber):
        with self._lock:
            self._subscribers.discard(subscriber)
            last = not any(s.user.id == subscriber.user.id for s in self._subscribers)
        if last:
            self.publish("presence", {"online": self.online()})

    def online(self):
        with self._lock:
            return sorted({s.user.username for s in self._subscribers}, key=str.lower)

    # --- diffusion ---
    def publish(self, kind, data, to_user_id=None, except_user_id=None):
        payload = "id: %d\nevent: %s\ndata: %s\n\n" % (next(self._ids), kind, json.dumps(data, ensure_ascii=False))
        with self._lock:
            targets = [s for s in self._subscribers
                       if (to_user_id is None or s.user.id == to_user_id) and s.user.id != except_user_id]
        for subscriber in targets:
            subscriber.push(payload)

    def typing(self, user, topic, every=2.0):
        """« X écrit… » : au plus un signal toutes les 2 secondes par personne et par sujet."""
        now = self.clock()
        key = (user.id, topic)
        if now - self._typing.get(key, 0) < every:
            return False
        self._typing[key] = now
        if len(self._typing) > 5000:
            self._typing.clear()
        self.publish("typing", {"topic": topic, "user": user.username}, except_user_id=user.id)
        return True


class EventStreamReply(Reply):
    """Réponse qui reste ouverte : envoie les événements de l'abonné, et un signe de vie toutes les 15 s
    (sinon un proxy ou le navigateur coupe la connexion)."""

    HEARTBEAT = 15

    def __init__(self, hub, user, heartbeat=None):
        super().__init__(200, b"", "text/event-stream")
        self.hub = hub
        self.user = user
        self.heartbeat = heartbeat or self.HEARTBEAT
        self.close_connection = True

    def write_to(self, handler):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Accel-Buffering", "no")       # nginx : ne pas retenir le flux
        handler.send_header("Connection", "close")
        handler.end_headers()
        subscriber = self.hub.subscribe(self.user)
        try:
            handler.wfile.write(b"retry: 3000\n\n")
            handler.wfile.flush()
            while not subscriber.closed:
                try:
                    payload = subscriber.events.get(timeout=self.heartbeat)
                except queue.Empty:
                    payload = ": ping\n\n"
                handler.wfile.write(payload.encode("utf-8"))
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.hub.unsubscribe(subscriber)
