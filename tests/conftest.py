"""Fixtures comunes de la suite.

Cada prueba trabaja dentro de una carpeta temporal y con su propio registro de
proyectos: nada de lo que se ejecute aqui toca ``datos/`` ni ``proyectos/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:  # permite "import fabrica" sin instalar el paquete
    sys.path.insert(0, str(RAIZ))


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Aisla la fabrica de proyectos en una carpeta temporal.

    Devuelve la raiz temporal; la carpeta de proyectos queda en ``sandbox/proyectos``.
    """
    proyectos = tmp_path / "proyectos"
    proyectos.mkdir()
    monkeypatch.setenv("ARQUITECTO_CARPETA_PROYECTOS", str(proyectos))
    monkeypatch.setenv("ARQUITECTO_REGISTRO", str(tmp_path / "proyectos.json"))
    monkeypatch.setenv("ARQUITECTO_GIT_USUARIO", "Fabrica de Pruebas")
    monkeypatch.setenv("ARQUITECTO_GIT_EMAIL", "fabrica@example.com")
    monkeypatch.delenv("ARQUITECTO_PERMITIR_EXTERNO", raising=False)
    monkeypatch.delenv("ARQUITECTO_CREAR_VENV", raising=False)
    return tmp_path
