"""Mise a jour via les releases GitHub (zip portable)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from typing import Callable, Optional

from fm_ui.constants import APP_VERSION

GITHUB_API = "https://api.github.com/repos/Fisticent/blank_fm/releases/latest"
GITHUB_RELEASES = "https://github.com/Fisticent/blank_fm/releases"
UA = f"DofusFM/{APP_VERSION}"


def parse_ver(s: str) -> tuple:
    s = (s or "").strip().lstrip("vV")
    parts = []
    for bit in s.split("."):
        n = ""
        for ch in bit:
            if ch.isdigit():
                n += ch
            else:
                break
        if n == "":
            break
        parts.append(int(n))
    return tuple(parts or (0,))


def is_newer(remote: str, local: str) -> bool:
    return parse_ver(remote) > parse_ver(local)


def fetch_latest() -> dict:
    req = urllib.request.Request(
        GITHUB_API,
        headers={"User-Agent": UA, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.load(resp)
    tag = str(data.get("tag_name") or "")
    zip_url = ""
    assets = data.get("assets") or []
    for a in assets:
        name = str(a.get("name") or "")
        if name.lower().endswith(".zip") and "portable" in name.lower():
            zip_url = str(a.get("browser_download_url") or "")
            break
    if not zip_url:
        for a in assets:
            if str(a.get("name") or "").lower().endswith(".zip"):
                zip_url = str(a.get("browser_download_url") or "")
                break
    return {
        "tag": tag,
        "zip_url": zip_url,
        "html_url": str(data.get("html_url") or GITHUB_RELEASES),
    }


def download_zip(url: str, dest: str, progress: Optional[Callable[[int, int], None]] = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        with open(dest, "wb") as out:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                got += len(chunk)
                if progress:
                    progress(got, total)
    if os.path.getsize(dest) < 1_000_000:
        raise RuntimeError("zip trop petit, telechargement rate")
    return dest


def extract_app_dir(zip_path: str, dest_dir: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    for root, _dirs, files in os.walk(dest_dir):
        if "DofusFM.exe" in files:
            return root
    raise RuntimeError("zip invalide : DofusFM.exe introuvable")


def launch_apply(src_dir: str, install_dir: str, exe_path: str, pid: int) -> None:
    src_dir = os.path.normpath(src_dir)
    install_dir = os.path.normpath(install_dir)
    exe_path = os.path.normpath(exe_path)
    bat = os.path.join(tempfile.gettempdir(), "dofusfm_apply_update.bat")
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "echo Mise a jour de Dofus FM...",
        f'set "SRC={src_dir}"',
        f'set "DST={install_dir}"',
        f'set "EXE={exe_path}"',
        f"powershell -NoProfile -Command "
        f"\"try {{ Wait-Process -Id {int(pid)} -ErrorAction Stop }} catch {{}}\"",
        "timeout /t 2 /nobreak >nul",
        'robocopy "%SRC%" "%DST%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP '
        "/XD _scratch captures cache "
        "/XF fm_settings.json fm_history.json protocol_map.json prices_history.json",
        "if %ERRORLEVEL% GEQ 8 (",
        "  echo Echec de la copie.",
        "  pause",
        "  exit /b 1",
        ")",
        "echo Relance...",
        'start "" "%EXE%"',
    ]
    with open(bat, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines) + "\r\n")
    flags = 0
    if sys.platform == "win32":
        flags = (
            getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    subprocess.Popen(["cmd", "/c", bat], creationflags=flags, close_fds=False)


def apply_from_url(zip_url: str, progress: Optional[Callable[[int, int], None]] = None) -> None:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("mise a jour auto seulement depuis DofusFM.exe")
    tmp = tempfile.mkdtemp(prefix="dofusfm_upd_")
    zip_path = os.path.join(tmp, "DofusFM-portable.zip")
    download_zip(zip_url, zip_path, progress)
    src = extract_app_dir(zip_path, os.path.join(tmp, "unz"))
    install = os.path.dirname(os.path.abspath(sys.executable))
    launch_apply(src, install, sys.executable, os.getpid())
