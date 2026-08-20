"""Lance l'interface Forgemagie (PySide6 + QML)."""
import os
import runpy

_ROOT = os.path.dirname(os.path.abspath(__file__))
_MAIN = os.path.join(_ROOT, "app", "fm_ui", "main.py")
runpy.run_path(_MAIN, run_name="__main__")
