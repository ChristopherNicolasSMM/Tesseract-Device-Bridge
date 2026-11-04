"""Version gate for the production Raspberry Pi GPIO environment."""
import sys


def require_python39_for_real(version_info=None):
    """Keep tested GPIO/1-Wire operations on Python 3.9, never change system Python."""
    version = sys.version_info if version_info is None else version_info
    if (version[0], version[1]) != (3, 9):
        raise RuntimeError(
            f"Backend real requer Python 3.9.x (encontrado {version[0]}.{version[1]}). "
            "Ative a venv Python 3.9 do Raspberry Pi antes de iniciar. "
            "Modo simulated continua disponível para desenvolvimento com outras versões."
        )
