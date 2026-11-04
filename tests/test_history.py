"""Historique des recherches de l'écran du Pi."""
import os
import tempfile
import unittest

from pimedia.storage.database import Database
from pimedia.storage.history import MAX_ENTRIES, SearchHistory
from tests.support import AppTestCase


class SearchHistoryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "pi-media.db")

    def test_recent_first_duplicates_move_up_and_persist(self):
        history = SearchHistory(Database(self.path))
        for text in ("daft punk", "  britney   spears ", "Daft Punk", "x"):
            history.add("music", text)
        self.assertEqual(SearchHistory(Database(self.path)).entries("music"), ["Daft Punk", "britney spears"])
        self.assertEqual(history.entries("podcasts"), [])                 # listes séparées

    def test_limit_remove_clear(self):
        history = SearchHistory(Database(self.path))
        for i in range(MAX_ENTRIES + 5):
            history.add("podcasts", "recherche %d" % i)
        self.assertEqual(len(history.entries("podcasts")), MAX_ENTRIES)
        history.remove("podcasts", "recherche %d" % (MAX_ENTRIES + 4))
        self.assertNotIn("recherche %d" % (MAX_ENTRIES + 4), history.entries("podcasts"))
        history.clear("podcasts")
        self.assertEqual(SearchHistory(Database(self.path)).entries("podcasts"), [])

    def test_unknown_kind(self):
        with self.assertRaises(ValueError):
            SearchHistory(Database(self.path)).add("autre", "abc")


class HistoryApiTest(AppTestCase):
    def test_add_list_remove_clear(self):
        post = lambda body, **kw: self.client.post_json("/ext/history", body, **kw)
        self.assertEqual(post({"kind": "music", "action": "add", "text": "Toxic"}).json()["entries"], ["Toxic"])
        post({"kind": "music", "action": "add", "text": "Groove"})
        self.assertEqual(self.client.get("/ext/history?kind=music", csrf=False).json()["entries"], ["Groove", "Toxic"])
        self.assertEqual(post({"kind": "music", "action": "remove", "text": "Toxic"}).json()["entries"], ["Groove"])
        self.assertEqual(post({"kind": "music", "action": "clear"}).json()["entries"], [])
        self.assertEqual(post({"kind": "music", "action": "drop"}).status, 400)
        self.assertEqual(self.client.get("/ext/history?kind=nope", csrf=False).status, 400)
        self.assertEqual(post({"kind": "music", "action": "add", "text": "x"}, csrf=False).status, 403)



if __name__ == "__main__":
    unittest.main()
