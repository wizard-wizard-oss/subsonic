"""Invités AirPlay / Bluetooth : détection (qui joue, qui attend) et passage de main."""
import unittest

from pimedia.server.guests import WAITING_MAX_AGE, GuestWatcher, parse_sink_inputs, source_of
from tests.support import AppTestCase

PACTL = """Sink Input #41
\tDriver: protocol-native.c
\tCorked: no
\tProperties:
\t\tapplication.name = "Chromium"
\t\tapplication.process.binary = "chromium"
Sink Input #57
\tCorked: no
\tProperties:
\t\tapplication.process.binary = "shairport-sync"
"""


class FakeSystem:
    def __init__(self, streams=(), players=None):
        self.streams, self.player_states, self.played = list(streams), dict(players or {}), []

    def sink_inputs(self):
        return self.streams

    def players(self):
        return self.player_states

    def play(self, player):
        self.played.append(player)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class GuestFunctionsTest(unittest.TestCase):
    def test_parse_and_source(self):
        streams = parse_sink_inputs(PACTL)
        self.assertEqual([(s["name"], s["corked"]) for s in streams], [("Chromium", False), ("shairport-sync", False)])
        self.assertEqual([source_of(n) for n in ("shairport-sync", "bluez_source.AA", "chromium", "")],
                         ["airplay", "bluetooth", None, None])


class GuestWatcherTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.system = FakeSystem()
        self.watcher = GuestWatcher(self.system, self.clock)

    def tick(self, seconds=2):
        self.clock.now += seconds
        return self.watcher.state()

    def test_playing_waiting_and_nothing(self):
        self.assertIsNone(self.tick()["status"])
        self.system.player_states = {"bluez_player.AA_BB": "Paused", "chromium.instance1": "Playing"}
        state = self.tick()
        self.assertEqual((state["source"], state["label"], state["status"]), ("bluetooth", "Bluetooth", "waiting"))
        self.system.streams = [{"name": "bluez_source", "corked": False}]
        self.assertEqual(self.tick()["status"], "playing")
        self.system.streams = [{"name": "shairport-sync", "corked": True}]       # flux en pause : ne joue pas
        self.assertEqual(self.tick()["status"], "waiting")

    def test_phone_paused_for_too_long_is_not_waiting_anymore(self):
        self.system.player_states = {"ShairportSync": "Stopped"}
        self.assertEqual(self.tick()["status"], "waiting")
        self.assertIsNone(self.tick(WAITING_MAX_AGE + 5)["status"])

    def test_hand_over_plays_the_waiting_phone_only(self):
        self.assertFalse(self.watcher.hand_over())
        self.system.player_states = {"bluez_player.AA_BB": "Paused"}
        self.tick()
        self.assertTrue(self.watcher.hand_over())
        self.assertEqual(self.system.played, ["bluez_player.AA_BB"])


class GuestApiTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.system = FakeSystem(players={"bluez_player.AA_BB": "Paused"})
        self.app.guests.system = self.system

    def test_state_and_hand_over(self):
        state = self.client.get("/control/guest", csrf=False).json()
        self.assertEqual(state, {"source": "bluetooth", "label": "Bluetooth", "status": "waiting"})   # sans nom technique
        self.assertEqual(self.client.post_json("/control/guest", {}, csrf=False).status, 403)
        self.assertEqual(self.client.post_json("/control/guest", {}).status, 200)
        self.assertEqual(self.system.played, ["bluez_player.AA_BB"])

    def test_nothing_waiting(self):
        self.system.player_states = {}
        self.app.guests._cached = None
        self.assertEqual(self.client.post_json("/control/guest", {}).status, 409)



if __name__ == "__main__":
    unittest.main()
