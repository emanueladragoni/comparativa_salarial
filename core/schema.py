"""Lectura, mapeo de columnas y validación estructural del CSV de empleados."""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

# Campo lógico -> nombres de columna candidatos (comparación sin acentos ni mayúsculas).
FIELD_CANDIDATES: dict[str, list[str]] = {
    "departamento": ["departamento", "department", "dept"],
    "id": ["id empleado", "empleado", "id", "employee id", "employee"],
    "genero": ["genero", "género", "gender", "sexo"],
    "rol": ["rol", "role", "puesto", "position"],
    "experiencia": ["experiencia", "experience"],
    "salario_anterior": ["salario bruto anual fijo 2025", "salario 2025"],
    "ipc": ["ipc", "cpi"],
    "salario": ["salario bruto anual fijo 2026", "salario 2026"],
    "tecnologias": ["tecnologias", "tecnologías", "technologies", "tecnologia"],
}
REQUIRED_FIELDS = ["id", "departamento", "rol", "salario"]
OPTIONAL_FIELDS = ["genero", "experiencia", "salario_anterior", "ipc", "tecnologias"]
FIELD_LABELS = {
    "departamento": "Departamento", "id": "ID empleado", "genero": "Género", "rol": "Rol",
    "experiencia": "Experiencia", "salario_anterior": "Salario año anterior (opcional)",
    "ipc": "IPC (opcional)", "salario": "Columna salarial de análisis",
    "tecnologias": "Tecnologías (opcional)",
}


def _key(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def read_csv_bytes(data: bytes) -> pd.DataFrame:
    """Lee el CSV desde memoria, todo como texto (no se infieren tipos)."""
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("No se pudo decodificar el archivo.")
    try:
        delim = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
    df = pd.read_csv(io.StringIO(text), sep=delim, dtype=str, keep_default_na=False)
    return clean_column_names(df)


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df


def suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    keys = {_key(c): c for c in columns}
    mapping: dict[str, str | None] = {}
    for fld, cands in FIELD_CANDIDATES.items():
        mapping[fld] = next((keys[_key(c)] for c in cands if _key(c) in keys), None)
    return mapping


@dataclass
class StructureReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    empty_rows_removed: int = 0
    duplicate_ids: pd.DataFrame | None = None
    duplicate_rows: pd.DataFrame | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def is_blank(v: object) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def drop_fully_empty_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    mask = df.apply(lambda r: all(is_blank(v) for v in r), axis=1)
    return df.loc[~mask].copy(), int(mask.sum())


def validate_structure(df: pd.DataFrame, mapping: dict[str, str | None]) -> StructureReport:
    rep = StructureReport()
    if df.shape[1] == 0:
        rep.errors.append("El archivo no tiene columnas.")
        return rep
    dup_cols = df.columns[df.columns.duplicated()].tolist()
    if dup_cols:
        rep.errors.append(f"Columnas duplicadas tras limpiar espacios: {dup_cols}")
    for fld in REQUIRED_FIELDS:
        col = mapping.get(fld)
        if not col:
            rep.errors.append(f"Falta asignar la columna obligatoria «{FIELD_LABELS[fld]}».")
        elif col not in df.columns:
            rep.errors.append(f"La columna «{col}» no existe en el archivo.")
    used = [c for c in mapping.values() if c]
    if len(used) != len(set(used)):
        rep.errors.append("Una misma columna está asignada a varios campos.")
    if not mapping.get("genero"):
        rep.warnings.append("Sin columna de género: no se podrá hacer el análisis de equidad por género.")
    if not mapping.get("experiencia"):
        rep.warnings.append("Sin columna de experiencia: no se podrá segmentar por experiencia.")
    if rep.errors:
        return rep
    idc = mapping["id"]
    ids = df[idc].astype(str).str.strip()
    blanks = ids == ""
    if blanks.any():
        rep.warnings.append(f"{int(blanks.sum())} filas sin ID de empleado.")
    dup_mask = ids.duplicated(keep=False) & ~blanks
    rep.duplicate_ids = df.loc[dup_mask]
    rep.duplicate_rows = df.loc[df.duplicated(keep=False)]
    if dup_mask.any():
        rep.warnings.append(f"{int(dup_mask.sum())} filas comparten ID. No se eliminan: revísalas.")
    return rep


def department_key(s: object) -> str:
    """Clave de agrupación: cadena completa con espacios y mayúsculas normalizados."""
    return re.sub(r"\s+", " ", str(s)).strip().casefold()


def role_key(s: object) -> str:
    """Normalización confirmada: solo mayúsculas y espacios (sin corregir erratas)."""
    return re.sub(r"\s+", " ", str(s)).strip().upper()
