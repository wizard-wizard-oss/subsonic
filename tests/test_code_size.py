"""Taille du code du site (Python et JS) et du code commun : repères de 40 lignes par fonction et 300 par fichier.

Ce sont des recommandations : le test avertit, il n'échoue jamais. L'essentiel est qu'une fonction fasse une seule
tâche bien définie. Les dépassements déjà connus sont listés une fois pour ne pas répéter l'avertissement.
"""
import ast
import os
import re
import unittest
import warnings

from tests.support import PROJECT

PACKAGE = os.path.join(PROJECT, "pimedia")
PARTS = ("webapp", "shared")
MAX_FUNCTION_LINES = 40
MAX_FILE_LINES = 300
DATA_FILES = {"webapp/schema.py"}                 # la liste des migrations est une donnée, jamais modifiée
KNOWN_FUNCTIONS = {("webapp/mixes.py", "build"),
                   # Front plus ancien que la remise à plat (et mobile/navigation, venu de la 1.15) : à découper en y touchant.
                   ("js/account.js", "async function photo(box) {"), ("js/app.js", "async start(me) {"),
                   ("js/chat.js", "constructor(topic, options) {"), ("js/cover.js", "function open(album, onSaved) {"),
                   ("js/mix.js", "async render(main, route) {"), ("js/mobile/navigation.js", "constructor() {"),
                   ("js/player.js", "constructor(root, player) {"), ("js/playlists.js", "async render(main, route, focus) {"),
                   ("js/queue-memory.js", "async restore() {"), ("js/upload.js", "async render(main, route) {"),
                   ("js/views.js", "async render(main, route) {")}
KNOWN_FILES = {"webapp/entities.py", "webapp/mixes.py", "js/chat.js", "js/listen-later.js", "js/player.js", "js/views.js"}


JS_DIR = os.path.join(PROJECT, "web-pc", "static", "js")
# Début d'une fonction JS (déclaration, méthode ou fonction fléchée) dont le corps s'ouvre en fin de ligne.
JS_FUNCTION = re.compile(r"^(\s*)(?:(?:async\s+)?function\b.*|.*=>\s*|(?:async\s+)?(?:static\s+)?[\w$]+\s*\([^;]*\)\s*)\{\s*$")
JS_BLOCKS = ("if ", "if(", "for ", "for(", "while", "switch", "} else", "else", "catch", "try")


def js_files():
    for directory, _, names in os.walk(JS_DIR):
        for name in sorted(n for n in names if n.endswith(".js")):
            path = os.path.join(directory, name)
            yield "js/" + os.path.relpath(path, JS_DIR).replace(os.sep, "/"), path


def js_functions(text):
    """(nom, lignes) des fonctions ; l'enveloppe « Module = (() => { … })() » de premier niveau ne compte pas."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        match = JS_FUNCTION.match(line)
        if not match or line.strip().startswith(JS_BLOCKS) or (match.group(1) == "" and "(() =>" in line):
            continue
        indent = match.group(1)
        for j in range(i + 1, len(lines)):
            if lines[j].startswith(indent + "}") and not lines[j].startswith(indent + " "):
                yield "%d:%s" % (i + 1, line.strip()[:50]), j - i + 1
                break


def python_files():
    for part in PARTS:
        for directory, _, names in os.walk(os.path.join(PACKAGE, part)):
            for name in sorted(n for n in names if n.endswith(".py")):
                path = os.path.join(directory, name)
                yield os.path.relpath(path, PACKAGE).replace(os.sep, "/"), path


def measures():
    long_functions, long_files = set(), set()
    for relative, path in python_files():
        if relative in DATA_FILES:
            continue
        with open(path, encoding="utf-8") as source:
            text = source.read()
        if text.count("\n") > MAX_FILE_LINES:
            long_files.add(relative)
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                    node.end_lineno - node.lineno + 1 > MAX_FUNCTION_LINES:
                long_functions.add((relative, node.name))
    for relative, path in js_files():
        with open(path, encoding="utf-8") as source:
            text = source.read()
        if text.count("\n") > MAX_FILE_LINES:
            long_files.add(relative)
        for name, size in js_functions(text):
            if size > MAX_FUNCTION_LINES:
                long_functions.add((relative, name.split(":", 1)[1]))
    return long_functions, long_files


class CodeSizeTest(unittest.TestCase):
    def test_size_recommendations(self):
        """Recommandation, pas plafond : un dépassement est signalé (avertissement) mais ne fait jamais échouer les tests.
        Le vrai critère est qu'une fonction fasse une seule tâche bien définie ; la taille n'en est que le symptôme."""
        functions, files = measures()
        long_functions = sorted(functions - KNOWN_FUNCTIONS)
        long_files = sorted(files - KNOWN_FILES)
        if long_functions:
            warnings.warn("fonctions de plus de %d lignes (recommandation) : %s" % (MAX_FUNCTION_LINES, long_functions))
        if long_files:
            warnings.warn("fichiers de plus de %d lignes (recommandation) : %s" % (MAX_FILE_LINES, long_files))


if __name__ == "__main__":
    unittest.main()
