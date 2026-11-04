#!/usr/bin/env python3
"""Point d'entrée de l'édition PC (site pour plusieurs utilisateurs d'un serveur Subsonic).

Réglages : .env du dossier de données (~/.local/share/pimedia-web/.env par défaut, ou PI_MEDIA_WEB_DATA) :
    SUBSONIC_URL=https://musique.exemple.fr
    WEB_PORT=8200        WEB_BIND=127.0.0.1        WEB_SECURE_COOKIE=true   (site servi en HTTPS)
"""
import os
import sys

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE_DIR)

from pimedia.webapp.app import WebApplication  # noqa: E402

if __name__ == "__main__":
    WebApplication(CODE_DIR).run()
