"""Ejecucion de procesos externos a prueba de cuelgues (git, gh, python, pytest).

Por que existe este modulo
--------------------------
El servidor MCP corre por ``stdio``: sin consola propia y con su entrada estandar
conectada a la tuberia del protocolo. En ese contexto, un hijo de consola (git,
gh, python) que HEREDA ese stdin se queda bloqueado en el arranque. Medido en
esta maquina, dentro del proceso del servidor real:

* ``git --version`` heredando el stdin ............... colgado (mas de 10 s, en
  la practica nunca terminaba: habia procesos ``git`` vivos minutos despues).
* el mismo comando con ``stdin=DEVNULL`` ............ 0.05 s.

Consecuencia: cualquier herramienta MCP que lanzara un proceso (``estado_git``,
``estado_fabrica``, ``commit_proyecto``, ``publicar_en_github``,
``preparar_entorno``, ``activar_proyecto``) se colgaba hasta el timeout del IDE.

Solucion: un unico punto de salida, :func:`ejecutar`, que

1. no hereda el stdin (``DEVNULL``),
2. no deja que Windows cree una consola nueva para el hijo
   (``CREATE_NO_WINDOW``; en otros sistemas no aplica),
3. marca el entorno como no interactivo (git/gh fallan en vez de esperar datos),
4. corta el hijo si se pasa del tiempo y libera las tuberias sin quedarse
   esperando a un proceso rebelde.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, Sequence, Tuple

#: Segundos que se espera a un hijo ya matado antes de dar sus tuberias por perdidas.
ESPERA_TRAS_MATAR = 5.0

#: Variables que evitan que git/gh se queden pidiendo datos por una consola que no hay.
ENTORNO_NO_INTERACTIVO = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "echo",
    "GCM_INTERACTIVE": "never",
    "GH_PROMPT_DISABLED": "1",
}


def flags_sin_consola() -> int:
    """Banderas de creacion del hijo: sin ventana ni consola nueva (0 fuera de Windows)."""
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def entorno(extra: Dict[str, str] | None = None) -> Dict[str, str]:
    """Entorno del hijo: el del servidor, marcado como no interactivo."""
    valores = dict(os.environ)
    for clave, valor in ENTORNO_NO_INTERACTIVO.items():
        valores.setdefault(clave, valor)
    if extra:
        valores.update(extra)
    return valores


def kwargs_proceso(extra: Dict[str, str] | None = None) -> Dict[str, object]:
    """Argumentos seguros para ``subprocess``: sin heredar stdin ni crear consola.

    Se usa tambien en los sitios que llaman a ``subprocess`` directamente
    (por ejemplo, para crear enlaces en Windows).
    """
    return {
        "stdin": subprocess.DEVNULL,
        "env": entorno(extra),
        "creationflags": flags_sin_consola(),
        "shell": False,
    }


def ejecutar(
    comando: Sequence[str],
    cwd,
    timeout: float = 300,
    entorno_extra: Dict[str, str] | None = None,
) -> Tuple[int, str, str]:
    """Ejecuta ``comando`` en ``cwd`` y devuelve ``(codigo, salida, error)``.

    Args:
        comando: programa y argumentos (sin ``shell``: se pasa la lista tal cual).
        cwd: carpeta de trabajo del hijo.
        timeout: segundos maximos; al pasarse, el hijo se mata y se levanta
            :class:`subprocess.TimeoutExpired`.
        entorno_extra: variables que se anaden (o pisan) al entorno del hijo.

    Raises:
        FileNotFoundError: si el ejecutable no existe o no esta en el PATH.
        subprocess.TimeoutExpired: si el hijo no termina dentro de ``timeout``.
    """
    proceso = subprocess.Popen(
        [str(pieza) for pieza in comando],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs_proceso(entorno_extra),
    )
    try:
        salida, error = proceso.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _cortar(proceso)
        raise
    if proceso.returncode is None:  # defensivo: no deberia ocurrir
        _cortar(proceso)
    return proceso.returncode, salida or "", error or ""


def ejecutar_texto(
    comando: Sequence[str],
    cwd,
    timeout: float = 300,
    entorno_extra: Dict[str, str] | None = None,
) -> Tuple[int, str]:
    """Como :func:`ejecutar`, pero con la salida y el error ya unidos en un texto."""
    codigo, salida, error = ejecutar(comando, cwd, timeout, entorno_extra)
    return codigo, "{}\n{}".format(salida, error).strip()


def _cortar(proceso: subprocess.Popen) -> None:
    """Mata el proceso y libera sus tuberias sin quedarse colgado esperandolo."""
    try:
        proceso.kill()
    except OSError:
        return
    try:
        proceso.communicate(timeout=ESPERA_TRAS_MATAR)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass
    for flujo in (proceso.stdout, proceso.stderr):
        try:
            if flujo is not None:
                flujo.close()
        except (OSError, ValueError):
            pass


def ruta_legible(cwd) -> str:
    """Devuelve la ruta de trabajo tal como se muestra en los mensajes de error."""
    return str(Path(cwd))
