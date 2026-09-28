"""Herramientas de archivos de la fabrica: leer, escribir, listar, mover y borrar.

Este modulo es la **unica** puerta de entrada a disco. Todas las funciones:

* reciben el nombre del proyecto y una ruta **relativa** dentro de el;
* pasan por :mod:`rutas`, que valida la raiz permitida, normaliza el nombre y
  bloquea binarios o nombres reservados de Windows;
* nunca tocan la carpeta ``.git`` (protegida a proposito: git la gestiona el,
  no la IA) ni los ficheros de bloqueo que pueden estar en uso.

No dependen de MCP ni de la red, asi que se pueden probar y reutilizar desde la
fabrica, el orquestador o un script suelto.
"""

from __future__ import annotations

import fnmatch
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import config as configuracion
import rutas

#: Extensiones que se pueden leer como texto aunque su sufijo no lo delate.
TEXTO_CONOCIDO = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json", ".jsonc",
    ".md", ".rst", ".txt", ".cfg", ".ini", ".toml", ".yaml", ".yml", ".env",
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".sql", ".sh", ".ps1",
    ".bat", ".cmd", ".c", ".h", ".cpp", ".hpp", ".cs", ".java", ".go", ".rs",
    ".rb", ".php", ".kt", ".swift", ".sol", ".vue", ".svelte", ".xml", ".svg",
    ".lock", ".mdc", ".log",
}

#: Carpetas que se omiten al listar o buscar: ruido o estado interno.
IGNORAR = {
    ".git", "venv", ".venv", "env", "__pycache__", "node_modules", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build", ".idea", ".vs", "capturas",
}

LECTURA_MAXIMA = 400_000


class ErrorArchivo(ValueError):
    """Operacion de archivos rechazada (ruta, tipo de fichero o uso incorrecto)."""


# --------------------------------------------------------------------------
# Utilidades internas
# --------------------------------------------------------------------------
def config_fabrica() -> configuracion.ConfigFabrica:
    """Config de la fabrica activa (se relee para respetar cambios del .env)."""
    return configuracion.cargar_fabrica()


def base_registrada(proyecto: str):
    """Carpeta real de un proyecto registrado, o ``None`` si no aplica.

    Los proyectos ACTIVADOS sobre una carpeta existente viven donde el usuario
    quiera (dentro de las raices permitidas): su ficha guarda esa ruta y las
    herramientas deben trabajar ahi, no en ``proyectos/<slug>``. Sin esto,
    activar una carpeta cuyo nombre no es un slug la dejaria desconectada.
    """
    nombre = (proyecto or "").strip()
    if not nombre:
        return None
    try:
        import fabrica  # import diferido a proposito: fabrica importa este modulo

        ficha = fabrica.cargar_registro().get(rutas.normalizar_nombre(nombre))
    except Exception:  # nunca tumbar una herramienta por leer el registro
        return None
    if not isinstance(ficha, dict):
        return None
    indicada = str(ficha.get("ruta") or "").strip()
    if not indicada:
        return None
    try:
        carpeta = Path(indicada).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    return carpeta if carpeta.is_dir() else None


def base_de_proyecto(proyecto: str) -> Path:
    """Carpeta base sobre la que operan las herramientas de archivos."""
    registrada = base_registrada(proyecto)
    if registrada is not None:
        return registrada
    return rutas.ruta_de_proyecto(proyecto) if (proyecto or "").strip() else rutas.raiz_fabrica()


def _resolver(proyecto: str, ruta: str, crear_padres: bool = False) -> Path:
    """Resuelve una ruta del proyecto aplicando el sandbox de :mod:`rutas`."""
    return rutas.resolver(
        ruta,
        base=base_de_proyecto(proyecto),
        crear_padres=crear_padres,
        permitir_externo=config_fabrica().permitir_externo,
    )


def _rechazar_git(destino: Path) -> None:
    """Protege la carpeta ``.git`` y los archivos internos de git."""
    if any(parte.lower() == ".git" for parte in destino.parts):
        raise ErrorArchivo(
            "La carpeta .git esta protegida: git la gestiona el, no la IA. "
            "Usa las herramientas de git para cambiar el estado del repositorio."
        )


def _es_binario(ruta: Path) -> bool:
    """Heuristica rapida: byte nulo en los primeros 4 KB o extension desconocida."""
    try:
        with ruta.open("rb") as gestor:
            muestra = gestor.read(4096)
    except OSError as exc:
        raise ErrorArchivo("No se pudo abrir {}: {}".format(ruta, exc))
    if b"\0" in muestra:
        return True
    sufijo = ruta.suffix.lower()
    return sufijo != "" and sufijo not in TEXTO_CONOCIDO


def _relativa(destino: Path, proyecto: str) -> str:
    """Ruta mostrada al modelo: relativa al proyecto cuando es posible."""
    base = base_de_proyecto(proyecto)
    try:
        return str(destino.relative_to(base)).replace("\\", "/")
    except ValueError:  # ruta externa permitida por ARQUITECTO_PERMITIR_EXTERNO
        return str(destino)


def _pista(archivo: Path) -> str:
    """Sugerencia con nombres parecidos cuando un archivo no existe."""
    if not archivo.parent.exists():
        return " (la carpeta '{}' tampoco existe)".format(archivo.parent.name)
    try:
        vecinos = sorted(p.name for p in archivo.parent.iterdir() if p.is_file())[:8]
    except OSError:
        return ""
    return " (en esa carpeta hay: {})".format(", ".join(vecinos)) if vecinos else ""


# --------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------
def leer_archivo(
    proyecto: str,
    ruta: str,
    desde: int = 1,
    hasta: int = 0,
    max_caracteres: int = 40_000,
) -> str:
    """Devuelve el contenido de un archivo de texto del proyecto.

    Args:
        proyecto: nombre del proyecto ('' para la raiz de la fabrica).
        ruta: ruta relativa dentro del proyecto.
        desde: primera linea a devolver (1 = principio).
        hasta: ultima linea a devolver (0 = hasta el final).
        max_caracteres: recorte de seguridad del texto devuelto.

    Raises:
        ErrorArchivo: si no existe, es una carpeta o parece binario.
    """
    archivo = _resolver(proyecto, ruta)
    if not archivo.exists():
        raise ErrorArchivo(
            "No existe {}:{}{}".format(
                proyecto or "(raiz)", _relativa(archivo, proyecto), _pista(archivo)
            )
        )
    if archivo.is_dir():
        raise ErrorArchivo(
            "{} es una carpeta, no un archivo. Usa listar_proyecto.".format(
                _relativa(archivo, proyecto)
            )
        )
    if _es_binario(archivo):
        raise ErrorArchivo(
            "{} no parece un archivo de texto (binario o extension no soportada).".format(
                _relativa(archivo, proyecto)
            )
        )

    texto = archivo.read_bytes()[:LECTURA_MAXIMA].decode("utf-8", errors="replace")
    lineas = texto.splitlines()
    total = len(lineas)

    inicio = max(1, int(desde or 1))
    fin = int(hasta or 0)
    if fin <= 0 or fin > total:
        fin = total
    seleccion = lineas[inicio - 1 : fin] if inicio <= total else []

    cuerpo = "\n".join(seleccion)
    aviso = ""
    if len(cuerpo) > max_caracteres:
        cuerpo = cuerpo[:max_caracteres]
        aviso = "\n\n[recortado: el archivo supera {} caracteres]".format(max_caracteres)

    cabecera = "### {} (lineas {}-{} de {})".format(
        _relativa(archivo, proyecto), inicio, min(fin, total), total
    )
    return "{}\n{}\n{}{}".format(cabecera, "-" * len(cabecera), cuerpo, aviso)


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------
def escribir_archivo(
    proyecto: str,
    ruta: str,
    contenido: str,
    sobreescribir: bool = True,
) -> str:
    """Crea o reemplaza un archivo de texto dentro del proyecto.

    Args:
        proyecto: nombre del proyecto.
        ruta: ruta relativa dentro del proyecto.
        contenido: texto completo del archivo (UTF-8, saltos LF).
        sobreescribir: si es ``False`` falla cuando el archivo ya existe.

    Returns:
        Mensaje de confirmacion apto para la IA.

    Raises:
        ErrorArchivo: si la ruta es invalida, esta protegida o ya existe.
    """
    if not isinstance(contenido, str):
        raise ErrorArchivo("El contenido debe ser texto.")
    destino = _resolver(proyecto, ruta, crear_padres=True)
    _rechazar_git(destino)

    existia = destino.exists()
    if existia and destino.is_dir():
        raise ErrorArchivo(
            "{} es una carpeta: elige otro nombre.".format(_relativa(destino, proyecto))
        )
    if existia and not sobreescribir:
        raise ErrorArchivo(
            "{} ya existe. Usa sobreescribir=True si quieres reemplazarlo.".format(
                _relativa(destino, proyecto)
            )
        )
    if not existia:
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ErrorArchivo("No se pudo crear la carpeta destino: {}".format(exc))

    try:
        with destino.open("w", encoding="utf-8", newline="\n") as gestor:
            gestor.write(contenido if contenido.endswith("\n") else contenido + "\n")
    except OSError as exc:
        raise ErrorArchivo("No se pudo escribir {}: {}".format(destino, exc))

    return "{} {} ({} caracteres)".format(
        "Reemplazado" if existia else "Creado",
        _relativa(destino, proyecto),
        len(contenido),
    )


def escribir_varios(proyecto: str, archivos: Dict[str, str]) -> List[str]:
    """Escribe un lote de archivos (ruta -> contenido) y devuelve los mensajes."""
    return [escribir_archivo(proyecto, ruta, texto) for ruta, texto in archivos.items()]


# --------------------------------------------------------------------------
# Carpetas, movimiento y borrado
# --------------------------------------------------------------------------
def crear_carpeta(proyecto: str, ruta: str) -> str:
    """Crea una carpeta (y sus padres) dentro del proyecto."""
    destino = _resolver(proyecto, ruta, crear_padres=True)
    _rechazar_git(destino)
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ErrorArchivo("No se pudo crear la carpeta {}: {}".format(destino, exc))
    return "Carpeta lista: {}/".format(_relativa(destino, proyecto))


def mover(proyecto: str, origen: str, destino: str) -> str:
    """Mueve (o renombra) un archivo o carpeta dentro del proyecto."""
    fuente = _resolver(proyecto, origen)
    objetivo = _resolver(proyecto, destino, crear_padres=True)
    _rechazar_git(fuente)
    _rechazar_git(objetivo)

    if not fuente.exists():
        raise ErrorArchivo("No existe {}.".format(_relativa(fuente, proyecto)))
    if objetivo.exists():
        raise ErrorArchivo(
            "El destino {} ya existe: borralo o elige otro nombre.".format(
                _relativa(objetivo, proyecto)
            )
        )
    try:
        shutil.move(str(fuente), str(objetivo))
    except (OSError, shutil.Error) as exc:
        raise ErrorArchivo("No se pudo mover: {}".format(exc))
    return "Movido {} -> {}".format(_relativa(fuente, proyecto), _relativa(objetivo, proyecto))


def borrar(proyecto: str, ruta: str, recursivo: bool = False) -> str:
    """Borra un archivo o carpeta del proyecto.

    Args:
        proyecto: nombre del proyecto.
        ruta: ruta relativa a borrar.
        recursivo: obligatorio para borrar carpetas (proteccion anti accidentes).

    Raises:
        ErrorArchivo: si no existe, es la raiz del proyecto, esta protegida o es
            una carpeta sin ``recursivo=True``.
    """
    objetivo = _resolver(proyecto, ruta)
    _rechazar_git(objetivo)

    if not objetivo.exists():
        raise ErrorArchivo("No existe {}.".format(_relativa(objetivo, proyecto)))
    if objetivo.resolve() == (rutas.ruta_de_proyecto(proyecto) if (proyecto or "").strip() else rutas.raiz_fabrica()):
        raise ErrorArchivo("No se puede borrar la raiz del proyecto: borra archivos concretos.")
    if objetivo.is_dir():
        if not recursivo:
            raise ErrorArchivo(
                "{} es una carpeta. Confirma con recursivo=True (se borra con todo su contenido).".format(
                    _relativa(objetivo, proyecto)
                )
            )
        try:
            shutil.rmtree(objetivo)
        except OSError as exc:
            raise ErrorArchivo("No se pudo borrar la carpeta: {}".format(exc))
        return "Borrada la carpeta {}/ (con su contenido)".format(_relativa(objetivo, proyecto))

    try:
        objetivo.unlink()
    except OSError as exc:
        raise ErrorArchivo("No se pudo borrar el archivo: {}".format(exc))
    return "Borrado {}".format(_relativa(objetivo, proyecto))


# --------------------------------------------------------------------------
# Exploracion
# --------------------------------------------------------------------------
def _recorrer(raiz: Path, profundidad: int, max_entradas: int) -> Tuple[List[str], bool]:
    """Arbol de texto (estilo ``tree``) con limite de profundidad y de entradas.

    Returns:
        (lineas, truncado)
    """
    lineas: List[str] = []
    truncado = False

    def visitar(carpeta: Path, nivel: int) -> None:
        nonlocal truncado
        if nivel > profundidad or truncado:
            return
        try:
            hijos = sorted(carpeta.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for hijo in hijos:
            if hijo.name in IGNORAR:
                continue
            if len(lineas) >= max_entradas:
                truncado = True
                return
            sangria = "    " * nivel
            if hijo.is_dir():
                lineas.append("{}{}/".format(sangria, hijo.name))
                visitar(hijo, nivel + 1)
            else:
                try:
                    peso = hijo.stat().st_size
                except OSError:
                    peso = 0
                lineas.append("{}{}  ({} B)".format(sangria, hijo.name, peso))

    visitar(raiz, 0)
    return lineas, truncado


def listar_proyecto(
    proyecto: str,
    subcarpeta: str = "",
    profundidad: int = 3,
    max_entradas: int = 200,
) -> str:
    """Muestra el arbol de archivos de un proyecto (o de una subcarpeta suya).

    Args:
        proyecto: nombre del proyecto ('' = lista las carpetas de la fabrica).
        subcarpeta: subruta concreta a listar.
        profundidad: niveles a mostrar.
        max_entradas: tope de lineas para no desbordar el contexto del modelo.
    """
    if not (proyecto or "").strip():
        raiz = rutas.raiz_fabrica()
        if not raiz.exists():
            return (
                "La carpeta de proyectos aun no existe: {}\n"
                "Se creara al crear el primer proyecto.".format(raiz)
            )
        proyectos = sorted(p.name for p in raiz.iterdir() if p.is_dir() and p.name not in IGNORAR)
        if not proyectos:
            return "Sin proyectos todavia en {}".format(raiz)
        return "Proyectos en {} ({}):\n{}".format(
            raiz, len(proyectos), "\n".join("- {}".format(nombre) for nombre in proyectos)
        )

    objetivo = _resolver(proyecto, subcarpeta) if subcarpeta else rutas.ruta_de_proyecto(proyecto)
    if not objetivo.exists():
        raise ErrorArchivo(
            "No existe la ruta '{}' dentro de {}.".format(subcarpeta or ".", proyecto)
        )
    if objetivo.is_file():
        return leer_archivo(proyecto, subcarpeta)

    lineas, truncado = _recorrer(objetivo, max(1, int(profundidad)), max(1, int(max_entradas)))
    titulo = "{}:{}".format(proyecto, _relativa(objetivo, proyecto))
    cuerpo = "\n".join(lineas) if lineas else "(vacio)"
    cola = "\n[... truncado: sube la profundidad solo si hace falta]" if truncado else ""
    return "{}\n{}\n{}{}".format(titulo, "=" * len(titulo), cuerpo, cola)


def buscar_archivos(proyecto: str, patron: str, max_resultados: int = 60) -> str:
    """Busca archivos por patron glob (``*.py``, ``**/test_*.py``, ``main?.js``)."""
    if not (patron or "").strip():
        raise ErrorArchivo("Indica un patron, por ejemplo '*.py' o '**/test_*.py'.")
    raiz = rutas.ruta_de_proyecto(proyecto)
    if not raiz.exists():
        raise ErrorArchivo("El proyecto {} no existe.".format(proyecto))

    encontrados: List[str] = []
    for ruta in sorted(raiz.rglob("*")):
        if not ruta.is_file():
            continue
        if any(parte in IGNORAR for parte in ruta.parts):
            continue
        if ruta.match(patron) or fnmatch.fnmatch(ruta.name, patron):
            encontrados.append(_relativa(ruta, proyecto))
            if len(encontrados) >= max_resultados:
                break

    if not encontrados:
        return "Sin resultados para '{}' en {}.".format(patron, proyecto)
    return "{} coincidencia(s) de '{}' en {}:\n{}".format(
        len(encontrados), patron, proyecto, "\n".join("- {}".format(r) for r in encontrados)
    )


def buscar_en_contenido(
    proyecto: str,
    texto: str,
    subcarpeta: str = "",
    max_resultados: int = 40,
    sensible_a_mayusculas: bool = False,
) -> str:
    """Busca un texto dentro de los archivos del proyecto (estilo grep).

    Devuelve ``ruta:linea: contenido`` y omite carpetas de ruido (``venv``,
    ``node_modules``, ``.git``...). Muy util para localizar donde tocar antes de
    reescribir un archivo.
    """
    aguja = texto or ""
    if not aguja.strip():
        raise ErrorArchivo("Indica el texto a buscar.")
    raiz = _resolver(proyecto, subcarpeta) if subcarpeta else rutas.ruta_de_proyecto(proyecto)
    if not raiz.exists():
        raise ErrorArchivo("No existe la ruta a buscar dentro de {}.".format(proyecto))

    objetivo = aguja if sensible_a_mayusculas else aguja.lower()
    resultados: List[str] = []
    revisados = 0
    truncado = False

    candidatos = raiz.rglob("*") if raiz.is_dir() else [raiz]
    for ruta in sorted(candidatos):
        if truncado or not ruta.is_file():
            continue
        if any(parte in IGNORAR for parte in ruta.parts):
            continue
        if ruta.suffix.lower() not in TEXTO_CONOCIDO:
            continue
        try:
            if ruta.stat().st_size > LECTURA_MAXIMA:
                continue
            contenido = ruta.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        revisados += 1
        for numero, linea in enumerate(contenido.splitlines(), 1):
            comparable = linea if sensible_a_mayusculas else linea.lower()
            if objetivo in comparable:
                resultados.append(
                    "{}:{}: {}".format(_relativa(ruta, proyecto), numero, linea.strip()[:160])
                )
                if len(resultados) >= max_resultados:
                    truncado = True
                    break

    if not resultados:
        return "Sin coincidencias de '{}' en {} ({} archivos revisados).".format(
            aguja, proyecto, revisados
        )
    cola = "\n[... hay mas coincidencias: afina la busqueda]" if truncado else ""
    return "{} coincidencia(s) de '{}' en {} ({} archivos revisados):\n{}{}".format(
        len(resultados), aguja, proyecto, revisados, "\n".join(resultados), cola
    )


def info_archivo(proyecto: str, ruta: str) -> str:
    """Tamano, tipo y fecha de modificacion de un archivo o carpeta."""
    objetivo = _resolver(proyecto, ruta)
    relativa = _relativa(objetivo, proyecto)
    if not objetivo.exists():
        return "No existe {}:{}{}".format(proyecto, relativa, _pista(objetivo))

    estadistica = objetivo.stat()
    if objetivo.is_dir():
        tipo = "carpeta"
    else:
        tipo = "texto" if not _es_binario(objetivo) else "binario"
    return "{} -> tipo={} | tamano={} B | modificado={:%Y-%m-%d %H:%M} | ruta={}".format(
        relativa,
        tipo,
        estadistica.st_size,
        datetime.fromtimestamp(estadistica.st_mtime),
        objetivo,
    )
