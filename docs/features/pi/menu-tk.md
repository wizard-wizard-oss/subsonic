# Menu Tk de démarrage (Pi)

## Ce que ça fait
- `launcher.py` → `pimedia/menu/main.py` + `ui.py` : Tk plein écran 800×480, thème `themes/retro.yaml`. Accueil : horloge, date,
  météo, égaliseur, 6 tuiles (Musique = Chromium kiosque sur la page web, YouTube = FreeTube, Radio, Podcasts, Bluetooth, Horloge).
- Pied de page : titre en cours (MPRIS), volume, Éteindre / Redémarrer avec confirmation dans la fenêtre, bouton Bureau.
- Une seule appli à la fois ; le menu se cache puis revient. Si le nouveau menu plante au démarrage : repli sur
  `launcher_classic.py` (797 lignes, « ne plus modifier »), erreur notée dans `menu-erreur.log`.
- Réglages : `DEVICE_NAME`, `WEATHER_*`, `SCREENSAVER_SECONDS`, `WEB_URL`, `THEME`. Textes en français seulement.

## Où
`src/launcher.py`, `launcher_classic.py`, `pimedia/menu/`, `themes/`, `deploy/pi/system/40-bureau.sh`.

## Tests
`tests/test_menu.py` (45, faux Tk `tests/fake_tk.py`).

## N'existe pas / pas vérifié
- **Nouveau menu Tk sur le Pi : non vérifié.**
- Feishin et Supersonic sont installés par `20-applis.sh` mais **aucune tuile du nouveau menu ne les lance**.
