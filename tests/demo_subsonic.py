"""Faux Subsonic de démonstration seul (bibliothèque inventée de demo_webapp), pour l'édition Pi en conteneur
(service « pi-subsonic » de compose.yaml). Compte : alice / secret.
Usage : python3 -m tests.demo_subsonic [secondes]
Adresse et port : PI_MEDIA_DEMO_BIND (127.0.0.1 par défaut), PI_MEDIA_DEMO_PORT (4040 par défaut)."""
import os
import sys
import time

from tests.demo_webapp import start_demo_subsonic


def main():
    address = (os.environ.get("PI_MEDIA_DEMO_BIND", "127.0.0.1"), int(os.environ.get("PI_MEDIA_DEMO_PORT", "4040")))
    fake = start_demo_subsonic(address)
    print("Faux Subsonic de démonstration sur %s:%d" % (address[0], fake.port), flush=True)
    time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 31536000)


if __name__ == "__main__":
    main()
