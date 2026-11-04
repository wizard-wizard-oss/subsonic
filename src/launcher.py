#!/usr/bin/env python3
"""Menu tactile du Pi : le code est dans pimedia/menu/ (logique) et pimedia/menu/ui.py (écran).

Si le nouveau menu ne démarre pas (erreur au lancement), l'erreur est notée dans menu-erreur.log
(dossier de données) et l'ancien menu (launcher_classic.py) prend le relais : l'écran n'est jamais vide."""
import os
import runpy
import sys
import time
import traceback

CODE_DIR = os.path.dirname(os.path.realpath(__file__))      # suit le lien ~/.local/share/pi-media/launcher.py
sys.path.insert(0, CODE_DIR)


def log_failure():
    try:
        from pimedia.paths import resolve_data_dir
        data_dir = resolve_data_dir(CODE_DIR, os.environ)
    except Exception:
        data_dir = CODE_DIR
    try:
        with open(os.path.join(data_dir, "menu-erreur.log"), "a", encoding="utf-8") as f:
            f.write("\n=== %s ===\n%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), traceback.format_exc()))
    except OSError:
        pass
    traceback.print_exc()


def close_half_built_window():
    try:
        import tkinter
        if tkinter._default_root is not None:
            tkinter._default_root.destroy()
    except Exception:
        pass


def main():
    try:
        from pimedia.menu.main import build, start
        services, ui = build(CODE_DIR)
    except Exception:
        log_failure()
        close_half_built_window()
        runpy.run_path(os.path.join(CODE_DIR, "launcher_classic.py"), run_name="__main__")
        return
    start(services, ui)


if __name__ == "__main__":
    main()
