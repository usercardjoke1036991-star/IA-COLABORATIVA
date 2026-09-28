"""Contexto del repositorio para el Arquitecto: real, acotado y sin secretos.

El bucle de mejora continua necesita que la IA de la API vea lo que hay de
verdad en el proyecto (estructura, stack, comandos de prueba, ultimos cambios,
pruebas) SIN volcar el repositorio entero (coste de tokens) y SIN filtrar
credenciales (seguridad). Las dos cosas se resuelven aqui:

* :func:`sanea` tacha los valores de secretos: los del ``.env`` del proyecto y
  los de patrones tipicos (claves ``sk-``, tokens de GitHub, bloques PEM, JWT).
* :func:`contexto_del_repo` construye un resumen con presupuesto de bytes: stack,
  comandos reales, arbol acotado, cabeceras de los archivos clave y estado de
  git; todo pasa por el saneador antes de salir de aqui.

Este modulo no habla con la red ni con MCP: es puro calculo sobre el disco.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import herramientas_archivos as archivos
import procesos

#: Presupuesto por defecto del contexto que se manda al arquitecto (bytes).
TOPE_POR_DEFECTO = 14_000

#: Sufijos de variable que delatan un secreto (se comparan en mayusculas).
CLAVES_SENSIBLES = (
    "_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_PASSWD", "_CREDENTIAL", "_DSN",
    "APIKEY", "SECRET", "TOKEN", "PASSWORD",
)

#: Patrones de secreto que se tachan aunque no vengan de un ``.env``.
PATRONES_SECRETO: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{12,}"), "***CLAVE***"),
    (re.compile(r"sk_live_[0-9A-Za-z]{16,}"), "***CLAVE-STRIPE***"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"), "***TOKEN-GITHUB***"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "***TOKEN-GITHUB***"),
    (re.compile(r"glpat-[A-Za-z0-9_\-]{20,}"), "***TOKEN-GITLAB***"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "***CLAVE-AWS***"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), "***TOKEN-SLACK***"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "***CLAVE-GOOGLE***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), "***JWT***"),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "***CLAVE-PRIVADA***",
    ),
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_.-]*(?:key|token|secret|password|passwd|authorization)"
            r"[A-Za-z0-9_.-]*)\s*[:=]\s*[\"']?([^\s\"',]{6,})"
        ),
        r"\1=***SECRETO***",
    ),
)

#: Extensiones de las que interesa la cabecera (los archivos "de contrato").
CABECERAS_INTERESANTES = (
    "README.md", "pyproject.toml", "requirements.txt", "package.json", "Makefile",
    "AGENTS.md", ".clinerules", "INFORME.md", "SUGERENCIAS.md",
)

#: Bytes maximos por archivo del que se enseña la cabecera.
TOPE_CABECERA = 900


def _es_sensible(clave: str) -> bool:
    """True si el nombre de la variable huele a credencial."""
    limpia = (clave or "").strip().upper()
    return any(limpia.endswith(sufijo) or sufijo in limpia for sufijo in CLAVES_SENSIBLES)


def secretos_del_proyecto(carpeta: Path) -> List[str]:
    """Valores de las variables sensibles del ``.env`` del proyecto.

    Se leen solo para poder tacharlos: nunca se devuelven como contexto ni se
    registran en ningun log.
    """
    valores: List[str] = []
    for nombre in (".env", ".env.local", ".env.production"):
        ruta = Path(carpeta) / nombre
        try:
            contenido = ruta.read_text(encoding="utf-8-sig", errors="replace")
        except (FileNotFoundError, OSError):
            continue
        for linea in contenido.splitlines():
            limpia = linea.strip()
            if not limpia or limpia.startswith("#") or "=" not in limpia:
                continue
            clave, _, valor = limpia.partition("=")
            valor = valor.strip().strip('"').strip("'")
            if valor and len(valor) >= 6 and _es_sensible(clave):
                valores.append(valor)
    return valores


def sanea(texto: str, secretos: Sequence[str] = ()) -> str:
    """Tacha credenciales conocidas y las que encajan con los patrones tipicos."""
    limpio = (texto or "").replace("\ufeff", "")
    for secreto in secretos:
        if secreto and len(secreto) >= 6:
            limpio = limpio.replace(secreto, "***SECRETO***")
    for patron, reemplazo in PATRONES_SECRETO:
        limpio = patron.sub(reemplazo, limpio)
    return limpio


# --------------------------------------------------------------------------
# Piezas del resumen
# --------------------------------------------------------------------------
def arbol(carpeta: Path, profundidad: int = 2, max_entradas: int = 70) -> str:
    """Arbol de archivos acotado (omite ruido: venv, node_modules, .git...)."""
    base = Path(carpeta)
    lineas: List[str] = []

    def recorrer(directorio: Path, nivel: int) -> None:
        if nivel > profundidad or len(lineas) >= max_entradas:
            return
        try:
            hijos = sorted(directorio.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for hijo in hijos:
            if len(lineas) >= max_entradas:
                return
            if hijo.name in archivos.IGNORAR:
                continue
            relativo = hijo.relative_to(base).as_posix()
            if hijo.is_dir():
                lineas.append("{}/".format(relativo))
                recorrer(hijo, nivel + 1)
            else:
                lineas.append(relativo)

    recorrer(base, 1)
    if not lineas:
        return "(carpeta vacia)"
    if len(lineas) >= max_entradas:
        lineas.append("... [arbol recortado]")
    return "\n".join(lineas)


def cabeceras(carpeta: Path, max_archivos: int = 6) -> str:
    """Cabeceras de los archivos que definen el proyecto (README, deps, reglas...)."""
    piezas: List[str] = []
    for nombre in CABECERAS_INTERESANTES:
        ruta = Path(carpeta) / nombre
        if not ruta.is_file():
            continue
        try:
            texto = ruta.read_text(encoding="utf-8-sig", errors="replace")[:TOPE_CABECERA]
        except OSError:
            continue
        piezas.append("### {}\n{}".format(nombre, texto.strip()))
        if len(piezas) >= max_archivos:
            break
    return "\n\n".join(piezas) if piezas else "(sin archivos de contrato todavia)"


def estado_git(carpeta: Path) -> str:
    """Rama, ultimos commits y cambios pendientes (si hay git disponible)."""
    base = Path(carpeta)
    if not (base / ".git").exists():
        return "(sin repositorio git)"

    def _git(*argumentos: str) -> str:
        try:
            _, salida, _ = procesos.ejecutar(["git"] + list(argumentos), cwd=base, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return ""
        return (salida or "").strip()

    rama = _git("rev-parse", "--abbrev-ref", "HEAD") or "(desconocida)"
    commits = _git("--no-pager", "log", "--oneline", "-5")
    cambios = _git("--no-pager", "status", "--short")
    piezas = ["rama: {}".format(rama)]
    if commits:
        piezas.append("ultimos commits:\n{}".format(commits))
    piezas.append("cambios pendientes:\n{}".format(cambios or "(ninguno)"))
    return "\n".join(piezas)


def contexto_del_repo(
    carpeta,
    stack: Dict[str, str] | None = None,
    tope_bytes: int = TOPE_POR_DEFECTO,
    extra: str = "",
) -> str:
    """Resumen del proyecto listo para el arquitecto: real, acotado y saneado.

    Args:
        carpeta: raiz del proyecto.
        stack: resultado de ``activacion.detectar_stack`` (opcional).
        tope_bytes: recorte de seguridad del texto devuelto.
        extra: notas adicionales (por ejemplo, el historial de la sesion).

    Returns:
        Texto con estructura, archivos de contrato, git y comandos, sin secretos.
    """
    base = Path(carpeta)
    datos = stack or {"stack": "desconocido", "prueba": "", "marcador": ""}
    secretos = secretos_del_proyecto(base)
    bloque = [
        "PROYECTO: {}".format(base.name),
        "ruta: {}".format(base),
        "stack: {} ({})".format(datos.get("stack"), datos.get("marcador") or "sin marcador"),
        "prueba real: {}".format(datos.get("prueba") or "(sin definir)"),
        "",
        "ESTRUCTURA (acotada):",
        arbol(base),
        "",
        "ARCHIVOS DE CONTRATO (cabeceras):",
        cabeceras(base),
        "",
        "GIT:",
        estado_git(base),
    ]
    if extra:
        bloque += ["", "NOTAS DEL PROYECTO:", extra]
    texto = sanea("\n".join(bloque), secretos)
    if len(texto) > tope_bytes:
        texto = texto[:tope_bytes] + "\n... [contexto recortado a {} caracteres]".format(tope_bytes)
    return texto

