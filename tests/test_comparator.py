import pandas as pd
import pytest

from core.roles import confirm_rows
from tests.conftest import market_frame


def _setup_market(c, rows):
    c.registry.register(market_frame(rows), "csv", "ficticio.csv")
    c.market_map = confirm_rows(pd.DataFrame([{
        "grupo_equivalente": "DEV X", "fuente": "GuiaFicticia", "edicion": "", "rol_original": "Developer",
        "estado": "propuesta", "confirmado_por": "", "fecha_confirmacion": "", "notas": ""}]), [0], "test")


def test_normalization(comparator):
    e = comparator.employees.set_index("fila_origen")
    assert e.loc[3, "salario"] == 45000.0                       # formato español
    assert e.loc[2, "departamento"] == e.loc[3, "departamento"] == "Dep A"
    amb = comparator.money_review()
    assert list(amb["salario_original"]) == ["52,000"]         # ambiguo, original conservado
    assert comparator.employees["rol"].iloc[1] == "DEV X"


def test_ambiguous_money_excluded_until_resolved(comparator):
    w = comparator.compare_within_departments()
    assert w[(w["departamento"] == "Dep A") & (w["grupo"] == "DEV X")].iloc[0]["n"] == 2
    comparator.resolve_money(6, 52000.0, "test")
    w = comparator.compare_within_departments()
    assert w[(w["departamento"] == "Dep A") & (w["grupo"] == "DEV X")].iloc[0]["n"] == 3


def test_point_reference_diff(comparator):
    _setup_market(comparator, [{"rol_original": "Developer", "tipo_estadistico": "media", "valor": "40000"}])
    r = comparator.compare_market_individual(["1"]).iloc[0]
    assert r["estado"] == "comparable"
    assert r["dif_eur"] == 1200 and r["dif_pct"] == pytest.approx(3.0)


def test_closed_and_open_intervals_no_midpoint(comparator):
    _setup_market(comparator, [
        {"rol_original": "Developer", "tipo_estadistico": "intervalo", "valor_min": "45000", "valor_max": "55000",
         "banda_experiencia_original": "<5"},
        {"rol_original": "Developer", "tipo_estadistico": "intervalo", "valor_min": "50000",
         "limite_abierto": "superior", "banda_experiencia_original": ">5"}])
    m = comparator.compare_market_individual(["1", "3"]).set_index("id")
    assert m.loc["1", "posicion"] == "por debajo" and m.loc["1", "dif_vs_inferior_eur"] == -3800
    assert pd.isna(m.loc["1", "referencia"])                                    # sin punto medio
    assert m.loc["3", "posicion"].startswith("por encima del límite inferior")
    assert pd.isna(m.loc["3", "posicion_en_intervalo_pct"])                     # falta límite


def test_experience_gating(comparator):
    _setup_market(comparator, [{"rol_original": "Developer", "tipo_estadistico": "media", "valor": "40000",
                                "banda_experiencia_original": "2-5 años"}])
    m = comparator.compare_market_individual(["2"])
    assert m.iloc[0]["estado"].startswith("no comparable por experiencia")    # "almost 4" no validada


def test_concept_mismatch_blocked_by_default(comparator):
    _setup_market(comparator, [{"rol_original": "Developer", "tipo_estadistico": "media", "valor": "40000",
                                "concepto_retributivo": "total bruto anual"}])
    assert "no comparado" in comparator.compare_market_individual(["1"]).iloc[0]["estado"]
    comparator.settings.allow_concept_mismatch = True
    assert comparator.compare_market_individual(["1"]).iloc[0]["estado"].startswith("comparable con advertencia")


def test_location_requires_selection(comparator):
    _setup_market(comparator, [{"rol_original": "Developer", "tipo_estadistico": "media", "valor": "40000",
                                "ubicacion": "Madrid"},
                               {"rol_original": "Developer", "tipo_estadistico": "media", "valor": "38000",
                                "ubicacion": "Valencia"}])
    m = comparator.compare_market_individual(["1"])
    assert list(m["estado"]) == ["ubicación de referencia no seleccionada"]
    comparator.settings.reference_location = "Madrid"
    m = comparator.compare_market_individual(["1"])
    assert len(m) == 1 and m.iloc[0]["referencia"] == 40000


def test_sources_not_averaged(comparator):
    rows = [{"rol_original": "Developer", "tipo_estadistico": "media", "valor": "40000"},
            {"fuente": "OtraFicticia", "rol_original": "Developer", "tipo_estadistico": "moda", "valor": "42000"}]
    _setup_market(comparator, rows)
    comparator.market_map = pd.concat([comparator.market_map, comparator.market_map.assign(fuente="OtraFicticia")])
    agg = comparator.compare_market_aggregated()
    assert set(agg["fuente"]) == {"GuiaFicticia", "OtraFicticia"} and len(agg) == 2
    assert set(agg["grupo"]) == {"DEV X"}


def test_unconfirmed_roles_excluded(comparator):
    comparator.catalog["estado"] = "propuesta"
    assert comparator.compare_within_departments().empty


def test_gender_aggregated_only(comparator):
    comparator.settings.women_values, comparator.settings.men_values = ["F"], ["M"]
    stats, gaps = comparator.gender_analysis()
    assert not gaps.empty
    _, gaps_sh = comparator.gender_shareable()
    assert gaps_sh["brecha_media_pct"].isna().all()            # n < 5 => suprimido
    assert "genero" not in comparator.individual_view("1")["empleado"]


def test_individual_view_no_threshold(comparator):
    v = comparator.individual_view("1")
    assert v["grupo_interno"]["n"] >= 2 and v["grupo_interno"]["min"] is not None


def test_raw_text_not_in_aggregates(comparator):
    for df in (comparator.compare_within_departments(), comparator.compare_across_departments()):
        assert "experiencia_texto" not in df.columns and "id" not in df.columns


def test_duplicate_ids_keep_their_own_rows(comparator):
    _setup_market(comparator, [{"rol_original": "Developer", "tipo_estadistico": "media", "valor": "40000"}])
    m = comparator.compare_market_individual(["5"])
    assert m.empty or set(m["grupo"]) <= {"DEV X"}   # la fila 'Analyst Y' con ID 5 no hereda referencias
    with pytest.raises(ValueError):
        comparator.individual_view("5")
    assert comparator.individual_view("", row_key=8)["empleado"]["rol"] == "ANALYST Y"
