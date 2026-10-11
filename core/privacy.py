"""Control de divulgación para informes agregados compartibles.

- Supresión primaria: grupos con n < umbral pierden todos sus estadísticos.
- Supresión complementaria: si en un conjunto de grupos «hermanos» (p. ej. los
  dos géneros de un mismo grupo) solo uno queda suprimido, se suprime también el
  menor de los restantes para impedir deducirlo por diferencia con el total.
- Los informes compartibles nunca incluyen mínimo ni máximo (revelan individuos).
El umbral NO se aplica a la vista individual restringida.
"""
from __future__ import annotations

import pandas as pd

SUPPRESSED = "suprimido"
EXTREME_COLUMNS = ["min", "max"]
EXPORT_WARNING = (
    "Vas a exportar información salarial confidencial. El archivo saldrá del entorno controlado "
    "de la aplicación: guárdalo solo en ubicaciones corporativas autorizadas, no lo reenvíes "
    "fuera de los destinatarios previstos y elimínalo cuando deje de ser necesario."
)
INDIVIDUAL_EXPORT_WARNING = (
    "Esta exportación contiene datos INDIVIDUALES de empleados. Solo debe realizarla personal "
    "autorizado, con una finalidad legítima y documentada."
)


def suppress_small_groups(df: pd.DataFrame, n_col: str, threshold: int,
                          sibling_keys: list[str] | None = None) -> pd.DataFrame:
    out = df.copy()
    value_cols = [c for c in out.columns if c not in (sibling_keys or []) and c != n_col
                  and pd.api.types.is_numeric_dtype(out[c])]
    out["divulgacion"] = ""
    small = out[n_col].fillna(0) < threshold
    out.loc[small, "divulgacion"] = f"{SUPPRESSED} (n<{threshold})"
    if sibling_keys:
        for _, idx in out.groupby(sibling_keys, dropna=False).groups.items():
            idx = list(idx)
            sup = [i for i in idx if out.at[i, "divulgacion"]]
            rest = [i for i in idx if not out.at[i, "divulgacion"]]
            if len(sup) == 1 and rest:
                j = min(rest, key=lambda i: out.at[i, n_col])
                out.at[j, "divulgacion"] = f"{SUPPRESSED} (complementaria)"
    mask = out["divulgacion"] != ""
    out[value_cols] = out[value_cols].astype("float64")
    out.loc[mask, value_cols] = float("nan")
    out[n_col] = out[n_col].astype(object)
    out.loc[mask, n_col] = f"<{threshold}"
    return out


def shareable(df: pd.DataFrame, n_col: str, threshold: int,
              sibling_keys: list[str] | None = None) -> pd.DataFrame:
    cleaned = df.drop(columns=[c for c in EXTREME_COLUMNS if c in df.columns])
    return suppress_small_groups(cleaned, n_col, threshold, sibling_keys)
