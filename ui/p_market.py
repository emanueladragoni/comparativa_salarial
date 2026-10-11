import streamlit as st

from core.config import CONCEPTS, DEFAULT_MARKET_CONCEPT, EXPERIENCE_KINDS, STAT_TYPES
from core.market import VALIDATION_STATES, coerce_market, template_csv
from core.session import uploader_nonce
from extraction.ocr_local import ocr_available
from extraction.pdf_extractor import extract_pdf

from .common import read_uploaded_csv


def render(ctx):
    cmp = ctx.comparator
    st.header("4. Guías de mercado")
    st.caption("Las referencias de mercado no contienen datos de empleados. Descarga las versiones "
               "validadas en CSV para reutilizarlas en próximas revisiones sin tocar el código.")
    st.download_button("Descargar plantilla CSV de referencias", template_csv(), "plantilla_referencias_mercado.csv")
    nonce = uploader_nonce(st.session_state)
    tab_pdf, tab_csv, tab_ver = st.tabs(["Extraer de PDF", "Cargar CSV validado", "Versiones y ubicación"])

    with tab_pdf:
        ok, lang = ocr_available()
        st.caption(f"OCR local: {'disponible (' + lang + ')' if ok else 'no disponible — páginas sin texto requerirán plantilla CSV'}")
        pdfs = st.file_uploader("Guías PDF", type=["pdf"], accept_multiple_files=True, key=f"pdfs_{nonce}")
        for f in pdfs or []:
            with st.expander(f"📄 {f.name}", expanded=True):
                c1, c2, c3 = st.columns(3)
                fuente = c1.text_input("Fuente *", key=f"src_{f.name}")
                edicion = c2.text_input("Edición *", key=f"ed_{f.name}")
                pages = c3.text_input("Páginas (p. ej. 3-12, 15; vacío = todas)", key=f"pg_{f.name}")
                c4, c5, c6 = st.columns(3)
                concepto = c4.selectbox("Concepto retributivo", CONCEPTS,
                                        index=CONCEPTS.index(DEFAULT_MARKET_CONCEPT), key=f"cc_{f.name}")
                stat = c5.selectbox("Estadístico de los valores puntuales *", ["— selecciona —"] +
                                    [s for s in STAT_TYPES if s != "intervalo"], key=f"st_{f.name}",
                                    help="Indícalo según la metodología de la guía (p. ej. media, moda).")
                tipo_exp = c6.selectbox("Tipo de experiencia de la guía", EXPERIENCE_KINDS,
                                        index=EXPERIENCE_KINDS.index("puesto"), key=f"te_{f.name}")
                use_ocr = st.checkbox("Usar OCR local en páginas sin texto", value=ok, disabled=not ok,
                                      key=f"ocr_{f.name}")
                ready = bool(fuente and edicion and not stat.startswith("—"))
                if st.button("Extraer", key=f"x_{f.name}", disabled=not ready):
                    bar = st.progress(0.0)
                    res = extract_pdf(f.getvalue(), fuente, edicion, concepto, stat, pages or None, use_ocr,
                                      tipo_exp, progress=lambda p, t: bar.progress(p, t))
                    ctx.pending_extractions[f.name] = res
                res = ctx.pending_extractions.get(f.name)
                if res is None:
                    continue
                st.dataframe(res.pages, use_container_width=True, hide_index=True)
                if res.records.empty:
                    st.warning("No se ha podido extraer ninguna tabla de forma fiable. Usa la plantilla CSV.")
                    continue
                st.markdown("**Vista previa editable.** Revisa cada fila; marca `validada` las correctas. "
                            "Las alertas señalan posibles errores de la fuente o de la extracción: no se corrigen solas.")
                ed = st.data_editor(res.records, key=f"prev_{f.name}", num_rows="dynamic",
                                    use_container_width=True, height=420,
                                    column_config={"estado_validacion": st.column_config.SelectboxColumn(options=VALIDATION_STATES),
                                                   "tipo_estadistico": st.column_config.SelectboxColumn(options=STAT_TYPES)})
                cA, cB, cC = st.columns(3)
                if cA.button("Marcar todas como validadas", key=f"va_{f.name}"):
                    res.records = ed.assign(estado_validacion="validada")
                    st.rerun()
                if cB.button("Registrar como versión", key=f"reg_{f.name}", type="primary"):
                    data, errors = coerce_market(ed)
                    if errors:
                        for e in errors[:30]:
                            st.error(e)
                    else:
                        ids = cmp.registry.register(data, "pdf", f.name)
                        st.success(f"Versión registrada: {ids}")
                cC.download_button("Descargar CSV de esta extracción", ed.to_csv(index=False).encode("utf-8-sig"),
                                   f"{fuente}_{edicion}_referencias.csv".replace(" ", "_"), key=f"dl_{f.name}")

    with tab_csv:
        csvs = st.file_uploader("CSV de referencias validadas", type=["csv"], accept_multiple_files=True,
                                key=f"mcsv_{nonce}")
        for f in csvs or []:
            data, errors = coerce_market(read_uploaded_csv(f))
            st.write(f"**{f.name}** — {len(data)} filas, {int((data['estado_validacion'] == 'validada').sum())} validadas")
            for e in errors[:30]:
                st.error(e)
            if len(data) and (data["alerta_revision"] != "").any():
                st.warning(f"{int((data['alerta_revision'] != '').sum())} filas con alertas de revisión.")
            st.dataframe(data, use_container_width=True, height=250)
            if not errors and st.button(f"Registrar {f.name}", key=f"regc_{f.name}"):
                st.success(f"Versiones: {cmp.registry.register(data, 'csv', f.name)}")

    with tab_ver:
        summ = cmp.registry.summary()
        if summ.empty:
            st.info("Aún no hay versiones registradas.")
            return
        ed = st.data_editor(summ, disabled=[c for c in summ.columns if c != "activa"], hide_index=True,
                            key="ver_editor", use_container_width=True)
        if st.button("Aplicar versiones activas"):
            for r in ed.itertuples():
                cmp.registry.versions[r.version_id].activa = bool(r.activa)
        st.caption("Las comparaciones se muestran por fuente y versión; nunca se promedian automáticamente.")
        st.subheader("Ubicación de referencia")
        locs = cmp.registry.available_locations()
        st.caption("Los empleados no tienen ubicación en los datos. Selecciona explícitamente la ciudad "
                   "de las guías con desglose geográfico; la aplicación no asigna ninguna por defecto.")
        cur = cmp.settings.reference_location
        sel = st.selectbox("Ciudad de referencia", ["— sin seleccionar —"] + locs,
                           index=(locs.index(cur) + 1) if cur in locs else 0)
        cmp.settings.reference_location = None if sel.startswith("—") else sel
        cmp.settings.use_unlocated_references = st.checkbox(
            "Usar referencias sin ubicación (p. ej. guías nacionales)", value=cmp.settings.use_unlocated_references)
