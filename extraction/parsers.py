"""Interpretación de celdas y reconstrucción de filas a partir de palabras posicionadas.

Funciona igual con palabras de la capa de texto (pdfplumber) y con palabras de OCR.
Todo lo extraído es una PROPUESTA que debe validarse en la vista previa.
"""
from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field

from core.config import KNOWN_LOCATIONS
from core.experience import parse_band_label

_NA = re.compile(r"^(n\.?\s*/?\s*a\.?|n\.?\s*d\.?|s\s*/\s*d|-|—|–|\*)$", re.IGNORECASE)
_N = r"(\d{1,3}(?:[.\s]\d{3})+|\d+(?:[.,]\d+)?)"
_K = r"\s*(k\s*€?|k€|€)?"


@dataclass
class CellValue:
    kind: str                     # puntual | intervalo | abierto_superior | abierto_inferior | na | none
    valor: float | None = None
    valor_min: float | None = None
    valor_max: float | None = None
    alerts: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).strip()


def _number(num: str, k: bool, k_hint: bool, alerts: list[str]) -> float | None:
    s = num.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        v = float(s.replace(".", ""))
    elif re.fullmatch(r"\d+,\d+", s):
        v = float(s.replace(",", "."))
    elif re.fullmatch(r"\d+\.\d{1,2}", s):
        v = float(s)
    else:
        try:
            v = float(s.replace(",", "."))
        except ValueError:
            return None
    if k:
        return v * 1000
    if v < 1000:
        if k_hint:
            alerts.append("Multiplicado ×1000 por cabecera en miles (K€)")
            return v * 1000
        alerts.append("Unidad no determinada (¿miles?): completar manualmente")
        return None
    return v


def parse_market_cell(text: str, k_hint: bool = False) -> CellValue:
    t = _norm(text).lower().replace("–", "-").replace("—", "-")
    t = re.sub(r"\s*(eur|euros)\b", "€", t)
    if t == "" or _NA.match(t):
        return CellValue("na")
    alerts: list[str] = []
    m = re.fullmatch(rf"{_N}{_K}\s*(?:-|a|/)\s*{_N}{_K}", t)
    if m:
        k1, k2 = bool(m.group(2) and "k" in m.group(2)), bool(m.group(4) and "k" in m.group(4))
        shared_k = k1 or k2
        if k2 and not k1:
            alerts.append("Sufijo K compartido aplicado a ambos límites")
        lo = _number(m.group(1), shared_k, k_hint, alerts)
        hi = _number(m.group(3), shared_k, k_hint, alerts)
        if lo is not None and hi is not None and lo > hi:
            alerts.append("Límite inferior mayor que superior en la fuente (no corregido)")
        return CellValue("intervalo", None, lo, hi, alerts)
    m = re.fullmatch(rf"(?:>|\+|más de|mas de|>=|desde)\s*{_N}{_K}|{_N}{_K}\s*\+", t)
    if m:
        num = m.group(1) or m.group(3)
        suf = m.group(2) or m.group(4) or ""
        return CellValue("abierto_superior", None, _number(num, "k" in suf, k_hint, alerts), None, alerts)
    m = re.fullmatch(rf"(?:<|menos de|hasta)\s*{_N}{_K}", t)
    if m:
        k = bool(m.group(2) and "k" in m.group(2))
        return CellValue("abierto_inferior", None, None, _number(m.group(1), k, k_hint, alerts), alerts)
    m = re.fullmatch(rf"{_N}{_K}", t)
    if m:
        k = bool(m.group(2) and "k" in m.group(2))
        return CellValue("puntual", _number(m.group(1), k, k_hint, alerts), None, None, alerts)
    if re.fullmatch(r"\d+(?:[.,]\d+)?\s*%|0[.,]\d+", t):
        return CellValue("none", alerts=["porcentaje"])
    return CellValue("none")


def is_value_cell(text: str) -> bool:
    return parse_market_cell(text).kind != "none" and bool(re.search(r"\d|n\.?\s*/?a|^-$", text.strip().lower()))


# ------------------------------------------------------------- palabras -> filas
@dataclass
class Cell:
    x0: float
    x1: float
    text: str
    conf: float = 100.0

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


def words_to_lines(words: list[dict]) -> list[list[Cell]]:
    """words: dicts con x0, x1, top, bottom, text (y opcional conf)."""
    if not words:
        return []
    h = statistics.median([w["bottom"] - w["top"] for w in words]) or 8
    lines, cur, cur_top = [], [], None
    for w in sorted(words, key=lambda w: w["top"]):
        if cur_top is None or abs(w["top"] - cur_top) <= h * 0.5:
            cur.append(w)
            cur_top = w["top"] if cur_top is None else cur_top
        else:
            lines.append(cur)
            cur, cur_top = [w], w["top"]
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda w: w["x0"])
        cells: list[Cell] = []
        for w in ln:
            if cells and w["x0"] - cells[-1].x1 <= h * 0.9:
                c = cells[-1]
                cells[-1] = Cell(c.x0, w["x1"], f"{c.text} {w['text']}", min(c.conf, w.get("conf", 100)))
            else:
                cells.append(Cell(w["x0"], w["x1"], w["text"], w.get("conf", 100)))
        out.append(_split_value_runs(cells))
    return out


def _split_value_runs(cells: list[Cell]) -> list[Cell]:
    """Separa celdas fusionadas del tipo '45.000 52.000' en valores independientes."""
    res = []
    for c in cells:
        toks = c.text.split()
        if len(toks) > 1 and all(is_value_cell(t) for t in toks) and not is_value_cell(c.text):
            step = (c.x1 - c.x0) / len(toks)
            res += [Cell(c.x0 + i * step, c.x0 + (i + 1) * step, t, c.conf) for i, t in enumerate(toks)]
        else:
            res.append(c)
    return res


def _location_of(text: str) -> str | None:
    t = _norm(text).lower()
    for loc in KNOWN_LOCATIONS:
        if re.search(rf"(?<!\w){re.escape(loc.lower())}(?!\w)", t):
            return loc
    return None


def _band_of(text: str) -> str | None:
    t = _norm(text)
    if re.search(r"\d", t) and parse_band_label(t) is not None and re.search(r"(año|year|[<>+]|\d\s*-\s*\d)", t, re.I):
        return t
    return None


def _is_var(text: str) -> bool:
    return bool(re.search(r"\b(var\.?|variable|bonus)\b", text, re.I))


@dataclass
class RawRecord:
    pagina: int
    rol_original: str
    categoria: str
    ubicacion: str
    banda: str
    cell_text: str
    variable: str
    alerts: list[str]


def _nearest(c: Cell, hdr: list[Cell]) -> Cell | None:
    if not hdr:
        return None
    return min(hdr, key=lambda h: abs(h.xc - c.xc))


def lines_to_records(lines: list[list[Cell]], page_no: int, k_hint_page: bool) -> tuple[list[RawRecord], list[str]]:
    records: list[RawRecord] = []
    notes: list[str] = []
    loc_hdr: list[Cell] = []
    band_hdr: list[Cell] = []
    var_hdr: list[Cell] = []
    category = ""
    in_data = False
    for cells in lines:
        texts = [c.text for c in cells]
        locs = [c for c in cells if _location_of(c.text)]
        bands = [c for c in cells if _band_of(c.text)]
        values = [c for c in cells if is_value_cell(c.text)]
        if len(locs) >= 2 or len(bands) >= 2:
            if in_data:
                loc_hdr, band_hdr, var_hdr, in_data = [], [], [], False
            loc_hdr += locs
            band_hdr += bands
            var_hdr += [c for c in cells if _is_var(c.text)]
            continue
        first_val = next((i for i, c in enumerate(cells) if is_value_cell(c.text)), None)
        if first_val is None or first_val == 0:
            joined = " ".join(texts).strip()
            if joined.startswith(("*", "(1)", "(2)", "Nota", "Fuente")):
                notes.append(joined)
            elif joined and len(cells) <= 2 and not values:
                category = joined
            continue
        role = " ".join(texts[:first_val]).strip()
        if not (band_hdr or loc_hdr):
            notes.append(f"Fila sin cabecera reconocible: «{role}»")
            continue
        in_data = True
        row_alerts = []
        if re.search(r"[A-Za-z]\.?\d|\d[A-Za-z]{2,}|\.\d{3}[a-z]", role):
            row_alerts.append("Posible error de la capa de texto en el rol")
        if "*" in role:
            row_alerts.append("Rol con nota al pie: revisar notas de la página")
        if any(c.conf < 60 for c in cells):
            row_alerts.append("OCR con baja confianza en esta fila")
        var_cells = [c for c in cells[first_val:] if var_hdr and _nearest(c, var_hdr + band_hdr) in var_hdr]
        variable = " ".join(c.text for c in var_cells)
        for c in cells[first_val:]:
            if c in var_cells or not is_value_cell(c.text):
                continue
            b = _nearest(c, band_hdr)
            lc = _nearest(c, loc_hdr)
            records.append(RawRecord(
                page_no, role, category,
                _location_of(lc.text) if lc else "",
                b.text if b else "", c.text, variable, list(row_alerts)))
    return records, notes


def page_hints(text: str) -> dict:
    t = text.lower()
    stat = None
    for kw, st in (("moda", "moda"), ("mediana", "mediana"), ("media", "media"), ("promedio", "media")):
        if re.search(rf"\b{kw}\b", t):
            stat = st
            break
    return {"stat_hint": stat, "k_hint": bool(re.search(r"\bk€|\(k\)|miles de", t))}
