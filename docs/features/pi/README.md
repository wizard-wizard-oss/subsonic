# Fonctionnalités du Pi

Inventaire fait **d'après le code** le 25/10/2026 (lecture seule ; les tests n'ont pas été relancés pour cet inventaire).
**Rien de cela n'est vérifié sur le vrai Pi** : tous les tests Pi tournent avec des faux (faux Subsonic, faux mpv, faux Tk, jsdom).
Les chemins sont relatifs à `src/` sauf `deploy/` et `tests/`. Format des fiches : voir `../README.md`.

| Fiche | Fonctionnalité |
|---|---|
| [relais-subsonic](relais-subsonic.md) | Relais Subsonic, cache et classement par dossiers |
| [interface-tactile](interface-tactile.md) | Interface web tactile : navigation, accueil, albums, artistes, recherche, clavier |
| [lecteur-et-file](lecteur-et-file.md) | Lecture et file d'attente (page) |
| [haute-fidelite](haute-fidelite.md) | Haute fidélité (mpv) |
| [mixes-radios](mixes-radios.md) | Mixes, radios et créateur de mix (page) |
| [radios-internet](radios-internet.md) | Radios Internet |
| [podcasts](podcasts.md) | Podcasts |
| [musique-ailleurs](musique-ailleurs.md) | Musique d'ailleurs : Jamendo et YouTube |
| [playlists-favoris](playlists-favoris.md) | Playlists (Subsonic et locales) et favoris |
| [paroles-anecdotes](paroles-anecdotes.md) | Paroles et anecdotes |
| [telephone](telephone.md) | Saisie et envoi depuis le téléphone (QR code) |
| [invites-airplay-bluetooth](invites-airplay-bluetooth.md) | Invités AirPlay / Bluetooth (passage de main) et installation système |
| [menu-tk](menu-tk.md) | Menu Tk de démarrage |
| [veille-ampli-meteo](veille-ampli-meteo.md) | Météo, horloge, égaliseur, écran de veille et veille de l'ampli |
| [sortie-audio-extinction](sortie-audio-extinction.md) | Sortie audio HDMI/USB, volume, Éteindre / Redémarrer |
| [historique-recherche](historique-recherche.md) | Historique de recherche |
| [deploiement-pi](deploiement-pi.md) | Déploiement du Pi (archive, mise à jour, retour arrière, Pi neuf) |
| [socle](socle.md) | Socle commun : réglages, textes, base |

## Manques à retenir
- **Sans aucun test** : mixes/radios et créateur de mix (page), onglets Accueil/Albums/Artistes/Favoris/Radios/Playlists Subsonic,
  `/info/*` (paroles/anecdotes), `deploy.sh` / `install.sh` / `build_archive.py` / `cli.py`, scripts système (AirPlay, Bluetooth,
  HDMI, autorisations), `diagnostic-veille.py`.
- **Table sans code** : `play_history`.
- **Ouvert** : l'ampli ne se met jamais en veille (`veille-ampli-meteo.md`).
