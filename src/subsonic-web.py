#!/usr/bin/env python3
"""Point d'entrée du serveur (relais Subsonic, interface web, podcasts, lecture haute fidélité).

Code : paquet « pimedia » (assemblage dans pimedia/server/app.py).
Réglages d'installation et secrets : fichier .env du dossier de données (voir .env.example) ;
réglages modifiés depuis l'application et données : base pi-media.db du même dossier.
"""
import os
import sys

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE_DIR)

from pimedia.server.app import Application  # noqa: E402


def main():
    Application(CODE_DIR).run()


if __name__ == "__main__":
    main()
