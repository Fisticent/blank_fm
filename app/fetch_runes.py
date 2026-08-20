#!/usr/bin/env python3
"""
fetch_runes.py — Construit la table de correspondance des runes (GID -> nom,
effectId, valeur ajoutee) depuis l'API dofusdb.fr (items/{gid}).

L'API de collection etant desactivee, on scanne des plages de GIDs et on
garde les items typeId == 78 (Rune de forgemagie). Resultats :
    runes.json   — table brute (gid -> {nom, effectId, valeur, niveau, icone})
    runes.md     — table markdown lisible (triee par stat puis valeur)

Usage :
    python fetch_runes.py                # scan des plages par defaut
    python fetch_runes.py 1500 1600      # scan d'une plage supplementaire
    python fetch_runes.py --probe 1500 1580

Donnees issues de DofusDB. Utilisation soumise a la LPNC-IA 1.0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from paths import data_file

API = "https://api.dofusdb.fr/items/{gid}"
API_EFFECTS = "https://api.dofusdb.fr/effects/{eid}"
HEADERS = {"User-Agent": "dofus-fm/1.0 (lecture encyclopedie)", "Accept": "application/json"}
WORKERS = 12
SLEEP = 0.0

# Plages par defaut (clusters connus de GIDs de runes)
DEFAULT_RANGES = [(1500, 2150), (7350, 7850), (11400, 12200), (19600, 20600)]

# API DofusDude (liste complete en 1 requete)
DUDE_ALL = "https://api.dofusdu.de/dofus3/v1/fr/items/resources/all"
DUDE_TYPE_RUNE = 133   # "Rune de forgemagie" (numerotation DofusDude)

# Plage des identifiants d'effets dofusdb a sonder pour detecter les malus
EFFECTS_RANGE = (0, 4000)

# Noms attendus (d'apres l'encyclopedie / dofus-tools) pour valider la couverture
EXPECTED_NAMES = {
    "Rune Fo", "Rune Sa", "Rune Ine", "Rune Vi", "Rune Age", "Rune Cha",
    "Rune Ini", "Rune Po", "Rune Prospe", "Rune Fui", "Rune Tac", "Rune So",
    "Rune Cri", "Rune Do", "Rune Do Air", "Rune Do Eau", "Rune Do Feu",
    "Rune Do Neutre", "Rune Do Terre", "Rune Do Pou", "Rune Do Cri",
    "Rune Do Ren", "Rune Do Per Ar", "Rune Do Per Di", "Rune Do Per Me",
    "Rune Do Per So", "Rune Re Terre", "Rune Re Feu", "Rune Re Eau",
    "Rune Re Air", "Rune Re Neutre", "Rune Re Pou", "Rune Re Cri",
    "Rune Re Pa", "Rune Re Pme", "Rune Ret Pa", "Rune Ret Pme",
    "Rune Re Per Terre", "Rune Re Per Feu", "Rune Re Per Eau",
    "Rune Re Per Air", "Rune Re Per Neutre", "Rune Re Per Me",
    "Rune Re Per Di", "Rune Pod", "Rune Pi", "Rune Pi Per", "Rune Invo",
    "Rune Puit", "Rune Ga Pa", "Rune Ga Pme", "Rune de chasse",
}

# Poids de forgemagie par stat (densites communauteaires, cf. FM_FONCTIONNEMENT.md)
# cle = nom de la stat (suffixe de la rune) ; valeur = (base, pa, ra)
STAT_WEIGHTS: dict[str, tuple[float, float | None, float | None]] = {
    "Fo": (1, 3, 10), "Ine": (1, 3, 10), "Cha": (1, 3, 10), "Age": (1, 3, 10),
    "Vi": (2, 3, 10), "Ini": (1, 3, 10), "Sa": (3, 9, 30), "Prospe": (3, 9, None),
    "Pui": (2, 6, 20), "Pod": (2.5, 7.5, 25),
    "Re Terre": (2, 6, None), "Re Eau": (2, 6, None), "Re Air": (2, 6, None),
    "Re Feu": (2, 6, None), "Re Neutre": (2, 6, None),
    "Re Cri": (2, 6, None), "Re Pou": (2, 6, None),
    "Re Pa": (7, 21, None), "Re Pme": (7, 21, None),
    "Ret Pa": (7, 21, None), "Ret Pme": (7, 21, None),
    "Re Per Terre": (6, None, None), "Re Per Eau": (6, None, None),
    "Re Per Air": (6, None, None), "Re Per Feu": (6, None, None),
    "Re Per Neutre": (6, None, None), "Re Per Di": (15, None, None),
    "Re Per Me": (15, None, None),
    "Tac": (4, 12, None), "Fui": (4, 12, None),
    "Do": (20, None, None),
    "Do Cri": (5, 15, None), "Do Terre": (5, 15, None), "Do Feu": (5, 15, None),
    "Do Eau": (5, 15, None), "Do Air": (5, 15, None), "Do Neutre": (5, 15, None),
    "Do Pou": (5, 15, None), "Do Pi": (5, 15, None),
    "Do Ren": (5, None, None), "So": (10, 30, None), "Cri": (10, None, None),
    "Do Per Ar": (15, None, None), "Do Per Di": (15, None, None),
    "Do Per Me": (15, None, None), "Do Per So": (15, None, None),
    "Invo": (30, None, None), "Po": (51, None, None),
    "Ga Pme": (90, None, None), "Ga Pa": (100, None, None),
    "Pi": (5, 15, None), "Pi Per": (2, 6, 20), "Per Pi": (2, 6, 20),
    "Chasse": (5, None, None),
}


def _deaccent(s: str) -> str:
    return (s.replace("é", "e").replace("è", "e").replace("ê", "e")
             .replace("É", "E").replace("à", "a").replace("ô", "o"))


def rune_weight(name: str) -> float | None:
    """Poids de forgemagie d'une rune depuis son nom (densite x rang)."""
    n = name.replace("Rune ", "").strip()
    # cas speciaux : Ga Pa / Ga Pme (stat = PA/PM) et Rune de chasse
    if n == "Ga Pa":
        return 100
    if n == "Ga Pme":
        return 90
    if n == "de chasse":
        n = "Chasse"
    prefix, stat = None, n
    for p in ("Pa ", "Ra "):
        if n.startswith(p):
            prefix = p.strip()
            stat = n[len(p):]
            break
    w = STAT_WEIGHTS.get(_deaccent(stat))
    if not w:
        return None
    if prefix == "Pa":
        return w[1]
    if prefix == "Ra":
        return w[2]
    return w[0]


def fetch_effect(eid: int) -> dict | None:
    try:
        req = urllib.request.Request(API_EFFECTS.format(eid=eid), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def fetch(gid: int) -> dict | None:
    try:
        req = urllib.request.Request(API.format(gid=gid), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def scan(ranges: list[tuple[int, int]], out_json: str, out_md: str) -> int:
    runes: dict[int, dict] = {}
    try:  # merge avec la table deja generee (relances partielles)
        with open(out_json, encoding="utf-8") as f:
            runes = {int(k): v for k, v in json.load(f).items()}
    except (OSError, ValueError):
        pass
    all_gids = [g for lo, hi in ranges for g in range(lo, hi + 1)]
    total = len(all_gids)
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch, g): g for g in all_gids}
        for fut in as_completed(futs):
            gid = futs[fut]
            done += 1
            d = fut.result()
            if d and d.get("typeId") == 78:
                eff = (d.get("possibleEffects") or [{}])[0]
                runes[gid] = {
                    "name": d["name"]["fr"],
                    "effectId": eff.get("effectId"),
                    "value": eff.get("diceNum"),
                    "level": d.get("level"),
                    "icon": d.get("iconId"),
                }
            if done % 500 == 0:
                print(f"  {done}/{total} GIDs, {len(runes)} runes", flush=True)
            if done % 1000 == 0:
                _write(runes, out_json, out_md)   # incremental : survit aux crashes
    _write(runes, out_json, out_md)
    return len(runes)


def fetch_dude(out_json: str, out_md: str) -> int:
    """Liste complete des runes via DofusDude (1 requete), fusionnee avec les
    effectIds dofusdb deja connus (numerotation des paquets)."""
    req = urllib.request.Request(DUDE_ALL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    items = data.get("items", [])
    runes: dict[int, dict] = {}
    for it in items:
        t = it.get("type") or {}
        if t.get("id") != DUDE_TYPE_RUNE:
            continue
        eff = (it.get("effects") or [{}])[0]
        runes[int(it["ankama_id"])] = {
            "name": it["name"],
            "level": it.get("level"),
            "value": eff.get("int_minimum"),
            "effect_name": (eff.get("type") or {}).get("name"),
        }
    # Regle DPLN : une variante Pa/Ra sans poids dans la table n'existe pas
    # (les GIDs correspondants dans les donnees DofusDude sont residuels).
    before = len(runes)
    artifacts = sorted(g for g, d in runes.items()
                       if _is_pa_ra(d["name"]) and rune_weight(d["name"]) is None)
    if artifacts:
        print("exclues (n'existent pas selon DPLN) :",
              ", ".join(f"{g} {runes[g]['name']}" for g in artifacts), flush=True)
    for g in artifacts:
        del runes[g]
    old: dict[int, dict] = {}
    try:
        with open(out_json, encoding="utf-8") as f:
            old = {int(k): v for k, v in json.load(f).items()}
    except (OSError, ValueError):
        pass
    # effectId dofusdb (numerotation des paquets) pour les runes sans effectId
    for gid in sorted(g for g in runes if not (old.get(g) or {}).get("effectId")):
        d = fetch(gid)
        if d and d.get("typeId") == 78:
            eff = (d.get("possibleEffects") or [{}])[0]
            old[gid] = {"effectId": eff.get("effectId"), "icon": d.get("iconId")}
            print(f"  effectId dofusdb: {gid} {runes[gid]['name']} -> "
                  f"{eff.get('effectId')}", flush=True)
    # effectId dofusdb par nom d'effet (pour les runes inconnues du scan)
    name_to_eff = {}
    for gid, r in old.items():
        if r.get("effectId"):
            name_to_eff.setdefault(_norm(r.get("effect_name") or ""), r["effectId"])
    merged: dict[int, dict] = {}
    for gid, d in runes.items():
        o = old.get(gid) or {}
        merged[gid] = {
            "name": d["name"],
            "effectId": o.get("effectId") or name_to_eff.get(_norm(d.get("effect_name") or "")),
            "value": o.get("value", d.get("value")),
            "level": d.get("level"),
            "icon": o.get("icon"),
            "effect_name": d.get("effect_name"),
        }
    _write(merged, out_json, out_md)
    new_gids = sorted(set(runes) - set(old))
    lost = sorted(set(old) - set(runes))
    print(f"DofusDude : {len(runes)} runes retenues (brut {before}, "
          f"scan dofusdb : {len(old)})")
    if new_gids:
        print("runes nouvelles (absentes du scan dofusdb) :", new_gids)
    if lost:
        print("GIDs dofusdb absents de DofusDude :", lost)
    return len(runes)


def _is_pa_ra(name: str) -> bool:
    return name.startswith("Rune Pa ") or name.startswith("Rune Ra ")


def fetch_malus_effects(out_json: str) -> int:
    """Son d les effectIds dofusdb et construit la liste des MALUS.

    Un malus = effect dont characteristicOperator == "-" (le paquet porte la
    magnitude positive, le signe vient de la definition). Ecrit effects.json :
        {"malus": [ids...], "names": {id: nom_fr}, "total": n}
    """
    import re
    lo, hi = EFFECTS_RANGE
    all_ids = list(range(lo, hi + 1))
    malus: list[int] = []
    names: dict[int, str] = {}
    total = 0
    done = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_effect, g): g for g in all_ids}
        for fut in as_completed(futs):
            eid = futs[fut]
            done += 1
            d = fut.result()
            if not d or "id" not in d:
                continue
            total += 1
            op = d.get("characteristicOperator")
            if op == "-":
                malus.append(eid)
            desc = (d.get("description") or {}).get("fr") or ""
            name = _clean_effect_name(desc)
            if name:
                names[eid] = name + (" (malus)" if op == "-" else "")
            if done % 1000 == 0:
                print(f"  {done}/{len(all_ids)} effets, {total} trouves, "
                      f"{len(malus)} malus", flush=True)
    data = {"malus": sorted(malus), "names": names, "total": total}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{total} effets (id 0-{hi}), {len(malus)} malus -> {out_json}")
    print("malus:", ", ".join(map(str, sorted(malus))))
    return len(malus)


def _clean_effect_name(desc: str) -> str:
    """Nom court depuis la description dofusdb (template FR)."""
    import re
    s = desc or ""
    s = re.sub(r"\{\{.*?\}\}", "", s)      # templates ~1~2
    s = re.sub(r"#\d+", "", s)             # placeholders #1 #2
    s = s.replace("à", " ").replace("-", " ").replace("%", "% ")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.lstrip("% ").strip()
    return s.capitalize() if len(s) > 1 else ""


def _norm(s: str) -> str:
    return s.lower().replace("é", "e").replace("è", "e").replace("ê", "e")


def _norm2(s: str) -> str:
    return s.replace("é", "e").replace("è", "e").replace("ê", "e").replace("É", "E")


def _write(runes: dict[int, dict], out_json: str, out_md: str) -> None:
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(runes, f, ensure_ascii=False, indent=1, sort_keys=True)
    names = {_norm2(r["name"]) for r in runes.values()}
    missing = sorted(EXPECTED_NAMES - names)
    by_effect: dict[int, list[tuple[int, dict]]] = defaultdict(list)
    for gid, r in sorted(runes.items()):
        by_effect[r["effectId"]].append((gid, r))
    lines = [        "# Correspondance des runes de forgemagie (Dofus 3)",
        "",
        "> Genere le 2026-08-20 via `fetch_runes.py` (liste complete DofusDude",
        "> `api.dofusdu.de` + effectIds dofusdb `api.dofusdb.fr`).",
        "> `GID` = identifiant de l'objet dans les paquets ; `valeur` = stat",
        "> ajoutee a l'item ; `effectId` = numerotation dofusdb (celle des",
        "> paquets) ; `poids` = poids de forgemagie (densite x rang) d'apres",
        "> la table dofuspourlesnoobs.com/guide-forgemagie.html (Pa = x3, Ra = x10).",
        "> Regle DPLN : une rune Pa/Ra sans poids dans la table n'existe pas",
        "> (variantes exclues : Ra Re X, Ra Do Pou, Pa Do Ren, presentes dans",
        "> les donnees DofusDude mais residuelles).",
        ">",
        "> Donnees issues de DofusDB. Utilisation soumise a la LPNC-IA 1.0.",
        "",
        f"**{len(runes)} runes** | absentes (runes Dofus 2 non retrouvees en",
        "Dofus 3, probablement retirees par la refonte FM) :",
        f"{', '.join(missing) if missing else 'aucune'}",
        "",
        "| GID | Rune | Stat (effectId) | Valeur | Poids | Niv. |",
        "|-----|------|-----------------|--------|-------|------|",
    ]
    for eid in sorted(by_effect, key=lambda x: x if x is not None else -1):
        label = eid if eid is not None else "-"
        for gid, r in sorted(by_effect[eid], key=lambda x: (x[1]["value"] is None, x[1]["value"] or 0)):
            w = rune_weight(r["name"])
            ws = f"{w:g}" if w is not None else "-"
            lines.append(f"| {gid} | {r['name']} | {label} | {r['value'] or '-'} | {ws} | {r['level']} |")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Table des runes via api.dofusdb.fr")
    ap.add_argument("ranges", nargs="*", type=int,
                    help="plages optionnelles 'lo hi lo hi ...'")
    ap.add_argument("--probe", action="store_true",
                    help="mode sonde : n'affiche que les runes trouvees")
    ap.add_argument("--out", default=os.path.splitext(data_file("runes.json"))[0],
                    help="prefixe de sortie (runes.json/.md)")
    ap.add_argument("--gen-only", action="store_true",
                    help="regenerer runes.md depuis runes.json sans reseau")
    ap.add_argument("--dude", action="store_true",
                    help="liste complete des runes via api.dofusdu.de (1 requete)")
    ap.add_argument("--malus", action="store_true",
                    help="sonder les effectIds dofusdb et ecrire effects.json "
                         "(detection automatique des malus)")
    args = ap.parse_args(argv)

    if args.malus:
        n = fetch_malus_effects(args.out.replace("runes", "effects") + ".json")
        return 0

    if args.dude:
        n = fetch_dude(args.out + ".json", args.out + ".md")
        print(f"{n} runes (DofusDude) -> {args.out}.json / {args.out}.md")
        return 0

    if args.gen_only:
        with open(args.out + ".json", encoding="utf-8") as f:
            runes = {int(k): v for k, v in json.load(f).items()}
        _write(runes, args.out + ".json", args.out + ".md")
        print(f"regenerer depuis runes.json : {len(runes)} runes -> {args.out}.md")
        return 0

    if args.ranges:
        it = iter(args.ranges)
        ranges = list(zip(it, it))
    else:
        ranges = DEFAULT_RANGES

    if args.probe:
        found = []
        for lo, hi in ranges:
            for gid in range(lo, hi + 1):
                d = fetch(gid)
                if d and d.get("typeId") == 78:
                    eff = (d.get("possibleEffects") or [{}])[0]
                    found.append((gid, d["name"]["fr"], eff.get("effectId"),
                                  eff.get("diceNum"), d.get("level")))
        print(f"{len(found)} runes sur {sum(b - a + 1 for a, b in ranges)} GIDs")
        for g in sorted(found):
            print("  ", g)
        return 0

    n = scan(ranges, args.out + ".json", args.out + ".md")
    print(f"{n} runes -> {args.out}.json / {args.out}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
