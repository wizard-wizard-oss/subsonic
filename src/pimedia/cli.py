"""Petits réglages en ligne de commande (sur le Pi ou le serveur, sans ouvrir l'application).

  python3 -m pimedia.cli set SUBSONIC_URL=https://… SUBSONIC_USER=utilisateur SUBSONIC_PASS=…
  python3 -m pimedia.cli show            (affiche les clés du .env, secrets masqués)
  python3 -m pimedia.cli migrate         (reprend secrets et clés API de l'ancien config.json dans le .env)
"""
import os
import sys

from .envfile import EnvFile
from .paths import resolve_data_dir
from .settings import ENV_TYPES
from .storage.legacy import RENAMED_KEYS, env_text, read_json

SECRET_WORDS = ("PASS", "SECRET", "KEY", "TOKEN")


def data_dir():
    code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    directory = resolve_data_dir(code_dir, os.environ)
    os.makedirs(directory, exist_ok=True)
    return directory


def env_file():
    return EnvFile(os.path.join(data_dir(), ".env"))


def masked(key, value):
    return "••••" if any(w in key for w in SECRET_WORDS) and value else value


def migrate():
    """Ancien config.json (ou sa copie .importe) -> .env : adresse et identifiants Subsonic, clés API, réglages du menu.
    Les valeurs déjà présentes dans le .env sont gardées."""
    old = next((p for p in (os.path.join(data_dir(), n) for n in ("config.json", "config.json.importe")) if os.path.exists(p)), None)
    data = read_json(old) if old else None
    if not isinstance(data, dict):
        print("Aucun ancien config.json à reprendre.")
        return 0
    env = env_file()
    present = env.values()
    data = {RENAMED_KEYS.get(k, k): v for k, v in data.items()}
    fresh = {k.upper(): env_text(v) for k, v in data.items() if k in ENV_TYPES and k.upper() not in present and v not in ("", None)}
    if fresh:
        env.set(**fresh)
    print("Repris depuis %s :" % os.path.basename(old))
    for key, value in sorted(fresh.items()):
        print("  %s=%s" % (key, masked(key, value)))
    if not fresh:
        print("  rien de nouveau (tout est déjà dans le .env)")
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "set" and all("=" in a for a in argv[1:]):
        changes = dict(a.split("=", 1) for a in argv[1:])
        env_file().set(**{k.strip().upper(): v for k, v in changes.items()})
        print("Enregistré dans", env_file().path, ":", ", ".join(k.upper() for k in changes))
        return 0
    if argv == ["show"]:
        for key, value in sorted(env_file().values().items()):
            print("%s=%s" % (key, masked(key, value)))
        return 0
    if argv == ["migrate"]:
        return migrate()
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
