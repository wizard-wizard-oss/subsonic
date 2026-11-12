"""Lance tous les parcours navigateur (jsdom) : chaque parcours a son propre serveur de test, tout neuf.
Usage : python3 -m tests.run_e2e [chemin vers jsdom]   (sinon JSDOM_PATH, sinon « jsdom » trouvé par Node)
Code de sortie : 0 si tout est OK, 1 sinon."""
import os
import subprocess
import sys

from tests.support import ROOT

PI_HARNESS = "tests.e2e_harness"
PC_HARNESS = "tests.e2e_webapp_harness"
JOURNEYS = [   # (parcours, serveur de test)
    ("e2e_podcasts.js", PI_HARNESS),
    ("e2e_music.js", PI_HARNESS),
    ("e2e_queue.js", PI_HARNESS),
    ("e2e_hifi.js", PI_HARNESS),
    ("e2e_webapp.js", PC_HARNESS),
    ("e2e_webapp_queue.js", PC_HARNESS),
    ("e2e_listen_later.js", PC_HARNESS),
]
TIMEOUT = 300


def run_journey(script, harness, jsdom):
    server = subprocess.Popen([sys.executable, "-m", harness, str(TIMEOUT)], cwd=ROOT,
                              stdout=subprocess.PIPE, text=True)
    try:
        port = server.stdout.readline().strip()
        if not port.isdigit():
            print("FAIL %s : le serveur de test n'a pas démarré" % script)
            return False
        result = subprocess.run(["node", os.path.join("tests", script), port, jsdom], cwd=ROOT,
                                timeout=TIMEOUT)
        return result.returncode == 0
    finally:
        server.kill()
        server.wait()


def main():
    jsdom = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("JSDOM_PATH", "jsdom")
    failed = []
    for script, harness in JOURNEYS:
        print("== " + script, flush=True)
        if not run_journey(script, harness, jsdom):
            failed.append(script)
    print("Parcours en échec : " + ", ".join(failed) if failed else "Tous les parcours sont OK")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
