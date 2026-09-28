"""Pruebas del utillaje de limpieza de ``scripts/verificar_activador.py``.

El script activa de verdad una carpeta (ajena y vacia) dos veces y, con
``--registro-aislado`` (lo que corre el CI), apunta el registro a un temporal
para no tocar ``datos/proyectos.json``. Ese temporal **no se borraba**: en la
maquina del proyecto se contaron 4 carpetas ``registro-*`` en ``%TEMP%``.

Aqui se fijan las dos piezas nuevas: el ayudante ``_borrar_temporal`` (Windows
se calla ante objetos de solo lectura y eso no puede pasar desapercibido) y que
la verificacion completa del modo aislado no deje su registro en disco.
"""

from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_SCRIPT = RAIZ / "scripts" / "verificar_activador.py"

#: Claves del entorno que ``main`` escribe durante la verificacion.
CLAVES_DE_MAIN = ("ARQUITECTO_REGISTRO", "ARQUITECTO_PERMITIR_EXTERNO", "ARQUITECTO_LOG")


def _cargar_script():
    """Importa ``scripts/verificar_activador.py`` sin que forme parte del paquete."""
    especificacion = importlib.util.spec_from_file_location("verificar_activador", RUTA_SCRIPT)
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
    """El caso que se le escapaba a ``rmtree(ignore_errors=True)`` en Windows."""
    arbol = tmp_path / "registro-prueba"
    _arbol_con_objeto_de_git(arbol)

    assert verificador._borrar_temporal(arbol) is True
    assert not arbol.exists()


def test_borrar_temporal_avisa_si_no_pudo_borrar(tmp_path, monkeypatch):
    """Con un ``rmtree`` que no borra, el ayudante lo dice y no finge."""
    arbol = tmp_path / "registro-testarudo"
    _arbol_con_objeto_de_git(arbol)
    monkeypatch.setattr(verificador.shutil, "rmtree", lambda *argumentos, **clave: None)

    assert verificador._borrar_temporal(arbol, intentos=1) is False
    assert arbol.exists()


def test_la_verificacion_aislada_no_deja_el_registro_en_disco(tmp_path, monkeypatch, capsys):
    """``--registro-aislado`` corre la verificacion entera y limpia su temporal.

    La carpeta a activar y el temporal del registro se crean bajo ``tmp_path``
    (monkeypatch de ``mkdtemp`` y de ``_carpeta_de_prueba``) para no depender de
    ``%TEMP%`` ni dejar nada fuera de la prueba.
    """
    carpeta = tmp_path / "carpeta-de-prueba"
    monkeypatch.setattr(verificador, "_carpeta_de_prueba", lambda ruta: carpeta)

    creados = []

    def _mkdtemp(prefix="", **clave):
        hecha = tmp_path / "{}{}".format(prefix, len(creados))
        hecha.mkdir()
        creados.append(hecha)
        return str(hecha)

    monkeypatch.setattr(verificador.tempfile, "mkdtemp", _mkdtemp)
    # ``main`` escribe en el entorno del proceso: monkeypatch lo devuelve a su sitio.
    for clave in CLAVES_DE_MAIN:
        monkeypatch.setenv(clave, os.environ.get(clave, ""))

    codigo = verificador.main(["--registro-aislado"])

    texto = capsys.readouterr().out
    assert codigo == 0, texto[-2000:]
    assert "0 FALLOS" in texto
    assert "AVISO" not in texto
    assert creados, "no se creo el registro temporal aislado"
    assert not creados[0].exists(), "el registro aislado se quedo en disco"
    assert (carpeta / ".clinerules").is_file(), "la activacion no llego a hacer su trabajo"
