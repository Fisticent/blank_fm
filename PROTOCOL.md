# Protocole HDV Dofus 3 — notes de reverse-engineering

> Session du 2026-08-09, client **Dofus 3.6.10.10** (Unity/IL2CPP). Méthode :
> capture pktmon → analyse protobuf → validation croisée écran + lecture mémoire.
> Les noms de messages (`kbt`, `kda`…) sont **obfusqués** : à re-identifier à
> chaque version du jeu.

## Transport

| Port | Usage | Chiffrement |
|------|-------|-------------|
| **5555** | Protocole de jeu (dont HDV) | **Aucun** — protobuf en clair |
| 6337 | Autre service (Ankama) | TLS 1.2 (`0x17 0x03 0x03`) |

## Framing

Chaque trame TCP = **`[varint longueur][message protobuf]`** (varint LEB128).
Un même segment TCP peut contenir plusieurs trames (ou une trame fragmentée).

## Enveloppe

```
message Enveloppe {
  message Inner {
    string type_url = 1;   // "type.ankama.com/<obfusque>"
    bytes  payload  = 2;
  }
  Inner field_1 = 1;
}
```

## Catalogue des messages identifiés

| type_url | Rôle | Contenu |
|----------|------|---------|
| `kqy` | heartbeat | `f1=1` |
| `kda` | liste HDV (catégorie) | blob binaire de GIDs en varint (+ petites valeurs = compteurs ?) |
| `kbt` | annonces d'un item sélectionné | `f2` = gid, `f3` répété = annonces |
| `kmb`, `jsj`, `jsn` | entités/monde (joueurs visibles) | noms de joueurs, stats |
| `keh`, `kqo` | requêtes client | heartbeats/requêtes |

## Message `kbt` (annonces) — structure détaillée

```
payload:
  f1 varint = 1
  f2 varint = gid            # GID Dofus de l'item
  f3 bytes  (répété) = annonce :
      f1 varint = uid        # identifiant unique de l'annonce
      f4 bytes  = stats/effets de l'item (sous-messages)
      f5 varint = gid
      f6 bytes  = PRIX (varint LEB128, suivi d'octets 0x00 de bourrage)
      f8 varint = quantité
```

Exemple brut annoté (annonce uid 15433, Amublop Coco) :

```
08 c9 78              f1 uid = 15433
22 04 20 2a 58 7d      f4 stats {élément 42: 125}
22 04 20 20 58 77      f4 stats {élément 32: 119}
22 04 20 0f 58 7c      f4 stats {élément 15: 124}
22 04 20 04 58 73      f4 stats {élément 4: 115}
28 bf 47               f5 gid = 9151
32 05 c4 45 00 00 00   f6 prix = varint(c4 45) = 8900 kamas
40 01                  f8 quantité = 1
```

Un `kbt` court (`f1=1, f2=gid`, **aucun `f3`**) = item **sans annonce en vente**
(« pas de prix » affiché).

## Encodage du prix

- **Varint LEB128** (PAS un int32 little-endian — piège identifié).
  Ex. `ba 45` = 8890, `a8 46` = 9000, `8f 4e` = 9999, `c0 b8 02` = 40000.
- Le champ `f6` contient le varint suivi d'octets `0x00` de bourrage (3 octets
  observés) — les ignorer lors du décodage.

## Validation (Amublop Coco, gid 9151)

19 annonces capturées : 8890, 8900, 8999, 9000 ×7, 9999 ×5, 19967, 21000, 23000, 40000.
- **min 8890 = prix affiché à l'écran** (validation utilisateur) ✓
- **moyenne 12829, médiane 9000**

## Lecture mémoire (complémentaire — l'autre canal)

Le client garde aussi le **prix moyen affiché** en mémoire (objet par item :
`id@+0x10`, `price@+0x20` en int64, `qty@+0x28` ; `price=0` = « pas de prix »).
Ex. validé : Amublop Coco prix moyen **8 404 194** (agrégat historique, marché
crashé vs annonces actuelles 9k-40k).

## ForgeMagie (FM) — messages, runes, état de l'item

> Session du 2026-08-20, même client Dofus 3, méthode identique (capture live
> port 5555 → `fm_live.py`, analyse → `fm_decoder.py`). Item forgé : **Amulette
> du Strigide** (GID 14094, UID 63847366, slot 63), 24 poses de runes.
> Les noms (`kcj`, `kfb`…) sont obfusqués : à re-identifier par version.

### Séquence d'une pose de rune

Chaque pose de rune = 1 requête client + 1 rafale serveur :

```
c2s kcj  (47 B)   ObjectUse              -> utilise la rune (UID)
s2c kfb  (54 B)   écho de la rune        -> GID + effet + UID
s2c irq  (43 B)   état/objet (partiel)   -> f5 = compteur +120/rune
s2c ivj  (44 B)   quantité de pile       -> rune UID, quantite restante
s2c kfs  (32 B)   ack d'utilisation      -> UID de la rune
s2c kdr  (117-124 B) état de l'item      -> effets apres la rune
s2c iuj  ×2 (110-123 B) inventaire       -> item complet (GID, effets, UID)
s2c iun  (34 B)   partiel                -> f1 = compteur decroissant (7063->7057)
s2c kdb  (40 B)   ack                    -> f2 = 1
```

### Structure détaillée

**`kcj` (c2s) — ObjectUse (poser la rune)**
```
f1 varint = objectUID de la rune (ex. 63847879)
f3 varint = 1
f6 varint = 1
```

**`kfb` (s2c) — la rune utilisée (ObjectItem)**
```
f1 bytes : f1 = slot (63), f5 = ObjectItem {
    f1 = GID de la rune (ex. 1546)
    f2 = effet { f4 = valeur/poids, f11 = effectId }   # ObjectEffectInteger
    f3 = 1, f4 = objectUID
}
```

**`kdr` (s2c) — état de l'item forgé après la rune**
```
f2 bytes : f1 = état (0-2, semi-aléatoire)
           f3 = fixed32 float = PUITS de l'item (affiche dans l'UI de
           forgemagie, decimal possible en Dofus 3 : 0.6, 2.8, 3.6…)
           f4 = conteneur item {
               f1 = GID de l'item (14094)
               f2 répété = effet { f4 = valeur, f11 = effectId }
               f3 = 1
               f4 = objectUID de l'item
           }
```

**`iuj` (s2c) — item d'inventaire (mêmes infos + slot)**
```
f1 bytes : f1 = slot (63), f5 = ObjectItem {
    f1 = GID, f2 répété = effets, f3 = 1, f4 = objectUID,
    f5 = bytes { f1 = 1, f2 = 1 }
}
```

**`ivj` (s2c) — quantité restante de la pile de runes**
```
f2 bytes : f1 = quantité, f2 = flag (1 ou 2)
f3 bytes : f2 = objectUID de la rune, f3 = quantité
```
Obs. : décrémente de 1 à chaque rune consommée (ex. 100 → 99 → 98).

**`kfs` (s2c)** = ack d'utilisation : `f1 = objectUID de la rune`.

**`kdb` (s2c)** = ack constant `f2 = 1`.

**`iun` (s2c)** = partiellement identifié : `f1` décrémente par à-coups
(7063 → 7057 sur 24 runes), `f3` constant (23492). Non corrélé aux GIDs connus.

**`irq` (s2c)** = partiellement identifié : `f1 { f1 = slot, f3 = 200,
f4 = 398000, f5 = +120/rune }` — absent de certaines rafales.

### ObjectEffectInteger — correction HDV

Le couple `{ f4 = valeur, f11 = effectId }` est le **même** que dans les stats
HDV du message `kbt` : la notation « élément 42 : 125 » du tableau précédent
était **inversée** — il faut lire **effectId 125 (Vitalité) = 42**.
Vérifié : Rune Sa (GID 1521, poids 1, effectId 124) fait passer Sagesse
23 → 24 ; Rune Pa Sa (GID 1546, poids 3) 24 → 27.

### Runes identifiées (session)

| GID | Rune | Poids | effectId |
|-----|------|-------|----------|
| 1521 | Rune Sa | 1 | 124 Sagesse |
| 1546 | Rune Pa Sa | 3 | 124 Sagesse |
| 7433 | Rune Cri | 1 | 115 Critique |
| 7458 | Rune Ré Per Air | 1 | 212 |
| 7459 | Rune Ré Per Terre | 1 | 210 |
| 11639 | Rune Tac | 1 | 753 Tacle |
| 11641 | Rune Ré Pa | 1 | 160 |
| 11654 | Rune Pa Do Cri | 3 | 418 Do Cri |

### Mécanique observée (24 poses)

- **Succès** : la stat visée augmente du poids de la rune (ex. Sagesse +3).
- **Échec** : la stat visée reste identique ou **diminue**, et d'autres stats
  de l'item baissent aléatoirement (ex. Vitalité 392 → 330 sur la session ;
  Rune Cri : Critique 6 → 4).
- Une stat tombée à 0 **disparaît** de la liste d'effets du paquet.
- `état` (0-2) et `puits` (float) varient à chaque rune ; le puits est
  affiché tel quel dans l'UI de forgemagie (confirmé par observation le
  2026-08-20 : valeur du paquet = valeur affichée, virgule comprise).
- effectId 421 (Rés. Critiques) : la base donne −16 à −20, le paquet porte la
  **magnitude positive** (16) — le signe vient de la définition de l'effet.
- **Détection automatique des malus** : `fetch_runes.py --malus` sonde les
  effectIds dofusdb (0-4000) et écrit `effects.json` — les **112 malus**
  (characteristicOperator = "-") sont chargés par `fm_decoder.py`/`fm_panel.py`
  pour afficher les stats négatives avec le bon signe (ex. « Critique (malus) -11 »),
  quelle que soit la caractéristique.

### Validation par les simulateurs communautaires (2026-08-20)

Sources : `zoezenKebab/gdFM` (simulateur Godot, mécanique + `STATS_TABLE`) et
`lilgallon/dofus-tools` (calculateur de puit, `js/runes.js`). Ces projets
modélisent la FM Dofus (thème 1.29/2.x) — la logique est indépendante du client.

**Stats ajoutées par rune — correspondance exacte avec nos paquets :**

| Rune | Paquet (f4) | gdFM `STATS_TABLE` |
|------|-------------|--------------------|
| Rune Sa | 1 | `sa` base stat = 1 |
| Rune Pa Sa | 3 | `sa` pa stat = 3 |
| Rune Cri | 1 | `cri` base stat = 1 |
| Rune Ré Per Air / Terre | 1 | `re_per_air` / `re_per_ter` base = 1 |
| Rune Tac | 1 | `tac` base stat = 1 |
| Rune Ré Pa | 1 | `re_pa` base stat = 1 |
| Rune Pa Do Cri | 3 | `do_cri` pa stat = 3 |

**Mécanique à 3 issues** (gdFM `puit_controller.gd`) — explique nos
observations :

- `sc` **succès critique** : la rune s'ajoute, **aucune autre stat ne bouge**
  (correspond à nos `état=0` où seul l'effet visé change, ex. lignes 6 et 8) ;
- `sn` **succès neutre** : la rune s'ajoute **et** d'autres stats perdent du
  poids (retrait pondéré par densité — nos cas « +1 sur la stat, −1 ailleurs ») ;
- `ec` **échec critique** : la rune ne s'ajoute pas, d'autres stats perdent du
  poids (notre ligne 2 : rien ne change, `état=2`) ;
- les stats ≤ 0 sont exclues du retrait et **disparaissent** de la liste ✓ ;
- garde-fou anti-négatif (le retrait s'arrête avant de passer sous 0) ✓ ;
- stats au-delà du jet théorique (over) : retrait ×4 de bonus.

**Poids / puit** (dofus-tools `runes.js`, gdFM `item_controller.gd`) : chaque
stat a une **densité** (Sa = 3, Pa Sa = 9, Vi = 1, Pui = 2, Do Cri = 5,
Cri = 10, Ré Per = 6, Ré Pa = 7, Tac = 4, PA = 100…) ; le « puit » est le
budget de poids de l'item ; la densité n'est **pas** envoyée dans les paquets
(seule la stat ajoutée `f4` l'est). Le float `f3` de `kdr` = le **puits**
affiche dans l'UI de forgemagie (confirme par observation UI ; décimal en
Dofus 3, ex. 2.8, contrairement au puit entier de Dofus 2). La règle de mise
à jour du puits (quand/comment il bouge selon succès/échec) reste à
confirmer par corrélation UI (session `--fm` + marqueurs).
Bonus : le simulateur gdFM inclut l'**Amulette du Strigide** parmi ses items —
même objet que notre session de validation.

### Prix moyens des runes — message `ivi` (identifié le 2026-08-20)

Capturé à l'ouverture de l'UI FM (session `--fm`) puis confirmé **au login**
(capture complète, port 5555). Le client affiche le prix moyen dans le tooltip
de l'UI FM — cette donnée vient d'un **message serveur**, pas de la mémoire :

```
type_url: ivi   (s2c, à la CONNEXION — ~5 s après l'entrée dans le monde,
                 PAS à l'ouverture de l'UI FM : l'UI FM ne déclenche aucun
                 message de prix, le client affiche la table reçue au login)
payload  : f2 répété ×N : { f1 = gid, f2 = prix moyen }
```

- Session login du 2026-08-20 : **7 677 paires** `{gid → prix moyen}`,
  69 Ko — équivalent Dofus 3 de `ObjectAveragePricesMessage` (Dofus 2,
  `Chuckame/dofus-protocol`, id 6335) ;
- **Runes présentes** : Rune Fo 69, Rune Cha 43, Rune Vi 211, Rune Pa Sa 704,
  Rune Pa Vi 2 226… (prix moyens cohérents avec le marché) ;
- **Items absents = pas de prix** : `18448` (Grains de Sable, objet de quête)
  absent ✓ — permet de détecter « jamais vu à l'HDV » ;
- **Couple `iwo`/`kgq`** : `iwo {f1=gid, f2=…}` (c2s) → `kgq {f1=prix}` (s2c),
  présent à l'ouverture de l'UI FM — probablement **demande ponctuelle de prix
  moyen par item** (équivalent `ExchangeBidPriceMessage` 5755) ; à confirmer
  (le seul couple capturé demande le gid 18448 → réponse 168, non-rune).
- ⚠️ **Gids `11622` / `18448` absents de `runes.json`** (96 entrées) : ce sont
  des **items**, pas des runes — vérifier le hook FM qui les affiche comme
  « rune » (bug d'étiquetage : `11622` = Anneau Nobstant, lvl 146).

Pour le coût d'une session FM : `Σ(qté rune × prix moyen gid)` — la table
`ivi` du login sert de référence prix (à rafraîchir à chaque login, les prix
moyens bougent).

### Outils

```
python fm_live.py live --out _scratch/capture        # capture + journal JSONL
python fm_decoder.py captures/fm_2026-08-20.jsonl    # rapport FM lisible
```

## Limites / maintenance

- Noms de messages et numéros de champs **obfusqués et versionnés** : à
  revérifier à chaque mise à jour du jeu (dump IL2CPP pour les offsets mémoire).
- Le champ `f4` (stats) et les petites valeurs du blob `kda` restent à
  documenter précisément.
- `iun` / `irq` / le flag de `ivj` / `état` / la règle de mise à jour du
  puits : sémantique exacte à confirmer (les valeurs + corrélations sont
  documentées ci-dessus).
- **Prix moyens des runes (canal réseau)** : le client affiche le prix moyen
  dans l'UI FM ; en protocole Dofus 2 c'est `ObjectAveragePricesMessage`
  (id 6335, liste `ids[]` + `avgPrices[]`, demandé par `ObjectAveragePricesGetMessage`
  id 6334 au login) et `ExchangeBidPriceMessage` (id 5755, `{genericId,
  averagePrice}` par item) — cf. `Chuckame/dofus-protocol`. L'équivalent Dofus 3
  (obfusqué) **n'est pas encore identifié** : absent de nos captures car elles
  démarrent en milieu de session. À capturer dès le login (ou à l'ouverture de
  l'UI forge/HDV) : chercher le gros message protobuf à champs répétés
  `{gid → prix}` et le croiser avec `runes.json` pour le coût des runes.
- Rappel : le sniffing est **passif**, mais l'automatisation (trading, clics)
  reste dans la zone grise des CGU Ankama (« bots / auto-clics »).
