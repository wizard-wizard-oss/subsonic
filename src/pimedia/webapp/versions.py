"""Versions du site, lues dans i18n/versions.yaml (la plus récente en premier) : numéro « majeure.mineure » (ou « majeure.mineure.correction »),
date de mise en ligne, titre et changements, pour la page « Versions ». Un fichier mal tenu (numéro ou date qui recule, champ
manquant) est refusé au démarrage : mieux vaut le voir tout de suite qu'afficher un historique faux."""
import datetime
import os
import re
from dataclasses import dataclass

try:
    import yaml
except ImportError:            # python3-yaml absent : pas d'historique, rien ne plante (comme les textes)
    yaml = None

NUMBER = re.compile(r"\d+\.\d+(\.\d+)?")


class InvalidVersions(ValueError):
    """args[0] : la version (ou la position) fautive."""


@dataclass(frozen=True)
class Release:
    version: str
    date: datetime.date
    title: str
    changes: tuple

    @property
    def number(self):
        return tuple(int(part) for part in self.version.split("."))

    def to_api(self):
        return {"version": self.version, "date": self.date.isoformat(), "title": self.title,
                "changes": list(self.changes)}


def read_releases(path):
    if yaml is None or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        items = yaml.safe_load(f) or []
    if not isinstance(items, list):
        raise InvalidVersions(path)
    releases = [_release(position, item) for position, item in enumerate(items, 1)]
    for newer, older in zip(releases, releases[1:]):
        if newer.number <= older.number or newer.date < older.date:
            raise InvalidVersions(newer.version)
    return releases


def _release(position, item):
    if not isinstance(item, dict):
        raise InvalidVersions(position)
    version, date, title, changes = (item.get(key) for key in ("version", "date", "title", "changes"))
    if isinstance(date, str):
        try:
            date = datetime.date.fromisoformat(date)
        except ValueError:
            raise InvalidVersions(version or position) from None
    if not (isinstance(version, str) and NUMBER.fullmatch(version) and isinstance(date, datetime.date)
            and isinstance(title, str) and title.strip() and isinstance(changes, list) and changes
            and all(isinstance(change, str) and change.strip() for change in changes)):
        raise InvalidVersions(version or position)
    return Release(version, date, title.strip(), tuple(change.strip() for change in changes))
