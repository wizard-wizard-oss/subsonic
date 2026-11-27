"""La table des routes du site (méthode, chemin, garde, droit, limite, fonction) ne change pas quand les contrôleurs
déclarent eux-mêmes leurs routes. Référence : tests/data/routes.txt."""
import os
import tempfile
import unittest

from pimedia.webapp.app import WebApplication
from tests.support import PROJECT

REFERENCE = os.path.join(os.path.dirname(__file__), "data", "routes.txt")


def describe(handler):
    """Garde (lecture, écriture, écriture brute ou ouverte), droit, limite de corps et fonction finale."""
    names = handler.__code__.co_freevars if hasattr(handler, "__code__") else ()
    cells = dict(zip(names, (cell.cell_contents for cell in handler.__closure__ or ()))) if names else {}
    if "handler" not in cells or "self" not in cells:
        return "open " + getattr(handler, "__qualname__", type(handler).__name__)
    kind = "write" if "body_limit" in cells else "raw" if "check_write" in handler.__code__.co_names else "read"
    return "%s right=%s limit=%s %s" % (kind, cells.get("right"), cells.get("body_limit"), cells["handler"].__qualname__)


def route_table():
    with tempfile.TemporaryDirectory() as data:
        app = WebApplication(PROJECT, environ={"PI_MEDIA_WEB_SUBSONIC_URL": "http://127.0.0.1:9"}, data_dir=data)
        router = app.http.router
        lines = ["%s %s %s" % (method, path, describe(handler)) for (method, path), handler in router._exact.items()]
        lines += ["%s %s* %s" % (method, prefix, describe(handler)) for method, prefix, handler in router._prefixes]
        app.db.close()
    return sorted(lines)


class RouteTableTest(unittest.TestCase):
    def test_route_table_is_unchanged(self):
        with open(REFERENCE, encoding="utf-8") as reference:
            self.assertEqual(route_table(), reference.read().splitlines())


if __name__ == "__main__":
    if os.environ.get("WRITE_ROUTES"):
        with open(REFERENCE, "w", encoding="utf-8") as reference:
            reference.write("\n".join(route_table()) + "\n")
    unittest.main()
