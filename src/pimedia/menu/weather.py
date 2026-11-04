"""Météo du jour (Open-Meteo, sans clé) et libellés des codes WMO (i18n : launcher.weather.codes)."""
import json
import time
import urllib.request

FORECAST_URL = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min"
                "&timezone=auto&forecast_days=1")


def fetch_json(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


class WeatherReport:
    def __init__(self, main="", sub=""):
        self.main = main
        self.sub = sub


class Weather:
    def __init__(self, config, texts, fetch=fetch_json):
        self.config = config
        self.texts = texts
        self.fetch = fetch
        self.report = WeatherReport(texts.t("launcher.weather.unavailable"))

    def sky(self, code):
        key = "launcher.weather.codes.%d" % code
        text = self.texts.t(key)
        return self.texts.t("launcher.weather.unknown") if text == key else text

    def describe(self, data):
        current, daily = data["current"], data["daily"]
        main = self.texts.t("launcher.weather.now", temperature=round(current["temperature_2m"]),
                            sky=self.sky(int(current["weather_code"])))
        sub = self.texts.t("launcher.weather.today", city=self.config.weather_city,
                           low=round(daily["temperature_2m_min"][0]), high=round(daily["temperature_2m_max"][0]))
        return WeatherReport(main, sub)

    def refresh(self):
        """Met à jour le bulletin ; en cas d'échec on garde le précédent."""
        try:
            data = self.fetch(FORECAST_URL % (self.config.weather_latitude, self.config.weather_longitude))
            self.report = self.describe(data)
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            pass
        return self.report

    def loop(self, every=900):
        while True:
            self.refresh()
            time.sleep(every)
