"""Recorre todas las páginas con un contexto ficticio precargado."""
import os
from pathlib import Path

import pytest

from core.comparator import SalaryComparator
from core.roles import confirm_rows
from core.schema import clean_column_names
from core.session import CTX_KEY, SessionContext
from tests.conftest import market_frame

ROOT = Path(__file__).resolve().parents[1]


def _ctx(raw, mapping, role="Developer"):
    ctx = SessionContext(comparator=SalaryComparator())
    c = ctx.comparator
    c.load_employees(clean_column_names(raw), mapping)
    c.set_catalog(confirm_rows(c.catalog, list(c.catalog.index), "t"))
    c.registry.register(market_frame([{"rol_original": role, "tipo_estadistico": "media", "valor": "40000"}]),
                        "csv", "f.csv")
    c.propose_market_mapping()
    return ctx


def _run(ctx, page):
    from streamlit.testing.v1 import AppTest
    os.chdir(ROOT)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.session_state[CTX_KEY] = ctx
    at.run()
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[page]).run()
    assert not at.exception, at.exception


@pytest.mark.parametrize("page", range(8))
def test_pages_render(page, raw_employees, mapping):
    _run(_ctx(raw_employees, mapping), page)


def test_authorized_individual_and_bands(raw_employees, mapping, monkeypatch):
    from core.auth import hash_password
    from core.bands import build_band
    h = hash_password("contraseña-ficticia")
    monkeypatch.setenv("SALARY_APP_PASSWORD_HASH", h)
    ctx = _ctx(raw_employees, mapping, role="DEV X")
    c = ctx.comparator
    c.set_market_mapping(confirm_rows(c.market_map, list(c.market_map.index), "t"))
    rec = build_band(c.group_info("DEV X"), c.band_candidates("DEV X"), "valor_con_amplitud", 10)
    c.bands.add(rec)
    c.bands.approve(rec["band_id"], 1, "Persona Ficticia", "HR")
    assert ctx.auth.login("ficticia", "contraseña-ficticia", h)
    v = c.individual_view("1")
    assert v["bandas"][0]["posicion_banda"] == "dentro" and len(v["mercado"]) == 1
    for page in (4, 5, 6):
        _run(ctx, page)
