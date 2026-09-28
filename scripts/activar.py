"""Activa (o re-activa) la carpeta abierta en el IDE: la enchufa al Arquitecto.

Es el script que lanza la tarea ``.vscode/tasks.json`` al abrir el proyecto y el
que puede ejecutar el usuario a mano. No necesita MCP ni red: registra la
carpeta en la fabrica, inyecta la capa de orquestacion que falte y devuelve el
kit de arranque con el contexto real del repositorio.

Uso:
    venv\\Scripts\\python.exe scripts\\activar.py
    venv\\Scripts\\python.exe scripts\\activar.py --ruta "C:\\ruta\\al\\proyecto"
    venv\\Scripts\\python.exe scripts\\activar.py --ruta . --forzar
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
    """Activa la carpeta indicada e imprime el kit de arranque."""
    _consola_utf8()
    analizador = argparse.ArgumentParser(prog="activar", description=__doc__)
    analizador.add_argument("--ruta", default="", help="carpeta a activar (def. la actual)")
    analizador.add_argument("--nombre", default="", help="nombre con el que se registra")
    analizador.add_argument("--descripcion", default="", help="objetivo en una frase")
    analizador.add_argument(
        "--forzar", action="store_true", help="reescribe la capa de orquestacion existente"
    )
    opciones = analizador.parse_args(argv)

    try:
        informe = activacion.activar(
            ruta=opciones.ruta or None,
            nombre=opciones.nombre,
            descripcion=opciones.descripcion,
            forzar=opciones.forzar,
        )
    except Exception as exc:  # noqa: BLE001 - script de consola: mensaje claro y salida 1
        print("No se pudo activar la carpeta: {}: {}".format(type(exc).__name__, exc))
        return 1

    print(informe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
