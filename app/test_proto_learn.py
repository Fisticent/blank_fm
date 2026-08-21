#!/usr/bin/env python3
"""Tests du learner proto ancre UID (captures locales, sans sniffer)."""
from __future__ import annotations

import json
import os
import sys
import tempfile

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
if APP not in sys.path:
    sys.path.insert(0, APP)

from fm_live import extract_envelope  # noqa: E402
import proto_learn as pl  # noqa: E402

CAP_A = os.path.join(ROOT, "captures", "fm_2026-08-20.jsonl")
CAP_B = os.path.join(ROOT, "captures", "fm_2026-08-20_bague.jsonl")


def _payload(row: dict) -> bytes:
    hx = row.get("payload_hex") or ""
    if hx:
        return bytes.fromhex(hx)
    frame = row.get("frame_hex") or ""
    if not frame:
        return b""
    _url, payload = extract_envelope(bytes.fromhex(frame))
    return payload or b""


def _replay(path: str, rename: dict[str, str] | None = None) -> None:
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            name = row.get("type") or "?"
            if rename and name in rename:
                name = rename[name]
            payload = _payload(row)
            if not payload:
                continue
            pl.classify_payload(name, payload, row.get("dir") or "s2c")


def _fresh(*, awake: bool = True) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    os.remove(tmp.name)
    pl.PROTO = pl.ProtocolMap(user_path=tmp.name, load=False)
    pl.PROTO.awake = awake
    pl.PROTO.force_learn = awake
    return tmp.name


def test_replay_empty_map_converges():
    _fresh(awake=True)
    _replay(CAP_A)
    n = pl.PROTO.names
    assert n["rune_echo"] == "kfb", n
    assert n["item_state"] == "kdr", n
    assert n["inventory"] == "iuj", n
    assert n["stack_qty"] == "ivj", n
    assert n["object_use"] == "kcj", n
    assert pl.PROTO.promoted.get("rune_echo") == "kfb"


def test_bague_same_map_no_kti():
    _fresh(awake=True)
    _replay(CAP_A)
    _replay(CAP_B)
    n = pl.PROTO.names
    assert n["rune_echo"] == "kfb"
    assert n["item_state"] == "kdr"
    assert n["inventory"] == "iuj"
    for role, name in n.items():
        assert name != "kti", (role, name)
        assert name != "ivx", (role, name)


def test_noise_zero_bind():
    _fresh(awake=True)
    _replay(CAP_A)
    bound = set(pl.PROTO.names.values())
    assert "kti" not in bound
    assert "ivx" not in bound
    assert "kqo" not in bound
    assert "jsn" not in bound


def test_rename_kfb():
    _fresh(awake=True)
    _replay(CAP_A, rename={"kfb": "abc"})
    assert pl.PROTO.names["rune_echo"] == "abc", pl.PROTO.names
    assert pl.PROTO.promoted.get("rune_echo") == "abc"
    assert pl.PROTO.names["item_state"] == "kdr"
    assert sum(pl.PROTO.scores["rune_echo"].values()) >= 3


def test_v1_corrupt_ignored():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "rune_echo": "ivx",
            "item_state": "kdr",
            "inventory": "kti",
            "object_use": "kcj",
            "stack_qty": "ivj",
        }, f)
    m = pl.ProtocolMap(user_path=path, load=True)
    assert m.names["rune_echo"] == "kfb"
    assert m.names["item_state"] == "kdr"
    assert m.names["inventory"] == "iuj"
    os.remove(path)


def main() -> int:
    tests = [
        test_v1_corrupt_ignored,
        test_replay_empty_map_converges,
        test_bague_same_map_no_kti,
        test_noise_zero_bind,
        test_rename_kfb,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("OK", fn.__name__)
        except Exception as e:
            failed += 1
            print("FAIL", fn.__name__, ":", e)
    if failed:
        print(f"{failed} test(s) en echec")
        return 1
    print("tous les tests proto_learn OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
