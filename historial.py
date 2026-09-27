"""Memoria de la conversacion entre el PROGRAMADOR y el ARQUITECTO.

Sin memoria, cada llamada al Arquitecto seria amnesica y no podria validar lo
que el PROGRAMADOR acaba de hacer. Esta clase:

* Guarda cada turno (idea / plan / progreso / directriz) con su marca de tiempo.
* Mantiene una **ventana** acotada por numero de turnos y por caracteres, para
  no desbordar el contexto del modelo ni el coste por peticion.
* **Normaliza** los roles (colapsa mensajes consecutivos del mismo rol y evita
  que la ventana empiece por el asistente), porque las APIs de tipo OpenAI
  rechazan secuencias de roles mal formadas.
* Puede persistir en disco para sobrevivir a reinicios del servidor MCP.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import protocolo
from config import Config

log = logging.getLogger("arquitecto.historial")

ROL_USUARIO = "usuario"
ROL_ARQUITECTO = "arquitecto"

_ROL_API = {ROL_USUARIO: "user", ROL_ARQUITECTO: "assistant"}


def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Entrada:
    """Un turno del dialogo."""

    rol: str
    tipo: str
    contenido: str
    momento: str = field(default_factory=_ahora)

    @property
    def rol_api(self) -> str:
        return _ROL_API.get(self.rol, "user")


class Historial:
    """Buffer circular de turnos, seguro para uso concurrente."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._cerrojo = threading.Lock()
        self._entradas: List[Entrada] = []
        self.creado = _ahora()
        if config.persistir:
            self._cargar()

    # -- Escritura -------------------------------------------------------
    # Nota: el texto se envuelve con el protocolo (marcadores + instrucciones)
    # en el momento de registrarlo, de modo que el mensaje que recibe el modelo
    # sea EXACTAMENTE el mismo que queda guardado en la memoria.
    def registrar_idea(self, idea: str, contexto: str = "") -> None:
        self._agregar(
            ROL_USUARIO, "idea", protocolo.bloque_idea(idea, contexto)
        )

    def registrar_plan(self, contenido: str) -> None:
        self._agregar(ROL_ARQUITECTO, "plan", contenido.strip())

    def registrar_progreso(
        self,
        resumen: str,
        prompt_original: str = "",
        archivos_tocados: str = "",
        bloqueo: str = "",
    ) -> None:
        self._agregar(
            ROL_USUARIO,
            "progreso",
            protocolo.bloque_progreso(
                resumen_de_lo_hecho=resumen,
                prompt_original=prompt_original,
                archivos_tocados=archivos_tocados,
                bloqueo=bloqueo,
            ),
        )

    def registrar_directriz(self, contenido: str) -> None:
        self._agregar(ROL_ARQUITECTO, "directriz", contenido.strip())

    # -- Escritura generica (rol PROGRAMADOR) ------------------------------
    def registrar_usuario(self, contenido: str, tipo: str = "tarea") -> None:
        """Guarda un mensaje ya formateado dirigido al modelo (sin reenvolverlo).

        Lo usa el rol PROGRAMADOR, que construye sus propios mensajes con
        ``protocolo.bloque_implementacion`` / ``protocolo.bloque_correccion``.
        """
        self._agregar(ROL_USUARIO, tipo, (contenido or "").strip())

    def registrar_asistente(self, contenido: str, tipo: str = "codigo") -> None:
        """Guarda la respuesta del modelo (codigo entregado, correccion...)."""
        self._agregar(ROL_ARQUITECTO, tipo, (contenido or "").strip())

    def _agregar(self, rol: str, tipo: str, contenido: str) -> None:
        with self._cerrojo:
            self._entradas.append(Entrada(rol=rol, tipo=tipo, contenido=contenido))
            self._recortar()
            self._guardar()

    # -- Lectura ---------------------------------------------------------
    def mensajes_para_llm(self, system_prompt: str) -> List[Dict[str, str]]:
        """Construye la lista de mensajes lista para enviar a la API."""
        with self._cerrojo:
            ventana = list(self._entradas)
        ventana = self._aplicar_presupuesto(ventana)
        ventana = _normalizar_roles(ventana)
        mensajes: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        mensajes.extend({"role": e.rol_api, "content": e.contenido} for e in ventana)
        return mensajes

    def turno(self) -> int:
        """Numero de respuestas del Arquitecto emitidas hasta ahora."""
        with self._cerrojo:
            return sum(1 for e in self._entradas if e.rol == ROL_ARQUITECTO)

    def ultima_directriz(self) -> str:
        with self._cerrojo:
            for entrada in reversed(self._entradas):
                if entrada.rol == ROL_ARQUITECTO:
                    return entrada.contenido
        return ""

    def conteo(self) -> int:
        with self._cerrojo:
            return len(self._entradas)

    def resumen_texto(self, limite: int = 10) -> str:
        """Vista compacta de los ultimos turnos, util para diagnostico humano."""
        with self._cerrojo:
            ultimas = self._entradas[-limite:]
        if not ultimas:
            return "(historial vacio)"
        filas = ["{:<19} {:<10} {:<10} {}".format("momento", "rol", "tipo", "extracto")]
        for entrada in ultimas:
            extracto = " ".join(entrada.contenido.split())
            if len(extracto) > 70:
                extracto = extracto[:70] + "..."
            filas.append(
                "{:<19} {:<10} {:<10} {}".format(
                    entrada.momento, entrada.rol, entrada.tipo, extracto
                )
            )
        return "\n".join(filas)

    # -- Mantenimiento ---------------------------------------------------
    def limpiar(self) -> None:
        """Olvida toda la conversacion (inicia una sesion de trabajo nueva)."""
        with self._cerrojo:
            self._entradas = []
            self.creado = _ahora()
            self._guardar()
        log.info("Historial reiniciado.")

    # -- Internos --------------------------------------------------------
    def _limite_entradas(self) -> int:
        # Cada turno completo son dos entradas (usuario + arquitecto).
        return max(2, self.config.max_turnos_historial * 2)

    def _recortar(self) -> None:
        limite = self._limite_entradas()
        if len(self._entradas) > limite:
            self._entradas = self._entradas[-limite:]

    def _aplicar_presupuesto(self, ventana: List[Entrada]) -> List[Entrada]:
        """Descarta los turnos mas antiguos si el contexto excede el presupuesto."""
        presupuesto = self.config.max_caracteres_contexto
        seleccion: List[Entrada] = []
        total = 0
        for entrada in reversed(ventana):
            coste = len(entrada.contenido) + 40
            if seleccion and total + coste > presupuesto:
                break
            seleccion.append(entrada)
            total += coste
        seleccion.reverse()
        return seleccion

    # -- Persistencia ----------------------------------------------------
    def _guardar(self) -> None:
        if not self.config.persistir:
            return
        ruta: Path = self.config.ruta_historial
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            datos = {
                "creado": self.creado,
                "actualizado": _ahora(),
                "proveedor": self.config.proveedor,
                "modelo": self.config.modelo,
                "entradas": [asdict(e) for e in self._entradas],
            }
            ruta.write_text(
                json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            log.warning("No se pudo guardar el historial en %s: %s", ruta, exc)

    def _cargar(self) -> None:
        ruta: Path = self.config.ruta_historial
        if not ruta.exists():
            return
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Historial ilegible en %s (%s). Se empieza de cero.", ruta, exc)
            return
        entradas = []
        for cruda in datos.get("entradas", []):
            try:
                entradas.append(Entrada(**cruda))
            except TypeError:
                continue
        with self._cerrojo:
            self._entradas = entradas
            self.creado = datos.get("creado", self.creado)
            self._recortar()
        log.info("Historial restaurado: %s entradas desde %s", len(entradas), ruta)


def _normalizar_roles(entradas: List[Entrada]) -> List[Entrada]:
    """Colapsa roles consecutivos y garantiza que la ventana empiece en 'usuario'."""
    normalizadas: List[Entrada] = []
    for entrada in entradas:
        if normalizadas and normalizadas[-1].rol == entrada.rol:
            previa = normalizadas[-1]
            previa.contenido = "{}\n\n{}".format(previa.contenido, entrada.contenido)
            continue
        normalizadas.append(Entrada(**asdict(entrada)))

    while normalizadas and normalizadas[0].rol != ROL_USUARIO:
        normalizadas.pop(0)
    return normalizadas
