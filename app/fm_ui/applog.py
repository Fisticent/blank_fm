"""Tampon de logs UI + fichier dofus_fm.log (stderr/stdout + tracebacks)."""
from __future__ import annotations

import os
import sys
import threading
import traceback
from collections import deque
from datetime import datetime
from typing import Optional, TextIO

MAX_LINES = 1000
_lock = threading.Lock()
_lines: deque[str] = deque(maxlen=MAX_LINES)
_partial = ""
_generation = 0
_file: Optional[TextIO] = None
_orig_stderr: Optional[TextIO] = None
_orig_stdout: Optional[TextIO] = None
_orig_excepthook = None
_in_write = False
_log_path = ""


def path() -> str:
    return _log_path


def generation() -> int:
    with _lock:
        return _generation


def text() -> str:
    with _lock:
        return "\n".join(_lines)


def clear_memory() -> None:
    global _partial, _generation
    with _lock:
        _lines.clear()
        _partial = ""
        _generation += 1


def feed(s: str) -> None:
    """Ajoute du texte brut (peut contenir plusieurs lignes)."""
    global _partial, _generation, _in_write
    if not s:
        return
    with _lock:
        if _in_write:
            return
        _in_write = True
        try:
            if _file is not None:
                try:
                    _file.write(s)
                    _file.flush()
                except OSError:
                    pass
            _partial += s
            while "\n" in _partial:
                line, _partial = _partial.split("\n", 1)
                line = line.rstrip("\r")
                if line:
                    ts = datetime.now().strftime("%H:%M:%S")
                    _lines.append(f"[{ts}] {line}")
                    _generation += 1
        finally:
            _in_write = False


class _Tee:
    def __init__(self, orig: Optional[TextIO]):
        self._orig = orig

    def write(self, s) -> int:
        if not isinstance(s, str):
            s = str(s)
        orig = self._orig
        if orig is not None:
            try:
                orig.write(s)
                orig.flush()
            except Exception:
                pass
        feed(s)
        return len(s)

    def flush(self) -> None:
        orig = self._orig
        if orig is not None:
            try:
                orig.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        orig = self._orig
        try:
            return bool(orig is not None and orig.isatty())
        except Exception:
            return False

    def fileno(self) -> int:
        orig = self._orig
        if orig is not None:
            try:
                return orig.fileno()
            except Exception:
                pass
        raise OSError("tee has no fileno")

    @property
    def encoding(self) -> str:
        orig = self._orig
        return getattr(orig, "encoding", None) or "utf-8"

    @property
    def errors(self) -> str:
        return "replace"


def _excepthook(typ, val, tb) -> None:
    msg = "".join(traceback.format_exception(typ, val, tb))
    try:
        sys.stderr.write(msg)
    except Exception:
        feed(msg)
    if _orig_excepthook and _orig_excepthook is not _excepthook:
        try:
            _orig_excepthook(typ, val, tb)
        except Exception:
            pass


def install(log_path: str) -> str:
    """Redirige stdout/stderr vers le fichier + tampon. Idempotent."""
    global _file, _orig_stderr, _orig_stdout, _orig_excepthook, _log_path
    _log_path = log_path
    if _file is None:
        try:
            os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
            _file = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)
        except OSError:
            _file = None
    if _orig_stderr is None:
        _orig_stderr = sys.stderr
        _orig_stdout = sys.stdout
        _orig_excepthook = sys.excepthook
        sys.stderr = _Tee(_orig_stderr)
        sys.stdout = _Tee(_orig_stdout)
        sys.excepthook = _excepthook
    return log_path


def install_qt_handler() -> None:
    try:
        from PySide6.QtCore import qInstallMessageHandler
    except Exception:
        return

    def _qt_msg(mode, ctx, message):
        print(f"[QT] {message}", file=sys.stderr)

    qInstallMessageHandler(_qt_msg)
