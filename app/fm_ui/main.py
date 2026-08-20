"""
Dofus FM — interface graphique (PySide6 / QML).

Usage :
    python run_ui.py
    python app/fm_ui/main.py
    python app/fm_ui/main.py --replay captures/fm_2026-08-20.jsonl
    python app/fm_ui/main.py --selftest --no-admin
    python app/fm_ui/main.py --no-admin
"""
import os
import sys
import ctypes
import socket
import threading

_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_UI_DIR)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine

from fm_ui.constants import resource_path, COLORS as C
from fm_ui.bridge import FmPanelBridge
from paths import PROJECT_DIR, CAPTURES_DIR

UDP_PORT = 43213


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def run_as_admin(argv: list[str]) -> None:
    cwd = PROJECT_DIR
    if getattr(sys, "frozen", False):
        params = " ".join(f'"{a}"' for a in argv)
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, cwd, 1)
        return
    script = os.path.abspath(sys.argv[0])
    params = " ".join([f'"{a}"' for a in argv])
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{script}" {params}',
        cwd, 1)


def _pid_on_udp_port(port: int) -> int:
    import subprocess
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "udp"],
            text=True, errors="replace")
    except (OSError, subprocess.CalledProcessError):
        return 0
    suffix = f":{port}"
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[-1].isdigit():
            continue
        if parts[1].endswith(suffix):
            return int(parts[-1])
    return 0


def _process_exe(pid: int) -> str:
    if not pid:
        return ""
    import subprocess
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True, errors="replace")
    except (OSError, subprocess.CalledProcessError):
        return ""
    line = out.strip().splitlines()[0] if out.strip() else ""
    if line.startswith('"'):
        return line.split('","')[0].strip('"').lower()
    return line.split(",")[0].strip().lower()


def handle_multiple_instances():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", UDP_PORT))
        return sock
    except OSError:
        pass
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.sendto(b"SHOW", ("127.0.0.1", UDP_PORT))
    except OSError:
        pass
    pid = _pid_on_udp_port(UDP_PORT)
    exe = _process_exe(pid)
    # Instance pythonw orpheline (lancement sans terminal) : on la remplace.
    if exe in ("pythonw.exe", "dofusfm.exe") and pid:
        try:
            import subprocess
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           check=False, capture_output=True)
        except OSError:
            pass
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("127.0.0.1", UDP_PORT))
            return sock
        except OSError:
            pass
    print("[DOFUS-FM] une instance est deja ouverte, on l'affiche.",
          file=sys.stderr)
    sys.exit(0)


def main() -> int:
    if getattr(sys, "frozen", False):
        try:
            os.makedirs(PROJECT_DIR, exist_ok=True)
            log_path = os.path.join(PROJECT_DIR, "dofus_fm.log")
            sys.stderr = open(log_path, "a", encoding="utf-8")
        except OSError:
            pass

    argv = sys.argv[1:]
    if "--no-admin" not in argv and not is_admin():
        run_as_admin(argv)
        return 0

    os.chdir(PROJECT_DIR)

    app_sock = None
    if "--no-single" not in argv:
        app_sock = handle_multiple_instances()

    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(True)
    icon_path = resource_path(os.path.join("icons", "logo.ico"))
    if os.path.exists(icon_path):
        qapp.setWindowIcon(QIcon(icon_path))

    bridge = FmPanelBridge(qapp)

    engine = QQmlApplicationEngine()
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", PROJECT_DIR)
        engine.addImportPath(meipass)
        engine.addImportPath(os.path.join(meipass, "fm_ui", "qml"))
        pyside_qml = os.path.join(meipass, "PySide6", "qml")
        if os.path.isdir(pyside_qml):
            engine.addImportPath(pyside_qml)
    ctx = engine.rootContext()
    ctx.setContextProperty("app", bridge)
    ctx.setContextProperty("Colors", dict(C))
    ctx.setContextProperty("capturesDir",
                           QUrl.fromLocalFile(CAPTURES_DIR).toString())

    qml_main = resource_path(os.path.join("qml", "Main.qml"))
    engine.load(QUrl.fromLocalFile(qml_main))
    if not engine.rootObjects():
        print("[DOFUS-FM] ERREUR : échec du chargement QML", file=sys.stderr)
        print("  QML :", qml_main, file=sys.stderr)
        return 1

    from npcap_setup import npcap_present

    if "--replay" in argv:
        idx = argv.index("--replay")
        path = argv[idx + 1] if idx + 1 < len(argv) else None
        if path:
            if not os.path.isabs(path):
                path = os.path.join(PROJECT_DIR, path)
            QTimer.singleShot(300, lambda: bridge.start_replay(path))
    elif npcap_present():
        QTimer.singleShot(300, bridge.start_live)
    else:
        print("[DOFUS-FM] Npcap absent : capture non demarree.", file=sys.stderr)

    if "--selftest" in argv:
        QTimer.singleShot(
            2500, lambda: (print("[DOFUS-FM] self-test OK : UI lancée puis fermée."),
                           qapp.quit()))

    if app_sock is not None:
        def udp_listener():
            while True:
                try:
                    data, _ = app_sock.recvfrom(1024)
                    if data == b"SHOW":
                        bridge.requestShow.emit()
                except OSError:
                    break
        threading.Thread(target=udp_listener, daemon=True).start()

    qapp.aboutToQuit.connect(bridge.shutdown)

    code = qapp.exec()
    bridge.shutdown()
    os._exit(code if isinstance(code, int) else 0)


if __name__ == "__main__":
    sys.exit(main())
