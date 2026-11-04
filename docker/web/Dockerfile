# Site de l'édition PC (plusieurs utilisateurs d'un serveur Subsonic). Contexte de construction : la racine du projet.
# Données (webapp.db : comptes du site, salon, notes, photos) dans le volume /data.
FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PI_MEDIA_WEB_DATA=/data PI_MEDIA_WEB_BIND=0.0.0.0 PI_MEDIA_WEB_PORT=8200
# APP_UID / APP_GID : ceux de l'utilisateur de l'hôte qui possède la musique (le même que Subsonic) : les fichiers envoyés
# lui appartiennent.
ARG APP_UID=1000
ARG APP_GID=1000
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && groupadd --non-unique --gid "$APP_GID" pimedia \
    && useradd --create-home --non-unique --uid "$APP_UID" --gid "$APP_GID" pimedia \
    && mkdir /data && chown pimedia:pimedia /data
WORKDIR /app
# Code en lecture seule pour l'utilisateur du site (root reste propriétaire)
COPY --chmod=u=rwX,go=rX src/pimedia-web.py ./
COPY --chmod=u=rwX,go=rX src/i18n ./i18n
COPY --chmod=u=rwX,go=rX src/pimedia ./pimedia
COPY --chmod=u=rwX,go=rX src/web-pc ./web-pc
USER pimedia
VOLUME /data
EXPOSE 8200
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8200/health', timeout=4)"
CMD ["python3", "pimedia-web.py"]
