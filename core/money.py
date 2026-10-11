"""Normalización de importes monetarios y porcentajes.

Principios:
- Se conserva siempre el texto original.
- Solo se asigna un valor cuando la interpretación es inequívoca.
- Los casos ambiguos (p. ej. "52,000" o "52.000" sin decimales) se marcan para
  revisión con sus interpretaciones candidatas; no se elige una automáticamente.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

_CURRENCY = re.compile(r"(€|eur(os)?|\beur\b)", re.IGNORECASE)
_SPACES = re.compile(r"[\s\u00a0\u202f']+")

STATUS_OK = "ok"
STATUS_EMPTY = "vacío"
STATUS_AMBIGUOUS = "ambiguo"
STATUS_INVALID = "inválido"


@dataclass(frozen=True)
class MoneyParse:
    original: str
    value: float | None
    status: str
    fmt: str          # "1,234.56" | "1.234,56" | "sin separadores" | "ambiguo" | ""
    note: str = ""


def _valid_grouping(int_part: str, sep: str) -> bool:
    groups = int_part.split(sep)
    if not groups[0] or len(groups[0]) > 3 or not groups[0].isdigit():
        return False
    return all(len(g) == 3 and g.isdigit() for g in groups[1:])


def parse_money(raw: object) -> MoneyParse:
    original = "" if raw is None or (isinstance(raw, float) and pd.isna(raw)) else str(raw)
    s = _CURRENCY.sub("", original)
    s = _SPACES.sub("", s).strip()
    if s == "":
        return MoneyParse(original, None, STATUS_EMPTY, "")
    negative = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()+")
    if not re.fullmatch(r"[0-9.,]+", s):
        return MoneyParse(original, None, STATUS_INVALID, "", "Contiene caracteres no numéricos")

    has_dot, has_comma = "." in s, "," in s
    sign = -1.0 if negative else 1.0

    if has_dot and has_comma:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        thou = "," if dec == "." else "."
        int_part, _, frac = s.rpartition(dec)
        if dec in int_part or not frac.isdigit() or not _valid_grouping(int_part, thou):
            return MoneyParse(original, None, STATUS_INVALID, "", "Separadores incoherentes")
        value = float(int_part.replace(thou, "") + "." + frac)
        fmt = "1,234.56" if dec == "." else "1.234,56"
        return MoneyParse(original, sign * value, STATUS_OK, fmt)

    if has_dot or has_comma:
        sep = "." if has_dot else ","
        parts = s.split(sep)
        if len(parts) > 2:  # varios separadores iguales => separador de miles
            if _valid_grouping(s, sep):
                return MoneyParse(original, sign * float(s.replace(sep, "")), STATUS_OK,
                                  "1,234,567" if sep == "," else "1.234.567")
            return MoneyParse(original, None, STATUS_INVALID, "", "Agrupación de miles inválida")
        int_part, frac = parts
        if len(frac) in (1, 2):
            return MoneyParse(original, sign * float(f"{int_part}.{frac}"), STATUS_OK,
                              f"decimal '{sep}'")
        if len(frac) == 3 and 1 <= len(int_part) <= 3:
            as_thousands = float(int_part + frac)
            as_decimal = float(f"{int_part}.{frac}")
            return MoneyParse(
                original, None, STATUS_AMBIGUOUS, "ambiguo",
                f"Puede ser {as_thousands:,.0f} (miles) o {as_decimal} (decimales). Requiere revisión.",
            )
        return MoneyParse(original, None, STATUS_INVALID, "", "Formato no reconocido")

    return MoneyParse(original, sign * float(s), STATUS_OK, "sin separadores")


def normalize_money_series(series: pd.Series) -> pd.DataFrame:
    """Devuelve original, valor, estado, formato y nota para cada celda."""
    parsed = [parse_money(v) for v in series.tolist()]
    return pd.DataFrame(
        {
            "original": [p.original for p in parsed],
            "valor": [p.value for p in parsed],
            "estado": [p.status for p in parsed],
            "formato": [p.fmt for p in parsed],
            "nota": [p.note for p in parsed],
        },
        index=series.index,
    )


def mixed_format_warning(norm: pd.DataFrame) -> str | None:
    fmts = {f for f in norm["formato"] if f in ("1,234.56", "1.234,56")}
    if len(fmts) > 1:
        return ("La columna mezcla formatos con coma y con punto decimal. "
                "Se han interpretado por celda; revisa los marcados.")
    return None


def parse_percent(raw: object) -> tuple[float | None, str]:
    """'3%' -> 0.03 ; '3' -> ambiguo (se señala) ; '0,03' -> ambiguo (se señala)."""
    original = "" if raw is None or (isinstance(raw, float) and pd.isna(raw)) else str(raw).strip()
    if original == "":
        return None, STATUS_EMPTY
    has_pct = original.endswith("%")
    s = original.rstrip("%").strip().replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None, STATUS_INVALID
    if has_pct:
        return v / 100.0, STATUS_OK
    return None, STATUS_AMBIGUOUS  # sin "%": no se sabe si es fracción o porcentaje
