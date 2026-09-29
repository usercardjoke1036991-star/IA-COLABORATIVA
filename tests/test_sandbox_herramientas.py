"""Regresion del sandbox de las herramientas de archivos (path traversal).

El fallo que se blinda aqui: las herramientas resolvian la ruta contra el
proyecto pero dejaban pasar ``..`` mientras el resultado cayera dentro de las
raices permitidas de la fabrica. Con eso, una sola llamada bastaba para
escribir, leer, mover o **borrar** en un proyecto hermano
(``../otro-proyecto``), en la raiz comun (``..``) o, con
``ARQUITECTO_PERMITIR_EXTERNO=true``, en cualquier parte del disco.

Ahora ``rutas.resolver`` recibe ``confinar_a_base=True`` desde
:mod:`herramientas_archivos` y desde :mod:`activacion`: el candado del proyecto
activo no se negocia. Estos tests recorren la superficie entera de las
herramientas (escribir, leer, listar, buscar, mover e informar) con los ataques
clasicos, y comprueban ademas que un intento rechazado no deja rastro ni toca al
vecino.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import activacion
import fabrica
import herramientas_archivos as archivos
import rutas

#: Formas clasicas de salirse del proyecto.
ATAQUES = [
    "..",
    "./sub/..",
    "../otro-proyecto",
    "../otro-proyecto/colado.txt",
    "sub/../../colado.txt",
]

#: Errores con los que la fabrica rechaza una ruta: los dos son ValueError.
AQUI = (archivos.ErrorArchivo, rutas.ErrorRuta)


@pytest.fixture()
def dos_proyectos(sandbox):
    """Proyecto ``victima`` (el activo) y ``vecino`` con un archivo propio."""
    fabrica.crear_proyecto("Victima", plantillas_seleccion="vacio")
    fabrica.crear_proyecto("Vecino", plantillas_seleccion="vacio")
    (sandbox / "proyectos" / "vecino" / "secreto.txt").write_text(
        "no me toques\n", encoding="utf-8"
    )
    return sandbox


def _enlace(destino: Path, enlace: Path, carpeta: bool = False) -> bool:
    """Crea un enlace a ``destino`` y dice si el sistema lo permitio.

    En Windows ``os.symlink`` necesita permiso de desarrollador; para carpetas
    se intenta ademas una junction (``mklink /J``), que no lo necesita. Si no
    hay manera, el test que lo use se salta en vez de fingir que paso.
    """
    try:
        os.symlink(destino, enlace, target_is_directory=carpeta)
        return True
    except (AttributeError, NotImplementedError, OSError):
        pass
    if os.name != "nt" or not carpeta:
        return False
    creado = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(enlace), str(destino)], capture_output=True
    )
    return creado.returncode == 0 and enlace.exists()


# --------------------------------------------------------------------------
# La ruta no puede salir del proyecto: ninguna herramienta
# --------------------------------------------------------------------------
@pytest.mark.parametrize("ataque", ATAQUES)
def test_escribir_archivo_no_sale_del_proyecto(dos_proyectos, ataque):
    with pytest.raises(AQUI, match="fuera del proyecto"):
        archivos.escribir_archivo("victima", ataque, "colado")


@pytest.mark.parametrize("ataque", ATAQUES)
def test_crear_carpeta_no_sale_del_proyecto(dos_proyectos, ataque):
    with pytest.raises(AQUI, match="fuera del proyecto"):
        archivos.crear_carpeta("victima", ataque)


@pytest.mark.parametrize("ataque", ATAQUES)
def test_leer_archivo_no_sale_del_proyecto(dos_proyectos, ataque):
    """El ataque mas util para la IA (espiar al proyecto de al lado) tambien cae."""
    with pytest.raises(AQUI):
        archivos.leer_archivo("victima", ataque)


@pytest.mark.parametrize("ataque", ATAQUES)
def test_info_archivo_no_sale_del_proyecto(dos_proyectos, ataque):
    with pytest.raises(AQUI):
        archivos.info_archivo("victima", ataque)


@pytest.mark.parametrize("ataque", ATAQUES)
def test_listar_proyecto_no_sale_del_proyecto(dos_proyectos, ataque):
    with pytest.raises(AQUI):
        archivos.listar_proyecto("victima", ataque)


@pytest.mark.parametrize("ataque", ATAQUES)
def test_buscar_en_contenido_no_sale_del_proyecto(dos_proyectos, ataque):
    with pytest.raises(AQUI):
        archivos.buscar_en_contenido("victima", "no me toques", subcarpeta=ataque)


@pytest.mark.parametrize("ataque", ATAQUES)
def test_mover_no_sale_del_proyecto(dos_proyectos, ataque):
    """Ni sacando el origen, ni escondiendo el destino fuera del proyecto."""
    with pytest.raises(AQUI):
        archivos.mover("victima", ataque, "destino.txt")

    with pytest.raises(AQUI):
        archivos.mover("victima", "notas.txt", ataque)


@pytest.mark.parametrize("ataque", ATAQUES)
def test_borrar_no_sale_del_proyecto(dos_proyectos, ataque):
    """El caso grave: el borrado recursivo de ``..`` se llevaba TODA la fabrica."""
    with pytest.raises(AQUI):
        archivos.borrar("victima", ataque, recursivo=True)

    assert (dos_proyectos / "proyectos" / "vecino" / "secreto.txt").exists()
    assert (dos_proyectos / "proyectos" / "victima").is_dir()


#: Rutas absolutas o de red: fuera del proyecto en cualquier plataforma.
ATAQUES_ABSOLUTOS = ["/etc/passwd", "/tmp/colado.txt", "//otro/share/colado.txt"]

#: Vectores de ruta propios de Windows (unidad, dispositivo y recurso de red).
ATAQUES_WINDOWS = [
    "C:\\Windows\\win.ini",
    "C:/Windows/win.ini",
    "\\\\?\\C:\\Windows\\win.ini",
    "\\\\.\\NUL",
    "\\\\localhost\\c$\\colado.txt",
]


@pytest.mark.parametrize("ataque", ATAQUES_ABSOLUTOS)
def test_ninguna_herramienta_acepta_rutas_absolutas_o_de_red(dos_proyectos, ataque):
    """Una ruta absoluta no es una ruta del proyecto: la rechaza el candado."""
    with pytest.raises(AQUI):
        archivos.escribir_archivo("victima", ataque, "colado")
    with pytest.raises(AQUI):
        archivos.crear_carpeta("victima", ataque)
    with pytest.raises(AQUI):
        archivos.leer_archivo("victima", ataque)
    with pytest.raises(AQUI):
        archivos.borrar("victima", ataque, recursivo=True)


@pytest.mark.skipif(os.name != "nt", reason="vectores de ruta propios de Windows")
@pytest.mark.parametrize("ataque", ATAQUES_WINDOWS)
def test_ninguna_herramienta_acepta_vectores_de_windows(dos_proyectos, ataque):
    """Letra de unidad, ``\\\\?\\``, ``\\\\.\\`` y ``\\\\host\\recurso``."""
    with pytest.raises(AQUI):
        archivos.escribir_archivo("victima", ataque, "colado")
    with pytest.raises(AQUI):
        archivos.leer_archivo("victima", ataque)
    with pytest.raises(AQUI):
        archivos.info_archivo("victima", ataque)


@pytest.mark.parametrize("ataque", ["CON", "aux.md", "carpeta/nul/x.txt"])
def test_ninguna_herramienta_acepta_nombres_reservados(dos_proyectos, ataque):
    """Un nombre reservado apunta a un dispositivo, no a un archivo del proyecto."""
    with pytest.raises(AQUI):
        archivos.escribir_archivo("victima", ataque, "colado")
    with pytest.raises(AQUI):
        archivos.crear_carpeta("victima", ataque)


# --------------------------------------------------------------------------
# Efectos colaterales: el intento rechazado no puede dejar rastro
# --------------------------------------------------------------------------
def test_el_intento_rechazado_no_deja_rastro(dos_proyectos):
    victima = dos_proyectos / "proyectos" / "victima"
    antes = sorted(ruta.name for ruta in victima.iterdir())

    for ataque in ATAQUES:
        for intento in (
            lambda ataque=ataque: archivos.escribir_archivo("victima", ataque, "colado"),
            lambda ataque=ataque: archivos.crear_carpeta("victima", ataque),
        ):
            with pytest.raises(AQUI):
                intento()

    assert sorted(ruta.name for ruta in victima.iterdir()) == antes
    assert sorted(ruta.name for ruta in (dos_proyectos / "proyectos").iterdir()) == [
        "vecino",
        "victima",
    ]


def test_buscar_no_encuentra_el_secreto_del_vecino(dos_proyectos):
    """Sin salirse del proyecto, el contenido del vecino es invisible."""
    assert "secreto.txt" not in archivos.buscar_en_contenido("victima", "no me toques")
    assert "secreto.txt" not in archivos.buscar_archivos("victima", "*secreto*")


def test_mover_no_puede_llevarse_la_raiz_del_proyecto(dos_proyectos):
    with pytest.raises(archivos.ErrorArchivo):
        archivos.mover("victima", ".", "copia")

    assert (dos_proyectos / "proyectos" / "victima").is_dir()


# --------------------------------------------------------------------------
# Enlaces: una puerta trasera dentro del arbol tampoco vale
# --------------------------------------------------------------------------
def test_un_enlace_hacia_fuera_no_filtra_contenido(dos_proyectos):
    victima = dos_proyectos / "proyectos" / "victima"
    secreto = dos_proyectos / "proyectos" / "vecino" / "secreto.txt"
    if not _enlace(secreto, victima / "atajo.txt"):
        pytest.skip("esta maquina no permite crear enlaces")

    with pytest.raises(AQUI):
        archivos.leer_archivo("victima", "atajo.txt")

    assert "atajo.txt" not in archivos.buscar_en_contenido("victima", "no me toques")
    assert "atajo.txt" not in archivos.buscar_archivos("victima", "*.txt")
    assert "atajo.txt" not in archivos.listar_proyecto("victima", profundidad=2)


def test_un_enlace_de_carpeta_hacia_fuera_no_filtra_contenido(dos_proyectos):
    """La version que corre en Windows sin privilegios: junction de carpeta.

    ``os.symlink`` pide permiso de desarrollador, pero ``mklink /J`` no: asi el
    filtro de enlaces queda cubierto tambien en la maquina de desarrollo.
    """
    victima = dos_proyectos / "proyectos" / "victima"
    vecino = dos_proyectos / "proyectos" / "vecino"
    if not _enlace(vecino, victima / "puerta", carpeta=True):
        pytest.skip("esta maquina no permite crear enlaces")

    salida = archivos.listar_proyecto("victima", profundidad=3)
    assert "puerta" not in salida
    assert "secreto.txt" not in archivos.buscar_archivos("victima", "*.txt")
    assert "puerta" not in archivos.buscar_en_contenido("victima", "no me toques")
    with pytest.raises(AQUI):
        archivos.leer_archivo("victima", "puerta/secreto.txt")


def test_un_enlace_hacia_dentro_del_proyecto_no_se_bloquea(dos_proyectos):
    """El filtro no puede pasarse de listo: un atajo interno es legitimo."""
    victima = dos_proyectos / "proyectos" / "victima"
    (victima / "docs").mkdir(exist_ok=True)
    (victima / "docs" / "guia.md").write_text("hola\n", encoding="utf-8")
    _enlace(victima / "docs", victima / "atajo", carpeta=True)

    assert not archivos._fuera_del_proyecto((victima / "atajo").resolve(), victima)
    assert "guia.md" in archivos.buscar_archivos("victima", "*.md")
    assert "docs/guia.md" in archivos.buscar_en_contenido("victima", "hola")
    assert "docs/" in archivos.listar_proyecto("victima", profundidad=2)


# --------------------------------------------------------------------------
# Proyecto activado: la base es la ruta fichada, no ``proyectos/<slug>``
# --------------------------------------------------------------------------
def test_el_candado_usa_la_ruta_fichada(sandbox):
    carpeta = sandbox / "proyectos" / "Mi App"
    carpeta.mkdir(parents=True)
    (sandbox / "proyectos" / "vecino").mkdir()
    activacion.activar(ruta=carpeta)

    with pytest.raises(AQUI, match="fuera del proyecto"):
        archivos.escribir_archivo("mi-app", "../vecino/colado.txt", "x")

    assert not (sandbox / "proyectos" / "vecino" / "colado.txt").exists()
