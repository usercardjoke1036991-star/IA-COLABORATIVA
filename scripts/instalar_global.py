"""Instala la orquestacion en TODA la maquina (una vez y listo).

Registra el servidor MCP en Cursor (global **y** del proyecto) y en los settings
de Cline, y deja las reglas de arranque en ``~/.cursor/rules``. A partir de ahi,
cualquier carpeta que abras en el IDE sabe activarse sola con la herramienta MCP
``activar_proyecto`` (o con ``scripts/activar.py`` si el IDE no tiene MCP).

Es idempotente y solo fusiona: nunca pisa servidores ni reglas de otros.

Uso:
    venv\\Scripts\\python.exe scripts\\instalar_global.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:  # activacion vive en la raiz del proyecto
    sys.path.insert(0, str(RAIZ))

import activacion  # noqa: E402 - despues de ajustar sys.path, a proposito


def _consola_utf8() -> None:
    """Evita UnicodeEncodeError en consolas clasicas de Windows (cp1252)."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # flujo redirigido o sin soporte
            continue


def main(argv=None) -> int:
    """Instala la configuracion global e imprime el unico paso manual que queda."""
    _consola_utf8()
    analizador = argparse.ArgumentParser(prog="instalar_global", description=__doc__)
    analizador.add_argument(
        "--sin-cline", action="store_true", help="no toca los settings de Cline"
    )
    opciones = analizador.parse_args(argv)

    try:
        informe = activacion.instalar_global(con_cline=not opciones.sin_cline)
    except Exception as exc:  # noqa: BLE001 - script de consola: mensaje claro y salida 1
        print("No se pudo instalar la orquestacion global: {}: {}".format(type(exc).__name__, exc))
        return 1

    print(informe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
