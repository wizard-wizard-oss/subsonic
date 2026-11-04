# Tous les tests (éditions Pi et PC) : unitaires, intégration, parcours navigateur jsdom.
# Sert aussi à la démonstration (tests/demo_webapp.py). Contexte de construction : la racine du projet.

# jsdom, installé avec npm dans l'image Node officielle
FROM node:22-bookworm-slim AS jsdom
WORKDIR /opt/jsdom
RUN npm install --no-audit --no-fund jsdom@25.0.1

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 JSDOM_PATH=/opt/jsdom/node_modules/jsdom
COPY requirements.txt /tmp/requirements.txt
COPY tests/requirements.txt /tmp/tests/requirements.txt
RUN pip install --no-cache-dir -r /tmp/tests/requirements.txt \
    && useradd --create-home --uid 1000 pimedia
COPY --from=jsdom /usr/local/bin/node /usr/local/bin/node
COPY --from=jsdom /opt/jsdom/node_modules /opt/jsdom/node_modules
WORKDIR /app
COPY --chown=pimedia:pimedia src ./src
COPY --chown=pimedia:pimedia tests ./tests
USER pimedia
CMD ["sh", "-c", "python3 -m unittest discover -s tests -t . && python3 -m tests.run_e2e"]
