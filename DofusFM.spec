# -*- mode: python ; coding: utf-8 -*-
"""Build portable Dofus FM (onedir). Ne bundler PAS l'installeur Npcap."""
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = os.path.abspath(SPECPATH)
APP = os.path.join(ROOT, "app")

datas = [
    (os.path.join(APP, "data"), "data"),
    (os.path.join(APP, "fm_ui", "qml"), os.path.join("fm_ui", "qml")),
    (os.path.join(APP, "fm_ui", "icons"), os.path.join("fm_ui", "icons")),
    (os.path.join(APP, "fm_ui", "sounds"), os.path.join("fm_ui", "sounds")),
]
binaries = []
hiddenimports = [
    "fm_ui",
    "fm_ui.bridge",
    "fm_ui.constants",
    "fm_ui.fm_sounds",
    "fm_panel",
    "fm_decoder",
    "fm_live",
    "fm_cost",
    "item_jet",
    "fetch_runes",
    "sniffer_hdv",
    "paths",
    "npcap_setup",
    "proto_learn",
    "fm_updater",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtNetwork",
    "scapy",
    "scapy.all",
    "scapy.layers.inet",
    "scapy.layers.l2",
]

for pkg in ("PySide6", "scapy"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += collect_data_files("scapy")

block_cipher = None

a = Analysis(
    [os.path.join(APP, "fm_ui", "main.py")],
    pathex=[APP, ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "fm_send",
        "tkinter",
        "matplotlib",
        "numpy",
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPositioning",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtTextToSpeech",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DofusFM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DofusFM",
)
