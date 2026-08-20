"""fm_ui.constants — tokens visuels (design system reframed) + couleurs par stat.

Source des tokens : labs/reframed_qml/constants.py (COLORS) — réutilisés tels
quels pour garder la même identité visuelle. Exposés à QML via `Colors`.
"""
import os
import sys

APP_NAME = "Dofus FM"
APP_VERSION = "1.0.0"


def get_app_dir():
    """Répertoire de l'exe (PyInstaller) ou du projet (dev)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        direct = os.path.join(base, relative_path)
        nested = os.path.join(base, "fm_ui", relative_path)
        if os.path.exists(direct):
            return direct
        return nested
    return os.path.join(get_app_dir(), relative_path)


# ----------------------------------------------------------------- tokens
# Repris du design system reframed (DESIGN.md + constants.py) — identité sombre
# dense, adaptée à un outil desktop de pilotage.
COLORS = {
    # surfaces & texte
    "bg": "#1e2128",
    "bg_card": "#262a33",
    "bg_elevated": "#2f3540",
    "text": "#e8eaed",
    "text_muted": "#8b95a5",
    "text_on_accent": "#1e2128",
    "separator": "#363d4a",
    "disabled_bg": "#2a2f3a",
    # primaire & actions
    "primary": "#5a9e3e",
    "primary_hover": "#4a8532",
    "primary_bright": "#6db84a",
    "primary_button": "#3d6b28",
    "primary_button_hover": "#356024",
    "secondary": "#363d4a",
    "secondary_hover": "#424957",
    "secondary_dark": "#2a2f3a",
    "focus_ring": "#8bc96e",
    # sémantique
    "success": "#4caf6a",
    "success_hover": "#3d9460",
    "warning": "#c4782a",
    "warning_hover": "#a86520",
    "danger": "#b83a32",
    "danger_hover": "#962f28",
    "tooltip_bg": "#363d4a",
    "tooltip_fg": "#e8eaed",
    # typo
    "font_family": "Segoe UI",
    "font_size_ui": 12,
    "font_size_secondary": 11,
    "font_size_heading": 14,
    "font_size_title": 20,
    # rayons
    "radius_card": 8,
    "radius_control": 6,
    "radius_window": 10,
    # seuils + couleurs de stats (exposes a QML via le meme dict)
    "JET_GREEN": 80.0,
    "JET_YELLOW": 50.0,
    "STAT_COLOR_FALLBACK": "#5a6478",
}

# Seuils du jet global -> couleur (mêmes valeurs que fm_panel.py)
JET_GREEN = 80.0
JET_YELLOW = 50.0

# ----------------------------------------------------------------- stats
# Couleur par effectId pour les pastilles de stats. Fallback si inconnu : gris.
# Couleurs inspirées du jeu (Vitalité rouge, Sagesse bleue, Force rouge foncé…).
STAT_COLORS: dict[int, str] = {
    # caractéristiques principales
    125: "#d64541",   # Vitalité
    124: "#4a7dbd",   # Sagesse
    118: "#b34a3a",   # Force
    126: "#5a8fd6",   # Intelligence
    123: "#5da04a",   # Chance
    119: "#c4903a",   # Agilité
    174: "#8b95a5",   # Initiative
    # combat
    111: "#d64541",   # PA
    128: "#d64541",   # PM
    117: "#c4782a",   # Portée
    115: "#b83a32",   # Critique
    112: "#b83a32",   # Dommage
    138: "#c4782a",   # Puissance
    178: "#4caf6a",   # Soin
    182: "#c4782a",   # Invocation
    # dommages élémentaires
    428: "#5a9e3e",   # Do Air
    426: "#4a7dbd",   # Do Eau
    424: "#d64541",   # Do Feu
    422: "#a0803a",   # Do Terre
    430: "#8b95a5",   # Do Neutre
    414: "#c4782a",   # Do Poussée
    418: "#b83a32",   # Do Critiques
    114: "#8b95a5",   # Renvoi dommages
    2812: "#c4782a",  # Do Per So
    2804: "#c4782a",  # Do Per Di
    2808: "#c4782a",  # Do Per Ar
    # résistances %
    212: "#5a9e3e",   # Ré Per Air
    211: "#4a7dbd",   # Ré Per Eau
    213: "#d64541",   # Ré Per Feu
    210: "#a0803a",   # Ré Per Terre
    214: "#8b95a5",   # Ré Per Neutre
    215: "#c4782a",   # Ré Per Poussée
    216: "#b83a32",   # Ré Per Critiques
    # résistances élémentaires
    242: "#5a9e3e",   # Ré Air
    241: "#4a7dbd",   # Ré Eau
    240: "#d64541",   # Ré Feu
    243: "#a0803a",   # Ré Terre
    244: "#8b95a5",   # Ré Neutre
    416: "#c4782a",   # Ré Poussée
    420: "#b83a32",   # Ré Critiques
    421: "#b83a32",   # Rés. Critiques (malus)
    # retrait / esquive / misc
    410: "#c4782a",   # Retrait PA
    412: "#c4782a",   # Retrait PM
    91: "#5a9e3e",    # Esquive PA
    92: "#5a9e3e",    # Esquive PM
    753: "#a0803a",   # Tacle
    752: "#a0803a",   # Fuite
    176: "#c4782a",   # Prospection
    158: "#8b95a5",   # Pods
}

# Couleur de pastille par défaut pour les effectIds inconnus
STAT_COLOR_FALLBACK = "#5a6478"

# Pastille par abréviation courte (pour les stats sans effectId dans le GUI)
# -> générée en SVG par un helper ; garde une couleur par famille de nom.
FALLBACK_STAT_COLORS: dict[str, str] = {
    "PA": "#d64541", "PM": "#d64541", "PO": "#c4782a", "Invocation": "#c4782a",
    "Dommage": "#b83a32", "Critique": "#b83a32", "Soin": "#4caf6a",
}
