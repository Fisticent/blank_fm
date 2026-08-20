@echo off
REM Build le dossier portable dist\DofusFM puis un zip a envoyer.
setlocal
cd /d "%~dp0"

set "PY=C:\Users\xavle\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=python"

echo [Dofus FM] pip : pyinstaller PySide6 scapy
"%PY%" -m pip install -q pyinstaller pyinstaller-hooks-contrib PySide6 scapy
if errorlevel 1 (
    echo pip a echoue.
    exit /b 1
)

echo [Dofus FM] pyinstaller DofusFM.spec
"%PY%" -m PyInstaller --noconfirm --clean DofusFM.spec
if errorlevel 1 (
    echo Build PyInstaller echoue.
    exit /b 1
)

copy /Y "packaging\LIRE_MOI.txt" "dist\DofusFM\LIRE_MOI.txt" >nul

echo [Dofus FM] zip
"%PY%" -c "import pathlib, shutil; root=pathlib.Path('dist'); src=root/'DofusFM'; shutil.make_archive(str(root/'DofusFM-portable'), 'zip', root, 'DofusFM'); print(src.resolve()); print((root/'DofusFM-portable.zip').resolve())"

echo.
echo Pret : dist\DofusFM-portable.zip
echo Envoie ce zip a ton ami. Pas de fichier Npcap dedans (telecharge au clic).
endlocal
