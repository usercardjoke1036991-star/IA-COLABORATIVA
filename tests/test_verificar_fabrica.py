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
    """El resumen no puede decir "eliminada" cuando la carpeta sigue en disco."""
    creados = _main_sin_pasos(tmp_path, monkeypatch)
    monkeypatch.setattr(verificador, "_borrar_temporal", lambda *argumentos, **clave: False)

    codigo = verificador.main([])

    texto = capsys.readouterr().out
    assert codigo == 0
    assert "AVISO: no se pudo borrar la carpeta temporal" in texto
    assert "Carpeta temporal eliminada" not in texto
    assert creados and creados[0].exists(), "el aviso no se corresponde con el disco"


def test_main_borra_el_temporal_y_lo_dice(tmp_path, monkeypatch, capsys):
    """El camino normal: se borra de verdad (aunque haya objetos de solo lectura)."""
    creados = _main_sin_pasos(tmp_path, monkeypatch, solo_lectura=True)

    codigo = verificador.main([])

    texto = capsys.readouterr().out
    assert codigo == 0
    assert "Carpeta temporal eliminada (el registro real no se toco)." in texto
    assert creados and not creados[0].exists()
