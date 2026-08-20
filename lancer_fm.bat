@echo off
REM ============================================================
REM  Dofus FM - interface graphique (PySide6 + QML)
REM  Lance l'UI : capture live port 5555 (UAC auto si besoin).
REM  Usage :   lancer_fm.bat            -> UI live
REM            lancer_fm.bat replay     -> rejouer la session de reference
REM            lancer_fm.bat dev        -> UI live sans UAC (admin requis deja)
REM ============================================================
setlocal

REM --- repertoire du script (le projet dofus_fm) --------------------
cd /d "%~dp0"

REM --- Python : chemin connu en priorite, sinon `python` du PATH -------
set "PY=C:\Users\xavle\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=python"

REM --- arguments -----------------------------------------------------
set "ARGS="
if /i "%~1"=="replay" set "ARGS=--replay captures\fm_2026-08-20.jsonl --no-admin"
if /i "%~1"=="dev"    set "ARGS=--no-admin"

REM --- lancement -----------------------------------------------------
echo [Dofus FM] python: %PY%
echo [Dofus FM] args: %ARGS%
"%PY%" run_ui.py %ARGS%
if errorlevel 1 (
    echo.
    echo [Dofus FM] Erreur au lancement. Verifie que PySide6 et scapy sont
    echo            installes :  pip install PySide6 scapy
    pause
)

endlocal
