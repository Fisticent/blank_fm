# dofus_fm — lecture HDV + outil Forgemagie (Dofus 3)

Reverse-engineering du protocole HDV de Dofus 3 : lire les items en vente et
leurs prix, par **sniffing réseau** (port 5555, protocole en clair). Voir
`PROTOCOL.md` pour le détail.

L'outil FM graphique (PySide6 + QML) et son backend vivent dans **`app/`**.

## Structure

```
app/                    backend FM + UI
  fm_ui/                interface PySide6 / QML   →  python run_ui.py
  data/                 items.json, runes.json, prices.json, effects.json
  fm_panel.py           panneau terminal + moteur partagé avec l'UI
  fm_decoder.py         rapport de session
  fm_live.py            capture JSONL
  ...
captures/               journaux de référence
pcaps/                  captures HDV
```

| Fichier | Rôle |
|---------|------|
| `run_ui.py` | **Lance l'UI FM** |
| `app/fm_ui/` | Fenêtre sombre : item, stats, jet %, puits, coût, issues, historique |
| `app/fm_panel.py` | Moteur FM (SC/SN/EC, puits, reliquat) + panneau terminal |
| `app/fm_decoder.py` | Rapport d'une session capturée |
| `app/fm_live.py` | Capture live des messages Forgemagie |
| `app/fm_cost.py` | Table des prix moyens (`ivi` au login) |
| `app/item_jet.py` | Jet mini→maxi et % du jet global |
| `app/fetch_items.py` | Génère `app/data/items.json` |
| `app/fetch_runes.py` | Génère `app/data/runes.json` |
| `app/sniffer_hdv.py` | Parseur HDV (pcap ou live) |
| `app/data/` | Tables locales (runes, items, prix, malus) |
| `FM_FONCTIONNEMENT.md` | Poids, puits, succès/neutre/échec |
| `PROTOCOL.md` | Notes de reverse-engineering |
| `captures/fm_2026-08-20.jsonl` | Session FM de référence (24 poses) |

## Prérequis

- Windows + Python 3.13
- `pip install scapy PySide6` (npcap pour la capture live)

## Interface FM (PySide6 + QML)

```powershell
python run_ui.py
python run_ui.py --replay captures\fm_2026-08-20.jsonl --no-admin
python app\fm_ui\main.py --selftest --no-admin
```

La capture live demande l'admin (UAC). Relancer depuis la racine du projet.

## Usage HDV / CLI

```powershell
python app\sniffer_hdv.py parse pcaps\dofus2.pcap --item 9151
python app\fm_live.py live --out _scratch\capture --fm
python app\fm_decoder.py captures\fm_2026-08-20.jsonl
python app\fm_panel.py live
python app\fm_panel.py replay captures\fm_2026-08-20.jsonl
python app\fm_cost.py prices captures\login.jsonl
```

## ForgeMagie (FM)

```powershell
# Capturer une session FM (le jeu doit être connecté sur le port 5555)
python app\fm_live.py live --out _scratch/capture
# ... fais tes poses de runes ... Ctrl+C pour arrêter

# Analyser la session : runes, effets, état de l'item à chaque pose
python app\fm_decoder.py captures\fm_2026-08-20.jsonl
```

Exemple de sortie (`fm_decoder.py`) :

```
Session FM - 24 pose(s) de rune sur Amulette du Strigide (GID 14094, UID 63847366, slot 63)

  #  heure         rune               effet         valeur  delta etat   puit
  1  16:11:16.664  Rune Pa Sa         Sagesse            3           1    3.6
  4  16:11:18.694  Rune Pa Sa         Sagesse            3     +3    2    1.6
  5  16:11:19.835  Rune Cri           Critique           1     +1    1    3.6
```

`fm_live.py` affiche aussi en direct une ligne compacte par message FM
(`>> rune Rune Pa Sa (gid 1546) : Sagesse +3 [uid 63847879]`,
`*** PUIT=3.6  etat=1 Rune Pa Sa -> [Vitalite 392, ...]` — le puits affiché
par l'UI). Voir `PROTOCOL.md` → ForgeMagie.

## Panneau de contrôle FM (live)

```powershell
# Pendant que tu fores (le jeu connecté sur le port 5555)
python app\fm_panel.py live --out _scratch\panel

# Rejouer une session enregistrée (frames.jsonl)
python app\fm_panel.py replay captures\fm_2026-08-20.jsonl
```

Le panneau (mis à jour à chaque pose) affiche :
- **Issues** : SC (succès critique), SN (succès neutre), EC (échec critique),
  rien — avec compteurs cumulés ;
- **Puits** : valeur courante, variation totale, et **reliquat** calculé
  (`poids perdu − poids de la rune`, modèle FM_FONCTIONNEMENT.md) affiché
  à côté de la variation observée pour valider les poids ;
- **Jet item** : **% du jet global** de l'item forgé (moyenne des lignes
  positives, malus exclus — items.json) avec code couleur
  (vert ≥ 80 %, jaune ≥ 50 %, rouge sinon) ;
- **Runes** : nombre posées + décompte par type ;
- l'état de l'item et l'historique roulant des poses.

## Coût des runes + % du jet

Le prix moyen affiché dans l'UI FM vient du message serveur **`ivi`** (s2c,
envoyé **à la connexion** — pas à l'ouverture de l'UI) : la liste complète
`{gid → prix moyen}` (~7 700 items, runes comprises). Une capture **depuis le
login** suffit donc pour avoir tous les prix.

```powershell
# 1× par connexion : capture depuis le login du jeu (admin)…
python app\fm_live.py live --out _scratch\login --fm
# …puis extraire la table des prix moyens -> app/data/prices.json
python app\fm_cost.py prices _scratch\login\frames.jsonl

# Base des équipements (1×, hors ligne ensuite) : app/data/items.json
python app\fetch_items.py

# Rapport de session : coût par pose + total + % du jet de l'item
python app\fm_decoder.py captures\fm_2026-08-20.jsonl --prices app\data\prices.json --jet 14094
```

Exemple de sortie :

```
  #  heure         rune            effet         valeur  delta etat  puit      prix      cout
  5  16:11:19.835  Rune Cri       Critique            1     +1    1   3.6     2,947     2,947
...
TOTAL depense en runes : 46 057 kamas

Jet de l'item (Amulette du Strigide) — valeur actuelle vs maxi (%=actuel/maxi) :
stat                    actuel   mini   maxi    % jet
Vitalite                  330    351    400    82.5%
Puissance                  67     51     70    95.7%
Do Cri                     25     16     25   100.0%
...
JET GLOBAL                                       66.7%   (moyenne des 10 lignes positives, malus exclus)
```

- `% jet = actuel / maxi` (« jet % classique ») : 0-100 % = qualité du jet,
  **> 100 %** = dépassé par la FM. **JET GLOBAL** = moyenne des lignes
  **positives** uniquement (malus exclus, donc toujours ≥ 0).
- En live : `fm_panel.py` affiche le Jet item ; `fm_live.py --fm` l'ajoute
  à chaque ligne `kdr` (`*** PUIT=…  jet 84.2%`).
- Le template vient de `items.json` (équipement) ; sinon fetch dofusdb avec
  cache (`item_templates.json`).

## Interface graphique (`app/fm_ui/`)

Fenêtre **PySide6 + QML**, alimentée par le même backend que le panneau
terminal (`app/fm_ui/bridge.py` → `FmPanel`).

```powershell
python run_ui.py
python run_ui.py --replay captures\fm_2026-08-20.jsonl --no-admin
```

Ce que la fenêtre affiche (mis à jour à chaque pose de rune) :
- **Item** : icône (cache `app/fm_ui/icons/`), nom + GID + UID, jet global ;
  changement d'item auto-détecté (slot 63 / kdr) → compteurs reset ;
- **Stats** : lignes avec pastille + valeur + % du jet par stat ;
- **Puits** : valeur, variation totale, reliquat cumulé ;
- **Coût runes** : total en kamas (`app/data/prices.json`) ;
- **Temps** : durée de session + durée sur l'item courant ;
- **Issues** SC/SN/EC + historique des 14 dernières poses.

Les icônes viennent de `app/data/items.json` ; régénérer avec
`python app\fetch_items.py`.

## Table des runes

```powershell
# Regenerer la table depuis api.dofusdb.fr (scan des GIDs, ~3 min)
python app\fetch_runes.py
python app\fetch_runes.py --gen-only
python app\fetch_runes.py --malus
```

`runes.md` contient les **96 runes de Dofus 3** : GID (celui des paquets),
stat (effectId dofusdb), valeur ajoutée, **poids de forgemagie** (table
DPLN — dofuspourlesnoobs.com/guide-forgemagie.html, qui fait foi). Règle
DPLN : pas de poids Pa/Ra listé = la variante n'existe pas en jeu
(variantes résiduelles des données DofusDude exclues : Ra Ré X, Ra Do Pou,
Pa Do Ren). Les runes Do Per, Pi, Puit, Chasse, Ré Per Di/Mé n'existent pas
en Dofus 3 (retirées par la refonte).

`fm_decoder.py` charge `runes.json` et `effects.json` automatiquement : toutes
les runes et effets inconnus sont nommés sans modification de code, et les
**malus sont détectés et affichés négatifs** (ex. « Critique (malus) -11 »).

Exemple de sortie :

```
item 9151: 19 vente(s) — min 8890, max 40000, moyenne 12829
    uid=58078  prix=8890 qty=1
    ...
```

## API

```python
from sniffer_hdv import parse_pcap
events = parse_pcap("pcaps/dofus2.pcap", item=9151)
for ev in events:                      # ev.kind == "listings"
    for l in ev.listings:
        print(l.gid, l.price, l.quantity)   # Listing(uid, gid, price, qty)
```

`HdvParser` accepte aussi un flux live via `parser.feed(direction, payload, flow_key)`
ou `parser.on(callback)`.

## Notes

- Le protocole est en clair sur le port 5555 (pas de TLS) ; le port 6337 est
  TLS (autre service).
- Les noms de messages (`kbt`, `kda`) sont obfusqués → à revérifier par version.
- Sniffing passif = lecture seule ; l'automatisation reste à la discrétion de
  l'utilisateur vis-à-vis des CGU Ankama.
