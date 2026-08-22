"""Chemins de l'outil FM : app/, data/, captures, _scratch."""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any


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


# --------------------------------------------------------------- ecriture

REPLACE_TRIES = 5


def replace_retry(tmp: str, dest: str, tries: int = REPLACE_TRIES) -> None:
    """os.replace avec quelques tentatives courtes.

    Sous Windows, un antivirus ou l'indexeur peut tenir le fichier cible
    ouvert une fraction de seconde et faire echouer le renommage avec
    WinError 5 (acces refuse). Le verrou est transitoire : reessayer suffit.
    """
    for attempt in range(tries):
        try:
            os.replace(tmp, dest)
            return
        except OSError:
            if attempt == tries - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def write_json_atomic(dest: str, payload: Any, **dump_kw: Any) -> None:
    """Ecrit du JSON via un .tmp puis un renommage atomique.

    Evite de laisser un fichier tronque si l'appli est tuee en pleine
    ecriture. Le .tmp residuel est nettoye si le renommage echoue.
    """
    tmp = dest + ".tmp"
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    dump_kw.setdefault("ensure_ascii", False)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, **dump_kw)
        replace_retry(tmp, dest)
    except Exception:
        # Inclut TypeError (payload non serialisable) : sans ca le .tmp
        # a moitie ecrit resterait sur le disque.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def trim_file(path: str, max_bytes: int) -> None:
    """Fait tourner `path` en .1 quand il depasse max_bytes.

    Un seul niveau de rotation : le .1 precedent est ecrase. Suffit pour
    des logs de diagnostic, et borne l'espace disque a ~2x max_bytes.
    """
    try:
        if os.path.getsize(path) <= max_bytes:
            return
    except OSError:
        return
    backup = path + ".1"
    try:
        if os.path.exists(backup):
            os.remove(backup)
        os.replace(path, backup)
    except OSError:
        pass
