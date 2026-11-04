# Étoiles, cœur et commentaires d'album (site web)

## Ce que ça fait
- **Étoiles 1–5** lues et écrites **dans Subsonic** (`setRating`, compte de la personne), rien en base locale. Subsonic
  d'origine note le **dossier** de l'album (`parent` des titres ; album en plusieurs disques : dossier parent). Moyenne de
  tous les comptes (`averageRating`) affichée. Droit `comment` requis pour noter.
- **Cœur** (`star`/`unstar`) sur un album, un artiste ou un titre.
- **Commentaires** sous chaque album : fil de discussion du site (table `chat_messages`, sujet `album:<id>`), avec les
  mêmes fonctions que le salon (réponses, réactions, mentions…). **Pas** le chat de Subsonic (volontairement séparé).

## Où
`pimedia/webapp/ratings.py`, `chat.py`, `storage/messages.py` ; page : `stars.js`, `chat.js` (`ChatThread`).

## Tests
`tests/test_webapp.py`, `tests/e2e_webapp.js` (note de bob ≠ note d'alice, moyenne 4).

## N'existe pas / pas vérifié
- Aucune note sur un titre seul (Subsonic d'origine ne note que le dossier).
- Pas vérifié sur le vrai Subsonic : notes posées sur le dossier d'un album en plusieurs disques.
