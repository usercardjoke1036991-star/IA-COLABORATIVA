"""Pruebas del unico punto de salida de procesos externos (:mod:`procesos`).

Cubre el fallo real que motivo el modulo: un hijo lanzado desde el servidor MCP
heredaba el stdin del protocolo y se quedaba colgado para siempre.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

import fabrica
import procesos

RAIZ = Path(__file__).resolve().parent.parent

#: Modulos de produccion que ejecutan procesos externos (git, gh, python, pytest).
MODULOS_CON_PROCESOS = (
    "arquitecto.py",
    "arquitecto_mcp.py",
    "activacion.py",
    "contexto.py",
    "fabrica.py",
    "mejora.py",
    "orquestador.py",
    "plantillas.py",
    "rutas.py",
    "sesiones.py",
)


def test_ejecuta_y_separa_salida_y_error(tmp_path):
    codigo, salida, error = procesos.ejecutar(
        [sys.executable, "-c", "import sys; print('hola'); print('aviso', file=sys.stderr)"],
        cwd=tmp_path,
        timeout=30,
    )
    assert codigo == 0
    assert salida.strip() == "hola"
    assert error.strip() == "aviso"


def test_ejecutar_texto_une_salida_y_error(tmp_path):
    codigo, texto = procesos.ejecutar_texto(
        [sys.executable, "-c", "import sys; print('uno'); print('dos', file=sys.stderr)"],
        cwd=tmp_path,
        timeout=30,
    )
    assert codigo == 0
    assert "uno" in texto
    assert "dos" in texto


def test_el_hijo_no_hereda_el_stdin_del_servidor(tmp_path):
    """Con stdin=DEVNULL el hijo lee 0 bytes y termina al instante (antes: colgado)."""
    inicio = time.time()
    codigo, salida, _ = procesos.ejecutar(
        [sys.executable, "-c", "import sys; print(len(sys.stdin.read()))"],
        cwd=tmp_path,
        timeout=30,
    )
    assert codigo == 0
    assert salida.strip() == "0"
    assert time.time() - inicio < 20


def test_kwargs_proceso_no_hereda_stdin_ni_abre_consola():
    kwargs = procesos.kwargs_proceso()
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["shell"] is False
    assert kwargs["creationflags"] == procesos.flags_sin_consola()
    if sys.platform == "win32":
        assert kwargs["creationflags"] != 0, "en Windows hace falta CREATE_NO_WINDOW"


def test_entorno_conserva_el_del_sistema_y_marca_no_interactivo():
    valores = procesos.entorno({"ARQUITECTO_PRUEBA": "1"})
    assert valores["GIT_TERMINAL_PROMPT"] == "0"
    assert valores["GH_PROMPT_DISABLED"] == "1"
    assert valores["ARQUITECTO_PRUEBA"] == "1"
    assert "PATH" in valores or "Path" in valores


def test_el_entorno_extra_llega_al_hijo(tmp_path):
    codigo, salida, _ = procesos.ejecutar(
        [sys.executable, "-c", "import os; print(os.environ['ARQUITECTO_PRUEBA'])"],
        cwd=tmp_path,
        timeout=30,
        entorno_extra={"ARQUITECTO_PRUEBA": "si"},
    )
    assert codigo == 0
    assert salida.strip() == "si"


def test_timeout_corta_al_hijo_sin_quedarse_esperando(tmp_path):
    inicio = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        procesos.ejecutar(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            cwd=tmp_path,
            timeout=1,
        )
    assert time.time() - inicio < 45, "el helper se quedo esperando al hijo rebelde"


def test_ejecutable_inexistente_avisa(tmp_path):
    with pytest.raises(FileNotFoundError):
        procesos.ejecutar(["no-existe-este-programa-xyz", "--version"], cwd=tmp_path, timeout=5)


def test_fabrica_combina_salida_y_error(tmp_path):
    codigo, salida = fabrica._ejecutar(  # noqa: SLF001 (se prueba el contrato interno)
        [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
        cwd=tmp_path,
        timeout=30,
    )
    assert codigo == 0
    assert "out" in salida
    assert "err" in salida


def test_fabrica_traduce_ejecutable_ausente(tmp_path):
    with pytest.raises(fabrica.ErrorFabrica):
        fabrica._ejecutar(["no-existe-este-programa-xyz"], cwd=tmp_path, timeout=5)  # noqa: SLF001


def test_git_disponible_no_se_cuelga():
    """git --version debe responder o decir que no hay git: nunca bloquear."""
    inicio = time.time()
    version = fabrica.git_disponible()
    assert time.time() - inicio < 60
    assert version == "" or "git version" in version


@pytest.mark.parametrize("nombre", MODULOS_CON_PROCESOS)
def test_regresion_ningun_modulo_lanza_subprocess_directo(nombre):
    """Si alguien vuelve a ``subprocess.run``, el cuelgue del MCP vuelve con el."""
    ruta = RAIZ / nombre
    if not ruta.is_file():
        pytest.skip("{} no existe".format(nombre))
    texto = ruta.read_text(encoding="utf-8")
    for prohibido in ("subprocess.run(", "subprocess.Popen("):
        assert prohibido not in texto, (
            "{} usa {}: debe pasar por procesos.ejecutar".format(nombre, prohibido)
        )
