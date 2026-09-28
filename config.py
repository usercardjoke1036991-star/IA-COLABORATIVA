"""Configuracion central del Arquitecto Externo (servidor MCP para Cursor).

Como funciona
-------------
Toda la configuracion se lee de variables de entorno y, opcionalmente, de un
archivo ``.env`` situado junto a este modulo. No hay secretos hardcodeados:
la API key se toma siempre del entorno (o del ``.env``, ignorado por git).

Variables reconocidas
---------------------
ARQUITECTO_PROVIDER      deepseek | openrouter | openai | custom | mock  (def. deepseek)
ARQUITECTO_MODEL         nombre del modelo (def. segun el proveedor)
ARQUITECTO_API_URL       solo para ARQUITECTO_PROVIDER=custom
ARQUITECTO_API_KEY       solo para ARQUITECTO_PROVIDER=custom
DEEPSEEK_API_KEY         credencial de DeepSeek
OPENROUTER_API_KEY       credencial de OpenRouter
OPENAI_API_KEY           credencial de OpenAI
ARQUITECTO_TEMPERATURA   creatividad, 0..2 (def. 0.4)
ARQUITECTO_TIMEOUT       segundos por peticion (def. 120)
ARQUITECTO_MAX_TOKENS    tokens maximos de la respuesta (def. 4096)
ARQUITECTO_REINTENTOS    reintentos ante error de red / 429 / 5xx (def. 2)
ARQUITECTO_MAX_TURNOS    pares usuario/arquitecto guardados en memoria (def. 12)
ARQUITECTO_MAX_CARACTERES  tope de caracteres enviados como contexto (def. 24000)
ARQUITECTO_PERSISTIR     true|false, guarda el historial en disco (def. true)
ARQUITECTO_MOCK          true|false, respuestas simuladas sin red (def. false)
ARQUITECTO_LOG           DEBUG | INFO | WARNING | ERROR (def. INFO)
ARQUITECTO_APP_URL       opcional, cabecera HTTP-Referer pedida por OpenRouter

Rol PROGRAMADOR (segundo modelo; si no se define, hereda lo del arquitecto)
--------------------------------------------------------------------------
ARQUITECTO_EJECUTOR_PROVIDER    deepseek | openrouter | openai | custom | mock
ARQUITECTO_EJECUTOR_MODEL       modelo del programador (def. el del proveedor)
ARQUITECTO_EJECUTOR_API_KEY     credencial propia del programador (opcional)
ARQUITECTO_EJECUTOR_API_URL     solo para proveedor custom
ARQUITECTO_EJECUTOR_TEMPERATURA creatividad, 0..2 (def. 0.2, mas deterministico)
ARQUITECTO_EJECUTOR_MAX_TOKENS  tokens maximos (def. ARQUITECTO_MAX_TOKENS)
ARQUITECTO_EJECUTOR_TIMEOUT     segundos por peticion (def. ARQUITECTO_TIMEOUT)
ARQUITECTO_EJECUTOR_MOCK        true|false, respuestas simuladas (def. hereda)

Fabrica de proyectos
--------------------
ARQUITECTO_CARPETA_PROYECTOS    carpeta raiz donde nacen los proyectos (def. proyectos/)
ARQUITECTO_REGISTRO             ruta del registro de proyectos (def. datos/proyectos.json)
ARQUITECTO_PERMITIR_EXTERNO     true|false, permite escribir fuera de las raices (def. false)
ARQUITECTO_PLANTILLAS           plantillas por defecto (def. python)
ARQUITECTO_CREAR_VENV           true|false, crea el entorno virtual al crear proyecto (def. true)
ARQUITECTO_INSTALAR_DEPENDENCIAS true|false, instala las librerias al crear proyecto (def. false)
ARQUITECTO_GIT_USUARIO          usuario para los commits de la fabrica
ARQUITECTO_GIT_EMAIL            email para los commits de la fabrica
ARQUITECTO_GITHUB               true|false, publica el repo en GitHub via gh (def. false)
ARQUITECTO_GITHUB_VISOR         private | public (def. private)
ARQUITECTO_GITHUB_ORG           organizacion o usuario destino (def. el del token de gh)
ARQUITECTO_ORQUESTADOR          cline | interno: quien ejecuta el bucle autonomo (def. cline)
ARQUITECTO_CLINE_COMANDO        ejecutable de Cline CLI (def. cline)
ARQUITECTO_CLINE_AUTO           true|false, pasa --yolo al CLI (def. false)
ARQUITECTO_LIMITE_TURNOS        tope de iteraciones del orquestador (def. 6)
ARQUITECTO_MAX_RONDAS           tope de rondas del bucle de mejora continua por sesion (def. 10)
ARQUITECTO_CARPETA_SESIONES     carpeta de la memoria del bucle (def. datos/sesiones)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

RAIZ_PROYECTO = Path(__file__).resolve().parent
RUTA_ENV = RAIZ_PROYECTO / ".env"
RUTA_HISTORIAL = RAIZ_PROYECTO / "datos" / "historial_arquitecto.json"

#: Proveedores soportados de fabrica. ``custom`` sirve para cualquier endpoint
#: compatible con la API de OpenAI (Ollama, LM Studio, vLLM, Azure, Groq...).
PERFILES_PROVEEDOR = {
    "deepseek": {
        "url": "https://api.deepseek.com/chat/completions",
        "variable_key": "DEEPSEEK_API_KEY",
        "modelo": "deepseek-chat",
        "nota": "DeepSeek oficial (la de la ballenita).",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "variable_key": "OPENROUTER_API_KEY",
        "modelo": "anthropic/claude-3.5-sonnet",
        "nota": "OpenRouter: un catalogo enorme de modelos con una sola clave.",
    },
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "variable_key": "OPENAI_API_KEY",
        "modelo": "gpt-4o",
        "nota": "OpenAI directo.",
    },
    "custom": {
        "url": "",
        "variable_key": "ARQUITECTO_API_KEY",
        "modelo": "",
        "nota": "Endpoint compatible con la API de OpenAI (Ollama, LM Studio, vLLM...).",
    },
    "mock": {
        "url": "",
        "variable_key": "",
        "modelo": "simulado",
        "nota": "Sin llamadas de red: respuestas simuladas para probar la mecanica del loop.",
    },
}


@dataclass
class Config:
    """Instantanea de la configuracion activa."""

    proveedor: str = "deepseek"
    modelo: str = ""
    url: str = ""
    variable_key: str = ""
    api_key: str = ""
    temperatura: float = 0.4
    timeout: int = 120
    max_tokens: int = 4096
    reintentos: int = 2
    max_turnos_historial: int = 12
    max_caracteres_contexto: int = 24000
    persistir: bool = True
    ruta_historial: Path = RUTA_HISTORIAL
    modo_mock: bool = False
    nivel_log: str = "INFO"
    app_url: str = ""

    # -- Utilidades ------------------------------------------------------
    def clave_enmascarada(self) -> str:
        """Devuelve la API key ofuscada, apta para logs y diagnosticos."""
        if not self.api_key:
            return "(sin api key)"
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return "{}...{}".format(self.api_key[:4], self.api_key[-4:])

    def es_local(self) -> bool:
        """True si el endpoint apunta a esta misma maquina (no exige API key)."""
        return any(host in self.url for host in ("localhost", "127.0.0.1", "0.0.0.0"))

    def problemas(self) -> list:
        """Errores de configuracion que impedirian consultar la API."""
        fallos = []
        if self.modo_mock:
            return fallos
        if not self.url:
            fallos.append(
                "Falta ARQUITECTO_API_URL (obligatoria con ARQUITECTO_PROVIDER=custom)."
            )
        if not self.modelo:
            fallos.append("Falta ARQUITECTO_MODEL: no se sabe que modelo invocar.")
        if not self.api_key and not self.es_local():
            fallos.append(
                "Falta la API key. Definela en .env, por ejemplo: {}=sk-...".format(
                    self.variable_key or "ARQUITECTO_API_KEY"
                )
            )
        return fallos

    def resumen(self) -> str:
        """Resumen legible de la configuracion (sin exponer secretos)."""
        return (
            "proveedor={} | modelo={} | url={} | clave={} | mock={} | "
            "timeout={}s | reintentos={} | temperatura={}".format(
                self.proveedor,
                self.modelo,
                self.url or "(no aplica)",
                self.clave_enmascarada(),
                self.modo_mock,
                self.timeout,
                self.reintentos,
                self.temperatura,
            )
        )


@dataclass
class ConfigFabrica:
    """Ajustes de la fabrica de proyectos (rutas, venv, git y publicacion)."""

    raiz_proyectos: Path = RAIZ_PROYECTO / "proyectos"
    permitir_externo: bool = False
    plantillas_por_defecto: List[str] = field(default_factory=lambda: ["python"])
    crear_venv: bool = True
    instalar_dependencias: bool = False
    git_usuario: str = ""
    git_email: str = ""
    github: bool = False
    github_visor: str = "private"
    github_org: str = ""
    orquestador: str = "interno"
    cline_comando: str = "cline"
    cline_auto: bool = False
    limite_turnos: int = 6
    max_rondas: int = 10

    def resumen(self) -> str:
        """Resumen legible de la configuracion de la fabrica."""
        return (
            "proyectos={} | plantillas={} | venv={} | instalar={} | github={} ({}) | "
            "orquestador={} | auto={} | turnos={} | externo={}".format(
                self.raiz_proyectos,
                ", ".join(self.plantillas_por_defecto) or "(ninguna)",
                self.crear_venv,
                self.instalar_dependencias,
                self.github,
                self.github_visor,
                self.orquestador,
                self.cline_auto,
                self.limite_turnos,
                self.permitir_externo,
            )
        )


# --------------------------------------------------------------------------
# Lectura de entorno
# --------------------------------------------------------------------------
def cargar_env(ruta: Path = RUTA_ENV) -> None:
    """Carga un ``.env`` sencillo (CLAVE=valor) sin dependencias externas.

    Nunca sobreescribe variables ya presentes en el entorno real del sistema.
    """
    try:
        contenido = ruta.read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError):
        return
    for linea in contenido.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("#") or "=" not in limpia:
            continue
        if limpia.lower().startswith("export "):
            limpia = limpia[len("export "):].strip()
        clave, _, valor = limpia.partition("=")
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        if clave and clave not in os.environ:
            os.environ[clave] = valor


def _texto(nombre: str, por_defecto: str = "") -> str:
    return (os.getenv(nombre) or por_defecto).strip()


def _bool(nombre: str, por_defecto: bool = False) -> bool:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return por_defecto  # vacio = no definido: asi se hereda del rol base
    return valor.strip().lower() in {"1", "true", "si", "yes", "on"}


def _int(nombre: str, por_defecto: int) -> int:
    try:
        return int(float(os.getenv(nombre, por_defecto)))
    except (TypeError, ValueError):
        return por_defecto


def _float(nombre: str, por_defecto: float) -> float:
    try:
        return float(os.getenv(nombre, por_defecto))
    except (TypeError, ValueError):
        return por_defecto


def cargar(ruta_env: Path = RUTA_ENV) -> Config:
    """Construye la :class:`Config` activa a partir del entorno y del ``.env``."""
    cargar_env(ruta_env)

    proveedor = _texto("ARQUITECTO_PROVIDER", "deepseek").lower()
    if proveedor not in PERFILES_PROVEEDOR:
        proveedor = "deepseek"
    if _bool("ARQUITECTO_MOCK"):
        proveedor = "mock"

    perfil = PERFILES_PROVEEDOR[proveedor]
    url = _texto("ARQUITECTO_API_URL") if proveedor == "custom" else perfil["url"]
    variable_key = perfil["variable_key"]
    api_key = _texto(variable_key) if variable_key else ""

    return Config(
        proveedor=proveedor,
        modelo=_texto("ARQUITECTO_MODEL", perfil["modelo"]),
        url=url,
        variable_key=variable_key,
        api_key=api_key,
        temperatura=_float("ARQUITECTO_TEMPERATURA", 0.4),
        timeout=_int("ARQUITECTO_TIMEOUT", 120),
        max_tokens=_int("ARQUITECTO_MAX_TOKENS", 4096),
        reintentos=max(0, _int("ARQUITECTO_REINTENTOS", 2)),
        max_turnos_historial=max(1, _int("ARQUITECTO_MAX_TURNOS", 12)),
        max_caracteres_contexto=max(2000, _int("ARQUITECTO_MAX_CARACTERES", 24000)),
        persistir=_bool("ARQUITECTO_PERSISTIR", True),
        ruta_historial=RAIZ_PROYECTO / "datos" / "historial_arquitecto.json",
        modo_mock=proveedor == "mock",
        nivel_log=_texto("ARQUITECTO_LOG", "INFO").upper(),
        app_url=_texto("ARQUITECTO_APP_URL"),
    )


def cargar_ejecutor() -> Config:
    """Config del rol PROGRAMADOR (por defecto, mismo proveedor con otro modelo).

    La gracia del sistema es el *cross-model*: el ARQUITECTO razona con un modelo
    fuerte (por ejemplo ``deepseek-reasoner``) y el PROGRAMADOR escribe codigo con
    uno mas rapido y barato (``deepseek-chat``). Cada variable
    ``ARQUITECTO_EJECUTOR_*`` es opcional: si falta, se hereda del arquitecto.
    """
    cargar_env()
    base = cargar()

    proveedor = _texto("ARQUITECTO_EJECUTOR_PROVIDER", base.proveedor).lower()
    if _bool("ARQUITECTO_EJECUTOR_MOCK", base.modo_mock):
        proveedor = "mock"
    if proveedor not in PERFILES_PROVEEDOR:
        proveedor = base.proveedor
    perfil = PERFILES_PROVEEDOR[proveedor]

    if proveedor == "custom":
        url = _texto("ARQUITECTO_EJECUTOR_API_URL", base.url)
    else:
        url = perfil["url"]
    variable_key = perfil["variable_key"]
    api_key = (
        _texto("ARQUITECTO_EJECUTOR_API_KEY")
        or (_texto(variable_key) if variable_key else "")
        or base.api_key
    )

    return Config(
        proveedor=proveedor,
        modelo=_texto("ARQUITECTO_EJECUTOR_MODEL", perfil["modelo"]),
        url=url,
        variable_key=variable_key,
        api_key=api_key,
        temperatura=_float("ARQUITECTO_EJECUTOR_TEMPERATURA", 0.2),
        timeout=_int("ARQUITECTO_EJECUTOR_TIMEOUT", base.timeout),
        max_tokens=_int("ARQUITECTO_EJECUTOR_MAX_TOKENS", base.max_tokens),
        reintentos=max(0, _int("ARQUITECTO_REINTENTOS", base.reintentos)),
        max_turnos_historial=base.max_turnos_historial,
        max_caracteres_contexto=base.max_caracteres_contexto,
        persistir=base.persistir,
        ruta_historial=RAIZ_PROYECTO / "datos" / "historial_ejecutor.json",
        modo_mock=base.modo_mock or proveedor == "mock",
        nivel_log=base.nivel_log,
        app_url=base.app_url,
    )


def cargar_por_rol(rol: str) -> Config:
    """Devuelve la config del rol indicado (``arquitecto`` o ``ejecutor``)."""
    return cargar_ejecutor() if (rol or "").strip().lower() in {"ejecutor", "programador"} else cargar()


def cargar_fabrica(ruta_env: Path = RUTA_ENV) -> ConfigFabrica:
    """Config de la fabrica de proyectos (carpeta raiz, venv, git, GitHub...)."""
    cargar_env(ruta_env)

    carpeta = _texto("ARQUITECTO_CARPETA_PROYECTOS")
    if carpeta:
        raiz = Path(carpeta).expanduser()
        if not raiz.is_absolute():
            raiz = RAIZ_PROYECTO / raiz
    else:
        raiz = RAIZ_PROYECTO / "proyectos"

    plantillas = [
        pieza.strip().lower()
        for pieza in _texto("ARQUITECTO_PLANTILLAS", "python").replace(";", ",").split(",")
        if pieza.strip()
    ]
    visor = _texto("ARQUITECTO_GITHUB_VISOR", "private").lower()
    if visor not in {"private", "public"}:
        visor = "private"
    orquestador = _texto("ARQUITECTO_ORQUESTADOR", "interno").lower()
    if orquestador not in {"cline", "interno"}:
        orquestador = "cline"

    return ConfigFabrica(
        raiz_proyectos=raiz,
        permitir_externo=_bool("ARQUITECTO_PERMITIR_EXTERNO", False),
        plantillas_por_defecto=plantillas or ["vacio"],
        crear_venv=_bool("ARQUITECTO_CREAR_VENV", True),
        instalar_dependencias=_bool("ARQUITECTO_INSTALAR_DEPENDENCIAS", False),
        git_usuario=_texto("ARQUITECTO_GIT_USUARIO"),
        git_email=_texto("ARQUITECTO_GIT_EMAIL"),
        github=_bool("ARQUITECTO_GITHUB", False),
        github_visor=visor,
        github_org=_texto("ARQUITECTO_GITHUB_ORG"),
        orquestador=orquestador,
        cline_comando=_texto("ARQUITECTO_CLINE_COMANDO", "cline"),
        cline_auto=_bool("ARQUITECTO_CLINE_AUTO", False),
        limite_turnos=max(1, _int("ARQUITECTO_LIMITE_TURNOS", 6)),
        max_rondas=max(1, _int("ARQUITECTO_MAX_RONDAS", 10)),
    )


def configurar_log(nivel: str = "INFO") -> None:
    """Configura el logging hacia **stderr**.

    Es critico: el transporte ``stdio`` de MCP usa ``stdout`` para el protocolo
    JSON-RPC, por lo que escribir ahi romperia la conexion con Cursor.
    """
    import sys

    raiz = logging.getLogger("arquitecto")
    if not raiz.handlers:
        manejador = logging.StreamHandler(sys.stderr)
        manejador.setFormatter(
            logging.Formatter("[arquitecto] %(levelname)s %(name)s: %(message)s")
        )
        raiz.addHandler(manejador)
        raiz.propagate = False
    raiz.setLevel(getattr(logging, nivel, logging.INFO))
