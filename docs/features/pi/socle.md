# Socle commun : réglages, textes, base (Pi)

## Ce que ça fait
- `storage/database.py` (SQLite + migrations, une liste par édition), `settings.py` (variables `PI_MEDIA_*`, `.env`, table
  `app_settings`), `envfile.py`, `i18n.py` + `i18n/fr.yaml`, import des anciens `config.json`, `paths.py`.
- **Partagé avec le site web** pour la base, le `.env` et les textes : voir `docs/architecture/`.

## Où
`pimedia/storage/`, `settings.py`, `envfile.py`, `i18n.py`, `paths.py`.

## Tests
`tests/test_storage.py` (11), `tests/test_pi_mode.py`, `tests/test_units.py`.

## N'existe pas / pas vérifié
- Une seule langue (français).
