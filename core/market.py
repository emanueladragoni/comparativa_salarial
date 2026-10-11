"""Referencias de mercado: esquema, validación, versiones y compatibilidad.

Formato *largo*: una fila = un dato publicado (fuente × rol × ubicación × banda).
Las referencias no contienen datos de empleados; pueden exportarse y reutilizarse.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .config import POINT_STAT_TYPES, STAT_TYPES
from .experience import parse_band_label

MARKET_COLUMNS = [
    "fuente", "edicion", "pagina", "rol_original", "categoria_fuente", "ubicacion",
    "banda_experiencia_original", "tipo_experiencia", "moneda", "unidad",
    "concepto_retributivo", "tipo_estadistico", "valor", "valor_min", "valor_max",
    "limite_abierto", "disponible", "valor_original", "variable_original",
    "notas_fuente", "alerta_revision", "estado_validacion",
]
REQUIRED_MARKET = ["fuente", "edicion", "rol_original", "moneda", "unidad",
                   "concepto_retributivo", "tipo_estadistico", "disponible"]
LIMIT_OPEN_VALUES = ["", "inferior", "superior"]
VALIDATION_STATES = ["pendiente", "validada", "descartada"]

TEMPLATE_HELP = {
    "fuente": "Nombre de la guía (p. ej. Hays).",
    "edicion": "Edición/año publicado (p. ej. 2026).",
    "pagina": "Página del PDF de origen.",
    "rol_original": "Denominación exacta en la guía, sin corregir.",
    "categoria_fuente": "Sección/familia en la guía (opcional).",
    "ubicacion": "Ciudad tal como aparece; vacío si la guía no indica ubicación.",
    "banda_experiencia_original": "Texto exacto de la banda (p. ej. '<2 años', '2-5', '8+'). Vacío si no hay.",
    "tipo_experiencia": "puesto | total | no especificada",
    "moneda": "EUR",
    "unidad": "EUR/año (valores ya normalizados a euros anuales)",
    "concepto_retributivo": "total bruto anual | fijo bruto anual | no especificado",
    "tipo_estadistico": "media | moda | mediana | valor_referencia | intervalo",
    "valor": "Valor puntual (solo si tipo_estadistico no es intervalo).",
    "valor_min": "Límite inferior publicado (solo intervalos). Vacío si no existe.",
    "valor_max": "Límite superior publicado (solo intervalos). Vacío si es abierto.",
    "limite_abierto": "'' | inferior | superior (p. ej. '>65K' -> superior).",
    "disponible": "true | false (false para NA, N.A, '-').",
    "valor_original": "Texto literal de la celda en la guía.",
    "variable_original": "Columna de variable/bonus, literal (no se mezcla con el salario).",
    "notas_fuente": "Notas al pie u observaciones de la guía.",
    "alerta_revision": "Posibles errores detectados; NO se corrigen.",
    "estado_validacion": "pendiente | validada | descartada",
}


def empty_market_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=MARKET_COLUMNS)


def template_csv() -> bytes:
    """Plantilla vacía con fila de ayuda comentada (se ignora al cargar)."""
    help_row = {c: f"# {TEMPLATE_HELP[c]}" for c in MARKET_COLUMNS}
    return pd.DataFrame([help_row], columns=MARKET_COLUMNS).to_csv(index=False).encode("utf-8")


def _to_bool(v) -> bool | None:
    s = str(v).strip().lower()
    if s in ("true", "1", "sí", "si", "yes", "verdadero"):
        return True
    if s in ("false", "0", "no", "falso"):
        return False
    return None


def _to_float(v) -> float | None:
    if v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(" ", ""))
    except ValueError:
        return None


def coerce_market(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Normaliza tipos y valida. Devuelve (datos, errores). No corrige la fuente."""
    errors: list[str] = []
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    if len(df) and df.iloc[:, 0].astype(str).str.startswith("#").any():
        df = df.loc[~df.iloc[:, 0].astype(str).str.startswith("#")]
    missing = [c for c in REQUIRED_MARKET if c not in df.columns]
    if missing:
        return empty_market_frame(), [f"Faltan columnas obligatorias: {missing}"]
    for c in MARKET_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[MARKET_COLUMNS].copy()
    for c in ("valor", "valor_min", "valor_max"):
        df[c] = pd.Series([_to_float(v) for v in df[c]], index=df.index, dtype=object)
    df["disponible"] = df["disponible"].map(_to_bool)
    for c in ["fuente", "edicion", "rol_original", "ubicacion", "banda_experiencia_original",
              "tipo_experiencia", "moneda", "unidad", "concepto_retributivo", "tipo_estadistico",
              "limite_abierto", "valor_original", "variable_original", "notas_fuente",
              "alerta_revision", "estado_validacion", "categoria_fuente", "pagina"]:
        df[c] = df[c].fillna("").astype(str).str.strip().replace({"nan": "", "None": ""})
    df.loc[df["estado_validacion"] == "", "estado_validacion"] = "pendiente"
    df = df.reset_index(drop=True)

    for i, r in df.iterrows():
        alerts = [a for a in str(r["alerta_revision"]).split(" | ") if a]
        loc = f"Fila {i + 2}"
        if r["tipo_estadistico"] not in STAT_TYPES:
            errors.append(f"{loc}: tipo_estadistico «{r['tipo_estadistico']}» no válido.")
        if r["disponible"] is None:
            errors.append(f"{loc}: 'disponible' debe ser true/false.")
        if r["limite_abierto"] not in LIMIT_OPEN_VALUES:
            errors.append(f"{loc}: limite_abierto debe ser vacío, 'inferior' o 'superior'.")
        if r["estado_validacion"] not in VALIDATION_STATES:
            errors.append(f"{loc}: estado_validacion no válido.")
        if r["disponible"]:
            if r["tipo_estadistico"] in POINT_STAT_TYPES and r["valor"] is None:
                errors.append(f"{loc}: falta 'valor' para un estadístico puntual.")
            if r["tipo_estadistico"] == "intervalo":
                if r["valor_min"] is None and r["valor_max"] is None:
                    errors.append(f"{loc}: intervalo sin límites.")
                if r["limite_abierto"] == "" and (r["valor_min"] is None or r["valor_max"] is None):
                    errors.append(f"{loc}: intervalo cerrado con un límite vacío; indica limite_abierto.")
                if (r["valor_min"] is not None and r["valor_max"] is not None
                        and r["valor_min"] > r["valor_max"]):
                    alerts.append("Mínimo mayor que máximo en la fuente")
        if r["banda_experiencia_original"] and parse_band_label(r["banda_experiencia_original"]) is None:
            alerts.append("Banda de experiencia no interpretable automáticamente")
        if r["moneda"] != "EUR":
            alerts.append("Moneda distinta de EUR: no comparable")
        if r["unidad"] != "EUR/año":
            alerts.append("Unidad distinta de EUR/año: no comparable")
        for v in (r["valor"], r["valor_min"], r["valor_max"]):
            if v is not None and not (5_000 <= v <= 1_000_000):
                alerts.append("Valor fuera del rango plausible (5.000-1.000.000 €)")
                break
        df.at[i, "alerta_revision"] = " | ".join(dict.fromkeys(alerts))
    df = flag_non_monotonic(df)
    return df, errors


def _ref_point(r) -> float | None:
    if r["tipo_estadistico"] in POINT_STAT_TYPES:
        return r["valor"]
    return r["valor_min"]


def flag_non_monotonic(df: pd.DataFrame) -> pd.DataFrame:
    """Señala si a más experiencia el valor publicado disminuye (posible errata)."""
    df = df.copy()
    keys = ["fuente", "edicion", "rol_original", "ubicacion", "tipo_estadistico"]
    for _, g in df.groupby(keys, dropna=False):
        rows = []
        for i, r in g.iterrows():
            iv = parse_band_label(r["banda_experiencia_original"]) if r["banda_experiencia_original"] else None
            pt = _ref_point(r)
            if iv is not None and iv.low is not None and pt is not None and r["disponible"]:
                rows.append((iv.low, pt, i))
        rows.sort()
        for (l1, v1, i1), (l2, v2, i2) in zip(rows, rows[1:]):
            if v2 < v1:
                msg = "Valor menor que en la banda de experiencia inferior (posible error de la fuente)"
                cur = df.at[i2, "alerta_revision"]
                if msg not in cur:
                    df.at[i2, "alerta_revision"] = (cur + " | " if cur else "") + msg
    return df


@dataclass
class MarketVersion:
    version_id: str
    fuente: str
    edicion: str
    origen: str             # "pdf" | "csv"
    archivo: str
    cargada: str
    data: pd.DataFrame
    activa: bool = True


@dataclass
class MarketRegistry:
    """Versiones de referencias de mercado de la sesión (en memoria)."""
    versions: dict[str, MarketVersion] = field(default_factory=dict)

    def register(self, df: pd.DataFrame, origen: str, archivo: str) -> list[str]:
        ids = []
        for (fuente, edicion), g in df.groupby(["fuente", "edicion"], dropna=False):
            digest = hashlib.sha256(g.to_csv(index=False).encode()).hexdigest()[:8]
            vid = f"{fuente} · {edicion} · {digest}"
            if vid not in self.versions:
                self.versions[vid] = MarketVersion(vid, fuente, edicion, origen, archivo,
                                                   datetime.now().strftime("%Y-%m-%d %H:%M"),
                                                   g.reset_index(drop=True))
            ids.append(vid)
        return ids

    def active_references(self, only_validated: bool = True) -> pd.DataFrame:
        frames = []
        for v in self.versions.values():
            if not v.activa:
                continue
            d = v.data.copy()
            d["version_id"] = v.version_id
            frames.append(d)
        if not frames:
            return empty_market_frame().assign(version_id=[])
        out = pd.concat(frames, ignore_index=True)
        if only_validated:
            out = out[out["estado_validacion"] == "validada"]
        return out.reset_index(drop=True)

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "version_id": v.version_id, "fuente": v.fuente, "edicion": v.edicion,
            "origen": v.origen, "archivo": v.archivo, "cargada": v.cargada,
            "filas": len(v.data), "validadas": int((v.data["estado_validacion"] == "validada").sum()),
            "activa": v.activa,
        } for v in self.versions.values()])

    def available_locations(self) -> list[str]:
        refs = self.active_references(only_validated=False)
        return sorted({u for u in refs["ubicacion"] if u})
