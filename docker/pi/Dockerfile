# Édition Pi sur le poste de développement, pour l'essayer sans le Raspberry Pi. Contexte de construction : la racine du projet.
# Même chemin que sur le Pi : l'archive est fabriquée par deploy/pi/build_archive.py, puis installée au démarrage du
# conteneur par deploy.sh (données et versions installées dans le volume ~/.local/share/pi-media).
# Sans systemd : deploy.sh lance le serveur lui-même (PI_MEDIA_SERVICE=direct). Sans son : le vrai mpv, sortie audio nulle.
# Pas dans le conteneur : menu tactile Tk, écran, Bluetooth, AirPlay, bouton Éteindre.

# L'archive, comme « python3 deploy/pi/build_archive.py » sur le Mac (version : date et heure de la construction)
FROM debian:bookworm-slim AS archive
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY src ./src
COPY deploy/pi ./deploy/pi
RUN python3 deploy/pi/build_archive.py

# Le « Pi » : Debian bookworm comme Raspberry Pi OS 64 bits, utilisateur pi, paquets que demande deploy.sh
FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-yaml curl ca-certificates mpv procps tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /bin/bash pi \
    && mkdir -p /home/pi/.local/share/pi-media /home/pi/.config/mpv \
    && echo "ao=null" > /home/pi/.config/mpv/mpv.conf \
    && chown -R pi:pi /home/pi
# Lisibles par pi (sur le Mac, les fichiers du projet peuvent être en 600)
COPY --from=archive --chmod=u=rwX,go=rX /build/dist/ /opt/pi-media/
COPY --chmod=755 docker/pi/entrypoint.sh /usr/local/bin/pi-media-entrypoint
# PI_MEDIA_BIND : le serveur du Pi n'écoute que sur 127.0.0.1 ; ici il doit répondre hors du conteneur
# (compose.yaml ne l'ouvre que sur 127.0.0.1 du Mac).
ENV PI_MEDIA_SERVICE=direct PI_MEDIA_BIND=0.0.0.0 PI_MEDIA_PORT=8099 LANG=C.UTF-8
USER pi
WORKDIR /home/pi
VOLUME /home/pi/.local/share/pi-media
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD curl -fsS http://127.0.0.1:8099/health
ENTRYPOINT ["/usr/bin/tini", "--", "pi-media-entrypoint"]
