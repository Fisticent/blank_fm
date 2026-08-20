# Forgemagie (FM) — fonctionnement, poids, puits, succès/neutre/échec

> Document de référence sur les mécaniques de la forgemagie à Dofus, orienté
> pratique (et utile pour un bot FM). Compilé le 2026-08-20.
>
> **Source principale (à jour, Dofus 3.x) :** guide forgemagie de
> dofuspourlesnoobs — poids des runes + Over max :
> <https://www.dofuspourlesnoobs.com/guide-forgemagie.html>
> (site maintenu, suivi des mises à jour Dofus jusqu'à la 3.6).
>
> Sources secondaires (croisées, Dofus 2.x) :
> - table des poids de runes : `lilgallon/dofus-tools` (`js/runes.js`) ;
> - densités par stat et modèle de probabilité : `zoezenKebab/gdFM` (`src/globals.gd`, `src/puit_controller.gd`) ;
> - guide communautaire cité par dofus-tools : guide forgemagie Eclypsia.
>
> ⚠️ **Limite importante** : Ankama ne publie pas les formules exactes de la FM.
> Les **poids de runes et Over max** ci-dessous sont des données du jeu (la
> table DPLN fait foi pour Dofus 3 ; deux valeurs ont changé vs les sources 2.x,
> signalées en note). Les **probabilités et les règles du puits restent des
> modèles communautaires calibrés par observation** — à valider sur Dofus 3
> (Unity) si tu veux les utiliser dans un bot.

---

## 1. Vue d'ensemble

La forgemagie consiste à **modifier les caractéristiques d'un objet** en y
appliquant des **runes**. C'est le seul moyen d'« exotiser » un objet (ajouter
PA, PM, PO…) et d'en améliorer les jets au-delà de ce que le jeu fournit.

Le système repose sur **deux notions centrales** :

1. **Le poids** : chaque stat et chaque rune a un poids. Un objet a une
   « capacité » de poids. Tout ce qui dépasse cette capacité s'appelle le
   **surpoids**, et plus il y a de surpoids, plus la FM devient difficile.
2. **Le puits** : une réserve invisible qui s'accumule sur les échecs et se
   consomme sur les succès. Le puits permet de **compenser le surpoids** et de
   réussir des runes à fort poids (les exos).

---

## 2. Obtenir des runes : le broyage

Les runes s'obtiennent en **broyant des objets** dans un broyeur (métier
Forgemage, atelier).

- **Rendement** : le broyage rend des runes liées aux stats de l'objet broyé
  et à son niveau. Plus l'objet a de stats variées, plus le broyage est rentable.
- **Types de runes obtenues** : runes simples (les plus courantes), runes `Pa`
  (plus rares), runes `Ra` (rares), runes `Ga` (très rares, uniquement PA/PM).
- Pratique courante : on broie des objets **craftés en masse** (souvent des
  items de faible niveau à stats riches) pour alimenter la FM.

---

## 3. Le poids (concept central)

### 3.1 Poids d'une rune

Chaque rune porte un **poids** (fixe). C'est ce poids qui compte pour le puits
et le surpoids — pas la valeur de stat ajoutée.

Table complète (source : dofuspourlesnoobs Dofus 3.x, croisée `runes.js` de dofus-tools) :

| Rune | Poids | | Rune | Poids |
|---|---|---|---|---|
| Rune Ga Pa (PA) | **100** | | Rune Pa Sa | 9 |
| Rune Ga Pme (PM) | **90** | | Rune Pa Prospe | 9 |
| Rune Po (Portée) | **51** | | Rune Pa Pod | 7.5 |
| Rune Invo | 30 | | Rune Pa Pui | 6 |
| Rune Pa So | 30 | | Rune Pa Ré Air/Eau/Feu/Neutre/Terre/Cri/Pou | 6 |
| Rune Do (Dommage) | 20 | | Rune Pa Pi Per | 6 |
| Rune Do Air/Eau/Feu/Neutre/Terre/Cri/Pou | 5 | | Rune Pa Fui | 12 |
| Rune Do Per Ar/Di/Mé/So | 15 | | Rune Pa Tac | 12 |
| Rune Do Ren | **5** | | Rune Pa Pi | 15 |
| Rune Cri | 10 | | Rune Pa Do Air/…/Terre | 15 |
| Rune So | 10 | | Rune Pa Ré Pa / Ré Pme | 21 |
| Rune Sa | 3 | | Rune Pa Ret Pa / Ret Pme | 21 |
| Rune Fo / Ine / Cha / Age | 1 | | Rune Ra (toutes) | 10–30 |
| Rune Vi | **2** | | Rune Ret Pa / Ret Pme | 7 |
| Rune Ini | 1 | | Rune Ré Pa / Ré Pme | 7 |
| Rune Fui | 4 | | Rune Ré Air/…/Pou | 2 |
| Rune Tac | 4 | | Rune Ré Per Di / Mé | 15 |
| Rune Prospe | 3 | | Rune Ré Per Air/…/Terre | 6 |
| Rune Pui | 2 | | Rune Pod | 2.5 |
| Rune Pi | 5 | | Rune Pi Per | 2 |
| Rune Chasse | 5 | | **Rune Pa Vi / Fo / Ine / Cha / Age / Ini** | **3** |

> ℹ️ **Corrections Dofus 3 (vs sources 2.x)** : `Rune Vi` simple = **2** (2.x : 1),
> `Rune Do Ren` = **5** (2.x : 10). `Rune Chasse` = 5. La table DPLN ci-dessus
> fait foi pour le client actuel.

Règles de lecture :
- **Les runes `Pa`** (pa vi, pa fo, …) ont le poids `pa density` de la stat :
  Force/Int/Cha/Agilité/Initiative = 3, Sagesse = 9, Dommages élémentaires = 15…
- **Les runes simples** ont le poids `base density` de la stat.
- **Les exos lourds** sont les runes à fort poids : PA (100), PM (90), Portée (51),
  Invocation (30). C'est pourquoi elles sont si difficiles à poser.

### 3.2 Poids des runes et Over max (jet max) — table à jour Dofus 3.x

Le poids d'une stat sur un objet = **poids simple × valeur**. La colonne
**Over max** = le **plafond absolu de la stat** sur un objet : au-delà, une
rune ne peut plus rien ajouter (issue « neutre »).

Source : dofuspourlesnoobs (Dofus 3.x).

| Stat | Simple | Pa | Ra | Over max |
|---|---|---|---|---|
| PA (Ga Pa) | 100 | – | – | 1 |
| PM (Ga Pme) | 90 | – | – | 1 |
| Portée (PO) | 51 | – | – | 1 |
| Invocation | 30 | – | – | 3 |
| Dommage (Do) | 20 | – | – | 5 |
| % Do Per (Ar/Di/Mé/So) | 15 | – | – | 6 |
| Renvoi dommages (Do Ren) | 5 | – | – | 20 |
| Soin | 10 | 30 | – | 10 |
| Critique % (Cri) | 10 | – | – | 10 |
| Do Neutre/Air/Eau/Feu/Terre, Do Cri, Do Pou, Pi | 5 | 15 | – | 20 |
| Retrait / Esquive PA & PM | 7 | 21 | – | 14 |
| % Résistances (Ré Per Air/…/Terre) | 6 | – | – | 16 |
| % Résistances Distance / Mêlée | 15 | – | – | 6 |
| Résistances élémentaires (Ré Air/…/Pou) | 2 | 6 | – | 50 |
| Tacle / Fuite | 4 | 12 | – | 25 |
| Prospection | 3 | 9 | – | 33 |
| Sagesse | 3 | 9 | 30 | 33 |
| Puissance / Puissance Piège | 2 | 6 | 20 | 50 |
| Force / Int / Cha / Agi | 1 | 3 | 10 | 101 |
| Pods | 2.5 | 7.5 | 25 | 404 |
| Vitalité | **2** | 3 | 10 | 505 |
| Initiative | 1 | 3 | 10 | 1010 |
| Chasse | 5 | – | – | 20 |

Exemple : un objet avec **+30 Force** pèse **30** (30 × poids simple 1),
plafond 101. Un objet avec **+50 Vitalité** pèse **100** (50 × 2 sur Dofus 3),
plafond 505.

### 3.3 Capacité d'un objet, poids actuel, surpoids

- **Capacité** = somme des poids des **stats de base** de l'objet (son « jet »
  à la création, sans FM).
- **Poids actuel** = somme des poids de **toutes** les stats actuelles
  (base + celles ajoutées en FM).
- **Surpoids** = poids actuel − capacité.

Tant que `poids actuel ≤ capacité`, la FM est facile (les runes passent
presque toujours). Dès que l'objet est en **surpoids**, la probabilité de
succès chute : c'est là qu'intervient le puits.

---

## 4. Passer une rune : les issues

Quand on applique une rune, trois issues possibles (dénomination communautaire) :

| Issue | Effet sur l'objet | Effet sur le puits |
|---|---|---|
| **Succès** | La stat augmente de la valeur de la rune. Poids actuel += poids(rune). | Puits −= poids(rune) (min 0) |
| **Neutre** | La rune est consommée **sans effet visible** (stat déjà au max, ou succès « compensé »). | Puits += poids(rune) (selon modèle) |
| **Échec** | La rune est consommée, l'objet **ne change pas**. | **Puits += poids(rune)** |

- **Succès** : c'est le but recherché (sauf quand on « monte le puits »).
- **Échec** : rien n'est retiré à l'objet dans la FM moderne (la refonte a
  supprimé la destruction/le retrait de stats) ; la rune est simplement perdue
  et **le puits augmente de son poids**.
- **Neutre** : cas où la rune « passe » mais la stat visée est **au jet max**
  théorique de l'objet — rien n'est gagné, la rune part dans le puits.
- Variante (modèle du simulateur gdFM, plus conservateur) : il distingue
  **succès critique** (rune posée à pleine valeur), **succès neutre** (rune
  posée mais des stats retirées en compensation) et **échec critique**
  (rune perdue + retrait de stats). C'est une approximation : le jeu moderne
  ne retire plus de stats sur simple échec.

> **Message client** : à l'écran, le résultat s'affiche dans le chat
> (« L'objet gagne +X … » / « L'objet n'a rien gagné »). Pour un bot, on peut
> détecter l'issue en comparant les stats de l'objet **avant/après** la passe.

---

## 5. Le puits

### 5.1 Règles pratiques (modèle communautaire, implémenté par dofus-tools)

1. **Un échec remplit le puits** du poids de la rune échouée.
2. **Un succès consomme le puits** du poids de la rune posée (le puits ne
   descend pas sous 0).
3. Le puits agit comme **capacité virtuelle supplémentaire** : il compense le
   surpoids et « absorbe » le poids des runes à fort poids.
4. Conséquence : **pour tenter un exo**, il faut avoir accumulé un puits
   suffisant (idéalement ≥ poids de la rune à poser).

### 5.2 Exemples chiffrés (issus du calculateur dofus-tools)

- « J'ai perdu 1 PA après avoir passé une rune pa vi » → le puits gagne
  `poids(PA) − poids(pa vi)` = `90 − 3` = **87**. *(Dans ce modèle historique, une
  rune qui fait « sauter » une stat rapporte la différence de poids. Avec les
  poids Dofus 3 — Ga Pa = 100 — ce serait `100 − 3` = 97.)*
- « J'ai 50 de puits, je passe une rune pa vi (poids 3) » → il reste **47**.
- « J'ai 50 de puits, combien de runes ré per air (poids 6) puis-je passer ? »
  → `50 / 6 = 8` runes (reste 2 de puits).

### 5.3 Monter le puits, en pratique

- **Passer des runes sur un objet déjà plein** : elles échouent souvent →
  le puits monte vite. Les runes à fort poids (pa sa, pa do, …) font monter
  le puits plus vite mais coûtent cher.
- **Astuce du calculateur** : le puits se déduit **poids par poids** des runes
  qu'on compte poser ensuite. On « budgète » : `nb_runes_posables =
  floor(puits / poids(rune))`.

---

## 6. Les exos (PA / PM / PO) et le surpoids

Un **exo** = une stat **absente du jet de base** de l'objet, ajoutée en FM
(typiquement PA, PM, Portée, parfois Invocation).

- Poser un exo ajoute son poids **en totalité** au poids de l'objet →
  l'objet part immédiatement en **surpoids**.
- Sans puits, une rune PA (poids 100) sur un objet déjà chargé échoue quasi
  systématiquement. Il faut :
  1. **monter le puits** (échecs volontaires ou naturels sur d'autres stats) ;
  2. puis **tenter l'exo** tant que le puits couvre le poids de la rune ;
  3. si l'exo passe, le puits est consommé d'autant ; si l'objet est
     « repassé » ensuite (on refait des stats), les échecs regonflent le puits
     pour une nouvelle tentative.
- **Poids max par stat** (« jet max » / **Over max**) : plafond absolu par stat
  (table 3.2) — Force/Int/Cha/Agi **101**, Vitalité **505**, Initiative **1010**,
  Pods **404**, Sagesse & Prospection **33**, Tacle/Fuite **25**, Puissance **50**,
  % Résistances **16**, Résistances élémentaires **50**, Dommages élémentaires
  **20**, Dommage **5**, PA/PM/PO **1**, Invocation **3**. Poser une rune au-delà
  du max = **neutre** (rune perdue → puits).

---

## 7. Modèle de probabilité (approximations du simulateur gdFM)

Ankama n'a jamais publié la formule. Le simulateur gdFM modélise la probabilité
d'un **succès critique** comme le **minimum** de 4 facteurs (chacun une courbe
0→1) :

1. **Remplissage de la ligne** : `stat_actuelle / (valeur_rune × 20)` — plus la
   stat est déjà haute, plus c'est dur.
2. **Remplissage max de la ligne** : `(stat / max_stat) / 3` — approcher le jet
   max rend la rune difficile (1 = 3× le max).
3. **Poids de la rune** : `poids / 100` — une Ga Pa (100) est plus dure qu'une
   pa vi (3).
4. **Remplissage de l'objet** : `(poids_item / poids_max) / 2` — un objet
   chargé rend tout plus dur.

Puis : seuil succès critique `sc = facteur_min × 100` ; seuil succès neutre
`sn` (défaut 80) ; le reste = échec critique. Le puits n'est pas intégré dans
cette version du simulateur (WIP) — le modèle communautaire courant consiste à
dire que **le puits déplace le surpoids** : `poids_effectif = poids_actuel −
puits` dans le calcul des chances.

**En résumé qualitatif** : *la probabilité de succès baisse quand l'objet est
plein (surpoids), quand la stat visée est haute ou au max, et quand la rune est
lourde. Le puits compense le surpoids.*

---

## 8. Déroulé pratique d'une FM

1. **Préparer les runes** : broyer des objets (de préférence des items
   « poubelle » à stats riches) → stocker runes simples, `Pa`, `Ra`, `Ga`.
2. **Choisir l'objet** : un item avec de bons jets de base et une capacité
   raisonnable, ou un item « cadeau » à exotiser.
3. **Monter les stats** : tant que l'objet n'est pas en surpoids, passer les
   runes voulues (pa vi, pa fo…) — succès fréquents, coût faible.
4. **Gérer le puits** : suivre puits = Σ(poids des runes échouées) −
   Σ(poids des runes réussies). Utiliser un calculateur de puits.
5. **Tenter l'exo** : quand le puits ≥ poids de la rune d'exo (100 pour PA,
   90 pour PM, 51 pour PO), tenter la passe. Si ça passe → objectif atteint.
   Si ça échoue → le puits a augmenté, on peut retenter.
6. **Repasser** : si une stat utile est « cassée » ou si l'objet part en
   surpoids défavorable, on peut repasser des runes (le puits continue
   d'évoluer à chaque passe).

---

## 9. Lexique

| Terme | Définition |
|---|---|
| Rune simple | Rune de base (poids = poids simple de la stat) |
| Rune Pa | Rune améliorée (poids = colonne Pa de la stat) |
| Rune Ra / Ga | Runes rares (poids élevés ; Ga réservé PA/PM) |
| Over max (jet max) | Plafond absolu d'une stat sur un objet (table 3.2) |
| Poids | Valeur numérique d'une stat/rune, cœur du système FM |
| Capacité | Somme des poids des stats de base de l'objet |
| Surpoids | Poids actuel − capacité |
| Puits | Réserve compensant le surpoids ; + sur échec, − sur succès |
| Exo | Stat absente du jet de base, ajoutée en FM (PA, PM, PO…) |
| Jet max | Plafond d'une stat sur un objet (= Over max, au-delà = neutre) |
| Succès / Neutre / Échec | Les trois issues d'une passe de rune |
| Broyage | Action de réduire un objet en runes |

---

## 10. Sources et limites

- **dofuspourlesnoobs — Guide Forgemagie** (source principale, à jour
  Dofus 3.x — poids des runes + Over max) :
  <https://www.dofuspourlesnoobs.com/guide-forgemagie.html>
- **`lilgallon/dofus-tools`** — calculateur de puits, guide Eclypsia :
  <https://github.com/lilgallon/dofus-tools>
- **`zoezenKebab/gdFM`** — simulateur FM (courbes de probabilité) :
  <https://github.com/zoezenKebab/gdFM>
- **Guide Eclypsia** (référence communautaire Dofus 2.x) :
  <https://www.eclypsia.com/fr/dofus/guides/dofus-guide-forgemagie-21664>

Limites à garder en tête :
- Les **poids et Over max** de la table 3.2 suivent la source Dofus 3.x (DPLN) ;
  les sources 2.x (`dofus-tools`, `gdFM`) divergent sur deux valeurs
  (`Vi` simple 1 vs 2, `Do Ren` 10 vs 5) — DPLN fait foi.
- Les **probabilités** ne sont que des modèles approchés (dont le simulateur
  gdFM). Pour un bot, la stratégie robuste est empirique : lire l'état de
  l'objet **avant/après chaque passe**, et non calculer
  une probabilité théorique.
