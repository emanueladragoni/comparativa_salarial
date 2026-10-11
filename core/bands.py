"""Propuestas de bandas salariales internas, aprobación y versionado inmutable.

Distinción fundamental:
- Rango publicado: lo que dice la guía (se conserva tal cual en las referencias).
- Banda interna propuesta: decisión de diseño de la empresa basada en esos datos.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pandas as pd

from .config import POINT_STAT_TYPES

BAND_COLUMNS = [
    "band_id", "version", "grupo_equivalente", "roles_internos", "familia_profesional",
    "especialidad", "nivel_responsabilidad", "banda_experiencia", "ubicacion",
    "equivalencias_mercado", "limite_inferior", "punto_medio", "limite_superior",
    "origen_limites", "metodo_calculo", "criterios_seleccion", "fuentes_referencias",
    "versiones_mercado", "concepto_retributivo", "estado", "faltan", "creada",
    "aprobada_por", "rol_aprobador", "fecha_aprobacion", "sustituye_version",
]
NUMERIC = ("limite_inferior", "punto_medio", "limite_superior")
METHODS = {
    "intervalo_publicado": "Límites = intervalo cerrado publicado por una única fuente. "
                           "Punto medio = (inferior + superior) / 2, cálculo aritmético de la banda interna "
                           "(no es una mediana de mercado).",
    "valor_con_amplitud": "Punto medio = valor de referencia de una única fuente. Límites = PM · (1 ∓ amplitud). "
                          "Los límites son una DECISIÓN DE DISEÑO, no datos publicados.",
    "combinacion_media": "Punto medio = media aritmética de los valores puntuales seleccionados "
                         "(solo fuentes compatibles). Límites = PM · (1 ∓ amplitud): decisión de diseño.",
    "combinacion_mediana": "Punto medio = mediana de los valores puntuales seleccionados "
                           "(solo fuentes compatibles). Límites = PM · (1 ∓ amplitud): decisión de diseño.",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v) == ""


def _src(r) -> str:
    return (f"{r['fuente']} {r['edicion']} p.{r['pagina'] or '?'} · «{r['rol_original']}» · "
            f"{r['ubicacion'] or 'sin ubicación'} · {r['banda_experiencia_original'] or 'sin banda'} · "
            f"{r['tipo_estadistico']}")


def compatibility_issues(refs: pd.DataFrame) -> list[str]:
    """Criterios para combinar fuentes: mismo concepto, ubicación, banda y estadístico puntual."""
    issues = []
    for col, label in [("concepto_retributivo", "conceptos retributivos"),
                       ("ubicacion", "ubicaciones"),
                       ("banda_experiencia_norm", "bandas de experiencia")]:
        if refs[col].nunique(dropna=False) > 1:
            issues.append(f"No se combinan {label} distintos: {sorted(refs[col].astype(str).unique())}")
    if refs["nivel_responsabilidad"].nunique(dropna=False) > 1:
        issues.append("No se combinan niveles de responsabilidad distintos.")
    if not refs["tipo_estadistico"].isin(POINT_STAT_TYPES).all():
        issues.append("Solo se combinan valores puntuales; los intervalos se usan por separado.")
    if (~refs["disponible"].astype(bool)).any():
        issues.append("Hay referencias no disponibles (NA) en la selección.")
    return issues


def build_band(group_info: dict, refs: pd.DataFrame, method: str,
               amplitude_pct: float | None, extra_criteria: str = "") -> dict:
    """Crea una propuesta. Nunca inventa límites: si faltan datos queda 'pendiente de definición'."""
    rec = {c: "" for c in BAND_COLUMNS}
    rec.update({
        "band_id": uuid.uuid4().hex[:10], "version": 1, "creada": _now(),
        "grupo_equivalente": group_info.get("grupo_equivalente", ""),
        "roles_internos": group_info.get("roles_internos", ""),
        "familia_profesional": group_info.get("familia_profesional", ""),
        "especialidad": group_info.get("especialidad", ""),
        "nivel_responsabilidad": group_info.get("nivel_responsabilidad", ""),
        "metodo_calculo": METHODS.get(method, method),
        "criterios_seleccion": extra_criteria,
        "limite_inferior": None, "punto_medio": None, "limite_superior": None,
    })
    missing: list[str] = []
    if refs is None or refs.empty:
        missing.append("referencias de mercado validadas con equivalencia confirmada")
        rec.update(estado="pendiente de definición", faltan="; ".join(missing))
        return rec
    rec["fuentes_referencias"] = " || ".join(_src(r) for _, r in refs.iterrows())
    rec["equivalencias_mercado"] = "; ".join(sorted(set(refs["fuente"] + ": " + refs["rol_original"])))
    rec["versiones_mercado"] = "; ".join(sorted(set(refs["version_id"])))
    rec["ubicacion"] = "; ".join(sorted(set(refs["ubicacion"].replace("", "sin ubicación"))))
    rec["banda_experiencia"] = "; ".join(sorted(set(refs["banda_experiencia_original"].replace("", "sin banda"))))
    rec["concepto_retributivo"] = "; ".join(sorted(set(refs["concepto_retributivo"])))

    if (~refs["disponible"].astype(bool)).all():
        missing.append("valor publicado (la guía indica NA)")
    elif method == "intervalo_publicado":
        if len(refs) != 1 or refs.iloc[0]["tipo_estadistico"] != "intervalo":
            missing.append("un único intervalo publicado")
        else:
            r = refs.iloc[0]
            if _missing(r["valor_min"]):
                missing.append("límite inferior publicado")
            if _missing(r["valor_max"]):
                missing.append("límite superior publicado (intervalo abierto)")
            if not missing:
                lo, hi = float(r["valor_min"]), float(r["valor_max"])
                rec.update(limite_inferior=lo, limite_superior=hi, punto_medio=(lo + hi) / 2,
                           origen_limites="Límites publicados en la guía; punto medio calculado")
    elif method in ("valor_con_amplitud", "combinacion_media", "combinacion_mediana"):
        if method == "valor_con_amplitud" and len(refs) != 1:
            missing.append("seleccionar una única referencia")
        if method != "valor_con_amplitud":
            issues = compatibility_issues(refs)
            if len(refs) < 2:
                missing.append("al menos dos referencias compatibles para combinar")
            missing.extend(issues)
        if not refs["tipo_estadistico"].isin(POINT_STAT_TYPES).all():
            missing.append("valor puntual (media/moda/mediana/referencia)")
        if amplitude_pct is None:
            missing.append("amplitud de banda definida por la usuaria")
        if not missing:
            vals = refs["valor"].astype(float)
            pm = float(vals.iloc[0] if method == "valor_con_amplitud"
                       else (vals.mean() if method == "combinacion_media" else vals.median()))
            a = amplitude_pct / 100
            rec.update(punto_medio=pm, limite_inferior=pm * (1 - a), limite_superior=pm * (1 + a),
                       origen_limites=f"DECISIÓN DE DISEÑO: amplitud ±{amplitude_pct:g}% sobre el punto medio")
    else:
        missing.append(f"método desconocido: {method}")

    rec["estado"] = "pendiente de definición" if missing else "pendiente de validación"
    rec["faltan"] = "; ".join(dict.fromkeys(missing))
    return rec


class BandStore:
    """Registro de bandas. Las versiones aprobadas son inmutables."""

    def __init__(self, df: pd.DataFrame | None = None):
        self.df = df.copy() if df is not None else pd.DataFrame(columns=BAND_COLUMNS)

    def add(self, rec: dict) -> None:
        new = pd.DataFrame([rec], columns=BAND_COLUMNS).astype(object)
        self.df = new if self.df.empty else pd.concat([self.df.astype(object), new], ignore_index=True)

    def _locate(self, band_id: str, version: int) -> int:
        idx = self.df.index[(self.df["band_id"] == band_id) & (self.df["version"].astype(int) == int(version))]
        if len(idx) != 1:
            raise KeyError("Banda/versión no encontrada")
        return idx[0]

    def edit(self, band_id: str, version: int, changes: dict) -> tuple[str, int]:
        """Editar una aprobada crea una NUEVA versión pendiente; nunca sobrescribe."""
        i = self._locate(band_id, version)
        row = self.df.loc[i].to_dict()
        protected = {"band_id", "version", "estado", "aprobada_por", "fecha_aprobacion"}
        changes = {k: v for k, v in changes.items() if k not in protected}
        if row["estado"] == "aprobada":
            new = {**row, **changes}
            new_v = int(self.df.loc[self.df["band_id"] == band_id, "version"].astype(int).max()) + 1
            new.update(version=new_v, estado="pendiente de validación", aprobada_por="",
                       rol_aprobador="", fecha_aprobacion="", sustituye_version=str(version), creada=_now())
            self.add(new)
            return band_id, new_v
        for k, v in changes.items():
            self.df.at[i, k] = v
        self._recompute_state(i)
        return band_id, int(version)

    def _recompute_state(self, i: int) -> None:
        complete = not any(_missing(self.df.at[i, c]) for c in NUMERIC)
        if complete and self.df.at[i, "estado"] == "pendiente de definición":
            self.df.at[i, "estado"] = "pendiente de validación"
            self.df.at[i, "faltan"] = ""

    def approve(self, band_id: str, version: int, name: str, role: str) -> None:
        if not name.strip() or not role.strip():
            raise ValueError("Indica nombre y rol de quien aprueba.")
        i = self._locate(band_id, version)
        if self.df.at[i, "estado"] != "pendiente de validación":
            raise ValueError("Solo pueden aprobarse bandas completas pendientes de validación.")
        lo, pm, hi = (float(self.df.at[i, c]) for c in NUMERIC)
        if not lo <= pm <= hi:
            raise ValueError("Límites incoherentes: inferior ≤ punto medio ≤ superior.")
        self.df.at[i, "estado"] = "aprobada"
        self.df.at[i, "aprobada_por"] = name.strip()
        self.df.at[i, "rol_aprobador"] = role.strip()
        self.df.at[i, "fecha_aprobacion"] = _now()

    def approved_for(self, group: str) -> pd.DataFrame:
        d = self.df[(self.df["grupo_equivalente"] == group) & (self.df["estado"] == "aprobada")]
        if d.empty:
            return d
        d = d.assign(_v=d["version"].astype(int)).sort_values("_v")
        return d.groupby("band_id").tail(1).drop(columns="_v")

    def export_csv(self) -> bytes:
        return self.df.to_csv(index=False).encode("utf-8")

    @classmethod
    def from_csv(cls, df: pd.DataFrame) -> "BandStore":
        missing = [c for c in BAND_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Faltan columnas: {missing}")
        df = df[BAND_COLUMNS].copy()
        for c in NUMERIC:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["version"] = df["version"].astype(int)
        return cls(df.fillna({c: "" for c in BAND_COLUMNS if c not in NUMERIC}))


def position_vs_band(salary: float, band: pd.Series) -> dict:
    lo, pm, hi = (float(band[c]) for c in NUMERIC)
    pos = "por debajo" if salary < lo else ("por encima" if salary > hi else "dentro")
    return {"posicion_banda": pos, "dif_vs_punto_medio_eur": salary - pm,
            "dif_vs_punto_medio_pct": (salary - pm) / pm * 100 if pm else None,
            "limite_inferior": lo, "punto_medio": pm, "limite_superior": hi}
