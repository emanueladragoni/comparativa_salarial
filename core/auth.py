"""Autorización local para la vista individual (v1: usuario único con contraseña hasheada).

El hash se configura fuera del repositorio:
  - variable de entorno SALARY_APP_PASSWORD_HASH, o
  - .streamlit/secrets.toml -> [auth] password_hash = "..."
Generar con: python scripts/hash_password.py
En infraestructura corporativa se recomienda sustituirlo por SSO (Entra ID).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

ITERATIONS = 390_000


def hash_password(password: str, salt: bytes | None = None, iterations: int = ITERATIONS) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(it))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def configured_hash(secrets_obj=None) -> str | None:
    env = os.environ.get("SALARY_APP_PASSWORD_HASH")
    if env:
        return env
    try:
        return secrets_obj["auth"]["password_hash"] if secrets_obj is not None else None
    except Exception:  # noqa: BLE001
        return None


class AuthState:
    """Se guarda en la sesión; caduca tras `minutes` de inactividad."""

    def __init__(self, minutes: int):
        self.minutes = minutes
        self.user: str | None = None
        self._last = 0.0

    def login(self, user: str, password: str, stored_hash: str | None) -> bool:
        if not stored_hash or not user.strip() or not verify_password(password, stored_hash):
            return False
        self.user, self._last = user.strip(), time.time()
        return True

    def is_authorized(self) -> bool:
        if self.user and time.time() - self._last < self.minutes * 60:
            self._last = time.time()
            return True
        self.user = None
        return False

    def logout(self) -> None:
        self.user = None
