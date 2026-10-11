import streamlit as st

from core.privacy import shareable
from core.stats import FORMULAS

from .common import export_block, need_data


def render(ctx):
    cmp = ctx.comparator
    st.header("5. Análisis agregado")
    if need_data(cmp):
        return
    s = cmp.settings
    authorized = ctx.auth.is_authorized()
    mode = "compartible"
    if authorized:
        mode = st.radio("Vista", ["compartible", "interna completa (autorizada)"], horizontal=True)
    k = s.min_group_size
    st.caption(f"Vista compartible: grupos con n < {k} suprimidos (con supresión complementaria) y sin mínimos ni máximos.")
    with st.expander("Fórmulas utilizadas"):
        for name, f in FORMULAS.items():
            st.markdown(f"- **{name}**: `{f}`")

    def show(df, key, siblings=None):
        if df is None or df.empty:
            st.info("Sin datos suficientes (revisa equivalencias confirmadas, validaciones y referencias).")
            return
        out = df if mode != "compartible" else shareable(df, "n", k, siblings)
        st.dataframe(out, use_container_width=True, hide_index=True)
        export_block(shareable(df, "n", k, siblings), key, key, label="Exportar versión compartible")

    t1, t2, t3, t4, t5 = st.tabs(["Dentro del departamento", "Entre departamentos", "Por experiencia",
                                  "Mercado (por fuente)", "Equidad por género"])
    with t1:
        show(cmp.compare_within_departments(), "interno_departamento", ["grupo"])
    with t2:
        show(cmp.compare_across_departments(), "entre_departamentos", ["grupo"])
    with t3:
        s.internal_experience_bands = st.text_input(
            "Bandas de experiencia internas (separadas por ';')", value=s.internal_experience_bands,
            placeholder="p. ej. <2; 2-5; >5",
            help="Decisión metodológica: defínelas tú. Se usa experiencia en el puesto validada.")
        try:
            show(cmp.compare_by_experience(), "por_experiencia", ["grupo"])
        except ValueError as ex:
            st.error(str(ex))
    with t4:
        if not s.allow_concept_mismatch:
            st.warning("Las guías registradas como «total bruto anual» no se comparan con el salario fijo "
                       "mientras no actives la opción en la barra lateral.")
        agg = cmp.compare_market_aggregated()
        if agg.empty:
            st.info("Sin comparaciones de mercado compatibles.")
        else:
            out = agg if mode != "compartible" else cmp.market_shareable()
            for fuente, g in out.groupby("fuente"):
                st.markdown(f"**{fuente}**")
                st.dataframe(g.dropna(axis=1, how="all"), use_container_width=True, hide_index=True)
            st.caption("Puntuales: diferencia de la mediana interna frente a la referencia y mediana de las diferencias "
                       "individuales. Intervalos: recuento por debajo / dentro / por encima. Sin punto medio de intervalo.")
            export_block(cmp.market_shareable(), "mercado_agregado", "exp_mkt", label="Exportar versión compartible")
    with t5:
        vals = sorted(set(cmp.employees["genero"]) - {""})
        c1, c2 = st.columns(2)
        s.women_values = c1.multiselect("Valores que corresponden a mujeres", vals,
                                        default=[v for v in s.women_values if v in vals])
        s.men_values = c2.multiselect("Valores que corresponden a hombres", vals,
                                      default=[v for v in s.men_values if v in vals and v not in s.women_values])
        st.caption("El género se usa solo para análisis agregado. Brecha = (hombres − mujeres) / hombres · 100.")
        if mode == "compartible":
            stats, gaps = cmp.gender_shareable()
        else:
            stats, gaps = cmp.gender_analysis()
        if stats.empty:
            st.info("Asigna los valores de género para calcular el análisis.")
        else:
            st.dataframe(gaps, use_container_width=True, hide_index=True)
            with st.expander("Estadísticos por género"):
                st.dataframe(stats, use_container_width=True, hide_index=True)
            export_block(cmp.gender_shareable()[1], "brecha_genero", "exp_gen", label="Exportar versión compartible")
        st.warning("Una brecha no ajustada **no demuestra discriminación**: no controla responsabilidades, "
                   "nivel, variable, antigüedad ni otros factores.")
    with st.expander("Advertencias y limitaciones", expanded=False):
        for w in cmp.warnings():
            st.markdown(f"- {w}")
