import pandas as pd
import streamlit as st

from core.bands import METHODS, BandStore, build_band
from core.session import uploader_nonce

from .common import read_uploaded_csv


def _num(v):
    return None if v is None or v == "" or pd.isna(v) else float(v)


def render(ctx):
    cmp = ctx.comparator
    st.header("7. Bandas salariales")
    st.info("Los rangos publicados por las guías se conservan en las referencias. Aquí se crean **bandas internas "
            "propuestas**, que son decisiones de diseño. Una banda aprobada nunca se sobrescribe: editarla o "
            "regenerarla crea una versión nueva pendiente de validación.")
    nonce = uploader_nonce(st.session_state)
    up = st.file_uploader("Importar bandas guardadas (CSV)", type=["csv"], key=f"bands_up_{nonce}")
    if up is not None and st.button("Cargar bandas"):
        try:
            imported = BandStore.from_csv(read_uploaded_csv(up))
            merged = imported.df if cmp.bands.df.empty else pd.concat([cmp.bands.df, imported.df])
            cmp.bands = BandStore(merged.drop_duplicates(["band_id", "version"]).reset_index(drop=True))
            st.success("Bandas importadas.")
        except ValueError as ex:
            st.error(str(ex))

    groups = (sorted(set(cmp.catalog.loc[cmp.catalog["estado"] == "confirmada", "grupo_equivalente"]))
              if len(cmp.catalog) else [])
    st.subheader("Nueva propuesta")
    if not groups:
        st.caption("Confirma equivalencias de roles para poder proponer bandas.")
    else:
        g = st.selectbox("Grupo equivalente", groups)
        cands = cmp.band_candidates(g)
        if cands.empty:
            st.warning("Banda pendiente de definición: no hay referencias validadas con equivalencia confirmada.")
        else:
            show = ["fuente", "edicion", "pagina", "rol_original", "ubicacion", "banda_experiencia_original",
                    "concepto_retributivo", "tipo_estadistico", "valor", "valor_min", "valor_max",
                    "limite_abierto", "disponible", "alerta_revision"]
            cands = cands.reset_index(drop=True)
            st.dataframe(cands[show], use_container_width=True)
            sel = st.multiselect("Filas de referencia a utilizar", cands.index.tolist())
            method = st.selectbox("Método", list(METHODS), format_func=lambda m: f"{m}: {METHODS[m]}")
            amp = st.number_input("Amplitud ± % (obligatoria si hay valor puntual; sin valor por defecto)",
                                  min_value=0.0, max_value=100.0, value=None, step=1.0)
            crit = st.text_area("Criterios de selección/combinación")
            if st.button("Crear propuesta", type="primary"):
                rec = build_band(cmp.group_info(g), cands.loc[sel], method, amp, crit)
                cmp.bands.add(rec)
                msg = f"Estado: {rec['estado']}" + (f" — falta: {rec['faltan']}" if rec["faltan"] else "")
                (st.warning if rec["estado"] == "pendiente de definición" else st.success)(msg)
    miss = cmp.groups_without_band_data()
    if not miss.empty:
        with st.expander(f"Grupos con banda pendiente de definición ({len(miss)})"):
            st.dataframe(miss, use_container_width=True, hide_index=True)

    st.subheader("Registro de bandas")
    df = cmp.bands.df
    if df.empty:
        st.caption("Sin bandas.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    keys = [f"{r.band_id} v{r.version} · {r.grupo_equivalente} · {r.estado}" for r in df.itertuples()]
    pick = st.selectbox("Seleccionar banda/versión", keys)
    bid, ver = pick.split(" · ")[0].split(" v")
    row = df[(df["band_id"] == bid) & (df["version"].astype(int) == int(ver))].iloc[0]
    c1, c2, c3 = st.columns(3)
    lo = c1.number_input("Límite inferior", value=_num(row["limite_inferior"]))
    pm = c2.number_input("Punto medio", value=_num(row["punto_medio"]))
    hi = c3.number_input("Límite superior", value=_num(row["limite_superior"]))
    why = st.text_input("Motivo del cambio (se añade a criterios)")
    if st.button("Guardar edición (si está aprobada se crea nueva versión)"):
        changes = {"limite_inferior": lo, "punto_medio": pm, "limite_superior": hi}
        if why:
            changes["criterios_seleccion"] = f"{row['criterios_seleccion']} | Edición manual: {why}"
            changes["origen_limites"] = f"{row['origen_limites']} | Ajuste manual (decisión de diseño)"
        b, v = cmp.bands.edit(bid, int(ver), changes)
        st.success(f"Guardado como {b} v{v}.")
        st.rerun()
    a1, a2 = st.columns(2)
    name = a1.text_input("Aprobado por (nombre)")
    role = a2.selectbox("Rol de quien aprueba", ["HR", "Department Head", "Managing Director"])
    if st.button("Aprobar versión seleccionada"):
        try:
            cmp.bands.approve(bid, int(ver), name, role)
            st.success("Aprobada.")
            st.rerun()
        except ValueError as ex:
            st.error(str(ex))
    st.download_button("Exportar bandas (sin datos personales)", cmp.bands.export_csv(), "bandas_salariales.csv")
