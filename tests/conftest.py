"""Fixtures FICTICIOS mínimos (autorizados): no proceden de datos reales."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.comparator import SalaryComparator  # noqa: E402
from core.market import coerce_market  # noqa: E402
from core.roles import confirm_rows  # noqa: E402
from core.schema import clean_column_names  # noqa: E402


@pytest.fixture
def raw_employees():
    return pd.DataFrame({
        "Departamento": ["Dep A", "Dep A ", "Dep B", "Dep B", "Dep A", "", "Dep B"],
        "Empleado": ["1", "2", "3", "4", "5", "", "5"],
        "Género": ["F", "M", "F", "M", "M", "", "F"],
        "Rol": ["Dev X", "DEV  X", "Dev X", "Analyst Y", "Dev X", "", "Analyst Y"],
        "Experiencia ": ["3 years in the role", "almost 4 years", "over 10 years in the role", "",
                         "1 year in the role", "", "2 years"],
        "Salario 2025": ["40,000.00 €", "", "50,000.00 €", "", "", "", ""],
        "IPC": ["3%", "0%", "3%", "0%", "0%", "", "0%"],
        "Salario 2026": ["41,200.00 €", "45.000,00 €", "51,500.00 €", "38000", "52,000", "", "39000"],
    })


@pytest.fixture
def mapping():
    return {"departamento": "Departamento", "id": "Empleado", "genero": "Género", "rol": "Rol",
            "experiencia": "Experiencia", "salario_anterior": "Salario 2025", "ipc": "IPC",
            "salario": "Salario 2026", "tecnologias": None}


def market_frame(rows):
    base = {"fuente": "GuiaFicticia", "edicion": "2099", "pagina": "1", "categoria_fuente": "",
            "ubicacion": "", "banda_experiencia_original": "", "tipo_experiencia": "puesto",
            "moneda": "EUR", "unidad": "EUR/año", "concepto_retributivo": "fijo bruto anual",
            "valor": "", "valor_min": "", "valor_max": "", "limite_abierto": "", "disponible": "true",
            "valor_original": "", "variable_original": "", "notas_fuente": "", "alerta_revision": "",
            "estado_validacion": "validada"}
    df, errors = coerce_market(pd.DataFrame([{**base, **r} for r in rows]))
    assert not errors, errors
    return df


@pytest.fixture
def comparator(raw_employees, mapping):
    c = SalaryComparator()
    c.load_employees(clean_column_names(raw_employees), {**mapping})
    c.set_catalog(confirm_rows(c.catalog, list(c.catalog.index), "test"))
    return c
