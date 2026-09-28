"""Prueba de punta a punta del activador de carpetas (:mod:`activacion`).

``activar_proyecto`` es la puerta de entrada del sistema: convierte una carpeta
normal, **vacia y ajena a la fabrica** en un proyecto registrado, con la capa de
orquestacion puesta y los artefactos del bucle listos. Este script lo ejecuta de
verdad DOS veces sobre una carpeta limpia y comprueba, con hashes SHA-256, que:

1. la primera pasada deja los 6 archivos de orquestacion + ``INFORME.md`` +
   ``SUGERENCIAS.md`` + ``.vscode/tasks.json`` y registra el proyecto con su
   ruta real, su stack y el estado ``activado``;
2. la segunda pasada **no modifica ni un byte** (idempotencia medida, no
   prometida) y el kit lo dice ("no habia nada que escribir");
3. los archivos que el usuario ya tenia (por ejemplo un ``AGENTS.md`` propio) no
   se pisan.

Por defecto trabaja en una carpeta temporal nueva y usa el registro REAL de la
fabrica (que es justo lo que se quiere verificar). Con ``--registro-aislado``
apunta el registro a un temporal y no toca ``datos/proyectos.json``.

Uso:
    venv\\Scripts\\python.exe scripts\\verificar_activador.py
    venv\\Scripts\\python.exe scripts\\verificar_activador.py --registro-aislado
    venv\\Scripts\\python.exe scripts\\verificar_activador.py --carpeta "%USERPROFILE%\\Downloads\\prueba_activador"
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:  # activacion vive en la raiz del proyecto
    sys.path.insert(0, str(RAIZ))

import activacion  # noqa: E402 - despues de ajustar sys.path, a proposito
import fabrica  # noqa: E402
import rutas  # noqa: E402

#: Artefactos que el activador anade ademas de la capa de orquestacion.
ARCHIVOS_EXTRA = (activacion.ARCHIVO_INFORME, activacion.ARCHIVO_SUGERENCIAS, ".vscode/tasks.json")

#: Archivo propio del usuario: si el activador lo cambia, la prueba falla.
ARCHIVO_SENTINELA = "AGENTS.md"

#: Contenido exacto que debe sobrevivir a la activacion.
SENTINELA = "# mis notas de casa\n\nNO PISAR: esto lo escribio el usuario.\n"

_resultados = []

#: Carpeta temporal del registro aislado (``--registro-aislado``). Se borra al
#: cerrar la verificacion: antes se quedaba en ``%TEMP%`` una por ejecucion.
_temporal_registro = None


def _ok(titulo: str, detalle: str = "") -> None:
    _resultados.append(True)
    print("  [OK]   {}{}".format(titulo, " -> " + detalle if detalle else ""))


def _fallo(titulo: str, detalle: str = "") -> None:
    _resultados.append(False)
    print("  [FALLO] {}{}".format(titulo, " -> " + detalle if detalle else ""))


def _paso(numero: int, titulo: str) -> None:
    print("")
    print("-" * 70)
    print("PASO {}: {}".format(numero, titulo))


def _borrar_temporal(ruta: Path, intentos: int = 3) -> bool:
    """Borra una carpeta temporal de verdad y dice si lo consiguio.

    Copia del ayudante de ``verificar_fabrica.py`` y ``verificar_servidor.py``
    (los tres scripts son independientes y no comparten modulo). En Windows
    ``shutil.rmtree(..., ignore_errors=True)`` se calla ante objetos de git de
    solo lectura o un fichero bloqueado: aqui se quita el solo-lectura, se
    reintenta y se informa del resultado real.
    """
    for espera in (0.0, 0.3, 0.9, 1.5)[:intentos]:
        if espera:
            time.sleep(espera)
        for entrada in (ruta, *ruta.rglob("*")):
            try:
                os.chmod(entrada, stat.S_IWRITE)
            except OSError:  # pragma: no cover - entrada ya borrada o sin permisos
                pass
        shutil.rmtree(ruta, ignore_errors=True)
        if not ruta.exists():
            return True
    return False


def _huellas(carpeta: Path) -> dict:
    """Hash SHA-256 de cada archivo de la carpeta (la carpeta ``.git`` se ignora)."""
    huellas = {}
    for ruta in sorted(Path(carpeta).rglob("*")):
        if not ruta.is_file() or ".git" in ruta.parts:
            continue
        huellas[ruta.relative_to(carpeta).as_posix()] = hashlib.sha256(
            ruta.read_bytes()
        ).hexdigest()
    return huellas


def _diferentes(antes: dict, despues: dict) -> list:
    """Archivos creados, borrados o modificados entre dos fotos de hashes."""
    claves = sorted(set(antes) | set(despues))
    return [clave for clave in claves if antes.get(clave) != despues.get(clave)]


def _preparar(carpeta: Path) -> None:
    """Deja la carpeta como una carpeta cualquiera del usuario, pero sin capa."""
    sobrantes = [ruta.name for ruta in carpeta.iterdir()] if carpeta.exists() else []
    if sobrantes:
        raise ValueError(
            "la carpeta {} no esta vacia ({}). Usa una carpeta nueva o vaciala a mano; "
            "esta prueba necesita medir la activacion desde cero.".format(
                carpeta, ", ".join(sorted(sobrantes)[:5])
            )
        )
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (carpeta / ARCHIVO_SENTINELA).write_text(SENTINELA, encoding="utf-8")


def _carpeta_de_prueba(ruta: str) -> Path:
    """Carpeta a activar: la indicada o una temporal recien creada."""
    if (ruta or "").strip():
        return Path(ruta.strip().strip('"')).expanduser().resolve()
    return Path(tempfile.mkdtemp(prefix="activador-")).resolve()


def _resumen() -> int:
    """Cierra la verificacion: recuento de comprobaciones y codigo de salida."""
    print("")
    print("=" * 70)
    fallos = _resultados.count(False)
    print(
        " RESUMEN: {} comprobaciones OK, {} FALLOS ".format(
            _resultados.count(True), fallos
        ).center(70, "=")
    )
    print("=" * 70)
    if _temporal_registro is not None and not _borrar_temporal(_temporal_registro):
        print("AVISO: no se pudo borrar el registro temporal: {}".format(_temporal_registro))
    return 1 if fallos else 0


def main(argv=None) -> int:
    """Activa una carpeta ajena dos veces y comprueba el resultado byte a byte."""
    analizador = argparse.ArgumentParser(prog="verificar_activador", description=__doc__)
    analizador.add_argument(
        "--carpeta", default="", help="carpeta a activar (por defecto, una temporal nueva)"
    )
    analizador.add_argument(
        "--registro-aislado", action="store_true", help="no toca datos/proyectos.json"
    )
    opciones = analizador.parse_args(argv)

    os.environ.setdefault("ARQUITECTO_LOG", "WARNING")
    # La carpeta vive fuera de las raices de la fabrica A PROPOSITO: es justo lo
    # que hay que verificar (una carpeta cualquiera del usuario, no un proyecto).
    os.environ["ARQUITECTO_PERMITIR_EXTERNO"] = "true"
    if opciones.registro_aislado:
        global _temporal_registro
        _temporal_registro = Path(tempfile.mkdtemp(prefix="registro-")).resolve()
        os.environ["ARQUITECTO_REGISTRO"] = str(_temporal_registro / "proyectos.json")

    print("=" * 70)
    print(" VERIFICACION DEL ACTIVADOR DE CARPETAS ".center(70, "="))
    print("=" * 70)

    _paso(1, "Preparacion de una carpeta ajena y vacia")
    try:
        carpeta = _carpeta_de_prueba(opciones.carpeta)
        _preparar(carpeta)
    except (OSError, ValueError) as exc:
        _fallo("no se pudo preparar la carpeta de prueba", str(exc))
        return _resumen()
    print("  carpeta : {}".format(carpeta))
    print("  registro: {}".format(fabrica.ruta_registro()))
    _ok("carpeta lista sin capa: solo requirements.txt y un AGENTS.md propio")

    _paso(2, "Primera activacion")
    try:
        activacion.activar(ruta=carpeta, descripcion="verificacion del activador")
    except Exception as exc:  # noqa: BLE001 - es una verificacion: se informa y se para
        _fallo("activar()", "{}: {}".format(type(exc).__name__, exc))
        return _resumen()
    nombre = rutas.normalizar_nombre(carpeta.name)

    faltan = [
        relativo
        for relativo in activacion.ARCHIVOS_ORQUESTACION
        if not (carpeta / relativo).is_file()
    ]
    if faltan:
        _fallo("capa de orquestacion incompleta", ", ".join(faltan))
    else:
        _ok(
            "capa de orquestacion completa",
            "{} archivos".format(len(activacion.ARCHIVOS_ORQUESTACION)),
        )

    extra_faltan = [relativo for relativo in ARCHIVOS_EXTRA if not (carpeta / relativo).is_file()]
    if extra_faltan:
        _fallo("faltan artefactos del bucle", ", ".join(extra_faltan))
    else:
        _ok("artefactos del bucle creados", ", ".join(ARCHIVOS_EXTRA))

    try:
        sentinela = (carpeta / ARCHIVO_SENTINELA).read_text(encoding="utf-8")
    except OSError as exc:
        _fallo("no se pudo leer {}".format(ARCHIVO_SENTINELA), str(exc))
    else:
        if sentinela == SENTINELA:
            _ok("no piso {} del usuario".format(ARCHIVO_SENTINELA))
        else:
            _fallo("{} del usuario fue modificado".format(ARCHIVO_SENTINELA))

    try:
        ficha = fabrica.ficha_proyecto(nombre)
    except Exception as exc:  # noqa: BLE001 - ficha ausente o registro ilegible
        _fallo("el proyecto no quedo registrado", str(exc))
    else:
        misma_ruta = Path(ficha.ruta).resolve() == carpeta
        if misma_ruta and ficha.estado == "activado":
            _ok("ficha registrada con la ruta real", ficha.resumen())
        else:
            _fallo(
                "ficha registrada con datos inesperados",
                "ruta={} estado={}".format(ficha.ruta, ficha.estado),
            )

    registro = fabrica.ruta_registro()
    try:
        registrados = fabrica.cargar_registro()
    except Exception as exc:  # noqa: BLE001 - registro ausente o corrupto
        _fallo("registro ilegible", "{}: {}".format(registro, exc))
    else:
        if nombre in registrados:
            _ok("aparece en el registro", "{} ({} proyectos)".format(registro, len(registrados)))
        else:
            _fallo("no aparece en el registro", str(registro))

    _paso(3, "Segunda activacion (idempotencia medida)")
    antes = _huellas(carpeta)
    try:
        kit2 = activacion.activar(ruta=carpeta)
    except Exception as exc:  # noqa: BLE001 - la segunda pasada no debe romperse
        _fallo("la segunda activacion fallo", "{}: {}".format(type(exc).__name__, exc))
        return _resumen()
    despues = _huellas(carpeta)

    cambios = _diferentes(antes, despues)
    if cambios:
        _fallo(
            "la segunda pasada modifico archivos",
            "{} ({} de {} archivos)".format(", ".join(cambios[:8]), len(cambios), len(antes)),
        )
    else:
        _ok(
            "ni un byte cambiado en la segunda pasada",
            "{} archivos con el mismo SHA-256".format(len(antes)),
        )
    if "no habia nada que escribir" in kit2:
        _ok("el kit de la segunda pasada lo reconoce")
    else:
        _fallo("el kit no detecto que ya estaba activado")

    _paso(4, "Siguiente paso")
    print("  El proyecto '{}' sigue registrado con la ruta: {}".format(nombre, carpeta))
    print("  Para ensuciar lo menos posible: borra la carpeta y, si quieres,")
    print("  quita su entrada de {}.".format(registro))
    return _resumen()


if __name__ == "__main__":
    sys.exit(main())
