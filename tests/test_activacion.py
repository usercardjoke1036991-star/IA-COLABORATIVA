"""Pruebas de la activacion automatica de carpetas (:mod:`activacion`).

La activacion es la puerta de entrada del sistema: convierte una carpeta normal
en un proyecto registrado, con la capa de orquestacion puesta y el kit de
arranque listo. Estas pruebas fijan que sea idempotente, que respete el sandbox
y que las herramientas de archivos apunten a la carpeta REAL registrada.
"""

from __future__ import annotations

import json

import pytest

import activacion
import fabrica
import herramientas_archivos as archivos


@pytest.fixture()
def carpeta_cruda(sandbox):
    """Carpeta que ya existe (nombre no-slug) y sin capa de orquestacion."""
    carpeta = sandbox / "proyectos" / "Mi App"
    carpeta.mkdir(parents=True)
    (carpeta / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    return carpeta


def test_activar_inyecta_la_capa_y_devuelve_el_kit(carpeta_cruda):
    kit = activacion.activar(ruta=carpeta_cruda, descripcion="prueba de activacion")

    for relativo in activacion.ARCHIVOS_ORQUESTACION:
        assert (carpeta_cruda / relativo).exists(), "falta {}".format(relativo)
    assert (carpeta_cruda / ".vscode" / "tasks.json").exists()
    assert (carpeta_cruda / activacion.ARCHIVO_INFORME).exists()
    assert (carpeta_cruda / activacion.ARCHIVO_SUGERENCIAS).exists()

    assert "PROYECTO ACTIVADO: mi-app" in kit
    assert "consultar_arquitecto" in kit
    assert "CONTEXTO DEL REPOSITORIO" in kit


def test_activar_registra_la_ficha_con_la_ruta_real_y_el_stack(carpeta_cruda):
    activacion.activar(ruta=carpeta_cruda)

    ficha = fabrica.ficha_proyecto("mi-app")
    assert ficha.estado == "activado"
    assert ficha.stack == "python"
    assert ficha.ruta == str(carpeta_cruda.resolve())


def test_activar_es_idempotente(carpeta_cruda):
    activacion.activar(ruta=carpeta_cruda, descripcion="primera")
    kit = activacion.activar(ruta=carpeta_cruda)

    assert "no habia nada que escribir" in kit
    assert "= .clinerules" in kit
    assert kit.count("+ .clinerules") == 0


def test_activar_no_pisa_la_capa_salvo_con_forzar(carpeta_cruda):
    reglas = carpeta_cruda / ".clinerules"
    reglas.write_text("mis reglas de casa\n", encoding="utf-8")

    activacion.activar(ruta=carpeta_cruda)
    assert reglas.read_text(encoding="utf-8") == "mis reglas de casa\n"

    activacion.activar(ruta=carpeta_cruda, forzar=True)
    assert "PROGRAMADOR" in reglas.read_text(encoding="utf-8")


def test_activar_rechaza_carpetas_fuera_de_las_raices(sandbox):
    fuera = sandbox / "otra-carpeta"
    fuera.mkdir()

    with pytest.raises(ValueError):
        activacion.activar(ruta=fuera)

    assert not (fuera / ".clinerules").exists()


def test_activar_rechaza_carpetas_que_no_existen(sandbox):
    with pytest.raises(ValueError):
        activacion.activar(ruta=sandbox / "proyectos" / "no-existe")


def test_las_herramientas_trabajan_en_la_carpeta_registrada(carpeta_cruda):
    """El slug no coincide con el nombre de la carpeta: se usa la ruta fichada."""
    activacion.activar(ruta=carpeta_cruda)

    mensaje = archivos.escribir_archivo("mi-app", "src/x.py", "print(1)")

    assert "src/x.py" in mensaje
    assert (carpeta_cruda / "src" / "x.py").exists()


def test_las_herramientas_listan_la_carpeta_registrada(carpeta_cruda):
    """Sin ``subcarpeta`` hay que listar la carpeta REAL de la ficha.

    Regresion: la raiz se pedia a ``rutas.ruta_de_proyecto`` (que asume
    ``proyectos/<slug>``), asi que un proyecto activado sobre una carpeta con
    otro nombre respondia "no existe la ruta '.'" aunque su ficha fuera
    correcta. Con ``subcarpeta`` si funcionaba: el fallo estaba solo en el
    atajo de la raiz.
    """
    activacion.activar(ruta=carpeta_cruda)

    salida = archivos.listar_proyecto("mi-app", profundidad=1)

    assert "requirements.txt" in salida
    assert ".clinerules" in salida


def test_buscar_en_contenido_usa_la_carpeta_registrada(carpeta_cruda):
    """La busqueda recursiva tambien arranca de la carpeta fichada."""
    activacion.activar(ruta=carpeta_cruda)
    (carpeta_cruda / "notas.md").write_text("aguja-unica\n", encoding="utf-8")

    salida = archivos.buscar_en_contenido("mi-app", "aguja-unica")

    assert "notas.md" in salida


def test_buscar_archivos_por_patron_usa_la_carpeta_registrada(carpeta_cruda):
    """La busqueda glob tambien arranca de la carpeta fichada."""
    activacion.activar(ruta=carpeta_cruda)
    (carpeta_cruda / "notas.md").write_text("hola\n", encoding="utf-8")

    salida = archivos.buscar_archivos("mi-app", "*.md")

    assert "notas.md" in salida


def test_no_se_puede_borrar_la_raiz_de_un_proyecto_activado(carpeta_cruda):
    """La proteccion de la raiz debe comparar con la carpeta fichada.

    Regresion: comparaba con ``proyectos/<slug>``, asi que en un proyecto
    activado el borrado recursivo de "." SI se llevaba por delante el proyecto
    entero en vez de rechazarse.
    """
    activacion.activar(ruta=carpeta_cruda)

    with pytest.raises(archivos.ErrorArchivo):
        archivos.borrar("mi-app", ".", recursivo=True)

    assert (carpeta_cruda / "requirements.txt").exists()


def test_listar_un_proyecto_inexistente_sigue_avisando(sandbox):
    """El atajo arreglado no debe tapar el caso normal: proyecto que no existe."""
    with pytest.raises(archivos.ErrorArchivo):
        archivos.listar_proyecto("no-existe-este-proyecto", profundidad=1)


def test_tarea_de_arranque_usa_la_carpeta_abierta():
    tarea = activacion.tarea_de_arranque()

    assert tarea["runOptions"]["runOn"] == "folderOpen"
    assert "${workspaceFolder}" in tarea["command"]
    assert "activar.py" in tarea["command"]


def test_fusionar_tareas_conserva_las_del_usuario(sandbox):
    carpeta = sandbox / "proyectos" / "con-tareas"
    (carpeta / ".vscode").mkdir(parents=True)
    previas = {"version": "2.0.0", "tasks": [{"label": "mi tarea", "type": "shell"}]}
    (carpeta / ".vscode" / "tasks.json").write_text(json.dumps(previas), encoding="utf-8")

    activacion.activar(ruta=carpeta)

    datos = json.loads((carpeta / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
    etiquetas = [tarea.get("label") for tarea in datos["tasks"]]
    assert "mi tarea" in etiquetas
    assert "Arquitecto: activar orquestacion" in etiquetas


@pytest.mark.parametrize(
    "marcador,esperado",
    [("requirements.txt", "python"), ("package.json", "node"), ("go.mod", "go")],
)
def test_detectar_stack_reconoce_los_marcadores(sandbox, marcador, esperado):
    carpeta = sandbox / "proyectos" / "stack"
    carpeta.mkdir(parents=True)
    (carpeta / marcador).write_text("{}\n", encoding="utf-8")

    assert activacion.detectar_stack(carpeta)["stack"] == esperado


def test_detectar_stack_avisa_cuando_no_reconoce_nada(sandbox):
    carpeta = sandbox / "proyectos" / "vacia"
    carpeta.mkdir(parents=True)

    datos = activacion.detectar_stack(carpeta)

    assert datos["stack"] == "desconocido"
    assert datos["prueba"] == ""
    assert "nota" in datos
