"""Pruebas del andamiaje: todo proyecto nuevo nace orquestado.

Cubre la capa de **orquestacion** que anade :mod:`plantillas` a cualquier
combinacion de plantillas: reglas para la IA del IDE (`.clinerules`,
`.cursorrules`, `.cursor/rules/arquitecto.mdc`), resumen neutro (`AGENTS.md`),
registro del servidor MCP (`.cursor/mcp.json`) y plantilla de credenciales
(`.env.example`).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

import fabrica
import plantillas

ARCHIVOS_ORQUESTACION = (
    ".clinerules",
    ".cursorrules",
    ".cursor/rules/arquitecto.mdc",
    ".cursor/mcp.json",
    "AGENTS.md",
    ".env.example",
)

SELECCIONES = ("vacio", "python", "python,web3", "python,fastapi,playwright")

#: Marcadores de plantilla que nunca deben quedar sin sustituir.
MARCADORES = ("__NOMBRE__", "__DESCRIPCION__", "__PAQUETE__", "__FECHA__", "__PLANTILLAS__")

#: Piezas del protocolo que la IA del IDE tiene que encontrar en sus reglas.
PIEZAS_DEL_PROTOCOLO = (
    "consultar_arquitecto",
    "reportar_progreso",
    "escribir_archivo",
    "commit_proyecto",
    "preparar_entorno",
    "estado del loop: TAREA TERMINADA",
    "BLOQUEO: CREDENCIALES",
)

#: Herramientas del modo consola que las reglas del IDE prohiben expresamente.
HERRAMIENTAS_PROHIBIDAS_EN_EL_IDE = (
    "pedir_codigo_al_programador",
    "aplicar_codigo_del_programador",
    "corregir_con_el_programador",
)


@pytest.mark.parametrize("seleccion", SELECCIONES)
def test_todo_proyecto_nace_orquestado(seleccion):
    andamiaje = plantillas.construir(
        seleccion, nombre="Demo Orquestado", descripcion="proyecto de prueba"
    )

    for ruta in ARCHIVOS_ORQUESTACION:
        assert ruta in andamiaje.archivos, "falta {} con {}".format(ruta, seleccion)


def test_las_reglas_explican_el_protocolo_y_el_proyecto():
    andamiaje = plantillas.construir(
        "python", nombre="Demo Orquestado", descripcion="proyecto de prueba"
    )
    reglas = andamiaje.archivos[".clinerules"]

    for pieza in PIEZAS_DEL_PROTOCOLO:
        assert pieza in reglas, "las reglas no mencionan {}".format(pieza)
    assert 'proyecto="demo-orquestado"' in reglas
    assert "venv/Scripts/python.exe" in reglas, "no se indica como ejecutar las pruebas"
    assert "Nunca" in reglas or "nunca" in reglas, "no se prohibe inventar credenciales"


def test_las_reglas_prohiben_delegar_el_codigo():
    """El arquitecto solo planifica: el codigo y la ejecucion son de la IA del IDE."""
    andamiaje = plantillas.construir("python", nombre="Demo")
    reglas = andamiaje.archivos[".clinerules"]

    assert "PROHIBIDO" in reglas
    for delegada in HERRAMIENTAS_PROHIBIDAS_EN_EL_IDE:
        assert delegada in reglas, "{} debe aparecer como prohibida".format(delegada)
    assert "escribir_archivo" in reglas, "el codigo lo escribe la IA del IDE"
    assert "Auto-reparacion con tus propias manos" in reglas

    resumen = andamiaje.archivos["AGENTS.md"]
    assert "solo planifica" in resumen
    assert "Delegar en otro modelo esta prohibido" in resumen


def test_los_tres_formatos_de_reglas_comparten_el_mismo_protocolo():
    andamiaje = plantillas.construir("python", nombre="Demo")
    cuerpo = andamiaje.archivos[".clinerules"]

    assert andamiaje.archivos[".cursorrules"] == cuerpo
    assert andamiaje.archivos[".cursor/rules/arquitecto.mdc"].endswith(cuerpo)
    assert andamiaje.archivos[".cursor/rules/arquitecto.mdc"].startswith("---\n")


def test_el_resumen_de_agentes_apunta_al_arquitecto_y_al_bloqueo():
    resumen = plantillas.construir("vacio", nombre="Demo").archivos["AGENTS.md"]

    assert "arquitecto-externo" in resumen
    assert "BLOQUEO: CREDENCIALES" in resumen
    assert "# demo - contexto" in resumen, "el slug del proyecto debe aparecer"


def test_el_registro_mcp_apunta_al_servidor_de_la_fabrica():
    andamiaje = plantillas.construir("python", nombre="Demo")

    registro = json.loads(andamiaje.archivos[".cursor/mcp.json"])
    servidor = registro["mcpServers"]["arquitecto-externo"]

    assert servidor["args"] == [plantillas._servidor_mcp()]
    assert servidor["args"][0].endswith("arquitecto_mcp.py")
    assert servidor["command"]
    assert "\\" not in servidor["args"][0], "las rutas del JSON deben usar barras normales"


def test_el_registro_mcp_usa_el_interprete_del_venv_de_la_fabrica():
    """Si el entorno del orquestador existe, debe arrancar el servidor con el."""
    andamiaje = plantillas.construir("python", nombre="Demo")

    comando = json.loads(andamiaje.archivos[".cursor/mcp.json"])["mcpServers"][
        "arquitecto-externo"
    ]["command"]
    venv = plantillas.rutas.raiz_proyecto() / "venv"
    # El interprete lleva el nombre de SU plataforma: un venv creado en Windows
    # (visible desde WSL en /mnt/c) tiene Scripts/python.exe y no bin/python, y
    # entonces la fabrica no puede usarlo aunque la carpeta del venv exista.
    piezas = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    interprete = venv.joinpath(*piezas)

    assert comando == plantillas._interprete_mcp()
    if interprete.is_file():
        assert comando.startswith(venv.as_posix()), "debe apuntar al venv de la fabrica"
    else:  # pragma: no cover - runner sin venv
        assert comando == "python"


@pytest.mark.parametrize(
    "clave", ["DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"]
)
def test_la_plantilla_de_credenciales_deja_las_claves_vacias(clave):
    ejemplo = plantillas.construir("python", nombre="Demo").archivos[".env.example"]

    assert re.search(r"^{}=$".format(clave), ejemplo, re.MULTILINE), (
        "{} debe quedar vacia para que el usuario la rellene".format(clave)
    )
    assert "# ARQUITECTO_MOCK=true" in ejemplo, "el modo simulado debe venir comentado"


def test_ningun_archivo_generado_tiene_escapes_rotos():
    """Refuerza la comprobacion global: nada de caracteres de control ni dobles barras."""
    andamiaje = plantillas.construir("python,web3", nombre="Demo")

    for ruta, contenido in andamiaje.archivos.items():
        assert chr(11) not in contenido, "caracter de control en {}".format(ruta)
        assert "\\\\" not in contenido, "ruta sobre-escapada en {}".format(ruta)


@pytest.mark.parametrize("seleccion", SELECCIONES)
def test_no_quedan_marcadores_sin_sustituir(seleccion):
    andamiaje = plantillas.construir(seleccion, nombre="Demo", descripcion="una frase")

    for ruta, contenido in andamiaje.archivos.items():
        for marcador in MARCADORES:
            assert marcador not in contenido, "{} sin sustituir en {}".format(marcador, ruta)


def test_la_nota_de_orquestacion_llega_al_informe():
    andamiaje = plantillas.construir("python", nombre="Demo")

    assert any("Orquestacion:" in nota for nota in andamiaje.notas)


# --------------------------------------------------------------------------
# Integracion con la fabrica
# --------------------------------------------------------------------------
def test_la_fabrica_deja_el_proyecto_orquestado_y_versionado(sandbox):
    if not fabrica.hay_git():  # pragma: no cover - runner sin git
        pytest.skip("git no esta disponible en esta maquina")

    fabrica.crear_proyecto(
        "Demo Orquestado", "proyecto de prueba", plantillas_seleccion="python"
    )
    raiz = Path(fabrica.ficha_proyecto("demo-orquestado").ruta)

    for ruta in ARCHIVOS_ORQUESTACION:
        assert (raiz / ruta).is_file(), "no se escribio {}".format(ruta)

    seguidos = subprocess.run(
        ["git", "ls-files"],
        cwd=str(raiz),
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.replace("\\", "/")

    assert ".clinerules" in seguidos
    assert ".cursor/mcp.json" in seguidos
    assert ".env.example" in seguidos
    assert not (raiz / ".env").exists(), "nunca se crea un .env con secretos"
