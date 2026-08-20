#!/usr/bin/env python3
"""
fm_live.py - Capture / decodeur Forgemagie (Dofus 3, port 5555).

Complément de sniffer_hdv.py, orienté Forgemagie :
- capture live (npcap, admin requis) OU relecture d'un pcap enregistré ;
- réassemblage TCP + découpage des trames [varint longueur][protobuf] ;
- dump récursif de TOUS les messages (pas seulement HDV) pour identifier
  les messages FM (pose de rune, état de l'item, effets…) dont les noms
  sont obfusqués (type.ankama.com/<obfusque>) ;
- journal JSONL + payloads bruts pour analyse offline.

Usage :
    python fm_live.py live --out _scratch/capture --timeout 120
    python fm_live.py live --fm --out _scratch/capture   # mode FM epure + marqueurs Entree
    python fm_live.py replay pcaps/dofus2.pcap --out _scratch/capture
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Optional

try:
    from scapy.all import PcapReader, Raw, TCP, IP, sniff
except ImportError:  # permet l'import du module meme sans scapy
    PcapReader = Raw = TCP = IP = sniff = None

from sniffer_hdv import (PORT_GAME, TcpStream, decode_kbt, is_ascii,
                         parse_message)

TYPE_URL_MARK = b"type.ankama.com/"


# ------------------------------------------------------------- enveloppe

def extract_envelope(frame: bytes) -> tuple[Optional[str], Optional[bytes]]:
    """Enveloppe protobuf (imbrication quelconque) -> (type_url, payload)."""
    r = _walk_envelope(frame, 0)
    return r if r else (None, None)


def _walk_envelope(buf: bytes, depth: int) -> Optional[tuple[str, Optional[bytes]]]:
    if depth > 8:
        return None
    try:
        fields = parse_message(buf)
    except Exception:
        return None
    for fnum, wt, val in fields:
        if wt != 2 or not isinstance(val, bytes):
            continue
        if is_ascii(val) and TYPE_URL_MARK in val and len(val) < 256:
            url = val.decode("ascii", "replace")
            payload = None
            for f2, w2, v2 in fields:
                if f2 == 2 and w2 == 2 and isinstance(v2, bytes) and v2 != val:
                    payload = v2
                    break
            return url, payload
        r = _walk_envelope(val, depth + 1)
        if r:
            return r
    return None


# ------------------------------------------------------------- dump

def dump(buf: bytes, depth: int = 0, maxdepth: int = 8) -> list[str]:
    """Dump protobuf recursif -> lignes de texte (champs + sous-messages)."""
    try:
        fields = parse_message(buf)
    except Exception:
        return [f"{'  '*depth}<non protobuf: {buf[:32].hex()}>"]
    if not fields:
        return [f"{'  '*depth}<opaque {len(buf)}B>"]
    out: list[str] = []
    for fnum, wt, val in fields:
        pad = "  " * depth
        if wt == 0:
            out.append(f"{pad}f{fnum} = {val}")
        elif wt == 1:
            out.append(f"{pad}f{fnum} = fixed64 {val.hex()}")
        elif wt == 5:
            out.append(f"{pad}f{fnum} = fixed32 {val.hex()}")
        elif wt == 2 and isinstance(val, bytes):
            if is_ascii(val) and len(val) < 256:
                out.append(f"{pad}f{fnum} = \"{val.decode('utf-8','replace')}\"")
            else:
                out.append(f"{pad}f{fnum} = bytes[{len(val)}]")
                if depth < maxdepth:
                    out.extend(dump(val, depth + 1, maxdepth))
        else:
            out.append(f"{pad}f{fnum} = {val!r}")
    return out


# ------------------------------------------------------------- marqueur

class _MarkerThread:
    """Lit stdin (mode --fm) : chaque ligne saisie = marqueur horodate dans le
    journal, pour annoter ce qui est affiche a l'ecran pendant la session."""

    def __init__(self, cap: "FmCapture") -> None:
        self.cap = cap
        self._stop = False

    def start(self) -> None:
        import threading
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self) -> None:
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                self.cap.emit(f"[{self.cap._now()}] >>> MARQUEUR: {line}")
                if line.lower() in ("quit", "exit", "stop"):
                    self._stop = True
                    return
        except Exception:
            pass


# ------------------------------------------------------------- capture

class FmCapture:
    """Reassemble les flux TCP et journalise toutes les trames decodees."""

    def __init__(self, outdir: str, verbose: bool = True,
                 fm_only: bool = False) -> None:
        self.flows: dict[tuple, TcpStream] = {}
        self.outdir = outdir
        self.verbose = verbose
        self.fm_only = fm_only
        self.n = 0
        self._last_rune: Optional[str] = None
        self._marker = None
        self._txt = None
        os.makedirs(outdir, exist_ok=True)
        self.log_path = os.path.join(outdir, "frames.jsonl")
        self._log = open(self.log_path, "a", encoding="utf-8")
        self._txt = open(os.path.join(outdir, "frames.txt"), "a", encoding="utf-8")
        if fm_only:
            self._marker = _MarkerThread(self)
            self._marker.start()

    def close(self) -> None:
        if self._log:
            self._log.close()
        if self._txt:
            self._txt.close()

    def emit(self, line: str) -> None:
        try:
            print(line, flush=True)
        except UnicodeEncodeError:  # console cp1252 : remplace les caracteres inconnus
            print(line.encode("cp1252", "replace").decode("cp1252"), flush=True)
        if self._txt:
            self._txt.write(line + "\n")
            self._txt.flush()

    def feed(self, direction: str, data: bytes, flow_key: tuple) -> None:
        stream = self.flows.setdefault(flow_key, TcpStream())
        for frame in stream.feed(data):
            self.handle(direction, frame)

    def handle(self, direction: str, frame: bytes) -> None:
        url, payload = extract_envelope(frame)
        name = url.rsplit("/", 1)[-1] if url else "?"
        rec = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "dir": direction,
            "url": url,
            "type": name,
            "frame_hex": frame.hex(),
            "payload_hex": payload.hex() if payload is not None else "",
        }
        self._log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._log.flush()
        self.n += 1
        if self.fm_only:
            self._fm_hook(name, payload)
            return
        if not self.verbose:
            return
        self.emit(f"[{rec['ts'][11:23]}] {direction} {name} ({len(frame)}B)")
        if name == "kbt":
            gid, listings = decode_kbt(frame)
            if gid is not None:
                prices = sorted(l.price for l in listings)
                extra = (f" - {len(listings)} vente(s), "
                         f"min {prices[0] if prices else '-'}") if prices else ""
                self.emit(f"    gid={gid}{extra}")
        if payload is not None:
            for line in dump(payload):
                self.emit("    " + line)
        self._fm_hook(name, payload)

    def _fm_hook(self, name: str, payload: Optional[bytes]) -> None:
        """Ligne compacte Forgemagie (active si fm_decoder.py est present)."""
        if payload is None or name not in ("kfb", "kdr", "ivj"):
            return
        try:
            from fm_decoder import (MALUS_EFFECTS, RUNES, effect_name,
                                    parse_ivj, parse_kdr, parse_kfb)
        except ImportError:
            return
        if name == "kfb":
            ru = parse_kfb(payload)
            if ru:
                self._last_rune = ru.name
                self.emit(f"[{self._now()}] >> rune {ru.name} (gid {ru.gid}) : "
                          f"{effect_name(ru.effect_id)} +{ru.weight} "
                          f"[uid {ru.uid}]")
        elif name == "kdr":
            st = parse_kdr(payload)
            if st:
                effs = ", ".join(f"{effect_name(e)} {v}"
                                 for e, v in st.effects)
                puit = f"{st.puit:.1f}" if st.puit is not None else "-"
                rune = f" {self._last_rune} ->" if self._last_rune else ""
                jet = self._jet_pct(st)
                jet_s = f"  jet {jet:.1f}%" if jet is not None else ""
                self.emit(f"[{self._now()}] *** PUIT={puit}  etat={st.state}"
                          f"{rune}{jet_s}  [{effs}]")
        elif name == "ivj":
            q = parse_ivj(payload)
            if q:
                self.emit(f"[{self._now()}] >> pile rune UID {q[0]} : "
                          f"{q[1]} restante(s)")

    _JET_CACHE: dict[int, Optional[dict]] = {}

    def _jet_pct(self, st) -> Optional[float]:
        """% du jet global de l'item (items.json, sinon dofusdb en cache)."""
        if not st.effects or not st.gid:
            return None
        if st.gid not in self._JET_CACHE:
            try:
                from item_jet import get_template
                self._JET_CACHE[st.gid] = get_template(st.gid)
            except Exception:
                self._JET_CACHE[st.gid] = None
        tpl = self._JET_CACHE[st.gid]
        if not tpl:
            return None
        from item_jet import global_jet_pct
        from fm_decoder import MALUS_EFFECTS
        return global_jet_pct(dict(st.effects), tpl, MALUS_EFFECTS)

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="milliseconds")[11:23]


def _feed_pkt(cap: FmCapture, pkt) -> None:
    if TCP in pkt and Raw in pkt:
        dport, sport = pkt[TCP].dport, pkt[TCP].sport
        if dport != PORT_GAME and sport != PORT_GAME:
            return
        direction = "s2c" if sport == PORT_GAME else "c2s"
        src = pkt[IP].src if IP in pkt else "?"
        dst = pkt[IP].dst if IP in pkt else "?"
        cap.feed(direction, bytes(pkt[Raw].load), (src, sport, dst, dport))


def live(outdir: str, timeout: Optional[int] = None, verbose: bool = True,
         fm_only: bool = False) -> int:
    if sniff is None:
        raise RuntimeError("scapy requis : pip install scapy")
    cap = FmCapture(outdir, verbose, fm_only=fm_only)
    try:
        mode = "ForgeMagie (mode --fm : lignes FM + marqueurs Entree)" \
            if fm_only else "tous les messages"
        cap.emit(f"Capture {mode} sur le port {PORT_GAME} - "
                 f"Ctrl+C pour arreter. Log: {cap.log_path}")
        if fm_only:
            cap.emit("Appuie sur Entree (+ texte optionnel) pour poser un "
                     "marqueur, 'stop' pour arreter proprement.")
        sniff(filter=f"tcp port {PORT_GAME}", store=False,
              prn=lambda pkt: _feed_pkt(cap, pkt), timeout=timeout)
    except PermissionError as e:
        cap.emit(f"ERREUR permissions : {e}")
        cap.emit("Requis : terminal en mode Administrateur (npcap).")
        return 2
    finally:
        cap.emit(f"{cap.n} trame(s) capturee(s) -> {cap.log_path}")
        cap.close()
    return 0


def replay(pcap_path: str, outdir: str, verbose: bool = True) -> int:
    if PcapReader is None:
        raise RuntimeError("scapy requis : pip install scapy")
    cap = FmCapture(outdir, verbose)
    try:
        for direction, payload, key in _iter_pcap_payloads(pcap_path):
            cap.feed(direction, payload, key)
    finally:
        cap.emit(f"{cap.n} trame(s) relue(s) depuis {pcap_path} -> {cap.log_path}")
        cap.close()
    return 0


def _iter_pcap_payloads(pcap_path: str):
    for pkt in PcapReader(pcap_path):
        if TCP not in pkt or Raw not in pkt:
            continue
        dport, sport = pkt[TCP].dport, pkt[TCP].sport
        if dport != PORT_GAME and sport != PORT_GAME:
            continue
        direction = "s2c" if sport == PORT_GAME else "c2s"
        src = pkt[IP].src if IP in pkt else "?"
        dst = pkt[IP].dst if IP in pkt else "?"
        yield direction, bytes(pkt[Raw].load), (src, sport, dst, dport)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Capture/decodeur Forgemagie Dofus 3 (port 5555)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_live = sub.add_parser("live", help="Capture en temps reel (admin/npcap)")
    p_live.add_argument("--out", default="_scratch/capture", help="dossier de sortie")
    p_live.add_argument("--timeout", type=int, default=None,
                        help="arret automatique apres N secondes")
    p_live.add_argument("--quiet", action="store_true", help="journal seul, pas de dump")
    p_live.add_argument("--fm", action="store_true",
                        help="mode ForgeMagie : lignes FM epurees + marqueurs Entree")
    p_rp = sub.add_parser("replay", help="Relire un pcap enregistre")
    p_rp.add_argument("pcap")
    p_rp.add_argument("--out", default="_scratch/capture", help="dossier de sortie")
    p_rp.add_argument("--quiet", action="store_true", help="journal seul, pas de dump")
    args = ap.parse_args(argv)

    if args.cmd == "live":
        return live(args.out, args.timeout, verbose=not args.quiet,
                    fm_only=args.fm)
    if args.cmd == "replay":
        return replay(args.pcap, args.out, verbose=not args.quiet)
    return 2


if __name__ == "__main__":
    sys.exit(main())
