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
4. corta el ARBOL del hijo si se pasa del tiempo: en Windows lo mete en un
   *Job Object* con ``KILL_ON_JOB_CLOSE`` (matar solo al padre deja vivos a los
   nietos, cada uno con su propia consola), en POSIX lo lanza en su propio grupo
   y mata al grupo entero. Despues libera las tuberias sin quedarse esperando a
   un proceso rebelde.
5. sanea los argumentos antes de lanzar: un ``argv[0]`` que empiece por ``-`` se
   leeria como una opcion (inyeccion de argumentos) y un byte NUL corta la
   cadena al llegar al sistema. Es la unica puerta, asi que ningun llamador
   puede olvidarse de validar.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

#: Segundos que se espera a un hijo ya matado antes de dar sus tuberias por perdidas.
ESPERA_TRAS_MATAR = 5.0

#: Segundos que se espera a ``taskkill`` cuando hay que cortar el arbol a mano.
ESPERA_DE_TASKKILL = 10.0

#: Clase de informacion de un Job Object con limites extendidos (Windows).
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

#: Bandera que mata todos los procesos del job al cerrar su ultima referencia.
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


class _ContadoresES(ctypes.Structure):
    """``IO_COUNTERS``: contadores de E/S que exige la estructura de limites."""

    _fields_ = [
        (nombre, ctypes.c_ulonglong)
        for nombre in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _LimitesBasicos(ctypes.Structure):
    """``JOBOBJECT_BASIC_LIMIT_INFORMATION`` (solo se usa ``LimitFlags``)."""

    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_ulong),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_ulong),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", ctypes.c_ulong),
        ("SchedulingClass", ctypes.c_ulong),
    ]


class _LimitesExtendidos(ctypes.Structure):
    """``JOBOBJECT_EXTENDED_LIMIT_INFORMATION``: aqui vive ``KILL_ON_JOB_CLOSE``."""

    _fields_ = [
        ("BasicLimitInformation", _LimitesBasicos),
        ("IoInfo", _ContadoresES),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]

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


def _abrir_job() -> int:
    """Crea el Job Object donde se mete el hijo (0 si no aplica o no se puede).

    Con ``KILL_ON_JOB_CLOSE`` el sistema mata TODOS los procesos del job cuando se
    cierra su ultima referencia: es lo que garantiza que no queden nietos vivos
    cuando hay que cortar por tiempo (matar solo al padre no los toca).
    """
    if os.name != "nt":
        return 0
    try:
        crear = ctypes.windll.kernel32.CreateJobObjectW
        crear.restype = ctypes.c_void_p
        crear.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        job = crear(None, None)
        if not job:
            return 0
        limites = _LimitesExtendidos()
        limites.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ajustado = ctypes.windll.kernel32.SetInformationJobObject(
            ctypes.c_void_p(job),
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limites),
            ctypes.sizeof(limites),
        )
        if not ajustado:
            _cerrar_job(job)
            return 0
        return job
    except (AttributeError, OSError, TypeError, ValueError):
        return 0


def _meter_en_job(job: int, proceso: subprocess.Popen) -> bool:
    """Mete al hijo recien creado en el job: desde ahi, sus nietos son del job."""
    if not job or os.name != "nt":
        return False
    try:
        handle = int(proceso._handle)  # noqa: SLF001 - handle real en Windows
    except (AttributeError, TypeError, ValueError):
        return False
    try:
        return bool(
            ctypes.windll.kernel32.AssignProcessToJobObject(
                ctypes.c_void_p(job), ctypes.c_void_p(handle)
            )
        )
    except (AttributeError, OSError, ValueError):
        return False


def _cerrar_job(job: int) -> None:
    """Suelta el job: cualquier proceso que quede dentro muere al cerrarlo."""
    if not job or os.name != "nt":
        return
    try:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(job))
    except (AttributeError, OSError, ValueError):
        pass


def _terminar_job(job: int) -> None:
    """Mata todos los procesos del job (padre, hijos y nietos)."""
    if not job or os.name != "nt":
        return
    try:
        ctypes.windll.kernel32.TerminateJobObject(ctypes.c_void_p(job), 1)
    except (AttributeError, OSError, ValueError):
        pass


def _matar_arbol(proceso: subprocess.Popen) -> None:
    """Corta el arbol sin Job Object: ``taskkill /T /F`` o el grupo de procesos."""
    pid = getattr(proceso, "pid", None)
    if not pid:
        return
    if os.name == "nt":
        try:
            subprocess.Popen(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                creationflags=flags_sin_consola(),
            ).wait(timeout=ESPERA_DE_TASKKILL)
        except (OSError, subprocess.SubprocessError):
            pass
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (OSError, AttributeError, ValueError):
        pass


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
        # En POSIX el hijo estrena grupo propio: asi se puede matar el arbol entero.
        "start_new_session": os.name != "nt",
    }


def _validar_argumentos(comando: Sequence[str]) -> List[str]:
    """Sanea la lista de argumentos antes de entregarsela al sistema.

    Aunque aqui NUNCA se interpreta una linea de comandos (``shell`` esta
    apagado), un valor que venga de fuera (la idea del usuario, el plan del
    arquitecto, una ruta del ``.env``) puede colarse como OPCION si empieza por
    ``-``, y un byte NUL corta la cadena al llegar al sistema. Se valida en este
    unico punto de salida de procesos para que ningun llamador pueda olvidarlo.

    Raises:
        ValueError: si el comando esta vacio, si el programa a ejecutar empieza
            por ``-`` o si algun argumento lleva un byte NUL.
    """
    piezas = [str(pieza) for pieza in comando]
    if not piezas:
        raise ValueError("comando vacio: falta el programa a ejecutar")
    if piezas[0].startswith("-"):
        raise ValueError(
            "el programa a ejecutar no puede empezar por '-': {!r}".format(piezas[0])
        )
    for pieza in piezas:
        if "\x00" in pieza:
            raise ValueError(
                "un argumento lleva un byte NUL y no se puede ejecutar: {!r}".format(pieza)
            )
    return piezas


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
        ValueError: si el comando no pasa el saneado de :func:`_validar_argumentos`.
    """
    job = _abrir_job()
    try:
        proceso = subprocess.Popen(
            _validar_argumentos(comando),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs_proceso(entorno_extra),
        )
    except BaseException:
        _cerrar_job(job)
        raise
    if job and not _meter_en_job(job, proceso):
        _cerrar_job(job)  # no se pudo: el corte caera a taskkill /T /F
        job = 0
    try:
        salida, error = proceso.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _cortar(proceso, job)
        raise
    except BaseException:
        _cortar(proceso, job)
        raise
    if proceso.returncode is None:  # defensivo: no deberia ocurrir
        _cortar(proceso, job)
    else:
        _cerrar_job(job)
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


def _cortar(proceso: subprocess.Popen, job: int = 0) -> None:
    """Corta el ARBOL del hijo y libera sus tuberias sin quedarse esperando.

    Matar solo al padre no basta en Windows: los nietos (otro ``python.exe``, un
    ``git`` con su propia consola...) siguen vivos minutos enteros, que es
    exactamente el sintoma del cuelgue original. Con Job Object se van todos;
    sin el, se cae a ``taskkill /PID <pid> /T /F``.
    """
    if job:
        _terminar_job(job)
    else:
        _matar_arbol(proceso)
    try:
        proceso.kill()
    except OSError:
        pass
    _cerrar_job(job)
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
