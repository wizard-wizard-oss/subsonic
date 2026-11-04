"""Thème du menu : couleurs, polices et égaliseur lus dans themes/<nom>.yaml (THEME=<nom> dans le .env).

Les valeurs par défaut ci-dessous sont celles du thème rétro : un thème incomplet, un fichier absent ou
PyYAML manquant donnent toujours un menu utilisable."""
import os
from dataclasses import dataclass, field

try:
    import yaml
except ImportError:
    yaml = None

DEFAULT_THEME = "retro"


@dataclass
class Colors:
    background: str = "#040a04"
    panel: str = "#0b1a0d"
    panel_pressed: str = "#14301a"
    edge: str = "#1f6b2f"
    text: str = "#39ff6e"
    text_soft: str = "#9be8ae"
    text_dim: str = "#2f9a4c"
    warning: str = "#ffd23f"
    danger: str = "#7f1d1d"
    saver_background: str = "#000000"


@dataclass
class Equalizer:
    off: str = "#0a2410"
    segments: list = field(default_factory=lambda: ["#39ff6e"] * 5 + ["#ffd23f"] + ["#ff4b3a"] * 2)
    columns: int = 20


@dataclass
class Fonts:
    mono: str = "DejaVu Sans Mono"
    sans: str = "DejaVu Sans"
    uppercase_buttons: bool = True


@dataclass
class Theme:
    name: str = "Rétro hi-fi"
    colors: Colors = field(default_factory=Colors)
    equalizer: Equalizer = field(default_factory=Equalizer)
    fonts: Fonts = field(default_factory=Fonts)
    web: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data):
        data = data or {}

        def part(kind, values):
            obj = kind()
            for key, value in (values or {}).items():
                if key in obj.__dataclass_fields__:
                    setattr(obj, key, value)
            return obj

        theme = cls(colors=part(Colors, data.get("colors")), equalizer=part(Equalizer, data.get("equalizer")),
                    fonts=part(Fonts, data.get("fonts")), web=dict(data.get("web") or {}))
        theme.name = data.get("name", theme.name)
        if not theme.equalizer.segments:
            theme.equalizer.segments = Equalizer().segments
        return theme

    def css_variables(self):
        """Pour la page web : --theme-background: #040a04; …"""
        values = dict(vars(self.colors), **self.web)
        return "".join("--theme-%s: %s; " % (key.replace("_", "-"), value) for key, value in values.items()).strip()


def available_themes(themes_dir):
    try:
        return sorted(name[:-5] for name in os.listdir(themes_dir) if name.endswith(".yaml"))
    except OSError:
        return []


def load_theme(themes_dir, name=DEFAULT_THEME):
    """Thème demandé ; s'il manque ou est illisible : thème rétro."""
    for candidate in (name or DEFAULT_THEME, DEFAULT_THEME):
        path = os.path.join(themes_dir, os.path.basename(candidate) + ".yaml")
        if yaml is not None and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return Theme.from_dict(yaml.safe_load(f))
            except (OSError, yaml.YAMLError):
                continue
    return Theme()
