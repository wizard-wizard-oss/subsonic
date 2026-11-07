#!/usr/bin/env bash
# Met à jour le site (édition PC, Docker) sur un serveur : copie le code, puis reconstruit et relance le conteneur.
#
#   bash deploy/pc/push.sh utilisateur@serveur [dossier distant]     (dossier par défaut : ~/pimedia)
#
# Le .env du serveur n'est jamais touché ni écrasé. Les données (webapp.db) sont dans un volume Docker :
# une mise à jour les garde, et les migrations de la base s'appliquent toutes seules au démarrage.
# Premier déploiement : créer le .env sur le serveur à partir de .env.example avant de lancer ce script.
set -euo pipefail

TARGET="${1:?usage : bash deploy/pc/push.sh utilisateur@serveur [dossier distant]}"
REMOTE_DIR="${2:-pimedia}"
PROJECT="$(cd "$(dirname "$0")/../.." && pwd)"

# Page « Versions » du site : la version la plus récente est en tête de src/i18n/versions.yaml.
VERSIONS="$PROJECT/src/i18n/versions.yaml"
LATEST_VERSION="$(sed -n 's/^- version: "\(.*\)"$/\1/p' "$VERSIONS" | head -1)"
LATEST_DATE="$(sed -n 's/^  date: \([0-9-]*\)$/\1/p' "$VERSIONS" | head -1)"
echo "==> Version $LATEST_VERSION du $LATEST_DATE (src/i18n/versions.yaml)"
if [ "$LATEST_DATE" != "$(date +%F)" ]; then
  echo "    Rappel : toute mise à jour change la version (évolution ou correction : 3e niveau ; fonctionnalité distincte : mineure). Ajouter d'abord une entrée en tête de ce fichier."
fi

echo "==> Copie du code vers $TARGET:$REMOTE_DIR"
rsync -az --delete --exclude .git --exclude .idea --exclude .vscode --exclude .env --exclude datas --exclude dist --exclude archive --exclude tests --exclude __pycache__ \
      --exclude .DS_Store --exclude '*.db*' "$PROJECT/" "$TARGET:$REMOTE_DIR/"

echo "==> Reconstruction et redémarrage"
ssh "$TARGET" "cd '$REMOTE_DIR' && test -f .env || { echo 'Erreur : pas de .env dans $REMOTE_DIR (modèle : .env.example)'; exit 1; }; \
               docker compose up -d --build web && docker compose ps web"
echo "==> Terminé. Journal : ssh $TARGET 'cd $REMOTE_DIR && docker compose logs --tail 50 web'"
