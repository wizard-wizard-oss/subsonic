"""Menu tactile : logique (réglages, thème, météo, son, veille, extinction) et écran avec une doublure de Tk."""
import json
import os
import runpy
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

from pimedia.i18n import Texts
from pimedia.menu import audio, idle, system, theme
from pimedia.menu.config import MenuConfig
from pimedia.menu.main import Services, build
from pimedia.menu.players import MprisPlayers, Radio, WebPlayer
from pimedia.menu.spectrum import Spectrum, level_of
from pimedia.menu.stations import STATIONS
from pimedia.menu.weather import Weather
from tests import fake_tk

PROJECT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
TEXTS = Texts(os.path.join(PROJECT, "i18n"), "fr")

SINK_INPUTS = """Sink Input #41
	Corked: no
	Properties:
		application.name = "Chromium"
		application.process.binary = "chromium"
Sink Input #42
	Corked: yes
	Properties:
		application.name = "Shairport Sync"
		application.process.binary = "shairport-sync"
Sink Input #43
	Corked: no
	Properties:
		application.name = "pi-media-hifi"
		application.process.binary = "mpv"
"""


class Process:
    def __init__(self, code=None):
        self.code = code
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True
        self.code = -15


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_defaults_without_any_file(self):
        config = MenuConfig.load(self.dir, {})
        self.assertEqual((config.device_name, config.screensaver_seconds, config.theme), ("Salon", 120, "retro"))

    def test_env_file_with_types(self):
        self.write(".env", "DEVICE_NAME=Cuisine\nWEATHER_LATITUDE=48.85\nSCREENSAVER_SECONDS=30\nTHEME=clair\n")
        config = MenuConfig.load(self.dir, {})
        self.assertEqual((config.device_name, config.weather_latitude, config.screensaver_seconds, config.theme),
                         ("Cuisine", 48.85, 30, "clair"))

    def test_legacy_json_then_env_wins(self):
        self.write("config.json", json.dumps({"nom": "Bureau", "ville": "Paris", "veille_secondes": 60}))
        self.write(".env", "WEATHER_CITY=Nantes\n")
        config = MenuConfig.load(self.dir, {})
        self.assertEqual((config.device_name, config.weather_city, config.screensaver_seconds), ("Bureau", "Nantes", 60))

    def test_process_environment_wins_and_bad_values_are_ignored(self):
        self.write(".env", "SCREENSAVER_SECONDS=beaucoup\nDEVICE_NAME=Salon\n")
        config = MenuConfig.load(self.dir, {"PI_MEDIA_DEVICE_NAME": "Test"})
        self.assertEqual((config.device_name, config.screensaver_seconds), ("Test", 120))

    def test_web_address(self):
        self.assertEqual(MenuConfig(web_url="http://x:1/").web("/podcasts"), "http://x:1/podcasts")
        self.assertEqual(MenuConfig(web_url="http://x:1").web(), "http://x:1/")


class ThemeTest(unittest.TestCase):
    def test_retro_file_matches_built_in_defaults(self):
        loaded = theme.load_theme(os.path.join(PROJECT, "themes"), "retro")
        self.assertEqual(loaded.colors, theme.Colors())
        self.assertEqual(loaded.equalizer.segments, theme.Equalizer().segments)

    def test_unknown_theme_falls_back_to_retro(self):
        self.assertEqual(theme.load_theme(os.path.join(PROJECT, "themes"), "inexistant").colors.text, "#39ff6e")

    def test_partial_theme_keeps_other_values(self):
        partial = theme.Theme.from_dict({"name": "Clair", "colors": {"background": "#ffffff", "inconnu": 1}})
        self.assertEqual((partial.name, partial.colors.background, partial.colors.text), ("Clair", "#ffffff", "#39ff6e"))

    def test_theme_name_cannot_leave_the_folder(self):
        self.assertEqual(theme.load_theme(os.path.join(PROJECT, "themes"), "../i18n/fr").name, "Rétro hi-fi")

    def test_css_variables_for_the_web_page(self):
        css = theme.Theme().css_variables()
        self.assertIn("--theme-background: #040a04;", css)
        self.assertIn("--theme-text-soft: #9be8ae;", css)

    def test_available_themes(self):
        self.assertIn("retro", theme.available_themes(os.path.join(PROJECT, "themes")))


class WeatherTest(unittest.TestCase):
    DATA = {"current": {"temperature_2m": 12.6, "weather_code": 61},
            "daily": {"temperature_2m_max": [15.2], "temperature_2m_min": [7.4]}}

    def test_report(self):
        weather = Weather(MenuConfig(weather_city="Lyon"), TEXTS, fetch=lambda url: self.DATA)
        report = weather.refresh()
        self.assertEqual(report.main, "13°C · Pluie")
        self.assertEqual(report.sub, "Lyon · min 7° / max 15°")

    def test_unknown_code_and_failure_keep_something_readable(self):
        weather = Weather(MenuConfig(), TEXTS, fetch=mock.Mock(side_effect=OSError))
        self.assertEqual(weather.refresh().main, "Météo indisponible")
        self.assertEqual(weather.sky(42), "Variable")
        self.assertEqual(weather.sky(0), "Ciel dégagé")

    def test_url_uses_coordinates(self):
        seen = []
        Weather(MenuConfig(weather_latitude=1.5, weather_longitude=2.5), TEXTS,
                fetch=lambda url: seen.append(url) or self.DATA).refresh()
        self.assertIn("latitude=1.5&longitude=2.5", seen[0])


class AudioTest(unittest.TestCase):
    def test_parse_sink_inputs(self):
        streams = audio.parse_sink_inputs(SINK_INPUTS)
        self.assertEqual([s.id for s in streams], [41, 42, 43])
        self.assertEqual([s.corked for s in streams], [False, True, False])
        self.assertEqual([s.label for s in streams], ["chromium", "shairport-sync", "pi-media-hifi"])

    def test_families(self):
        self.assertEqual([audio.family_of(n) for n in ("pi-media-hifi", "mpv", "chromium", "feishin",
                                                        "shairport-sync", "bluealsa-bluez", "", "vlc")],
                         ["web", "mpv", "web", "feishin", "airplay", "bluetooth", "inconnu", "vlc"])

    def test_last_one_to_start_wins(self):
        self.assertEqual(audio.families_to_silence({}, {1: "chromium"}), [])
        self.assertEqual(audio.families_to_silence({1: "chromium"}, {1: "chromium", 2: "shairport-sync"}), ["web"])
        self.assertEqual(audio.families_to_silence({1: "chromium"}, {1: "chromium"}), [])
        # la haute fidélité (mpv nommé pi-media-hifi) est le lecteur web : pas de conflit avec la page
        self.assertEqual(audio.families_to_silence({1: "chromium"}, {1: "chromium", 2: "pi-media-hifi"}), [])

    def test_volume(self):
        calls = []

        def run(args, timeout=3):
            calls.append(args)
            return "Volume: front-left: 62259 /  95% / -1.34 dB" if "get-sink-volume" in args else ""
        pulse = audio.PulseAudio(run)
        self.assertEqual(pulse.volume(), 95)
        self.assertEqual(pulse.change_volume(10), 100)
        self.assertEqual(calls[-1][-1], "100%")
        self.assertIsNone(audio.PulseAudio(lambda *a, **k: "").change_volume(5))

    def test_arbiter_silences_the_older_source_once(self):
        chromium = "Sink Input #1\n\tCorked: no\n\t\tapplication.process.binary = \"chromium\"\n"
        airplay = "Sink Input #2\n\tCorked: no\n\t\tapplication.process.binary = \"shairport-sync\"\n"
        outputs = [chromium, chromium + airplay]
        pulse = audio.PulseAudio(lambda *a, **k: outputs[0])
        paused = []
        arbiter = audio.AudioArbiter(pulse, {"web": lambda: paused.append("web"),
                                             "airplay": mock.Mock(side_effect=RuntimeError)})
        self.assertEqual(arbiter.step(), [])
        outputs[0] = outputs[1]                     # AirPlay démarre
        self.assertEqual(arbiter.step(), ["web"])
        self.assertEqual(paused, ["web"])
        self.assertEqual(arbiter.step(), [])        # plus rien de nouveau

    def test_playing(self):
        self.assertTrue(audio.PulseAudio(lambda *a, **k: SINK_INPUTS).playing())
        self.assertFalse(audio.PulseAudio(lambda *a, **k: "").playing())


class SpectrumTest(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(level_of(-85, 0), 0.0)
        self.assertEqual(level_of(0, 0), 1.0)
        self.assertAlmostEqual(level_of(-200, 1.0), 0.82)
        spectrum = Spectrum(3, pulse=None)
        spectrum.levels = [0.0, 0.5, 1.0]
        self.assertEqual(spectrum.lit(8), [0, 4, 8])
        spectrum.clear()
        self.assertEqual(spectrum.levels, [0.0] * 3)


class PlayersTest(unittest.TestCase):
    def test_now_playing_picks_the_playing_player(self):
        out = "Paused|A – B\nPlaying|Daft Punk – One More Time\n"
        players = MprisPlayers(run=lambda *a, **k: out, which=lambda name: "/usr/bin/" + name)
        self.assertEqual(players.now_playing(), "Daft Punk – One More Time")
        self.assertEqual(MprisPlayers(run=lambda *a, **k: out, which=lambda n: None).now_playing(), "")

    def test_pause_matching(self):
        calls = []

        def run(args, timeout=3):
            calls.append(args)
            return "feishin.instance1 bluez_player spotify" if args == ["playerctl", "-l"] else ""
        MprisPlayers(run=run).pause_matching("bluez")
        self.assertEqual(calls[-1], ["playerctl", "-p", "bluez_player", "pause"])

    def test_web_player(self):
        opened = []
        player = WebPlayer(MenuConfig(), opener=lambda url: opened.append(url) or b'{"awake": true}')
        player.pause()
        self.assertTrue(player.wants_awake())
        self.assertEqual(opened[0], "http://127.0.0.1:8099/control/send?cmd=pause")
        self.assertFalse(WebPlayer(MenuConfig(), opener=mock.Mock(side_effect=OSError)).wants_awake())

    def test_radio(self):
        spawned = []
        radio = Radio(spawn=lambda args, **k: spawned.append(args) or Process(), which=lambda n: "/usr/bin/mpv")
        self.assertTrue(radio.play(STATIONS[0]))
        first = radio.process
        self.assertTrue(radio.play(STATIONS[1]))
        self.assertTrue(first.terminated)
        self.assertEqual(spawned[-1][-1], STATIONS[1].url)
        radio.process.code = 1                       # flux perdu
        radio.check()
        self.assertTrue(radio.interrupted)
        self.assertIsNone(radio.station)
        self.assertFalse(Radio(which=lambda n: None).play(STATIONS[0]))

    def test_nine_stations_for_the_grid(self):
        self.assertEqual(len(STATIONS), 9)
        self.assertTrue(all(s.url.startswith("https://") for s in STATIONS))


class SystemTest(unittest.TestCase):
    def test_power_tries_systemctl_then_sudo(self):
        calls = []
        results = iter([1, 0])

        def run(args, **kwargs):
            calls.append(args)
            return types.SimpleNamespace(returncode=next(results))
        self.assertTrue(system.Power(run).execute("reboot"))
        self.assertEqual(calls, [["systemctl", "--no-ask-password", "reboot"], ["sudo", "-n", "systemctl", "reboot"]])

    def test_power_refused_and_unknown_action(self):
        power = system.Power(lambda *a, **k: types.SimpleNamespace(returncode=1))
        self.assertFalse(power.execute("poweroff"))
        with self.assertRaises(ValueError):
            power.execute("rm -rf")
        failing = system.Power(mock.Mock(side_effect=OSError))
        self.assertFalse(failing.execute("poweroff"))

    def test_power_in_background_reports_refusal(self):
        refused = threading.Event()
        system.Power(lambda *a, **k: types.SimpleNamespace(returncode=1)).execute_in_background("reboot", refused.set)
        self.assertTrue(refused.wait(2))

    def test_app_launcher(self):
        process = Process()
        apps = system.AppLauncher(spawn=lambda args, env=None: process, which=lambda n: "/usr/bin/" + n)
        self.assertTrue(apps.launch(["chromium", "--kiosk"]))
        self.assertFalse(apps.launch(["freetube"]))      # une appli à la fois
        self.assertEqual(apps.name, "chromium")
        self.assertFalse(apps.finished())
        process.code = 0
        self.assertTrue(apps.finished())
        self.assertFalse(apps.running)
        with self.assertRaises(FileNotFoundError):
            system.AppLauncher(which=lambda n: None).launch(["freetube"])


class IdleTest(unittest.TestCase):
    def test_timer(self):
        now = [100.0]
        timer = idle.IdleTimer(clock=lambda: now[0])
        now[0] = 130
        self.assertEqual(timer.idle_seconds(), 30)
        timer.touch("event")
        self.assertEqual(timer.idle_seconds(), 0)

    def test_saver_decision(self):
        self.assertIsNone(idle.saver_decision(10, 120, False, None, True))
        self.assertEqual(idle.saver_decision(200, 120, False, None, False), "menu")
        self.assertIsNone(idle.saver_decision(200, 120, True, None, True))           # déjà affichée
        self.assertEqual(idle.saver_decision(200, 120, False, "chromium", True), "over_app")
        self.assertIsNone(idle.saver_decision(200, 120, False, "chromium", False))   # on ne pourrait pas la réveiller
        self.assertIsNone(idle.saver_decision(200, 120, False, "freetube", True))    # vidéo : pas de veille dessus


def quiet_services(data_dir):
    """Services réels, sans aucun programme externe ni réseau."""
    services = Services(PROJECT, data_dir, {})
    services.pulse.run = lambda args, timeout=3: SINK_INPUTS if "sink-inputs" in args else " 40% "
    services.mpris.run = lambda *a, **k: ""
    services.web_player.opener = lambda url: b"{}"
    services.radio.spawn = lambda args, **k: Process()
    services.radio.which = lambda name: "/usr/bin/" + name
    services.apps.spawn = lambda args, env=None: Process()
    services.apps.which = lambda name: "/usr/bin/" + name
    services.power.run = lambda *a, **k: types.SimpleNamespace(returncode=0)
    services.start_bluetooth = mock.Mock()
    services.web_command = lambda path="": ["chromium", "--app=" + services.config.web(path)]
    return services


class MenuScreenTest(unittest.TestCase):
    def setUp(self):
        from pimedia.menu.ui import MenuUI
        self.services = quiet_services(tempfile.mkdtemp())
        self.ui = MenuUI(fake_tk.module(), self.services)
        self.root = self.ui.root

    def button(self, text, inside=None):
        for widget in (inside or self.root).find_all(fake_tk.Button):
            if widget.options.get("text") == text:
                return widget
        raise AssertionError("bouton absent : " + text)

    def test_home_tiles_come_from_the_texts(self):
        texts = [b.options["text"] for b in self.ui.home.find_all(fake_tk.Button)]
        self.assertIn("MUSIQUE\nSUBSONIC", texts)
        self.assertIn("Éteindre", texts)
        self.assertEqual(self.root.options["title"], "Accueil")
        self.assertEqual(self.root.options["bg"], "#040a04")

    def test_radio_tile_plays_and_stop_button(self):
        self.button("RADIO").invoke()
        self.assertIs(self.root.raised, self.ui.radio)
        self.button("FIP", self.ui.radio).invoke()
        self.assertEqual(self.services.radio.station.name, "FIP")
        self.assertEqual(self.ui.playing_text(), "En écoute : FIP")
        self.button("Arrêter la radio", self.ui.radio).invoke()
        self.assertIsNone(self.services.radio.station)

    def test_music_tile_hides_the_menu_until_the_app_closes(self):
        self.button("MUSIQUE\nSUBSONIC").invoke()
        self.assertTrue(self.root.withdrawn)
        self.services.apps.process.code = 0
        self.ui.tick()
        self.assertFalse(self.root.withdrawn)
        self.assertIs(self.root.raised, self.ui.home)

    def test_missing_program_is_reported(self):
        self.services.apps.which = lambda name: None
        self.button("YOUTUBE\nFREETUBE").invoke()
        self.assertEqual(self.ui.status.get(), "freetube introuvable")

    def test_power_asks_first_and_no_means_no(self):
        executed = []
        self.services.power.execute_in_background = lambda action, refused: executed.append(action)
        self.button("Éteindre").invoke()
        veil = self.root.raised
        choices = {w.options["text"]: w for w in veil.find_all(fake_tk.Label) if w.options.get("text") in ("Oui", "Non")}
        choices["Non"].bindings["<ButtonPress-1>"](None)
        self.assertEqual(executed, [])
        self.assertFalse(veil.winfo_exists())
        self.button("Redémarrer").invoke()
        veil = self.root.raised
        yes = [w for w in veil.find_all(fake_tk.Label) if w.options.get("text") == "Oui"][0]
        yes.bindings["<ButtonPress-1>"](None)
        self.assertEqual(executed, ["reboot"])
        self.assertEqual(self.ui.status.get(), "Redémarrer en cours…")

    def test_confirmation_closes_by_itself(self):
        self.button("Éteindre").invoke()
        veil = self.root.raised
        self.root.run_timers()                  # les 20 s sont écoulées
        self.assertFalse(veil.winfo_exists())

    def test_tick_shows_clock_volume_and_screensaver(self):
        self.services.idle.last -= 1000
        self.ui.tick()
        self.assertTrue(self.ui.saver_visible)
        self.assertEqual(self.ui.volume_text.get(), "VOL 40%")
        self.assertRegex(self.ui.saver_clock.options["text"], r"^\d\d:\d\d$")
        self.assertRegex(self.ui.home_date.options["text"], r"^(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche) ")
        self.ui.hide_saver()
        self.assertFalse(self.ui.saver_visible)

    def test_volume_buttons_on_the_saver(self):
        calls = []
        self.services.pulse.run = lambda args, timeout=3: calls.append(args) or " 40% "
        self.button("+", self.ui.saver).invoke()
        self.assertEqual(calls[-1][-1], "45%")
        self.assertEqual(self.ui.volume_text.get(), "VOL 45%")

    def test_equalizer_lights_segments(self):
        self.services.spectrum.levels = [1.0] * 20
        self.ui.saver_visible = True
        self.ui.animate()
        lit = [item["fill"] for item in self.ui.saver_eq.canvas.items.values()]
        self.assertEqual(lit.count("#0a2410"), 0)
        self.assertIn("#ff4b3a", lit)

    def test_bluetooth_tile(self):
        self.button("BLUETOOTH\nAPPAIRAGE").invoke()
        self.services.start_bluetooth.assert_called_once()
        self.assertEqual(self.ui.status.get(), "Bluetooth : cherchez « Salon » (2 min)")


class StartupTest(unittest.TestCase):
    def test_build_reads_the_data_folder(self):
        data = tempfile.mkdtemp()
        with open(os.path.join(data, ".env"), "w") as f:
            f.write("DEVICE_NAME=Véranda\n")
        services, ui = build(PROJECT, tk=fake_tk.module(), environ={"PI_MEDIA_DATA": data})
        self.assertEqual(services.config.device_name, "Véranda")
        self.assertEqual(len(services.background_tasks()), 6)

    def test_launcher_falls_back_to_the_classic_menu(self):
        """Si le nouveau menu plante au démarrage, l'ancien prend le relais et l'erreur est notée."""
        data = tempfile.mkdtemp()
        fake = types.ModuleType("tkinter")
        fake.__dict__.update(vars(fake_tk.module()))
        fake._default_root = None
        started = []
        with mock.patch.dict(sys.modules, {"tkinter": fake}), \
                mock.patch.dict(os.environ, {"PI_MEDIA_DATA": data}), \
                mock.patch("pimedia.menu.main.build", side_effect=RuntimeError("panne")):
            launcher = runpy.run_path(os.path.join(PROJECT, "launcher.py"), run_name="launcher")
            with mock.patch("runpy.run_path", side_effect=lambda path, run_name: started.append(path)):
                launcher["main"]()
        self.assertTrue(started[0].endswith("launcher_classic.py"))
        with open(os.path.join(data, "menu-erreur.log")) as f:
            self.assertIn("RuntimeError: panne", f.read())

    def test_classic_menu_still_builds(self):
        """Le menu de secours doit au moins se construire (aucun nom manquant)."""
        fake = types.ModuleType("tkinter")
        fake.__dict__.update(vars(fake_tk.module()))
        with mock.patch.dict(sys.modules, {"tkinter": fake}), \
                mock.patch("threading.Thread.start"), \
                mock.patch("os.path.expanduser", return_value=tempfile.mkdtemp()):
            namespace = runpy.run_path(os.path.join(PROJECT, "launcher_classic.py"), run_name="classic")
        self.assertIn("confirm_here", namespace)
        self.assertIsInstance(namespace["root"], fake_tk.Tk)


if __name__ == "__main__":
    unittest.main()
