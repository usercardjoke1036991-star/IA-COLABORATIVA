"""Fixtures comunes de la suite.

Cada prueba trabaja dentro de una carpeta temporal y con su propio registro de
proyectos: nada de lo que se ejecute aqui toca ``datos/`` ni ``proyectos/``.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
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


def _es_enlace(ruta: Path) -> bool:
    """``True`` si ``ruta`` es un enlace simbolico o una junction.

    En Windows las junctions no son ``symlinks`` para la biblioteca estandar:
    hay que preguntar por ``Path.is_junction`` (Python 3.12+).
    """
    return ruta.is_symlink() or getattr(ruta, "is_junction", lambda: False)()


def _quitar_enlace(ruta: Path) -> None:
    """Borra un enlace que ya no vale (pytest limpia el destino, no el enlace)."""
    try:
        ruta.unlink()
    except OSError:
        os.rmdir(ruta)  # las junctions y los enlaces a carpetas se quitan asi


def alias_de_carpeta(carpeta: Path):
    """Otra forma valida de escribir la ruta de ``carpeta``, o ``None``.

    En Windows la misma carpeta tiene dos nombres (el largo y el corto 8.3:
    ``...\\Users\\runneradmin`` y ``...\\Users\\RUNNER~1``) y ademas se puede
    llegar a ella por un enlace. El runner de GitHub Actions vive exactamente
    asi: su ``%TEMP%`` se escribe con el nombre corto mientras que la raiz
    permitida se resuelve al largo. Este ayudante reproduce ese escenario sin
    depender de la maquina: primero prueba el nombre 8.3, luego un enlace
    simbolico y, si Windows no permite crearlo, una junction (``mklink /J``,
    que no necesita privilegios).
    """
    carpeta = Path(carpeta)
    if os.name == "nt":
        bufer = ctypes.create_unicode_buffer(4096)
        if ctypes.windll.kernel32.GetShortPathNameW(str(carpeta), bufer, 4096):
            corto = Path(bufer.value)
            if os.path.normcase(str(corto)) != os.path.normcase(str(carpeta)):
                return corto

    # El enlace vive fuera del sandbox a proposito: asi el texto sin resolver no
    # cuelga de la raiz permitida y se reproduce el fallo del runner (en su
    # temporal, el nombre corto no coincide con la raiz ya resuelta).
    contenedor = carpeta.parent.parent if carpeta.parent.parent.is_dir() else carpeta.parent
    enlace = contenedor / "{}-enlace".format(carpeta.name)
    if enlace.exists() and enlace.resolve() == carpeta.resolve():
        return enlace  # enlace bueno que dejo una ejecucion anterior
    if _es_enlace(enlace):
        # Colgaba de un temporal que pytest ya habia borrado: se rehace.
        _quitar_enlace(enlace)
    try:
        os.symlink(carpeta, enlace, target_is_directory=True)
        return enlace
    except (AttributeError, NotImplementedError, OSError):
        pass
    if os.name == "nt":
        creado = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(enlace), str(carpeta)],
            capture_output=True,
        )
        if creado.returncode == 0 and enlace.exists():
            return enlace
    return None
