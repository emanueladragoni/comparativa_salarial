import pandas as pd
import streamlit as st

from core.auth import configured_hash

from .common import export_block, fmt_eur, fmt_pct, need_data


def _secrets():
    try:
        return st.secrets
    except Exception:  # noqa: BLE001
        return None


def render(ctx):
    cmp = ctx.comparator
    st.header("6. Vista individual (acceso restringido)")
    if not ctx.auth.is_authorized():
        stored = configured_hash(_secrets())
        if not stored:
            st.error("No hay contraseña configurada. Consulta el README (SALARY_APP_PASSWORD_HASH).")
            return
        with st.form("login"):
            user = st.text_input("Usuario")
            pw = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Acceder"):
                if ctx.auth.login(user, pw, stored):
                    st.rerun()
                st.error("Credenciales no válidas.")
        return
    st.caption(f"Sesión autorizada: {ctx.auth.user}. Caduca tras inactividad.")
    if st.button("Cerrar acceso autorizado"):
        ctx.auth.logout()
        st.rerun()
    if need_data(cmp):
        return
    st.info("Información de apoyo a la revisión. No evalúa desempeño ni propone subidas o reducciones.")
    opts = [f"{r.id} (fila {r.fila_origen})" for r in cmp.employees.itertuples()]
    pick = st.selectbox("Empleado (ID y fila de origen; los IDs duplicados aparecen por separado)", opts)
    row_key = int(pick.rsplit("fila ", 1)[1].rstrip(")"))
    v = cmp.individual_view("", row_key=row_key)
    e = v["empleado"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Salario (análisis)", fmt_eur(e["salario"]))
    c2.metric("Grupo equivalente", e["grupo"] if pd.notna(e["grupo"]) else "—")
    c3.metric("Experiencia en el puesto", e["experiencia_puesto"])
    st.caption(f"{e['departamento']} · {e['rol']} · estado de equivalencia: {e['grupo_estado']}")

    for key, title in (("grupo_interno", "Grupo equivalente (todos los departamentos)"),
                       ("grupo_departamento", "Grupo equivalente en su departamento")):
        d = v[key]
        if d:
            st.markdown(f"**{title}** — n={d['n']}")
            st.dataframe(pd.DataFrame([{
                "mediana": fmt_eur(d["mediana"]), "media": fmt_eur(d["media"]),
                "P25": fmt_eur(d["p25"]), "P75": fmt_eur(d["p75"]),
                "mín": fmt_eur(d["min"]), "máx": fmt_eur(d["max"]),
                "dif. vs mediana": f"{fmt_eur(d['dif_vs_mediana_eur'])} ({fmt_pct(d['dif_vs_mediana_pct'])})"}]),
                hide_index=True)

    st.subheader("Bandas aprobadas")
    if v["bandas"]:
        st.dataframe(pd.DataFrame(v["bandas"]), use_container_width=True, hide_index=True)
    else:
        st.caption("No hay banda aprobada para este grupo.")

    st.subheader("Referencias de mercado (por fuente, sin promediar)")
    m = v["mercado"]
    if m.empty:
        st.caption("Sin referencias de mercado asociadas (revisa equivalencias y versiones activas).")
    else:
        st.dataframe(m.drop(columns=["salario"]).dropna(axis=1, how="all"), use_container_width=True, hide_index=True)
    st.subheader("Exportar todas las comparaciones individuales")
    if st.checkbox("Preparar exportación individual (todas las personas)"):
        export_block(cmp.compare_market_individual(), "comparaciones_individuales", "exp_ind",
                     individual=True, authorized=ctx.auth.is_authorized(), label="Exportar datos individuales")
