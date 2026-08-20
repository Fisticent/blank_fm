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
    """Echo de rune. kfb est petit ; on n'ouvre pas les dumps d'inventaire."""
    ru = parse_kfb(payload)
    if ru and ru.gid in RUNES:
        if not ru.effect_id:
            ru.effect_id = int(getattr(ru, "effect_id", 0) or 0)
        return ru
    if not payload or len(payload) > 160:
        return None
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
    """Etat forge (kdr). Le puits peut manquer a la pose de l'item."""
    st = parse_kdr(payload)
    if st and (st.puit is not None or st.gid or st.effects):
        return st
    return None


def parse_iuj_only(payload: bytes) -> Optional[ItemState]:
    st = parse_iuj(payload)
    if st and st.gid and st.slot and st.gid not in RUNES:
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
        self.seen: set[str] = set()
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
        current = self.names.get(role)
        canonical = DEFAULT_MAP.get(role)
        # Les vrais noms (kfb/kdr/iuj) reparsent toujours une map corrompue.
        if name != canonical:
            if current == canonical and canonical in self.seen:
                return False
            if current and current in self.seen and current != name:
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
_DEFAULT_ROLE = {v: k for k, v in DEFAULT_MAP.items()}


def _as_role(role: str, payload: bytes, direction: str):
    """Parse strict d'un role, sans apprentissage."""
    if role == "prices":
        prices = parse_ivi(payload)
        if prices:
            return ("prices", prices)
        return None
    if role == "price_gid":
        d = {f: v for f, w, v in parse_message(payload) if w == 0}
        if d.get(1):
            return ("price_gid", int(d[1]))
        return None
    if role == "price_val":
        d = {f: v for f, w, v in parse_message(payload) if w == 0}
        if d.get(1) is not None:
            return ("price_val", int(d[1]))
        return None
    if role == "object_use":
        if direction == "c2s" and 20 <= len(payload) <= 80:
            d = _fields0(payload)
            if d.get(3) == 1 and d.get(1) and set(d.keys()) <= {1, 3, 6}:
                return ("object_use", d.get(1))
        return None
    if role == "rune_echo":
        ru = parse_rune_any(payload)
        if ru and ru.gid in RUNES:
            return ("rune_echo", ru)
        # kfb sert aussi a l'echo de l'item pose dans la forge.
        inv = parse_iuj_only(payload)
        if inv:
            return ("inventory", inv)
        return None
    if role == "item_state":
        st = parse_item_state_any(payload)
        if st:
            return ("item_state", st)
        return None
    if role == "inventory":
        inv = parse_iuj_only(payload)
        if inv:
            return ("inventory", inv)
        return None
    return None


def classify_payload(name: str, payload: bytes, direction: str):
    """kfb/kdr/iuj d'abord, puis la map, puis apprentissage sur les noms inconnus."""
    if not payload:
        return None
    if name and name != "?":
        PROTO.seen.add(name)

    canonical_role = _DEFAULT_ROLE.get(name)
    if canonical_role:
        hit = _as_role(canonical_role, payload, direction)
        if hit:
            if hit[0] == canonical_role:
                PROTO.bind(hit[0], name)
            return hit

    mapped_role = PROTO.role_of(name)
    if mapped_role and mapped_role != canonical_role:
        hit = _as_role(mapped_role, payload, direction)
        if hit:
            return hit
        return None

    if direction == "c2s" and 20 <= len(payload) <= 80:
        hit = _as_role("object_use", payload, direction)
        if hit:
            PROTO.bind("object_use", name)
            return hit

    if len(payload) >= 200:
        prices = parse_ivi(payload)
        if len(prices) >= 20:
            PROTO.bind("prices", name)
            return ("prices", prices)

    if len(payload) > 400:
        return None

    ru = parse_rune_any(payload)
    if ru and ru.gid in RUNES:
        PROTO.bind("rune_echo", name)
        return ("rune_echo", ru)

    st = parse_item_state_any(payload)
    if st and st.puit is not None:
        PROTO.bind("item_state", name)
        return ("item_state", st)

    inv = parse_iuj_only(payload)
    if inv:
        PROTO.bind("inventory", name)
        return ("inventory", inv)

    return None
