"""Utilidades de interfaz compartidas (sin lógica de negocio)."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from core.privacy import EXPORT_WARNING, INDIVIDUAL_EXPORT_WARNING


def fmt_eur(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:,.0f} €".replace(",", ".")


def fmt_pct(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:+.1f} %".replace(".", ",")


def read_uploaded_csv(file) -> pd.DataFrame:
    from core.schema import read_csv_bytes
    return read_csv_bytes(file.getvalue())


def export_block(df: pd.DataFrame, filename: str, key: str, *, individual: bool = False,
                 authorized: bool = False, label: str = "Exportar") -> None:
    """Exportación solo por acción explícita. El archivo se genera en memoria."""
    if df is None or df.empty:
        return
    with st.expander(f"⬇️ {label}"):
        st.warning(EXPORT_WARNING)
        if individual:
            st.error(INDIVIDUAL_EXPORT_WARNING)
            if not authorized:
                st.info("Requiere iniciar sesión como usuaria autorizada.")
                return
        ok = st.checkbox("Confirmo que he leído la advertencia y que la exportación es necesaria.",
                         key=f"{key}_confirm")
        if individual:
            ok = ok and st.checkbox("Confirmo que exporto datos individuales con autorización.",
                                    key=f"{key}_confirm_ind")
        if ok:
            c1, c2 = st.columns(2)
            c1.download_button("CSV", df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"{filename}.csv", mime="text/csv", key=f"{key}_csv")
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as xw:
                df.to_excel(xw, index=False, sheet_name="datos")
            c2.download_button("Excel", buf.getvalue(), file_name=f"{filename}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key=f"{key}_xlsx")


def need_data(cmp) -> bool:
    if cmp.employees.empty:
        st.info("Primero carga y valida el CSV de empleados en «1. Datos de empleados».")
        return True
    return False
