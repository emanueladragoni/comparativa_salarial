import pandas as pd
import streamlit as st

from core import roles as R
from core.config import EQUIVALENCE_STATES, RESPONSIBILITY_LEVELS
from core.session import uploader_nonce

from .common import need_data, read_uploaded_csv


def render(ctx):
    cmp = ctx.comparator
    st.header("3. Equivalencias de roles")
    if need_data(cmp):
        return
    st.info("Cada rol empieza en su propio grupo. Para tratar dos roles como equivalentes, asígnales "
            "el mismo «grupo_equivalente» y confírmalos. Si el rol depende de la tecnología, añade una fila "
            "por tecnología (solo se aplica a empleados con esa tecnología validada).")
    nonce = uploader_nonce(st.session_state)
    up = st.file_uploader("Importar tabla de equivalencias guardada (CSV)", type=["csv"], key=f"cat_up_{nonce}")
    if up is not None and st.button("Cargar equivalencias importadas"):
        imp = read_uploaded_csv(up)
        missing = [c for c in R.CATALOG_COLUMNS if c not in imp.columns]
        if missing:
            st.error(f"Faltan columnas: {missing}")
        else:
            cmp.set_catalog(R.propose_catalog(cmp.employees["rol"], imp[R.CATALOG_COLUMNS]))
            st.success("Importadas. Los roles nuevos se añaden como propuesta.")

    st.subheader("Roles internos")
    ed = st.data_editor(
        cmp.catalog, key="cat_editor", num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "estado": st.column_config.SelectboxColumn(options=EQUIVALENCE_STATES),
            "nivel_responsabilidad": st.column_config.SelectboxColumn(options=RESPONSIBILITY_LEVELS)},
        disabled=["confirmado_por", "fecha_confirmacion"])
    who = st.text_input("Tu nombre (se registra al confirmar)", key="who_roles")
    c1, c2 = st.columns(2)
    if c1.button("Guardar tabla de roles", type="primary"):
        ed = ed.reset_index(drop=True)
        newly = ed.index[(ed["estado"] == "confirmada") & (ed["confirmado_por"].fillna("") == "")].tolist()
        ed = R.confirm_rows(ed, newly, who or "usuaria") if newly else ed
        for issue in cmp.set_catalog(ed):
            st.warning(issue)
        st.success("Guardado.")
    c2.download_button("Descargar equivalencias (sin datos personales)",
                       cmp.catalog.to_csv(index=False).encode("utf-8-sig"), "equivalencias_roles.csv")

    st.subheader("Correspondencias con roles de mercado")
    if cmp.registry.versions:
        if st.button("Proponer coincidencias exactas de nombre"):
            cmp.propose_market_mapping()
        refs = cmp.registry.active_references(only_validated=False)
        with st.expander("Roles disponibles en las guías activas"):
            st.dataframe(refs[["fuente", "edicion", "categoria_fuente", "rol_original"]].drop_duplicates(),
                         use_container_width=True, hide_index=True)
    else:
        st.caption("Carga guías en «4. Guías de mercado» para mapear roles de mercado.")
    groups = sorted(set(cmp.catalog["grupo_equivalente"].dropna()))
    mp = st.data_editor(
        cmp.market_map, key="map_editor", num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={"estado": st.column_config.SelectboxColumn(options=EQUIVALENCE_STATES),
                       "grupo_equivalente": st.column_config.SelectboxColumn(options=groups)},
        disabled=["confirmado_por", "fecha_confirmacion"])
    if st.button("Guardar correspondencias de mercado"):
        mp = mp.reset_index(drop=True)
        newly = mp.index[(mp["estado"] == "confirmada") & (mp["confirmado_por"].fillna("") == "")].tolist()
        cmp.set_market_mapping(R.confirm_rows(mp, newly, who or "usuaria") if newly else mp)
        st.success("Guardado.")
    up2 = st.file_uploader("Importar correspondencias (CSV)", type=["csv"], key=f"map_up_{nonce}")
    if up2 is not None and st.button("Cargar correspondencias importadas"):
        imp = read_uploaded_csv(up2)
        if all(c in imp.columns for c in R.MAPPING_COLUMNS):
            cmp.set_market_mapping(pd.concat([cmp.market_map, imp[R.MAPPING_COLUMNS]]).drop_duplicates())
        else:
            st.error("Estructura no válida.")
    st.download_button("Descargar correspondencias", cmp.market_map.to_csv(index=False).encode("utf-8-sig"),
                       "correspondencias_mercado.csv")
