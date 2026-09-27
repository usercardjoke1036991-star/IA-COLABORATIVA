"""Registra este servidor MCP en Cursor y en Cline, sin editar nada a mano.

Escribe (fusionando, no pisando lo que ya hubiera):

* ``.cursor/mcp.json`` (Cursor del proyecto).
* los ``cline_mcp_settings.json`` de Cline que encuentre (app y extension de
  VS Code), respetando los servidores ya configurados.

Uso:
    venv\\\\Scripts\\\\python.exe scripts\\\\registrar_mcp.py
    venv\\\\Scripts\\\\python.exe scripts\\\\registrar_mcp.py --nombre otro-nombre
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SERVIDOR = RAIZ / "arquitecto_mcp.py"
NOMBRE_POR_DEFECTO = "arquitecto-externo"


def _entrada(interprete: str, nombre: str) -> dict:
    """Bloque JSON con el que se registra el servidor en cualquier cliente MCP."""
    return {
        "command": interprete,
        "args": [str(SERVIDOR)],
        "env": {"ARQUITECTO_LOG": "INFO"},
    }


def _fusionar(ruta: Path, nombre: str, entrada: dict, raiz_json: str = "mcpServers") -> str:
    """Fusiona la entrada del servidor en un JSON existente (lo crea si falta)."""
    datos = {}
    if ruta.exists():
        try:
            contenido = ruta.read_text(encoding="utf-8-sig") or "{}"
            datos = json.loads(contenido) if contenido.strip() else {}
        except (OSError, json.JSONDecodeError) as exc:
            return "aviso: no se pudo leer {} ({})".format(ruta, exc)
    if not isinstance(datos, dict):
        datos = {}
    servidores = datos.get(raiz_json)
    if not isinstance(servidores, dict):
        servidores = {}
    servidores[nombre] = entrada
    datos[raiz_json] = servidores

    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return "aviso: no se pudo escribir {} ({})".format(ruta, exc)
    return "actualizado {}".format(ruta)


def _destinos_cline() -> list:
    """Rutas de settings de Cline que existen en esta maquina."""
    usuario = Path(os.environ.get("USERPROFILE") or Path.home())
    candidatos = [
        usuario / ".cline" / "data" / "settings" / "cline_mcp_settings.json",
        Path(os.environ.get("APPDATA", "")) / "Code" / "User" / "globalStorage"
        / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
    ]
    return [ruta for ruta in candidatos if ruta.parent.parent.exists() or ruta.exists()]


def main(argv=None) -> int:
    """Registra el servidor y resume lo que hizo."""
    analizador = argparse.ArgumentParser(prog="registrar_mcp", description=__doc__)
    analizador.add_argument("--nombre", default=NOMBRE_POR_DEFECTO, help="nombre del servidor MCP")
    analizador.add_argument("--interprete", default=sys.executable, help="python que ejecuta el servidor")
    opciones = analizador.parse_args(argv)

    if not SERVIDOR.exists():
        print("No se encontro {}. Ejecuta este script desde el proyecto.".format(SERVIDOR))
        return 1

    entrada = _entrada(opciones.interprete, opciones.nombre)
    print("=" * 66)
    print(" REGISTRO DEL SERVIDOR MCP ".center(66, "="))
    print("=" * 66)
    print("servidor  : {}".format(SERVIDOR))
    print("interprete: {}".format(opciones.interprete))
    print("nombre    : {}".format(opciones.nombre))
    print("")

    print("[Cursor]  {}".format(_fusionar(RAIZ / ".cursor" / "mcp.json", opciones.nombre, entrada)))

    destinos = _destinos_cline()
    if not destinos:
        print("[Cline]   no se encontro ninguna instalacion de Cline (se omite)")
    for ruta in destinos:
        print("[Cline]   {}".format(_fusionar(ruta, opciones.nombre, entrada)))

    for carpeta in (Path(__file__).resolve().parent.parent / "proyectos",
                    Path(__file__).resolve().parent.parent / "datos"):
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    print("")
    print("Reinicia Cursor / Cline para que carguen el servidor.")
    print("Comprueba con:  python arquitecto_mcp.py --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
