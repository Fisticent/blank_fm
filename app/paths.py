"""Chemins de l'outil FM : app/, data/, captures, _scratch."""
from __future__ import annotations

import os
import sys


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _meipass() -> str:
    return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))


if _frozen():
    PROJECT_DIR = os.path.dirname(os.path.abspath(sys.executable))
    APP_DIR = _meipass()
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_DIR = os.path.dirname(APP_DIR)

DATA_DIR = os.path.join(APP_DIR, "data")
SCRATCH_DIR = os.path.join(PROJECT_DIR, "_scratch")
CAPTURES_DIR = os.path.join(PROJECT_DIR, "captures")
CACHE_DIR = os.path.join(PROJECT_DIR, "cache")


def data_file(*parts: str) -> str:
    return os.path.join(DATA_DIR, *parts)


def scratch_dir(*parts: str) -> str:
    path = os.path.join(SCRATCH_DIR, *parts)
    os.makedirs(path if not os.path.splitext(path)[1] else os.path.dirname(path),
                exist_ok=True)
    return path


def captures_file(*parts: str) -> str:
    return os.path.join(CAPTURES_DIR, *parts)


def cache_dir(*parts: str) -> str:
    path = os.path.join(CACHE_DIR, *parts)
    os.makedirs(path if not os.path.splitext(path)[1] else os.path.dirname(path),
                exist_ok=True)
    return path
