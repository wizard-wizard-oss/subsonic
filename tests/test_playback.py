"""Lecture haute fidélité : mpv piloté par son protocole JSON (ici un faux mpv qui parle le même protocole)."""
import json
import os
import sys
import tempfile
import time
import unittest

from pimedia.server.playback import CLIENT_NAME, HifiPlayer, mpv_command
from tests.support import ROOT, AppTestCase

FAKE_MPV = [sys.executable, os.path.join(ROOT, "tests", "fake_mpv.py")]


class FakeConfig:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def update(self, **changes):
        self.values.update(changes)


def wait_for(condition, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


class HifiPlayerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pm-mpv-")
        self.socket = os.path.join(self.dir, "mpv.sock")
        self.player = HifiPlayer(FakeConfig(), self.socket, lambda: "http://127.0.0.1:8099",
                                 FAKE_MPV + ["--input-ipc-server=" + self.socket])
        self.addCleanup(self.player.mpv.stop)

    def commands(self):
        with open(self.socket + ".log") as log:
            return [json.loads(line) for line in log]

    def test_command_line_keeps_the_original_sample_rate(self):
        command = mpv_command("/tmp/s")
        self.assertIn("--gapless-audio=yes", command)
        self.assertIn("--audio-client-name=" + CLIENT_NAME, command)
        self.assertFalse(any("samplerate" in c for c in command))    # aucune fréquence imposée : celle du fichier

    def test_load_plays_through_the_local_relay(self):
        self.player.load("/rest/stream.view?id=71048&format=raw")
        self.assertIn(["loadfile", "http://127.0.0.1:8099/rest/stream.view?id=71048&format=raw", "replace"], self.commands())
        self.assertTrue(wait_for(lambda: self.player.state()["duration"] == 261.0))
        state = self.player.state()
        self.assertEqual((state["url"], state["paused"], state["idle"]), ("/rest/stream.view?id=71048&format=raw", False, False))

    def test_refuses_other_addresses(self):
        for bad in ("/rest/deleteUser.view?u=x", "file:///etc/passwd", "http://127.0.0.1:22/", "http://localhost/x", ""):
            with self.assertRaises(ValueError, msg=bad):
                self.player.resolve(bad)
        self.assertEqual(self.player.resolve("https://radio.example/stream"), "https://radio.example/stream")

    def test_gapless_next_track(self):
        first, second = "/rest/stream.view?id=1&format=raw", "/rest/stream.view?id=2&format=raw"
        self.player.load(first)
        self.player.preload(second)
        self.assertEqual(self.commands()[-1], ["loadfile", "http://127.0.0.1:8099/rest/stream.view?id=2&format=raw", "append"])
        self.player.mpv.call("test-finish")
        self.assertTrue(wait_for(lambda: self.player.state()["ended"] == 1))
        self.assertEqual((self.player.state()["url"], self.player.state()["queued"]), (second, ""))
        loads_before = len([c for c in self.commands() if c[0] == "loadfile"])
        self.player.load(second)                        # la page demande le titre suivant : déjà en cours, rien à recharger
        self.assertEqual(len([c for c in self.commands() if c[0] == "loadfile"]), loads_before)

    def test_pause_seek_volume_and_errors(self):
        self.player.load("/rest/stream.view?id=1")
        self.player.pause(True)
        self.assertTrue(wait_for(lambda: self.player.state()["paused"]))
        self.player.seek(42)
        self.assertTrue(wait_for(lambda: self.player.state()["pos"] == 42.0))
        self.player.volume(150)
        self.assertIn(["set_property", "volume", 100], self.commands())
        self.player.mpv.call("test-fail")
        self.assertTrue(wait_for(lambda: self.player.state()["errors"] == 1))

    def test_restarts_mpv_if_it_stopped(self):
        self.player.load("/rest/stream.view?id=1")
        self.player.mpv.process.kill()
        self.player.mpv.process.wait()
        self.player.load("/rest/stream.view?id=2")
        self.assertEqual(self.player.state()["url"], "/rest/stream.view?id=2")


class AudioReleaseTest(unittest.TestCase):
    """Après une pause assez longue, mpv est arrêté pour rendre la carte son (l'ampli peut alors s'endormir)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pm-mpv-")
        self.socket = os.path.join(self.dir, "mpv.sock")
        self.now = 1000.0
        self.player = HifiPlayer(FakeConfig(), self.socket, lambda: "http://127.0.0.1:8099",
                                 FAKE_MPV + ["--input-ipc-server=" + self.socket], release_after=30,
                                 clock=lambda: self.now)
        self.addCleanup(self.player.mpv.stop)
        self.song = "/rest/stream.view?id=1&format=raw"

    def commands(self):
        with open(self.socket + ".log") as log:
            return [json.loads(line) for line in log]

    def paused_for(self, seconds):
        self.assertTrue(wait_for(lambda: self.player.state()["paused"]))
        self.assertFalse(self.player.release_if_idle())      # première vue : l'horloge démarre
        self.now += seconds
        return self.player.release_if_idle()

    def play_and_pause_at(self, position):
        self.player.load(self.song)
        self.assertTrue(wait_for(lambda: self.player.state()["duration"] == 261.0))
        self.player.seek(position)
        self.assertTrue(wait_for(lambda: self.player.state()["pos"] == position))
        self.player.pause(True)

    def test_playing_is_never_released(self):
        self.player.load(self.song)
        self.assertTrue(wait_for(lambda: self.player.state()["duration"] == 261.0))
        self.assertFalse(self.player.release_if_idle())
        self.now += 3600
        self.assertFalse(self.player.release_if_idle())
        self.assertTrue(self.player.mpv.alive())

    def test_short_pause_keeps_mpv(self):
        self.play_and_pause_at(10)
        self.assertFalse(self.paused_for(29))
        self.assertTrue(self.player.mpv.alive())

    def test_long_pause_stops_mpv_and_keeps_the_state(self):
        self.play_and_pause_at(42)
        self.assertTrue(self.paused_for(30))
        self.assertFalse(self.player.mpv.alive())
        state = self.player.state()
        self.assertEqual((state["released"], state["paused"], state["url"], state["pos"]), (True, True, self.song, 42.0))

    def test_resume_reloads_in_pause_seeks_then_plays(self):
        self.play_and_pause_at(42)
        self.player.volume(60)
        self.paused_for(60)
        self.player.pause(False)
        self.assertTrue(self.player.mpv.alive())
        commands = self.commands()
        resumed = commands[max(i for i, c in enumerate(commands) if c[0] == "observe_property") + 1:]
        self.assertEqual(resumed[0], ["set_property", "pause", True])
        self.assertEqual(resumed[1], ["set_property", "volume", 60.0])
        self.assertEqual(resumed[2][:3], ["loadfile", "http://127.0.0.1:8099" + self.song, "replace"])
        self.assertEqual(resumed[3], ["seek", 42.0, "absolute"])
        self.assertEqual(resumed[4], ["set_property", "pause", False])
        self.assertFalse(self.player.state()["released"])
        self.assertTrue(wait_for(lambda: not self.player.state()["paused"]))

    def test_seek_while_released_resumes_at_the_new_position(self):
        self.play_and_pause_at(42)
        self.paused_for(60)
        self.player.seek(100)
        self.assertTrue(wait_for(lambda: self.player.state()["pos"] == 100.0))

    def test_new_track_while_released_loads_it(self):
        self.play_and_pause_at(42)
        self.paused_for(60)
        self.player.load("/rest/stream.view?id=2&format=raw")
        self.assertEqual(self.commands()[-2][1], "http://127.0.0.1:8099/rest/stream.view?id=2&format=raw")
        self.assertEqual(self.player.state()["url"], "/rest/stream.view?id=2&format=raw")
        self.assertTrue(wait_for(lambda: not self.player.state()["paused"]))

    def test_preloaded_track_survives_the_release(self):
        self.play_and_pause_at(42)
        self.player.preload("/rest/stream.view?id=2&format=raw")
        self.paused_for(60)
        self.player.pause(False)
        self.assertIn(["loadfile", "http://127.0.0.1:8099/rest/stream.view?id=2&format=raw", "append"], self.commands()[-6:])

    def test_stop_while_released_does_not_start_mpv(self):
        self.play_and_pause_at(42)
        self.paused_for(60)
        self.player.stop()
        self.assertFalse(self.player.mpv.alive())
        self.assertEqual((self.player.state()["url"], self.player.state()["released"]), ("", False))

    def test_idle_player_is_released_too(self):
        self.player.load(self.song)
        self.assertTrue(wait_for(lambda: self.player.state()["duration"] == 261.0))
        self.player.mpv.call("test-finish")                  # file d'attente finie : mpv ne joue plus rien
        self.assertTrue(wait_for(lambda: self.player.state()["idle"]))
        self.assertFalse(self.player.release_if_idle())
        self.now += 30
        self.assertTrue(self.player.release_if_idle())
        self.player.volume(70)
        self.player.load(self.song)                          # reprise : mpv redémarre et lit
        self.assertTrue(self.player.mpv.alive())
        self.assertIn(["set_property", "volume", 70.0], self.commands())


class PlayerApiTest(AppTestCase):
    def setUp(self):
        super().setUp()
        sock = os.path.join(tempfile.mkdtemp(prefix="pm-mpv-"), "mpv.sock")
        self.app.hifi.mpv.socket_path = sock
        self.app.hifi.mpv.command = FAKE_MPV + ["--input-ipc-server=" + sock]
        self.addCleanup(self.app.hifi.mpv.stop)

    def cmd(self, body, **kwargs):
        return self.client.post_json("/player/cmd", body, **kwargs)

    def test_enable_load_and_state(self):
        self.assertFalse(self.client.get("/player/state", csrf=False).json()["enabled"])
        self.assertTrue(self.cmd({"action": "enable", "value": True}).json()["enabled"])
        self.assertEqual(self.cmd({"action": "load", "url": "/rest/stream.view?id=9&format=raw"}).status, 200)
        self.assertEqual(self.client.get("/player/state", csrf=False).json()["url"], "/rest/stream.view?id=9&format=raw")

    def test_refusals(self):
        self.assertEqual(self.cmd({"action": "load", "url": "/rest/stream.view?id=1"}, csrf=False).status, 403)
        self.assertEqual(self.cmd({"action": "load", "url": "file:///etc/passwd"}).status, 400)
        self.assertEqual(self.cmd({"action": "rm -rf"}).status, 400)



if __name__ == "__main__":
    unittest.main()


class AmpDiagnosticTest(unittest.TestCase):
    def load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("diagnostic_ampli", os.path.join(ROOT, "src", "diagnostic-ampli.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_verdicts(self):
        from pimedia.menu.audio import AudioStream
        diag = self.load()
        sinks = diag.parse_sinks("1\talsa_output.usb-DAC.analog-stereo\tPipeWire\ts32le 2ch 48000Hz\tIDLE\n")
        self.assertEqual(sinks, [("alsa_output.usb-DAC.analog-stereo", "IDLE")])
        hifi = AudioStream(5, corked=True, name="pi-media-hifi")
        self.assertIn("pi-media-hifi", diag.verdict(sinks, [hifi], [], {"card1/pcm0p": "RUNNING"}))
        self.assertTrue(diag.verdict(sinks, [hifi], [], {}).startswith("OK"))
        self.assertIn("joue", diag.verdict(sinks, [AudioStream(6, binary="chromium")], [], {"card1/pcm0p": "RUNNING"}))
        self.assertIn("enregistre", diag.verdict(sinks, [], ["parec"], {"card1/pcm0p": "RUNNING"}))
        self.assertIn("WirePlumber", diag.verdict(sinks, [], [], {"card1/pcm0p": "RUNNING"}))
