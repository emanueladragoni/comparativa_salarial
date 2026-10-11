"""Estadísticos descriptivos con fórmulas documentadas."""
from __future__ import annotations

import numpy as np
import pandas as pd

FORMULAS = {
    "n": "n = número de empleados con salario válido en el grupo.",
    "media": "media = (1/n) · Σ xᵢ",
    "mediana": "mediana = valor central de los salarios ordenados (promedio de los dos centrales si n es par).",
    "desv_tipica": "s = √( Σ (xᵢ − media)² / (n − 1) )  (desviación típica muestral; requiere n ≥ 2).",
    "p25/p75": "Percentiles 25 y 75 con interpolación lineal (método 'linear' de NumPy, tipo 7 de Hyndman-Fan).",
    "iqr": "IQR = P75 − P25 (dispersión robusta frente a valores extremos).",
    "cv": "CV = s / media · 100 (dispersión relativa, en %).",
    "brecha_media": "Brecha media (%) = (media_hombres − media_mujeres) / media_hombres · 100",
    "brecha_mediana": "Brecha mediana (%) = (mediana_hombres − mediana_mujeres) / mediana_hombres · 100",
    "dif_mercado": "Diferencia € = salario − referencia ; Diferencia % = (salario − referencia) / referencia · 100",
    "posicion_intervalo": "Posición en intervalo cerrado (%) = (salario − mín) / (máx − mín) · 100. "
                          "No se calcula si falta algún límite.",
    "dif_punto_medio": "Diferencia vs punto medio de banda interna: € = salario − PM ; % = (salario − PM) / PM · 100",
}


def describe(values: pd.Series) -> dict:
    x = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    n = len(x)
    out = {"n": n, "media": None, "mediana": None, "desv_tipica": None, "p25": None,
           "p75": None, "iqr": None, "cv_pct": None, "min": None, "max": None}
    if n == 0:
        return out
    out["media"] = float(np.mean(x))
    out["mediana"] = float(np.median(x))
    out["min"], out["max"] = float(x.min()), float(x.max())
    if n >= 2:
        sd = float(np.std(x, ddof=1))
        out["desv_tipica"] = sd
        out["cv_pct"] = sd / out["media"] * 100 if out["media"] else None
        p25, p75 = np.percentile(x, [25, 75], method="linear")
        out["p25"], out["p75"], out["iqr"] = float(p25), float(p75), float(p75 - p25)
    return out


def describe_groups(df: pd.DataFrame, by: list[str], value_col: str) -> pd.DataFrame:
    rows = []
    for keys, g in df.groupby(by, dropna=False, sort=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        rows.append({**dict(zip(by, keys)), **describe(g[value_col])})
    return pd.DataFrame(rows)


def pct_diff(value: float, ref: float) -> float | None:
    if ref in (None, 0) or value is None or pd.isna(ref) or pd.isna(value):
        return None
    return (value - ref) / ref * 100


def gap_pct(men: float | None, women: float | None) -> float | None:
    if men in (None, 0) or women is None:
        return None
    return (men - women) / men * 100
