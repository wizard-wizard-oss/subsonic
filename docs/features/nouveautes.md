# Nouveautés : la page qui explique le site aux utilisateurs (site web)

## Ce que ça fait
Page **« Nouveautés »** (`#/whatsnew`, lien dans le menu du haut), écrite **pour les personnes qui utilisent le site**,
pas pour les développeurs, sur un ton léger : le principe (Subsonic reste la maison de la musique, le site ajoute le
reste, sans contourner YouTube), puis six parties en cartes : Ensemble (salon, écouté en ce moment, commentaires,
Actualité et flux RSS), Se perdre dans la musique (mix, créateur, radio sur 4 niveaux, similaires, accueil), Playlists
(glisser-déposer, communautaires, partagées, titres d'ailleurs), YouTube/Jamendo/SoundCloud (recherche, quota d'une
centaine de recherches par jour, vidéo refusée, import par lien, « J'aime » privés, petits caractères), Les petits plus
(karaoké des paroles synchronisées, file, raccourcis, télécharger/envoyer), Qui garde quoi. Certaines cartes ont un
lien « J'y vais ». En haut, un lien vers la page « Versions » (`docs/features/versions.md`).

**À tenir à jour** quand une fonctionnalité visible change : les textes sont dans `i18n/fr.yaml` (section `whatsnew`).

## Où
`web-pc/static/js/whatsnew.js` (ordre des parties et des cartes, icônes, liens), `i18n/fr.yaml` (`webapp.whatsnew`,
`nav.whatsnew`), `web-pc/static/css/views.css` (`.whatsnew-*`), route dans `app.js`, lien dans `index.html`.

## Tests
`tests/e2e_webapp.js` : page et lien du menu, six parties et 27 cartes, aucun texte manquant, quota expliqué,
playlists (glisser-déposer, communautaires, partagées), lien vers Mix.

## N'existe pas
- Pas de pastille sur le lien « Nouveautés » : ce qui est nouveau depuis la dernière visite est signalé par la page
  « Versions » (numéro et pastille à côté du titre du site).
