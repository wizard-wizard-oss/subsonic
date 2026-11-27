# Notifications privées de l’administration (site web, 1.17)

## Pour les membres

La page **Notifications**, accessible dans le menu sous la photo du compte, affiche uniquement les messages destinés au compte
connecté. Chaque message comporte un objet, son texte et sa date. Une pastille indique le nombre de messages
non lus ; la photo du compte porte une pastille rouge, y compris sur téléphone et lorsque le menu est fermé. « Marquer comme lu » retire la pastille pour
ce message, qui reste consultable. L’ouverture de la page ne marque pas automatiquement tous les messages
comme lus. Les anciens messages se chargent par pages de 40. « Actualiser » relit la liste.

Les messages et la lecture sont conservés dans SQLite, après déconnexion et redémarrage. Le SSE existant
signale un changement uniquement au destinataire ; le compteur est relu à la connexion, au retour sur
l’onglet et après reconnexion. Une réponse tardive du compte précédent ne remplace pas son compteur.

## Pour les administrateurs

La même page présente « Envoyer une notification à un membre ». Choisir une personne déjà connectée au site,
rédiger l’objet (120 caractères maximum) et le message (2 000 caractères), puis envoyer. La confirmation
nomme le destinataire. Un membre ordinaire ne voit pas le formulaire et ne peut pas appeler la route d’envoi.
Les routes exigent une session ; les écritures exigent aussi l’en-tête CSRF. Les droits administrateur sont
ceux de Subsonic, relus par le parcours de compte existant.

Un identifiant de demande accompagne l’envoi : si la réponse se perd après l’enregistrement, réessayer ne
crée pas un second message. Le texte est rendu comme du texte, sans interprétation HTML. Un message peut
servir à prévenir d’un retrait de fichier, rappeler une règle ou expliquer un problème d’import.

## Modèle et responsabilités

Migration web 22 : table `notifications`, identifiant propre, administrateur émetteur, destinataire,
objet, texte, date de création, date de lecture et clé de dédoublonnage. Cette table est indépendante de
`upload_history` et `upload_albums` : elle ne change pas qui a envoyé un album et n’enregistre pas les
personnes qui modifient ses tags.

- Entités et limites : `pimedia/webapp/notification_entities.py`.
- SQL seulement : `storage/notifications.py`, renvoie des entités.
- Droits, validation, destinataire et événements : `notifications.py`.
- HTTP : `controllers/notifications.py`, assemblage dans `app.py`.
- Interface : `web-pc/static/js/notifications.js`, `static/css/notifications.css`.
- Temps réel : EventHub/LiveEvents existants, événement privé `notifications`.

Routes : `GET /api/notifications?before=…`, `GET /api/notifications/status`,
`GET /api/notifications/recipients` (administrateur), `POST /api/notifications/send` (administrateur),
`POST /api/notifications/read` (lecture limitée au destinataire).

## Validation et limites

Neuf tests Python couvrent confidentialité, droits, CSRF, persistance, lecture, validation, pagination,
reprises et migration depuis la 21. Le parcours jsdom dédié vérifie l’arrivée SSE, la pastille, le rendu
d’un texte contenant du HTML, la lecture, une erreur réseau, l’envoi par l’interface administrateur,
la réponse d’envoi perdue et le changement de compte. Les parcours PC général et mobile passent aussi.
Chrome vérifie les vues administrateur et destinataire à 1440, 390 et 320 px, clair/sombre, sans
surlargeur ni erreur JavaScript. La migration a été répétée sur la sauvegarde de production : contenu
des 26 tables existantes conservé, intégrité et clés étrangères valides.

Aucun e-mail, notification système du navigateur, envoi collectif, pièce jointe ou suivi de lecture
exposé aux administrateurs. Le mécanisme sert aux messages de service ; il ne crée pas une messagerie
privée générale. Les futurs envois audio seuls sont refusés avec une explication immédiate, sans produire
automatiquement une notification persistante supplémentaire.

## Mise en service

Version 1.17 publiée et vérifiée le 27/11/2026 sur https://music2.foos.fr. La notification n° 1 explique
à Mnu le retrait de son MP3 seul de Baston 3000 et la règle des albums ZIP. Message déposé via l’API
réelle avec la clé `upload-18-standalone-audio-removed`, non lu au moment du contrôle. Le compte
administrateur a été vérifié auprès de Subsonic ; la session technique temporaire a été supprimée.

## Menu sous la photo (1.18)

Un clic sur la photo ouvre Mon compte, Notifications et Se déconnecter. Le compteur détaillé reste dans
la ligne Notifications ; le point rouge sur la photo disparaît uniquement quand il n’y a plus de message
non lu. Le menu se ferme après un choix, un clic extérieur, une navigation ou Échap, qui rend le focus
à la photo. La photo reste visible dans l’en-tête mobile. Ouvrir le menu du compte ferme le volet artistes
ou salon mobile, et ouvrir un de ces volets ferme le menu du compte. Aucun changement des messages,
des droits ou des marqueurs de lecture. Composant `account-menu.js`, styles `account-menu.css`,
réutilisation des liens, de la déconnexion et du compteur existants.

Validation : 58 contrôles du composant mobile, parcours Notifications/PC/mobile et cinq tests de versions.
Chrome vérifie les menus fermés/ouverts, la pastille sur la photo, le clavier, les liens et une déconnexion
réelle sur données de test à 1440, 390, 320 px et 667×375 en paysage, clair/sombre, sans débordement
ni erreur JavaScript.

Version 1.18 publiée et vérifiée sur le site : menu sous la photo et ressources publiques conformes,
conteneur sain, base inchangée au schéma 22 et notification précédente à Mnu conservée.
