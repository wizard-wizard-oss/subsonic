"""Règles de dépendances entre les parties du code, vérifiées à chaque passage des tests."""
import os
import re
import unittest

from tests.support import PROJECT

PACKAGE = os.path.join(PROJECT, "pimedia")
IMPORT = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.M)


def imports_of(part):
    """{fichier: [modules importés, en chemin absolu « pimedia.x.y »]} pour une partie (« shared », « server »…)."""
    found = {}
    for directory, _, names in os.walk(os.path.join(PACKAGE, part)):
        for name in (n for n in names if n.endswith(".py")):
            path = os.path.join(directory, name)
            package = os.path.relpath(directory, PROJECT).replace(os.sep, ".")
            modules = []
            for module in IMPORT.findall(open(path, encoding="utf-8").read()):
                if module.startswith("."):
                    dots = len(module) - len(module.lstrip("."))
                    base = package.split(".")[:len(package.split(".")) - dots + 1]
                    module = ".".join(base + [m for m in module.lstrip(".").split(".") if m])
                modules.append(module)
            found[os.path.relpath(path, PACKAGE)] = modules
    return found


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
