"""Pruebas de la limpieza de ``scripts/verificar_fabrica.py``.

El verificador crea su proyecto de prueba dentro de una carpeta temporal con
``git init`` + commit (objetos de git de solo lectura) y, con ``--venv``, un
entorno virtual entero. ``shutil.rmtree(..., ignore_errors=True)`` falla en
Windows con cualquiera de las dos cosas y se calla: el resumen imprimia
"carpeta temporal eliminada" aunque la carpeta siguiera ahi (se comprobo con una
ejecucion real: quedaba ``%TEMP%/verificacion-fabrica-*`` con 51 entradas).

Estas pruebas fijan el contrato nuevo: se quita el solo-lectura, se reintenta y,
si de verdad no se puede borrar, se avisa en vez de mentir.
"""

from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
RUTA_SCRIPT = RAIZ / "scripts" / "verificar_fabrica.py"

#: Claves del entorno que ``main`` escribe durante la verificacion.
CLAVES_DE_MAIN = (
    "ARQUITECTO_CARPETA_PROYECTOS",
    "ARQUITECTO_LOG",
    "ARQUITECTO_PERSISTIR",
    "ARQUITECTO_PERMITIR_EXTERNO",
    "ARQUITECTO_MOCK",
)

#: Pasos de ``main``: se sustituyen por dobles para probar solo el cierre.
PASOS = ("paso_rutas", "paso_plantillas", "paso_fabrica", "paso_archivos", "paso_programador")


def _cargar_script():
    """Importa ``scripts/verificar_fabrica.py`` sin que forme parte del paquete."""
    especificacion = importlib.util.spec_from_file_location("verificar_fabrica", RUTA_SCRIPT)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


verificador = _cargar_script()


def _arbol_con_objeto_de_git(carpeta: Path) -> Path:
    """Arbol de prueba con un objeto de git de solo lectura, como los reales."""
    objetos = carpeta / ".git" / "objects" / "0d"
    objetos.mkdir(parents=True)
    fichero = objetos / "d9e58b4eee99b9416b19a6cf23b1de2f6cd450"
    fichero.write_text("objeto", encoding="utf-8")
    os.chmod(fichero, stat.S_IREAD)  # en Windows, atributo de solo lectura
    return fichero


def test_borrar_temporal_quita_arboles_con_solo_lectura(tmp_path):
    """Los objetos de git de solo lectura ya no impiden borrar el temporal."""
    arbol = tmp_path / "verificacion-fabrica-prueba"
    _arbol_con_objeto_de_git(arbol)

    assert verificador._borrar_temporal(arbol) is True
    assert not arbol.exists()


def test_borrar_temporal_avisa_si_no_pudo_borrar(tmp_path, monkeypatch):
    """Con un ``rmtree`` que no borra, el ayudante lo dice y no finge."""
    arbol = tmp_path / "verificacion-fabrica-testarudo"
    _arbol_con_objeto_de_git(arbol)
    monkeypatch.setattr(verificador.shutil, "rmtree", lambda *argumentos, **clave: None)

    assert verificador._borrar_temporal(arbol, intentos=1) is False
    assert arbol.exists()


def _main_sin_pasos(tmp_path, monkeypatch, solo_lectura: bool = False) -> list:
    """Deja ``main`` listo: temporal bajo ``tmp_path`` y pasos sustituidos."""
    creados = []

    def _mkdtemp(prefix="", **clave):
        carpeta = tmp_path / "{}{}".format(prefix, len(creados))
        carpeta.mkdir()
        if solo_lectura:
            # El proyecto de prueba real trae .git con objetos de solo lectura.
            _arbol_con_objeto_de_git(carpeta)
        creados.append(carpeta)
        return str(carpeta)

    monkeypatch.setattr(verificador.tempfile, "mkdtemp", _mkdtemp)
    for nombre in PASOS:
        monkeypatch.setattr(verificador, nombre, lambda *argumentos, **clave: None)
    # ``main`` escribe en el entorno del proceso y reapunta el registro de la
    # fabrica: monkeypatch los devuelve a su sitio al terminar la prueba.
    for clave in CLAVES_DE_MAIN:
        monkeypatch.setenv(clave, os.environ.get(clave, ""))
    import fabrica

    monkeypatch.setattr(fabrica, "RUTA_REGISTRO", fabrica.RUTA_REGISTRO)
    return creados


def test_main_avisa_si_no_puede_borrar_la_carpeta_temporal(tmp_path, monkeypatch, capsys):
    """El resumen no puede decir "eliminada" cuando la carpeta sigue en disco.

    Y el aviso trae diagnostico (cuantas entradas quedan y un ejemplo), para no
    tener que abrir el temporal a mano en el proximo ciclo.
    """
    creados = _main_sin_pasos(tmp_path, monkeypatch, solo_lectura=True)
    monkeypatch.setattr(verificador, "_borrar_temporal", lambda *argumentos, **clave: False)

    codigo = verificador.main([])

    texto = capsys.readouterr().out
    assert codigo == 0
    assert "AVISO: no se pudo borrar la carpeta temporal" in texto
    assert "Carpeta temporal eliminada" not in texto
    assert "sigue habiendo 4 entradas, por ejemplo: " in texto
    assert ".git" in texto, "el aviso no dice que es lo que no se pudo borrar"
    assert creados and creados[0].exists(), "el aviso no se corresponde con el disco"


def test_main_borra_el_temporal_y_lo_dice(tmp_path, monkeypatch, capsys):
    """El camino normal: se borra de verdad (aunque haya objetos de solo lectura)."""
    creados = _main_sin_pasos(tmp_path, monkeypatch, solo_lectura=True)

    codigo = verificador.main([])

    texto = capsys.readouterr().out
    assert codigo == 0
    assert "Carpeta temporal eliminada (el registro real no se toco)." in texto
    assert creados and not creados[0].exists()


# --------------------------------------------------------------------------
# Interprete del venv en scripts de shell: el candado de las comillas
# --------------------------------------------------------------------------
def test_la_revision_detecta_el_interprete_sin_comillas():
    """Un ``venv/bin/python`` suelto se parte en la ruta con espacio."""
    texto = (
        "#!/usr/bin/env bash\n"
        "venv/bin/python -m pip install -r requirements.txt --quiet\n"
    )

    fallos = verificador._lineas_sin_comillas(texto)

    assert len(fallos) == 1
    assert "venv/bin/python" in fallos[0]


@pytest.mark.parametrize(
    "linea",
    [
        '"$RAIZ/venv/bin/python" -m pip install -r requirements.txt',
        '"venv/Scripts/python.exe" -m pytest -q',
        'if [[ ! -x "$RAIZ/venv/bin/python" ]]; then',
        'echo "  venv/bin/python arquitecto_mcp.py --check"',
        "printf '%s\\n' 'venv/bin/python'",
        "# venv/bin/python no hace falta aqui",
        "",
    ],
)
def test_la_revision_acepta_lo_que_esta_bien_o_solo_imprime(linea):
    assert verificador._lineas_sin_comillas(linea) == []


def test_los_scripts_de_shell_del_repositorio_citan_el_interprete():
    """El candado sobre el propio repositorio: corre en local y en el CI."""
    propios = sorted(RAIZ.glob("*.sh")) + sorted((RAIZ / "scripts").glob("*.sh"))
    textos = verificador._textos_sh(propios)
    assert textos, "no se encontro ningun script de shell que revisar"

    fallos, revisados = verificador._revisar_scripts_sh(textos)

    assert fallos == [], "interprete del venv sin comillas -> {}".format(" // ".join(fallos))
    assert revisados == len(textos)


def test_la_revision_mira_tambien_los_scripts_generados():
    """Un .sh generado por la fabrica entra en la revision aunque no exista."""

    def _con_venv_bin(seleccion, nombre, descripcion=""):
        class _Andamiaje:
            archivos = {"instalar.sh": "venv/bin/python -m pip install -r requirements.txt\n"}

        return _Andamiaje()

    sin_comillas = verificador._textos_sh([], _con_venv_bin("python", "demo").archivos)
    fallos, revisados = verificador._revisar_scripts_sh(sin_comillas)

    assert revisados == 1
    assert fallos and "instalar.sh" in fallos[0]
