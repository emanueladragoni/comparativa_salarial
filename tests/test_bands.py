import io

import pandas as pd
import pytest

from core.bands import BandStore, build_band
from tests.conftest import market_frame

INFO = {"grupo_equivalente": "DEV X", "nivel_responsabilidad": "Mid"}


def refs(rows):
    d = market_frame(rows)
    return d.assign(version_id="v1", nivel_responsabilidad="Mid", banda_experiencia_norm="sin banda")


def test_point_without_amplitude_is_pending():
    b = build_band(INFO, refs([{"rol_original": "Dev", "tipo_estadistico": "media", "valor": "40000"}]),
                   "valor_con_amplitud", None)
    assert b["estado"] == "pendiente de definición" and "amplitud" in b["faltan"]
    assert b["limite_inferior"] is None


def test_point_with_amplitude_is_design_decision():
    b = build_band(INFO, refs([{"rol_original": "Dev", "tipo_estadistico": "media", "valor": "40000"}]),
                   "valor_con_amplitud", 10)
    assert (b["limite_inferior"], b["punto_medio"], b["limite_superior"]) == pytest.approx((36000, 40000, 44000))
    assert "DECISIÓN DE DISEÑO" in b["origen_limites"]


def test_open_interval_not_invented():
    b = build_band(INFO, refs([{"rol_original": "Dev", "tipo_estadistico": "intervalo", "valor_min": "65000",
                                "limite_abierto": "superior"}]), "intervalo_publicado", None)
    assert b["estado"] == "pendiente de definición" and "superior" in b["faltan"]


def test_no_combination_of_different_concepts():
    r = refs([{"rol_original": "Dev", "tipo_estadistico": "media", "valor": "40000"},
              {"fuente": "B", "rol_original": "Dev", "tipo_estadistico": "media", "valor": "44000",
               "concepto_retributivo": "total bruto anual"}])
    b = build_band(INFO, r, "combinacion_media", 10)
    assert b["estado"] == "pendiente de definición" and "conceptos" in b["faltan"]


def test_approved_is_immutable_and_versioned():
    s = BandStore()
    rec = build_band(INFO, refs([{"rol_original": "Dev", "tipo_estadistico": "intervalo",
                                  "valor_min": "40000", "valor_max": "50000"}]), "intervalo_publicado", None)
    s.add(rec)
    with pytest.raises(ValueError):
        s.approve(rec["band_id"], 1, "", "")
    s.approve(rec["band_id"], 1, "Persona Ficticia", "HR")
    bid, v = s.edit(rec["band_id"], 1, {"limite_superior": 52000.0})
    assert v == 2
    v1 = s.df[(s.df["band_id"] == bid) & (s.df["version"].astype(int) == 1)].iloc[0]
    assert v1["estado"] == "aprobada" and v1["limite_superior"] == 50000
    assert int(s.approved_for("DEV X").iloc[0]["version"]) == 1
    back = BandStore.from_csv(pd.read_csv(io.BytesIO(s.export_csv()), dtype=str, keep_default_na=False))
    assert len(back.df) == 2
