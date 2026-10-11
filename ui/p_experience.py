import streamlit as st

from core.config import EXPERIENCE_KINDS

from .common import need_data


def render(ctx):
    cmp = ctx.comparator
    st.header("2. Experiencia y tecnologías")
    if need_data(cmp):
        return
    st.markdown(
        "Notación de intervalos: `5` exacto · `[6, 7]` intervalo · `(20, ∞)` más de 20 · "
        "`[0, 1)` menos de 1 · `(?, 4)` casi 4 (límite inferior desconocido) · `~5` aproximado.  \n"
        "Las guías miden **experiencia en el puesto**. Solo se usa si el texto lo indica "
        "explícitamente o si marcas la fila como **validada**. Los textos aproximados no se "
        "convierten en cifras exactas.")
    er = cmp.experience_review
    only_pending = st.checkbox("Mostrar solo filas sin validar", value=True)
    view = er[~er["validado"].astype(bool)] if only_pending else er
    ed = st.data_editor(
        view, key="exp_editor", use_container_width=True, hide_index=True,
        disabled=["fila_origen", "id", "rol", "experiencia_original", "explicito", "tecnologias_propuestas"],
        column_config={"validado": st.column_config.CheckboxColumn("validado")})
    if st.button("Guardar cambios de experiencia/tecnologías", type="primary"):
        merged = er.set_index("fila_origen")
        merged.update(ed.set_index("fila_origen"))
        errs = cmp.update_experience_review(merged.reset_index())
        for x in errs:
            st.error(x)
        if not errs:
            st.success("Cambios guardados.")

    st.subheader("Acciones en bloque (decisiones explícitas, quedan registradas)")
    who = st.text_input("Tu nombre (para el registro de decisiones)", key="who_exp")
    ids = st.multiselect("Empleados afectados (vacío = todos los filtrados)", sorted(set(er["id"])), key="bulk_ids")
    target = ids or view["id"].tolist()
    c1, c2 = st.columns(2)
    kind = c1.selectbox("Tratar experiencia «no especificada» como",
                        [k for k in EXPERIENCE_KINDS if k != "no especificada"])
    if c1.button("Aplicar a la selección"):
        n = cmp.bulk_unspecified_as(kind, target, who)
        st.success(f"{n} filas actualizadas y marcadas como validadas.")
    if c2.button("Aceptar tecnologías propuestas de la selección"):
        cmp.accept_proposed_technologies(target, who)
        st.success("Tecnologías copiadas a «tecnologias_validadas».")
