"""Extracción con un PDF FICTICIO generado en memoria (sin datos de guías reales)."""
import pandas as pd
import pytest

from core.market import coerce_market
from extraction.parsers import lines_to_records, parse_market_cell, words_to_lines
from extraction.pdf_extractor import extract_pdf


def test_cells():
    assert parse_market_cell("30-45K").valor_min == 30000
    c = parse_market_cell(">65K")
    assert c.kind == "abierto_superior" and c.valor_max is None
    assert parse_market_cell("N.A").kind == "na"
    assert parse_market_cell("45").valor is None and parse_market_cell("45").alerts


def _w(x, y, t):
    return {"x0": x, "x1": x + 6 * len(t), "top": y, "bottom": y + 10, "text": t}


def test_lines_to_records_two_level_header():
    words = [_w(200, 10, "Madrid"), _w(400, 10, "Barcelona"),
             _w(150, 30, "<2"), _w(200, 30, "2-5"), _w(250, 30, ">5"),
             _w(350, 30, "<2"), _w(400, 30, "2-5"), _w(450, 30, ">5"),
             _w(10, 50, "Rol"), _w(40, 50, "Ficticio"),
             _w(150, 50, "30.000"), _w(200, 50, "40.000"), _w(250, 50, "N.A"),
             _w(350, 50, "31.000"), _w(400, 50, "41.000"), _w(450, 50, "55.000")]
    recs, _ = lines_to_records(words_to_lines(words), 1, False)
    assert len(recs) == 6
    r = {(x.ubicacion, x.banda): x.cell_text for x in recs}
    assert r[("Madrid", "2-5")] == "40.000" and r[("Barcelona", ">5")] == "55.000"
    assert r[("Madrid", ">5")] == "N.A"


def _fake_pdf(fitz):
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    page.insert_text((72, y), "Tabla ficticia de prueba - salario medio")
    for x, t in [(250, "1-3 años"), (330, "4-7 años"), (410, "8+ años")]:
        page.insert_text((x, y + 30), t)
    for i, (role, vals) in enumerate([("Rol Ficticio A", ["30-45K", "45-60K", ">65K"]),
                                      ("Rol Ficticio B", ["NA", "40-50K", "60-55K"])]):
        page.insert_text((72, y + 60 + 20 * i), role)
        for x, v in zip([250, 330, 410], vals):
            page.insert_text((x, y + 60 + 20 * i), v)
    return doc.tobytes()


def test_extract_pdf_text_layer():
    fitz = pytest.importorskip("fitz")
    res = extract_pdf(_fake_pdf(fitz), "Ficticia", "2099", "total bruto anual", "media", use_ocr=False)
    df = res.records
    assert len(df) == 6
    a = df[(df["rol_original"] == "Rol Ficticio A") & (df["banda_experiencia_original"] == "8+ años")].iloc[0]
    assert a["limite_abierto"] == "superior" and a["valor_min"] == 65000 and pd.isna(a["valor_max"])
    b = df[df["rol_original"] == "Rol Ficticio B"]
    assert not b.iloc[0]["disponible"]
    assert (df["estado_validacion"] == "pendiente").all()
    checked, errors = coerce_market(df)
    assert not errors
    bad = checked[checked["valor_original"] == "60-55K"].iloc[0]
    assert "Mínimo mayor que máximo" in bad["alerta_revision"] and bad["valor_min"] == 60000  # no corregido


def test_page_without_text_requests_manual():
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page()
    res = extract_pdf(doc.tobytes(), "F", "1", "total bruto anual", "media", use_ocr=False)
    assert res.records.empty and "plantilla CSV" in res.pages.iloc[0]["resultado"]
