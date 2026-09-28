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


def test_un_comando_vacio_se_rechaza(tmp_path):
    with pytest.raises(ValueError):
        procesos.ejecutar([], cwd=tmp_path, timeout=5)


def test_un_programa_que_empieza_por_guion_se_rechaza(tmp_path):
    """argv[0] nunca es una opcion: eso es la puerta de la inyeccion de argumentos."""
    with pytest.raises(ValueError):
        procesos.ejecutar(["--yolo", "algo"], cwd=tmp_path, timeout=5)


def test_un_argumento_con_byte_nulo_se_rechaza(tmp_path):
    """El NUL corta la cadena al llegar al sistema: se corta antes, aqui."""
    with pytest.raises(ValueError):
        procesos.ejecutar([sys.executable, "-c", "pass\x00--yolo"], cwd=tmp_path, timeout=5)


def test_el_saneado_no_toca_los_argumentos_legitimos(tmp_path):
    """Solo se valida argv[0] y el NUL: un texto con guion sigue llegando igual."""
    codigo, salida, _ = procesos.ejecutar(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "-no-es-una-opcion"],
        cwd=tmp_path,
        timeout=30,
    )
    assert codigo == 0
    assert salida.strip() == "-no-es-una-opcion"


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


#: Guion de un hijo rebelde: abre un nieto que tambien duerme y despues se cuelga.
#: Espera medio segundo antes de crear el nieto para que el Job Object ya este
#: asignado: asi se mide el corte del arbol, no una carrera.
GUION_HIJO_CON_NIETO = (
    "import os, pathlib, subprocess, sys, time\n"
    "time.sleep(0.5)\n"
    "nieto = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
    "pathlib.Path(sys.argv[1]).write_text('{} {}'.format(os.getpid(), nieto.pid))\n"
    "time.sleep(120)\n"
)


def _sigue_vivo(pid: int) -> bool:
    """True si ese PID existe todavia (``tasklist`` en Windows, ``/proc``/``ps`` fuera)."""
    if sys.platform == "win32":
        _, salida, _ = procesos.ejecutar(
            ["tasklist", "/FI", "PID eq {}".format(pid), "/NH"], cwd=RAIZ, timeout=30
        )
        return str(pid) in salida
    if Path("/proc/{}".format(pid)).exists():
        return True
    # ejecutar() devuelve (codigo, salida, error): la rama de Windows ya lo tenia
    # en cuenta y esta no, asi que en Linux la prueba reventaba con "too many
    # values to unpack" justo cuando el proceso YA habia muerto (el caso bueno).
    codigo, _, _ = procesos.ejecutar(["ps", "-p", str(pid)], cwd=RAIZ, timeout=30)
    return codigo == 0


def test_el_timeout_mata_tambien_a_los_nietos(tmp_path):
    """Prueba adversarial: se corta el ARBOL, no solo al padre.

    Matar solo al padre dejaba vivos a los nietos (cada uno con su consola), que
    es el sintoma real del cuelgue. Aqui el hijo abre un nieto y los dos duermen:
    tras el corte ninguno puede seguir vivo.
    """
    marcador = tmp_path / "pids.txt"
    guion = tmp_path / "cuelga.py"
    guion.write_text(GUION_HIJO_CON_NIETO, encoding="utf-8")

    inicio = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        procesos.ejecutar(
            [sys.executable, str(guion), str(marcador)], cwd=tmp_path, timeout=8
        )
    duracion = time.time() - inicio

    assert duracion < 45, "el helper se quedo esperando al hijo rebelde"
    assert marcador.exists(), "el hijo no llego a crear el nieto"
    pid_hijo, pid_nieto = (int(pieza) for pieza in marcador.read_text().split())
    for _ in range(20):  # margen para que Windows libere handles e hilos
        if not _sigue_vivo(pid_hijo) and not _sigue_vivo(pid_nieto):
            break
        time.sleep(0.5)
    assert not _sigue_vivo(pid_hijo), "el hijo sigue vivo despues del corte"
    assert not _sigue_vivo(pid_nieto), "el nieto sobrevivio: no se corto el arbol"


def test_el_job_object_se_abre_donde_el_sistema_lo_permite():
    """El Job Object es el mecanismo fuerte del corte por tiempo."""
    job = procesos._abrir_job()  # noqa: SLF001 - se prueba el contrato interno
    try:
        if sys.platform == "win32":
            assert job, "Windows deberia permitir un Job Object para matar el arbol"
        else:
            assert job == 0, "fuera de Windows el corte usa el grupo de procesos"
    finally:
        procesos._cerrar_job(job)  # noqa: SLF001


def test_matar_arbol_de_un_proceso_ya_muerto_no_rompe(tmp_path):
    """El corte de emergencia es tolerante: nunca lanza desde la limpieza."""
    proceso = subprocess.Popen(
        [sys.executable, "-c", "pass"], stdin=subprocess.DEVNULL, cwd=str(tmp_path)
    )
    proceso.wait(timeout=30)

    procesos._matar_arbol(proceso)  # noqa: SLF001 - no debe lanzar nada


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
