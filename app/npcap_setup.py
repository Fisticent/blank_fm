"""Detection Npcap + telechargement de l'installeur officiel (pas de redistrib)."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import urllib.request
from urllib.parse import urljoin

NPCAP_DIST = "https://npcap.com/dist/"
NPCAP_FALLBACK = "https://npcap.com/dist/npcap-1.88.exe"
UA = "DofusFM/1.0 (Npcap installer helper)"


def npcap_present() -> bool:
    win = os.environ.get("SystemRoot", r"C:\Windows")
    roots = (
        os.path.join(win, "System32", "Npcap"),
        os.path.join(win, "SysWOW64", "Npcap"),
        os.path.join(win, "System32"),
        os.path.join(win, "SysWOW64"),
    )
    for root in roots:
        for name in ("wpcap.dll", "Packet.dll"):
            if os.path.isfile(os.path.join(root, name)):
                return True
    try:
        import winreg
        winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Services\npcap",
        )
        return True
    except OSError:
        return False


def latest_installer_url() -> str:
    req = urllib.request.Request(NPCAP_DIST, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", "replace")
    except OSError:
        return NPCAP_FALLBACK
    found = re.findall(
        r"""href=["']([^"']*npcap-\d+(?:\.\d+)+\.exe)["']""",
        html,
        flags=re.I,
    )
    found = [u for u in found if "oem" not in u.lower()]
    if not found:
        return NPCAP_FALLBACK
    url = found[0]
    if url.startswith("http"):
        return url
    return urljoin(NPCAP_DIST, url)


def download_installer(progress=None) -> str:
    url = latest_installer_url()
    dest = os.path.join(tempfile.gettempdir(), os.path.basename(url.split("?")[0]))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        with open(dest, "wb") as out:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                got += len(chunk)
                if progress and total:
                    progress(got, total)
    if os.path.getsize(dest) < 10000:
        raise RuntimeError("installeur Npcap trop petit, telechargement rate")
    return dest


def launch_installer(path: str) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", path, "", os.path.dirname(path), 1)
    return int(rc) > 32
