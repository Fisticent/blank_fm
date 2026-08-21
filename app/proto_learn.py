"""Noms de messages FM (type.ankama.com/<obfusque>).

Le contenu (UID, GID rune, effectId, puits) reste stable, les noms changent
a chaque patch. Apprentissage uniquement pendant une fenetre UID ouverte par
un ObjectUse, chemins protobuf exacts, jamais de walk recursif.
"""
from __future__ import annotations

import json
import os
import struct
import time
from collections import Counter, defaultdict
from typing import Optional

from sniffer_hdv import parse_message
from fm_decoder import (
    RUNES, EFFECTS, ITEMS, RuneUse, ItemState,
    parse_kfb, parse_kdr, parse_iuj, parse_ivj, known_item_gid,
    _ensure_effects_loaded, _ensure_items_enriched, _fields, _effect_list,
)
from fm_cost import parse_ivi
from paths import PROJECT_DIR, data_file

DEFAULT_MAP = {
    "rune_echo": "kfb",
    "item_state": "kdr",
    "inventory": "iuj",
    "object_use": "kcj",
    "stack_qty": "ivj",
    "prices": "ivi",
    "price_gid": "iwo",
    "price_val": "kgq",
}

LEARN_ROLES = (
    "object_use",
    "rune_echo",
    "stack_qty",
    "item_state",
    "inventory",
)

USER_MAP_PATH = os.path.join(PROJECT_DIR, "protocol_map.json")
BUNDLED_MAP_PATH = data_file("protocol_map.json")
FORGE_SLOT = 63
WINDOW_TTL = 2.0
VOTES_PROMOTE = 3
VOTES_CONFLICT = 2
VOTES_UNSTABLE = 10
MAP_VERSION = 2


def _at(buf, *path):
    cur = buf
    for p in path:
        if not isinstance(cur, bytes):
            return None
        cur = _fields(cur).get(p)
    return cur


def _fields0(buf: bytes) -> dict:
    return {f: v for f, w, v in parse_message(buf) if w == 0}


def detect_object_use(payload: bytes, direction: str) -> Optional[int]:
    if direction != "c2s" or not payload or not (8 <= len(payload) <= 80):
        return None
    d = _fields0(payload)
    if d.get(3) == 1 and d.get(1) and set(d.keys()) <= {1, 3, 6}:
        return int(d[1])
    return None


def match_rune_echo(payload: bytes, pending_uid: int) -> bool:
    if not payload or len(payload) > 160 or not pending_uid:
        return False
    gid = _at(payload, 1, 5, 1)
    uid = _at(payload, 1, 5, 4)
    try:
        gid_i, uid_i = int(gid), int(uid)
    except (TypeError, ValueError):
        return False
    return gid_i in RUNES and uid_i == int(pending_uid)


def match_stack_qty(payload: bytes, pending_uid: int) -> bool:
    if not payload or not pending_uid:
        return False
    uid = _at(payload, 3, 2)
    qty = _at(payload, 3, 3)
    try:
        uid_i, qty_i = int(uid), int(qty)
    except (TypeError, ValueError):
        return False
    return uid_i == int(pending_uid) and qty_i >= 0


def match_item_state(payload: bytes) -> bool:
    if not payload:
        return False
    raw = _at(payload, 2, 3)
    if not isinstance(raw, bytes) or len(raw) != 4:
        return False
    val = struct.unpack("<f", raw)[0]
    if not (0.0 <= val <= 500.0):
        return False
    em = _at(payload, 2, 4)
    if not isinstance(em, bytes):
        return False
    effs = _effect_list(em)
    if not effs:
        return False
    _ensure_effects_loaded()
    for eid, _v in effs:
        if eid in EFFECTS or eid in RUNES:
            return True
    return False


def match_inventory(payload: bytes, pending_uid: int,
                    item_slot: int = 0) -> bool:
    if not payload:
        return False
    slot = _at(payload, 1, 1)
    gid = _at(payload, 1, 5, 1)
    uid = _at(payload, 1, 5, 4)
    try:
        slot_i, gid_i, uid_i = int(slot), int(gid), int(uid)
    except (TypeError, ValueError):
        return False
    if uid_i == int(pending_uid or 0):
        return False
    if gid_i in RUNES:
        return False
    _ensure_items_enriched()
    if gid_i not in ITEMS:
        return False
    if slot_i == FORGE_SLOT:
        return True
    if item_slot and slot_i == int(item_slot):
        return True
    return False


def parse_iuj_only(payload: bytes) -> Optional[ItemState]:
    st = parse_iuj(payload)
    if st and known_item_gid(st.gid) and st.slot:
        return st
    return None


def parse_rune_stack(payload: bytes) -> Optional[ItemState]:
    st = parse_iuj(payload)
    if st and st.gid in RUNES:
        return st
    return None


class ProtocolMap:
    def __init__(self, user_path: Optional[str] = None, load: bool = True):
        self.user_path = user_path or USER_MAP_PATH
        self.names = dict(DEFAULT_MAP)
        self.promoted: dict[str, str] = {}
        self.scores: dict[str, Counter] = defaultdict(Counter)
        self.samples: dict[str, dict] = {}
        self.awake = False
        self.force_learn = False
        self.unstable = False
        self.pending_uid: Optional[int] = None
        self.pending_t = 0.0
        self.window_echo = False
        self.window_echo_ok = False
        self._voted: dict[int, set[str]] = {}
        self.item_slot = 0
        self.seen: set[str] = set()
        if load:
            self._load()

    def _now(self) -> float:
        return time.monotonic()

    def _expire(self) -> None:
        if self.pending_uid is None:
            return
        if self._now() - self.pending_t <= WINDOW_TTL:
            return
        self._close_window()

    def _close_window(self) -> None:
        if self.pending_uid is None:
            return
        if not self.window_echo_ok and "rune_echo" not in self.promoted:
            self.awake = True
        elif self.window_echo_ok and "rune_echo" in self.promoted:
            self.awake = False
            self.force_learn = False
        self.pending_uid = None
        self.window_echo = False
        self.window_echo_ok = False

    def _open_window(self, uid: int) -> None:
        if self.pending_uid and self.pending_uid != uid:
            self._close_window()
        self.pending_uid = int(uid)
        self.pending_t = self._now()
        self.window_echo = False
        self.window_echo_ok = False

    def _load(self) -> None:
        for path in (self.user_path, BUNDLED_MAP_PATH):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            if int(data.get("version") or 0) == MAP_VERSION:
                self._load_v2(data)
            else:
                self._load_v1(data)
            break

    def _load_v1(self, data: dict) -> None:
        for k, v in data.items():
            if k not in self.names or not isinstance(v, str) or not v:
                continue
            if k in ("rune_echo", "item_state", "inventory"):
                if v != DEFAULT_MAP[k]:
                    continue
            self.names[k] = v

    def _load_v2(self, data: dict) -> None:
        promoted = data.get("promoted") or {}
        samples = data.get("samples") or {}
        if not isinstance(promoted, dict):
            promoted = {}
        if not isinstance(samples, dict):
            samples = {}
        for role, name in promoted.items():
            if role not in LEARN_ROLES or not isinstance(name, str) or not name:
                continue
            sample = samples.get(role) if isinstance(samples.get(role), dict) else None
            if sample and not self._sample_ok(role, sample):
                continue
            self.names[role] = name
            self.promoted[role] = name
            if sample:
                self.samples[role] = {
                    "name": sample.get("name") or name,
                    "payload_hex": sample.get("payload_hex") or "",
                }

    def _sample_ok(self, role: str, sample: dict) -> bool:
        name = sample.get("name") or ""
        hex_s = sample.get("payload_hex") or ""
        if not name or not hex_s:
            return False
        try:
            payload = bytes.fromhex(hex_s)
        except ValueError:
            return False
        if role == "object_use":
            return detect_object_use(payload, "c2s") is not None
        if role == "rune_echo":
            ru = parse_kfb(payload)
            return bool(ru and ru.gid in RUNES)
        if role == "stack_qty":
            q = parse_ivj(payload)
            return bool(q and q[0])
        if role == "item_state":
            return match_item_state(payload)
        if role == "inventory":
            st = parse_iuj_only(payload)
            return bool(st)
        return False

    def _save_v2(self) -> None:
        blob = {
            "version": MAP_VERSION,
            "promoted": dict(self.promoted),
            "scores": {r: dict(c) for r, c in self.scores.items() if c},
            "samples": dict(self.samples),
        }
        tmp = self.user_path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.user_path) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(blob, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.user_path)
        except OSError:
            pass

    def relearn(self) -> None:
        self.awake = True
        self.force_learn = True
        self.unstable = False
        self.scores = defaultdict(Counter)
        self.samples = {}
        self.promoted = {}
        self._voted = {}
        self.names = dict(DEFAULT_MAP)
        self.pending_uid = None
        self.window_echo = False
        self.window_echo_ok = False
        try:
            if os.path.isfile(self.user_path):
                os.remove(self.user_path)
        except OSError:
            pass

    def role_of(self, name: str) -> Optional[str]:
        for role, n in self.names.items():
            if n and n == name:
                return role
        return None

    def _name_taken(self, name: str, role: str) -> bool:
        for r, n in self.names.items():
            if r == role:
                continue
            if n == name:
                return True
        return False

    def _vote(self, role: str, name: str, payload: bytes) -> None:
        if role not in LEARN_ROLES or not name or name == "?":
            return
        uid = self.pending_uid
        if not uid:
            return
        voted = self._voted.setdefault(uid, set())
        if role in voted:
            return
        voted.add(role)
        self.scores[role][name] += 1
        if payload:
            self.samples[role] = {"name": name, "payload_hex": payload.hex()}
        self._try_promote(role)

    def _try_promote(self, role: str) -> None:
        if self.unstable:
            return
        ctr = self.scores.get(role) or Counter()
        total = sum(ctr.values())
        if total >= VOTES_UNSTABLE:
            top = ctr.most_common(2)
            if len(top) < 1 or top[0][1] < VOTES_PROMOTE:
                self.unstable = True
                return
            if len(top) > 1 and top[1][1] >= VOTES_CONFLICT:
                self.unstable = True
                return
        if not ctr:
            return
        name, n = ctr.most_common(1)[0]
        if n < VOTES_PROMOTE:
            return
        if len(ctr) > 1 and ctr.most_common(2)[1][1] >= VOTES_CONFLICT:
            return
        if self._name_taken(name, role):
            return
        if role in self.promoted and self.promoted.get(role) == name:
            return
        self.names[role] = name
        self.promoted[role] = name
        self._save_v2()

    def confirm_pose(self) -> None:
        """Pose dont les noms connus collent encore (dormant)."""
        return

    def status(self) -> str:
        n = self.names
        core = f"{n.get('rune_echo') or '?'} / {n.get('item_state') or '?'} / {n.get('inventory') or '?'}"
        if self.unstable:
            return "Proto instable, map livree conservee"
        if self.awake or self.force_learn:
            got = sum((self.scores.get("rune_echo") or Counter()).values())
            return f"Proto en cours, {got}/{VOTES_PROMOTE}  ({core})"
        if self.promoted:
            npos = sum((self.scores.get("rune_echo") or Counter()).values())
            if npos:
                return f"Proto appris, {npos} poses  ({core})"
            return f"Proto appris ({core})"
        return f"Proto defaut ({core})"

    def observe(self, name: str, payload: bytes, direction: str):
        """Ouvre la fenetre UID, vote si eveille, retourne un hit eventuel."""
        self._expire()
        uid = detect_object_use(payload, direction)
        if uid:
            self._open_window(uid)
            if self.awake or self.force_learn or (
                    name and name != self.names.get("object_use")):
                self._vote("object_use", name, payload)
            return ("object_use", uid)

        if direction != "s2c" or not self.pending_uid:
            return None

        pending = self.pending_uid
        mapped = self.role_of(name) if name and name != "?" else None

        if mapped == "rune_echo" and match_rune_echo(payload, pending):
            self.window_echo_ok = True
            self.window_echo = True

        learning = self.awake or self.force_learn
        if not learning:
            return None

        if match_rune_echo(payload, pending):
            self.window_echo = True
            self.window_echo_ok = True
            self._vote("rune_echo", name, payload)
            ru = parse_kfb(payload)
            if ru and ru.gid in RUNES:
                return ("rune_echo", ru)
        if match_stack_qty(payload, pending):
            self._vote("stack_qty", name, payload)
            q = parse_ivj(payload)
            if q and q[0]:
                return ("stack_qty", q)
        if self.window_echo and match_item_state(payload):
            self._vote("item_state", name, payload)
            st = parse_kdr(payload)
            if st:
                return ("item_state", st)
        if match_inventory(payload, pending, self.item_slot):
            self._vote("inventory", name, payload)
            inv = parse_iuj_only(payload)
            if inv:
                if inv.slot:
                    self.item_slot = inv.slot
                return ("inventory", inv)
        return None


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
        uid = detect_object_use(payload, direction)
        if uid:
            return ("object_use", uid)
        return None
    if role == "rune_echo":
        ru = parse_kfb(payload)
        if ru and ru.gid in RUNES:
            return ("rune_echo", ru)
        inv = parse_iuj_only(payload)
        if inv:
            return ("inventory", inv)
        return None
    if role == "item_state":
        st = parse_kdr(payload)
        if st and (st.puit is not None or st.gid or st.effects):
            return ("item_state", st)
        return None
    if role == "inventory":
        inv = parse_iuj_only(payload)
        if inv:
            return ("inventory", inv)
        rune = parse_rune_stack(payload)
        if rune:
            return ("rune_stack", rune)
        return None
    if role == "stack_qty":
        q = parse_ivj(payload)
        if q and q[0]:
            return ("stack_qty", q)
        return None
    return None


def classify_payload(name: str, payload: bytes, direction: str):
    """Parse le paquet. Apprend seulement dans la fenetre UID (eveille)."""
    if not payload:
        return None
    if name and name != "?":
        PROTO.seen.add(name)

    learned = PROTO.observe(name, payload, direction)

    canonical_role = _DEFAULT_ROLE.get(name)
    if canonical_role:
        hit = _as_role(canonical_role, payload, direction)
        if hit:
            return hit

    mapped_role = PROTO.role_of(name)
    if mapped_role and mapped_role != canonical_role:
        hit = _as_role(mapped_role, payload, direction)
        if hit:
            return hit

    if learned:
        return learned
    return None
