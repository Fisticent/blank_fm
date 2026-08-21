#!/usr/bin/env python3
"""
fm_decoder.py — Decodeur des messages Forgemagie (Dofus 3, port 5555).

Analyse une session FM capturee par fm_live.py (fichier frames.jsonl) et
produit un rapport lisible : pour chaque pose de rune, la rune utilisee
(GID -> nom), son effet (effectId -> nom, valeur), le delta observe sur
l'effet vise, et l'evolution de l'etat complet de l'item forge.

Decodage reverse-engineere le 2026-08-20 (client Dofus 3) :
    kcj (c2s) : ObjectUse          { f1 = UID rune, f3 = 1, f6 = 1 }
    kfb (s2c) : rune utilisee      { f1 { f1 = slot, f5 = ObjectItem {
                                       f1 = GID, f2 = effet, f3 = 1, f4 = UID } } }
    kdr (s2c) : etat item forge    { f2 { f1 = etat, f3 = float puit (affiche UI), f4 = effets {
                                       f2 rep = effet, f3 = 1, f4 = UID item } } }
    iuj (s2c) : inventaire         { f1 { f1 = slot, f5 = ObjectItem {
                                       f1 = GID, f2 rep = effets, f4 = UID, f5 = {1,1} } } }
    ivj (s2c) : quantite pile      { f2 { f1 = qty, f2 = flag }, f3 { f2 = UID, f3 = qty } }
    kfs (s2c) : ack                { f1 = UID rune }
    Effet (ObjectEffectInteger)    { f4 = valeur, f11 = effectId }

Usage :
    python fm_decoder.py captures/fm_2026-08-20.jsonl
    python fm_decoder.py captures/fm_2026-08-20.jsonl --item 14094
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from fm_live import extract_envelope
from sniffer_hdv import parse_message
from paths import data_file

# ------------------------------------------------------------- dictionnaires

def _load_runes_table() -> tuple[dict[int, str], dict[int, int], dict[int, str]]:
    """runes.json -> ({gid: nom}, {gid: effectId}, {effectId: caracteristique})."""
    path = data_file("runes.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        names = {int(gid): r["name"] for gid, r in data.items()}
        effects = {int(gid): r.get("effectId") or 0 for gid, r in data.items()}
        by_eid: dict[int, str] = {}
        for r in data.values():
            eid = r.get("effectId")
            en = r.get("effect_name")
            if eid and en:
                by_eid.setdefault(int(eid), str(en))
        return names, effects, by_eid
    except (OSError, ValueError, KeyError):
        return {}, {}, {}


_STAT_DISPLAY = {
    "Cri": "Critique", "Cha": "Chance", "Sa": "Sagesse", "Vi": "Vitalite",
    "Fo": "Force", "Ine": "Intelligence", "Age": "Agilite", "Ini": "Initiative",
    "Pui": "Puissance", "Do": "Dommage", "So": "Soin", "Po": "Portee",
    "Prospe": "Prospection", "Pod": "Pods", "Invo": "Invocation",
    "Pi": "Do Piege", "Tac": "Tacle", "Fui": "Fuite",
    "Do Ren": "Renvoi Do", "Chasse": "Chasse",
}


def _display_stat(stat: str) -> str:
    s = stat.replace("é", "e").replace("è", "e").replace("ê", "e")
    if s.startswith("Re Per "):
        return "Res. % " + s[7:]
    if s in ("Re Pa", "Re Pme"):
        return {"Re Pa": "Esquive PA", "Re Pme": "Esquive PM"}[s]
    if s.startswith("Re "):
        return "Res. " + s[3:]
    if s.startswith("Do Per "):
        return "Do % " + s[7:]
    if s.startswith("Ret "):
        return "Ret. " + {"Pa": "PA", "Pme": "PM"}.get(s[4:], s[4:])
    if s in ("Pa", "Pme"):
        return {"Pa": "PA", "Pme": "PM"}[s]
    return _STAT_DISPLAY.get(s, stat)


def _effect_names_from_runes(runes: dict[int, str], runes_eff: dict[int, int]) -> dict[int, str]:
    """effectId -> nom de stat, derive des runes de base (ex. Rune Pa Sa -> Sa)."""
    out: dict[int, str] = {}
    for gid, name in sorted(runes.items()):
        n = name.replace("Rune ", "").strip()
        prefix = next((p.strip() for p in ("Pa ", "Ra ", "Ga ") if n.startswith(p)), None)
        if prefix is not None:
            continue  # seule la rune de base nomme la stat
        stat = _display_stat(n)
        out.setdefault(runes_eff.get(gid, 0), stat)
    return out


_RUNES, _RUNES_EFFECT, _RUNES_STAT = _load_runes_table()


# GIDs identifies via api.dofusdb.fr (session du 2026-08-20) ; completes
# automatiquement par runes.json si present (voir fetch_runes.py)
RUNES: dict[int, str] = {
    1521: "Rune Sa", 1525: "Rune Cha", 1546: "Rune Pa Sa", 1550: "Rune Pa Cha",
    7433: "Rune Cri",
    7458: "Rune Re Per Air", 7459: "Rune Re Per Terre",
    11639: "Rune Tac", 11641: "Rune Re Pa", 11654: "Rune Pa Do Cri",
}
RUNES.update(_RUNES)
ITEMS: dict[int, str] = {
    14094: "Amulette du Strigide", 12086: "Bague Moutheuze",
    27524: "Alliance des Rebelles",
}
_ITEMS_ENRICHED = False


def _ensure_items_enriched() -> None:
    """Ajoute les noms d'items depuis items.json (fetch_items.py) au premier
    appel. Ne remplace pas les entrees connues (elles font foi)."""
    global _ITEMS_ENRICHED
    if _ITEMS_ENRICHED:
        return
    _ITEMS_ENRICHED = True
    path = data_file("items.json")
    try:
        with open(path, encoding="utf-8") as f:
            db = json.load(f)
    except (OSError, ValueError):
        return
    for gid, d in db.items():
        try:
            g = int(gid)
        except (TypeError, ValueError):
            continue
        if g not in ITEMS and d.get("name"):
            ITEMS[g] = d["name"]


def item_name(gid: int) -> str:
    _ensure_items_enriched()
    return ITEMS.get(gid, f"gid {gid}")


def known_item_gid(gid: int) -> bool:
    """True si le GID est un item du catalogue (items.json), pas une rune."""
    if not gid:
        return False
    _ensure_items_enriched()
    return gid in ITEMS and gid not in RUNES

# effectId -> nom de caracteristique (pas le nom de rune).
# Priorite : runes.json effect_name, puis derivation du nom de rune, puis alias.
EFFECTS: dict[int, str] = dict(_RUNES_STAT)
for _eid, _stat in _effect_names_from_runes(_RUNES, _RUNES_EFFECT).items():
    if _eid:
        EFFECTS.setdefault(_eid, _stat)
for _eid, _stat in {
    111: "PA", 115: "Critique", 123: "Chance", 124: "Sagesse", 125: "Vitalite",
    138: "Puissance", 160: "Esquive PA", 171: "Critique (malus)",
    210: "Res. % Terre", 212: "Res. % Air",
    242: "Res. Air", 412: "Ret. PM", 416: "Res. Poussee", 418: "Dommage Critiques",
    421: "Res. Critiques (malus)", 426: "Do Eau", 753: "Tacle",
}.items():
    EFFECTS.setdefault(_eid, _stat)

# Effets dont la valeur du paquet est une MAGNITUDE positive alors que
# l'effet est un malus (le signe vient de la definition, cf. dofusdb
# characteristicOperator = "-") : a afficher en negatif.
MALUS_EFFECTS = {171, 421}


def _load_effects_table() -> tuple[set[int], dict[int, str]]:
    """Charge effects.json (genere par fetch_runes.py --malus).

    Retourne (malus, noms) : les malus detects par characteristicOperator=\"-\"
    sur toute la plage des effectIds dofusdb, plus les noms propres nettoyes.
    En l'absence du fichier, on retombe sur les valeurs connues.
    """
    malus = set(MALUS_EFFECTS)
    names: dict[int, str] = {}
    path = data_file("effects.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return malus, names
    malus |= {int(i) for i in data.get("malus", [])}
    for k, v in (data.get("names") or {}).items():
        try:
            names[int(k)] = v
        except (TypeError, ValueError):
            continue
    return malus, names


# Table des effets enrichie par effects.json au premier appel d'effect_name
_EFFECTS_LOADED = False


def _ensure_effects_loaded() -> None:
    global _EFFECTS_LOADED, MALUS_EFFECTS
    if _EFFECTS_LOADED:
        return
    malus, names = _load_effects_table()
    MALUS_EFFECTS = malus
    for eid, name in names.items():
        EFFECTS.setdefault(eid, name)
    _EFFECTS_LOADED = True


def effect_str(eid: int, value: int) -> str:
    """Rendu d'un effet avec signe : les malus connus s'affichent negatifs."""
    _ensure_effects_loaded()
    if eid in MALUS_EFFECTS and value > 0:
        return f"{effect_name(eid)} -{value}"
    return f"{effect_name(eid)} {value}"


# ------------------------------------------------------------- primitives

def _fields(buf: bytes) -> dict:
    return {f: v for f, w, v in parse_message(buf)}


def _effect_list(buf: bytes) -> list[tuple[int, int]]:
    """Liste d'effets -> [(effectId, valeur)] (f2 repete = ObjectEffectInteger)."""
    out = []
    for f, w, v in parse_message(buf):
        if f == 2 and w == 2 and isinstance(v, bytes):
            e = _fields(v)
            out.append((e.get(11), e.get(4)))
    return [(eid, val) for eid, val in out if eid is not None]


# ------------------------------------------------------------- parseurs

@dataclass
class RuneUse:
    ts: str
    uid: int
    gid: int
    effect_id: int
    weight: int          # valeur de la rune (dice)

    @property
    def name(self) -> str:
        return RUNES.get(self.gid, f"gid {self.gid}")


def _object_qty(oi: dict) -> int:
    q = oi.get(3)
    if isinstance(q, int) and q > 0:
        return q
    f5 = oi.get(5)
    if isinstance(f5, bytes):
        m = _fields(f5)
        q = m.get(1)
        if isinstance(q, int) and q > 0:
            return q
    return 1


@dataclass
class ItemState:
    gid: int
    uid: int
    slot: int
    state: int           # kdr f2.f1 (0-2, semi-aléatoire)
    puit: Optional[float]  # kdr f2.f3 = puit (budget de poids) affiche dans l'UI de forgemagie
    effects: list[tuple[int, int]] = field(default_factory=list)  # (effectId, valeur)
    qty: int = 1

    def effect(self, eid: int) -> Optional[int]:
        for i, v in self.effects:
            if i == eid:
                return v
        return None


@dataclass
class FmEvent:
    rune: RuneUse
    state: ItemState


def parse_kfb(payload: bytes) -> Optional[RuneUse]:
    """kfb : rune utilisee -> {uid, gid, effect_id, weight}."""
    d = _fields(payload)
    a = d.get(1)
    if not isinstance(a, bytes):
        return None
    o = _fields(a).get(5)
    if not isinstance(o, bytes):
        return None
    oi = _fields(o)
    eff = _fields(oi.get(2)) if isinstance(oi.get(2), bytes) else {}
    return RuneUse(ts="", uid=oi.get(4) or 0, gid=oi.get(1) or 0,
                   effect_id=eff.get(11) or 0, weight=eff.get(4) or 0)


def parse_kdr(payload: bytes) -> Optional[ItemState]:
    """kdr : etat de l'item forge apres la rune."""
    import struct
    d = _fields(payload)
    it = d.get(2)
    if not isinstance(it, bytes):
        return None
    oi = _fields(it)
    f3 = oi.get(3)
    puit = struct.unpack("<f", f3)[0] if isinstance(f3, bytes) and len(f3) == 4 else None
    em = oi.get(4)
    effs = _effect_list(em) if isinstance(em, bytes) else []
    emf = _fields(em) if isinstance(em, bytes) else {}
    return ItemState(gid=emf.get(1) or 0, uid=emf.get(4) or 0, slot=0,
                     state=oi.get(1) or 0, puit=puit, effects=effs)


def parse_iuj(payload: bytes) -> Optional[ItemState]:
    """iuj : item d'inventaire (avec GID)."""
    d = _fields(payload)
    a = d.get(1)
    if not isinstance(a, bytes):
        return None
    ai = _fields(a)
    o = ai.get(5)
    if not isinstance(o, bytes):
        return None
    oi = _fields(o)
    return ItemState(gid=oi.get(1) or 0, uid=oi.get(4) or 0, slot=ai.get(1) or 0,
                     state=0, puit=None,
                     effects=_effect_list(o) if isinstance(oi.get(2), bytes) else [],
                     qty=_object_qty(oi))


def parse_ivj(payload: bytes) -> Optional[tuple[int, int]]:
    """ivj : (uid rune, quantite restante de la pile)."""
    d = _fields(payload)
    f3 = d.get(3)
    if not isinstance(f3, bytes):
        return None
    m = _fields(f3)
    return m.get(2), m.get(3)


# ------------------------------------------------------------- session

def load_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def decode_session(rows: list[dict]) -> list[FmEvent]:
    """Reconstitue les poses de runes : chaque kcj est suivi de kfb + kdr."""
    events: list[FmEvent] = []
    pending: Optional[RuneUse] = None
    for r in rows:
        t = r["type"]
        if t in ("?", ""):
            continue
        payload = extract_envelope(bytes.fromhex(r["frame_hex"]))[1]
        if payload is None:
            continue
        if t == "kcj":
            pending = None  # la rune est identifiee par le kfb qui suit
        elif t == "kfb":
            ru = parse_kfb(payload)
            if ru:
                ru.ts = r["ts"]
                pending = ru
        elif t == "kdr":
            st = parse_kdr(payload)
            if pending and st:
                events.append(FmEvent(rune=pending, state=st))
                pending = None
    # GID + slot de l'item forge : pris depuis les iuj (kdr ne les porte pas)
    for r in reversed(rows):
        if r["type"] != "iuj":
            continue
        p = extract_envelope(bytes.fromhex(r["frame_hex"]))[1]
        st = parse_iuj(p) if p else None
        if st and st.gid:
            for ev in events:
                if not ev.state.gid:
                    ev.state.gid = st.gid
                ev.state.slot = st.slot
            break
    return events


# ------------------------------------------------------------- rapport

def effect_name(eid: int) -> str:
    _ensure_effects_loaded()
    return EFFECTS.get(eid, f"eff {eid}")


def signed_value(eid: int, v: int) -> int:
    """Valeur signee (les malus sont envoyes en magnitude positive)."""
    _ensure_effects_loaded()
    return -v if eid in MALUS_EFFECTS else v


def _norm_stat_key(name: str) -> str:
    s = (name or "").strip().lower()
    if s.endswith(" (malus)"):
        s = s[:-8]
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").strip()
    if s.startswith("res. "):
        s = "resistance " + s[5:]
    return s


_MALUS_TO_BONUS: dict[int, int] | None = None


def malus_to_bonus() -> dict[int, int]:
    """effectId malus -> effectId bonus (meme caracteristique)."""
    global _MALUS_TO_BONUS
    _ensure_effects_loaded()
    if _MALUS_TO_BONUS is not None:
        return _MALUS_TO_BONUS
    bonus_by_name: dict[str, int] = {}
    for eid, name in EFFECTS.items():
        if eid in MALUS_EFFECTS:
            continue
        bonus_by_name.setdefault(_norm_stat_key(name), eid)
    mapping: dict[int, int] = {}
    for eid in MALUS_EFFECTS:
        key = _norm_stat_key(EFFECTS.get(eid, ""))
        bid = bonus_by_name.get(key)
        if bid is not None:
            mapping[eid] = bid
    _MALUS_TO_BONUS = mapping
    return mapping


def fold_malus_onto_template(
    effects: dict[int, int],
    template: dict[int, tuple[int, int]],
) -> tuple[dict[int, int], set[int]]:
    """Ramene un id malus du paquet sur l'id bonus du template (jet negatif).

    Encyclopedie : 414 Do Pousse [-30, -21]. Paquet : 415 magnitude 21.
    Sans ce repli, l'UI affiche les deux lignes.
    """
    if not effects or not template:
        return dict(effects or {}), set()
    mapping = malus_to_bonus()
    out = dict(effects)
    consumed: set[int] = set()
    for meid, val in list(effects.items()):
        beid = mapping.get(meid)
        if beid is None:
            cand = meid - 1
            if cand in template:
                _lo, hi = template[cand]
                if hi < 0:
                    beid = cand
        if beid is None or beid not in template or beid == meid:
            continue
        _lo, hi = template[beid]
        if hi >= 0:
            continue
        if beid not in out:
            out[beid] = val
        out.pop(meid, None)
        consumed.add(meid)
    return out, consumed


def signed_stat(eid: int, v: int, hi: Optional[int] = None) -> int:
    """Comme signed_value, plus le jet negatif natif (template bonus, paquet malus)."""
    sv = signed_value(eid, v)
    if eid not in MALUS_EFFECTS and hi is not None and hi < 0 and sv > 0:
        return -abs(sv)
    return sv


def render(events: list[FmEvent], out=sys.stdout, prices: Optional[dict[int, int]] = None,
           template: Optional[dict[int, tuple[int, int]]] = None) -> None:
    if not events:
        print("aucun evenement FM trouve")
        return
    first = events[0]
    item_gid = first.state.gid
    item_uid = first.state.uid
    print(f"Session FM - {len(events)} pose(s) de rune sur "
          f"{item_name(item_gid)} "
          f"(GID {item_gid}, UID {item_uid}, slot {first.state.slot})")
    print()
    hdr = (f"{'#':>3}  {'heure':<13} {'rune':<18} {'effet':<22} {'valeur':>7} "
           f"{'delta':>6} {'etat':>4} {'puit':>5}  item (effectId: valeur)")
    if prices is not None:
        hdr = (f"{'#':>3}  {'heure':<13} {'rune':<18} {'effet':<22} {'valeur':>7} "
               f"{'delta':>6} {'etat':>4} {'puit':>5} {'prix':>9} {'cout':>9}  "
               f"item (effectId: valeur)")
    print(hdr)
    prev: Optional[ItemState] = None
    total = 0
    for i, ev in enumerate(events, 1):
        ru, st = ev.rune, ev.state
        delta = ""
        if prev is not None:
            before = prev.effect(ru.effect_id)
            after = st.effect(ru.effect_id)
            if before is not None and after is not None:
                d = after - before
                delta = f"{d:+d}"
            elif after is not None:
                delta = f"+{after}"   # nouvel effet
        effs = ", ".join(f"{effect_name(e)}: {v}" for e, v in st.effects)
        if prices is not None:
            price = prices.get(ru.gid, 0)
            cost = price  # 1 rune consommee par pose (kfb)
            total += cost
            px = f"{price:>9,}" if price else f"{'n/a':>9}"
            cx = f"{cost:>9,}" if cost else f"{'n/a':>9}"
            print(f"{i:>3}  {ru.ts[11:23]:<13} {ru.name:<18} "
                  f"{effect_name(ru.effect_id):<22} {ru.weight:>7} {delta:>6} "
                  f"{st.state:>4} {st.puit or 0:>5.1f} {px} {cx}  {effs}")
        else:
            print(f"{i:>3}  {ru.ts[11:23]:<13} {ru.name:<18} "
                  f"{effect_name(ru.effect_id):<22} {ru.weight:>7} {delta:>6} "
                  f"{st.state:>4} {st.puit or 0:>5.1f}  {effs}")
        prev = st
    if prices is not None:
        noprice = sum(1 for ev in events if not prices.get(ev.rune.gid))
        print("-" * (len(hdr) - 2))
        print(f"TOTAL depense en runes : {total:,} kamas".replace(",", " "))
        if noprice:
            print(f"({noprice} pose(s) sans prix moyen — jamais vues a l'HDV)")

    if template is not None:
        final = events[-1].state
        print()
        print(f"Jet de l'item ({item_name(final.gid)}) — "
              f"valeur actuelle vs maxi du template (%% = actuel/maxi) :")
        print(f"{'stat':<24} {'actuel':>7} {'mini':>6} {'maxi':>6} {'% jet':>8}")
        print("-" * 55)
        pcts: list[float] = []
        for eid, v in sorted(final.effects, key=lambda x: x[0]):
            sv = signed_value(eid, v)
            t = template.get(eid)
            if t is None:
                tag = "malus" if sv < 0 else "exo/n.t."
                print(f"{effect_name(eid):<24} {sv:>7} {'':>6} {'':>6} "
                      f"{tag:>8}")   # absent du template (ajoute FM / malus)
                continue
            lo, hi = t
            if hi <= 0:
                tag = "malus" if sv < 0 else "n/a"
                print(f"{effect_name(eid):<24} {sv:>7} {lo:>6} {hi:>6} "
                      f"{tag:>8}")
                continue
            p = sv / hi * 100.0
            print(f"{effect_name(eid):<24} {sv:>7} {lo:>6} {hi:>6} {p:>7.1f}%")
            # % global : lignes POSITIVES uniquement (malus exclus)
            if sv >= 0:
                pcts.append(p)
        if pcts:
            global_pct = sum(pcts) / len(pcts)
            print("-" * 55)
            print(f"{'JET GLOBAL':<24} {'':>7} {'':>6} {'':>6} "
                  f"{global_pct:>7.1f}%   (moyenne des {len(pcts)} lignes "
                  f"positives, malus exclus)")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Decodeur Forgemagie (frames.jsonl de fm_live)")
    ap.add_argument("jsonl", help="journal fm_live (frames.jsonl)")
    ap.add_argument("--item", type=int, default=None, help="filtrer sur un GID d'item")
    ap.add_argument("--prices", default=None, help="prices.json (sortie de `prices`)")
    ap.add_argument("--jet", type=int, default=None,
                    help="GID d'item : affiche le %% du jet (valeur vs mini->maxi du "
                         "template dofusdb, via item_jet.py) en fin de rapport")
    args = ap.parse_args(argv)

    rows = load_rows(args.jsonl)
    events = decode_session(rows)
    if args.item is not None:
        events = [e for e in events if e.state.gid == args.item]
    prices = None
    if args.prices:
        with open(args.prices, encoding="utf-8") as f:
            prices = {int(k): v for k, v in json.load(f).items()}
    template = None
    if args.jet is not None:
        from item_jet import get_template
        template = get_template(args.jet)
    render(events, prices=prices, template=template)
    return 0


if __name__ == "__main__":
    sys.exit(main())
