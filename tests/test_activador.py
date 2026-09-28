"""Prueba de punta a punta del activador: la "friccion cero", medida.

El activador convierte una carpeta cualquiera del usuario (vacia y ajena a la
fabrica) en un proyecto enchufado al sistema. Estas pruebas lo ejecutan de verdad
sobre esa carpeta, dos veces, y comparan los hashes SHA-256 de todo lo que deja:
la segunda pasada no puede cambiar NI UN BYTE, y los archivos que el usuario ya
tenia no se tocan.
"""

from __future__ import annotations

import hashlib

import pytest

import activacion
import fabrica

#: Contenido de un archivo propio del usuario: debe sobrevivir intacto.
SENTINELA = "# mis notas de casa\n\nNO PISAR\n"


@pytest.fixture()
def carpeta_ajena(sandbox, monkeypatch):
    """Carpeta fuera de las raices de la fabrica, con un archivo propio dentro."""
    monkeypatch.setenv("ARQUITECTO_PERMITIR_EXTERNO", "true")
    carpeta = sandbox / "Descargas" / "Mi Proyecto"
    carpeta.mkdir(parents=True)
    (carpeta / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (carpeta / "AGENTS.md").write_text(SENTINELA, encoding="utf-8")
    return carpeta


def _huellas(carpeta):
    """SHA-256 de cada archivo de la carpeta (la foto que se compara despues)."""
    return {
        ruta.relative_to(carpeta).as_posix(): hashlib.sha256(ruta.read_bytes()).hexdigest()
        for ruta in sorted(carpeta.rglob("*"))
        if ruta.is_file()
    }


def test_activar_en_carpeta_ajena_deja_toda_la_capa(carpeta_ajena):
    activacion.activar(ruta=carpeta_ajena, descripcion="prueba e2e")

    for relativo in activacion.ARCHIVOS_ORQUESTACION:
        assert (carpeta_ajena / relativo).is_file(), "falta {}".format(relativo)
    for relativo in (
        activacion.ARCHIVO_INFORME,
        activacion.ARCHIVO_SUGERENCIAS,
        ".vscode/tasks.json",
    ):
        assert (carpeta_ajena / relativo).is_file(), "falta {}".format(relativo)

    ficha = fabrica.ficha_proyecto("mi-proyecto")
    assert ficha.estado == "activado"
    assert ficha.ruta == str(carpeta_ajena.resolve())
    assert ficha.stack == "python"


def test_la_segunda_pasada_no_cambia_ni_un_byte(carpeta_ajena):
    activacion.activar(ruta=carpeta_ajena)
    antes = _huellas(carpeta_ajena)

    kit = activacion.activar(ruta=carpeta_ajena)

    assert _huellas(carpeta_ajena) == antes
    assert "no habia nada que escribir" in kit


def test_no_pisa_los_archivos_del_usuario(carpeta_ajena):
    reglas = carpeta_ajena / ".clinerules"
    reglas.write_text("mis reglas de casa\n", encoding="utf-8")

    activacion.activar(ruta=carpeta_ajena)

    assert (carpeta_ajena / "AGENTS.md").read_text(encoding="utf-8") == SENTINELA
    assert reglas.read_text(encoding="utf-8") == "mis reglas de casa\n"


def test_el_kit_de_arranque_trae_el_protocolo(carpeta_ajena):
    kit = activacion.activar(ruta=carpeta_ajena)

    assert "PROYECTO ACTIVADO: mi-proyecto" in kit
    assert "consultar_arquitecto" in kit
    assert "informe_de_trabajo" in kit
    assert "sugerir_mejoras" in kit
