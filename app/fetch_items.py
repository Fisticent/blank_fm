#!/usr/bin/env python3
"""
fetch_items.py — Base locale des items EQUIPEMENT de Dofus 3 (jet mini->maxi).

Source : API DofusDude (api.dofusdu.de, dofus3, categorie `equipment`) — tous
les items en 1 requete. Pour chaque item on garde :
    items.json[gid] = {
        "name":   nom,
        "level":  niveau requis,
        "effects": { effectId_dofusdb: [mini, maxi] }   # numerotation des paquets
    }

Le lien DofusDude -> effectId des paquets se fait par NOM de stat, via la table
construite depuis runes.json + les effectIds connus (voir build_effectid_map).
Les lignes sans effectId connu (ex. "Fertile", "-special spell-") sont ignorees.

Usage :
    python fetch_items.py                # telecharge et ecrit items.json
    python fetch_items.py --stats        # affiche la couverture nom->effectId

NB : les malus (ex. "Res. Critiques -16 a -20") sont stockes tels quels dans
items.json ; c'est le rapport fm_decoder qui les exclut du % du jet global.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import urllib.request
from collections import Counter

from paths import data_file

DUDE = "https://api.dofusdu.de/dofus3/v1/fr/items/equipment/all"
HEADERS = {"User-Agent": "dofus-fm/1.0"}
OUT = data_file("items.json")

# effectIds dofusdb (numerotation des paquets) connus par nom de stat.
# Priorite : runes.json (effect_name -> effectId) puis cette table manuelle.
EFFECTID_BY_NAME: dict[str, int] = {
    "PA": 111, "PM": 128, "Portee": 117, "Initiative": 174, "Prospection": 176,
    "Pods": 158, "Vitalite": 125, "Sagesse": 124, "Chance": 123, "Agilite": 119,
    "Intelligence": 126, "Force": 118, "Puissance": 138, "Tacle": 753,
    "Fuite": 752, "Critique": 115, "Soin": 116, "Dommage": 112,
    "Dommage Air": 428, "Dommage Eau": 426, "Dommage Feu": 424,
    "Dommage Terre": 422, "Dommage Neutre": 430, "Dommage Poussee": 414,
    "Dommage Critiques": 418, "Dommage Puit": 415, "Dommage Renvoi": 114,
    "Retrait PA": 410, "Retrait PM": 412, "Esquive PA": 91, "Esquive PM": 92,
    "Resistance Poussee": 416, "Resistance Critiques": 420,
    "% Resistance Air": 212, "% Resistance Eau": 211, "% Resistance Feu": 213,
    "% Resistance Terre": 210, "% Resistance Neutre": 214,
    "Resistance Air": 242, "Resistance Eau": 241, "Resistance Feu": 240,
    "Resistance Terre": 243, "Resistance Neutre": 244,
    "Re Pa": 160, "Re Pme": 152, "Ret Pa": 182, "Ret Pme": 183,
    "Tacle %": 754, "Fuite %": 755,
    # variantes de casse/utilisees par DofusDude (apres normalisation)
    "dommages neutre": 430, "dommages feu": 424, "dommages eau": 426,
    "dommages terre": 422, "dommages air": 428, "dommages critiques": 418,
    "dommage puit": 415, "resistance poussee": 416, "resistance critiques": 420,
}

# stats qui existent en version positive ET en malus : quand DofusDude donne
# des valeurs negatives, le paquet porte l'effectId malus (MALUS_EFFECTS).
MALUS_EFFECTID_BY_NAME: dict[str, int] = {
    "resistance critiques": 421,   # 420 = positif, 421 = malus (paquet)
    "critique": 171,               # 115 = positif, 171 = malus (paquet)
}


def norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower().strip()


def build_effectid_map() -> dict[str, int]:
    """nom normalise -> effectId : runes.json d'abord, puis table manuelle."""
    m: dict[str, int] = {}
    try:
        with open(data_file("runes.json"), encoding="utf-8") as f:
            runes = json.load(f)
        for d in runes.values():
            if d.get("effect_name") and d.get("effectId"):
                m.setdefault(norm(d["effect_name"]), d["effectId"])
    except (OSError, ValueError):
        pass
    for name, eid in EFFECTID_BY_NAME.items():
        m.setdefault(norm(name), eid)
    return m


def fetch_all() -> list[dict]:
    """Tous les equipements DofusDude (suit les liens next si presents)."""
    items: list[dict] = []
    url = DUDE + "?page[size]=1000&page[number]=0"
    seen = set()
    while url and url not in seen:
        seen.add(url)
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode())
        batch = d.get("items") or []
        items.extend(batch)
        nxt = (d.get("_links") or {}).get("next")
        print(f"  {len(batch):>5} items  (total {len(items)})", flush=True)
        url = nxt if nxt else None
        if url:
            url = url + ("" if "page[number]" in url else "?page[number]=1")
    return items


def build_db(items: list[dict], emap: dict[str, int]) -> tuple[dict, Counter]:
    db: dict[str, dict] = {}
    unmapped = Counter()
    for it in items:
        gid = str(it.get("ankama_id"))
        if not gid:
            continue
        effects: dict[str, list[int]] = {}
        for e in it.get("effects") or []:
            t = e.get("type") or {}
            name = t.get("name")
            lo, hi = e.get("int_minimum"), e.get("int_maximum")
            if name is None or lo is None or hi is None:
                continue
            eid = emap.get(norm(name))
            if eid is None:
                unmapped[name] += 1
                continue
            # malus : les valeurs negatives portent l'effectId malus du paquet
            if lo < 0 and hi < 0:
                eid = MALUS_EFFECTID_BY_NAME.get(norm(name), eid)
            # normalise l'ordre (les malus ont min > max chez dofusdb)
            effects[str(eid)] = [min(lo, hi), max(lo, hi)]
        if not effects:
            continue
        entry: dict = {
            "name": it.get("name"),
            "level": it.get("level"),
            "effects": effects,
        }
        # icône d'item (URL DofusDude 64px) — affichée par l'UI
        icon = (it.get("image_urls") or {}).get("icon")
        if icon:
            entry["icon"] = icon
        db[gid] = entry
    return db, unmapped


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stats", action="store_true",
                    help="affiche la couverture nom->effectId puis quitte")
    args = ap.parse_args(argv)

    emap = build_effectid_map()
    if args.stats:
        print(f"table nom->effectId : {len(emap)} stats")
        for n in sorted(emap):
            print(f"  {n:<24} -> {emap[n]}")
        return 0

    print("telechargement des equipements DofusDude...")
    items = fetch_all()
    print(f"{len(items)} equipements recus")
    db, unmapped = build_db(items, emap)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(db)} items avec stats -> {OUT}")
    if unmapped:
        top = unmapped.most_common(8)
        print("lignes ignorees (pas d'effectId) :",
              ", ".join(f"{n} x{c}" for n, c in top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
