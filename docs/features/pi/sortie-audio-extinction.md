# Sortie audio HDMI/USB, volume, Éteindre / Redémarrer (Pi)

## Ce que ça fait
- `set-hdmi-audio.sh` (au démarrage de labwc) : sortie par défaut USB sinon HDMI, volume 100 %, surcharge par
  `~/.local/share/pi-media/hdmi-sink`. `50-son.sh` : PipeWire autorise 44,1 / 48 / 88,2 / 96 kHz.
- Volume : boutons +/- 5 de la page (écran local, plafonné à 100 %) et du menu.
- Éteindre / Redémarrer : `systemctl` puis `sudo -n systemctl` (règle sudoers limitée à `poweroff`/`reboot`, `80-autorisations.sh`),
  confirmation dans la fenêtre, message « refusé » en cas d'échec.

## Où
`deploy/pi/bin/set-hdmi-audio.sh`, `deploy/pi/system/50-son.sh`, `80-autorisations.sh` ; `pimedia/menu/audio.py`, `system.py` (`Power`).

## Tests
`tests/test_menu.py` (volume, Éteindre : systemctl puis sudo, refus, confirmation). Aucun test des scripts shell.

## N'existe pas / pas vérifié
- **Non vérifié sur le vrai Pi** (scripts, bouton Éteindre).
- Pas de choix de la sortie dans l'interface. **192 kHz non permis** (max 96000 dans `50-son.sh`) : à noter si l'ampli le supporte.
