"""Verificacion de la instalacion del Arquitecto Externo.

Comprueba, de verdad y paso a paso, que todo el sistema funciona:

1. Dependencias instaladas (mcp + requests) y sus versiones.
2. Modulos del proyecto importables y configuracion cargada.
3. El servidor MCP se construye y registra sus 5 herramientas.
4. Se invoca una herramienta A TRAVES del gestor de MCP (no llamando a la
   funcion de Python directamente), para validar el camino real que usa Cursor.

Por defecto se ejecuta en modo simulado (sin red ni API key). Con --real usa el
proveedor configurado en tu .env y si consume tokens.

Uso:
    venv\\Scripts\\python.exe scripts\\verificar_servidor.py
    venv\\Scripts\\python.exe scripts\\verificar_servidor.py --real
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

HERRAMIENTAS_ESPERADAS = {
    # Arquitecto (planifica)
    "consultar_arquitecto",
    "reportar_progreso",
    "ver_estado",
    "exportar_plan",
    "reiniciar_sesion",
    # Fabrica de proyectos
    "estado_fabrica",
    "catalogo_plantillas",
    "crear_proyecto",
    "listar_proyectos",
    "ver_proyecto",
    # Archivos
    "listar_archivos",
    "leer_archivo",
    "escribir_archivo",
    "crear_carpeta",
    "mover_archivo",
    "borrar_archivo",
    "buscar_en_proyecto",
    "buscar_archivos",
    # Entorno, git y GitHub
    "preparar_entorno",
    "estado_git",
    "commit_proyecto",
    "publicar_en_github",
    # Programador externo
    "estado_programador",
    "pedir_codigo_al_programador",
    "aplicar_codigo_del_programador",
    "corregir_con_el_programador",
    "reiniciar_programador",
}

_anchos = (70,)
_resultados = []


def _ok(titulo: str, detalle: str = "") -> None:
    _resultados.append(True)
    print("  [OK]   {}{}".format(titulo, " -> " + detalle if detalle else ""))


def _fallo(titulo: str, detalle: str = "") -> None:
    _resultados.append(False)
    print("  [FALLO] {}{}".format(titulo, " -> " + detalle if detalle else ""))


def _paso(numero: int, titulo: str) -> None:
    print("")
    print("-" * _anchos[0])
    print("PASO {}: {}".format(numero, titulo))


# --------------------------------------------------------------------------
# Paso 1: dependencias
# --------------------------------------------------------------------------
def paso_dependencias() -> bool:
    _paso(1, "Dependencias")
    valido = True
    try:
        import importlib.metadata as metadatos

        print("  python  : {}".format(sys.version.split()[0]))
        print("  ejecutable: {}".format(sys.executable))
        for paquete in ("mcp", "requests"):
            try:
                print("  {}      : {}".format(paquete.ljust(8), metadatos.version(paquete)))
                _ok("paquete '{}' presente".format(paquete))
            except Exception:
                _fallo(
                    "paquete '{}' ausente".format(paquete),
                    "ejecuta: pip install -r requirements.txt",
                )
                valido = False
    except Exception as exc:  # pragma: no cover
        _fallo("no se pudo leer la version de los paquetes", str(exc))
        valido = False
    return valido


# --------------------------------------------------------------------------
# Paso 2: modulos y configuracion
# --------------------------------------------------------------------------
def paso_modulos():
    _paso(2, "Modulos del proyecto y configuracion")
    try:
        import config as configuracion
        import historial  # noqa: F401
        import protocolo  # noqa: F401
        import proveedores  # noqa: F401
        from arquitecto import Arquitecto
    except Exception as exc:
        _fallo("import de los modulos del proyecto", str(exc))
        return None, None

    _ok("modulos importados", "config, protocolo, proveedores, historial, arquitecto")

    conf = configuracion.cargar()
    print("  configuracion: {}".format(conf.resumen()))
    problemas = conf.problemas()
    if problemas:
        for fallo in problemas:
            print("  aviso: {}".format(fallo))
        _ok("configuracion cargada (sin credenciales; usa --real solo si las tienes)")
    else:
        _ok("configuracion valida para el proveedor '{}'".format(conf.proveedor))

    try:
        arquitecto = Arquitecto(config=conf)
        _ok("nucleo del Arquitecto instanciado")
    except Exception as exc:
        _fallo("instanciar el Arquitecto", str(exc))
        return conf, None
    return conf, arquitecto


# --------------------------------------------------------------------------
# Paso 3: construccion del servidor MCP
# --------------------------------------------------------------------------
def paso_servidor():
    _paso(3, "Servidor MCP y herramientas registradas")
    try:
        import arquitecto_mcp
    except Exception as exc:
        _fallo("import de arquitecto_mcp", str(exc))
        return None

    try:
        servidor = arquitecto_mcp.construir_servidor()
    except SystemExit as exc:
        _fallo("construir el servidor MCP", str(exc))
        return None
    _ok("servidor FastMCP 'ArquitectoExterno' creado")

    listadas = _listar_herramientas(servidor)
    if not listadas:
        _fallo("no se pudieron listar las herramientas del servidor")
        return servidor

    print("  herramientas: {}".format(", ".join(listadas)))
    faltan = HERRAMIENTAS_ESPERADAS - set(listadas)
    sobran = set(listadas) - HERRAMIENTAS_ESPERADAS
    if faltan:
        _fallo("faltan herramientas", ", ".join(sorted(faltan)))
    else:
        _ok("las {} herramientas esperadas estan registradas".format(len(HERRAMIENTAS_ESPERADAS)))
    if sobran:
        print("  nota: hay herramientas adicionales: {}".format(", ".join(sorted(sobran))))
    return servidor


def _listar_herramientas(servidor):
    try:
        return sorted(servidor._tool_manager._tools.keys())
    except AttributeError:
        pass
    try:
        return sorted(herramienta.name for herramienta in asyncio.run(servidor.list_tools()))
    except Exception:
        return []


def _a_texto(resultado) -> str:
    """Extrae el texto de la respuesta de una herramienta MCP."""
    if isinstance(resultado, tuple) and resultado:
        resultado = resultado[0]
    bloques = resultado if isinstance(resultado, (list, tuple)) else [resultado]
    partes = []
    for bloque in bloques:
        texto = getattr(bloque, "text", None)
        partes.append(texto if texto is not None else str(bloque))
    return "\n".join(partes)


def _invocar(servidor, nombre: str, argumentos: dict):
    """Invoca una herramienta a traves del gestor real de MCP."""
    gestor = getattr(servidor, "_tool_manager", None)
    if gestor is None or not hasattr(gestor, "call_tool"):
        return None, "el SDK no expone _tool_manager.call_tool"
    try:
        resultado = asyncio.run(gestor.call_tool(nombre, argumentos))
    except Exception as exc:
        return None, "{}: {}".format(type(exc).__name__, exc)
    return _a_texto(resultado), None


# --------------------------------------------------------------------------
# Paso 4: invocacion real a traves del protocolo MCP
# --------------------------------------------------------------------------
def paso_invocacion(servidor) -> bool:
    _paso(4, "Invocacion de las herramientas a traves del gestor MCP")
    if servidor is None:
        _fallo("se omite: el servidor no se pudo construir")
        return False

    idea = (
        "Necesito una API en FastAPI con login JWT y un endpoint de salud, "
        "con pruebas automatizadas."
    )
    texto, error = _invocar(
        servidor, "consultar_arquitecto", {"idea_del_usuario": idea}
    )
    if error:
        _fallo("consultar_arquitecto", error)
        return False
    if "ARQUITECTO EXTERNO" not in texto:
        _fallo("consultar_arquitecto devolvio un texto inesperado", texto[:120])
        return False
    _ok("consultar_arquitecto respondio con el plan")
    print("      estado: {}".format(_estado_del_loop(texto)))

    terminada = False
    for intento in range(1, 4):
        texto, error = _invocar(
            servidor,
            "reportar_progreso",
            {
                "resumen_de_lo_hecho": "Implementado el bloque {} del plan y verificado localmente.".format(intento),
                "prompt_original": idea,
                "archivos_tocados": "app/main.py, tests/test_main.py",
            },
        )
        if error:
            _fallo("reportar_progreso", error)
            return False
        print("      informe {}: {}".format(intento, _estado_del_loop(texto)))
        if "TAREA TERMINADA" in texto:
            terminada = True
            break

    if terminada:
        _ok("el loop se cierra solo: el programador deja de iterar")
    else:
        _fallo("el arquitecto no cerro el loop en 3 informes (revisa el modo simulado)")

    texto, error = _invocar(servidor, "ver_estado", {})
    if error or "ESTADO" not in (texto or ""):
        _fallo("ver_estado", error or "respuesta inesperada")
    else:
        _ok("ver_estado responde con el diagnostico")

    texto, error = _invocar(servidor, "exportar_plan", {"ruta": ".verificacion_plan.md"})
    if error or "exportado" not in (texto or "").lower():
        _fallo("exportar_plan", error or "respuesta inesperada")
    else:
        _ok("exportar_plan escribe el archivo")
        _limpiar(RAIZ / ".verificacion_plan.md")

    # El reinicio se prueba al final: borra la memoria y deja el servidor limpio.
    texto, error = _invocar(servidor, "reiniciar_sesion", {})
    if error or "borrada" not in (texto or "").lower():
        _fallo("reiniciar_sesion", error or "respuesta inesperada")
    else:
        _ok("reiniciar_sesion limpia la memoria")

    return terminada


def _estado_del_loop(texto: str) -> str:
    for linea in (texto or "").splitlines():
        if "estado del loop" in linea:
            return linea.strip()
    return "(sin estado)"


def _limpiar(ruta: Path) -> None:
    try:
        ruta.unlink(missing_ok=True)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Principal
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    analizador = argparse.ArgumentParser(
        prog="verificar_servidor", description="Verifica la instalacion del Arquitecto Externo."
    )
    analizador.add_argument(
        "--real", action="store_true", help="usa el proveedor real del .env (consume tokens)"
    )
    argumentos = analizador.parse_args(argv)

    os.environ.setdefault("ARQUITECTO_LOG", "WARNING")
    if not argumentos.real:
        os.environ["ARQUITECTO_MOCK"] = "1"
    os.environ["ARQUITECTO_PERSISTIR"] = "0"

    print("=" * 70)
    print(" VERIFICACION DEL ARQUITECTO EXTERNO ".center(70, "="))
    print("=" * 70)
    print("modo: {}".format("REAL (consume tokens)" if argumentos.real else "SIMULADO (sin red)"))

    paso_dependencias()
    paso_modulos()
    servidor = paso_servidor()
    paso_invocacion(servidor)

    print("")
    print("=" * 70)
    fallos = _resultados.count(False)
    print(
        " RESUMEN: {} comprobaciones OK, {} FALLOS ".format(
            _resultados.count(True), fallos
        ).center(70, "=")
    )
    print("=" * 70)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
