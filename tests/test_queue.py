"""File d'attente commune : copie de la file de l'écran, demandes d'ajout des téléphones."""
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

from pimedia.entities import QueueSnapshot, Track
from pimedia.server.queue import QueueService
from pimedia.storage.database import Database
from pimedia.storage.queue import PlayQueue
from tests.support import AppTestCase


def track(n, **extra):
    return Track.from_api(dict({"id": "s%d" % n, "title": "Titre %d" % n, "artist": "A"}, **extra))


class PlayQueueTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(prefix="pm-q-"), "pi-media.db")
        self.queue = PlayQueue(Database(self.path))

    def test_replace_keeps_order_current_and_survives_restart(self):
        snapshot = self.queue.replace([(track(1), "screen"), (track(2), "phone"), (track(3), "screen")], 1)
        self.assertIsInstance(snapshot, QueueSnapshot)
        reloaded = PlayQueue(Database(self.path)).snapshot()
        self.assertEqual([i.track.id for i in reloaded.items], ["s1", "s2", "s3"])
        self.assertEqual((reloaded.current_index, reloaded.current.track.id, reloaded.items[1].added_by), (1, "s2", "phone"))
        self.assertEqual(self.queue.replace([], -1).current, None)
        self.assertEqual(self.queue.snapshot().version, 2)

    def test_requests_are_taken_once_in_order(self):
        self.queue.request(track(1), "end", "phone")
        self.queue.request(track(2), "next", "phone")
        self.assertEqual(len(self.queue.pending()), 2)
        taken = self.queue.take_requests()
        self.assertEqual([(r.track.id, r.mode) for r in taken], [("s1", "end"), ("s2", "next")])
        self.assertEqual(self.queue.take_requests(), [])
        with self.assertRaises(ValueError):
            self.queue.request(track(3), "maintenant", "phone")


class QueueServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = QueueService(PlayQueue(Database(os.path.join(tempfile.mkdtemp(prefix="pm-q-"), "pi-media.db"))))

    def test_invalid_entries_are_dropped_and_current_follows(self):
        state = self.service.save_from_screen({"currentIndex": 2, "items": [
            {"track": {"title": "sans id"}}, {"track": track(1).to_api()}, {"track": track(2).to_api(), "addedBy": "phone"}]})
        self.assertEqual([i["track"]["id"] for i in state["items"]], ["s1", "s2"])
        self.assertEqual(state["currentIndex"], 1)
        with self.assertRaises(ValueError):
            self.service.save_from_screen({"items": "pas une liste"})

    def test_phone_view(self):
        self.service.save_from_screen({"currentIndex": 0, "items": [{"track": track(n).to_api()} for n in (1, 2, 3)]})
        self.service.request_from_phone(track(9), "next")
        view = self.service.upcoming_for_phone()
        self.assertEqual(view["current"]["title"], "Titre 1")
        self.assertEqual([t["title"] for t in view["upcoming"]], ["Titre 2", "Titre 3"])
        self.assertEqual(view["pending"], [{"title": "Titre 9", "artist": "A", "mode": "next"}])


class QueueApiTest(AppTestCase):
    def test_save_state_take(self):
        body = {"currentIndex": 0, "items": [{"track": track(1).to_api()}, {"track": track(2).to_api()}]}
        self.assertEqual(self.client.post_json("/queue/save", body, csrf=False).status, 403)
        saved = self.client.post_json("/queue/save", body).json()
        self.assertEqual(saved["version"], 1)
        self.assertEqual(len(self.client.get("/queue/state", csrf=False).json()["items"]), 2)
        self.assertEqual(self.client.post_json("/queue/take", {}).json(), {"requests": []})


class PhoneQueueTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.phone_server = self.app.start_phone_server(0)
        self.addCleanup(self.phone_server.server.server_close)
        self.addCleanup(self.phone_server.server.shutdown)
        url = self.client.post_json("/ext/remote", {}).json()["url"]
        self.code = parse_qs(urlsplit(url).query)["c"][0]

    def phone(self, path, body):
        request = urllib.request.Request("http://127.0.0.1:%d%s" % (self.phone_server.port, path),
                                         json.dumps(dict({"code": self.code}, **body)).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    def test_search_add_and_screen_takes_it(self):
        status, found = self.phone("/tel/search", {"text": "waterloo"})
        self.assertEqual(status, 200)
        song = next(s for s in found["songs"] if s["title"] == "Waterloo")
        self.assertEqual(self.phone("/tel/queue/add", {"id": song["id"], "mode": "next"})[0], 200)
        self.assertEqual(self.phone("/tel/queue", {})[1]["pending"][0]["title"], "Waterloo")
        taken = self.client.post_json("/queue/take", {}).json()["requests"]
        self.assertEqual((taken[0]["track"]["title"], taken[0]["mode"], taken[0]["addedBy"]), ("Waterloo", "next", "phone"))

    def test_only_searched_titles_and_valid_code(self):
        self.assertEqual(self.phone("/tel/queue/add", {"id": "s4", "mode": "end"})[0], 404)       # jamais cherché
        self.code = "faux"
        self.assertEqual(self.phone("/tel/search", {"text": "abba"})[0], 403)



if __name__ == "__main__":
    unittest.main()
