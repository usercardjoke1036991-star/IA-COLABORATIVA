"""Prueba de extremo a extremo: actua como Cursor y habla con el servidor por stdio.

El script arranca ``arquitecto_mcp.py`` como subproceso y se comunica con el
usando el protocolo MCP real (handshake -> tools/list -> tools/call). Es la
misma secuencia que ejecuta Cursor, asi que si esto pasa, la integracion con el
IDE tambien funciona.

Uso:
    venv\\Scripts\\python.exe scripts\\prueba_cliente_mcp.py
    venv\\Scripts\\python.exe scripts\\prueba_cliente_mcp.py --real   (consume tokens)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

IDEA = (
    "Quiero un script que lea un CSV de ventas, calcule el top 10 de productos "
    "y genere un grafico PNG."
)


def _texto_de(resultado) -> str:
    """Extrae el texto de un CallToolResult de MCP."""
    contenido = getattr(resultado, "content", None)
    if contenido is None:
        return str(resultado)
    partes = []
    for bloque in contenido:
        texto = getattr(bloque, "text", None)
        partes.append(texto if texto is not None else str(bloque))
    return "\n".join(partes)


async def ejecutar(usar_real: bool) -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    entorno = dict(os.environ)
    entorno["ARQUITECTO_LOG"] = "WARNING"
    entorno["ARQUITECTO_PERSISTIR"] = "0"
    if not usar_real:
        entorno["ARQUITECTO_MOCK"] = "1"

    parametros = StdioServerParameters(
        command=sys.executable,
        args=[str(RAIZ / "arquitecto_mcp.py")],
        env=entorno,
    )

    print("lanzando el servidor: {} {}".format(sys.executable, parametros.args[0]))
    async with stdio_client(parametros) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            await sesion.initialize()
            print("[OK] handshake MCP completado")

            listado = await sesion.list_tools()
            nombres = sorted(herramienta.name for herramienta in listado.tools)
            print("[OK] tools/list -> {}".format(", ".join(nombres)))

            resultado = await sesion.call_tool(
                "consultar_arquitecto", {"idea_del_usuario": IDEA}
            )
            plan = _texto_de(resultado)
            print("\n--- tools/call consultar_arquitecto ---")
            print(plan[:600])
            if "ARQUITECTO EXTERNO" not in plan:
                print("[FALLO] respuesta inesperada de consultar_arquitecto")
                return 1

            cierra = False
            for intento in range(1, 4):
                resultado = await sesion.call_tool(
                    "reportar_progreso",
                    {
                        "resumen_de_lo_hecho": "Bloque {} implementado y verificado.".format(intento),
                        "prompt_original": IDEA,
                        "archivos_tocados": "ventas.py, grafico.py",
                    },
                )
                directriz = _texto_de(resultado)
                estado = next(
                    (l.strip() for l in directriz.splitlines() if "estado del loop" in l),
                    "(sin estado)",
                )
                print("    tools/call reportar_progreso #{} -> {}".format(intento, estado))
                if "TAREA TERMINADA" in directriz:
                    cierra = True
                    break

            resultado = await sesion.call_tool("ver_estado", {})
            estado_servidor = _texto_de(resultado)
            print("[OK] tools/call ver_estado -> {}".format(
                next((l.strip() for l in estado_servidor.splitlines() if "turnos" in l), "sin datos")
            ))
            if not cierra:
                print("[AVISO] el arquitecto no cerro el loop en 3 informes")

    print("\n[OK] servidor MCP cerrado limpiamente")
    return 0


def main(argv=None) -> int:
    analizador = argparse.ArgumentParser(
        prog="prueba_cliente_mcp",
        description="Cliente MCP de prueba: habla con el Arquitecto igual que Cursor.",
    )
    analizador.add_argument(
        "--real", action="store_true", help="usa el proveedor real del .env (consume tokens)"
    )
    argumentos = analizador.parse_args(argv)

    print("=" * 70)
    print(" CLIENTE MCP DE PRUEBA (como lo haria Cursor) ".center(70, "="))
    print("=" * 70)
    modo = "REAL" if argumentos.real else "SIMULADO"
    print("modo: {}\n".format(modo))

    try:
        return asyncio.run(ejecutar(argumentos.real))
    except Exception as exc:
        print("[FALLO] no se pudo completar la conversacion MCP: {}: {}".format(
            type(exc).__name__, exc
        ))
        return 1


if __name__ == "__main__":
    sys.exit(main())
