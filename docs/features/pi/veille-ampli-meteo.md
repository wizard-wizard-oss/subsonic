# Météo, horloge, égaliseur, écran de veille et veille de l'ampli (Pi)

## Ce que ça fait
- Météo Open-Meteo (sans clé, toutes les 15 min, garde l'ancien bulletin en cas d'échec).
- Écran de veille = horloge + météo + égaliseur après `SCREENSAVER_SECONDS` (120 s), réveillé par tout toucher (`/dev/input`) ;
  peut passer par-dessus Feishin/Chromium ; boutons de volume dessus.
- Égaliseur à segments par FFT (numpy) sur le moniteur de la sortie : n'écoute que si un flux joue. Sans numpy : pas d'égaliseur,
  le reste marche. Outil `src/diagnostic-veille.py` (quel périphérique d'entrée empêche la veille).

## Où
`pimedia/menu/weather.py`, `idle.py`, `spectrum.py`, `system.py` ; `pimedia/server/playback.py` (libération de mpv) ;
`src/diagnostic-veille.py` (écran de veille) et `src/diagnostic-ampli.py` (veille de l'ampli).

## Tests
`tests/test_menu.py` (météo, spectre, veille, volume) ; `tests/test_playback.py` (`AudioReleaseTest` avec le faux mpv, verdicts de
`diagnostic-ampli.py`). Aucun test de `diagnostic-veille.py`. Note : `diagnostic-veille.py` concerne l'écran, pas l'ampli.

## N'existe pas / pas vérifié
- **Veille de l'ampli : correctif écrit, PAS vérifié sur le vrai Pi.** Cause la plus probable (non mesurée) : le mpv de la
  lecture haute fidélité reste lancé ; en pause son flux est « corked » mais **ouvert** vers le DAC, et à l'arrêt rien ne garantit
  qu'il rende la carte. Le correctif ne dépend pas de ce qu'mpv fait de son flux : après 30 s de pause (ou de file vide)
  `HifiPlayer.release_if_idle` (vérifié toutes les 5 s) **arrête le processus mpv** → la carte est rendue pour de bon. À la reprise
  (lecture, déplacement dans le titre) mpv redémarre, recharge le titre en pause, se replace à la seconde gardée, remet le volume,
  re-précharge le titre suivant, puis joue. Pendant la lecture, rien ne change. Coût : ~0,5 à 1 s au redémarrage après 30 s de
  pause ; l'ampli, lui, met quelques secondes à se réveiller et peut couper le tout début du titre (à constater).
  Les radios du menu (mpv lancé puis tué à l'arrêt) et l'égaliseur (ne lit le moniteur que si un flux joue) étaient déjà corrects.
- **Hypothèses restantes si ça ne suffit pas** (les départager avec `python3 diagnostic-ampli.py`, pause lancée) :
  1. Chromium (lecteur sans haute fidélité) garde un flux ouvert → le diagnostic le nomme dans « flux » ; réponse : activer la
     haute fidélité, ou ajuster `session.suspend-timeout-seconds` dans WirePlumber (non touché : réglage par défaut = 5 s).
  2. Un enregistreur (`parec` de l'égaliseur resté lancé) → « enregistreurs » > 0.
  3. Rien n'ouvre de flux mais la carte reste ouverte → PipeWire/WirePlumber ne suspend pas la sortie USB (`wpctl status`, `pw-top`).
  4. L'ampli ne dort pas lui-même (minuterie, entrée active) alors que la carte est fermée : le diagnostic dit « OK » ; régler l'ampli.
  Commandes à la main : `pactl list short sinks` (RUNNING/IDLE/SUSPENDED), `pactl list sink-inputs | grep -E "Sink Input|Corked|application.name"`,
  `pw-top`, `cat /proc/asound/card*/pcm*p/sub0/status` (« closed » = carte fermée).
