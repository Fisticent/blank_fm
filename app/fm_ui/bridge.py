"""
fm_ui.bridge — pont backend → QML (composition autour de fm_panel.FmPanel).

FmPanelBridge délègue parse, SC/SN/EC, puits, reliquat, coût, jet % à FmPanel.
Le rendu terminal est remplacé par le signal Qt `updated` (queued, thread-safe).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
from collections import Counter
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, Property, QTimer, QUrl, QCoreApplication
from PySide6.QtGui import QGuiApplication, QDesktopServices

from fm_panel import FmPanel, PORT_GAME
from fm_decoder import RUNES, effect_name, item_name, signed_value
from fm_ui.constants import STAT_COLORS, STAT_COLOR_FALLBACK, APP_VERSION
from fm_ui.fm_sounds import (
    DEFAULT_RULES, eval_cues, exo_increased, is_exo_attempt, play_cues,
)
from paths import data_file, SCRATCH_DIR, CAPTURES_DIR, APP_DIR, PROJECT_DIR, cache_dir
from npcap_setup import npcap_present

SETTINGS_PATH = os.path.join(PROJECT_DIR, "fm_settings.json")
HISTORY_PATH = os.path.join(PROJECT_DIR, "fm_history.json")
MAX_RECENT = 10
MAX_HISTORY_POSES = 80
IDLE_PAUSE_SEC = 10.0

EXO_TRACK = (
    (111, "PA"),
    (128, "PM"),
    (117, "PO"),
    (182, "Invo"),
    (2812, "Do Per So"),
    (2804, "Do Per Di"),
    (2808, "Do Per Ar"),
)
EXO_EIDS = {eid for eid, _ in EXO_TRACK}


def _fmt_kamas(v: int) -> str:
    return f"{v:,}".replace(",", " ")


def _empty_exo_counts() -> dict[int, dict[str, int]]:
    return {eid: {"attempts": 0, "landed": 0, "cost": 0, "last_cost": 0}
            for eid, _ in EXO_TRACK}


def _parse_exo(raw) -> dict[int, dict[str, int]]:
    out = _empty_exo_counts()
    if not isinstance(raw, dict):
        return out
    for eid, _ in EXO_TRACK:
        rec = raw.get(str(eid), raw.get(eid))
        if isinstance(rec, dict):
            try:
                out[eid]["attempts"] = int(rec.get("attempts") or 0)
                out[eid]["landed"] = int(rec.get("landed") or 0)
                out[eid]["cost"] = int(rec.get("cost") or 0)
                out[eid]["last_cost"] = int(rec.get("last_cost") or 0)
            except (TypeError, ValueError):
                pass
        else:
            try:
                out[eid]["attempts"] = int(rec or 0)
            except (TypeError, ValueError):
                pass
    return out


def _exo_summary(exo: dict) -> str:
    parts = []
    for eid, label in EXO_TRACK:
        rec = exo.get(eid) or exo.get(str(eid)) or {}
        if isinstance(rec, dict):
            n = int(rec.get("attempts") or 0)
            landed = int(rec.get("landed") or 0)
        else:
            try:
                n = int(rec or 0)
            except (TypeError, ValueError):
                n = 0
            landed = 0
        if n <= 0:
            continue
        cost = int(rec.get("cost") or 0) if isinstance(rec, dict) else 0
        bit = f"{label} {n}"
        if landed:
            bit += f" ({landed})"
        if cost:
            bit += f" {_fmt_kamas(cost)}"
        parts.append(bit)
    return " · ".join(parts)


def _fmt_duration(seconds: float) -> str:
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class FmPanelBridge(QObject):
    """Pont Qt autour d'un FmPanel interne — expose l'état FM à QML."""

    updated = Signal()
    requestShow = Signal()
    settingsChanged = Signal()
    runesChanged = Signal()
    runeIconReady = Signal(int, str)
    npcapChanged = Signal()
    npcapReady = Signal()
    updateChanged = Signal()
    requestQuit = Signal()

    def __init__(self, qapp=None):
        super().__init__()
        self._panel: Optional[FmPanel] = None
        self._outdir: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._sniffer = None
        self._stop = threading.Event()
        self._prices_loaded = False
        self.prices: dict[int, int] = {}
        self._items_db: Optional[dict] = None
        self._t0 = datetime.now()
        self._t_item = datetime.now()
        self._elapsed_session = 0.0
        self._elapsed_item = 0.0
        self._clock_anchor = datetime.now()
        self._clock_paused = False
        self._last_rune_at = None
        self._history_dirty = False
        self._exo = _empty_exo_counts()
        self._exo_pending_cost = 0
        self._exo_last_cost = 0
        self._sessions: dict[int, dict] = {}
        self._seen_eids: set[int] = set()
        self._history_override: list = []
        self._recent: list[dict] = []
        self._settings = self._load_settings()
        self._load_history()
        self._stat_choices_cache: Optional[list] = None
        self._rune_filter = ""
        self._runes_rows: Optional[list] = None
        self._rune_dl: set[int] = set()
        self._rune_dl_lock = threading.Semaphore(4)
        self._rune_icon_debounce = QTimer(self)
        self._rune_icon_debounce.setSingleShot(True)
        self._rune_icon_debounce.setInterval(200)
        self._rune_icon_debounce.timeout.connect(self.runesChanged)
        self.runeIconReady.connect(self._apply_rune_icon)
        self._history_save = QTimer(self)
        self._history_save.setSingleShot(True)
        self._history_save.setInterval(800)
        self._history_save.timeout.connect(self._save_history)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()
        self._shutting_down = False
        self._quit_requested = False
        self._npcap_ok = npcap_present()
        self._npcap_busy = False
        self._npcap_msg = (
            "" if self._npcap_ok
            else "Npcap est requis pour capturer le jeu (installeur officiel).")
        self.npcapReady.connect(self.start_live)
        self.requestQuit.connect(self.quit_app)
        self._update_available = False
        self._update_busy = False
        self._update_msg = ""
        self._update_tag = ""
        self._update_zip = ""
        self._update_html = ""
        QTimer.singleShot(1500, self.check_for_update)

    def _ensure_panel(self, outdir: str) -> FmPanel:
        if self._panel is not None and self._outdir == outdir:
            return self._panel
        if self._panel is not None:
            self._stash_current_session()
            self._archive_current_item()
            try:
                self._panel.close()
            except Exception:
                pass
        os.makedirs(outdir, exist_ok=True)
        self._panel = FmPanel(outdir)
        orig_switch = self._panel._switch_item
        orig_state = self._panel._on_state

        def _sw(st):
            self._stash_current_session()
            self._archive_current_item()
            orig_switch(st)
            self._restore_session(getattr(st, "uid", 0) or 0,
                                  getattr(st, "gid", 0) or 0)

        def _st(st, ts):
            before = dict(self._panel._effects) if self._panel._effects else None
            rune = self._panel._rune
            tpl = getattr(self._panel, "_template", None)
            orig_state(st, ts)
            after = self._panel._effects
            exo_changed = False
            eid = 0
            pose_cost = 0
            events = getattr(self._panel, "events", None) or []
            if events and len(events[-1]) >= 10 and events[-1][9]:
                try:
                    pose_cost = int(events[-1][9] or 0)
                except (TypeError, ValueError):
                    pose_cost = 0
            if pose_cost:
                self._exo_pending_cost += pose_cost
            if rune:
                eid = int(getattr(rune, "effect_id", 0) or 0)
                if eid in EXO_EIDS:
                    try:
                        rec = self._exo.setdefault(
                            eid, {"attempts": 0, "landed": 0, "cost": 0,
                                  "last_cost": 0})
                        if (before is not None and after is not None
                                and is_exo_attempt(eid, before, tpl)):
                            rec["attempts"] += 1
                            rec["cost"] = (int(rec.get("cost") or 0)
                                           + int(self._exo_pending_cost))
                            rec["last_cost"] = int(self._exo_pending_cost)
                            self._exo_last_cost = int(self._exo_pending_cost)
                            self._exo_pending_cost = 0
                            exo_changed = True
                            if exo_increased(before, after, tpl, eid):
                                rec["landed"] += 1
                    except Exception as e:
                        print("[DOFUS-FM] exo attempt:", e, file=sys.stderr)
            if rune:
                self._on_rune_posed()
            if rune and before is not None and after is not None:
                try:
                    lost, exo, exo_fail = eval_cues(
                        before, after, tpl, self._settings, eid)
                    play_cues(lost, exo, exo_fail)
                except Exception as e:
                    print("[DOFUS-FM] son FM:", e, file=sys.stderr)
            if exo_changed:
                self.updated.emit()

        self._panel._switch_item = _sw
        self._panel._on_state = _st
        self._panel._render = self._on_panel_render
        self._prices_rev_seen = -1
        self._outdir = outdir
        return self._panel

    def _on_panel_render(self):
        p = self._panel
        if p is not None:
            p._load_prices()
            if p.prices:
                self.prices.update(p.prices)
                self._prices_loaded = True
            rev = getattr(p, "prices_rev", 0)
            if rev != self._prices_rev_seen:
                self._prices_rev_seen = rev
                self._runes_rows = None
                self.runesChanged.emit()
        else:
            self._load_prices()
        p = self._panel
        if p is not None and getattr(p, "_effects", None):
            self._seen_eids.update(p._effects.keys())
        self.updated.emit()
        self._history_dirty = True

    @property
    def _p(self) -> Optional[FmPanel]:
        return self._panel

    def _counter_from(self, raw) -> Counter:
        out = Counter()
        if not isinstance(raw, dict):
            return out
        for k, v in raw.items():
            try:
                out[int(k)] = int(v)
            except (TypeError, ValueError):
                continue
        return out

    def _capture_session(self) -> Optional[dict]:
        p = self._p
        if p is None or not getattr(p, "item_gid", 0):
            return None
        uid = int(getattr(p, "item_uid", 0) or 0)
        if not uid:
            return None
        oc = getattr(p, "outcomes", {}) or {}
        return {
            "uid": uid,
            "gid": int(p.item_gid),
            "poses": int(getattr(p, "poses", 0) or 0),
            "event_no": int(getattr(p, "event_no", 0) or 0),
            "sc": int(oc.get("sc", 0) or 0),
            "sn": int(oc.get("sn", 0) or 0),
            "ec": int(oc.get("ec", 0) or 0),
            "outcomes": Counter(oc),
            "rune_counts": Counter(getattr(p, "rune_counts", {}) or {}),
            "rune_by_stat": Counter(getattr(p, "rune_by_stat", {}) or {}),
            "cost_total": int(getattr(p, "cost_total", 0) or 0),
            "cost_by_stat": Counter(getattr(p, "cost_by_stat", {}) or {}),
            "puit_delta_total": float(getattr(p, "puit_delta_total", 0) or 0),
            "reliquat_cumul": float(getattr(p, "reliquat_cumul", 0) or 0),
            "events": list(getattr(p, "events", []) or []),
            "history_rows": self._panel_history_rows(p) or list(self._history_override),
            "exo": {str(eid): dict(self._exo.get(eid) or {})
                    for eid, _ in EXO_TRACK},
            "exo_pending_cost": int(self._exo_pending_cost),
            "exo_last_cost": int(self._exo_last_cost),
            "seen_eids": [int(x) for x in sorted(self._seen_eids)],
            "t_item": self._t_item,
            "elapsed_item": self._item_seconds(),
            "effects": dict(getattr(p, "_effects", None) or {}),
            "puit": getattr(p, "puit", None),
            "item_slot": int(getattr(p, "item_slot", 0) or 0),
        }

    def _stash_current_session(self) -> None:
        snap = self._capture_session()
        if not snap:
            return
        self._sessions[int(snap["uid"])] = snap

    def _session_from_snapshot(self, rec: dict) -> dict:
        seen = []
        for x in rec.get("seen_eids") or []:
            try:
                seen.append(int(x))
            except (TypeError, ValueError):
                pass
        return {
            "uid": int(rec.get("uid") or 0),
            "gid": int(rec.get("gid") or 0),
            "poses": int(rec.get("poses") or 0),
            "event_no": int(rec.get("event_no") or rec.get("poses") or 0),
            "sc": int(rec.get("sc") or 0),
            "sn": int(rec.get("sn") or 0),
            "ec": int(rec.get("ec") or 0),
            "rune_by_stat": self._counter_from(rec.get("rune_by_stat")),
            "cost_total": int(rec.get("cost_total") or 0),
            "cost_by_stat": self._counter_from(rec.get("cost_by_stat")),
            "puit_delta_total": float(rec.get("puit_delta_total") or 0),
            "reliquat_cumul": float(rec.get("reliquat_cumul") or 0),
            "history_rows": list(rec.get("history") or rec.get("history_rows") or []),
            "exo": rec.get("exo") or {},
            "exo_pending_cost": int(rec.get("exo_pending_cost") or 0),
            "exo_last_cost": int(rec.get("exo_last_cost") or 0),
            "seen_eids": seen,
            "events": rec.get("events"),
            "t_item": rec.get("t_item"),
            "elapsed_item": rec.get("elapsed_item"),
        }

    def _apply_session(self, s: dict) -> None:
        p = self._p
        if p is None or not s:
            return
        p.poses = int(s.get("poses") or 0)
        p.event_no = int(s.get("event_no") or p.poses)
        oc = s.get("outcomes")
        if isinstance(oc, Counter):
            p.outcomes = Counter(oc)
        else:
            p.outcomes = Counter(
                sc=int(s.get("sc") or 0),
                sn=int(s.get("sn") or 0),
                ec=int(s.get("ec") or 0),
            )
        if isinstance(s.get("rune_counts"), Counter):
            p.rune_counts = Counter(s["rune_counts"])
        if isinstance(s.get("rune_by_stat"), Counter):
            p.rune_by_stat = Counter(s["rune_by_stat"])
        else:
            p.rune_by_stat = self._counter_from(s.get("rune_by_stat"))
        p.cost_total = int(s.get("cost_total") or 0)
        if isinstance(s.get("cost_by_stat"), Counter):
            p.cost_by_stat = Counter(s["cost_by_stat"])
        else:
            p.cost_by_stat = self._counter_from(s.get("cost_by_stat"))
        p.puit_delta_total = float(s.get("puit_delta_total") or 0)
        p.reliquat_cumul = float(s.get("reliquat_cumul") or 0)
        events = s.get("events")
        if events:
            p.events.clear()
            p.events.extend(events)
            self._history_override = []
        else:
            p.events.clear()
            self._history_override = list(s.get("history_rows") or [])
        self._exo = _parse_exo(s.get("exo"))
        try:
            self._exo_pending_cost = int(s.get("exo_pending_cost") or 0)
        except (TypeError, ValueError):
            self._exo_pending_cost = 0
        try:
            self._exo_last_cost = int(s.get("exo_last_cost") or 0)
        except (TypeError, ValueError):
            self._exo_last_cost = 0
        self._seen_eids = {int(x) for x in (s.get("seen_eids") or [])}
        elapsed_item = s.get("elapsed_item")
        try:
            elapsed_item_f = float(elapsed_item) if elapsed_item is not None else -1.0
        except (TypeError, ValueError):
            elapsed_item_f = -1.0
        if elapsed_item_f >= 0:
            self._reanchor_item(elapsed_item_f)
        else:
            t_item = s.get("t_item")
            if isinstance(t_item, datetime):
                self._reanchor_item(
                    max(0.0, (datetime.now() - t_item).total_seconds()))
            else:
                self._reanchor_item(0.0)
        eff = s.get("effects")
        if isinstance(eff, dict) and eff:
            p._effects = {int(k): int(v) for k, v in eff.items()}
        elif events:
            last = events[-1]
            if len(last) >= 5 and isinstance(last[4], dict):
                p._effects = dict(last[4])
        puit = s.get("puit")
        if puit is not None:
            try:
                p.puit = float(puit)
                p.puit_prev = p.puit
            except (TypeError, ValueError):
                pass
        slot = s.get("item_slot")
        if slot:
            try:
                p.item_slot = int(slot)
            except (TypeError, ValueError):
                pass

    def _restore_session(self, uid: int, gid: int) -> None:
        self._history_override = []
        self._seen_eids = set()
        saved = self._sessions.get(int(uid)) if uid else None
        if saved and gid and int(saved.get("gid") or 0) not in (0, int(gid)):
            saved = None
        if not saved:
            self._exo = _empty_exo_counts()
            self._exo_pending_cost = 0
            self._exo_last_cost = 0
            self._reanchor_item(0.0)
            return
        self._apply_session(saved)

    def _clear_panel_session(self) -> None:
        p = self._p
        if p is None:
            return
        p.puit_delta_total = 0.0
        p.reliquat_cumul = 0.0
        p.rune_counts = Counter()
        p.rune_by_stat = Counter()
        p.outcomes = Counter()
        p.events.clear()
        p.poses = 0
        p.cost_total = 0
        p.cost_by_stat = Counter()
        p.event_no = 0
        if getattr(p, "puit", None) is not None:
            p.puit_prev = p.puit
        self._exo = _empty_exo_counts()
        self._exo_pending_cost = 0
        self._exo_last_cost = 0
        self._history_override = []
        self._seen_eids = set((getattr(p, "_effects", None) or {}).keys())
        self._reanchor_item(0.0)

    @Slot()
    def reset_item_session(self):
        p = self._p
        uid = int(getattr(p, "item_uid", 0) or 0) if p else 0
        if uid:
            self._sessions.pop(uid, None)
            self._recent = [r for r in self._recent if r.get("uid") != uid]
        self._clear_panel_session()
        self._schedule_history_save()
        self.updated.emit()

    @Slot()
    def resetItemSession(self):
        self.reset_item_session()

    def _stop_sniffer(self):
        sn = self._sniffer
        self._sniffer = None
        if sn is None:
            return
        try:
            sn.stop()
        except Exception as e:
            print("[DOFUS-FM] stop sniffer:", e, file=sys.stderr)

    def _begin_session(self) -> threading.Event:
        """Reveille l'ancienne capture sans bloquer l'UI, puis nouveau flag."""
        prev = self._stop
        prev.set()
        self._thread = None
        self._sniffer = None
        self._stop = threading.Event()
        return self._stop

    def _stop_thread(self):
        # Ne pas appeler AsyncSniffer.stop() ni join() depuis le thread Qt :
        # deadlock avec les callbacks paquets qui emettent `updated`.
        self._stop.set()
        self._thread = None
        self._sniffer = None

    @Slot()
    def start_live(self):
        if not npcap_present():
            self._npcap_ok = False
            self._npcap_msg = "Npcap est requis pour capturer le jeu."
            self.npcapChanged.emit()
            self.updated.emit()
            return
        self._npcap_ok = True
        self.npcapChanged.emit()
        self._begin_session()
        self._ensure_panel(os.path.join(SCRATCH_DIR, "ui_live"))
        self._reset_session_clock()
        stop = self._stop
        self._thread = threading.Thread(
            target=self._run_live, args=(stop,), daemon=True)
        self._thread.start()
        self.updated.emit()

    @Slot()
    def start_capture(self):
        self.start_live()

    @Slot()
    def stop_capture(self):
        self._stop_thread()
        self.updated.emit()

    @Slot()
    def startCapture(self):
        self.start_live()

    @Slot()
    def stopCapture(self):
        self._stop_thread()
        self.updated.emit()

    @Property(bool, notify=npcapChanged)
    def npcapInstalled(self) -> bool:
        return bool(self._npcap_ok)

    @Property(bool, notify=npcapChanged)
    def npcapBusy(self) -> bool:
        return bool(self._npcap_busy)

    @Property(str, notify=npcapChanged)
    def npcapMessage(self) -> str:
        return self._npcap_msg or ""

    @Slot()
    def refreshNpcap(self):
        self.refresh_npcap()

    @Slot()
    def refresh_npcap(self):
        self._npcap_ok = npcap_present()
        if self._npcap_ok:
            self._npcap_msg = "Npcap detecte."
        else:
            self._npcap_msg = "Npcap est requis pour capturer le jeu (installeur officiel)."
        self.npcapChanged.emit()

    @Slot()
    def installNpcap(self):
        self.install_npcap()

    @Slot()
    def install_npcap(self):
        if self._npcap_busy:
            return
        if npcap_present():
            self._npcap_ok = True
            self._npcap_msg = "Npcap est deja installe."
            self.npcapChanged.emit()
            return
        self._npcap_busy = True
        self._npcap_msg = "Telechargement de Npcap depuis npcap.com…"
        self.npcapChanged.emit()

        def _job():
            try:
                from npcap_setup import download_installer, launch_installer
                path = download_installer()
                self._npcap_msg = "Installeur Npcap lance. Accepte le UAC puis Suivant."
                self.npcapChanged.emit()
                if not launch_installer(path):
                    raise RuntimeError("impossible de lancer l'installeur")
                import time
                for _ in range(90):
                    time.sleep(2)
                    if npcap_present():
                        self._npcap_ok = True
                        self._npcap_busy = False
                        self._npcap_msg = "Npcap installe. Demarrage de la capture…"
                        self.npcapChanged.emit()
                        self.npcapReady.emit()
                        return
                self._npcap_ok = npcap_present()
                self._npcap_msg = (
                    "Si l'install est finie, relance Dofus FM "
                    "(un reboot Windows est parfois necessaire).")
            except Exception as e:
                self._npcap_ok = npcap_present()
                self._npcap_msg = f"Echec Npcap : {e}"
            self._npcap_busy = False
            self.npcapChanged.emit()

        threading.Thread(target=_job, daemon=True).start()

    @Property(str, notify=updateChanged)
    def appVersion(self) -> str:
        return APP_VERSION

    @Property(bool, notify=updateChanged)
    def updateAvailable(self) -> bool:
        return bool(self._update_available)

    @Property(bool, notify=updateChanged)
    def updateBusy(self) -> bool:
        return bool(self._update_busy)

    @Property(str, notify=updateChanged)
    def updateMessage(self) -> str:
        return self._update_msg or ""

    @Slot()
    def checkForUpdate(self):
        self.check_for_update()

    @Slot()
    def check_for_update(self):
        def _job():
            try:
                from fm_updater import fetch_latest, is_newer
                info = fetch_latest()
                tag = info.get("tag") or ""
                if tag and is_newer(tag, APP_VERSION):
                    self._update_available = True
                    self._update_tag = tag
                    self._update_zip = info.get("zip_url") or ""
                    self._update_html = info.get("html_url") or ""
                    self._update_msg = f"Mise a jour {tag} disponible (tu as {APP_VERSION})."
                else:
                    self._update_available = False
                    self._update_msg = ""
            except Exception as e:
                self._update_available = False
                self._update_msg = ""
                print("[DOFUS-FM] maj:", e, file=sys.stderr)
            self.updateChanged.emit()

        threading.Thread(target=_job, daemon=True).start()

    @Slot()
    def applyUpdate(self):
        self.apply_update()

    @Slot()
    def apply_update(self):
        if self._update_busy:
            return
        html = self._update_html or "https://github.com/Fisticent/blank_fm/releases"
        if not getattr(sys, "frozen", False) or not self._update_zip:
            QDesktopServices.openUrl(QUrl(html))
            return
        self._update_busy = True
        self._update_msg = "Telechargement de la mise a jour…"
        self.updateChanged.emit()

        def _job():
            try:
                from fm_updater import apply_from_url

                def prog(got: int, total: int) -> None:
                    if total > 0:
                        pct = min(99, int(got * 100 / total))
                        self._update_msg = f"Telechargement {pct} %"
                    else:
                        self._update_msg = "Telechargement…"
                    self.updateChanged.emit()

                apply_from_url(self._update_zip, prog)
                self._update_msg = "Redemarrage…"
                self.updateChanged.emit()
                self.requestQuit.emit()
            except Exception as e:
                self._update_busy = False
                self._update_msg = f"Echec de la maj : {e}"
                self.updateChanged.emit()

        threading.Thread(target=_job, daemon=True).start()

    @Slot()
    def pick_replay(self):
        default = os.path.join(CAPTURES_DIR, "fm_2026-08-20.jsonl")
        if os.path.exists(default):
            self.start_replay(default)

    @Slot(str)
    def start_replay(self, path: str):
        if path.startswith("file:"):
            path = QUrl(path).toLocalFile()
        if not path or not os.path.exists(path):
            print("[DOFUS-FM] replay introuvable:", path, file=sys.stderr)
            return
        self._begin_session()
        self._ensure_panel(os.path.join(SCRATCH_DIR, "ui_replay"))
        self._reset_session_clock()
        stop = self._stop
        self._thread = threading.Thread(
            target=self._run_replay, args=(path, stop), daemon=True)
        self._thread.start()
        self.updated.emit()

    @Slot(str)
    def startReplay(self, path: str):
        self.start_replay(path)

    def _run_live(self, stop: threading.Event):
        panel = self._panel
        if panel is None:
            return
        try:
            from scapy.all import Raw, TCP, IP, AsyncSniffer
        except Exception as e:
            print("[DOFUS-FM] scapy requis:", e, file=sys.stderr)
            self.updated.emit()
            return

        def on_packet(pkt):
            if stop.is_set():
                return
            if TCP not in pkt or Raw not in pkt:
                return
            dport, sport = pkt[TCP].dport, pkt[TCP].sport
            if dport != PORT_GAME and sport != PORT_GAME:
                return
            direction = "s2c" if sport == PORT_GAME else "c2s"
            src = pkt[IP].src if IP in pkt else "?"
            dst = pkt[IP].dst if IP in pkt else "?"
            try:
                panel.feed(direction, bytes(pkt[Raw].load),
                           (src, sport, dst, dport))
            except Exception as exc:
                print("[DOFUS-FM] paquet:", exc, file=sys.stderr)

        sniffer = None
        try:
            sniffer = AsyncSniffer(
                filter=f"tcp port {PORT_GAME}",
                prn=on_packet,
                store=False,
            )
            if stop.is_set():
                return
            self._sniffer = sniffer
            sniffer.start()
            stop.wait()
        except PermissionError as e:
            print("[DOFUS-FM] admin/npcap requis:", e, file=sys.stderr)
        except Exception as e:
            print("[DOFUS-FM] live error:", e, file=sys.stderr)
        finally:
            if self._sniffer is sniffer:
                self._sniffer = None
            if sniffer is not None:
                try:
                    sniffer.stop()
                except Exception as e:
                    print("[DOFUS-FM] stop sniffer:", e, file=sys.stderr)
            if self._thread is threading.current_thread():
                self._thread = None
            self.updated.emit()

    def _run_replay(self, path: str, stop: threading.Event):
        panel = self._panel
        if panel is None:
            return
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if stop.is_set():
                        break
                    line = line.strip()
                    if not line:
                        continue
                    r = json.loads(line)
                    frame = bytes.fromhex(r.get("frame_hex") or "")
                    if not frame:
                        continue
                    panel._frame(r.get("dir") or "s2c", frame)
        except Exception as e:
            print("[DOFUS-FM] replay error:", e, file=sys.stderr)
        finally:
            if self._thread is threading.current_thread():
                self._thread = None
            self.updated.emit()

    @Slot()
    def tick(self):
        self.updated.emit()

    def _on_tick(self):
        if self._idle_should_pause():
            self._freeze_clock()
        if self._history_dirty:
            self._history_dirty = False
            self._save_history()
        self.updated.emit()

    def _clock_delta(self) -> float:
        if self._clock_paused or self._clock_anchor is None:
            return 0.0
        return max(0.0, (datetime.now() - self._clock_anchor).total_seconds())

    def _session_seconds(self) -> float:
        return self._elapsed_session + self._clock_delta()

    def _item_seconds(self) -> float:
        return self._elapsed_item + self._clock_delta()

    def _freeze_clock(self) -> None:
        extra = self._clock_delta()
        self._elapsed_session += extra
        self._elapsed_item += extra
        self._clock_anchor = None
        self._clock_paused = True

    def _resume_clock(self) -> None:
        if not self._clock_paused and self._clock_anchor is not None:
            return
        self._clock_paused = False
        self._clock_anchor = datetime.now()

    def _reset_session_clock(self) -> None:
        now = datetime.now()
        self._elapsed_session = 0.0
        self._elapsed_item = 0.0
        self._clock_paused = False
        self._clock_anchor = now
        self._last_rune_at = None
        self._t0 = now
        self._t_item = now

    def _reanchor_item(self, elapsed: float) -> None:
        extra = self._clock_delta()
        self._elapsed_session += extra
        self._elapsed_item = max(0.0, float(elapsed or 0))
        if not self._clock_paused:
            self._clock_anchor = datetime.now()
        self._t_item = datetime.now()

    def _on_rune_posed(self) -> None:
        self._last_rune_at = datetime.now()
        self._resume_clock()

    def _idle_should_pause(self) -> bool:
        if self._clock_paused:
            return False
        now = datetime.now()
        last = self._last_rune_at
        if last is None:
            start = self._clock_anchor or self._t0
            return (now - start).total_seconds() >= IDLE_PAUSE_SEC
        return (now - last).total_seconds() >= IDLE_PAUSE_SEC

    @Property(str, notify=updated)
    def sessionDuration(self) -> str:
        return _fmt_duration(self._session_seconds())

    @Property(str, notify=updated)
    def itemDuration(self) -> str:
        return _fmt_duration(self._item_seconds())

    @Property(bool, notify=updated)
    def timerPaused(self) -> bool:
        return bool(self._clock_paused)

    @Property(str, notify=updated)
    def statusText(self) -> str:
        if self._thread is None or not self._thread.is_alive():
            if self.poses > 0:
                return "Capture arrêtée"
            return "En attente de capture"
        if not self.itemGid:
            return "Capture en cours, pose un item dans la forge…"
        return f"Capture en cours · {self.poses} pose(s)"

    @Property(str, notify=updated)
    def protoStatus(self) -> str:
        p = self._p
        return getattr(p, "proto_status", "") if p else ""

    @Property(str, notify=updated)
    def itemName(self) -> str:
        p = self._p
        if not p or not getattr(p, "item_gid", 0):
            return "En attente d'un item…"
        return item_name(p.item_gid)

    @Property(int, notify=updated)
    def itemGid(self) -> int:
        p = self._p
        return getattr(p, "item_gid", 0) if p else 0

    @Property(int, notify=updated)
    def itemUid(self) -> int:
        p = self._p
        return getattr(p, "item_uid", 0) if p else 0

    @Property(str, notify=updated)
    def itemIcon(self) -> str:
        gid = self.itemGid
        if not gid:
            return ""
        return self._icon_for(gid)

    _ICON_CACHE = {}

    def _icons_bundle_dir(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

    def _icons_write_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return cache_dir("icons")
        d = self._icons_bundle_dir()
        os.makedirs(d, exist_ok=True)
        return d

    def _icon_for(self, gid: int) -> str:
        if gid in self._ICON_CACHE:
            return self._ICON_CACHE[gid]
        for folder in (self._icons_write_dir(), self._icons_bundle_dir()):
            local = os.path.join(folder, f"{gid}.png")
            if os.path.exists(local):
                url = QUrl.fromLocalFile(local).toString()
                self._ICON_CACHE[gid] = url
                return url
        url = self._icon_url_from_db(gid)
        if url:
            self._ICON_CACHE[gid] = url
            self._download_icon(gid, url)
            return url
        self._ICON_CACHE[gid] = ""
        return ""

    def _download_icon(self, gid: int, url: str) -> None:
        local = os.path.join(self._icons_write_dir(), f"{gid}.png")
        os.makedirs(os.path.dirname(local), exist_ok=True)

        def _dl():
            try:
                import urllib.request
                req = urllib.request.Request(
                    url, headers={"User-Agent": "dofus-fm/1.0"})
                data = urllib.request.urlopen(req, timeout=20).read()
                if data[:4] == b"\x89PNG":
                    with open(local, "wb") as f:
                        f.write(data)
                    self._ICON_CACHE[gid] = QUrl.fromLocalFile(local).toString()
                    self.updated.emit()
            except Exception as e:
                print("[DOFUS-FM] icone", gid, ":", e, file=sys.stderr)
        threading.Thread(target=_dl, daemon=True).start()

    def _icon_url_from_db(self, gid: int) -> str:
        if self._items_db is None:
            try:
                with open(data_file("items.json"), encoding="utf-8") as f:
                    self._items_db = json.load(f)
            except (OSError, ValueError):
                self._items_db = {}
        return (self._items_db.get(str(gid)) or {}).get("icon") or ""

    def _rune_icon_dir(self) -> str:
        if getattr(sys, "frozen", False):
            bundled = os.path.join(self._icons_bundle_dir(), "runes")
            if os.path.isdir(bundled):
                return bundled
            return cache_dir("icons", "runes")
        return os.path.join(self._icons_bundle_dir(), "runes")

    def _rune_icon_for(self, gid: int, icon_id) -> str:
        local = os.path.join(self._rune_icon_dir(), f"{gid}.png")
        if os.path.isfile(local) and os.path.getsize(local) > 32:
            return QUrl.fromLocalFile(local).toString()
        if icon_id:
            try:
                self._ensure_rune_icon(gid, int(icon_id), local)
            except (TypeError, ValueError):
                pass
        return ""

    def _ensure_rune_icon(self, gid: int, icon_id: int, local: str) -> None:
        if gid in self._rune_dl:
            return
        self._rune_dl.add(gid)
        urls = [
            f"https://api.dofusdu.de/dofus3/v1/img/item/{icon_id}-64.png",
            f"https://api.dofusdb.fr/img/items/{icon_id}.png",
        ]

        def _dl():
            with self._rune_dl_lock:
                if os.path.isfile(local) and os.path.getsize(local) > 32:
                    self.runeIconReady.emit(
                        gid, QUrl.fromLocalFile(local).toString())
                    return
                os.makedirs(os.path.dirname(local), exist_ok=True)
                import urllib.request
                data = b""
                for url in urls:
                    try:
                        req = urllib.request.Request(
                            url, headers={"User-Agent": "dofus-fm/1.0"})
                        data = urllib.request.urlopen(req, timeout=20).read()
                        if data[:4] == b"\x89PNG":
                            break
                        data = b""
                    except Exception:
                        data = b""
                if data[:4] != b"\x89PNG":
                    return
                try:
                    with open(local, "wb") as f:
                        f.write(data)
                except OSError as e:
                    print("[DOFUS-FM] icone rune", gid, ":", e, file=sys.stderr)
                    return
                self.runeIconReady.emit(gid, QUrl.fromLocalFile(local).toString())

        threading.Thread(target=_dl, daemon=True).start()

    @Slot(int, str)
    def _apply_rune_icon(self, gid: int, url: str):
        if self._runes_rows:
            for row in self._runes_rows:
                if row.get("gid") == gid:
                    row["icon"] = url
                    break
        self._rune_icon_debounce.start()

    @Property(float, notify=updated)
    def puit(self) -> float:
        p = self._p
        v = getattr(p, "puit", None) if p else None
        return v if v is not None else 0.0

    @Property(float, notify=updated)
    def puitDeltaTotal(self) -> float:
        p = self._p
        return getattr(p, "puit_delta_total", 0.0) if p else 0.0

    @Property(float, notify=updated)
    def reliquatCumul(self) -> float:
        p = self._p
        return getattr(p, "reliquat_cumul", 0.0) if p else 0.0

    @Property(float, notify=updated)
    def jetPct(self) -> float:
        p = self._p
        if p is None:
            return -1.0
        try:
            v = p._jet_pct()
            return v if v is not None else -1.0
        except Exception:
            return -1.0

    @Property(int, notify=updated)
    def poses(self) -> int:
        p = self._p
        return getattr(p, "poses", 0) if p else 0

    @Property(bool, notify=updated)
    def captureRunning(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @Property(str, notify=updated)
    def costFormatted(self) -> str:
        p = self._p
        if p is None:
            return "—"
        self._load_prices()
        if not self.prices:
            return "— (pas de prices.json)"
        return _fmt_kamas(getattr(p, "cost_total", 0))

    def _issue(self, key: str) -> int:
        p = self._p
        return int(getattr(p, "outcomes", {}).get(key, 0)) if p else 0

    @Property(int, notify=updated)
    def scCount(self) -> int:
        return self._issue("sc")

    @Property(int, notify=updated)
    def snCount(self) -> int:
        return self._issue("sn")

    @Property(int, notify=updated)
    def ecCount(self) -> int:
        return self._issue("ec")

    @Property(int, notify=updated)
    def rienCount(self) -> int:
        return self._issue("rien")

    @Property("QVariantList", notify=updated)
    def exoAttemptsModel(self) -> list:
        rows = []
        for eid, label in EXO_TRACK:
            rec = self._exo.get(eid) or {
                "attempts": 0, "landed": 0, "cost": 0, "last_cost": 0}
            attempts = int(rec.get("attempts") or 0)
            cost = int(rec.get("cost") or 0)
            last_cost = int(rec.get("last_cost") or 0)
            cost_per = int(round(cost / attempts)) if attempts and cost else 0
            rows.append({
                "eid": eid,
                "label": label,
                "attempts": attempts,
                "landed": int(rec.get("landed") or 0),
                "cost": cost,
                "costText": _fmt_kamas(cost) if cost else "",
                "lastCost": last_cost,
                "lastCostText": _fmt_kamas(last_cost) if last_cost else "",
                "costPer": cost_per,
                "costPerText": _fmt_kamas(cost_per) if cost_per else "",
                "color": STAT_COLORS.get(eid, STAT_COLOR_FALLBACK),
                "icon": self._stat_icon_url(eid),
            })
        return rows

    @Property("QVariantList", notify=updated)
    def exoAttemptsActiveModel(self) -> list:
        return [r for r in self.exoAttemptsModel if int(r.get("attempts") or 0) > 0]

    @Property(str, notify=updated)
    def exoLastCostFormatted(self) -> str:
        v = int(self._exo_last_cost or 0)
        if not v:
            for rec in self._exo.values():
                v = int(rec.get("last_cost") or 0)
                if v:
                    break
        return _fmt_kamas(v) if v else ""

    @Property(str, notify=updated)
    def exoAvgCostFormatted(self) -> str:
        total = 0
        attempts = 0
        for rec in self._exo.values():
            total += int(rec.get("cost") or 0)
            attempts += int(rec.get("attempts") or 0)
        if not attempts or not total:
            return ""
        return _fmt_kamas(int(round(total / attempts)))

    @Slot(str, result=int)
    def issueCount(self, key: str) -> int:
        return self._issue(key)

    @Property("QVariantList", notify=updated)
    def statsModel(self) -> list:
        p = self._p
        if p is None:
            return []
        effects = dict(getattr(p, "_effects", None) or {})
        tpl = getattr(p, "_template", None) or {}
        eids = set(effects) | set(tpl) | set(self._seen_eids)
        if not eids:
            return []
        rows = []
        for eid in eids:
            if eid in effects:
                sv = signed_value(eid, effects[eid])
            else:
                sv = 0
            neg = sv < 0
            color = STAT_COLORS.get(eid, STAT_COLOR_FALLBACK)
            pct = ""
            if tpl and eid in tpl:
                lo, hi = tpl[eid]
                if hi > 0 and not neg:
                    pct = f"{(sv / hi * 100.0):.0f}%"
            rows.append({
                "name": effect_name(eid),
                "color": color,
                "value": str(sv),
                "pct": pct,
                "negative": neg,
                "icon": self._stat_icon_url(eid),
                "runes": int(getattr(p, "rune_by_stat", {}).get(eid, 0)),
                "cost": _fmt_kamas(int(getattr(p, "cost_by_stat", {}).get(eid, 0)))
                        if getattr(p, "cost_by_stat", {}).get(eid, 0) else "",
                "_abs": abs(sv),
            })
        rows.sort(key=lambda r: (-r["_abs"], r["name"].lower()))
        for r in rows:
            r.pop("_abs", None)
        return rows

    @Property("QVariantList", notify=updated)
    def historyModel(self) -> list:
        p = self._p
        rows = []
        events = getattr(p, "events", None) if p is not None else None
        if events:
            for ev in reversed(list(events)):
                if len(ev) < 10:
                    continue
                num, ts, ru, oc, eff, puit, dpuit, rel, perdu, cost = ev
                if ru is None:
                    continue
                rows.append({
                    "num": num,
                    "rune": RUNES.get(ru.gid, f"gid {ru.gid}"),
                    "outcome": (oc or "").upper(),
                    "outcomeLabel": {"sc": "Succès", "sn": "Neutre", "ec": "Échec"}
                    .get(oc, oc or "?"),
                    "puit": float(puit) if puit is not None else 0.0,
                    "cost": _fmt_kamas(cost) if cost else "",
                    "effects": ", ".join(
                        f"{effect_name(e)} {signed_value(e, v)}"
                        for e, v in (eff or {}).items()),
                })
        if rows:
            nums = {r["num"] for r in rows}
            older = [r for r in self._history_override if r.get("num") not in nums]
            return (rows + older)[:MAX_HISTORY_POSES]
        return list(self._history_override)[:MAX_HISTORY_POSES]

    def _panel_history_rows(self, p) -> list:
        rows = []
        for ev in reversed(list(getattr(p, "events", []) or [])):
            if len(ev) < 10:
                continue
            num, ts, ru, oc, eff, puit, dpuit, rel, perdu, cost = ev
            if ru is None:
                continue
            rows.append({
                "num": num,
                "rune": RUNES.get(ru.gid, f"gid {ru.gid}"),
                "outcome": (oc or "").upper(),
                "outcomeLabel": {"sc": "Succès", "sn": "Neutre", "ec": "Échec"}
                .get(oc, oc or "?"),
                "puit": float(puit) if puit is not None else 0.0,
                "cost": _fmt_kamas(cost) if cost else "",
                "effects": ", ".join(
                    f"{effect_name(e)} {signed_value(e, v)}"
                    for e, v in (eff or {}).items()),
            })
            if len(rows) >= MAX_HISTORY_POSES:
                break
        if rows:
            return rows
        return list(self._history_override)[:MAX_HISTORY_POSES]

    def _item_snapshot(self) -> Optional[dict]:
        p = self._p
        if p is None or not getattr(p, "item_gid", 0) or not getattr(p, "poses", 0):
            return None
        jet = -1.0
        try:
            v = p._jet_pct()
            if v is not None:
                jet = float(v)
        except Exception:
            pass
        oc = getattr(p, "outcomes", {})
        return {
            "name": item_name(p.item_gid),
            "gid": int(p.item_gid),
            "uid": int(getattr(p, "item_uid", 0) or 0),
            "icon": self._icon_for(p.item_gid),
            "jet": jet,
            "puit": float(p.puit) if getattr(p, "puit", None) is not None else 0.0,
            "poses": int(p.poses),
            "cost": _fmt_kamas(int(getattr(p, "cost_total", 0)))
                    if getattr(p, "cost_total", 0) else "",
            "cost_total": int(getattr(p, "cost_total", 0) or 0),
            "sc": int(oc.get("sc", 0)),
            "sn": int(oc.get("sn", 0)),
            "ec": int(oc.get("ec", 0)),
            "exo": {str(eid): dict(self._exo.get(eid) or {})
                    for eid, _ in EXO_TRACK},
            "exo_pending_cost": int(self._exo_pending_cost),
            "exo_last_cost": int(self._exo_last_cost),
            "exoSummary": _exo_summary(self._exo),
            "rune_by_stat": {str(k): int(v)
                             for k, v in (getattr(p, "rune_by_stat", {}) or {}).items()},
            "cost_by_stat": {str(k): int(v)
                             for k, v in (getattr(p, "cost_by_stat", {}) or {}).items()},
            "puit_delta_total": float(getattr(p, "puit_delta_total", 0) or 0),
            "reliquat_cumul": float(getattr(p, "reliquat_cumul", 0) or 0),
            "seen_eids": [int(x) for x in sorted(self._seen_eids)],
            "event_no": int(getattr(p, "event_no", 0) or 0),
            "elapsed_item": self._item_seconds(),
            "current": False,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "history": self._panel_history_rows(p),
        }

    def _archive_current_item(self) -> None:
        snap = self._item_snapshot()
        if not snap:
            return
        uid = snap["uid"]
        self._recent = [r for r in self._recent if r.get("uid") != uid]
        snap["current"] = False
        self._recent.insert(0, snap)
        self._recent = self._recent[:MAX_RECENT]
        self._schedule_history_save()

    def _schedule_history_save(self) -> None:
        self._history_save.start()

    def _history_items_to_save(self) -> list:
        rows: list[dict] = []
        seen: set[int] = set()
        cur = self._item_snapshot()
        if cur:
            rec = dict(cur)
            rec["current"] = False
            rows.append(rec)
            if rec.get("uid"):
                seen.add(int(rec["uid"]))
        for rec in self._recent:
            uid = rec.get("uid") or 0
            if uid and uid in seen:
                continue
            if uid:
                seen.add(int(uid))
            rows.append(dict(rec, current=False))
            if len(rows) >= MAX_RECENT:
                break
        return rows

    def _load_history(self) -> None:
        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return
        rows = []
        for rec in items:
            if not isinstance(rec, dict):
                continue
            try:
                gid = int(rec.get("gid") or 0)
                uid = int(rec.get("uid") or 0)
            except (TypeError, ValueError):
                continue
            if not gid:
                continue
            out = dict(rec)
            out["gid"] = gid
            out["uid"] = uid
            out["current"] = False
            out["icon"] = self._icon_for(gid)
            try:
                out["poses"] = int(out.get("poses") or 0)
                out["sc"] = int(out.get("sc") or 0)
                out["sn"] = int(out.get("sn") or 0)
                out["ec"] = int(out.get("ec") or 0)
                out["jet"] = float(out.get("jet") if out.get("jet") is not None else -1)
                out["puit"] = float(out.get("puit") or 0)
            except (TypeError, ValueError):
                continue
            if not isinstance(out.get("history"), list):
                out["history"] = []
            exo = _parse_exo(out.get("exo"))
            out["exo"] = {str(eid): dict(d) for eid, d in exo.items()}
            out["exoSummary"] = _exo_summary(exo)
            rows.append(out)
            if uid:
                self._sessions[uid] = self._session_from_snapshot(out)
            if len(rows) >= MAX_RECENT:
                break
        self._recent = rows

    def _save_history(self) -> None:
        rows = self._history_items_to_save()
        if not rows:
            return
        tmp = HISTORY_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"items": rows}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, HISTORY_PATH)
        except OSError as e:
            print("[DOFUS-FM] historique:", e, file=sys.stderr)

    @Property("QVariantList", notify=updated)
    def recentItemsModel(self) -> list:
        rows: list[dict] = []
        seen: set[int] = set()
        cur = self._item_snapshot()
        if cur:
            cur["current"] = True
            rows.append(cur)
            if cur["uid"]:
                seen.add(cur["uid"])
        for rec in self._recent:
            uid = rec.get("uid") or 0
            if uid and uid in seen:
                continue
            if uid:
                seen.add(uid)
            rows.append(dict(rec, current=False))
            if len(rows) >= MAX_RECENT:
                break
        return rows

    def _build_runes_rows(self) -> list:
        if self._runes_rows is not None:
            return self._runes_rows
        self._load_prices()
        from fetch_runes import rune_weight
        try:
            with open(data_file("runes.json"), encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            self._runes_rows = []
            return self._runes_rows
        rows = []
        for gid_s, d in (raw or {}).items():
            try:
                gid = int(gid_s)
            except (TypeError, ValueError):
                continue
            d = d or {}
            eid = int(d.get("effectId") or 0)
            name = d.get("name") or f"gid {gid}"
            stat = d.get("effect_name") or (effect_name(eid) if eid else "")
            val = d.get("value")
            w = rune_weight(name)
            price = int(self.prices.get(gid, 0) or 0)
            icon_id = d.get("icon")
            icon = self._rune_icon_for(gid, icon_id)
            rows.append({
                "gid": gid,
                "name": name,
                "stat": stat,
                "eid": eid,
                "value": "" if val is None else str(val),
                "weight": "" if w is None else (
                    str(int(w)) if float(w).is_integer() else str(w)),
                "price": _fmt_kamas(price) if price else "",
                "priceNum": price,
                "level": int(d.get("level") or 0),
                "icon": icon,
            })
        rows.sort(key=lambda r: (r["stat"].lower(), r["level"], r["name"].lower()))
        self._runes_rows = rows
        return rows

    @Slot(str)
    def set_rune_filter(self, query: str):
        q = (query or "").strip().lower()
        if q == self._rune_filter:
            return
        self._rune_filter = q
        self.runesChanged.emit()

    @Slot(str)
    def setRuneFilter(self, query: str):
        self.set_rune_filter(query)

    @Property("QVariantList", notify=runesChanged)
    def runesCatalogModel(self) -> list:
        rows = self._build_runes_rows()
        q = self._rune_filter
        if not q:
            return rows
        out = []
        for r in rows:
            hay = f"{r['name']} {r['stat']} {r['gid']}".lower()
            if q in hay:
                out.append(r)
        return out

    @Property(int, notify=runesChanged)
    def runesCatalogCount(self) -> int:
        return len(self.runesCatalogModel)

    def _default_settings(self) -> dict:
        return {
            "sound_exo": True,
            "sound_perte": True,
            "sound_exo_fail": True,
            "overlay_enabled": False,
            "overlay_x": -1,
            "overlay_y": -1,
            "overlay_w": -1,
            "overlay_h": -1,
            "rules": [dict(r) for r in DEFAULT_RULES],
        }

    def _load_settings(self) -> dict:
        cfg = self._default_settings()
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if "sound_exo" in data:
                    cfg["sound_exo"] = bool(data["sound_exo"])
                if "sound_perte" in data:
                    cfg["sound_perte"] = bool(data["sound_perte"])
                if "sound_exo_fail" in data:
                    cfg["sound_exo_fail"] = bool(data["sound_exo_fail"])
                if "overlay_enabled" in data:
                    cfg["overlay_enabled"] = bool(data["overlay_enabled"])
                try:
                    if "overlay_x" in data:
                        cfg["overlay_x"] = int(data["overlay_x"])
                    if "overlay_y" in data:
                        cfg["overlay_y"] = int(data["overlay_y"])
                    if "overlay_w" in data:
                        cfg["overlay_w"] = int(data["overlay_w"])
                    if "overlay_h" in data:
                        cfg["overlay_h"] = int(data["overlay_h"])
                except (TypeError, ValueError):
                    pass
                rules = data.get("rules")
                if isinstance(rules, list):
                    cleaned = []
                    seen = set()
                    for r in rules:
                        if not isinstance(r, dict):
                            continue
                        try:
                            eid = int(r.get("eid", 0))
                        except (TypeError, ValueError):
                            continue
                        kind = r.get("kind")
                        if eid and kind in ("exo", "perte"):
                            key = (eid, kind)
                            if key not in seen:
                                seen.add(key)
                                cleaned.append({"eid": eid, "kind": kind})
                    cfg["rules"] = cleaned
        except (OSError, ValueError):
            pass
        return cfg

    def _save_settings(self) -> None:
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print("[DOFUS-FM] settings:", e, file=sys.stderr)

    def _stat_choices(self) -> list:
        if self._stat_choices_cache is not None:
            return self._stat_choices_cache
        ids = set(STAT_COLORS)
        try:
            with open(data_file("runes.json"), encoding="utf-8") as f:
                runes = json.load(f)
            for v in runes.values():
                eid = (v or {}).get("effectId")
                if eid:
                    ids.add(int(eid))
        except (OSError, ValueError, TypeError):
            pass
        rows = []
        for eid in ids:
            name = effect_name(eid)
            if name.startswith("eff "):
                continue
            rows.append({"eid": eid, "name": name})
        rows.sort(key=lambda r: r["name"].lower())
        self._stat_choices_cache = rows
        return rows

    @Property(bool, notify=settingsChanged)
    def soundExoEnabled(self) -> bool:
        return bool(self._settings.get("sound_exo", True))

    @Property(bool, notify=settingsChanged)
    def soundPerteEnabled(self) -> bool:
        return bool(self._settings.get("sound_perte", True))

    @Property(bool, notify=settingsChanged)
    def soundExoFailEnabled(self) -> bool:
        return bool(self._settings.get("sound_exo_fail", True))

    @Slot(bool)
    def set_sound_exo_enabled(self, enabled: bool):
        self._settings["sound_exo"] = bool(enabled)
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(bool)
    def setSoundExoEnabled(self, enabled: bool):
        self.set_sound_exo_enabled(enabled)

    @Slot(bool)
    def set_sound_perte_enabled(self, enabled: bool):
        self._settings["sound_perte"] = bool(enabled)
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(bool)
    def setSoundPerteEnabled(self, enabled: bool):
        self.set_sound_perte_enabled(enabled)

    @Slot(bool)
    def set_sound_exo_fail_enabled(self, enabled: bool):
        self._settings["sound_exo_fail"] = bool(enabled)
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(bool)
    def setSoundExoFailEnabled(self, enabled: bool):
        self.set_sound_exo_fail_enabled(enabled)

    @Property(bool, notify=settingsChanged)
    def overlayEnabled(self) -> bool:
        return bool(self._settings.get("overlay_enabled", False))

    @Property(int, notify=settingsChanged)
    def overlayX(self) -> int:
        try:
            return int(self._settings.get("overlay_x", -1))
        except (TypeError, ValueError):
            return -1

    @Property(int, notify=settingsChanged)
    def overlayY(self) -> int:
        try:
            return int(self._settings.get("overlay_y", -1))
        except (TypeError, ValueError):
            return -1

    @Property(int, notify=settingsChanged)
    def overlayW(self) -> int:
        try:
            return int(self._settings.get("overlay_w", -1))
        except (TypeError, ValueError):
            return -1

    @Property(int, notify=settingsChanged)
    def overlayH(self) -> int:
        try:
            return int(self._settings.get("overlay_h", -1))
        except (TypeError, ValueError):
            return -1

    @Slot(bool)
    def set_overlay_enabled(self, enabled: bool):
        self._settings["overlay_enabled"] = bool(enabled)
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(bool)
    def setOverlayEnabled(self, enabled: bool):
        self.set_overlay_enabled(enabled)

    @Slot(int, int, int, int)
    def save_overlay_geometry(self, x: int, y: int, w: int, h: int):
        self._settings["overlay_x"] = int(x)
        self._settings["overlay_y"] = int(y)
        self._settings["overlay_w"] = max(180, int(w))
        self._settings["overlay_h"] = max(120, int(h))
        self._save_settings()

    @Slot(int, int, int, int)
    def saveOverlayGeometry(self, x: int, y: int, w: int, h: int):
        self.save_overlay_geometry(x, y, w, h)

    @Slot(int, int)
    def save_overlay_position(self, x: int, y: int):
        self.save_overlay_geometry(x, y, self.overlayW, self.overlayH)

    @Slot(int, int)
    def saveOverlayPosition(self, x: int, y: int):
        self.save_overlay_position(x, y)

    @Property("QVariantList", notify=settingsChanged)
    def soundRulesModel(self) -> list:
        rows = []
        for r in self._settings.get("rules") or []:
            eid = int(r["eid"])
            kind = r["kind"]
            rows.append({
                "key": f"{eid}:{kind}",
                "eid": eid,
                "name": effect_name(eid),
                "kind": kind,
                "kindLabel": "Exo (joyeux)" if kind == "exo" else "Perte",
            })
        return rows

    @Property("QVariantList", notify=settingsChanged)
    def statChoicesModel(self) -> list:
        return self._stat_choices()

    @Slot(int, str)
    def add_sound_rule(self, eid: int, kind: str):
        if kind not in ("exo", "perte") or not eid:
            return
        rules = self._settings.setdefault("rules", [])
        if any(int(r.get("eid", 0)) == eid and r.get("kind") == kind for r in rules):
            return
        rules.append({"eid": int(eid), "kind": kind})
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(int, str)
    def addSoundRule(self, eid: int, kind: str):
        self.add_sound_rule(eid, kind)

    @Slot(str)
    def remove_sound_rule(self, key: str):
        if ":" not in key:
            return
        eid_s, kind = key.split(":", 1)
        try:
            eid = int(eid_s)
        except ValueError:
            return
        rules = self._settings.get("rules") or []
        self._settings["rules"] = [
            r for r in rules
            if not (int(r.get("eid", 0)) == eid and r.get("kind") == kind)]
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(str)
    def removeSoundRule(self, key: str):
        self.remove_sound_rule(key)

    def _load_prices(self):
        if self._prices_loaded:
            return
        self._prices_loaded = True
        try:
            with open(data_file("prices.json"), encoding="utf-8") as f:
                self.prices = {int(k): v for k, v in json.load(f).items()}
        except (OSError, ValueError):
            self.prices = {}

    _STAT_ICONS: dict[int, str] | None = None
    _STAT_ICON_DIR = os.path.join(APP_DIR, "fm_ui", "icons", "stats")
    _KAMA_PATH = os.path.join(APP_DIR, "fm_ui", "icons", "kama.png")
    _KAMA_CDN = "https://www.dofusdb.fr/icons/kama.png"

    @Property(str, notify=updated)
    def kamaIcon(self) -> str:
        self._ensure_kama_icon()
        if os.path.isfile(self._KAMA_PATH):
            return QUrl.fromLocalFile(self._KAMA_PATH).toString()
        return ""

    def _ensure_kama_icon(self) -> None:
        path = self._KAMA_PATH
        if os.path.isfile(path) and os.path.getsize(path) > 32:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            req = urllib.request.Request(
                self._KAMA_CDN, headers={"User-Agent": "dofus-fm/1.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = r.read()
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                with open(path, "wb") as f:
                    f.write(data)
        except Exception as e:
            print("[DOFUS-FM] icone kama:", e)

    def _stat_icon_url(self, eid: int) -> str:
        if FmPanelBridge._STAT_ICONS is None:
            try:
                with open(data_file("stat_icons.json"), encoding="utf-8") as f:
                    FmPanelBridge._STAT_ICONS = {
                        int(k): v for k, v in json.load(f).items()
                    }
            except (OSError, ValueError):
                FmPanelBridge._STAT_ICONS = {}
        asset = FmPanelBridge._STAT_ICONS.get(eid)
        if not asset:
            return ""
        local = os.path.join(self._STAT_ICON_DIR, f"{asset}.png")
        if not os.path.exists(local):
            return ""
        return QUrl.fromLocalFile(local).toString()

    def shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        self._stop_thread()
        self._archive_current_item()
        self._save_history()
        if self._panel is not None:
            try:
                self._panel.close()
            except Exception:
                pass

    @Slot()
    def quit_app(self):
        if self._quit_requested:
            QCoreApplication.quit()
            return
        self._quit_requested = True
        self.shutdown()
        inst = QGuiApplication.instance()
        if inst is not None:
            for w in inst.allWindows():
                try:
                    w.hide()
                    w.close()
                except Exception:
                    pass
        QCoreApplication.quit()

    @Slot()
    def quitApp(self):
        self.quit_app()
