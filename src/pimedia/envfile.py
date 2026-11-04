"""Fichier .env : réglages d'installation et secrets (adresse Subsonic, mots de passe, clés API…).
Il reste sur la machine, hors du code et des archives. Format : une ligne CLE=valeur, # pour un commentaire."""
import os
import threading

QUOTES = ("'", '"')


def parse(text):
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in QUOTES:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def quote(value):
    value = str(value)
    if value == "" or any(c in value for c in " #'\"\t"):
        return '"' + value.replace('"', '\\"') + '"'
    return value


class EnvFile:
    """Lecture (relue si le fichier change) et mise à jour d'un .env, en gardant commentaires et ordre."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._mtime = None
        self._values = {}

    def values(self):
        try:
            mtime = os.stat(self.path).st_mtime_ns
        except OSError:
            return {}
        with self._lock:
            if mtime != self._mtime:
                with open(self.path, encoding="utf-8") as f:
                    self._values = parse(f.read())
                self._mtime = mtime
            return dict(self._values)

    def set(self, **changes):
        """Remplace ou ajoute des lignes CLE=valeur. Le fichier n'est lisible que par son propriétaire."""
        with self._lock:
            try:
                with open(self.path, encoding="utf-8") as f:
                    lines = f.read().splitlines()
            except OSError:
                lines = []
            pending = dict(changes)
            for i, line in enumerate(lines):
                key = line.split("=", 1)[0].strip()
                if "=" in line and not line.lstrip().startswith("#") and key in pending:
                    lines[i] = "%s=%s" % (key, quote(pending.pop(key)))
            lines += ["%s=%s" % (key, quote(value)) for key, value in pending.items()]
            tmp = self.path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            os.replace(tmp, self.path)
            self._mtime = None
