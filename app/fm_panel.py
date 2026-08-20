#!/usr/bin/env python3
"""
fm_panel.py — Panneau de controle FM en direct (Dofus 3, port 5555).

Affiche dans le terminal, pose de rune apres pose de rune :
- l'issue de la forge (SC = succes critique, SN = succes neutre,
  EC = echec critique, rien = aucun changement) + compteurs ;
- le PUITS courant et sa variation, avec le calcul du reliquat
  (Reliquat = poids perdu - poids de la rune, cf. FM_FONCTIONNEMENT.md) ;
- le nombre de runes posees, par type ;
- l'etat de l'item (effets) et l'historique roulant des poses.

Usage :
    python fm_panel.py live --out _scratch/panel     # capture live (admin/npcap)
    python fm_panel.py replay captures/fm_2026-08-20.jsonl   # relire un journal

Le journal JSONL est conserve (reutilisable par fm_decoder.py).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, deque
from datetime import datetime
from typing import Optional

try:
    from scapy.all import Raw, TCP, IP, sniff
except ImportError:
    Raw = TCP = IP = sniff = None

from fm_live import TcpStream, extract_envelope
from fm_decoder import (EFFECTS, ITEMS, RUNES, MALUS_EFFECTS, effect_name,
                        effect_str, item_name, parse_iuj, parse_kdr, parse_kfb)
from fetch_runes import rune_weight
from item_jet import get_template, global_jet_pct
from paths import data_file, SCRATCH_DIR
from fm_cost import parse_ivi
from sniffer_hdv import parse_message

PORT_GAME = 5555
FORGE_SLOT = 63   # emplacement de l'item dans l'interface de forgemagie

# Densite (poids de base) par effectId — source DPLN (poids simple), cf.
# dofuspourlesnoobs.com/guide-forgemagie.html. Inconnu -> 1.0 (fallback).
DENSITY: dict[int, float] = {
    111: 100, 128: 90, 117: 51, 182: 30, 112: 20,
    2800: 15, 2804: 15, 2808: 15, 2812: 15, 2803: 15, 2807: 15,
    115: 10, 178: 10, 220: 5, 795: 5,
    422: 5, 424: 5, 426: 5, 428: 5, 430: 5, 418: 5, 414: 5, 225: 5,
    240: 2, 241: 2, 242: 2, 243: 2, 244: 2, 420: 2, 416: 2,
    210: 6, 211: 6, 212: 6, 213: 6, 214: 6,
    160: 7, 161: 7, 410: 7, 412: 7,
    752: 4, 753: 4, 158: 2.5, 138: 2, 226: 2,
    118: 1, 119: 1, 123: 1, 124: 3, 125: 2, 126: 1, 174: 1, 176: 3,
}


# ------------------------------------------------------------- classif

def classify(before: Optional[dict], after: dict, target: int, w: int) -> str:
    """SC = seule la stat visee bouge (+w) ; SN = +w et d'autres stats
    bougent ; EC = la rune ne s'ajoute pas (item inchange ou autres stats
    qui bougent)."""
    if before is None:
        return "?"
    deltas = {e: (a, b) for e in set(before) | set(after)
              for a, b in [(before.get(e), after.get(e))] if a != b}
    t = deltas.get(target)
    t_added = t is not None and t[1] is not None and (t[1] - (t[0] or 0)) == w
    others = {e: d for e, d in deltas.items() if e != target}
    if t_added and not others:
        return "sc"
    if t_added and others:
        return "sn"
    return "ec"


def reliquat_of(deltas: dict, target: int) -> float:
    """Poids perdu - (les baisses x densite), hors gain de la cible.
    Une stat supprimee (b None) compte comme 0."""
    perdu = 0.0
    for e, (a, b) in deltas.items():
        bv = b if b is not None else 0
        if a is not None and bv < a:
            perdu += (a - bv) * DENSITY.get(e, 1.0)
    return perdu


# ------------------------------------------------------------- panneau

class FmPanel:
    def __init__(self, outdir: str) -> None:
        self.outdir = outdir
        os.makedirs(outdir, exist_ok=True)
        self.log_path = os.path.join(outdir, "frames.jsonl")
        self._log = open(self.log_path, "a", encoding="utf-8")
        self.flows: dict[tuple, TcpStream] = {}
        self.n = 0
        self.events: deque = deque(maxlen=80)
        self.rune_counts: Counter = Counter()
        self.rune_by_stat: Counter = Counter()
        self.outcomes: Counter = Counter()
        self.puit: Optional[float] = None
        self.puit_prev: Optional[float] = None
        self.puit_delta_total = 0.0
        self.reliquat_cumul = 0.0
        self.item_name = ""
        self.item_gid = 0
        self.item_uid = 0
        self.item_slot = 0
        self._effects: Optional[dict] = None
        self._rune = None
        self._template: Optional[dict[int, tuple[int, int]]] = None
        self._template_loaded = False
        self.prices: dict[int, int] = {}
        self._prices_loaded = False
        self.prices_rev = 0
        self._pending_price_gid: Optional[int] = None
        self.cost_total = 0
        self.cost_by_stat: Counter = Counter()
        self.t0 = datetime.now()
        self.poses = 0
        self.event_no = 0

    def close(self) -> None:
        if self._log:
            self._log.close()

    # --- flux ---
    def feed(self, direction: str, data: bytes, flow_key: tuple) -> None:
        stream = self.flows.setdefault(flow_key, TcpStream())
        for frame in stream.feed(data):
            self._frame(direction, frame)

    def _frame(self, direction: str, frame: bytes) -> None:
        url, payload = extract_envelope(frame)
        name = url.rsplit("/", 1)[-1] if url else "?"
        if payload is None:
            return
        rec = {"ts": datetime.now().isoformat(timespec="milliseconds"),
               "dir": direction, "url": url, "type": name,
               "frame_hex": frame.hex(), "payload_hex": payload.hex()}
        ivi_batch = None
        if name == "ivi":
            rec["frame_hex"] = ""
            rec["payload_hex"] = ""
            ivi_batch = parse_ivi(payload)
            rec["n_prices"] = len(ivi_batch)
        self._log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._log.flush()
        self.n += 1
        if name == "kfb":
            ru = parse_kfb(payload)
            if ru:
                self._rune = ru
        elif name == "kdr":
            st = parse_kdr(payload)
            if st:
                pending = self._rune
                if self._is_other_item(st):
                    self._switch_item(st)
                    self._rune = pending
                self._on_state(st, rec["ts"])
        elif name == "ivi":
            if ivi_batch:
                self._apply_prices(ivi_batch)
        elif name == "iwo":
            fields = {f: v for f, w, v in parse_message(payload) if w == 0}
            gid = fields.get(1)
            if gid is not None:
                self._pending_price_gid = int(gid)
        elif name == "kgq":
            fields = {f: v for f, w, v in parse_message(payload) if w == 0}
            price = fields.get(1)
            if self._pending_price_gid and price is not None:
                self._apply_prices({self._pending_price_gid: int(price)})
        elif name == "iuj":
            st = parse_iuj(payload)
            if st and st.gid:
                if st.slot == FORGE_SLOT:
                    if self._is_other_item(st):
                        self._switch_item(st)
                    self.item_slot = st.slot
                    if st.uid:
                        self.item_uid = st.uid
                    if self._effects is None and st.effects:
                        self._effects = dict(st.effects)
                    self._render()
                elif not self.item_gid:
                    self.item_gid, self.item_uid, self.item_slot = \
                        st.gid, st.uid, st.slot
                    self.item_name = item_name(st.gid)
                    self._load_template()
                    self._render()

    def _is_other_item(self, st) -> bool:
        """True si st n'est pas l'item actuellement en forge (gid ou uid)."""
        if not getattr(st, "gid", 0):
            return False
        if not self.item_gid:
            return True
        if st.gid != self.item_gid:
            return True
        uid = getattr(st, "uid", 0) or 0
        if uid and self.item_uid and uid != self.item_uid:
            return True
        return False

    def _switch_item(self, st) -> None:
        """Nouvel item forge : reset des compteurs (restaures ensuite par le bridge)."""
        self.item_gid, self.item_uid, self.item_slot = \
            st.gid, st.uid, st.slot
        self.item_name = item_name(st.gid)
        self._template_loaded = False
        self._template = None
        self._load_template()
        self._effects = None
        self._rune = None
        self.puit = self.puit_prev = None
        self.puit_delta_total = 0.0
        self.reliquat_cumul = 0.0
        self.rune_counts = Counter()
        self.rune_by_stat = Counter()
        self.outcomes = Counter()
        self.events.clear()
        self.poses = 0
        self.cost_total = 0
        self.cost_by_stat = Counter()
        self.event_no = 0

    def _load_template(self) -> None:
        """Jet mini->maxi de l'item (items.json, sinon fetch dofusdb)."""
        if self._template_loaded:
            return
        self._template_loaded = True
        try:
            self._template = get_template(self.item_gid)
        except Exception as e:
            self._template = None

    def _jet_pct(self) -> Optional[float]:
        """% du jet global courant de l'item (None si inconnu)."""
        if not self._effects or not self._template:
            return None
        return global_jet_pct(self._effects, self._template, MALUS_EFFECTS)

    def _save_prices(self) -> None:
        path = data_file("prices.json")
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in self.prices.items()},
                          f, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError as e:
            print("[DOFUS-FM] prices.json:", e, file=sys.stderr)

    def _apply_prices(self, batch: dict[int, int]) -> None:
        if not batch:
            return
        self._load_prices()
        changed = False
        for gid, price in batch.items():
            try:
                gid_i, price_i = int(gid), int(price)
            except (TypeError, ValueError):
                continue
            if self.prices.get(gid_i) != price_i:
                self.prices[gid_i] = price_i
                changed = True
        if not changed:
            return
        self.prices_rev += 1
        self._save_prices()
        self._render()

    def _load_prices(self) -> None:
        """Table des prix moyens {gid: kamas} (prices.json, optionnel)."""
        if self._prices_loaded:
            return
        self._prices_loaded = True
        try:
            with open(data_file("prices.json"), encoding="utf-8") as f:
                self.prices = {int(k): v for k, v in json.load(f).items()}
        except (OSError, ValueError):
            self.prices = {}

    def _price_of(self, gid: int) -> Optional[int]:
        self._load_prices()
        return self.prices.get(gid)

    def _on_state(self, st, ts: str) -> None:
        effects = dict(st.effects)
        outcome = classify(self._effects, effects, self._rune.effect_id,
                           self._rune.weight) if self._rune else "?"
        deltas = {}
        if self._effects is not None:
            deltas = {e: (a, b) for e in set(self._effects) | set(effects)
                      for a, b in [(self._effects.get(e), effects.get(e))]
                      if a != b}
        perdu = reliquat_of(deltas, self._rune.effect_id if self._rune else -1)
        w = 0.0
        if self._rune:
            w = rune_weight(self._rune.name)
            if w is None:
                w = DENSITY.get(self._rune.effect_id, 1.0)
        rel = perdu - w if outcome != "?" else None
        self.reliquat_cumul += rel if rel is not None else 0
        puit = st.puit
        dpuit = None
        if puit is not None and self.puit_prev is not None:
            dpuit = puit - self.puit_prev
            self.puit_delta_total += dpuit
        self.puit_prev = puit
        self.puit = puit
        self.outcomes[outcome] += 1
        cost = None
        if self._rune:
            self.rune_counts[self._rune.gid] += 1
            if self._rune.effect_id:
                self.rune_by_stat[self._rune.effect_id] += 1
            self.poses += 1
            price = self._price_of(self._rune.gid)
            if price is not None:
                cost = price
                self.cost_total += cost
                if self._rune.effect_id:
                    self.cost_by_stat[self._rune.effect_id] += cost
        self.event_no += 1
        self.events.append((self.event_no,
                            ts[11:19],
                            self._rune, outcome, effects, puit, dpuit, rel,
                            perdu, cost))
        self._effects = effects
        self._rune = None
        self._render()

    # --- affichage ---
    def _render(self) -> None:
        out = []
        out.append("\033[2J\033[H")  # clear + home
        dur = str(datetime.now() - self.t0).split(".")[0]
        out.append(f"\033[1;96m=== FM CONTROL PANEL ===\033[0m   session {dur}   "
                   f"{self.poses} pose(s)")
        out.append(f"Item : \033[1;33m{self.item_name or '...'}\033[0m "
                   f"(GID {self.item_gid}, UID {self.item_uid}, "
                   f"slot {self.item_slot})")
        puit_s = f"{self.puit:.1f}" if self.puit is not None else "-"
        dpuit_s = f"{self.puit_delta_total:+.1f}"
        out.append(f"Puits : \033[1;32m{puit_s}\033[0m "
                   f"(total \033[1;36m{dpuit_s}\033[0m)   "
                   f"reliquat cumule \033[1;35m{self.reliquat_cumul:+.1f}\033[0m")
        jet = self._jet_pct()
        if jet is not None:
            col = "\033[1;32m" if jet >= 80 else \
                  "\033[1;33m" if jet >= 50 else "\033[1;31m"
            out.append(f"Jet item : {col}{jet:.1f}%\033[0m  "
                       f"(toutes les lignes du jet, malus exclus)")
        elif self.item_gid and self._template_loaded:
            out.append("Jet item : \033[90mtemplate indisponible\033[0m")
        total_runes = sum(self.rune_counts.values())
        top = ", ".join(f"{RUNES.get(g, g)} x{c}"
                        for g, c in self.rune_counts.most_common(8))
        out.append(f"Runes : \033[1;33m{total_runes}\033[0m posee(s)  "
                   f"[{top}]")
        if self.prices:
            out.append(f"Depense runes : \033[1;33m{self.cost_total:,}\033[0m "
                       f"kamas (prix moyens, prices.json)"
                       .replace(",", " "))
        else:
            out.append("Depense runes : \033[90mprix moyens non charges "
                       "(lancer `fm_cost.py prices` pour creer prices.json)\033[0m")
        o = self.outcomes
        out.append("Issues : "
                   f"SC \033[1;32m{o['sc']}\033[0m  "
                   f"SN \033[1;36m{o['sn']}\033[0m  "
                   f"EC \033[1;31m{o['ec']}\033[0m  "
                   f"rien \033[90m{o['rien']}\033[0m  "
                   f"base \033[90m{o['?']}\033[0m")
        out.append("\033[90m" + "-" * 78 + "\033[0m")
        for num, ts, ru, oc, eff, puit, dpuit, rel, perdu, cost in self.events:
            if ru is None:
                continue
            col = {"sc": "\033[1;32mSC\033[0m", "sn": "\033[1;36mSN\033[0m",
                   "ec": "\033[1;31mEC\033[0m", "rien": "\033[90mrien\033[0m",
                   "?": "\033[90m?\033[0m"}.get(oc, oc)
            rname = RUNES.get(ru.gid, f"gid {ru.gid}")
            puit_s = f"{puit:.1f}" if puit is not None else "-"
            dpuit_s = f"{dpuit:+.1f}" if dpuit is not None else " "
            rel_s = f"{rel:+.1f} (perdu {perdu:.1f})" if rel is not None else "-"
            cost_s = f" {cost:,} k" if cost else ""
            out.append(f"#{num:<3} {ts}  {rname:<18} {col}  "
                       f"puit {puit_s} ({dpuit_s})  "
                       f"reliquat {rel_s}{cost_s}")
        if self._effects:
            eff_s = ", ".join(effect_str(e, v)
                              for e, v in sorted(self._effects.items(),
                                                 key=lambda x: -x[1]))
            out.append("\033[90m" + "-" * 78 + "\033[0m")
            out.append(f"Item : {eff_s}")
        sys.stdout.write("\n".join(out) + "\n")
        sys.stdout.flush()


# ------------------------------------------------------------- capture

def _feed_pkt(panel: FmPanel, pkt) -> None:
    if TCP in pkt and Raw in pkt:
        dport, sport = pkt[TCP].dport, pkt[TCP].sport
        if dport != PORT_GAME and sport != PORT_GAME:
            return
        direction = "s2c" if sport == PORT_GAME else "c2s"
        src = pkt[IP].src if IP in pkt else "?"
        dst = pkt[IP].dst if IP in pkt else "?"
        panel.feed(direction, bytes(pkt[Raw].load), (src, sport, dst, dport))


def live(outdir: str, timeout: Optional[int] = None) -> int:
    if sniff is None:
        raise RuntimeError("scapy requis : pip install scapy")
    panel = FmPanel(outdir)
    try:
        print(f"Panneau FM sur le port {PORT_GAME} - Ctrl+C pour arreter. "
              f"Log: {panel.log_path}", flush=True)
        sniff(filter=f"tcp port {PORT_GAME}", store=False,
              prn=lambda pkt: _feed_pkt(panel, pkt), timeout=timeout)
    except PermissionError as e:
        print(f"ERREUR permissions : {e}\nAdmin requis (npcap).")
        return 2
    finally:
        panel.close()
    return 0


def replay(path: str, outdir: str) -> int:
    panel = FmPanel(outdir)
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            panel._frame(r["dir"], bytes.fromhex(r["frame_hex"]))
    finally:
        panel.close()
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Panneau de controle FM")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_l = sub.add_parser("live", help="Capture en temps reel (admin/npcap)")
    p_l.add_argument("--out", default=os.path.join(SCRATCH_DIR, "panel"))
    p_l.add_argument("--timeout", type=int, default=None)
    p_r = sub.add_parser("replay", help="Relire un journal frames.jsonl")
    p_r.add_argument("jsonl")
    p_r.add_argument("--out", default=os.path.join(SCRATCH_DIR, "panel"))
    args = ap.parse_args(argv)
    if args.cmd == "live":
        return live(args.out, args.timeout)
    if args.cmd == "replay":
        return replay(args.jsonl, args.out)
    return 2


if __name__ == "__main__":
    sys.exit(main())
