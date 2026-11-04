# Comptes, connexion et droits (site web)

## Ce que ça fait, de A à Z
1. La personne se connecte avec **son compte Subsonic** (`POST /api/login`). Le site ne garde **jamais le mot de passe** :
   seulement le jeton Subsonic (`md5(mot de passe + sel)`) et le sel, dans `users`. Ce jeton sert ensuite à parler à
   Subsonic au nom de la personne (et, pour les playlists communautaires et le scan, au nom d'un autre : voir `playlists.md`).
2. Un cookie de session (`pmw_session`, hash sha256 en base, 30 jours) la reconnaît. Toutes les routes `/api` demandent une
   session ; les écritures demandent en plus l'en-tête `X-Requested-With: pmw` (protection CSRF). Essais de connexion limités : 8 échecs en 10 minutes par adresse (`LoginThrottle`, `accounts.py`). Derrière un proxy (`WEB_TRUST_PROXY=true`, réglé par défaut dans `compose.yaml`), l'adresse est la dernière de `X-Forwarded-For`, celle qu'ajoute le proxy (`client_address`, `controllers/base.py`) ; sinon toutes les personnes auraient l'adresse du proxy.
   **Mot de passe oublié** (31/10/2026, version 1.6) : un lien sous le bouton de connexion déplie une explication
   (`auth.forgot_help`) : l'administrateur réinitialise le mot de passe dans Subsonic. Rien n'est envoyé au serveur.
3. Les **droits du compte Subsonic** (`getUser`) sont lus à la connexion puis à chaque page (`/api/me`) : un changement
   fait dans Subsonic s'applique sans se reconnecter ; si Subsonic ne répond pas, on garde les derniers connus
   (`users.roles`, migration 6).
4. Réglages par personne (`/api/preferences`) : barre à gauche (fixe/survol/masquée), largeur, densité, salon ouvert/fermé,
   grille d'albums, compteurs d'albums, notifications de mentions, onglet de la barre (`sidebar_tab`).
5. **Réglages rapides** (roue dentée en haut, gardée) : affichage (barre, largeur en px, salon, densité, pochettes,
   notifications), liste « Votre compte Subsonic permet de… » et lien vers « Mon compte ».
6. **Page « Mon compte »** (`#/account`, 27/10/2026), ouverte par **sa photo et son nom en haut à droite** (ou depuis les
   réglages rapides), en cartes :
   - **Photo de profil** : d'où vient la photo (`GET /api/account` : `source` = `site`, `subsonic` ou rien) ;
     « Choisir une image… » (recadrée au centre en carré de 256 px et convertie en JPEG **par le navigateur**, envoyée en
     `data:` à `POST /api/avatar/upload`) ; **Gravatar** : le site **copie** la photo de gravatar.com
     (`POST /api/avatar/gravatar {email}`, SHA-256 de l'adresse, `d=404`), adresse du compte Subsonic (`getUser`)
     si le champ reste vide ; une copie, donc un changement fait plus tard sur Gravatar demande de recommencer, et les
     navigateurs ne contactent jamais Gravatar (politique de sécurité inchangée). « Retirer la photo du site » : la photo
     choisie dans Subsonic (`getAvatar`) revient, sinon l'initiale.
   - **Affichage** : les mêmes réglages que la roue dentée (`Dialogs.display`).
   - **Droits** du compte Subsonic.
   - **Last.fm et mot de passe** : gérés par Subsonic, bouton vers `SUBSONIC_PUBLIC_URL/personalSettings.view`
     (nouvel onglet). `SUBSONIC_PUBLIC_URL` (`.env`) : adresse de Subsonic vue par les personnes, à régler quand
     `SUBSONIC_URL` est interne (prod : `http://subsonic:4040`) ; vide = `SUBSONIC_URL`.
   - **Importer depuis YouTube ou SoundCloud** : le même champ « coller un lien » que la page Favoris
     (`ExtMusic.linkForm`), les titres vont dans Favoris → « D'ailleurs ».
7. **Photos partout** (`web-pc/static/js/avatars.js`) : initiale en couleur recouverte par la photo, en haut, dans le
   salon et dans « Écouté en ce moment ». `GET /api/avatars` donne une version par personne **qui a une photo** (sur le
   site : date d'envoi ; Subsonic : « s » + empreinte de l'image, relue au plus toutes les heures) : la page ne demande
   l'image que pour elles, relit la liste toutes les 10 minutes et tout de suite après un changement de sa photo.

## Droits appliqués
| Droit Subsonic | Effet sur le site |
|---|---|
| `stream` | écouter |
| `download` | télécharger un album (zip) ou un titre |
| `playlist` | créer, modifier, supprimer des playlists ; y ajouter |
| `comment` | étoiles et commentaires d'album (le salon reste libre) |
| `scrobble` | le lecteur signale les écoutes |
| `upload` | page « Envoyer » |
| `admin` | modérer le salon ; scan Subsonic avec ce compte |

## Où
`pimedia/webapp/accounts.py`, `controllers/auth.py`, `controllers/base.py` (`Guard.reader/writer/raw_writer`),
`entities.py` (`User`, `SUBSONIC_ROLES`), `preferences.py`, `storage/users.py`, `schema.py` (migrations 1 et 6) ;
photos : `avatars.py` (`Avatars`, `Gravatar`), `storage/avatars.py` (migration 2), `controllers/profile.py` ;
page : `web-pc/static/js/app.js`, `dialogs.js`, `account.js`, `avatars.js`, `core.js` (`App.can`).

## Tests
`tests/test_webapp.py` (dont `BehindProxyHttpTest` : limite par personne derrière le proxy), `tests/test_webapp_roles.py`,
`tests/test_webapp_music.py` (`ProfileHttpTest` : photos, versions, Gravatar, `/api/account` ; `GravatarTest`), parcours
`tests/e2e_webapp.js` (connexion, mauvais mot de passe ; Mon compte : photo Subsonic en haut et dans le salon, réglages
rapides gardés, Gravatar sans adresse puis copié, photo retirée). Faux Gravatar : `tests/webapp_support.py`.
**Vérifié dans Chromium** (démo, 27/10/2026) : envoi d'une image (recadrée en 256 px), vrai gravatar.com (adresse sans
photo : refus expliqué ; adresse avec photo : copiée), photo en haut et dans le salon.

## N'existe pas / pas vérifié
- Réinitialisation automatique du mot de passe : **pas faite**. L'API Subsonic n'a pas de « mot de passe oublié » ;
  il faudrait un compte administrateur Subsonic dans le `.env` (pour `changePassword`), un envoi de mail (SMTP) et des
  jetons à usage unique en base. `changePassword` en administrateur n'a pas été vérifié sur le Subsonic de production.
- Inscription : il n'y a pas de création de compte, tout passe par Subsonic.
- Droits `coverArt` (tags ID3), `share` (liens publics), `settings` : lus mais **aucune fonction ne les utilise** (le lien
  vers les réglages Subsonic est montré à tous ; Subsonic refuse lui-même si le droit manque).
- Pas de connexion à un compte YouTube ou SoundCloud (« J'aime » privés) : demande OAuth Google (mode test : 100 personnes
  inscrites à la main, reconnexion chaque semaine) et une appli SoundCloud (inscriptions restreintes) : pas fait.
- Envoi d'image : pas testé dans jsdom (pas de canvas), seulement dans Chromium. Une image GIF animée devient fixe.
- Gravatar : la photo n'est pas relue toute seule si elle change sur gravatar.com.
- Prod : `SUBSONIC_PUBLIC_URL` à ajouter dans le `.env` du serveur (`https://music.foos.fr`), sinon le bouton Last.fm
  pointe sur `http://subsonic:4040`.
- Droits `podcast`, `jukebox`, `videoConversion` : sans objet sur le site.
- Pas vérifié : un compte non administrateur réel (testé seulement avec le faux Subsonic).
