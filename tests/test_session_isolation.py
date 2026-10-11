"""Aislamiento de sesiones, limpieza y ausencia de persistencia."""
import logging
import os
import re
from pathlib import Path

from core.schema import clean_column_names
from core.session import CTX_KEY, NONCE_KEY, clear_session, get_context

ROOT = Path(__file__).resolve().parents[1]
CODE = [p for d in ("core", "extraction", "ui") for p in (ROOT / d).glob("*.py")] + [ROOT / "app.py"]


def test_contexts_are_independent(raw_employees, mapping):
    s1, s2 = {}, {}
    c1 = get_context(s1)
    c1.comparator.load_employees(clean_column_names(raw_employees), mapping)
    c2 = get_context(s2)
    assert not c1.comparator.employees.empty
    assert c2.comparator.employees.empty
    assert c1.comparator.registry is not c2.comparator.registry
    assert c1.comparator.settings is not c2.comparator.settings


def test_clear_session_removes_everything(raw_employees, mapping):
    s = {}
    get_context(s).comparator.load_employees(clean_column_names(raw_employees), mapping)
    s["otra_clave"] = "x"
    clear_session(s)
    assert CTX_KEY not in s and "otra_clave" not in s and s[NONCE_KEY] == 1
    assert get_context(s).comparator.employees.empty


def test_no_shared_caches_disk_writes_or_network():
    forbidden = [r"st\.cache_data", r"st\.cache_resource", r"\.to_csv\(\s*['\"/]", r"\.to_excel\(\s*['\"/]",
                 r"open\([^)]*['\"]w", r"\bimport requests\b", r"\burllib\b", r"\bhttpx\b", r"sqlite3",
                 r"\bpickle\.dump", r"logging\.(info|debug|warning)\("]
    for p in CODE:
        src = p.read_text(encoding="utf-8")
        for pat in forbidden:
            assert not re.search(pat, src), f"{p.name}: patrón prohibido {pat}"


def test_no_salary_values_logged(raw_employees, mapping, caplog):
    caplog.set_level(logging.DEBUG)
    c = get_context({}).comparator
    c.load_employees(clean_column_names(raw_employees), mapping)
    c.compare_within_departments()
    assert "41" not in caplog.text and "Dev X" not in caplog.text


def test_streamlit_sessions_isolated():
    from streamlit.testing.v1 import AppTest
    os.chdir(ROOT)
    a = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    b = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not a.exception and not b.exception
    a.session_state[CTX_KEY].comparator.decisions.append("solo en A")
    assert b.session_state[CTX_KEY].comparator.decisions == []
