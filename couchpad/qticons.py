"""Icon theme setup for our Qt processes."""

import os

from PySide6.QtGui import QIcon


def ensure_icon_theme():
    """Outside Plasma's platform theme (offscreen, other desktops) Qt knows
    no icon theme or search path: use the theme KDE is set to."""
    paths = list(QIcon.themeSearchPaths())
    data = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    for d in [os.path.expanduser("~/.local/share"), *data,
              os.path.expanduser("~/.local/share/flatpak/exports/share"),
              "/var/lib/flatpak/exports/share"]:
        p = os.path.join(d, "icons")
        if d and p not in paths and os.path.isdir(p):
            paths.append(p)
    QIcon.setThemeSearchPaths(paths)
    if QIcon.themeName() not in ("", "hicolor"):
        return
    theme = "breeze-dark"
    try:
        group = None
        with open(os.path.expanduser("~/.config/kdeglobals"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("["):
                    group = line
                elif group == "[Icons]" and line.startswith("Theme="):
                    theme = line.split("=", 1)[1]
    except OSError:
        pass
    QIcon.setThemeName(theme)
    QIcon.setFallbackThemeName("breeze")


ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "icons")


def bundled(spec):
    """"ph:name" / "ph-fill:name" -> path of the bundled Phosphor SVG."""
    kind, _sep, base = spec.partition(":")
    return os.path.join(ICONS, base + ("-fill" if kind == "ph-fill" else "") + ".svg")
