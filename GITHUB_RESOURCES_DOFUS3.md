# Ressources GitHub — FM & sniffing de paquets (orienté Dofus 3)

> Compilation du 2026-08-20. Contexte : **client Dofus 3 (Unity/IL2CPP)**, projet
> de lecture HDV/FM par sniffing passif (voir `PROTOCOL.md` pour le protocole
> Dofus 3 : port 5555 en clair, protobuf, noms de messages obfusqués `kbt`, `kda`…).
>
> ⚠️ Point clé : la quasi-totalité des sniffers/bots publics ciblent **Dofus 2.x**
> (ancien protocole : framing par message ID, chiffrement, clients AIR/Flash puis
> Dofus Invoke). **Seuls 2 repos annoncent Dofus 3 (Unity)**. Les autres restent
> précieux comme **référence d'architecture** (sniffing passif vs MITM, décodage,
> loop FM) mais ne fonctionnent pas tels quels.

---

## 1. Sniffing de paquets

### Dofus 3 (Unity) ✅

| Repo | ★ | Lang | Ce que c'est |
|---|---|---|---|
| [Vicfou-dev/dofus-fm-server](https://github.com/Vicfou-dev/dofus-fm-server) | 3 | – | **« Automatise ta Forgemagie sur Dofus 3.0 »** — bot FM payant (4.99–19.99€/exos), repo public = landing + serveur. Confirme le ciblage **Dofus 3 Unity** et l'approche **clics souris réels + lecture écran** (pas d'injection, pas de modification de fichiers). Aucun code de sniffing public. |

→ Il n'existe **aucun sniffer Dofus 3 open-source public** trouvé. Les captures
`pcaps/dofus.pcap` + notes `PROTOCOL.md` de ce workspace constituent la base
actuelle.

### Dofus 2.x — référence d'architecture (⚠️ protocole différent)

| Repo | ★ | Lang | Ce que ça apprend |
|---|---|---|---|
| [viclew1/VLDofusBot](https://github.com/viclew1/VLDofusBot) | 65 | Kotlin (npcap) | **Sniffer/MITM & pixel bot**. Le plus complet : interception des paquets, décodage, émulation clic. **DISCONTINUED** (code passé privé, site vldbot.com). Architecture de référence : « sniff + simulate clicks, aucun message envoyé au serveur ». |
| [Adwelean/VLDofusBotSniffer](https://github.com/Adwelean/VLDofusBotSniffer) | – | Kotlin | Partie sniffer extraite de VLDofusBot : « mimic the Dofus network and class hierarchy, every message converted to a Java object, stored in an EventStore ». Pédagogique pour la couche de décodage/mapping. |
| [bot4dofus/B4D](https://github.com/bot4dofus/B4D) | 23 | Java (pcap4j) | Pixel bot Dofus 2 avec **packet sniffing (pcap4j)** + émulation clavier/souris. **Wiki détaillé** (liens dans le repo) : bon point d'entrée conceptuel. MIT. |
| [BlueDream145/AmaknaCore-Sniffer](https://github.com/BlueDream145/AmaknaCore-Sniffer) | 21 | C# | « Game Sniffer for Desktop Dofus 2.0+ » — sniffer autonome, plus simple à lire. |
| [AxelConceicao/dofus-sniffer](https://github.com/AxelConceicao/dofus-sniffer) | 9 | Python + Scapy | **Sniffer passif, sans MITM** (« no MITM »). Le plus proche de notre approche (sniffing passif) — utile pour le framing/assemblement TCP. |
| [Miou-zora/SniffSniff](https://github.com/Miou-zora/SniffSniff) | – | Go | Sniffer Dofus 2 + traducteur + sauvegarde des prix d'items. MIT. |
| [Chuckame/dofus-sniffer-webui](https://github.com/Chuckame/dofus-sniffer-webui) | – | Vue | Intercepte les paquets et les affiche sur une UI dédiée — bon pour visualiser le trafic pendant le dev. |

---

## 2. La FM elle-même (mécaniques, simulateurs, calculateurs)

| Repo | ★ | Lang | Ce que c'est |
|---|---|---|---|
| [zoezenKebab/gdFM](https://github.com/zoezenKebab/gdFM) | 1 | GDScript (Godot) | **Simulateur de forgemagie de Dofus** — utile pour valider/confirmer les règles FM (impact d'une rune, poids, chances) indépendamment de la version du client. |
| [lilgallon/dofus-tools](https://github.com/lilgallon/dofus-tools) | 1 | JS/HTML | Site d'outils dont un **calculateur de forgemagie** (`forgemagie.html`, page GitHub Pages). MIT. |
| [Yassine9100/Dofus-Forgemagie-Calculator](https://github.com/Yassine9100/Dofus-Forgemagie-Calculator) | – | C# | Calculateur FM. MIT. |
| [Yassine9100/LaForge](https://github.com/Yassine9100/LaForge) | – | – | « Assistant de forgemagie pour le MMORPG Dofus v2.5 ». GPL-3.0. |
| [Gguignard/dofus-management](https://github.com/Gguignard/dofus-management) | – | HTML | Craft + forgemagie + XP familier dans une page, référentiel de prix partagé. |

> Les règles FM (mécaniques de runes) sont **indépendantes du protocole** : les
> simulateurs/calculateurs restent valables sur Dofus 3 pour la logique métier
> (quel rune tenter, quand s'arrêter).

---

## 3. Bots FM (approches globales)

| Repo | ★ | Lang | Approche | Dofus 3 ? |
|---|---|---|---|---|
| [vDAKK/stakk](https://github.com/vDAKK/stakk) | 11 | – | « Multi sur serveur mono, **bot FM**, overlay récolte, organizer ». Topics : `dofus-retro`, `multiaccount`. | ❌ plutôt Retro |
| [Vicfou-dev/dofus-fm-server](https://github.com/Vicfou-dev/dofus-fm-server) | 3 | – | Bot FM **Dofus 3.0** : IA de décision par rune, background click, multi-sessions, exos PA/PM/PO/Invocation. **Commerçant fermé** — pas de code utile, mais référence de produit + approche « safe » (clics réels, lecture écran). | ✅ **Dofus 3** |
| [NicolasIRAGNE/DofusBotFM](https://github.com/NicolasIRAGNE/DofusBotFM) | 1 | C++ | Bot FM (code minimal). | ❌ |
| [LittleTatsumi/fm-bot](https://github.com/LittleTatsumi/fm-bot) | – | Python | « Développement d'un bot dofus pour la forgemagie » (squelette). | ❌ |
| [VictorKrum0/LeBot](https://github.com/VictorKrum0/LeBot) | 1 | AutoIt | Bot FM. | ❌ |
| [Bazaltic/dofus_bot_fm](https://github.com/Bazaltic/dofus_bot_fm) | – | – | Bot FM (repo non documenté). | ❌ |
| [Plogeur/Forgemagie](https://github.com/Plogeur/Forgemagie) | 1 | Python | – | ❌ |

---

## 4. Ce qu'il faut en retenir pour notre projet (Dofus 3)

1. **Aucun sniffer Dofus 3 open-source public** n'existe à ce jour → le travail
   de `PROTOCOL.md` + `sniffer_hdv.py` (port 5555, protobuf en clair, framing
   varint, enveloppe `type_url`) est la référence locale à faire évoluer.
2. **Le protocole Dofus 2 ≠ Dofus 3** : les repos Dofus 2 servent pour
   l'*architecture* (sniff passif vs MITM, couche de décodage → objets métier →
   EventStore) et le *pipeline* (pcap/live → parser → annonces/prix), pas pour
   les formats de trame.
3. **Trois stratégies documentées dans la communauté** :
   - *Sniffing passif* (AxelConceicao, notre approche actuelle) — le plus
     discret, lecture seule ;
   - *MITM* (VLDofusBot) — interception entre client et serveur, plus invasif,
     permet de réécrire le trafic ;
   - *Lecture mémoire / écran* (dofus-fm-server) — lire les objets en mémoire
     (nous avons déjà validé `id@+0x10`, `price@+0x20`, `qty@+0x28`) ou
     simuler des clics.
4. **La logique FM** (simulateurs gdFM, calculateurs) est **réutilisable
   telle quelle** : elle ne dépend pas du client.
5. ⚠️ **CGU Ankama** : le sniffing passif est lecture seule ; l'automatisation
   (trading, clics) reste dans la zone grise — cf. avertissements de
   `PROTOCOL.md` et des repos eux-mêmes.

---

## 5. Liens utiles non-GitHub (trouvés via ces repos)

- Wiki B4D : <https://github.com/bot4dofus/B4D/wiki>
- Site vldbot.com (VLDofusBot, discontinué mais documentation) : <https://vldbot.com>
- DofusFM (bot Dofus 3, site produit) : <https://web.dofus-fm.cloud>
