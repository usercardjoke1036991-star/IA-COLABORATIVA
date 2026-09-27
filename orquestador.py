"""Orquestador autonomo: idea -> proyecto -> plan -> codigo -> pruebas -> commit.

Es la pieza que une todo lo construido y permite lanzar una idea completa desde
la consola, sin IDE delante:

1. Crea el proyecto (carpeta aislada + plantillas + git) con :mod:`fabrica`.
2. El ARQUITECTO (modelo fuerte) define el plan inicial.
3. El PROGRAMADOR (segundo modelo) entrega los archivos completos.
4. Se escriben en el proyecto, se ejecutan las pruebas y, si fallan, se le
   devuelve el error al PROGRAMADOR para que corrija.
5. Se hace commit y se le reporta el progreso al ARQUITECTO, que dicta los
   siguientes pasos hasta cerrar el loop (``TAREA TERMINADA``).

Dos modos de ejecucion:

* ``interno``: los dos modelos externos trabajan solos (DeepSeek R1 planifica
  y DeepSeek V3 escribe). Es el modo por defecto y no necesita nada instalado.
* ``cline``: cada turno se delega a la IA del IDE en la consola
  (``cline --cwd <proyecto> "<prompt>"``), util si prefieres que programe el
  agente de Cline con acceso a las herramientas MCP.

Uso:
    python orquestador.py --idea "Bot que vigila precios y avisa por Telegram"
    python orquestador.py --idea "..." --modo cline --turnos 3 --publicar
    python orquestador.py --idea "..." --sin-probar --plantillas python,fastapi
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import config as configuracion
import fabrica
import herramientas_archivos as archivos
import plantillas
import protocolo
import rutas
from arquitecto import Arquitecto
from ejecutor import Ejecutor

ANCHO = 72


@dataclass
class Resultado:
    """Resumen de una ejecucion del orquestador."""

    proyecto: str = ""
    ruta: str = ""
    turnos: int = 0
    terminado: bool = False
    archivos: List[str] = field(default_factory=list)
    commits: List[str] = field(default_factory=list)
    pruebas: str = "no ejecutadas"
    github: str = ""
    log: List[str] = field(default_factory=list)

    def formatear(self) -> str:
        """Informe final legible para la consola."""
        lineas = [
            "=" * ANCHO,
            " RESULTADO DEL ORQUESTADOR ".center(ANCHO, "="),
            "=" * ANCHO,
            "proyecto   : {}".format(self.proyecto),
            "carpeta    : {}".format(self.ruta),
            "turnos     : {}".format(self.turnos),
            "terminado  : {}".format(self.terminado),
            "pruebas    : {}".format(self.pruebas),
            "archivos   : {}".format(len(self.archivos)),
        ]
        for ruta in self.archivos:
            lineas.append("   - {}".format(ruta))
        if self.commits:
            lineas.append("commits    : {}".format(", ".join(self.commits)))
        if self.github:
            lineas.append("github     : {}".format(self.github))
        lineas.append("=" * ANCHO)
        return "\n".join(lineas)


def _paso(mensaje: str) -> None:
    """Imprime un paso del proceso con marca de tiempo."""
    print("[{}] {}".format(datetime.now().strftime("%H:%M:%S"), mensaje))


class Orquestador:
    """Bucle autonomo ARQUITECTO <-> PROGRAMADOR sobre un proyecto real."""

    def __init__(
        self,
        idea: str,
        proyecto: str = "",
        descripcion: str = "",
        seleccion: Optional[List[str]] = None,
        publicar: bool = False,
        probar: bool = True,
        intentos: int = 1,
        modo: str = "",
    ) -> None:
        self.idea = (idea or "").strip()
        if not self.idea:
            raise ValueError("Falta la idea: usa --idea \"tu idea en una frase\".")

        self.cfg = configuracion.cargar_fabrica()
        self.nombre = rutas.normalizar_nombre(proyecto or self.idea[:60])
        self.descripcion = descripcion or self.idea[:200]
        self.seleccion = seleccion or self.cfg.plantillas_por_defecto
        self.publicar = publicar
        self.probar = probar
        self.intentos = max(0, int(intentos))
        self.modo = modo or self.cfg.orquestador
        self.arquitecto = Arquitecto()
        self.programador = Ejecutor()
        self.plan = ""
        self.resultado = Resultado(proyecto=self.nombre)

    # -- Proyecto ---------------------------------------------------------
    def asegurar_proyecto(self) -> Path:
        """Crea el proyecto si no existe y devuelve su carpeta."""
        destino = rutas.ruta_de_proyecto(self.nombre)
        if destino.exists() and any(
            hijo for hijo in destino.iterdir() if hijo.name != ".git"
        ):
            _paso("El proyecto '{}' ya existe: se reutiliza su carpeta.".format(self.nombre))
            return destino

        _paso("Creando el proyecto '{}' con plantillas: {}".format(
            self.nombre, ", ".join(self.seleccion)
        ))
        print(
            fabrica.crear_proyecto(
                self.nombre,
                self.descripcion,
                self.seleccion,
                con_git=True,
                publicar=False,
            )
        )
        return rutas.ruta_de_proyecto(self.nombre)

    # -- Pruebas ----------------------------------------------------------
    def ejecutar_pruebas(self) -> tuple:
        """Lanza las pruebas del proyecto (pytest).

        Returns:
            ``(codigo, salida)``. ``codigo`` es ``-1`` cuando no habia pruebas o
            no se pudieron ejecutar (no se considera fallo).
        """
        destino = rutas.ruta_de_proyecto(self.nombre)
        interprete = destino / "venv" / "Scripts" / "python.exe"
        if not interprete.exists():
            interprete = destino / "venv" / "bin" / "python"
        if not interprete.exists():
            interprete = Path(sys.executable)

        carpetas = [c for c in ("tests", "pruebas") if (destino / c).exists()]
        if not carpetas:
            return -1, ""

        comando = [str(interprete), "-m", "pytest", "-q"] + carpetas
        _paso("Ejecutando pruebas: {}".format(" ".join(comando)))
        try:
            proceso = subprocess.run(
                comando,
                cwd=str(destino),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=900,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return -1, "No se pudieron ejecutar las pruebas: {}".format(exc)

        salida = "{}\n{}".format(proceso.stdout or "", proceso.stderr or "").strip()
        if "No module named pytest" in salida or "No module named 'pytest'" in salida:
            return -1, "pytest no esta instalado en el interprete usado:\n{}".format(salida[-400:])
        return proceso.returncode, salida or "(pytest no devolvio salida)"

    # -- Un turno de trabajo ----------------------------------------------
    def aplicar_entrega(self, entregados) -> List[str]:
        """Escribe en el proyecto los archivos que entrego el PROGRAMADOR."""
        mensajes = archivos.escribir_varios(self.nombre, dict(entregados))
        for mensaje in mensajes:
            _paso("  {}".format(mensaje))
        return [ruta for ruta, _ in entregados]

    def turno_interno(self, tarea: str) -> tuple:
        """Un turno completo: programar, aplicar, probar, corregir y commitear.

        Returns:
            ``(ok, resumen, bloqueo)``: lo que se hara llegar al ARQUITECTO.
        """
        contexto = self.contexto()
        respuesta = self.programador.implementar(
            tarea, plan=self.plan, contexto=contexto, proyecto=self.nombre
        )
        if respuesta.error:
            return False, "El PROGRAMADOR fallo antes de entregar codigo.", respuesta.error

        entregados = self.programador.archivos_de(respuesta)
        if not entregados:
            return (
                False,
                "El PROGRAMADOR respondio sin archivos en el formato acordado.",
                "Respuesta fuera de formato:\n{}".format(respuesta.contenido[:800]),
            )

        aplicados = self.aplicar_entrega(entregados)
        self.resultado.archivos.extend(aplicados)

        prueba = "no ejecutadas"
        if self.probar:
            codigo, salida = self.ejecutar_pruebas()
            if codigo == -1:
                prueba = "no hay pruebas que ejecutar"
            elif codigo == 0:
                prueba = "pruebas en verde"
            else:
                prueba = "pruebas en rojo"
                intento = 0
                while intento < self.intentos and codigo not in (0, -1):
                    intento += 1
                    _paso("Correccion {}/{} tras el fallo de las pruebas".format(intento, self.intentos))
                    correccion = self.programador.corregir(salida[-4000:], intento=intento)
                    if correccion.error:
                        break
                    corregidos = self.programador.archivos_de(correccion)
                    if corregidos:
                        self.resultado.archivos.extend(self.aplicar_entrega(corregidos))
                    codigo, salida = self.ejecutar_pruebas()
                prueba = "pruebas en verde" if codigo == 0 else "pruebas en rojo"
        self.resultado.pruebas = prueba

        commit = fabrica.hacer_commit(
            self.nombre, "feat: {}".format(tarea.splitlines()[0][:70])
        )
        if commit.lower().startswith("commit "):
            self.resultado.commits.append(commit.split(":")[0].replace("Commit ", "").strip())

        resumen = "Turno aplicado: {} archivo(s): {}.\n{}".format(
            len(aplicados), ", ".join(aplicados), prueba
        )
        bloqueo = ""
        if prueba == "pruebas en rojo":
            bloqueo = "Las pruebas siguen fallando. Ultima salida:\n{}".format(salida[-1500:])
        return True, resumen, bloqueo

    def contexto(self) -> str:
        """Contexto que recibe el PROGRAMADOR: objetivos, ruta y estructura actual."""
        try:
            arbol = archivos.listar_proyecto(self.nombre, profundidad=2, max_entradas=80)
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            arbol = "(no se pudo listar: {})".format(exc)
        return "\n".join(
            [
                "OBJETIVO DEL USUARIO: {}".format(self.idea),
                "PROYECTO: {} (carpeta: {})".format(
                    self.nombre, rutas.ruta_de_proyecto(self.nombre)
                ),
                "ESTRUCTURA ACTUAL:\n{}".format(arbol),
            ]
        )

    # -- Bucles -----------------------------------------------------------
    def plan_inicial(self) -> Optional[str]:
        """Pide el plan al ARQUITECTO. Devuelve ``None`` si hubo error."""
        _paso(
            "Pidiendo el plan inicial al ARQUITECTO ({}/{})".format(
                self.arquitecto.config.proveedor, self.arquitecto.config.modelo
            )
        )
        respuesta = self.arquitecto.consultar(self.idea, contexto_del_codigo=self.contexto())
        print(respuesta.formatear())
        if respuesta.error:
            self.resultado.log.append("plan: {}".format(respuesta.error))
            return None
        self.plan = respuesta.contenido
        return self.plan

    def correr_interno(self, turnos: int) -> Resultado:
        """Bucle autonomo con los dos modelos externos (sin IDE)."""
        self.resultado.ruta = str(self.asegurar_proyecto())
        if self.plan_inicial() is None:
            return self.resultado

        tarea = (
            "Implementa el PRIMER paso del plan, ni mas ni menos. "
            "Si el plan ya trae codigo de arranque, respetalo."
        )
        for numero in range(1, max(1, turnos) + 1):
            self.resultado.turnos = numero
            _paso(
                "TURNO {}/{} con el PROGRAMADOR ({}/{})".format(
                    numero,
                    turnos,
                    self.programador.config.proveedor,
                    self.programador.config.modelo,
                )
            )
            _, resumen, bloqueo = self.turno_interno(tarea)
            _paso(resumen)
            if bloqueo:
                _paso("Bloqueo detectado: se lo contamos al ARQUITECTO.")

            informe = self.arquitecto.reportar_progreso(
                resumen_de_lo_hecho=resumen,
                prompt_original=self.idea,
                archivos_tocados=", ".join(sorted(set(self.resultado.archivos))),
                bloqueo=bloqueo,
            )
            print(informe.formatear())
            if informe.error:
                self.resultado.log.append("informe: {}".format(informe.error))
                break
            if informe.terminada:
                self.resultado.terminado = True
                _paso("El ARQUITECTO declaro la tarea terminada.")
                break
            self.plan = informe.contenido
            tarea = "Implementa el SIGUIENTE paso que acaba de indicar el arquitecto."

        return self.cerrar()

    def prompt_cline(self, numero: int, turnos: int) -> str:
        """Prompt que recibe Cline CLI para trabajar dentro del proyecto."""
        return "\n".join(
            [
                "Eres el PROGRAMADOR de este proyecto. Trabaja SIEMPRE dentro de la carpeta actual.",
                "",
                "OBJETIVO ORIGINAL DEL USUARIO:",
                self.idea,
                "",
                "PLAN DEL ARQUITECTO (ronda {} de {}):".format(numero, turnos),
                self.plan or "(sin plan)",
                "",
                "INSTRUCCIONES:",
                "1. Implementa el siguiente paso pendiente del plan, completo y ejecutable.",
                "2. No reformatees archivos que no hagan falta; nada de cambios esteticos.",
                "3. Deja el codigo con type hints y docstrings breves.",
                "4. Si hay pruebas (carpetas tests/ o pruebas/), hazlas pasar con:",
                r"   venv\Scripts\python.exe -m pytest -q",
                "5. Al terminar, resume en dos lineas que hiciste y el estado de las pruebas.",
            ]
        )

    def correr_cline(self, turnos: int) -> Resultado:
        """Bucle delegando cada turno a la IA del IDE en consola (Cline CLI)."""
        self.resultado.ruta = str(self.asegurar_proyecto())
        if self.plan_inicial() is None:
            return self.resultado

        for numero in range(1, max(1, turnos) + 1):
            self.resultado.turnos = numero
            comando = [
                self.cfg.cline_comando,
                "--cwd",
                self.resultado.ruta,
                "--auto-approve",
                "true" if self.cfg.cline_auto else "false",
                "--timeout",
                "1800",
                self.prompt_cline(numero, turnos),
            ]
            _paso("TURNO {}/{} delegado a '{}'".format(numero, turnos, self.cfg.cline_comando))
            try:
                proceso = subprocess.run(
                    comando,
                    cwd=self.resultado.ruta,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=3600,
                    shell=False,
                )
            except FileNotFoundError:
                print(
                    "No se encontro '{}'. Instala Cline CLI o usa "
                    "ARQUITECTO_ORQUESTADOR=interno.".format(self.cfg.cline_comando)
                )
                self.resultado.log.append("cline no encontrado")
                self.resultado.turnos = numero - 1
                return self.cerrar()
            except subprocess.TimeoutExpired:
                print("Cline supero el tiempo maximo: turno cancelado.")
                self.resultado.log.append("timeout de cline")
                return self.cerrar()

            salida = "{}\n{}".format(proceso.stdout or "", proceso.stderr or "").strip()
            print(salida[-3000:])
            self.resultado.pruebas = "delegadas a Cline"

            commit = fabrica.hacer_commit(
                self.nombre, "feat: ronda {} del orquestador (cline)".format(numero)
            )
            if commit.lower().startswith("commit "):
                self.resultado.commits.append(
                    commit.split(":")[0].replace("Commit ", "").strip()
                )

            informe = self.arquitecto.reportar_progreso(
                resumen_de_lo_hecho=(
                    "Ronda {} ejecutada por Cline CLI (codigo {}). Ultimas lineas:\n{}".format(
                        numero,
                        "OK" if proceso.returncode == 0 else "con errores",
                        salida[-1200:],
                    )
                ),
                prompt_original=self.idea,
                archivos_tocados="(los determina Cline; revisa git status)",
            )
            print(informe.formatear())
            if informe.error:
                break
            if informe.terminada:
                self.resultado.terminado = True
                break
            self.plan = informe.contenido

        return self.cerrar()

    # -- Cierre -----------------------------------------------------------
    def cerrar(self) -> Resultado:
        """Publica si se pidio, guarda el informe y devuelve el resultado."""
        if self.publicar and self.resultado.turnos:
            try:
                self.resultado.github = fabrica.publicar_en_github(self.nombre)
                _paso("Proyecto publicado: {}".format(self.resultado.github))
            except fabrica.ErrorFabrica as exc:
                _paso("No se pudo publicar en GitHub: {}".format(str(exc).splitlines()[0]))
        self.guardar_informe()
        return self.resultado

    def guardar_informe(self) -> Path:
        """Escribe el informe de la ejecucion en datos/orquestador_<proyecto>.txt."""
        destino = configuracion.RAIZ_PROYECTO / "datos" / "orquestador_{}.txt".format(self.nombre)
        contenido = "{}\n\nGENERADO: {}\n".format(
            self.resultado.formatear(), datetime.now().isoformat(timespec="seconds")
        )
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(contenido, encoding="utf-8")
            _paso("Informe guardado en {}".format(destino))
        except OSError as exc:
            print("No se pudo guardar el informe: {}".format(exc))
        return destino


# --------------------------------------------------------------------------
# Linea de comandos
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    """Lanza una idea completa de principio a fin desde la consola."""
    analizador = argparse.ArgumentParser(
        prog="orquestador",
        description="Crea el proyecto, pide el plan, programa, prueba, commitea y publica.",
    )
    analizador.add_argument("--idea", required=True, help="la idea del usuario, en una frase")
    analizador.add_argument("--proyecto", default="", help="nombre del proyecto (por defecto, de la idea)")
    analizador.add_argument("--descripcion", default="", help="descripcion para el README")
    analizador.add_argument("--plantillas", default="", help="claves separadas por comas (python,web3...)")
    analizador.add_argument("--turnos", type=int, default=0, help="rondas maximas (def. ARQUITECTO_LIMITE_TURNOS)")
    analizador.add_argument("--intentos", type=int, default=1, help="correcciones por turno si fallan las pruebas")
    analizador.add_argument("--modo", default="", choices=["", "interno", "cline"], help="quien programa")
    analizador.add_argument("--auto", action="store_true", help="auto-aprobar los tools de Cline CLI")
    analizador.add_argument("--publicar", action="store_true", help="sube el proyecto a GitHub (gh)")
    analizador.add_argument("--sin-probar", action="store_true", help="no ejecuta pytest en cada turno")
    analizador.add_argument("--preparar", action="store_true", help="crea el venv e instala requirements.txt")
    opciones = analizador.parse_args(argv)

    os.environ.setdefault("ARQUITECTO_LOG", "INFO")
    if opciones.auto:
        os.environ["ARQUITECTO_CLINE_AUTO"] = "true"

    try:
        orquestador = Orquestador(
            idea=opciones.idea,
            proyecto=opciones.proyecto,
            descripcion=opciones.descripcion,
            seleccion=plantillas.interpretar_seleccion(opciones.plantillas) or None,
            publicar=opciones.publicar,
            probar=not opciones.sin_probar,
            intentos=opciones.intentos,
            modo=opciones.modo,
        )
    except (ValueError, rutas.ErrorRuta) as exc:
        print("No se puede empezar: {}".format(exc))
        return 2

    fabrica_cfg = orquestador.cfg
    turnos = opciones.turnos or fabrica_cfg.limite_turnos
    print("=" * ANCHO)
    print(" ORQUESTADOR DE LA FABRICA DE IA ".center(ANCHO, "="))
    print("=" * ANCHO)
    print("idea       : {}".format(opciones.idea))
    print("proyecto   : {} -> {}".format(orquestador.nombre, rutas.ruta_de_proyecto(orquestador.nombre)))
    print("plantillas : {}".format(", ".join(orquestador.seleccion)))
    print("modo       : {} (turnos={}, intentos={})".format(orquestador.modo, turnos, orquestador.intentos))
    print("arquitecto : {} / {}".format(orquestador.arquitecto.config.proveedor, orquestador.arquitecto.config.modelo))
    print("programador: {} / {}".format(orquestador.programador.config.proveedor, orquestador.programador.config.modelo))
    print("=" * ANCHO)

    if opciones.preparar:
        orquestador.asegurar_proyecto()
        print(fabrica.preparar_entorno(orquestador.nombre, instalar=True))

    try:
        resultado = (
            orquestador.correr_cline(turnos)
            if orquestador.modo == "cline"
            else orquestador.correr_interno(turnos)
        )
    except (fabrica.ErrorFabrica, archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
        print("\nEl orquestador se detuvo: {}".format(exc))
        return 1
    except Exception as exc:  # defensivo: nunca dejar una traza cruda al usuario
        print("\nFallo inesperado del orquestador ({}): {}".format(type(exc).__name__, exc))
        print("Revisa el .env y los logs; el proyecto sigue en disco con lo hecho hasta aqui.")
        return 1

    print("")
    print(resultado.formatear())
    return 0 if resultado.turnos else 1


if __name__ == "__main__":
    sys.exit(main())
