# Pi Media Station

Musique d'un serveur **Subsonic** (API standard 1.16.1, pas Navidrome), en deux éditions séparées qui partagent un
socle commun, sans aucun `if serveur` dans le code :

- **Pi** : station sur Raspberry Pi (écran tactile 7", ampli USB) — menu tactile, page web, podcasts, radios,
  AirPlay/Bluetooth, lecture haute fidélité par mpv, file partagée avec les téléphones. Un seul utilisateur.
- **PC** : site pour tous les utilisateurs d'un serveur Subsonic — connexion avec son compte, barre des artistes,
  étoiles et favoris envoyés à Subsonic, salon en temps réel, commentaires sous les albums. Se lance avec Docker.

À lire avant de coder : `docs/ETAT.md` (où en est le projet), `docs/CONVENTIONS.md` (règles).
Pour déployer (site et Pi) : `docs/DEPLOIEMENT.md`. Architecture et partage du code : `docs/architecture/`. Fonctionnalités détaillées : `docs/features/`.

## Organisation

| Dossier | Rôle |
|---|---|
| `src/` | tout le code de l'application (voir ci-dessous) |
| `tests/` | unitaires, intégration (faux Subsonic, faux mpv), parcours navigateur jsdom, démonstration |
| `docker/` | une image par usage : `web/` (site PC), `tests/` (tests et démonstration), `pi/` (édition Pi sur le poste de développement) |
| `deploy/pi/` | Pi : fabrication de l'archive, `install.sh` (Pi neuf), `deploy.sh` (mises à jour), étapes système |
| `deploy/pc/` | PC sans Docker (service systemd) et exemples de proxy HTTPS (Apache, nginx) |
| `docs/` | état du projet, conventions |
| `archive/` | anciennes versions, pour mémoire (jamais livrées) |

Dans `src/` :

| Chemin | Rôle |
|---|---|
| `pimedia/shared/` | classes communes aux deux éditions, sans dépendance vers l'une ou l'autre (paroles, MusicBrainz…) |
| `pimedia/storage/`, `envfile.py`, `i18n.py`, `settings.py` | socle commun : base SQLite et migrations, réglages, textes |
| `pimedia/server/`, `pimedia/menu/`, `web/`, `subsonic-web.py`, `launcher*.py` | édition Pi |
| `pimedia/webapp/`, `web-pc/`, `pimedia-web.py` | édition PC |
| `i18n/fr.yaml`, `themes/` | tous les textes (clés anglaises), thèmes du menu |

Dans chaque édition, les couches sont séparées : dépôts (SQL seulement) → services (règles) → contrôleurs (HTTP
seulement), assemblés à un seul endroit (`app.py`).

## Commandes

```bash
docker compose run --rm tests                     # tous les tests, sans rien installer d'autre que Docker
docker compose up -d web                          # site PC sur 127.0.0.1:8200 (SUBSONIC_URL dans .env)
docker compose --profile demo up demo             # site PC de démonstration sur 127.0.0.1:8300
docker compose --profile pi up --build pi         # édition Pi (page web, sans le matériel) sur 127.0.0.1:8399, Subsonic du .env
docker compose --profile pi-demo up --build pi-demo   # la même avec le faux Subsonic de démonstration, sur 127.0.0.1:8499
python3 -m unittest discover -s tests -t .        # tests sans Docker (pip install -r requirements.txt)
python3 deploy/pi/build_archive.py                # dist/ : archive du Pi + install.sh + deploy.sh + migration.sh
bash deploy/pc/push.sh utilisateur@serveur         # met à jour le site sur le serveur (copie + docker compose up -d --build web)
bash deploy/pi/push.sh pi@adresse-du-pi           # fabrique l'archive du Pi, l'envoie et l'installe
bash docker/pi/push.sh                            # la même chose vers le conteneur « pi » (répéter une mise à jour)
```

Sur le Pi : `bash install.sh` (Pi neuf), `bash deploy.sh pi-media-<version>.tar.gz` (mise à jour),
`bash deploy.sh --rollback | --status | --start`. Réglages : `deploy/pi/env.example` → `~/.local/share/pi-media/.env`.

L'édition Pi en conteneur (`docker/pi/`) sert à essayer la page web et le chemin de mise à jour (`deploy.sh`) sur le Mac
avant d'envoyer sur le Pi. **Pas dans le conteneur** : menu tactile Tk, écran, son (mpv joue dans le vide), Bluetooth,
AirPlay, bouton Éteindre. Détails : `docs/DEPLOIEMENT.md`, « Essayer l'édition Pi sur le poste ».

## Tester en local derrière Traefik

Le `.env` de test ajoute `compose.traefik.yaml` (`COMPOSE_FILE=compose.yaml:compose.traefik.yaml`) : le site est
servi par le Traefik déjà lancé sur le poste (réseau `proxy`, HTTPS sur `websecure`) à
`https://pimedia.localhost`, la démonstration à `https://demo.pimedia.localhost`, l'édition Pi à
`https://pi.pimedia.localhost` (et `https://pi-demo.pimedia.localhost`). Le port direct reste ouvert.

## Mettre le site PC sur le serveur

1. `cp .env.example .env`, y mettre `SUBSONIC_URL`, `WEB_SECURE_COOKIE=true`, `WEB_TRUST_PROXY=true` ; Subsonic dans un
   conteneur : `COMPOSE_FILE=compose.yaml:compose.subsonic.yaml` (le site rejoint son réseau Docker), jamais Traefik en prod.
2. `bash deploy/pc/push.sh music@serveur` : le site écoute sur `127.0.0.1:8200`, données dans le volume `pimedia_web-data`.
3. Apache en HTTPS devant : `deploy/pc/apache-exemple.conf`. Détails : `docs/DEPLOIEMENT.md`.
