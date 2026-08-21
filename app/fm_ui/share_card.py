"""Carte image partageable d'une session FM (Discord, etc.)."""
from __future__ import annotations

import os
import sys
from typing import Optional

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from PySide6.QtCore import Qt, QRectF, QUrl
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen,
)

from fm_decoder import effect_name, signed_value
import fm_decoder
from fm_ui.constants import (
    APP_NAME, COLORS, JET_GREEN, JET_YELLOW, STAT_COLOR_FALLBACK, STAT_COLORS,
)
from item_jet import get_template, global_jet_pct
from paths import APP_DIR, PROJECT_DIR, data_file

SCALE = 2
WIDTH = 520
PAD = 18
HEADER_H = 78
ROW_H = 26
FOOTER_H = 78
GAP = 12
BAR_H = 8
ICON_SZ = 56


def _fmt_kamas(v: int) -> str:
    return f"{int(v):,}".replace(",", " ")


OVER_GOLD = "#d4b45a"


def _q(hex_color: str) -> QColor:
    return QColor(hex_color)


def _jet_color(pct: float) -> QColor:
    if pct >= JET_GREEN:
        return _q(COLORS["success"])
    if pct >= JET_YELLOW:
        return _q(COLORS["warning"])
    return _q(COLORS["danger"])


def _local_path(url_or_path: str) -> str:
    if not url_or_path:
        return ""
    if url_or_path.startswith("file:"):
        return QUrl(url_or_path).toLocalFile()
    if os.path.isfile(url_or_path):
        return url_or_path
    return ""


def _load_image(path: str) -> Optional[QImage]:
    p = _local_path(path) if path.startswith("file:") else path
    if not p or not os.path.isfile(p):
        return None
    img = QImage(p)
    if img.isNull():
        return None
    return img


def _stat_icon_path(eid: int) -> str:
    try:
        with open(data_file("stat_icons.json"), encoding="utf-8") as f:
            import json
            mapping = {int(k): v for k, v in json.load(f).items()}
    except (OSError, ValueError, TypeError):
        return ""
    asset = mapping.get(int(eid))
    if not asset:
        return ""
    local = os.path.join(APP_DIR, "fm_ui", "icons", "stats", f"{asset}.png")
    return local if os.path.isfile(local) else ""


def _kama_path() -> str:
    p = os.path.join(APP_DIR, "fm_ui", "icons", "kama.png")
    return p if os.path.isfile(p) else ""


def lines_from_item(gid: int, effects: dict) -> list[dict]:
    """Lignes de jet : actuel / maxi du template, plus les exo hors jet."""
    raw: dict[int, int] = {}
    for k, v in (effects or {}).items():
        try:
            raw[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    try:
        tpl = get_template(int(gid)) if gid else {}
    except Exception:
        tpl = {}
    eids = list(tpl.keys()) + [e for e in raw if e not in tpl]
    if not raw:
        return []
    rows = []
    for eid in eids:
        if eid in raw:
            sv = signed_value(eid, raw[eid])
        else:
            sv = 0
        lo = hi = None
        if eid in tpl:
            lo, hi = tpl[eid]
        color = STAT_COLORS.get(eid, STAT_COLOR_FALLBACK)
        malus = eid in fm_decoder.MALUS_EFFECTS or (hi is not None and hi < 0)
        rows.append({
            "eid": eid,
            "name": effect_name(eid),
            "value": sv,
            "lo": lo,
            "hi": hi,
            "color": color,
            "icon": _stat_icon_path(eid),
            "malus": malus,
            "exo": (not malus) and hi is None,
        })
    rows.sort(key=lambda r: (
        r["malus"],
        0 if r["exo"] else 1,
        -abs(int(r["value"] or 0)),
        r["name"].lower(),
    ))
    return rows


def jet_pct_of(gid: int, effects: dict) -> Optional[float]:
    raw: dict[int, int] = {}
    for k, v in (effects or {}).items():
        try:
            raw[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    try:
        tpl = get_template(int(gid)) if gid else {}
    except Exception:
        tpl = {}
    effect_name(125)
    return global_jet_pct(raw, tpl, fm_decoder.MALUS_EFFECTS)


def _elide(fm: QFontMetrics, text: str, width: int) -> str:
    return fm.elidedText(text, Qt.ElideRight, width)


def _draw_kama_amount(p: QPainter, x: int, y: int, text: str, font: QFont,
                      color: QColor, align_center_w: int = 0) -> None:
    p.setFont(font)
    fm = QFontMetrics(font)
    tw = fm.horizontalAdvance(text)
    icon = _load_image(_kama_path())
    iw = 13 if icon is not None else 0
    gap = 4 if icon is not None else 0
    total = tw + gap + iw
    if align_center_w:
        x = x + (align_center_w - total) // 2
    p.setPen(color)
    p.drawText(x, y, text)
    if icon is not None:
        iy = y - fm.ascent() + (fm.height() - iw) // 2
        p.drawImage(QRectF(x + tw + gap, iy, iw, iw), icon)


def render_share_card(
    *,
    name: str,
    gid: int = 0,
    icon_path: str = "",
    effects: Optional[dict] = None,
    poses: int = 0,
    cost_total: int = 0,
    jet: Optional[float] = None,
    exo_summary: str = "",
    level: Optional[int] = None,
) -> QImage:
    rows = lines_from_item(gid, effects or {})
    if jet is None or jet < 0:
        jet = jet_pct_of(gid, effects or {})
    avg = int(round(cost_total / poses)) if poses and cost_total else 0

    n = max(1, len(rows))
    h = PAD + HEADER_H + n * ROW_H + GAP + FOOTER_H + PAD
    img = QImage(WIDTH * SCALE, h * SCALE, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.scale(SCALE, SCALE)

    bg = _q(COLORS["bg_card"])
    path = QPainterPath()
    path.addRoundedRect(QRectF(0.5, 0.5, WIDTH - 1, h - 1), 12, 12)
    p.fillPath(path, bg)
    p.setPen(QPen(_q(COLORS["separator"]), 1))
    p.drawPath(path)

    accent = QPainterPath()
    accent.addRoundedRect(QRectF(0.5, 0.5, 5, h - 1), 12, 12)
    p.fillPath(accent, _q(COLORS["primary"]))

    x0 = PAD + 6
    y0 = PAD

    item_icon = _load_image(icon_path)
    icon_rect = QRectF(x0, y0, ICON_SZ, ICON_SZ)
    p.setPen(QPen(_q(COLORS["separator"]), 1))
    p.setBrush(_q(COLORS["bg"]))
    p.drawRoundedRect(icon_rect, 8, 8)
    if item_icon is not None:
        p.drawImage(icon_rect.adjusted(4, 4, -4, -4), item_icon)
    else:
        p.setPen(_q(COLORS["text_muted"]))
        f = QFont(COLORS["font_family"], 22, QFont.Bold)
        p.setFont(f)
        letter = (name[:1] or "?").upper()
        p.drawText(icon_rect, Qt.AlignCenter, letter)

    title_x = int(icon_rect.right()) + 12
    title_w = WIDTH - title_x - PAD
    f_title = QFont(COLORS["font_family"], 15, QFont.Bold)
    p.setFont(f_title)
    p.setPen(_q(COLORS["text"]))
    p.drawText(title_x, y0 + 22, _elide(QFontMetrics(f_title), name, title_w))

    f_sub = QFont(COLORS["font_family"], 10)
    p.setFont(f_sub)
    p.setPen(_q(COLORS["text_muted"]))
    bits = []
    if level:
        bits.append(f"Niv. {level}")
    if gid:
        bits.append(f"GID {gid}")
    if exo_summary:
        bits.append(exo_summary)
    p.drawText(title_x, y0 + 40, " · ".join(bits) if bits else APP_NAME)

    f_jet = QFont(COLORS["font_family"], 13, QFont.Bold)
    p.setFont(f_jet)
    if jet is not None:
        p.setPen(_jet_color(float(jet)))
        p.drawText(title_x, y0 + 62, f"Jet {jet:.1f}%")
    else:
        p.setPen(_q(COLORS["text_muted"]))
        p.drawText(title_x, y0 + 62, "Jet non enregistre")

    p.setPen(_q(COLORS["text_muted"]))
    f_mark = QFont(COLORS["font_family"], 9)
    p.setFont(f_mark)
    wm = APP_NAME
    wm_w = QFontMetrics(f_mark).horizontalAdvance(wm)
    p.drawText(WIDTH - PAD - wm_w, y0 + 14, wm)

    y = y0 + HEADER_H
    f_name = QFont(COLORS["font_family"], 10)
    f_val = QFont(COLORS["font_family"], 10, QFont.Bold)
    name_x = x0 + 22
    bar_x = x0 + 172
    bar_w = 208
    val_x = bar_x + bar_w + 10
    val_w = WIDTH - PAD - val_x

    if not rows:
        p.setFont(f_name)
        p.setPen(_q(COLORS["text_muted"]))
        p.drawText(x0, y + 16, "Pas de jet enregistre pour cette session.")
        y += ROW_H
    else:
        for row in rows:
            cy = y + ROW_H // 2
            ico = _load_image(row["icon"])
            if ico is not None:
                p.drawImage(QRectF(x0, cy - 9, 18, 18), ico)
            else:
                p.setBrush(_q(row["color"]))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QRectF(x0 + 2, cy - 7, 14, 14))

            p.setFont(f_name)
            p.setPen(_q(COLORS["text"]))
            p.drawText(name_x, cy + 4,
                       _elide(QFontMetrics(f_name), row["name"], bar_x - name_x - 8))

            hi = row["hi"]
            sv = int(row["value"] or 0)
            malus = bool(row["malus"])
            exo = bool(row.get("exo"))
            is_over = (not malus and not exo and hi is not None
                       and hi > 0 and sv > hi)
            track = QRectF(bar_x, cy - BAR_H / 2, bar_w, BAR_H)
            p.setBrush(_q(COLORS["bg"]))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(track, 4, 4)

            ratio = 0.0
            if hi is not None and not malus and hi > 0:
                ratio = max(0.0, min(1.0, sv / float(hi)))
            elif malus and hi is not None:
                cap = max(abs(int(row["lo"] or hi)), abs(int(hi)), 1)
                ratio = max(0.0, min(1.0, abs(sv) / float(cap)))
            elif exo and sv:
                ratio = 1.0

            if ratio > 0:
                fill = QRectF(track.x(), track.y(), track.width() * ratio, track.height())
                if is_over:
                    col = _q(OVER_GOLD)
                elif exo:
                    col = _q("#5a9fd4")
                elif not malus and hi and hi > 0:
                    col = _jet_color(sv / float(hi) * 100.0)
                else:
                    col = _q(row["color"])
                p.setBrush(col)
                p.drawRoundedRect(fill, 4, 4)
            if is_over:
                ox = track.right() - 3
                p.setBrush(_q(OVER_GOLD))
                p.drawRoundedRect(QRectF(ox, track.y() - 1, 3, track.height() + 2), 1, 1)

            if exo:
                label = f"{sv}  exo"
            elif hi is not None:
                label = f"{sv} / {hi}"
            else:
                label = str(sv)
            p.setFont(f_val)
            if malus:
                p.setPen(_q(COLORS["text_muted"]))
            elif is_over:
                p.setPen(_q(OVER_GOLD))
            elif exo:
                p.setPen(_q("#6ea8d8"))
            elif hi and hi > 0 and sv >= hi:
                p.setPen(_q(COLORS["success"]))
            else:
                p.setPen(_q(COLORS["text"]))
            p.drawText(QRectF(val_x, y, val_w, ROW_H),
                       Qt.AlignVCenter | Qt.AlignRight, label)
            y += ROW_H

    fy = h - PAD - FOOTER_H
    p.setPen(QPen(_q(COLORS["separator"]), 1))
    p.drawLine(x0, fy, WIDTH - PAD, fy)
    fy += 10

    cells = [
        (str(int(poses)), "tentatives", False),
        (_fmt_kamas(cost_total) if cost_total else "-", "prix total", True),
        (_fmt_kamas(avg) if avg else "-", "moy. / tenta", True),
        (f"{jet:.1f}%" if jet is not None else "-", "jet", False),
    ]
    cell_w = (WIDTH - PAD - x0) / 4
    f_num = QFont(COLORS["font_family"], 13, QFont.Bold)
    f_lab = QFont(COLORS["font_family"], 9)
    for i, (num, lab, is_kama) in enumerate(cells):
        cx = x0 + i * cell_w
        p.setPen(_q(COLORS["text_muted"]))
        p.setFont(f_lab)
        p.drawText(QRectF(cx, fy, cell_w, 16), Qt.AlignHCenter, lab.upper())
        if is_kama and num != "-":
            _draw_kama_amount(
                p, int(cx), fy + 40, num, f_num, _q(COLORS["text"]),
                align_center_w=int(cell_w))
        else:
            p.setFont(f_num)
            if lab == "jet" and jet is not None:
                p.setPen(_jet_color(float(jet)))
            else:
                p.setPen(_q(COLORS["text"]))
            p.drawText(QRectF(cx, fy + 20, cell_w, 28), Qt.AlignHCenter | Qt.AlignVCenter, num)

    p.end()
    return img


def preview_strigide() -> QImage:
    """Carte exemple : Amulette du Strigide (GID 14094), jet FM plausible."""
    gid = 14094
    name = "Amulette du Strigide"
    icon = _ensure_item_icon(gid, "https://api.dofusdu.de/dofus3/v1/img/item/1235-64.png")
    _ensure_kama_icon()
    # Valeurs paquet (malus en magnitude positive). Mix over-max / sous-max
    # pour que les barres se lisent comme une distribution.
    effects = {
        125: 480,   # Vitalité / 400  over
        124: 36,    # Sagesse / 40
        115: 5,     # Critique / 6
        138: 85,    # Puissance / 70  over
        111: 1,     # PA / 1
        128: 1,     # PM exo (hors jet)
        210: 7,     # Ré Per Terre / 8
        212: 6,     # Ré Per Air / 8
        160: 4,     # Esquive PA / 6
        753: 13,    # Tacle / 15
        418: 22,    # Do Crit / 25
        421: 18,    # Rés. Critiques malus
    }
    return render_share_card(
        name=name,
        gid=gid,
        icon_path=icon,
        effects=effects,
        poses=186,
        cost_total=842150,
        exo_summary="",
        level=200,
    )


def _ensure_kama_icon() -> None:
    dest = os.path.join(APP_DIR, "fm_ui", "icons", "kama.png")
    if os.path.isfile(dest) and os.path.getsize(dest) > 32:
        return
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://www.dofusdb.fr/icons/kama.png",
            headers={"User-Agent": "dofus-fm/1.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = r.read()
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
    except Exception:
        pass


def _ensure_item_icon(gid: int, url: str) -> str:
    from paths import cache_dir
    dest = os.path.join(cache_dir("icons"), f"{gid}.png")
    if os.path.isfile(dest) and os.path.getsize(dest) > 32:
        return dest
    bundled = os.path.join(APP_DIR, "fm_ui", "icons", f"{gid}.png")
    if os.path.isfile(bundled):
        return bundled
    if not url:
        return dest
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "dofus-fm/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        if data[:4] == b"\x89PNG":
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
    except Exception:
        pass
    return dest


if __name__ == "__main__":
    _app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _app_dir not in sys.path:
        sys.path.insert(0, _app_dir)
    from PySide6.QtWidgets import QApplication
    qapp = QApplication(sys.argv)
    image = preview_strigide()
    out = os.path.join(PROJECT_DIR, "_scratch", "preview_strigide.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    image.save(out, "PNG")
    print(out)
