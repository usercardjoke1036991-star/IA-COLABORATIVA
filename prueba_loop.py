"""Simulador de consola del loop Cursor <-> Arquitecto Externo.

Reproduce, sin abrir el IDE, exactamente la misma secuencia que ejecuta la IA de
Cursor cuando llama a las herramientas MCP:

    consultar_arquitecto  ->  (el PROGRAMADOR programa)  ->  reportar_progreso
                          ->  ... hasta que el loop se cierra

Sirve para validar el sistema completo de tres formas:

* ``python prueba_loop.py --mock``   -> sin red, sin API key (mecanica del loop).
* ``python prueba_loop.py``          -> contra tu proveedor real configurado.
* ``python prueba_loop.py --turnos 5 --bloqueo`` -> forzando mas iteraciones y
  un bloqueo, para ver como el arquitecto corrige el rumbo.

Opciones utiles:
    --mock            activa el proveedor simulado (ARQUITECTO_MOCK=1)
    --idea "..."      idea a dimensionar (por defecto, una de ejemplo)
    --contexto "..."  contexto adicional que se envia al arquitecto
    --turnos N        maximo de informes de progreso (def. 4)
    --bloqueo         inyecta un bloqueo en el segundo informe
    --persistir       guarda el historial en disco (por defecto no lo toca)
    --exportar        escribe PLAN_ARQUITECTO.md con el ultimo plan recibido
"""

from __future__ import annotations

import argparse
import os
import sys

IDEA_EJEMPLO = (
    "Quiero un bot de Telegram en Python que escuche eventos de una wallet "
    "Web3 y guarde los movimientos en Google Sheets, con reintentos."
)


def _linea(caracter: str = "-", ancho: int = 58) -> None:
    print(caracter * ancho)


def _titulo(texto: str, ancho: int = 58) -> None:
    print("=" * ancho)
    print(" {} ".format(texto).center(ancho, "="))
    print("=" * ancho)


def _configurar_entorno(argumentos) -> None:
    """Ajusta las variables de entorno ANTES de instanciar el Arquitecto."""
    os.environ.setdefault("ARQUITECTO_LOG", "WARNING")
    if argumentos.mock:
        os.environ["ARQUITECTO_MOCK"] = "1"
    if argumentos.proveedor:
        os.environ["ARQUITECTO_PROVIDER"] = argumentos.proveedor
    # Por defecto el simulador no ensucia el historial real del proyecto.
    os.environ["ARQUITECTO_PERSISTIR"] = "1" if argumentos.persistir else "0"


def _resumen_simulado(turno: int) -> str:
    """Texto que 'escribiria' la IA de Cursor resumiendo su trabajo."""
    if turno == 1:
        return (
            "Implemente el primer bloque del plan: cree la estructura de carpetas, "
            "el modulo principal y las funciones base. Ejecute la verificacion local "
            "y pasa sin errores."
        )
    return (
        "Turno {}: implemente el bloque de trabajo indicado por el arquitecto, "
        "ajuste los modulos afectados y volvi a lanzar la verificacion local.".format(
            turno
        )
    )


def _construir_analizador() -> argparse.ArgumentParser:
    analizador = argparse.ArgumentParser(
        prog="prueba_loop",
        description="Simula el loop completo entre la IA de Cursor y el Arquitecto.",
    )
    analizador.add_argument("--mock", action="store_true", help="proveedor simulado, sin red")
    analizador.add_argument("--proveedor", help="deepseek | openrouter | openai | custom")
    analizador.add_argument("--idea", default=IDEA_EJEMPLO, help="idea a dimensionar")
    analizador.add_argument("--contexto", default="", help="contexto extra para el arquitecto")
    analizador.add_argument("--turnos", type=int, default=4, help="informes de progreso (def. 4)")
    analizador.add_argument("--bloqueo", action="store_true", help="inyecta un bloqueo en el turno 2")
    analizador.add_argument("--persistir", action="store_true", help="usa el historial en disco")
    analizador.add_argument("--exportar", action="store_true", help="escribe PLAN_ARQUITECTO.md")
    return analizador


def main(argv=None) -> int:
    argumentos = _construir_analizador().parse_args(argv)
    _configurar_entorno(argumentos)

    # Import diferido: las variables de entorno deben estar puestas antes de cargar.
    import config as configuracion
    from arquitecto import Arquitecto

    configuracion.configurar_log(os.getenv("ARQUITECTO_LOG", "WARNING"))
    config = configuracion.cargar()

    _titulo("SIMULADOR DEL LOOP  CURSOR <-> ARQUITECTO")
    print("configuracion: {}".format(config.resumen()))
    print("modo          : {}".format("SIMULADO (sin red)" if config.modo_mock else "REAL"))
    _linea()
    print("IDEA DEL USUARIO:")
    print(argumentos.idea)
    _linea()

    arquitecto = Arquitecto(config=config)
    informes = 0
    terminada = False
    hubo_error = False

    # --- Paso 1: consultar al arquitecto (lo mismo que hace Cursor) --------
    respuesta = arquitecto.consultar(argumentos.idea, argumentos.contexto)
    print(respuesta.formatear())
    if respuesta.error:
        hubo_error = True
    elif respuesta.terminada:
        terminada = True

    # --- Paso 2: el PROGRAMADOR programa y reporta en bucle ---------------
    while not terminada and not hubo_error and informes < argumentos.turnos:
        informes += 1
        bloqueo = ""
        if argumentos.bloqueo and informes == 2:
            bloqueo = "El webhook remoto devuelve 403 al firmar el payload; no se por que."

        if bloqueo:
            _linea()
            print("[SIMULACION] el PROGRAMADOR esta bloqueado y pide ayuda:")
            print("  {}".format(bloqueo))

        respuesta = arquitecto.reportar_progreso(
            resumen_de_lo_hecho=_resumen_simulado(informes),
            prompt_original=argumentos.idea,
            archivos_tocados="src/main.py, src/verificacion.py, README.md",
            bloqueo=bloqueo,
        )
        print(respuesta.formatear())
        if respuesta.error:
            hubo_error = True
        elif respuesta.terminada:
            terminada = True

    # --- Cierre: resumen del resultado ------------------------------------
    if argumentos.exportar and not hubo_error:
        _linea()
        print(arquitecto.exportar_plan())

    _titulo("RESULTADO DE LA PRUEBA")
    print("informes de progreso enviados : {}".format(informes))
    print("turnos del arquitecto         : {}".format(arquitecto.historial.turno()))
    if hubo_error:
        print("estado                        : ERROR (revisa el mensaje anterior)")
        return 1
    if terminada:
        print("estado                        : LOOP CERRADO por el arquitecto")
        print("siguiente accion              : el PROGRAMADOR no debe iterar mas")
        return 0
    print("estado                        : LIMITE DE TURNOS ALCANZADO")
    print("siguiente accion              : sube --turnos o revisa el plan generado")
    return 1


if __name__ == "__main__":
    sys.exit(main())
