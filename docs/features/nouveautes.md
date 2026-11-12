# Nouveautés : la page qui explique le site aux utilisateurs (site web)

## Ce que ça fait
Page **« Nouveautés »** (`#/whatsnew`, lien dans le menu du haut), écrite **pour les personnes qui utilisent le site**,
pas pour les développeurs, sur un ton léger : le principe (Subsonic reste la maison de la musique, le site ajoute le
reste), puis six parties et 34 cartes :

- Ensemble : salon, écouté en ce moment, commentaires, conseils à un autre membre, Actualités et flux RSS.
- Se perdre dans la musique : mix, créateur avec profondeur de 1 à 4 et sélection bornée aux artistes et styles
  retenus, radios d'artiste et de titre, similaires, accueil et chiffres de la collection quand disponibles,
  discographies Discogs avec choix mémorisé, crédits et relations Discogs/MusicBrainz, découverte et Top des labels
  avec versions YouTube au choix, marque-pages dans « À écouter ».
- Playlists : glisser-déposer, communautaires, partagées, titres d'ailleurs, import avec choix dans un export Apple
  contenant plusieurs playlists.
- YouTube/Jamendo/SoundCloud : recherche, limite de 120 recherches YouTube par heure et par personne, vidéo refusée,
  import par lien, « J'aime » privés, petits caractères.
- Les petits plus : paroles synchronisées, file et lecture juste après, raccourcis, télécharger/envoyer,
  changement de pochette selon les droits du compte.
- Qui garde quoi : données Subsonic et données du site, dont marque-pages, recommandations et choix Discogs.

Certaines cartes ont un lien « J'y vais », notamment les marque-pages et recommandations vers `#/listen-later`.
En haut, un lien vers la page « Versions » (`docs/features/versions.md`).

**À tenir à jour** quand une fonctionnalité visible change : les textes sont dans `i18n/fr.yaml` (section `whatsnew`).
Complétée le 10/11/2026 avec les fonctionnalités déjà présentes dans le code, y compris « À écouter » (1.9 encore
locale). À la demande de l'utilisateur, ce complément éditorial n'ajoute aucune version à l'historique.

## Où
`web-pc/static/js/whatsnew.js` (ordre des parties et des cartes, icônes, liens), `i18n/fr.yaml` (`webapp.whatsnew`,
`nav.whatsnew`), `web-pc/static/css/views.css` (`.whatsnew-*`), route dans `app.js`, lien dans `index.html`.

## Tests
`tests/e2e_webapp.js` : page et lien du menu, six parties et 34 cartes, aucun texte manquant, quota expliqué,
playlists (glisser-déposer, communautaires, partagées), lien vers Mix.

## N'existe pas
- Pas de pastille sur le lien « Nouveautés » : ce qui est nouveau depuis la dernière visite est signalé par la page
  « Versions » (numéro et pastille à côté du titre du site).
