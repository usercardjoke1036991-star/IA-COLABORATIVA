"""Seguridad de rutas: un unico punto por el que pasa toda la E/S de disco.

Reglas que aplica este modulo (no escribe nada: solo calcula y valida rutas):

* Todo lo que se crea o se modifica debe quedar dentro de una **raiz permitida**:
  el propio proyecto plantilla o la raiz de la fabrica de proyectos.
* Los nombres de proyecto o carpeta se normalizan a *slug*, de modo que no
  puedan contener ``..``, rutas absolutas encubiertas ni nombres reservados
  de Windows (``CON``, ``NUL``, ``LPT1``...).
* Con ``confinar_a_base=True`` (lo que usan las herramientas de archivos) el
  destino tiene que quedar **dentro de la base declarada**, o sea, dentro del
  proyecto activo. Ni ``..``, ni ``./sub/..``, ni ``../otro-proyecto/x`` pueden
  saltarse ese candado, y tampoco las rutas absolutas o *rooted* (``C:\\...``,
  ``/etc/...``, ``\\\\?\\...``, ``\\\\host\\recurso``) ni los nombres reservados de
  Windows en cualquier tramo (``CON``, ``NUL``, ``COM1``...): el sandbox del
  proyecto manda incluso sobre ``ARQUITECTO_PERMITIR_EXTERNO`` (ese permiso solo
  relaja las raices globales de la comprobacion que no confina, como el registro
  de proyectos).
* Con ``ARQUITECTO_PERMITIR_EXTERNO=true`` la restriccion se relaja para poder
  escribir en cualquier ruta absoluta. Es comodo y es peligroso: dejalo en
  ``false`` salvo que sepas exactamente por que lo necesitas.
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import List

import config as configuracion


class ErrorRuta(ValueError):
    """Ruta rechazada por las reglas de seguridad de la fabrica."""


#: Nombres que Windows no permite usar como carpeta o archivo.
RESERVADOS = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}

_CARACTERES_VALIDOS = re.compile(r"[^a-z0-9._-]+")
_GUIONES_REPETIDOS = re.compile(r"[-_.]{2,}")

#: Extensiones que la fabrica se niega a escribir: son vectores de ejecucion
#: accidental en Windows o binarios compilados que no tienen sentido aqui.
EXTENSIONES_PROHIBIDAS = {".exe", ".dll", ".msi", ".scr", ".com"}


def normalizar_nombre(nombre: str, longitud_maxima: int = 64) -> str:
    """Convierte texto libre en un nombre de carpeta/repositorio seguro (slug)."""
    base = unicodedata.normalize("NFKD", (nombre or "").strip().lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = base.replace(" ", "-").replace("_", "-")
    base = _CARACTERES_VALIDOS.sub("-", base).strip("-._")
    base = _GUIONES_REPETIDOS.sub("-", base)
    base = base[:longitud_maxima].strip("-._")

    if not base or base in {".", ".."}:
        raise ErrorRuta(
            "Nombre invalido: usa letras, numeros y guiones (por ejemplo 'arbitraje-bot')."
        )
    if base.lower() in RESERVADOS:
        base = "{}-app".format(base)
    return base


def raiz_proyecto() -> Path:
    """Carpeta de esta plantilla orquestadora (donde vive el codigo del MCP)."""
    return Path(configuracion.RAIZ_PROYECTO).resolve()


def raiz_fabrica() -> Path:
    """Carpeta donde la fabrica crea los proyectos nuevos."""
    return Path(configuracion.cargar_fabrica().raiz_proyectos).resolve()


def raices_permitidas() -> List[Path]:
    """Raices dentro de las cuales el sistema puede escribir."""
    raices = [raiz_proyecto()]
    candidata = raiz_fabrica()
    if candidata not in raices:
        raices.append(candidata)
    return raices


def _texto_comparable(ruta: Path) -> str:
    return os.path.normcase(str(Path(ruta).resolve())).rstrip("\\/")


def esta_dentro(ruta: Path, raiz: Path) -> bool:
    """True si ``ruta`` esta dentro de ``raiz`` (o es la propia raiz)."""
    objetivo = _texto_comparable(ruta)
    contenedor = _texto_comparable(raiz)
    return objetivo == contenedor or objetivo.startswith(contenedor + os.sep)


def _nombre_reservado(candidata: Path) -> str:
    """Primer tramo de la ruta que Windows reserva (``CON``, ``NUL``, ``COM1``...).

    Mira **cualquier** tramo, no solo el ultimo: ``CON/notas.md`` tambien acaba en
    un dispositivo en Windows. Y compara tambien la raiz del nombre, porque
    ``con.txt`` apunta al mismo dispositivo que ``CON``.
    """
    for parte in candidata.parts:
        limpio = parte.split(":")[0].strip().rstrip(".")
        if not limpio:
            continue
        if limpio.lower() in RESERVADOS or limpio.split(".")[0].lower() in RESERVADOS:
            return parte
    return ""


def resolver(
    destino: str,
    base: Path | None = None,
    permitir_externo: bool = False,
    crear_padres: bool = False,
    confinar_a_base: bool = False,
) -> Path:
    """Valida y devuelve la ruta absoluta de ``destino``.

    Args:
        destino: ruta relativa (a ``base``) o absoluta.
        base: carpeta de referencia para las rutas relativas. Por defecto, la
            raiz de la fabrica de proyectos.
        permitir_externo: salta la comprobacion de raices permitidas.
        crear_padres: crea los directorios intermedios si no existen.
        confinar_a_base: exige que el destino acabe **dentro de ``base``**. Es
            el candado del proyecto activo: bloquea ``..``, ``./sub/..``,
            ``../otro-proyecto``, las rutas absolutas o *rooted* (``C:\\...``,
            ``/etc/...``, ``\\\\?\\...``, ``\\\\host\\recurso``) y los nombres
            reservados de Windows en cualquier tramo. Se comprueba antes de crear
            carpetas, asi que un intento rechazado no deja rastro en disco.

    Raises:
        ErrorRuta: si la ruta se sale de las raices permitidas, si intenta
            salirse de ``base`` (con ``confinar_a_base``) o si es invalida.
    """
    texto = (destino or "").strip().strip('"')
    if not texto:
        raise ErrorRuta("Ruta vacia: indica un archivo o una carpeta.")
    if "\0" in texto:
        raise ErrorRuta("Ruta invalida: contiene un byte nulo.")

    referencia = Path(base) if base is not None else raiz_fabrica()
    candidata = Path(texto)

    # Candado del sandbox del proyecto. El orden importa y va ANTES de tocar el
    # disco: (1) fuera las rutas absolutas o *rooted* (unidad, ``C:\``, ``/``,
    # ``\\?\``, ``\\.\``, ``\\host\recurso``) porque no son "relativas al
    # proyecto" ni siquiera con el permiso de escritura externa, (2) fuera los
    # nombres reservados de Windows en cualquier tramo y (3) fuera cualquier '..'.
    # ``resolve()`` colapsa "./sub/.." a la propia raiz, asi que confiar solo en la
    # comparacion de rutas dejaria pasar formas raras de escribir el mismo ataque;
    # en Windows ademas una ruta *rooted* sin unidad (``/etc/passwd``) no es
    # ``is_absolute()`` pero al unirla a la base se lleva por delante la raiz.
    if confinar_a_base:
        if candidata.is_absolute() or texto.startswith(("/", "\\")):
            raise ErrorRuta(
                "Ruta fuera del proyecto: '{}' es absoluta o de red/dispositivo "
                "(letra de unidad, \\\\?\\, \\\\host\\recurso). Las herramientas de archivos "
                "solo aceptan rutas relativas a la raiz del proyecto.".format(texto)
            )

        reservado = _nombre_reservado(candidata)
        if reservado:
            raise ErrorRuta(
                "Ruta fuera del proyecto: '{}' usa el nombre reservado '{}', que en "
                "Windows apunta a un dispositivo y no a un archivo.".format(texto, reservado)
            )

        if ".." in candidata.parts:
            raise ErrorRuta(
                "Ruta fuera del proyecto por '..': '{}' intenta subir de nivel y las "
                "herramientas de archivos no salen de su carpeta. Escribe la ruta "
                "directa desde la raiz del proyecto (por ejemplo 'docs/notas.md').".format(
                    texto
                )
            )

    if not candidata.is_absolute():
        candidata = referencia / candidata

    try:
        absoluta = candidata.resolve()
    except (OSError, RuntimeError) as exc:  # pragma: no cover - defensivo
        raise ErrorRuta("No se pudo resolver la ruta {}: {}".format(texto, exc))

    if absoluta.name.lower() in RESERVADOS:
        raise ErrorRuta(
            "Nombre reservado del sistema: '{}'. Cambialo.".format(absoluta.name)
        )
    if absoluta.suffix.lower() in EXTENSIONES_PROHIBIDAS:
        raise ErrorRuta(
            "La extension '{}' esta bloqueada por seguridad (binarios). "
            "Compila aparte si de verdad lo necesitas.".format(absoluta.suffix)
        )

    if not permitir_externo:
        raices = raices_permitidas()
        if not any(esta_dentro(absoluta, raiz) for raiz in raices):
            raise ErrorRuta(
                "Ruta fuera de las raices permitidas: {}\n"
                "Permitido: {}\n"
                "Si de verdad quieres escribir ahi, pon "
                "ARQUITECTO_PERMITIR_EXTERNO=true en el .env y reinicia el servidor MCP.".format(
                    absoluta, ", ".join(str(raiz) for raiz in raices)
                )
            )

    # Candado del sandbox del proyecto: ademas de resolver (para atrapar los
    # enlaces que apuntan fuera y las rutas absolutas) se comprueba que el
    # resultado quede dentro de la base. Va ANTES de crear carpetas, para que un
    # intento rechazado no deje ni rastro. No lo salta ARQUITECTO_PERMITIR_EXTERNO
    # a proposito: ese permiso es para elegir donde vive una carpeta, no para que
    # una herramienta se salga de su proyecto. ``esta_dentro`` normaliza las dos
    # rutas, asi que los nombres cortos de Windows (8.3) y los enlaces validos no
    # dan falsos positivos.
    if confinar_a_base and not esta_dentro(absoluta, referencia):
        raise ErrorRuta(
            "Ruta fuera del proyecto: '{}' acaba en {}\n"
            "La base del proyecto es {} y las herramientas de archivos no salen "
            "de ahi: usa una ruta relativa a su raiz y sin '..'.".format(
                texto, absoluta, referencia.resolve()
            )
        )

    if crear_padres:
        try:
            absoluta.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ErrorRuta("No se pudo crear el directorio padre: {}".format(exc))
    return absoluta


def ruta_de_proyecto(nombre: str, crear: bool = False) -> Path:
    """Devuelve la carpeta de un proyecto de la fabrica a partir de su nombre."""
    carpeta = raiz_fabrica() / normalizar_nombre(nombre)
    if crear:
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ErrorRuta("No se pudo crear la carpeta del proyecto: {}".format(exc))
    return carpeta


def resolver_en_proyecto(
    proyecto: str,
    ruta: str,
    crear_padres: bool = False,
    permitir_externo: bool = False,
) -> Path:
    """Resuelve una ruta relativa **dentro** de un proyecto de la fabrica.

    Es el modo que usan las herramientas de archivos: asi el PROGRAMADOR puede
    escribir ``"app/main.py"`` indicando aparte el proyecto al que pertenece, sin
    depender del directorio de trabajo del servidor MCP. La ruta queda confinada
    al proyecto: ``..`` no sirve para colarse en el de al lado.
    """
    base = ruta_de_proyecto(proyecto) if (proyecto and proyecto.strip()) else raiz_fabrica()
    return resolver(
        ruta,
        base=base,
        crear_padres=crear_padres,
        permitir_externo=permitir_externo,
        confinar_a_base=True,
    )
