"""Fenêtres Feishin / FreeTube / Supersonic ouvertes agrandies (règles labwc dans ~/.config/labwc/rc.xml)."""
import os, re, shutil
home = os.path.expanduser("~")
rc = os.path.join(home, ".config/labwc/rc.xml")
if not os.path.exists(rc) and os.path.exists("/etc/xdg/labwc/rc.xml"):
    shutil.copy("/etc/xdg/labwc/rc.xml", rc)
if not os.path.exists(rc):
    print("rc.xml labwc introuvable : fenêtres non maximisées automatiquement.")
    raise SystemExit
txt = open(rc, encoding="utf-8").read()
if "supersonic" in txt:
    raise SystemExit
def rule(i):
    return f'<windowRule identifier="{i}"><action name="Maximize"/></windowRule>'
if "<!-- pi-media -->" in txt:
    # installation précédente : on ajoute seulement Supersonic
    extra = rule("io.github.dweymouth.supersonic*") + rule("supersonic*")
    txt = txt.replace("<!-- pi-media -->", "<!-- pi-media -->" + extra, 1)
    open(rc, "w", encoding="utf-8").write(txt)
    raise SystemExit
rules = "".join(rule(i) for i in (
    "feishin*", "freetube*", "io.github.dweymouth.supersonic*", "supersonic*"))
block = f"<!-- pi-media -->{rules}"
if "<windowRules>" in txt:
    txt = txt.replace("<windowRules>", "<windowRules>" + block, 1)
else:
    txt, n = re.subn(r"</(labwc_config|openbox_config)>",
                     lambda m: f"<windowRules>{block}</windowRules>{m.group(0)}", txt, 1)
    if n == 0:
        print("rc.xml inattendu : fenêtres non maximisées automatiquement.")
        raise SystemExit
open(rc, "w", encoding="utf-8").write(txt)
