"""Pruebas de la fabrica de proyectos (:mod:`fabrica` y :mod:`plantillas`)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import fabrica
import herramientas_archivos as archivos
import plantillas
import rutas

if not fabrica.hay_git():  # pragma: no cover - runner sin git
    pytest.skip("git no esta disponible en esta maquina", allow_module_level=True)


# --------------------------------------------------------------------------
# Plantillas
# --------------------------------------------------------------------------
def test_disponibles_incluye_las_plantillas_documentadas():
    assert {"vacio", "python", "flask", "fastapi", "web3", "playwright", "mcp"} <= set(
        plantillas.disponibles()
    )


@pytest.mark.parametrize(
    "seleccion",
    ["python,web3", ["python", "web3"], "python web3", "PYTHON;web3"],
)
def test_interpretar_seleccion_acepta_varios_formatos(seleccion):
    assert plantillas.interpretar_seleccion(seleccion) == ["python", "web3"]


def test_construir_genera_readme_requirements_y_paquete():
    andamiaje = plantillas.construir("python", nombre="Mi Api", descripcion="de prueba")

    assert "README.md" in andamiaje.archivos
    assert "requirements.txt" in andamiaje.archivos
    assert "de prueba" in andamiaje.archivos["README.md"]
    assert not andamiaje.avisos


def test_construir_avisa_de_plantillas_desconocidas():
    andamiaje = plantillas.construir("python,no-existe", nombre="demo")

    assert andamiaje.avisos
    assert andamiaje.plantillas == ["python"]


def test_los_scripts_generados_no_llevan_escapes_rotos():
    """Los .ps1 generados no deben contener caracteres de control ni barras dobles."""
    andamiaje = plantillas.construir("python", nombre="demo")

    for ruta, contenido in andamiaje.archivos.items():
        assert "\x0b" not in contenido, "caracter de control en {}".format(ruta)
        assert "\\\\" not in contenido, "ruta sobre-escapada en {}".format(ruta)


# --------------------------------------------------------------------------
# Fabrica de proyectos
# --------------------------------------------------------------------------
def test_crear_proyecto_deja_estructura_commit_y_registro(sandbox):
    informe = fabrica.crear_proyecto(
        "Demo Uno", "proyecto de prueba", plantillas_seleccion="python"
    )

    ficha = fabrica.ficha_proyecto("demo-uno")
    raiz = Path(ficha.ruta)

    assert "demo-uno" in informe
    assert (raiz / "README.md").exists()
    assert (raiz / "requirements.txt").exists()
    assert (raiz / ".git").is_dir()
    assert ficha.commit, "el primer commit no se registro"
    assert fabrica.cargar_registro()["demo-uno"]["plantillas"] == ["python"]


def test_crear_proyecto_sin_git_no_inicializa_repositorio(sandbox):
    fabrica.crear_proyecto("Sin Git", plantillas_seleccion="vacio", con_git=False)

    raiz = Path(fabrica.ficha_proyecto("sin-git").ruta)

    assert (raiz / "README.md").exists()
    assert not (raiz / ".git").exists()
    assert fabrica.ficha_proyecto("sin-git").con_git is False


def test_crear_proyecto_rechaza_una_carpeta_ocupada(sandbox):
    fabrica.crear_proyecto("Repetido", plantillas_seleccion="vacio")

    with pytest.raises(fabrica.ErrorFabrica):
        fabrica.crear_proyecto("Repetido", plantillas_seleccion="vacio")


def test_crear_proyecto_admite_forzar_sobre_carpeta_existente(sandbox):
    fabrica.crear_proyecto("Repetido", plantillas_seleccion="vacio")

    informe = fabrica.crear_proyecto("Repetido", plantillas_seleccion="vacio", forzar=True)

    assert "Proyecto 'repetido' creado" in informe


def test_estado_git_resume_el_repositorio(sandbox):
    fabrica.crear_proyecto("Con Git", plantillas_seleccion="vacio")

    salida = fabrica.estado_git("con-git")

    assert "main" in salida


def test_interprete_venv_es_multiplataforma(sandbox):
    esperado = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")

    assert fabrica.interprete_venv(sandbox).parts[-2:] == esperado


def test_listar_proyectos_avisa_de_carpetas_sin_registrar(sandbox):
    fabrica.crear_proyecto("Uno", plantillas_seleccion="vacio")
    (sandbox / "proyectos" / "colado-a-mano").mkdir()

    salida = fabrica.listar_proyectos()

    assert "uno" in salida
    assert "colado-a-mano" in salida


# --------------------------------------------------------------------------
# Herramientas de archivos dentro de un proyecto
# --------------------------------------------------------------------------
def test_escribir_y_leer_archivo_dentro_del_proyecto(sandbox):
    fabrica.crear_proyecto("Archivos", plantillas_seleccion="vacio")

    mensaje = archivos.escribir_archivo("archivos", "src/app.py", "print('hola')")
    leido = archivos.leer_archivo("archivos", "src/app.py")

    assert mensaje.startswith("Creado")
    assert "print('hola')" in leido


def test_escribir_archivo_no_pisa_la_carpeta_git(sandbox):
    fabrica.crear_proyecto("Protegido", plantillas_seleccion="vacio")

    with pytest.raises(archivos.ErrorArchivo):
        archivos.escribir_archivo("protegido", ".git/config", "malicioso")


def test_escribir_archivo_respeta_sobreescribir_falso(sandbox):
    fabrica.crear_proyecto("Respetuoso", plantillas_seleccion="vacio")
    archivos.escribir_archivo("respetuoso", "notas.txt", "primera")

    with pytest.raises(archivos.ErrorArchivo):
        archivos.escribir_archivo("respetuoso", "notas.txt", "segunda", sobreescribir=False)


def test_buscar_en_contenido_encuentra_coincidencias(sandbox):
    fabrica.crear_proyecto("Buscador", plantillas_seleccion="vacio")
    archivos.escribir_archivo("buscador", "src/app.py", "def salud():\n    return 'ok'")

    salida = archivos.buscar_en_contenido("buscador", "def salud")

    assert "src/app.py" in salida


# --------------------------------------------------------------------------
# Registro: saneado de ARQUITECTO_REGISTRO (path traversal, S2083)
# --------------------------------------------------------------------------
def test_ruta_registro_acepta_una_ruta_dentro_del_sandbox(sandbox, monkeypatch):
    monkeypatch.setenv("ARQUITECTO_REGISTRO", str(sandbox / "cerebro.json"))

    ruta = fabrica.ruta_registro()

    assert ruta.name == "cerebro.json"
    assert ruta.parent == Path(sandbox).resolve()


def test_ruta_registro_acepta_el_registro_por_defecto(sandbox, monkeypatch):
    monkeypatch.delenv("ARQUITECTO_REGISTRO", raising=False)

    assert fabrica.ruta_registro() == fabrica.RUTA_REGISTRO


def test_ruta_registro_rechaza_una_ruta_fuera_del_sandbox(sandbox, monkeypatch):
    monkeypatch.setenv("ARQUITECTO_REGISTRO", str(sandbox.parent / "colado.json"))

    with pytest.raises(fabrica.ErrorFabrica):
        fabrica.ruta_registro()


def test_ruta_registro_rechaza_el_traversal_con_puntos(sandbox, monkeypatch):
    monkeypatch.setenv("ARQUITECTO_REGISTRO", str(sandbox / ".." / "colado.json"))

    with pytest.raises(fabrica.ErrorFabrica):
        fabrica.ruta_registro()


@pytest.mark.parametrize("nombre", ["nul", "con.json", "aux.txt", "registro.exe"])
def test_ruta_registro_rechaza_nombres_peligrosos(sandbox, monkeypatch, nombre):
    monkeypatch.setenv("ARQUITECTO_REGISTRO", str(sandbox / nombre))

    with pytest.raises(fabrica.ErrorFabrica):
        fabrica.ruta_registro()


def test_carpeta_registro_rechaza_un_byte_nulo(sandbox):
    with pytest.raises(fabrica.ErrorFabrica, match="byte nulo"):
        fabrica._carpeta_registro(Path(sandbox / "datos") / "\0malo")


@pytest.mark.parametrize("nombre", ["", ".", "..", "nul.json", "aux.txt", "malo.exe"])
def test_archivo_registro_rechaza_nombres_peligrosos(nombre):
    with pytest.raises(fabrica.ErrorFabrica):
        fabrica._archivo_registro(nombre)


@pytest.mark.parametrize("nombre", ["proyectos.json", "cerebro.json", "registro-2.json"])
def test_archivo_registro_acepta_json_normales(nombre):
    assert fabrica._archivo_registro(nombre) == nombre


def test_raices_registro_admite_el_proyecto_y_el_sandbox(sandbox):
    raices = fabrica.raices_registro()

    assert rutas.raiz_proyecto() in raices
    assert Path(sandbox).resolve() in raices


def test_permitir_externo_salta_la_comprobacion_de_raices(sandbox, monkeypatch):
    externo = sandbox.parent / "cerebro.json"
    monkeypatch.setenv("ARQUITECTO_REGISTRO", str(externo))
    monkeypatch.setenv("ARQUITECTO_PERMITIR_EXTERNO", "1")

    assert fabrica.ruta_registro() == externo.resolve()


def test_guardar_y_leer_el_registro_en_el_sandbox(sandbox):
    fabrica.guardar_registro({"demo": {"nombre": "demo", "plantillas": ["python"]}})

    assert fabrica.cargar_registro() == {
        "demo": {"nombre": "demo", "plantillas": ["python"]}
    }
    assert (Path(sandbox) / "proyectos.json").exists()


def test_guardar_registro_no_obedece_a_una_ruta_manipulada(sandbox, monkeypatch):
    colado = sandbox.parent / "colado.json"
    monkeypatch.setenv("ARQUITECTO_REGISTRO", str(colado))

    with pytest.raises(fabrica.ErrorFabrica):
        fabrica.guardar_registro({"demo": {}})

    assert not colado.exists()
