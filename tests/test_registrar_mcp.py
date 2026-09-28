"""Pruebas del saneado de rutas de ``scripts/registrar_mcp.py``.

El nombre del servidor y la ruta de destino llegan por la linea de comandos, o
sea que son entrada externa: estas pruebas fijan que el script solo escribe
``.json`` dentro de las carpetas permitidas y que **no toca el disco** cuando el
destino se rechaza (regla SonarQube ``pythonsecurity:S2083``).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
RUTA_SCRIPT = RAIZ / "scripts" / "registrar_mcp.py"


def _cargar_script():
    """Importa ``scripts/registrar_mcp.py`` sin que forme parte del paquete."""
    especificacion = importlib.util.spec_from_file_location("registrar_mcp", RUTA_SCRIPT)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


registrar = _cargar_script()


@pytest.fixture()
def hogar(tmp_path, monkeypatch):
    """Simula la carpeta del usuario para que ``~/.cline`` sea una raiz permitida."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("APPDATA", raising=False)
    return tmp_path


# --------------------------------------------------------------------------
# Nombre del servidor
# --------------------------------------------------------------------------
def test_entrada_apunta_al_servidor_del_proyecto():
    entrada = registrar._entrada("C:/Python/python.exe", "arquitecto-externo")

    assert entrada["command"] == "C:/Python/python.exe"
    assert entrada["args"] == [str(registrar.SERVIDOR)]
    assert entrada["env"]["ARQUITECTO_LOG"] == "INFO"


@pytest.mark.parametrize("nombre", ["arquitecto-externo", "otro.nombre_1", "a", "A1"])
def test_nombre_validado_acepta_nombres_razonables(nombre):
    assert registrar._nombre_validado(nombre) == nombre


@pytest.mark.parametrize(
    "nombre", ["", "   ", "..", "../fuera", "sub/carpeta", "con espacios", "x" * 65]
)
def test_nombre_validado_rechaza_lo_que_no_es_un_nombre(nombre):
    with pytest.raises(ValueError):
        registrar._nombre_validado(nombre)


# --------------------------------------------------------------------------
# Ruta de destino
# --------------------------------------------------------------------------
def test_destino_validado_acepta_json_del_usuario(hogar):
    destino = hogar / ".cline" / "data" / "settings" / "cline_mcp_settings.json"

    assert registrar._destino_validado(destino) == destino.resolve()


def test_destino_validado_acepta_json_del_proyecto():
    assert registrar._destino_validado(RAIZ / ".cursor" / "mcp.json").name == "mcp.json"


def test_destino_validado_rechaza_rutas_fuera_de_las_permitidas(hogar):
    with pytest.raises(ValueError):
        registrar._destino_validado(hogar / "colado.json")


def test_destino_validado_rechaza_extensiones_que_no_son_json(hogar):
    with pytest.raises(ValueError):
        registrar._destino_validado(hogar / ".cline" / "notas.txt")


def test_destino_validado_rechaza_un_byte_nulo(hogar):
    with pytest.raises(ValueError):
        registrar._destino_validado(Path(hogar / ".cline") / "\0malo.json")


def test_raices_permitidas_incluye_el_proyecto(hogar):
    assert RAIZ.resolve() in registrar._raices_permitidas()


# --------------------------------------------------------------------------
# Fusion del JSON
# --------------------------------------------------------------------------
def test_fusionar_crea_el_archivo_y_conserva_otros_servidores(hogar):
    destino = hogar / ".cline" / "data" / "settings" / "cline_mcp_settings.json"
    destino.parent.mkdir(parents=True)
    destino.write_text(json.dumps({"mcpServers": {"otro": {"command": "x"}}}), encoding="utf-8")
    entrada = registrar._entrada("python.exe", "arquitecto-externo")

    mensaje = registrar._fusionar(destino, "arquitecto-externo", entrada)

    assert mensaje.startswith("actualizado")
    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert set(datos["mcpServers"]) == {"otro", "arquitecto-externo"}
    assert datos["mcpServers"]["arquitecto-externo"] == entrada


def test_fusionar_no_escribe_nada_si_el_destino_no_es_valido(hogar):
    colado = hogar / "colado.json"

    mensaje = registrar._fusionar(colado, "arquitecto-externo", {})

    assert mensaje.startswith("aviso:")
    assert not colado.exists()


def test_fusionar_no_escribe_nada_si_el_nombre_no_es_valido(hogar):
    destino = hogar / ".cline" / "mcp.json"

    mensaje = registrar._fusionar(destino, "../malo", {})

    assert mensaje.startswith("aviso:")
    assert not destino.exists()


def test_fusionar_no_pisa_un_json_corrupto(hogar):
    destino = hogar / ".cline" / "mcp.json"
    destino.parent.mkdir(parents=True)
    destino.write_text("{esto no es json", encoding="utf-8")

    mensaje = registrar._fusionar(destino, "arquitecto-externo", {})

    assert mensaje.startswith("aviso:")
    assert destino.read_text(encoding="utf-8") == "{esto no es json"
