"""Règles de dépendances entre les parties du code, vérifiées à chaque passage des tests."""
import ast
import os
import re
import unittest

from tests.support import PROJECT

PACKAGE = os.path.join(PROJECT, "pimedia")
IMPORT = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.M)
PERSONAL_HOME = re.compile(r"(?:^|[\s=\"'])/(?:Users|home)(?:/|$)|[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]")


def runtime_strings(source):
    """Chaînes Python, hors documentation : une adresse citée en commentaire n'est pas un réglage exécuté."""
    tree = ast.parse(source)
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.body and isinstance(node.body[0], ast.Expr)
                  and isinstance(node.body[0].value, ast.Constant)
                  and isinstance(node.body[0].value.value, str)}
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]


def imports_of(part):
    """{fichier: [modules importés, en chemin absolu « pimedia.x.y »]} pour une partie (« shared », « server »…)."""
    found = {}
    for directory, _, names in os.walk(os.path.join(PACKAGE, part)):
        for name in (n for n in names if n.endswith(".py")):
            path = os.path.join(directory, name)
            package = os.path.relpath(directory, PROJECT).replace(os.sep, ".")
            modules = []
            with open(path, encoding="utf-8") as source:
                imported = IMPORT.findall(source.read())
            for module in imported:
                if module.startswith("."):
                    dots = len(module) - len(module.lstrip("."))
                    base = package.split(".")[:len(package.split(".")) - dots + 1]
                    module = ".".join(base + [m for m in module.lstrip(".").split(".") if m])
                modules.append(module)
            found[os.path.relpath(path, PACKAGE)] = modules
    return found


class PortablePathsTest(unittest.TestCase):
    def test_runtime_python_contains_no_personal_absolute_path(self):
        for directory, _, names in os.walk(PROJECT):
            for name in (name for name in names if name.endswith(".py")):
                path = os.path.join(directory, name)
                with open(path, encoding="utf-8") as source:
                    values = runtime_strings(source.read())
                for line, value in values:
                    self.assertIsNone(PERSONAL_HOME.search(value),
                                      "%s:%d contient un chemin personnel codé en dur" %
                                      (os.path.relpath(path, PROJECT), line))

    def test_personal_paths_are_detected_without_scanning_docstrings(self):
        # Exemples fictifs : vérifier les syntaxes POSIX et Windows ainsi que les chaînes de commandes.
        paths = ("/Users/example/project", "/home/example/music", r"C:\Users\example\Music",
                 "command --directory=/home/example/music")
        for path in paths:
            source = repr(path) + '\nROOT = ' + repr(path)
            values = runtime_strings(source)
            self.assertEqual(len(values), 1)
            self.assertIsNotNone(PERSONAL_HOME.search(values[0][1]))
        for value in ("/api/home", "https://service.example/home", "~/.local/share/pimedia", "relative/path"):
            self.assertIsNone(PERSONAL_HOME.search(value))


class DependencyRulesTest(unittest.TestCase):
    def assert_never_imports(self, part, forbidden):
        for path, modules in imports_of(part).items():
            for module in modules:
                self.assertFalse(any(module == f or module.startswith(f + ".") for f in forbidden),
                                 "%s importe %s" % (path, module))

    def test_shared_code_depends_on_no_edition(self):
        self.assert_never_imports("shared", ["pimedia.server", "pimedia.webapp", "pimedia.menu"])

    def test_pi_edition_never_uses_the_pc_edition(self):
        self.assert_never_imports("server", ["pimedia.webapp"])
        self.assert_never_imports("menu", ["pimedia.webapp"])

    def test_the_rule_is_really_checked(self):
        self.assertIn("pimedia.shared.external", imports_of("server")["server/external.py"])
