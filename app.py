"""Interfaz Streamlit. Toda la lógica está en core/ y extraction/.

Ejecutar:  streamlit run app.py
"""
from pathlib import Path

import streamlit as st

from core.comparator import LIMITATIONS
from core.session import clear_session, get_context
from ui import p_analysis, p_bands, p_data, p_experience, p_individual, p_market, p_roles

st.set_page_config(page_title="Análisis salarial", layout="wide")

DOCS = Path(__file__).resolve().parent / "docs" / "METODOLOGIA.md"
PAGES = {
    "1. Datos de empleados": p_data.render,
    "2. Experiencia y tecnologías": p_experience.render,
    "3. Equivalencias de roles": p_roles.render,
    "4. Guías de mercado": p_market.render,
    "5. Análisis agregado": p_analysis.render,
    "6. Vista individual": p_individual.render,
    "7. Bandas salariales": p_bands.render,
    "8. Metodología y confidencialidad": None,
}


def methodology(ctx):
    st.header("8. Metodología y confidencialidad")
    st.markdown(DOCS.read_text(encoding="utf-8"))
    st.subheader("Registro de decisiones de esta sesión")
    for d in ctx.comparator.decisions or ["(ninguna)"]:
        st.markdown(f"- {d}")


ctx = get_context(st.session_state)
cmp = ctx.comparator

with st.sidebar:
    st.title("Análisis salarial")
    page = st.radio("Sección", list(PAGES))
    st.divider()
    st.subheader("Ajustes de sesión")
    cmp.settings.min_group_size = st.number_input("Umbral mínimo (informes compartibles)", 2, 50,
                                                  cmp.settings.min_group_size)
    cmp.settings.allow_concept_mismatch = st.checkbox(
        "Comparar salario fijo con referencias de total bruto anual",
        value=cmp.settings.allow_concept_mismatch,
        help="Decisión metodológica explícita. Si se activa, todas las comparaciones afectadas se etiquetan.")
    st.divider()
    st.caption("Datos en memoria de esta sesión. Sin bases de datos, sin APIs externas.")
    if st.checkbox("Quiero borrar todos los datos de la sesión"):
        if st.button("🧹 Limpiar sesión", type="primary"):
            clear_session(st.session_state)
            st.rerun()
    with st.expander("Limitaciones"):
        for item in LIMITATIONS:
            st.caption(f"• {item}")

if PAGES[page] is None:
    methodology(ctx)
else:
    PAGES[page](ctx)
