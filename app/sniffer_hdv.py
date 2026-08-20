"""
sniffer_hdv.py — Parseur du protocole HDV de Dofus 3 (port 5555).

Reverse-engineeré le 2026-08-09 sur le client 3.6.10.10 (voir PROTOCOL.md).

- Framing réseau : [varint longueur][message protobuf]
- Enveloppe      : field 1 = type_url "type.ankama.com/<obfusque>", field 2 = payload
- kda            : liste des items d'une categorie HDV (GIDs dans un blob binaire)
- kbt            : annonces d'un item selectionne (f2 = gid, f3 repete = annonces)

Usage :
    python sniffer_hdv.py parse pcaps/dofus2.pcap --item 9151
    python sniffer_hdv.py parse pcaps/dofus.pcap
    python sniffer_hdv.py live --port 5555        # capture temps reel (admin/npcap)
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

try:
    from scapy.all import PcapReader, Raw, TCP, IP, sniff
except ImportError:  # permet l'import du module meme sans scapy
    PcapReader = Raw = TCP = IP = sniff = None

PORT_GAME = 5555
TYPE_URL_MARK = b"type.ankama.com/"
MAX_FRAME = 10_000_000


def read_varint(buf: bytes, i: int = 0) -> tuple[int, int]:
    """Varint LEB128 depuis buf[i:] -> (valeur, index suivant)."""
    r = 0
    shift = 0
    n = len(buf)
    while i < n:
        x = buf[i]
        i += 1
        r |= (x & 0x7F) << shift
        if not x & 0x80:
            return r, i
        shift += 7
    raise ValueError("varint tronque")


def split_frames(stream: bytes) -> list[bytes]:
    """Decoupe un flux en trames [varint longueur][payload]."""
    frames: list[bytes] = []
    i = 0
    n = len(stream)
    while i < n:
        try:
            ln, j = read_varint(stream, i)
        except ValueError:
            break
        if ln <= 0 or ln > MAX_FRAME or j + ln > n:
            i += 1
            continue
        frames.append(stream[j:j + ln])
        i = j + ln
    return frames


def parse_message(buf: bytes) -> list[tuple[int, int, object]]:
    """Parse protobuf -> [(numero_de_champ, wire_type, valeur)]."""
    out: list[tuple[int, int, object]] = []
    i = 0
    n = len(buf)
    while i < n:
        try:
            tag, i = read_varint(buf, i)
        except ValueError:
            break
        fnum, wt = tag >> 3, tag & 7
        if wt == 0:
            v, i = read_varint(buf, i)
            out.append((fnum, 0, v))
        elif wt == 1:
            if i + 8 > n:
                break
            out.append((fnum, 1, buf[i:i + 8]))
            i += 8
        elif wt == 2:
            ln, i = read_varint(buf, i)
            if i + ln > n:
                break
            out.append((fnum, 2, buf[i:i + ln]))
            i += ln
        elif wt == 5:
            if i + 4 > n:
                break
            out.append((fnum, 5, buf[i:i + 4]))
            i += 4
        else:
            break
    return out


def is_ascii(b: bytes) -> bool:
    return bool(b) and all(32 <= c < 128 for c in b)


def type_url_of(frame: bytes) -> Optional[str]:
    """Type_url de l'enveloppe (ex. 'type.ankama.com/kbt')."""
    def walk(v, depth=0):
        if depth > 8:
            return None
        for fnum, wt, val in v:
            if wt == 2 and isinstance(val, bytes):
                if is_ascii(val) and TYPE_URL_MARK in val:
                    return val.decode("ascii")
                r = walk(parse_message(val), depth + 1)
                if r:
                    return r
        return None
    return walk(parse_message(frame))

# ------------------------------------------------------------- modele HDV

@dataclass
class Listing:
    uid: int       # identifiant unique de l'annonce
    gid: int       # GID Dofus de l'item
    price: int     # prix en kamas (varint LEB128)
    quantity: int  # quantite
    raw: bytes


@dataclass
class HdvEvent:
    kind: str                 # "list" | "listings"
    gid: Optional[int] = None
    listings: list[Listing] = field(default_factory=list)
    frame: bytes = b""
    direction: str = "s2c"


def _envelope_payload(m: list) -> Optional[bytes]:
    """Descend l'enveloppe imbriquee : f1 bytes -> ... -> {f1 type_url, f2 payload}."""
    for fnum, wt, val in m:
        if wt == 2 and isinstance(val, bytes):
            sub = parse_message(val)
            f1s = [v for n, w, v in sub
                   if n == 1 and w == 2 and isinstance(v, bytes) and is_ascii(v)]
            f2s = [v for n, w, v in sub
                   if n == 2 and w == 2 and isinstance(v, bytes)]
            if f1s and TYPE_URL_MARK in f1s[0] and f2s:
                return f2s[0]
            r = _envelope_payload(sub)
            if r is not None:
                return r
    return None


def decode_kbt(frame: bytes) -> tuple[Optional[int], list[Listing]]:
    """Decode un message kbt -> (gid, annonces)."""
    payload = _envelope_payload(parse_message(frame))
    if payload is None:
        return None, []

    gid: Optional[int] = None
    listings: list[Listing] = []
    for fnum, wt, val in parse_message(payload):
        if wt == 0 and fnum == 2:
            gid = val
        elif wt == 2 and fnum == 3 and isinstance(val, bytes):
            rec: dict[int, object] = {}
            for lf, lw, lv in parse_message(val):
                rec[lf] = lv
            uid = rec.get(1) if isinstance(rec.get(1), int) else 0
            rgid = rec.get(5) if isinstance(rec.get(5), int) else (gid or 0)
            qty = rec.get(8) if isinstance(rec.get(8), int) else 1
            price = 0
            f6 = rec.get(6)
            if isinstance(f6, bytes) and f6:
                try:
                    price, _ = read_varint(f6, 0)
                except ValueError:
                    price = 0
            listings.append(Listing(uid=uid, gid=rgid, price=price,
                                    quantity=qty, raw=val))
    return gid, listings


# ------------------------------------------------------------- flux TCP / parseur

@dataclass
class TcpStream:
    buf: bytes = b""

    def feed(self, payload: bytes) -> list[bytes]:
        self.buf += payload
        frames: list[bytes] = []
        while True:
            try:
                ln, j = read_varint(self.buf, 0)
            except ValueError:
                break
            if ln <= 0 or ln > MAX_FRAME:
                self.buf = self.buf[1:]
                continue
            end = j + ln
            if end > len(self.buf):
                break
            frames.append(self.buf[j:end])
            self.buf = self.buf[end:]
        return frames


class HdvParser:
    """Recoit des payloads TCP (direction, data) et emet des HdvEvent."""

    def __init__(self) -> None:
        self._flows: dict[tuple, TcpStream] = {}
        self.listeners: list[Callable[[HdvEvent], None]] = []

    def on(self, cb: Callable[[HdvEvent], None]) -> None:
        self.listeners.append(cb)

    def feed(self, direction: str, data: bytes, flow_key: tuple = ("?",)) -> list[HdvEvent]:
        stream = self._flows.setdefault(flow_key, TcpStream())
        events: list[HdvEvent] = []
        for frame in stream.feed(data):
            ev = self._event_from_frame(direction, frame)
            if ev is not None:
                events.append(ev)
                for cb in self.listeners:
                    cb(ev)
        return events

    def _event_from_frame(self, direction: str, frame: bytes) -> Optional[HdvEvent]:
        url = type_url_of(frame)
        if url is None:
            return None
        name = url.rsplit("/", 1)[-1]
        if name == "kbt":
            gid, listings = decode_kbt(frame)
            return HdvEvent(kind="listings", gid=gid, listings=listings,
                            frame=frame, direction=direction)
        if name == "kda":
            return HdvEvent(kind="list", frame=frame, direction=direction)
        return None

# ------------------------------------------------------------- entrees

def iter_pcap_payloads(pcap_path: str, port: int = PORT_GAME):
    """Itere (direction, payload, flow_key) sur les payloads du pcap, port filtre."""
    if PcapReader is None:
        raise RuntimeError("scapy requis : pip install scapy")
    for pkt in PcapReader(pcap_path):
        if TCP not in pkt or Raw not in pkt:
            continue
        dport, sport = pkt[TCP].dport, pkt[TCP].sport
        if dport != port and sport != port:
            continue
        direction = "s2c" if sport == port else "c2s"
        src = pkt[IP].src if IP in pkt else "?"
        dst = pkt[IP].dst if IP in pkt else "?"
        yield direction, bytes(pkt[Raw].load), (src, sport, dst, dport)


def parse_pcap(pcap_path: str, port: int = PORT_GAME,
               item: Optional[int] = None) -> list[HdvEvent]:
    parser = HdvParser()
    events: list[HdvEvent] = []
    for direction, payload, key in iter_pcap_payloads(pcap_path, port):
        events.extend(parser.feed(direction, payload, key))
    if item is not None:
        events = [e for e in events if e.kind == "listings" and e.gid == item]
    return events


def live(port: int = PORT_GAME, timeout: Optional[int] = None) -> None:
    if sniff is None:
        raise RuntimeError("scapy requis : pip install scapy")
    parser = HdvParser()
    parser.on(lambda ev: _print_event(ev))
    print(f"Capture en direct sur le port {port} (admin/npcap requis). Ctrl+C pour arreter.")
    sniff(filter=f"tcp port {port}", store=False,
          prn=lambda pkt: _feed_pkt(parser, pkt), timeout=timeout)


def _feed_pkt(parser: HdvParser, pkt) -> None:
    if TCP in pkt and Raw in pkt:
        dport, sport = pkt[TCP].dport, pkt[TCP].sport
        direction = "s2c" if sport == PORT_GAME else "c2s"
        src = pkt[IP].src if IP in pkt else "?"
        dst = pkt[IP].dst if IP in pkt else "?"
        parser.feed(direction, bytes(pkt[Raw].load), (src, sport, dst, dport))


def _print_event(ev: HdvEvent) -> None:
    if ev.kind == "listings":
        prices = sorted(l.price for l in ev.listings)
        if not prices:
            print(f"item {ev.gid}: pas d'annonces en vente")
            return
        print(f"item {ev.gid}: {len(ev.listings)} vente(s) — "
              f"min {prices[0]}, max {prices[-1]}, "
              f"moyenne {sum(prices) // len(prices)}")
        for l in sorted(ev.listings, key=lambda l: l.price):
            print(f"    uid={l.uid:<6} prix={l.price:>9} qty={l.quantity}")
    else:
        print(f"evenement {ev.kind} ({len(ev.frame)}b)")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Parseur protocole HDV Dofus 3 (voir PROTOCOL.md)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_parse = sub.add_parser("parse", help="Analyser un pcap enregistre")
    p_parse.add_argument("pcap")
    p_parse.add_argument("--port", type=int, default=PORT_GAME)
    p_parse.add_argument("--item", type=int, default=None,
                         help="Filtrer sur un GID d'item")
    sub.add_parser("live", help="Capture en temps reel (admin/npcap)")
    args = ap.parse_args(argv)

    if args.cmd == "parse":
        events = parse_pcap(args.pcap, args.port, args.item)
        if not events:
            print("aucun evenement HDV trouve")
            return 1
        for ev in events:
            _print_event(ev)
        return 0
    if args.cmd == "live":
        live(args.port)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
