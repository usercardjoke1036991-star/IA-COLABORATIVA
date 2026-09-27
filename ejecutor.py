"""Rol PROGRAMADOR externo: el segundo modelo, el que escribe el codigo.

El ARQUITECTO piensa (modelo fuerte, por ejemplo ``deepseek-reasoner``) y el
PROGRAMADOR escribe (modelo rapido y barato, ``deepseek-chat``). Este modulo
implementa el segundo rol reutilizando la misma maquinaria: historial propio,
proveedor propio y un system prompt que devuelve **archivos completos** en un
formato que :func:`protocolo.extraer_archivos` sabe analizar.

Flujo tipico (lo orquesta ``orquestador.py`` o las herramientas MCP):

1. El ARQUITECTO entrega el plan -> ``Arquitecto.consultar``.
2. El PROGRAMADOR escribe los archivos -> :meth:`Ejecutor.implementar`.
3. Los archivos se vuelcan al proyecto (``herramientas_archivos`` / ``fabrica``).
4. Si la ejecucion falla, el error real se le devuelve con
   :meth:`Ejecutor.corregir` hasta agotar los intentos.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

import config as configuracion
import protocolo
from arquitecto import Respuesta
from config import Config
from historial import Historial
from proveedores import ErrorProveedor, ProveedorLLM, crear_proveedor

log = logging.getLogger("arquitecto.ejecutor")


class Ejecutor:
    """Orquesta el rol PROGRAMADOR: historial + proveedor + contrato de archivos."""

    def __init__(
        self,
        config: Optional[Config] = None,
        proveedor: Optional[ProveedorLLM] = None,
        historial: Optional[Historial] = None,
    ) -> None:
        self.config = config or configuracion.cargar_ejecutor()
        self.historial = historial if historial is not None else Historial(self.config)
        self.proveedor = proveedor if proveedor is not None else crear_proveedor(self.config)
        self.ultima_entrega = ""
        log.info("Ejecutor listo. %s", self.config.resumen())

    # -- Herramientas ------------------------------------------------------
    def implementar(
        self,
        tarea: str,
        plan: str = "",
        contexto: str = "",
        proyecto: str = "",
    ) -> Respuesta:
        """Pide al PROGRAMADOR los archivos completos de una tarea."""
        if not (tarea or "").strip():
            return self._error("La tarea esta vacia: no hay nada que programar.")

        mensaje = protocolo.bloque_implementacion(tarea, plan, contexto, proyecto)
        return self._llamar(mensaje)

    def corregir(
        self,
        error: str,
        codigo_previo: str = "",
        intento: int = 1,
    ) -> Respuesta:
        """Devuelve un error de ejecucion al PROGRAMADOR para que lo arregle."""
        if not (error or "").strip():
            return self._error("No hay error que corregir.")

        mensaje = protocolo.bloque_correccion(error, codigo_previo, intento)
        return self._llamar(mensaje)

    # -- Utilidades --------------------------------------------------------
    def archivos_de(self, respuesta_o_texto) -> List[Tuple[str, str]]:
        """Archivos extraidos de una :class:`Respuesta` o de un texto crudo."""
        texto = (
            respuesta_o_texto.contenido
            if isinstance(respuesta_o_texto, Respuesta)
            else str(respuesta_o_texto or "")
        )
        return protocolo.extraer_archivos(texto)

    def estado(self) -> str:
        """Diagnostico del rol PROGRAMADOR (no gasta tokens)."""
        return "\n".join(
            [
                "=" * 58,
                " ROL PROGRAMADOR (escritor de codigo) ".center(58, "="),
                "=" * 58,
                self.config.resumen(),
                "turnos: {}".format(self.historial.turno()),
                "problemas: {}".format("; ".join(self.config.problemas()) or "ninguno"),
                "-" * 58,
                self.historial.resumen_texto(limite=6),
                "=" * 58,
            ]
        )

    def reiniciar(self) -> str:
        """Olvida la conversacion del PROGRAMADOR."""
        self.historial.limpiar()
        self.ultima_entrega = ""
        return "Memoria del PROGRAMADOR borrada (el ARQUITECTO conserva la suya)."

    # -- Internos ---------------------------------------------------------
    def _llamar(self, mensaje: str) -> Respuesta:
        """Envia un mensaje al modelo del rol y normaliza la respuesta."""
        self.historial.registrar_usuario(mensaje)
        mensajes = self.historial.mensajes_para_llm(protocolo.SYSTEM_PROMPT_PROGRAMADOR)
        inicio = time.time()
        try:
            contenido = self.proveedor.consultar(mensajes)
        except ErrorProveedor as exc:
            log.error("Fallo el proveedor del PROGRAMADOR: %s", exc)
            return self._error(str(exc))
        except Exception as exc:  # defensivo: el servidor MCP nunca debe caerse
            log.exception("Error inesperado del proveedor del PROGRAMADOR")
            return self._error("Error inesperado del proveedor: {}".format(exc))

        archivos = protocolo.extraer_archivos(contenido)
        self.historial.registrar_asistente(contenido)
        self.ultima_entrega = contenido
        return Respuesta(
            contenido=contenido,
            turno=self.historial.turno(),
            proveedor=self.config.proveedor,
            modelo=self.config.modelo,
            terminada=bool(archivos),
            segundos=time.time() - inicio,
            meta={"archivos": [ruta for ruta, _ in archivos]},
        )

    def formatear(self, respuesta: Respuesta) -> str:
        """Texto final que vera el IDE, con el resumen de archivos entregados."""
        if respuesta.error:
            return protocolo.formatear_error(respuesta.error)
        archivos = self.archivos_de(respuesta)
        return protocolo.formatear_respuesta_programador(
            contenido=respuesta.contenido,
            turno=respuesta.turno,
            proveedor=respuesta.proveedor,
            modelo=respuesta.modelo,
            archivos=archivos,
            segundos=respuesta.segundos,
        )

    def _error(self, mensaje: str) -> Respuesta:
        return Respuesta(
            error=mensaje,
            proveedor=self.config.proveedor,
            modelo=self.config.modelo,
            turno=self.historial.turno(),
        )
