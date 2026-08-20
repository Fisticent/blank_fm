# Dofus FM

Outil de **Forgemagie** pour Dofus 3 : capture passive du port 5555 (protobuf en clair).
Il affiche l’item, le jet, le puits, le coût des runes, les tentatives d’exo et un overlay.

Si Ankama change les noms de messages (`kfb`, `kdr`…), il faut un patch de l’outil
(les noms ne sont plus réappris tout seuls, ça cassait le switch d’item).

L’exe portable vérifie GitHub au lancement : bandeau si une release est plus récente,
un clic télécharge le zip et relance.

## Téléchargement

Release Windows (dossier portable) :

https://github.com/Fisticent/blank_fm/releases

1. Télécharge le zip, dézippe
2. Lance `DofusFM.exe`, accepte l’admin
3. Si besoin : bouton **Installer Npcap** (télécharge l’installeur officiel)
4. Ouvre la forgemagie dans Dofus, pose des runes

## Dev (Python)

```powershell
pip install scapy PySide6
python run_ui.py
```

Npcap requis pour la capture live. Relance depuis la racine du projet.

```powershell
python run_ui.py --replay captures\fm_2026-08-20.jsonl --no-admin
python app\fm_ui\main.py --selftest --no-admin
```

Build portable : `build_portable.bat` → `dist\DofusFM-portable.zip`

## Contenu

| Fichier | Rôle |
|---------|------|
| `run_ui.py` / `lancer_fm.bat` | Lance l’UI |
| `app/fm_ui/` | Interface PySide6 / QML |
| `app/fm_panel.py` | Moteur FM (SC/SN/EC, puits, reliquat) |
| `app/proto_learn.py` | Noms de messages figés (plus d'apprentissage sauvage) |
| `app/fm_updater.py` | Vérif GitHub + application du zip portable |
| `app/data/` | Runes, items, prix, effets |
