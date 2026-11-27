"""Taille du code du site et du code commun : 40 lignes au plus par fonction, 300 au plus par fichier.

Les exceptions existantes sont listées une fois ; la liste ne peut que diminuer (une exception résorbée doit en sortir).
"""
import ast
import os
import unittest

from tests.support import PROJECT

PACKAGE = os.path.join(PROJECT, "pimedia")
PARTS = ("webapp", "shared")
MAX_FUNCTION_LINES = 40
MAX_FILE_LINES = 300
DATA_FILES = {"webapp/schema.py"}                 # la liste des migrations est une donnée, jamais modifiée
KNOWN_FUNCTIONS = {("webapp/app.py", "__init__"), ("webapp/app.py", "_routes"), ("webapp/mixes.py", "build")}
KNOWN_FILES = {"webapp/app.py", "webapp/entities.py", "webapp/mixes.py"}


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
    return long_functions, long_files


class CodeSizeTest(unittest.TestCase):
    def test_no_new_long_function_or_file(self):
        functions, files = measures()
        self.assertEqual(functions - KNOWN_FUNCTIONS, set(), "fonctions de plus de %d lignes" % MAX_FUNCTION_LINES)
        self.assertEqual(files - KNOWN_FILES, set(), "fichiers de plus de %d lignes" % MAX_FILE_LINES)

    def test_known_exceptions_only_shrink(self):
        functions, files = measures()
        self.assertEqual(KNOWN_FUNCTIONS - functions, set(), "exception résorbée : la retirer de KNOWN_FUNCTIONS")
        self.assertEqual(KNOWN_FILES - files, set(), "exception résorbée : la retirer de KNOWN_FILES")


if __name__ == "__main__":
    unittest.main()
