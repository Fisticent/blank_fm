"""Apprentissage des noms de messages FM (type.ankama.com/<obfusque>).

Les noms changent a chaque patch. Le contenu (GID rune, effectId, puits)
reste reconnaissable. On bind le type_url des qu'une pose de rune connue
est vue, et on sauve protocol_map.json a cote de l'exe.
"""
from __future__ import annotations

import json
import os
import struct
from typing import Optional

from sniffer_hdv import parse_message
from fm_decoder import (
    RUNES, EFFECTS, ITEMS, RuneUse, ItemState,
    parse_kfb, parse_kdr, parse_iuj, _ensure_effects_loaded, _ensure_items_enriched,
)
from fm_cost import parse_ivi
from paths import PROJECT_DIR, data_file

DEFAULT_MAP = {
    "rune_echo": "kfb",
    "item_state": "kdr",
    "inventory": "iuj",
    "object_use": "kcj",
    "prices": "ivi",
    "price_gid": "iwo",
    "price_val": "kgq",
}

USER_MAP_PATH = os.path.join(PROJECT_DIR, "protocol_map.json")
BUNDLED_MAP_PATH = data_file("protocol_map.json")


def _fields0(buf: bytes) -> dict:
    return {f: v for f, w, v in parse_message(buf) if w == 0}


def _walk(buf: bytes, depth: int = 0):
    if depth > 8 or not buf or len(buf) > 20000:
        return
    try:
        fields = parse_message(buf)
    except Exception:
        return
    yield fields
    for _f, w, v in fields:
        if w == 2 and isinstance(v, bytes) and 2 <= len(v) <= 8000:
            yield from _walk(v, depth + 1)


def _as_effect(fields: list) -> Optional[tuple[int, int]]:
    d = {f: v for f, w, v in fields if w == 0}
    eid, val = d.get(11), d.get(4)
    if eid is None or val is None:
        return None
    _ensure_effects_loaded()
    if eid in EFFECTS or eid in RUNES:
        return int(eid), int(val)
    if 1 <= eid <= 4000 and abs(int(val)) < 100000:
        return int(eid), int(val)
    return None


def _collect_effects(buf: bytes) -> list[tuple[int, int]]:
    out = []
    seen = set()
    for fields in _walk(buf):
        pair = _as_effect(fields)
        if not pair:
            continue
        if pair in seen:
            continue
        seen.add(pair)
        out.append(pair)
    return out


def _floats(buf: bytes) -> list[float]:
    found = []
    for fields in _walk(buf):
        for _f, w, v in fields:
            raw = None
            if w == 5 and isinstance(v, bytes) and len(v) == 4:
                raw = v
            elif w == 2 and isinstance(v, bytes) and len(v) == 4:
                raw = v
            if raw is None:
                continue
            val = struct.unpack("<f", raw)[0]
            if 0.0 <= val <= 500.0:
                found.append(val)
    return found


def parse_rune_any(payload: bytes) -> Optional[RuneUse]:
    ru = parse_kfb(payload)
    if ru and ru.gid in RUNES:
        if not ru.effect_id:
            ru.effect_id = int(getattr(ru, "effect_id", 0) or 0)
        return ru
    rune_gids = RUNES
    for fields in _walk(payload):
        d = {f: v for f, w, v in fields if w == 0}
        gid = d.get(1)
        if gid not in rune_gids:
            continue
        uid = int(d.get(4) or 0)
        eid = wgt = 0
        for _f, w, v in fields:
            if w != 2 or not isinstance(v, bytes):
                continue
            pair = _as_effect(parse_message(v))
            if pair:
                eid, wgt = pair
                break
        return RuneUse(ts="", uid=uid, gid=int(gid), effect_id=eid, weight=wgt)
    return None


def parse_item_state_any(payload: bytes) -> Optional[ItemState]:
    """Etat apres pose : GID + effets + puits (float). Sans puits ce n'est pas kdr."""
    st = parse_kdr(payload)
    if st and st.puit is not None:
        return st
    if len(payload) > 2000:
        return None
    puits = _floats(payload)
    if not puits:
        return None
    effects = _collect_effects(payload)
    gid = uid = 0
    _ensure_items_enriched()
    for fields in _walk(payload):
        d = {f: v for f, w, v in fields if w == 0}
        g = d.get(1)
        if g and g not in RUNES and (g in ITEMS or int(g) > 100):
            gid = int(g)
            uid = int(d.get(4) or uid)
            break
    if not effects and not gid:
        return None
    return ItemState(gid=gid, uid=uid, slot=0, state=0, puit=puits[0], effects=effects)


def parse_iuj_only(payload: bytes) -> Optional[ItemState]:
    st = parse_iuj(payload)
    if st and st.gid and st.slot:
        return st
    return None


def parse_inventory_any(payload: bytes) -> Optional[ItemState]:
    st = parse_iuj_only(payload)
    if st:
        return st
    if len(payload) > 2000:
        return None
    effects = _collect_effects(payload)
    slot = gid = uid = 0
    _ensure_items_enriched()
    for fields in _walk(payload):
        d = {f: v for f, w, v in fields if w == 0}
        s = d.get(1)
        if s is not None and 1 <= int(s) <= 128:
            slot = int(s)
        g = d.get(1)
        if g in ITEMS or (g and g not in RUNES and int(g) > 1000):
            if g and int(g) > 200:
                gid = int(g)
                uid = int(d.get(4) or uid)
    if not gid:
        return None
    if not slot and not effects:
        return None
    return ItemState(gid=gid, uid=uid, slot=slot, state=0, puit=None, effects=effects)


class ProtocolMap:
    def __init__(self):
        self.names = dict(DEFAULT_MAP)
        self.learned = False
        self._load()

    def _load(self) -> None:
        for path in (USER_MAP_PATH, BUNDLED_MAP_PATH):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            for k, v in data.items():
                if k in self.names and isinstance(v, str) and v:
                    self.names[k] = v
            break

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(USER_MAP_PATH) or ".", exist_ok=True)
            tmp = USER_MAP_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.names, f, ensure_ascii=False, indent=2)
            os.replace(tmp, USER_MAP_PATH)
        except OSError:
            pass

    def bind(self, role: str, name: str) -> bool:
        if role not in self.names or not name or name == "?":
            return False
        if self.names.get(role) == name:
            return False
        self.names[role] = name
        self.learned = True
        self.save()
        return True

    def role_of(self, name: str) -> Optional[str]:
        for role, n in self.names.items():
            if n == name:
                return role
        return None

    def status(self) -> str:
        n = self.names
        flag = "appris" if self.learned else "auto"
        return (f"Proto {flag} : rune={n['rune_echo']}  item={n['item_state']}  "
                f"inv={n['inventory']}")


PROTO = ProtocolMap()


def classify_payload(name: str, payload: bytes, direction: str):
    """Identifie un message FM par structure, puis met a jour la map des noms."""
    if not payload:
        return None
    role = PROTO.role_of(name)

    if direction == "c2s" and 20 <= len(payload) <= 80:
        d = _fields0(payload)
        if d.get(3) == 1 and d.get(1) and set(d.keys()) <= {1, 3, 6}:
            PROTO.bind("object_use", name)
            return ("object_use", d.get(1))

    if len(payload) >= 200:
        prices = parse_ivi(payload)
        if len(prices) >= 20:
            PROTO.bind("prices", name)
            return ("prices", prices)

    if role == "prices" or name == PROTO.names["prices"]:
        prices = parse_ivi(payload)
        if prices:
            return ("prices", prices)

    if role == "price_gid" or name == PROTO.names["price_gid"]:
        d = {f: v for f, w, v in parse_message(payload) if w == 0}
        if d.get(1):
            return ("price_gid", int(d[1]))

    if role == "price_val" or name == PROTO.names["price_val"]:
        d = {f: v for f, w, v in parse_message(payload) if w == 0}
        if d.get(1) is not None:
            return ("price_val", int(d[1]))

    ru = parse_rune_any(payload)
    if ru and ru.gid in RUNES:
        PROTO.bind("rune_echo", name)
        return ("rune_echo", ru)

    inv = parse_iuj_only(payload)
    if inv and inv.gid and inv.slot:
        PROTO.bind("inventory", name)
        return ("inventory", inv)

    st = parse_item_state_any(payload)
    if st and st.puit is not None:
        PROTO.bind("item_state", name)
        return ("item_state", st)

    inv2 = parse_inventory_any(payload)
    if inv2 and inv2.gid and inv2.gid not in RUNES:
        PROTO.bind("inventory", name)
        return ("inventory", inv2)

    return None
