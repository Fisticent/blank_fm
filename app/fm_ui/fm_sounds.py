"""Sons FM : exo / perte, listes de caracteristiques configurables."""
from __future__ import annotations

import math
import os
import random
import struct
import sys
import threading
import wave

from fm_decoder import signed_value

PA_BONUS, PA_MALUS = 111, 168
PM_BONUS, PM_MALUS = 128, 169
MALUS_PAIR = {PA_BONUS: PA_MALUS, PM_BONUS: PM_MALUS}

DEFAULT_RULES = [
    {"eid": 111, "kind": "exo"},
    {"eid": 128, "kind": "exo"},
    {"eid": 117, "kind": "exo"},
    {"eid": 182, "kind": "exo"},
    {"eid": 111, "kind": "perte"},
    {"eid": 128, "kind": "perte"},
]

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
if not os.path.isdir(_DIR) and getattr(sys, "frozen", False):
    _DIR = os.path.join(getattr(sys, "_MEIPASS", ""), "fm_ui", "sounds")
_FAIL = os.path.join(_DIR, "fail.wav")
_SUCCESS = os.path.join(_DIR, "success.wav")
_CRY = os.path.join(_DIR, "cry.wav")
_RATE = 22050
_ready = False


def _sv(effects: dict | None, eid: int) -> int:
    if not effects or eid not in effects:
        return 0
    return signed_value(eid, effects[eid])


def _net(effects: dict | None, bonus: int, malus: int) -> int:
    return _sv(effects, bonus) + _sv(effects, malus)


def stat_lost(before: dict, after: dict, eid: int) -> bool:
    malus = MALUS_PAIR.get(eid)
    if malus is not None:
        return _net(after, eid, malus) < _net(before, eid, malus)
    return _sv(after, eid) < _sv(before, eid)


def exo_over(eid: int, effects: dict | None, template: dict | None) -> int:
    sv = _sv(effects, eid)
    if sv <= 0:
        return 0
    if not template or eid not in template:
        return sv
    _lo, hi = template[eid]
    if hi <= 0:
        return sv
    return max(0, sv - hi)


def exo_increased(before: dict, after: dict, template: dict | None, eid: int) -> bool:
    return exo_over(eid, after, template) > exo_over(eid, before, template)


def is_exo_attempt(eid: int, effects: dict | None, template: dict | None) -> bool:
    """True si poser cette stat maintenant serait de l'exo (max deja atteint, ou hors jet)."""
    sv = _sv(effects, eid)
    if not template or eid not in template:
        return True
    _lo, hi = template[eid]
    if hi <= 0:
        return True
    return sv >= hi


def eval_cues(before: dict, after: dict, template: dict | None,
              settings: dict, rune_eid: int = 0) -> tuple[bool, bool, bool]:
    exo_on = bool(settings.get("sound_exo", True))
    lost_on = bool(settings.get("sound_perte", True))
    cry_on = bool(settings.get("sound_exo_fail", True))
    lost = exo = exo_fail = False
    for rule in settings.get("rules") or []:
        try:
            eid = int(rule.get("eid", 0))
        except (TypeError, ValueError):
            continue
        if not eid:
            continue
        kind = rule.get("kind")
        if kind == "perte" and lost_on and not lost:
            if stat_lost(before, after, eid):
                lost = True
        elif kind == "exo" and exo_on and not exo:
            if exo_increased(before, after, template, eid):
                exo = True
        if lost and exo:
            break
    if cry_on and rune_eid and not exo:
        if is_exo_attempt(rune_eid, before, template):
            if not exo_increased(before, after, template, rune_eid):
                exo_fail = True
    return lost, exo, exo_fail


def _tone(freq: float, dur: float, volume: float = 0.38, decay: float = 6.0):
    n = int(_RATE * dur)
    out = []
    for i in range(n):
        t = i / _RATE
        env = math.exp(-decay * t) * min(1.0, i / (_RATE * 0.008))
        fund = math.sin(2 * math.pi * freq * t)
        harm = 0.28 * math.sin(2 * math.pi * freq * 2 * t)
        out.append(env * volume * (fund + harm))
    return out


def _silence(dur: float):
    return [0.0] * int(_RATE * dur)


def _write_wav(path: str, samples: list[float]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_RATE)
        frames = b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
            for s in samples)
        w.writeframes(frames)


def _cry_samples() -> list[float]:
    """Wails caricaturaux (pas un vrai enregistrement)."""
    rng = random.Random(7)
    out: list[float] = []
    phrases = (
        (0.42, 540.0, 320.0, 7.2),
        (0.55, 680.0, 290.0, 6.4),
        (0.36, 510.0, 260.0, 8.0),
    )
    for i, (dur, f0, f1, vib) in enumerate(phrases):
        n = int(_RATE * dur)
        phase = 0.0
        for k in range(n):
            p = k / max(1, n - 1)
            t = k / _RATE
            glide = f0 + (f1 - f0) * (p ** 0.55)
            freq = glide * (1.0 + 0.08 * math.sin(2 * math.pi * vib * t))
            phase += 2 * math.pi * freq / _RATE
            env = min(1.0, k / (_RATE * 0.035))
            env *= (1.0 - 0.35 * p) * (0.55 + 0.45 * math.sin(math.pi * p))
            env *= math.exp(-0.6 * p)
            s = math.sin(phase)
            s += 0.45 * math.sin(phase * 2.02)
            s += 0.12 * math.sin(phase * 3.1)
            noise = (rng.random() * 2 - 1) * 0.12 * (0.4 + 0.6 * p)
            out.append(max(-1.0, min(1.0, env * 0.48 * (s + noise))))
        if i < len(phrases) - 1:
            out += _silence(0.07 if i == 0 else 0.09)
    return out


def _ensure_wavs() -> None:
    global _ready
    if (_ready and os.path.isfile(_FAIL) and os.path.isfile(_SUCCESS)
            and os.path.isfile(_CRY)):
        return
    if not os.path.isfile(_FAIL):
        samples = []
        for freq in (392.0, 330.0, 262.0):
            samples += _tone(freq, 0.11, volume=0.42, decay=14.0)
            samples += _silence(0.07)
        _write_wav(_FAIL, samples)
    if not os.path.isfile(_SUCCESS):
        samples = []
        for freq, dur, gap in (
            (523.25, 0.11, 0.02),
            (659.25, 0.11, 0.02),
            (783.99, 0.11, 0.02),
            (1046.50, 0.32, 0.0),
        ):
            samples += _tone(freq, dur, volume=0.36, decay=5.5)
            samples += _silence(gap)
        _write_wav(_SUCCESS, samples)
    if not os.path.isfile(_CRY):
        _write_wav(_CRY, _cry_samples())
    _ready = True


def play_cues(lost: bool, exo: bool, exo_fail: bool = False) -> None:
    if not lost and not exo and not exo_fail:
        return
    if sys.platform != "win32":
        return

    def _run():
        try:
            _ensure_wavs()
            import winsound
            flags = winsound.SND_FILENAME
            if exo_fail:
                winsound.PlaySound(_CRY, flags)
            elif lost:
                winsound.PlaySound(_FAIL, flags)
            if exo:
                winsound.PlaySound(_SUCCESS, flags)
        except Exception as e:
            print("[DOFUS-FM] son:", e)

    threading.Thread(target=_run, daemon=True).start()
