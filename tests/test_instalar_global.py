"""Pruebas de la instalacion global de la orquestacion (:mod:`activacion`).

El registro GLOBAL es la pieza que hace que CUALQUIER carpeta abierta en el IDE
tenga ya las herramientas del arquitecto. Estas pruebas fijan que se fusione
(sin pisar otros servidores) y que sea idempotente.
"""

from __future__ import annotations

import json

import activacion


def _hogar(tmp_path, monkeypatch):
    """Simula la carpeta personal del usuario (Windows y Linux)."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("APPDATA", raising=False)
    return tmp_path


def test_instalar_global_fusiona_el_mcp_y_deja_las_reglas(tmp_path, monkeypatch):
    hogar = _hogar(tmp_path, monkeypatch)
    cursor = hogar / ".cursor"
    cursor.mkdir()
    (cursor / "mcp.json").write_text(
        json.dumps({"mcpServers": {"Snyk": {"command": "snyk"}}}), encoding="utf-8"
    )

    informe = activacion.instalar_global(con_cline=False)

    datos = json.loads((cursor / "mcp.json").read_text(encoding="utf-8"))
    assert set(datos["mcpServers"]) == {"Snyk", activacion.NOMBRE_MCP}
    entrada = datos["mcpServers"][activacion.NOMBRE_MCP]
    assert entrada["args"] == [str(activacion._registrador().SERVIDOR)]

    reglas = cursor / "rules" / activacion.NOMBRE_REGLAS_GLOBALES
    assert reglas.exists()
    assert "activar_proyecto" in reglas.read_text(encoding="utf-8")
    assert "PASO MANUAL" in informe


def test_instalar_global_es_idempotente(tmp_path, monkeypatch):
    _hogar(tmp_path, monkeypatch)

    activacion.instalar_global(con_cline=False)
    activacion.instalar_global(con_cline=False)

    datos = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert list(datos["mcpServers"]) == [activacion.NOMBRE_MCP]


def test_los_destinos_de_cursor_incluyen_el_global(tmp_path, monkeypatch):
    _hogar(tmp_path, monkeypatch)

    destinos = [str(ruta) for ruta in activacion._registrador()._destinos_cursor()]

    assert any(str(tmp_path) in destino for destino in destinos)


def test_las_reglas_globales_describen_el_bucle():
    texto = activacion.REGLAS_GLOBALES

    assert "activar_proyecto" in texto
    assert "informe_de_trabajo" in texto
    assert "sugerir_mejoras" in texto
    assert "__SERVIDOR__" in texto  # se sustituye al instalar
