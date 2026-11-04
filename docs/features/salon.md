# Salon de discussion en temps réel (site web)

## Ce que ça fait
Panneau à droite (bouton « Salon », touche C). Messages en temps réel (SSE, `/api/events`) : réponses, **@mentions**
(notification du navigateur si réglée), réactions emoji, modification, suppression (auteur ou administrateur Subsonic),
partage d'un album (carte cliquable), recherche, onglet Mentions, non-lus (badge), « écrit… », liste des personnes en
ligne, anti-spam. Reconnexion automatique avec message. Données dans `webapp.db`.

**Le plus récent en bas, et il reste en vue** (27/10/2026, demandé : un message d'un client arrivé sous le sien n'avait
pas été vu). Quand on est sur les derniers messages, on y reste même si la zone change de taille (« Écouté en ce moment »
qui apparaît au-dessus, saisie sur plusieurs lignes, panneau rouvert), si une image finit de se charger (pochette d'un
album partagé) ou si un message est modifié (`ChatThread.stuck`, `keepLatest`, `ResizeObserver`). Remonté dans la
discussion, on n'est pas dérangé : le bouton « Derniers messages (N) » compte ce qui arrive.

**Mis de côté : « le plus récent en haut »** (écrit et testé le 27/10/2026, pas activé). Le salon s'affiche du plus
récent au plus ancien, la saisie au-dessus des messages, les anciens se chargent en bas. Pour l'activer :
`ChatThread.NEWEST_FIRST_IN_ROOM = true` dans `chat.js` (rien d'autre : CSS `.newest-first` prête, parcours
`e2e_webapp.js` qui lit ce réglage ; vérifié qu'il passe dans les deux cas). Les commentaires d'album restent dans
l'ordre de lecture.

## Où
`pimedia/webapp/chat.py`, `events.py`, `controllers/chat.py`, `storage/messages.py` ; page : `web-pc/static/js/chat.js`,
`events.js`, `css/chat.css`.

## Tests
`tests/test_webapp.py` (service et HTTP), `tests/e2e_webapp.js` (flux temps réel, mentions, réactions, côté du plus
récent). « Reste en vue » : essayé dans le navigateur intégré de Claude (site de démo : zone passée de 451 à 346 px quand
« Écouté en ce moment » apparaît, dernier message toujours visible) ; jsdom ne calcule pas les tailles.

## N'existe pas / pas vérifié
- Photos de profil dans le salon : les initiales colorées sont utilisées (le serveur sait servir les photos, pas encore la page).
- Fermer le salon ou régler sa largeur : fermeture possible (réglage), **largeur non réglable**.
- Pas de messages privés, pas de salons multiples (un salon global + un fil par album).
