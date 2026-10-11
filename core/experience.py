"""Interpretación conservadora de textos de experiencia.

Cada mención se convierte en un *intervalo* (no en una cifra exacta):
    "5 years"        -> [5, 5]      exacto
    "6/7 years"      -> [6, 7]      intervalo
    "over 20", "+9"  -> (20, ∞)     límite abierto
    "less than 1"    -> [0, 1)      límite abierto
    "almost 4"       -> (?, 4)      límite inferior desconocido
    "around 5"       -> aproximado (no asignable sin validación)
El tipo (total / puesto / tecnología) solo se asigna si el texto lo indica
explícitamente; en otro caso queda como "no especificada".
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

INF = math.inf

_WORDNUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3,
    "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}
_NUM = r"(\d+(?:[.,]\d+)?)"
_UNIT = r"(?:years?|yrs?|yeas?|años?|anos?|year's)"


@dataclass(frozen=True)
class Interval:
    low: float | None          # None = desconocido
    low_incl: bool
    high: float | None         # INF = abierto; None = desconocido
    high_incl: bool
    exactness: str             # exacto | intervalo | límite abierto | aproximado | límite inferior desconocido

    def to_text(self) -> str:
        if self.exactness == "aproximado":
            return f"~{_fmt(self.low)}"
        lo = "?" if self.low is None else _fmt(self.low)
        hi = "?" if self.high is None else ("∞" if self.high == INF else _fmt(self.high))
        if self.low is not None and self.high is not None and self.low == self.high:
            return _fmt(self.low)
        return f"{'[' if self.low_incl else '('}{lo}, {hi}{']' if self.high_incl else ')'}"


@dataclass(frozen=True)
class ExperienceItem:
    kind: str
    interval: Interval
    fragment: str
    kind_explicit: bool


def _fmt(v: float | None) -> str:
    if v is None:
        return "?"
    return str(int(v)) if float(v).is_integer() else str(v).replace(".", ",")


def _num(s: str) -> float:
    s = s.lower()
    if s in _WORDNUM:
        return float(_WORDNUM[s])
    return float(s.replace(",", "."))


def parse_interval_notation(text: str) -> Interval | None:
    """Lee la notación editable: '5', '[3, 4)', '(20, ∞)', '[0, 1)', '~5', '(?, 4)'."""
    if text is None:
        return None
    t = str(text).strip()
    if t == "" or t.lower() in ("nan", "none"):
        return None
    if t.startswith("~"):
        return Interval(_num(t[1:].strip()), True, _num(t[1:].strip()), True, "aproximado")
    m = re.fullmatch(r"([\[(])\s*([^,;]+?)\s*[,;]\s*([^\])]+?)\s*([\])])", t)
    if m:
        lo_s, hi_s = m.group(2), m.group(3)
        lo = None if lo_s == "?" else _num(lo_s)
        hi = None if hi_s == "?" else (INF if hi_s in ("∞", "inf", "+inf") else _num(hi_s))
        if lo is None:
            ex = "límite inferior desconocido"
        elif hi == INF or (lo == 0 and m.group(4) == ")"):
            ex = "límite abierto"
        else:
            ex = "intervalo"
        return Interval(lo, m.group(1) == "[", hi, m.group(4) == "]", ex)
    try:
        v = _num(t)
        return Interval(v, True, v, True, "exacto")
    except ValueError:
        raise ValueError(f"Notación de intervalo no válida: {t!r}")


def _kind_of(fragment: str, role: str = "") -> tuple[str, bool]:
    f = fragment.lower()
    if re.search(r"\b(total|overall|en total|career|carrera|professional experience|"
                 r"experiencia profesional|in it\b|en it\b|in the it)", f):
        return "total", True
    if re.search(r"\b(in the (role|position|same role|current role)|en el puesto|en el rol|"
                 r"in this (role|position)|en (este|el mismo) puesto|in role)\b", f):
        return "puesto", True
    if re.search(r"\b(with|in|en|con|using)\s+[a-z0-9/.#+]{2,}", f) and not re.search(
            r"\b(in|en)\s+(the|el|la|los|las)?\s*(role|position|puesto|rol|company|empresa)\b", f):
        return "tecnología/especialidad", True
    return "no especificada", False


def _interval_from(fragment: str) -> Interval | None:
    f = fragment.lower().replace("–", "-").replace("—", "-")
    for w, n in _WORDNUM.items():
        f = re.sub(rf"\b{w}\b", str(n), f)
    months = re.search(rf"{_NUM}\s*(?:months?|meses?)", f)
    yrs_and_months = re.search(rf"{_NUM}\s*{_UNIT}\s*(?:and|y)\s*{_NUM}\s*(?:months?|meses?)", f)
    if yrs_and_months:
        v = _num(yrs_and_months.group(1)) + _num(yrs_and_months.group(2)) / 12
        return Interval(v, True, v, True, "exacto")
    pats = [
        (rf"(?:between|entre)\s*{_NUM}\s*(?:and|y|-)\s*{_NUM}", "range"),
        (rf"{_NUM}\s*(?:/|-|to|a)\s*{_NUM}(?=\s*(?:{_UNIT}|$|\s))", "range"),
        (rf"(?:over|more than|más de|mas de|above|>)\s*{_NUM}", "gt"),
        (rf"\+\s*{_NUM}|{_NUM}\s*\+", "gt_plus"),
        (rf"(?:at least|al menos|mínimo|minimo|min\.?)\s*{_NUM}", "ge"),
        (rf"(?:less than|under|menos de|below|<)\s*{_NUM}", "lt"),
        (rf"(?:up to|hasta)\s*{_NUM}", "le"),
        (rf"(?:almost|nearly|casi|close to|cerca de)\s*{_NUM}", "almost"),
        (rf"(?:about|around|approximately|approx\.?|aprox\.?|aproximadamente|~)\s*{_NUM}", "approx"),
    ]
    for pat, kind in pats:
        m = re.search(pat, f)
        if not m:
            continue
        nums = [g for g in m.groups() if g is not None]
        if kind == "range":
            a, b = sorted((_num(nums[0]), _num(nums[1])))
            return Interval(a, True, b, True, "intervalo")
        n = _num(nums[0])
        if kind in ("gt", "gt_plus"):
            return Interval(n, False, INF, False, "límite abierto")
        if kind == "ge":
            return Interval(n, True, INF, False, "límite abierto")
        if kind == "lt":
            return Interval(0.0, True, n, False, "límite abierto")
        if kind == "le":
            return Interval(0.0, True, n, True, "límite abierto")
        if kind == "almost":
            return Interval(None, False, n, False, "límite inferior desconocido")
        if kind == "approx":
            return Interval(n, True, n, True, "aproximado")
    if months and not re.search(rf"{_NUM}\s*{_UNIT}", f):
        v = _num(months.group(1)) / 12
        return Interval(v, True, v, True, "exacto")
    m = re.search(rf"{_NUM}\s*{_UNIT}", f)
    if m:
        v = _num(m.group(1))
        return Interval(v, True, v, True, "exacto")
    return None


def parse_experience(text: object, role: str = "") -> list[ExperienceItem]:
    if text is None:
        return []
    t = str(text).strip()
    if not t or t.lower() == "nan":
        return []
    fragments = re.split(r"[;\n]|,(?!\d)|\.(?!\d)|\s+(?:and|y)\s+(?=\D*\d)", t)
    items: list[ExperienceItem] = []
    for frag in (x.strip() for x in fragments):
        if not frag:
            continue
        iv = _interval_from(frag)
        if iv is None:
            continue
        kind, explicit = _kind_of(frag, role)
        items.append(ExperienceItem(kind, iv, frag, explicit))
    return items


@dataclass(frozen=True)
class Band:
    label: str
    interval: Interval


def parse_band_label(label: str) -> Interval | None:
    """Interpreta etiquetas de banda de las guías: '<2', '2-5', '>5', '+5', '8+', '-2', '1-3 años'."""
    if label is None:
        return None
    f = str(label).lower().replace("–", "-").replace("años", "")
    f = re.sub(r"(years?|yrs?|anos?|exp\.?|experiencia)", "", f).strip()
    if not f:
        return None
    m = re.fullmatch(rf"{_NUM}\s*-\s*{_NUM}", f)
    if m:
        return Interval(_num(m.group(1)), True, _num(m.group(2)), True, "intervalo")
    m = re.fullmatch(rf"(?:<|-|menos de)\s*{_NUM}", f)
    if m:
        return Interval(0.0, True, _num(m.group(1)), False, "límite abierto")
    m = re.fullmatch(rf"(?:>|\+|más de|mas de)\s*{_NUM}|{_NUM}\s*\+", f)
    if m:
        n = next(g for g in m.groups() if g)
        incl = "+" in f and not f.startswith(">")
        return Interval(_num(n), incl, INF, False, "límite abierto")
    return None


def _contains(outer: Interval, inner: Interval) -> bool:
    if inner.low is None or inner.high is None or inner.exactness == "aproximado":
        return False
    if outer.low is None or outer.high is None:
        return False
    lo_ok = inner.low > outer.low or (inner.low == outer.low and (outer.low_incl or not inner.low_incl))
    hi_ok = inner.high < outer.high or (inner.high == outer.high and (outer.high_incl or not inner.high_incl))
    return lo_ok and hi_ok


def _overlaps(a: Interval, b: Interval) -> bool:
    if None in (a.low, a.high, b.low, b.high):
        return False
    return not (b.high < a.low or b.low > a.high)


def assign_band(iv: Interval | None, bands: list[Band]) -> tuple[str | None, str]:
    """Asigna banda solo si el intervalo cabe íntegramente en una única banda."""
    if iv is None:
        return None, "sin dato de experiencia"
    if iv.exactness == "aproximado":
        return None, "aproximada: requiere validación"
    if iv.low is None:
        return None, "límite inferior desconocido: requiere validación"
    hits = [b for b in bands if b.interval is not None and _contains(b.interval, iv)]
    if len(hits) == 1:
        return hits[0].label, "asignada"
    if len(hits) > 1:
        return None, "bandas de la fuente solapadas: requiere validación"
    overlaps = [b for b in bands if b.interval is not None and _overlaps(b.interval, iv)]
    if overlaps:
        return None, "cruza límites de banda: no comparable por experiencia"
    return None, "fuera de las bandas o en un hueco entre bandas: no comparable"


def parse_band_set(text: str) -> list[Band]:
    """'<2; 2-5; >5' -> lista de bandas. Errores se elevan para mostrarlos al usuario."""
    bands = []
    for lbl in (x.strip() for x in re.split(r"[;|]", text or "")):
        if not lbl:
            continue
        iv = parse_band_label(lbl)
        if iv is None:
            raise ValueError(f"Banda no interpretable: {lbl!r}")
        bands.append(Band(lbl, iv))
    return bands
