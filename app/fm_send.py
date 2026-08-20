"""
fm_send.py — PoC : poser une rune de forgemagie via injection TCP (Dofus 3).

Principe (reverses le 2026-08-20, voir PROTOCOL.md) :
    une pose de rune = UN SEUL message client->serveur 'kcj' (ObjectUse) :
        payload  = { f1 = UID de la rune, f3 = 1, f6 = 1 }
        frame    = f2{ f1{ f1{ Inner } } f2{-1} }   avec Inner = { f1: type_url, f2: payload }
    envoye sur le flux [varint longueur][frame] de la connexion TCP du client.

Injection : on forge un paquet TCP avec le meme (ip:port source) que le client
et le BON sequence number (suivi du flux en direct), puis on l'emet sur la
carte reseau (Npcap, admin requis). Le serveur traite kcj comme si le client
l'avait envoye, repond (kfb/kdr/iuj...) et le client affiche l'etat de l'item.

    ⚠️ ADMIN + Npcap requis. Injection = automatisation de jeu = contraire aux
    CGU Ankama, risque de bannissement. Usage d'etude uniquement.

Usage :
    python fm_send.py --uid 63847918 --dry-run   # construit + verifie, n'envoie rien
    python fm_send.py --uid 63847918             # injecte la pose de rune
    python fm_send.py --uid 63847918 --watch 5   # injecte puis surveille la reponse 5 s
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

from sniffer_hdv import PORT_GAME, parse_message, read_varint
from fm_live import extract_envelope

try:
    from scapy.all import IP, Raw, TCP, get_if_addr, get_if_list, send, sniff
except ImportError:
    IP = Raw = TCP = get_if_addr = get_if_list = send = sniff = None

TYPE_URL = b"type.ankama.com/kcj"


# ------------------------------------------------------------- construction

def varint(v: int) -> bytes:
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _field(fnum: int, wt: int, val) -> bytes:
    tag = varint((fnum << 3) | wt)
    if wt == 0:                      # varint : val = int
        return tag + varint(val)
    if wt == 2:                      # length-delimited : val = bytes
        return tag + varint(len(val)) + val
    raise ValueError(f"wire type {wt} non gere")


def build_kcj_frame(uid: int) -> bytes:
    """Construit la trame kcj (47 octets) pour la rune d'UID donne.

    Structure observee (capture 2026-08-20) :
        frame = f2{ E1 }
        E1    = f1{ E2 } f2{-1}
        E2    = f1{ type_url (chaîne) } f2{ payload }
    """
    payload = _field(1, 0, uid) + _field(3, 0, 1) + _field(6, 0, 1)
    e2 = _field(1, 2, TYPE_URL) + _field(2, 2, payload)             # f1{url} f2{payload}
    e1 = _field(1, 2, e2) + _field(2, 0, 0xFFFF_FFFF_FFFF_FFFF)     # f1{..} f2{-1}
    return _field(2, 2, e1)                                         # f2{ E1 }
    # wire = varint(len(frame)) + frame


def check_frame(frame: bytes) -> Optional[str]:
    """Verifie qu'une trame kcj se decode correctement -> type_url ou None."""
    url, payload = extract_envelope(frame)
    if url != "type.ankama.com/kcj" or not payload:
        return None
    fields = dict((f, v) for f, w, v in parse_message(payload))
    return f"OK kcj uid={fields.get(1)}"


# ------------------------------------------------------------- etat connexion

class ConnState:
    def __init__(self) -> None:
        self.client_ip: Optional[str] = None
        self.client_port: Optional[int] = None
        self.server_ip: Optional[str] = None
        self.server_port: Optional[int] = None
        self.client_seq: Optional[int] = None   # prochain seq c2s (SND.NXT)
        self.server_ack: Optional[int] = None   # dernier ack du serveur observe

    def ready(self) -> bool:
        return all(v is not None for v in (
            self.client_ip, self.client_port, self.server_ip,
            self.server_port, self.client_seq))


def _observe(state: ConnState, pkt) -> None:
    if TCP not in pkt:
        return
    tcp = pkt[TCP]
    ip = pkt[IP] if IP in pkt else None
    if ip is None:
        return
    if tcp.sport == PORT_GAME:                      # serveur -> client
        state.server_ip, state.server_port = ip.src, tcp.sport
        state.client_ip, state.client_port = ip.dst, tcp.dport
        ln = len(bytes(pkt[Raw].load)) if Raw in pkt else 0
        state.server_ack = tcp.seq + ln
    elif tcp.dport == PORT_GAME:                    # client -> serveur
        state.client_ip, state.client_port = ip.src, tcp.sport
        state.server_ip, state.server_port = ip.dst, tcp.dport
        ln = len(bytes(pkt[Raw].load)) if Raw in pkt else 0
        state.client_seq = tcp.seq + ln
        state.server_ack = tcp.ack


def learn_connection(timeout: float = 5.0) -> ConnState:
    """Sniffe quelques paquets du port 5555 pour apprendre la connexion."""
    if sniff is None:
        raise RuntimeError("scapy requis : pip install scapy")
    state = ConnState()
    sniff(filter=f"tcp port {PORT_GAME}", store=False, timeout=timeout,
          prn=lambda p: _observe(state, p))
    return state


def _iface_for(ip: str) -> Optional[str]:
    for name in get_if_list():
        try:
            if get_if_addr(name) == ip:
                return name
        except Exception:
            continue
    return None


# ------------------------------------------------------------- injection

def inject(frame: bytes, state: ConnState, iface: Optional[str] = None) -> None:
    """Injecte la trame sur la connexion client->serveur (raw TCP, admin)."""
    if send is None or iface is None:
        raise RuntimeError("scapy avec Npcap requis (admin)")
    pkt = IP(src=state.client_ip, dst=state.server_ip) / \
        TCP(sport=state.client_port, dport=PORT_GAME,
            seq=state.client_seq,
            ack=state.server_ack or 0,
            flags="PA", window=65535) / \
        (varint(len(frame)) + frame)
    print(f"[inject] {state.client_ip}:{state.client_port} -> "
          f"{state.server_ip}:{state.server_port}  seq={state.client_seq} "
          f"ack={state.server_ack or 0}  {len(frame)} octets")
    send(pkt, iface=iface, verbose=False)


# ------------------------------------------------------------- entree

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="PoC : poser une rune via injection TCP")
    ap.add_argument("--uid", type=int, required=True, help="UID de la rune (cf. panneau)")
    ap.add_argument("--dry-run", action="store_true", help="construire/verifier sans envoyer")
    ap.add_argument("--watch", type=float, default=0.0,
                    help="secondes de surveillance de la reponse apres injection")
    ap.add_argument("--timeout", type=float, default=5.0,
                    help="secondes d'ecoute pour apprendre la connexion")
    args = ap.parse_args(argv)

    frame = build_kcj_frame(args.uid)
    check = check_frame(frame)
    print(f"frame kcj construite : {len(frame)} octets | {check} | "
          f"hex {frame.hex()}")
    if not check:
        print("ERREUR : la trame ne se decode pas — abandon")
        return 1

    if args.dry_run:
        print("dry-run : rien n'est envoye")
        return 0

    if send is None:
        print("scapy indisponible — injection impossible")
        return 2

    print(f"apprentissage de la connexion (port {PORT_GAME}, {args.timeout}s)...")
    state = learn_connection(args.timeout)
    if not state.ready():
        print("connexion non detectee — le jeu est-il connecte ?")
        return 3
    iface = _iface_for(state.client_ip)
    if iface is None:
        print(f"interface pour {state.client_ip} introuvable")
        return 3
    print(f"connexion : {state.client_ip}:{state.client_port} -> "
          f"{state.server_ip}:{state.server_port} sur {iface}")

    inject(frame, state, iface)

    if args.watch > 0:
        print(f"surveillance {args.watch}s des reponses serveur...")
        start = time.time()
        hits: list[str] = []
        def on_pkt(p):
            if TCP in pkt and Raw in pkt and pkt[TCP].sport == PORT_GAME:
                try:
                    url, _ = extract_envelope(bytes(pkt[Raw].load))
                except Exception:
                    url = None
                if url:
                    hits.append(url.rsplit("/", 1)[-1])
        sniff(filter=f"tcp port {PORT_GAME}", store=False,
              timeout=args.watch, prn=on_pkt)
        print("reponses observees :", hits or "aucune (la rune a peut-etre "
              "ete ignoree : seq desynchronise ou rune deja utilisee)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
