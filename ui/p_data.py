import pandas as pd
import streamlit as st

from core.schema import FIELD_LABELS, OPTIONAL_FIELDS, REQUIRED_FIELDS, suggest_mapping
from core.session import uploader_nonce

from .common import read_uploaded_csv


def render(ctx):
    cmp = ctx.comparator
    st.header("1. Datos de empleados")
    st.caption("El archivo se procesa en memoria durante esta sesión. No se guarda en disco.")
    f = st.file_uploader("CSV de empleados", type=["csv"], key=f"emp_csv_{uploader_nonce(st.session_state)}")
    if f is None and cmp.raw is None:
        return
    if f is not None:
        try:
            df = read_uploaded_csv(f)
        except Exception as ex:  # noqa: BLE001
            st.error(f"No se pudo leer el archivo: {type(ex).__name__}")
            return
    else:
        df = cmp.raw
    st.write(f"Columnas detectadas (espacios sobrantes eliminados): {list(df.columns)}")

    sug = cmp.mapping or suggest_mapping(list(df.columns))
    opts = ["—"] + list(df.columns)
    st.subheader("Asignación de columnas")
    mapping = {}
    cols = st.columns(3)
    for i, fld in enumerate(REQUIRED_FIELDS + OPTIONAL_FIELDS):
        cur = sug.get(fld)
        sel = cols[i % 3].selectbox(FIELD_LABELS[fld] + (" *" if fld in REQUIRED_FIELDS else ""), opts,
                                    index=opts.index(cur) if cur in opts else 0, key=f"map_{fld}")
        mapping[fld] = None if sel == "—" else sel
    st.caption("Puedes elegir otra columna salarial para futuras revisiones (p. ej. «Salario 2027»).")

    if st.button("Validar y normalizar", type="primary"):
        res = cmp.load_employees(df, mapping)
        if not res.structure.ok:
            for e in res.structure.errors:
                st.error(e)
            return

    res = cmp.load_result
    if res is None or cmp.employees.empty:
        return
    e = cmp.employees
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros", len(e))
    c2.metric("Filas vacías eliminadas", res.structure.empty_rows_removed)
    c3.metric("Importes a revisar", res.money_issues)
    c4.metric("Sin salario", int((e["salario_estado"] == "vacío").sum()))
    for w in res.structure.warnings + res.warnings:
        st.warning(w)
    if res.structure.duplicate_ids is not None and len(res.structure.duplicate_ids):
        st.subheader("Posibles duplicados (no eliminados)")
        st.dataframe(res.structure.duplicate_ids, use_container_width=True)

    st.subheader("Importes ambiguos o inválidos")
    mr = cmp.money_review()
    if mr.empty:
        st.success("Todos los importes se han interpretado sin ambigüedad.")
    else:
        st.caption("Se conserva el valor original. Introduce el importe correcto solo tras comprobarlo.")
        ed = st.data_editor(mr, disabled=[c for c in mr.columns if c != "salario_validado_manual"],
                            key="money_editor", use_container_width=True)
        if st.button("Aplicar importes validados"):
            for r in ed.itertuples():
                v = r.salario_validado_manual
                cmp.resolve_money(r.fila_origen, None if pd.isna(v) else float(v))
            st.rerun()
    if "coherencia_ipc" in e.columns and (e["coherencia_ipc"] != "").any():
        with st.expander("Comprobación informativa: salario vs año anterior × (1+IPC)"):
            st.dataframe(e.loc[e["coherencia_ipc"] != "", ["fila_origen", "id", "salario_original", "coherencia_ipc"]],
                         use_container_width=True)
    with st.expander("Vista de datos normalizados (uso interno)"):
        st.dataframe(e.drop(columns=["genero"]), use_container_width=True)
