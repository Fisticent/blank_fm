#!/usr/bin/env python3
"""
fm_cost.py — Prix moyens des runes et cout d'une session FM.

Deux sources, toutes deux par sniffing passif (aucun ReadProcessMemory) :

1. TABLE DES PRIX  : le message `ivi` (s2c, ~5 s apres le login) contient
   la liste complete {gid -> prix moyen} des items ayant un prix HDV
   (equivalent Dofus 3 de `ObjectAveragePricesMessage`, id 6335 en Dofus 2).
   -> `python fm_cost.py prices <capture_login.jsonl>  # ecrit prices.json`

2. COUT DE SESSION : croise les runes posees (fm_decoder.decode_session) avec
   la table de prix.
   -> `python fm_cost.py cost <capture_fm.jsonl> [--prices prices.json]`

Le prix affiche dans l'UI FM = prix moyen du message `ivi` (le client le garde
en memoire a partir du login ; l'ouverture de l'UI FM ne declenche aucun
nouveau message de prix — confirme par capture).

Usage :
    python fm_cost.py prices captures/login.jsonl
    python fm_cost.py cost   _scratch/capture_fm_ui/frames.jsonl
    python fm_cost.py cost   _scratch/capture_fm_ui/frames.jsonl --prices prices.json
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from fm_decoder import RUNES, decode_session, extract_envelope, load_rows
from sniffer_hdv import parse_message
from paths import data_file


def parse_ivi(payload: bytes) -> dict[int, int]:
    """ivi : f2 repete xN : { f1 = gid, f2 = prix moyen }."""
    prices: dict[int, int] = {}
    for fn, wt, val in parse_message(payload):
        if wt == 2 and isinstance(val, bytes):
            try:
                inner = {f: v for f, w, v in parse_message(val) if w == 0}
                gid, price = inner.get(1), inner.get(2)
                if gid is not None and price is not None:
                    prices[gid] = price
            except Exception:
                continue
    return prices


def extract_prices(rows: list[dict]) -> dict[int, int]:
    """Parcourt les trames, concatene tous les `ivi` (au login il n'y en a qu'un)."""
    prices: dict[int, int] = {}
    for r in rows:
        if r.get("type") != "ivi":
            continue
        payload = extract_envelope(bytes.fromhex(r["frame_hex"]))[1]
        if payload:
            prices.update(parse_ivi(payload))
    return prices


def fmt_kamas(v: int) -> str:
    return f"{v:,}".replace(",", " ")


def cmd_prices(args) -> int:
    rows = load_rows(args.jsonl)
    prices = extract_prices(rows)
    if not prices:
        print(f"aucun message ivi dans {args.jsonl} "
              f"(il faut capturer depuis le login du jeu)")
        return 1
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(prices, f, ensure_ascii=False, indent=0)
    n_runes = sum(1 for g in prices if g in RUNES)
    print(f"{len(prices)} items a prix moyen (dont {n_runes} runes connues) "
          f"-> {args.out}")
    # apercu des runes
    print("\nrunes avec prix moyen :")
    for gid, price in sorted(prices.items()):
        if gid in RUNES:
            print(f"  {RUNES[gid]:<20} gid {gid:<6} {fmt_kamas(price)} kamas")
    return 0


def cmd_cost(args) -> int:
    prices = extract_prices(load_rows(args.login)) if args.login else {}
    if not prices and args.prices:
        with open(args.prices, encoding="utf-8") as f:
            prices = {int(k): v for k, v in json.load(f).items()}
    if not prices:
        print("aucune table de prix : passez --login <capture login> ou "
              "--prices <prices.json> (voir `fm_cost.py prices --help`)")
        return 1

    rows = load_rows(args.jsonl)
    events = decode_session(rows)
    if not events:
        print("aucune pose de rune trouvee")
        return 1

    # chaque kfb = 1 rune consommee (la quantite restante ivj n'est pas la
    # consommation : c'est l'etat de la pile apres la pose)
    total = 0
    lines: list[tuple[str, int, int]] = []
    for ev in events:
        ru = ev.rune
        price = prices.get(ru.gid, 0)
        total += price
        lines.append((ru.name, price, price))

    print(f"Session FM — {len(lines)} pose(s) de rune\n")
    print(f"{'rune':<22} {'prix moy':>12} {'cout':>14}")
    print("-" * 50)
    for name, price, cost in lines:
        p = f"{fmt_kamas(price)}" if price else "n/a"
        c = f"{fmt_kamas(cost)}" if cost else "n/a"
        print(f"{name:<22} {p:>12} {c:>14}")
    print("-" * 50)
    print(f"{'TOTAL':<22} {'':>12} {fmt_kamas(total):>14} kamas")
    noprice = sum(1 for _, p, _ in lines if p == 0)
    if noprice:
        print(f"\n({noprice} rune(s) sans prix moyen — jamais vues a l'HDV "
              f"ou absentes de la table ivi)")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prices", help="extrait la table ivi {gid: prix} d'une capture login")
    p.add_argument("jsonl", help="capture contenant le message ivi (login)")
    p.add_argument("--out", default=data_file("prices.json"),
                    help="fichier de sortie (defaut: app/data/prices.json)")
    p.set_defaults(func=cmd_prices)

    p = sub.add_parser("cost", help="cout des runes d'une session FM")
    p.add_argument("jsonl", help="journal fm_live d'une session FM (frames.jsonl)")
    p.add_argument("--prices", default=None, help="prices.json (sortie de `prices`)")
    p.add_argument("--login", default=None, help="capture login pour extraire la table a la volee")
    p.set_defaults(func=cmd_cost)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
