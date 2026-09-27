"""Nucleo del sistema multi-agente: el Arquitecto y su loop de colaboracion.

Este modulo NO depende del SDK de MCP. Asi la misma logica se puede usar desde
el servidor MCP (``arquitecto_mcp.py``), desde un script de consola
(``prueba_loop.py``) o desde cualquier otra integracion futura.

El loop completo
----------------
1. El usuario escribe un prompt en Cursor.
2. El PROGRAMADOR (IA de Cursor) llama a :meth:`Arquitecto.consultar`.
3. El Arquitecto dimensiona la idea y devuelve un plan accionable.
4. El PROGRAMADOR implementa el codigo.
5. El PROGRAMADOR llama a :meth:`Arquitecto.reportar_progreso` con un resumen.
6. El Arquitecto valida lo hecho y dicta los siguientes pasos.
7. Se repite 4-6 hasta que el Arquitecto emita el marcador de fin, momento en
   el que el loop se detiene (no hay bucle infinito).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import config as configuracion
import protocolo
from config import Config
from historial import Historial
from proveedores import ErrorProveedor, ProveedorLLM, crear_proveedor

log = logging.getLogger("arquitecto.nucleo")

NOMBRE_ARCHIVO_PLAN = "PLAN_ARQUITECTO.md"


@dataclass
class Respuesta:
    """Resultado de una consulta al Arquitecto, listo para devolver al IDE."""

    contenido: str = ""
    turno: int = 0
    proveedor: str = ""
    modelo: str = ""
    terminada: bool = False
    segundos: float = 0.0
    error: Optional[str] = None
    meta: dict = field(default_factory=dict)

    def formatear(self) -> str:
        """Texto que el PROGRAMADOR vera en el chat / en el resultado de MCP."""
        if self.error:
            return protocolo.formatear_error(self.error)
        return protocolo.formatear_respuesta(
            contenido=self.contenido,
            turno=self.turno,
            proveedor=self.proveedor,
            modelo=self.modelo,
            terminada=self.terminada,
            segundos=self.segundos,
        )


class Arquitecto:
    """Orquesta historial + proveedor + protocolo."""

    def __init__(
        self,
        config: Optional[Config] = None,
        proveedor: Optional[ProveedorLLM] = None,
        historial: Optional[Historial] = None,
    ) -> None:
        self.config = config or configuracion.cargar()
        self.historial = historial if historial is not None else Historial(self.config)
        self.proveedor = proveedor if proveedor is not None else crear_proveedor(self.config)
        self.idea_original = ""
        self.plan_actual = ""
        log.info("Arquitecto listo. %s", self.config.resumen())

    # -- Herramienta 1: dimensionar la idea -------------------------------
    def consultar(self, idea_del_usuario: str, contexto_del_codigo: str = "") -> Respuesta:
        """Pide al Arquitecto el plan de ataque inicial para una idea."""
        if not idea_del_usuario or not idea_del_usuario.strip():
            return self._error(
                "La idea del usuario esta vacia: no hay nada que dimensionar."
            )

        self.idea_original = idea_del_usuario.strip()
        self.historial.registrar_idea(idea_del_usuario, contexto_del_codigo)
        respuesta = self._llamar_al_proveedor()
        if respuesta.error:
            return respuesta

        self.plan_actual = respuesta.contenido
        self.historial.registrar_plan(respuesta.contenido)
        respuesta.turno = self.historial.turno()
        respuesta.meta["plan_disponible"] = True
        return respuesta

    # -- Herramienta 2: cerrar el ciclo -----------------------------------
    def reportar_progreso(
        self,
        resumen_de_lo_hecho: str,
        prompt_original: str = "",
        archivos_tocados: str = "",
        bloqueo: str = "",
    ) -> Respuesta:
        """Informa de lo implementado y recibe los siguientes pasos."""
        if not resumen_de_lo_hecho or not resumen_de_lo_hecho.strip():
            return self._error(
                "El resumen de lo hecho esta vacio. Describe que se implemento, "
                "que archivos se tocaron y si hay algun bloqueo."
            )

        if prompt_original and prompt_original.strip():
            self.idea_original = prompt_original.strip()
        elif not self.idea_original:
            log.warning("reportar_progreso sin objetivo original en memoria.")

        self.historial.registrar_progreso(
            resumen=resumen_de_lo_hecho,
            prompt_original=self.idea_original,
            archivos_tocados=archivos_tocados,
            bloqueo=bloqueo,
        )
        respuesta = self._llamar_al_proveedor()
        if respuesta.error:
            return respuesta

        self.historial.registrar_directriz(respuesta.contenido)
        respuesta.turno = self.historial.turno()
        respuesta.meta["archivos_tocados"] = archivos_tocados.strip()
        return respuesta

    # -- Utilidades --------------------------------------------------------
    def estado(self) -> str:
        """Diagnostico legible del estado del loop (no gasta tokens)."""
        cabecera = "=" * 58
        objetivo = self.idea_original or "(no definido)"
        if len(objetivo) > 117:
            objetivo = objetivo[:117] + "..."
        problemas = self.config.problemas()
        lineas = [
            cabecera,
            " ARQUITECTO EXTERNO - ESTADO ".center(58, "="),
            "-" * 58,
            "configuracion: {}".format(self.config.resumen()),
            "turnos del arquitecto: {}".format(self.historial.turno()),
            "entradas en memoria: {}".format(self.historial.conteo()),
            "sesion iniciada: {}".format(self.historial.creado),
            "objetivo original: {}".format(objetivo),
            "problemas de configuracion: {}".format(
                "; ".join(problemas) if problemas else "ninguno"
            ),
            "-" * 58,
            "ultimos turnos:",
            self.historial.resumen_texto(6),
            cabecera,
        ]
        return "\n".join(lineas)

    def reiniciar(self) -> str:
        """Borra la memoria y arranca una sesion limpia."""
        self.historial.limpiar()
        self.idea_original = ""
        self.plan_actual = ""
        return (
            "Memoria del Arquitecto borrada. Sesion nueva lista.\n"
            "Vuelve a llamar a `consultar_arquitecto` con la nueva idea."
        )

    def exportar_plan(self, ruta: str = NOMBRE_ARCHIVO_PLAN) -> str:
        """Escribe el ultimo plan/directriz en un Markdown del proyecto.

        Sirve como "contrato" que el PROGRAMADOR puede releer sin gastar tokens
        y que queda versionado junto al codigo.
        """
        contenido = self.plan_actual or self.historial.ultima_directriz()
        if not contenido:
            return "No hay ningun plan todavia. Llama primero a `consultar_arquitecto`."

        destino = Path(ruta)
        if not destino.is_absolute():
            destino = configuracion.RAIZ_PROYECTO / destino
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(self._documento_plan(contenido), encoding="utf-8")
        except OSError as exc:
            return "No se pudo escribir {}: {}".format(destino, exc)

        return "Plan exportado a: {}\nRevisalo antes de seguir implementando.".format(
            destino
        )

    def _documento_plan(self, contenido: str) -> str:
        from datetime import datetime

        momento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            "# Plan del Arquitecto Externo\n\n"
            "- generado: {momento}\n"
            "- proveedor: {proveedor}\n"
            "- modelo: {modelo}\n"
            "- turno: {turno}\n"
            "- objetivo: {objetivo}\n\n"
            "---\n\n{contenido}\n\n---\n\n"
            "## Instrucciones para el PROGRAMADOR\n\n"
            "- Implementa los pasos en el orden indicado, sin agregar pasos extra.\n"
            "- Al terminar un bloque de trabajo llama a `reportar_progreso` con el\n"
            "  resumen, los archivos tocados y cualquier bloqueo.\n"
            "- Si el resultado indica `estado del loop: TAREA TERMINADA`, detente:\n"
            "  verifica los criterios de aceptacion y resume para el usuario.\n"
        ).format(
            momento=momento,
            proveedor=self.config.proveedor,
            modelo=self.config.modelo,
            turno=self.historial.turno(),
            objetivo=self.idea_original or "(no definido)",
            contenido=contenido.strip(),
        )

    # -- Internos ---------------------------------------------------------
    def _llamar_al_proveedor(self) -> Respuesta:
        """Envia el historial al proveedor y normaliza el resultado."""
        mensajes = self.historial.mensajes_para_llm(protocolo.SYSTEM_PROMPT)
        inicio = time.time()
        try:
            contenido = self.proveedor.consultar(mensajes)
        except ErrorProveedor as exc:
            log.error("Fallo el proveedor: %s", exc)
            return self._error(str(exc))
        except Exception as exc:  # defensivo: el servidor MCP nunca debe caerse
            log.exception("Error inesperado del proveedor")
            return self._error("Error inesperado del proveedor: {}".format(exc))

        return Respuesta(
            contenido=contenido,
            turno=self.historial.turno(),
            proveedor=self.config.proveedor,
            modelo=self.config.modelo,
            terminada=protocolo.tarea_terminada(contenido),
            segundos=time.time() - inicio,
        )

    def _error(self, mensaje: str) -> Respuesta:
        return Respuesta(
            error=mensaje,
            proveedor=self.config.proveedor,
            modelo=self.config.modelo,
            turno=self.historial.turno(),
        )
