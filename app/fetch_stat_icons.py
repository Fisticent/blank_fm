#!/usr/bin/env python3
"""Telecharge les icones de stats Dofus (textures tx_* de DofusDB).

Source : api.dofusdb.fr/characteristics (champ `asset`) +
         api.dofusdb.fr/effects (champ `characteristic`) +
         PNG : https://www.dofusdb.fr/icons/characteristics/{asset}.png

Ecrit :
    app/data/stat_icons.json     {effectId: asset}
    app/fm_ui/icons/stats/*.png  cache local
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from paths import APP_DIR, data_file

API = "https://api.dofusdb.fr"
ICON_CDN = "https://www.dofusdb.fr/icons/characteristics/{asset}.png"
HEADERS = {"User-Agent": "dofus-fm/1.0", "Accept": "*/*"}
ICON_DIR = os.path.join(APP_DIR, "fm_ui", "icons", "stats")

# Noms CDN (dofusdb.fr/icons/characteristics) parfois differents du champ `asset`.
ASSET_ALIASES = {
    "tx_strengthRes": "tx_res_earth",
    "tx_intelligenceRes": "tx_res_fire",
    "tx_chanceRes": "tx_res_water",
    "tx_agilityRes": "tx_res_air",
    "tx_neutralRes": "tx_res_neutral",
    "tx_damageMelee": "tx_meleeDamage",
    "tx_distance": "tx_distanceDamage",
    "tx_distanceRes": "tx_res_distance",
    "tx_resMelee": "tx_res_melee",
    "tx_weapon": "tx_weaponDamage",
    "tx_weaponRes": "tx_res_weapon",
    "tx_spells": "tx_spellDamage",
    "tx_spellsRes": "tx_res_spell",
    "tx_lifePoints": "tx_vitality",
}


def resolve_asset(asset: str) -> str:
    return ASSET_ALIASES.get(asset, asset)


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={**HEADERS, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _pages(path: str, page: int = 50) -> list[dict]:
    skip = 0
    out: list[dict] = []
    total = None
    while True:
        sep = "&" if "?" in path else "?"
        d = _get_json(f"{API}{path}{sep}$limit={page}&$skip={skip}")
        total = d.get("total")
        batch = d.get("data") or []
        out.extend(batch)
        print(f"  {path} {len(out)}/{total}", flush=True)
        if not batch or (total is not None and len(out) >= total):
            break
        skip += page
    return out


def _download(asset: str) -> bool:
    os.makedirs(ICON_DIR, exist_ok=True)
    dest = os.path.join(ICON_DIR, f"{asset}.png")
    if os.path.exists(dest) and os.path.getsize(dest) > 32:
        return True
    url = ICON_CDN.format(asset=asset)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        print(f"  skip {asset} ({e.code})", flush=True)
        return False
    if data[:4] != b"\x89PNG":
        print(f"  skip {asset} (pas un PNG)", flush=True)
        return False
    with open(dest, "wb") as f:
        f.write(data)
    return True


def main() -> int:
    print("characteristics", flush=True)
    chars = {c["id"]: c.get("asset") or "" for c in _pages("/characteristics")}
    print("effects", flush=True)
    effects = _pages("/effects")

    mapping: dict[str, str] = {}
    assets_needed: set[str] = set()
    for e in effects:
        eid = e.get("id")
        cid = e.get("characteristic")
        asset = chars.get(cid) if cid is not None else ""
        if eid is None or not asset:
            continue
        asset = resolve_asset(asset)
        mapping[str(eid)] = asset
        assets_needed.add(asset)

    ok = 0
    print(f"download {len(assets_needed)} icones -> {ICON_DIR}", flush=True)
    for asset in sorted(assets_needed):
        if _download(asset):
            ok += 1
        else:
            # ne pas mapper vers un fichier absent
            for k, v in list(mapping.items()):
                if v == asset:
                    del mapping[k]

    out = data_file("stat_icons.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{len(mapping)} effectIds, {ok} PNG -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
