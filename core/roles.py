"""Equivalencias de roles internos y roles de mercado.

Dos tablas editables:
1. Catálogo interno: (rol_interno, tecnologia) -> grupo_equivalente + familia,
   especialidad y nivel. Cada rol empieza en su propio grupo: NO se agrupan
   puestos por similitud de nombre.
2. Correspondencias de mercado: grupo_equivalente -> (fuente, rol_original).
Solo las filas en estado «confirmada» intervienen en los cálculos.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from .schema import role_key

CATALOG_COLUMNS = ["rol_interno", "tecnologia", "grupo_equivalente", "familia_profesional",
                   "especialidad", "nivel_responsabilidad", "estado", "confirmado_por",
                   "fecha_confirmacion", "notas"]
MAPPING_COLUMNS = ["grupo_equivalente", "fuente", "edicion", "rol_original", "estado",
                   "confirmado_por", "fecha_confirmacion", "notas"]


def propose_catalog(roles: pd.Series, existing: pd.DataFrame | None = None) -> pd.DataFrame:
    """Una fila por rol distinto (mayúsculas/espacios unificados). Conserva filas existentes."""
    base = existing.copy() if existing is not None and len(existing) else pd.DataFrame(columns=CATALOG_COLUMNS)
    known = set(base["rol_interno"]) if len(base) else set()
    new = []
    for r in sorted({role_key(x) for x in roles if str(x).strip()}):
        if r in known:
            continue
        note = "Contiene anotación entre paréntesis: revisar" if "(" in r else ""
        new.append({"rol_interno": r, "tecnologia": "", "grupo_equivalente": r,
                    "familia_profesional": "", "especialidad": "",
                    "nivel_responsabilidad": "Sin definir", "estado": "propuesta",
                    "confirmado_por": "", "fecha_confirmacion": "", "notas": note})
    new_df = pd.DataFrame(new, columns=CATALOG_COLUMNS)
    if base.empty:
        return new_df.reset_index(drop=True)
    return pd.concat([base, new_df], ignore_index=True) if len(new_df) else base.reset_index(drop=True)


def propose_market_mapping(catalog: pd.DataFrame, refs: pd.DataFrame,
                           existing: pd.DataFrame | None = None) -> pd.DataFrame:
    """Propone solo coincidencias EXACTAS de denominación (mayúsculas/espacios). Requieren confirmación."""
    base = existing.copy() if existing is not None and len(existing) else pd.DataFrame(columns=MAPPING_COLUMNS)
    have = {(r.grupo_equivalente, r.fuente, r.rol_original) for r in base.itertuples()}
    new = []
    if len(refs):
        ref_roles = refs[["fuente", "edicion", "rol_original"]].drop_duplicates()
        groups = set(catalog["grupo_equivalente"]) if len(catalog) else set()
        for r in ref_roles.itertuples():
            g = role_key(r.rol_original)
            if g in groups and (g, r.fuente, r.rol_original) not in have:
                new.append({"grupo_equivalente": g, "fuente": r.fuente, "edicion": r.edicion,
                            "rol_original": r.rol_original, "estado": "propuesta",
                            "confirmado_por": "", "fecha_confirmacion": "",
                            "notas": "Coincidencia exacta de nombre: verificar tecnologías y nivel"})
    new_df = pd.DataFrame(new, columns=MAPPING_COLUMNS)
    if base.empty:
        return new_df.reset_index(drop=True)
    return pd.concat([base, new_df], ignore_index=True) if len(new_df) else base.reset_index(drop=True)


def confirm_rows(df: pd.DataFrame, idx: list[int], who: str) -> pd.DataFrame:
    df = df.copy()
    df.loc[idx, "estado"] = "confirmada"
    df.loc[idx, "confirmado_por"] = who
    df.loc[idx, "fecha_confirmacion"] = date.today().isoformat()
    return df


def validate_catalog(catalog: pd.DataFrame) -> list[str]:
    issues = []
    conf = catalog[catalog["estado"] == "confirmada"]
    dup = conf.duplicated(["rol_interno", "tecnologia"], keep=False)
    if dup.any():
        issues.append("Hay combinaciones rol+tecnología confirmadas más de una vez: "
                      + ", ".join(sorted(set(conf.loc[dup, "rol_interno"]))))
    for g, sub in conf.groupby("grupo_equivalente"):
        for col in ("familia_profesional", "especialidad", "nivel_responsabilidad"):
            if sub[col].nunique() > 1:
                issues.append(f"El grupo «{g}» mezcla valores distintos de {col}.")
    no_level = conf["nivel_responsabilidad"].isin(["", "Sin definir"])
    if no_level.any():
        issues.append(f"{int(no_level.sum())} equivalencias confirmadas sin nivel de responsabilidad.")
    return issues


def resolve_group(role: str, techs: list[str], catalog: pd.DataFrame) -> tuple[str | None, str]:
    """Grupo confirmado para un empleado. Las filas con tecnología exigen que esté validada."""
    rk = role_key(role)
    conf = catalog[(catalog["estado"] == "confirmada") & (catalog["rol_interno"] == rk)]
    if conf.empty:
        return None, "rol sin equivalencia confirmada"
    tset = {t.strip().upper() for t in techs if t.strip()}
    tech_col = conf["tecnologia"].fillna("").astype(str).str.strip()
    specific = conf[tech_col != ""]
    hits = specific[specific["tecnologia"].str.upper().isin(tset)]
    if len(hits) > 1 and hits["grupo_equivalente"].nunique() > 1:
        return None, "varias equivalencias por tecnología: requiere validación"
    if len(hits) >= 1:
        return hits.iloc[0]["grupo_equivalente"], "confirmada (rol + tecnología)"
    generic = conf[tech_col == ""]
    if len(generic) == 1:
        return generic.iloc[0]["grupo_equivalente"], "confirmada"
    if len(specific) and generic.empty:
        return None, "la equivalencia exige una tecnología no validada para este empleado"
    return None, "equivalencia ambigua"
