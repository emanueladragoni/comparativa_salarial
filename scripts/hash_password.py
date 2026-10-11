"""Genera el hash de la contraseña para la vista individual (no guarda nada en disco)."""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.auth import hash_password  # noqa: E402

pw = getpass.getpass("Contraseña: ")
if pw != getpass.getpass("Repite la contraseña: ") or len(pw) < 12:
    sys.exit("Las contraseñas no coinciden o tienen menos de 12 caracteres.")
print(hash_password(pw))
