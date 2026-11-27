"""Première visite de Help : « vu » est noté par compte, une seule fois, et ne bouge pas les autres réglages."""
from pimedia.webapp.preferences import CHOICES, DEFAULTS
from tests.webapp_support import WebAppTestCase


class HelpFirstVisitTest(WebAppTestCase):
    def test_help_is_unseen_by_default_and_the_default_is_defined_once_on_the_server(self):
        self.assertIs(DEFAULTS["help_seen"], False)
        self.assertEqual(CHOICES["help_seen"], (True, False))
        bob = self.client("bob", "pw2")
        self.assertIs(bob.get("/api/me").json()["preferences"]["help_seen"], False)

    def test_noting_the_visit_is_remembered_by_account_and_across_sessions(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        saved = bob.post_json("/api/preferences", {"changes": {"help_seen": True}})
        self.assertEqual(saved.status, 200)
        self.assertIs(saved.json()["preferences"]["help_seen"], True)
        self.assertIs(self.client("bob", "pw2").get("/api/me").json()["preferences"]["help_seen"], True)
        self.assertIs(alice.get("/api/me").json()["preferences"]["help_seen"], False)

    def test_noting_the_visit_leaves_the_other_settings_untouched(self):
        bob = self.client("bob", "pw2")
        bob.post_json("/api/preferences", {"changes": {"help_seen": True}})
        expected = dict(DEFAULTS, help_seen=True)
        self.assertEqual(bob.get("/api/me").json()["preferences"], expected)

    def test_only_a_strict_boolean_is_accepted(self):
        bob = self.client("bob", "pw2")
        for invalid in (0, 1, "true", None, [], {}):
            with self.subTest(value=invalid):
                self.assertEqual(bob.post_json("/api/preferences", {"changes": {"help_seen": invalid}}).status, 400)
        self.assertIs(bob.get("/api/me").json()["preferences"]["help_seen"], False)
