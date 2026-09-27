"""Clientes hacia el proveedor de LLM que interpreta al Arquitecto.

* :class:`ProveedorLLM` habla con cualquier API compatible con el esquema
  ``/chat/completions`` de OpenAI (DeepSeek, OpenRouter, OpenAI, Ollama...).
  Incluye timeout, reintentos con espera progresiva y mensajes de error
  accionables en lugar de trazas crudas.
* :class:`ProveedorMock` no toca la red: devuelve respuestas simuladas para
  validar toda la mecanica del loop sin gastar tokens ni credenciales.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

import protocolo
from config import Config

try:  # ``requests`` solo es imprescindible cuando NO se usa el modo mock.
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

log = logging.getLogger("arquitecto.proveedor")

#: Codigos HTTP que merece la pena reintentar (limite de uso o fallo transitorio).
CODIGOS_REINTENTABLES = {408, 409, 425, 429, 500, 502, 503, 504}

#: Traduccion de los codigos de error mas habituales a acciones concretas.
AYUDA_POR_CODIGO = {
    400: "Peticion rechazada. Revisa ARQUITECTO_MODEL y el tamano del contexto enviado.",
    401: "Credencial invalida. Revisa la API key en tu archivo .env.",
    402: "Saldo agotado en el proveedor. Recarga credito.",
    403: "La clave no tiene permisos para ese modelo.",
    404: "Endpoint o modelo inexistente. Revisa ARQUITECTO_API_URL y ARQUITECTO_MODEL.",
    429: "Limite de peticiones alcanzado. El cliente ya reintenta con espera progresiva.",
    500: "Error interno del proveedor. Reintenta en unos segundos.",
    503: "Servicio no disponible temporalmente.",
}


class ErrorProveedor(RuntimeError):
    """Fallo controlado al hablar con el proveedor de LLM."""


def _recorte(texto: str, limite: int = 400) -> str:
    """Recorta un texto largo para poder mostrarlo en logs y errores."""
    limpio = " ".join((texto or "").split())
    return limpio if len(limpio) <= limite else limpio[:limite] + "..."


def _pedir_requests():
    if requests is None:
        raise ErrorProveedor(
            "Falta la libreria 'requests'. Ejecuta:  pip install -r requirements.txt"
        )
    return requests


class ProveedorLLM:
    """Cliente HTTP sincrono contra un endpoint ``/chat/completions``."""

    nombre = "http"

    def __init__(self, config: Config) -> None:
        self.config = config
        self.sesion = None

    # -- API publica -----------------------------------------------------
    def consultar(
        self, mensajes: List[Dict[str, str]], max_tokens: Optional[int] = None
    ) -> str:
        """Envia la conversacion y devuelve el texto del Arquitecto."""
        self._validar()
        req = _pedir_requests()
        if self.sesion is None:
            self.sesion = req.Session()

        payload = {
            "model": self.config.modelo,
            "messages": mensajes,
            "temperature": self.config.temperatura,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": False,
        }
        ultimo_error = "sin detalle"

        for intento in range(self.config.reintentos + 1):
            if intento:
                espera = 1.5 * (2 ** (intento - 1))
                log.warning(
                    "Reintento %s/%s en %.1fs (motivo: %s)",
                    intento,
                    self.config.reintentos,
                    espera,
                    _recorte(ultimo_error, 160),
                )
                time.sleep(espera)
            try:
                respuesta = self.sesion.post(
                    self.config.url,
                    headers=self._encabezados(),
                    json=payload,
                    timeout=self.config.timeout,
                )
            except req.RequestException as exc:
                ultimo_error = "Error de red: {}".format(exc)
                continue

            if (
                respuesta.status_code in CODIGOS_REINTENTABLES
                and intento < self.config.reintentos
            ):
                ultimo_error = "HTTP {}: {}".format(
                    respuesta.status_code, _recorte(respuesta.text)
                )
                continue

            if respuesta.status_code >= 400:
                raise ErrorProveedor(self._mensaje_error(respuesta))

            return self._extraer_contenido(respuesta)

        raise ErrorProveedor(
            "No se pudo completar la peticion tras {} intento(s). Ultimo error: {}".format(
                self.config.reintentos + 1, ultimo_error
            )
        )

    # -- Internos --------------------------------------------------------
    def _validar(self) -> None:
        fallos = self.config.problemas()
        if fallos:
            raise ErrorProveedor("Configuracion incompleta:\n- " + "\n- ".join(fallos))

    def _encabezados(self) -> Dict[str, str]:
        cabeceras = {"Content-Type": "application/json"}
        if self.config.api_key:
            cabeceras["Authorization"] = "Bearer {}".format(self.config.api_key)
        if self.config.proveedor == "openrouter":
            cabeceras["X-Title"] = "Arquitecto Externo MCP"
            if self.config.app_url:
                cabeceras["HTTP-Referer"] = self.config.app_url
        return cabeceras

    def _mensaje_error(self, respuesta) -> str:
        codigo = respuesta.status_code
        ayuda = AYUDA_POR_CODIGO.get(codigo, "Revisa la documentacion del proveedor.")
        return "El proveedor respondio HTTP {}.\n{}\nDetalle: {}".format(
            codigo, ayuda, _recorte(respuesta.text)
        )

    @staticmethod
    def _extraer_contenido(respuesta) -> str:
        try:
            datos = respuesta.json()
            contenido = datos["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ErrorProveedor(
                "Respuesta inesperada del proveedor ({}). Cuerpo: {}".format(
                    exc, _recorte(respuesta.text)
                )
            ) from exc
        if not contenido or not str(contenido).strip():
            raise ErrorProveedor("El proveedor devolvio una respuesta vacia.")
        return str(contenido).strip()


class ProveedorMock(ProveedorLLM):
    """Proveedor simulado: valida la mecanica sin red ni credenciales.

    Tras ``ARQUITECTO_MOCK_TURNOS`` informes de progreso (def. 2) el simulador
    emite el marcador de fin, de modo que tambien se pueda probar que el loop
    **termina** en lugar de girar para siempre.
    """

    nombre = "mock"

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._informes = 0
        self._apagado = False
        self._entregas = 0

    def consultar(
        self, mensajes: List[Dict[str, str]], max_tokens: Optional[int] = None
    ) -> str:
        del max_tokens  # el simulador ignora el presupuesto de tokens
        texto_usuario = "\n".join(
            str(m.get("content", "")) for m in mensajes if m.get("role") == "user"
        )
        if protocolo.MARCADOR_TAREA in texto_usuario:
            return self._entrega()
        if protocolo.MARCADOR_CORRECCION in texto_usuario:
            return self._entrega(corregido=True)
        if protocolo.MARCADOR_PROGRESO in texto_usuario:
            return self._informe()
        self._apagado = False
        self._informes = 0
        self._entregas = 0
        return self._plan(texto_usuario)

    def esta_apagado(self) -> bool:
        """True cuando el simulador ya declaro la tarea como terminada."""
        return self._apagado

    # -- Respuestas simuladas -------------------------------------------
    def _entrega(self, corregido: bool = False) -> str:
        """Respuesta del simulador en el formato de archivos del PROGRAMADOR.

        Permite validar de punta a punta (escribir, probar, commitear) la fabrica
        y el orquestador sin gastar tokens ni depender de la red.
        """
        self._entregas += 1
        numero = self._entregas
        modulo = "modulo_simulado"
        return "\n".join(
            [
                "### ARCHIVO: src/{}.py".format(modulo),
                "```python",
                '"""Modulo del simulador del PROGRAMADOR (ARQUITECTO_MOCK=1).',
                "",
                "Valida el contrato de entrega de archivos sin llamar a ninguna API.",
                '"""',
                "from __future__ import annotations",
                "",
                "",
                "def saludar(nombre: str = 'mundo') -> str:",
                '    """Devuelve un saludo simple, con tipos y docstring."""',
                '    return "hola " + nombre',
                "",
                "",
                'if __name__ == "__main__":',
                "    print(saludar())",
                "```",
                "",
                "### ARCHIVO: docs/entrega_{}.md".format(numero),
                "```markdown",
                "# Entrega {}".format(numero),
                "",
                "- estado: {}".format("correccion" if corregido else "version inicial"),
                "```",
                "",
                "### PASOS",
                "1. venv\\Scripts\\python.exe -m {}".format(modulo),
            ]
        )
    def _plan(self, texto_usuario: str) -> str:
        ultima = _recorte(texto_usuario.strip().splitlines()[-1] if texto_usuario.strip() else "", 120)
        return (
            "## Diagnostico\n"
            "Peticion recibida y dimensionada en modo simulado (ARQUITECTO_MOCK=1).\n"
            "No hay llamada de red: esto valida el contrato del loop, no la calidad\n"
            "del modelo. Ultima linea de la idea: {}\n\n"
            "## Plan\n"
            "1. Definir el alcance minimo viable y sus criterios de aceptacion.\n"
            "2. Crear la estructura de carpetas y los modulos base.\n"
            "3. Implementar el camino feliz y verificarlo con una prueba local.\n"
            "4. Anadir manejo de errores y documentar el uso.\n\n"
            "## Riesgos y decisiones tecnicas\n"
            "- Asumimos que no hay requisitos de rendimiento extremos.\n"
            "- Se prioriza simplicidad sobre abstraccion prematura.".format(ultima)
        )

    def _informe(self) -> str:
        self._informes += 1
        if self._informes >= self._limite_informes():
            self._apagado = True
            return (
                "## Diagnostico\n"
                "Informe {} recibido. El trabajo cumple los criterios de aceptacion\n"
                "del plan simulado y no quedan pasos pendientes.\n\n"
                "## Plan\n"
                "Sin pasos adicionales. Verificaciones finales: pruebas locales en\n"
                "verde, documentacion actualizada y logs sin errores.\n\n"
                "## Riesgos y decisiones tecnicas\n"
                "- Ninguno pendiente. Loop cerrado correctamente.\n\n"
                "{}".format(self._informes, protocolo.MARCADOR_FIN)
            )
        return (
            "## Diagnostico\n"
            "Informe {} recibido en el simulador. Se detectan dos mejoras: falta\n"
            "manejo de errores en los bordes y faltan pruebas del caso limite.\n\n"
            "## Plan\n"
            "1. Envuelve las operaciones de E/S en try/except y registra el error.\n"
            "2. Anade una prueba para la entrada vacia o invalida.\n"
            "3. Vuelve a ejecutar la verificacion local.\n\n"
            "## Riesgos y decisiones tecnicas\n"
            "- Riesgo bajo: los cambios son locales y quiza rompan firmas existentes.".format(
                self._informes
            )
        )

    @staticmethod
    def _limite_informes() -> int:
        """Tras N informes el simulador declara la tarea terminada."""
        import os

        try:
            return max(1, int(os.getenv("ARQUITECTO_MOCK_TURNOS", "2")))
        except ValueError:
            return 2


def crear_proveedor(config: Config) -> ProveedorLLM:
    """Fabrica: devuelve el proveedor adecuado segun la configuracion."""
    if config.modo_mock:
        return ProveedorMock(config)
    return ProveedorLLM(config)
