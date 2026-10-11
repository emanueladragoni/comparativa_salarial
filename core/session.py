"""Aislamiento por sesión y limpieza.

Todo el estado con datos de empleados vive en un único objeto `SessionContext`
guardado en st.session_state (memoria del proceso, por sesión de navegador).
No se usan las cachés de Streamlit (cache_data / cache_resource) con datos
personales porque esas cachés se COMPARTEN entre sesiones.
"""
from __future__ import annotations

import gc
from dataclasses import dataclass, field

from .auth import AuthState
from .comparator import SalaryComparator
from .config import AUTH_SESSION_MINUTES

CTX_KEY = "_salary_ctx"
NONCE_KEY = "_uploader_nonce"


@dataclass
class SessionContext:
    comparator: SalaryComparator = field(default_factory=SalaryComparator)
    auth: AuthState = field(default_factory=lambda: AuthState(AUTH_SESSION_MINUTES))
    pending_extractions: dict = field(default_factory=dict)   # nombre PDF -> extracción en revisión


def get_context(state) -> SessionContext:
    if CTX_KEY not in state:
        state[CTX_KEY] = SessionContext()
    return state[CTX_KEY]


def uploader_nonce(state) -> int:
    return state.get(NONCE_KEY, 0)


def clear_session(state) -> None:
    """Elimina referencias a archivos, datos y resultados de ESTA sesión.

    Limitación: Python no sobrescribe la memoria liberada; pueden quedar copias
    hasta que el sistema reutilice esas páginas (o en swap/volcados).
    """
    nonce = state.get(NONCE_KEY, 0) + 1
    for k in list(state.keys()):
        del state[k]
    state[NONCE_KEY] = nonce          # fuerza widgets de carga nuevos (vacíos)
    gc.collect()
