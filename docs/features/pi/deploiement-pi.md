# Déploiement du Pi (archive, mise à jour, retour arrière, Pi neuf) (Pi)

## Ce que ça fait
- `build_archive.py` : `dist/pi-media-<version>.tar.gz` (pimedia, web, i18n, themes, launcher*, subsonic-web, deploy/pi ; exclut
  `.env`, `*.db`, `webapp`) ; `push.sh` : archive + scp + `deploy.sh` ; `deploy.sh` : `releases/<version>`, lien `current`, 3 versions gardées,
  bascule atomique, vérification `/health` sous 20 s, retrait d'une version défectueuse, `--rollback`, `--status`, `--configure` ;
  `install.sh` : Pi neuf en 8 étapes (arm64 exigé, sans sudo) ; `set-subsonic.sh`, `set-podcastindex.sh`, `migration.sh` ;
  `pimedia/cli.py` (set/show/migrate du `.env`, secrets masqués).
- `deploy.sh --start` : (re)démarre la version active. `PI_MEDIA_SERVICE=direct` (conteneur de test seulement) : pas de
  systemd, `deploy.sh` arrête et lance le serveur lui-même, journal dans `server.log`.
- **Essai sur le poste** (26/10/2026) : image `docker/pi/` (Debian bookworm, utilisateur `pi`, vrai mpv avec sortie nulle),
  archive fabriquée par `build_archive.py` et installée par `deploy.sh` au démarrage ; services `pi` (vrai Subsonic,
  port 8399) et `pi-demo` (faux Subsonic `tests/demo_subsonic.py`, port 8499) ; `docker/pi/push.sh` répète `push.sh`
  vers le conteneur. Voir `docs/DEPLOIEMENT.md`.
- Voir `docs/DEPLOIEMENT.md` et `docs/architecture/`.

## Où
`deploy/pi/` (`build_archive.py`, `push.sh`, `deploy.sh`, `install.sh`, `bin/`, `system/`, `systemd/`) ; essai sur le
poste : `docker/pi/` (`Dockerfile`, `entrypoint.sh`, `push.sh`), services `pi`, `pi-demo`, `pi-subsonic` de `compose.yaml`.

## Tests
**Aucun test automatique** pour `deploy.sh`, `install.sh`, `build_archive.py`, `cli.py`.
Essayé à la main dans le conteneur (26/10/2026) : premier déploiement, mise à jour par `docker/pi/push.sh`, redémarrage
du conteneur (version gardée), `--rollback`, `--status`, `/health`.

## N'existe pas / pas vérifié
- **`install.sh` sur un Pi neuf et le retour arrière sur le vrai Pi (systemd) : non vérifiés.** Le retour arrière ne
  l'est que dans le conteneur (mode direct, sans systemd).
- Pas vérifiés dans le conteneur : `deploy.sh --configure` (saisie du compte), le retour automatique quand une nouvelle
  version ne répond pas, le vrai Subsonic avec le compte du Pi (pas de `PI_SUBSONIC_USER` dans le `.env` de test).
