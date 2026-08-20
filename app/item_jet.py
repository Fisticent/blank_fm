#!/usr/bin/env python3
"""
item_jet.py — Jet mini/maxi d'un item (template DofusDB) et % du jet.

Le template d'un item (donnees de jeu, API dofusdb.fr/items/{gid]) contient
pour chaque effet le jet possible : effects[] = { effectId, from (mini),
to (maxi) }.

Pour une stat donnee, le % du jet = position de la valeur actuelle entre le
mini et le maxi du template :
    %_jet = (valeur - mini) / (maxi - mini) * 100
  - < 0   : valeur sous le mini (ne devrait pas arriver)
  - 0-100 : jet normal
  - > 100 : FM « over » (depasse le max du template)

Usage :
    python item_jet.py 14094                     # template + % par stat (mini->max)
    python item_jet.py 14094 --value 392         # % du jet pour une valeur
    python item_jet.py --fetch 14094 14161 ...   # remplit le cache

Le cache est ecrit dans item_templates.json (une entree par gid).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Optional

from paths import data_file

API = "https://api.dofusdb.fr/items/{gid}"
HEADERS = {"User-Agent": "dofus-fm/1.0", "Accept": "application/json"}
CACHE = data_file("item_templates.json")
ITEMS_DB = data_file("items.json")


def _load_items_db() -> dict[int, dict[int, tuple[int, int]]]:
    """Base items.json : {gid: {name, level, effects: {eid: [mini, maxi]}}}."""
    if not os.path.exists(ITEMS_DB):
        return {}
    try:
        with open(ITEMS_DB, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    return {int(g): {int(e): tuple(v) for e, v in d.get("effects", {}).items()}
            for g, d in raw.items()}


def load_cache() -> dict[int, dict[int, tuple[int, int]]]:
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            raw = json.load(f)
        return {int(g): {int(e): (t[0], t[1]) for e, t in v.items()}
                for g, v in raw.items()}
    return {}


def save_cache(cache: dict[int, dict[int, tuple[int, int]]]) -> None:
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({str(g): {str(e): list(t) for e, t in v.items()}
                   for g, v in cache.items()}, f, ensure_ascii=False, indent=0)


def fetch_template(gid: int) -> dict[int, tuple[int, int]]:
    """Template {effectId: (mini, maxi)} depuis dofusdb (pas de cache)."""
    req = urllib.request.Request(API.format(gid=gid), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.load(resp)
    tpl: dict[int, tuple[int, int]] = {}
    for e in d.get("effects") or []:
        eid, lo, hi = e.get("effectId"), e.get("from"), e.get("to")
        if eid is None or lo is None or hi is None:
            continue
        # jet fixe (mini == maxi) ou sans jet : on le garde tel quel
        tpl[eid] = (int(lo), int(hi))
    return tpl


def get_template(gid: int, cache: Optional[dict[int, dict[int, tuple[int, int]]]] = None) -> dict[int, tuple[int, int]]:
    """Template avec cache : items.json d'abord, puis dofusdb (fetch + cache)."""
    items_db = _load_items_db()
    if gid in items_db:
        return items_db[gid]
    cache = cache if cache is not None else load_cache()
    if gid not in cache:
        cache[gid] = fetch_template(gid)
        save_cache(cache)
    return cache[gid]


def pct_jet(value: int, mini: int, maxi: int) -> Optional[float]:
    """% du jet = actuel / maxi (convention « jet % classique »).
    None si le template n'a pas de maxi utilisable (maxi <= 0)."""
    if maxi <= 0:
        return None
    return value / maxi * 100.0


def global_jet_pct(effects: dict[int, int],
                   template: dict[int, tuple[int, int]],
                   malus_effects: set[int]) -> Optional[float]:
    """% du jet GLOBAL = moyenne de actuel/maxi sur toutes les lignes du
    template avec un maxi utilisable, sauf les lignes negatives.

    Une stat native absente du paquet (tombee a 0) compte pour 0 %.
    Les exo hors template n'ont pas de maxi, ils sont ignores.
    `effects` : effectId -> valeur brute du paquet (les malus y sont en
    magnitude positive — le signe vient de `malus_effects`)."""
    if not template:
        return None
    effects = effects or {}
    pcts: list[float] = []
    for eid, (lo, hi) in template.items():
        if hi <= 0:
            continue
        if eid in effects:
            raw = effects[eid]
            sv = -raw if eid in malus_effects else raw
        else:
            sv = 0
        if sv < 0:
            continue
        pcts.append(sv / hi * 100.0)
    if not pcts:
        return None
    return sum(pcts) / len(pcts)


def fmt_pct(p: Optional[float]) -> str:
    if p is None:
        return "   n/a"
    return f"{p:6.1f}%"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gid", type=int, nargs="?", help="GID de l'item")
    ap.add_argument("--value", type=int, default=None,
                    help="valeur actuelle pour calculer le % du jet (ex. 392)")
    ap.add_argument("--fetch", type=int, nargs="*", default=None,
                    help="pre-remplit le cache pour ces gids puis quitte")
    args = ap.parse_args(argv)

    if args.fetch is not None:
        cache = load_cache()
        for gid in args.fetch:
            tpl = get_template(gid, cache)
            print(f"gid {gid}: {len(tpl)} effet(s) en cache")
        return 0

    if args.gid is None:
        ap.error("gid requis (ou --fetch)")

    tpl = get_template(args.gid)
    if not tpl:
        print(f"aucun template pour gid {args.gid}")
        return 1
    print(f"Template gid {args.gid} — jet mini -> maxi par stat :")
    for eid in sorted(tpl):
        lo, hi = tpl[eid]
        line = f"  effectId {eid:<4} {lo:>6} -> {hi:>6}"
        if args.value is not None:
            p = pct_jet(args.value, lo, hi)
            line += f"   valeur {args.value}: {fmt_pct(p)}"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
