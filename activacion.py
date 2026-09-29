"""Activacion automatica: enchufa cualquier carpeta al Arquitecto y arranca el bucle.

Dos responsabilidades, ambas **idempotentes** (se pueden repetir sin romper nada):

* :func:`instalar_global` deja el servidor MCP y las reglas de arranque en la
  configuracion PERSONAL del usuario (``~/.cursor`` y los settings de Cline),
  de modo que cualquier carpeta que se abra en el IDE tenga ya las herramientas
  del arquitecto y sepa activarse sola.
* :func:`activar` es el disparador por carpeta: registra el proyecto en la
  fabrica, inyecta la capa de orquestacion que falte, detecta el stack, deja los
  artefactos del bucle (``INFORME.md`` / ``SUGERENCIAS.md``) y devuelve el kit de
  arranque con el contexto real del repositorio.

No depende de MCP ni de la red: se puede llamar desde el servidor MCP (tool
``activar_proyecto``), desde ``scripts/activar.py`` (tarea del IDE al abrir la
carpeta) o desde un script suelto.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

import config as configuracion
import contexto
import fabrica
import herramientas_archivos as archivos
import plantillas
import rutas

#: Nombre del servidor MCP con el que se registra el arquitecto en el IDE.
NOMBRE_MCP = "arquitecto-externo"

#: Archivo de reglas GLOBALES de Cursor (se aplica a cualquier carpeta abierta).
NOMBRE_REGLAS_GLOBALES = "arquitecto-global.mdc"

#: Artefactos del bucle de mejora continua que viven en cada proyecto.
ARCHIVO_INFORME = "INFORME.md"
ARCHIVO_SUGERENCIAS = "SUGERENCIAS.md"

#: Nombres de la capa de orquestacion, para informar de lo que se inyecta.
ARCHIVOS_ORQUESTACION = (
    ".clinerules",
    ".cursorrules",
    ".cursor/rules/arquitecto.mdc",
    ".cursor/mcp.json",
    "AGENTS.md",
    ".env.example",
)

#: Reglas que se instalan en la carpeta personal del usuario. Se aplican a
#: CUALQUIER carpeta abierta en el IDE y son el disparador del arranque.
REGLAS_GLOBALES = r"""---
description: Arranque automatico de la orquestacion (Arquitecto externo + fabrica)
globs:
alwaysApply: true
---

# Arranque automatico de la IA colaborativa

Este equipo de trabajo tiene tres piezas: el ARQUITECTO externo (herramientas
MCP del servidor `__SERVIDOR__`, que planifica y revisa), la FABRICA (crea y
mantiene proyectos) y TU (la IA del IDE, que escribe TODO el codigo y lo
ejecuta en esta maquina).

## Si la carpeta que se acaba de abrir no esta activada

Senal: no existe `.cursor/rules/arquitecto.mdc` (o `.clinerules`). Entonces,
ANTES de programar nada y sin pedir permiso:

1. Llama a la herramienta MCP `activar_proyecto` (sin argumentos usa la carpeta
   abierta). Devuelve el kit de arranque: nombre de proyecto registrado, stack
   detectado, comandos reales de prueba y el contexto del repositorio.
2. Lee las reglas que acaban de aparecer (`.clinerules`, `.cursorrules`,
   `.cursor/rules/arquitecto.mdc`) y cumplilas.
3. Llama a `consultar_arquitecto` con la peticion LITERAL del usuario y el kit
   de arranque como `contexto_del_codigo`.
4. Explicale al usuario, en 2-3 lineas, que activaste el proyecto y que propone
   el arquitecto.

Si `activar_proyecto` no existe en esta instalacion, dilo claro y pide al
usuario que ejecute una vez:

    venv\Scripts\python.exe scripts\instalar_global.py

## Bucle de mejora continua (no pares en el primer entregable)

Por cada bloque de trabajo, en este orden:

1. Implementa el siguiente paso del plan (codigo completo, pruebas de verdad).
2. `informe_de_trabajo`: que hiciste, evidencia REAL de las pruebas, archivos
   tocados y tus propias sugerencias de mejora.
3. `sugerir_mejoras`: la IA de la API lee ese informe + el contexto del
   repositorio y devuelve el siguiente lote priorizado.
4. Vuelve al paso 1 con lo que devuelva. Repite mientras el estado sea EN CURSO.
5. Para cuando veas `[[ARQUITECTO: FIN]]`, `estado del loop: TAREA TERMINADA` o
   cuando el usuario escriba PARAR. Entonces entrega el informe final y como
   probarlo.

Reglas duras: nada de credenciales en el contexto que mandas al arquitecto;
nada de delegar el codigo en otro modelo; nunca anuncies un resultado sin
haberlo ejecutado.
"""


def raiz_cursor() -> Path:
    """Carpeta personal de Cursor del usuario actual (``~/.cursor``)."""
    usuario = Path(os.environ.get("USERPROFILE") or Path.home()).expanduser()
    return usuario / ".cursor"


def carpeta_de(proyecto: str) -> Path:
    """Carpeta real de un proyecto (la registrada por su activacion, si la tiene)."""
    return archivos.base_de_proyecto(proyecto)


def _registrador():
    """Carga ``scripts/registrar_mcp.py`` (no es un paquete importable)."""
    import sys

    global _REGISTRADOR
    if _REGISTRADOR is None:
        ruta = Path(__file__).resolve().parent / "scripts" / "registrar_mcp.py"
        if str(ruta.parent) not in sys.path:
            sys.path.insert(0, str(ruta.parent))
        especificacion = importlib.util.spec_from_file_location("registrar_mcp", ruta)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        _REGISTRADOR = modulo
    return _REGISTRADOR


_REGISTRADOR = None


def _entrada_mcp(nombre: str, interprete: str = "") -> Dict:
    """Bloque JSON con el que se registra el servidor MCP en el IDE."""
    registrador = _registrador()
    return registrador._entrada(interprete or plantillas._interprete_mcp(), nombre)


def instalar_global(
    ruta_cursor: Path | None = None,
    nombre: str = NOMBRE_MCP,
    con_cline: bool = True,
) -> str:
    """Registra el servidor y las reglas de arranque para TODO el usuario.

    Es el unico paso que no se puede automatizar al 100% desde el propio IDE
    (huevo y gallina: Cursor tiene que releer su configuracion para cargar las
    herramientas), asi que se hace una vez y se reinicia el IDE.

    Args:
        ruta_cursor: carpeta personal de Cursor (por defecto ``~/.cursor``).
        nombre: nombre del servidor MCP.
        con_cline: registra tambien en los settings de Cline detectados.

    Returns:
        Informe en texto con lo escrito y el paso manual que queda.
    """
    registrador = _registrador()
    carpeta = Path(ruta_cursor) if ruta_cursor else raiz_cursor()
    entrada = _entrada_mcp(nombre)
    lineas = ["=" * 66, " INSTALACION GLOBAL DE LA ORQUESTACION ".center(66, "="), "=" * 66]

    mcp_global = carpeta / "mcp.json"
    lineas.append("[Cursor]  {}".format(registrador._fusionar(mcp_global, nombre, entrada)))

    reglas = carpeta / "rules" / NOMBRE_REGLAS_GLOBALES
    contenido_reglas = REGLAS_GLOBALES.replace("__SERVIDOR__", nombre)
    try:
        if reglas.is_file() and reglas.read_text(encoding="utf-8") == contenido_reglas:
            lineas.append("[Reglas]  ya estaban al dia en {}".format(reglas))
        else:
            reglas.parent.mkdir(parents=True, exist_ok=True)
            reglas.write_text(contenido_reglas, encoding="utf-8", newline="\n")
            lineas.append("[Reglas]  escritas en {}".format(reglas))
    except OSError as exc:
        lineas.append("[Reglas]  aviso: no se pudo escribir {} ({})".format(reglas, exc))

    if con_cline:
        destinos = registrador._destinos_cline()
        if not destinos:
            lineas.append("[Cline]   no se detecto Cline en esta maquina (se omite)")
        for ruta in destinos:
            lineas.append("[Cline]   {}".format(registrador._fusionar(ruta, nombre, entrada)))

    lineas.extend(
        [
            "",
            "PASO MANUAL (una sola vez): cierra y vuelve a abrir el IDE, o usa",
            "  Ctrl+Shift+P -> Developer: Reload Window",
            "Con eso el transporte MCP arranca con el .env actual y cualquier",
            "carpeta que abras ya tiene las herramientas del arquitecto.",
            "",
            "Comprobacion:  venv\\Scripts\\python.exe arquitecto_mcp.py --check",
        ]
    )
    return "\n".join(lineas)


# --------------------------------------------------------------------------
# Deteccion de stack y comandos reales de prueba
# --------------------------------------------------------------------------
#: Marcadores de stack, de mas especifico a mas generico. Cada entrada es
#: ``(stack, archivo_marcador, comando_de_prueba)``; el comando usa ``{python}``
#: cuando depende de un interprete local.
MARCADORES_STACK: Tuple[Tuple[str, str, str], ...] = (
    ("python", "pyproject.toml", "{python} -m pytest -q"),
    ("python", "requirements.txt", "{python} -m pytest -q"),
    ("python", "setup.py", "{python} -m pytest -q"),
    ("node", "package.json", "npm test"),
    ("go", "go.mod", "go test ./..."),
    ("rust", "Cargo.toml", "cargo test"),
    ("java", "pom.xml", "mvn -q test"),
    ("dotnet", "app.csproj", "dotnet test"),
)


def _interprete_del_proyecto(carpeta: Path) -> str:
    """Interprete Python preferido dentro del proyecto (su venv si lo tiene)."""
    piezas = ("venv", "Scripts", "python.exe") if os.name == "nt" else ("venv", "bin", "python")
    candidato = carpeta.joinpath(*piezas)
    if candidato.exists():
        return plantillas._ruta_posix(candidato)
    return "python"


def detectar_stack(carpeta: Path) -> Dict[str, str]:
    """Detecta el stack del proyecto y el comando con el que se prueba de verdad.

    Mira los marcadores habituales (``pyproject.toml``, ``package.json``,
    ``go.mod``...) y devuelve algo que la IA pueda ejecutar sin adivinar. Si no
    reconoce nada, lo dice: mejor preguntar que inventar un comando.

    Args:
        carpeta: raiz del proyecto.

    Returns:
        ``{"stack": ..., "prueba": ..., "marcador": ...}``.
    """
    for stack, marcador, comando in MARCADORES_STACK:
        if (carpeta / marcador).is_file():
            return {
                "stack": stack,
                "prueba": comando.format(python=_interprete_del_proyecto(carpeta)),
                "marcador": marcador,
            }
    for csproj in sorted(carpeta.glob("*.csproj")):
        return {"stack": "dotnet", "prueba": "dotnet test", "marcador": csproj.name}
    return {
        "stack": "desconocido",
        "prueba": "",
        "marcador": "",
        "nota": "Sin marcadores de stack: define con la IA los comandos de prueba antes de dar nada por hecho.",
    }


# --------------------------------------------------------------------------
# Escritura dentro de la carpeta activada
# --------------------------------------------------------------------------
def _escribir(carpeta: Path, relativo: str, contenido: str, sobreescribir: bool) -> bool:
    """Escribe un archivo dentro de la carpeta activada, con el sandbox de rutas.

    Returns:
        ``True`` si escribio; ``False`` si respeto un archivo que ya existia.
    """
    destino = rutas.resolver(
        relativo,
        base=carpeta,
        crear_padres=True,
        permitir_externo=configuracion.cargar_fabrica().permitir_externo,
        confinar_a_base=True,
    )
    if any(parte.lower() == ".git" for parte in destino.parts):
        raise ValueError("la carpeta .git esta protegida: la activacion no la toca")
    if destino.exists() and not sobreescribir:
        return False
    try:
        destino.write_text(
            contenido if contenido.endswith("\n") else contenido + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise ValueError("no se pudo escribir {} ({})".format(destino, exc))
    return True


def tarea_de_arranque() -> dict:
    """Tarea de IDE que re-activa el proyecto cada vez que se abre la carpeta.

    No es el disparador principal (una carpeta nueva no tiene ``.vscode``), pero
    si es la red de seguridad barata: reabrir el proyecto lo vuelve a dejar
    enchufado sin que el usuario haga nada.
    """
    python = plantillas._interprete_mcp()
    script = plantillas._ruta_posix(rutas.raiz_proyecto() / "scripts" / "activar.py")
    return {
        "label": "Arquitecto: activar orquestacion",
        "type": "shell",
        "command": '"{}" "{}" --ruta "${{workspaceFolder}}"'.format(python, script),
        "runOptions": {"runOn": "folderOpen"},
        "presentation": {"reveal": "silent", "panel": "dedicated", "close": True},
        "problemMatcher": [],
    }


def _fusionar_tareas(carpeta: Path) -> str:
    """Anade la tarea de arranque a ``.vscode/tasks.json`` sin pisar las del usuario."""
    destino = carpeta / ".vscode" / "tasks.json"
    tarea = tarea_de_arranque()
    datos: Dict = {}
    existentes: List = []
    if destino.exists():
        try:
            leido = json.loads(destino.read_text(encoding="utf-8-sig") or "{}")
        except (OSError, json.JSONDecodeError):
            return (
                "aviso: .vscode/tasks.json tiene comentarios o esta corrupto; no lo toco. "
                "Quita los comentarios y vuelve a activar para anadir la tarea de arranque."
            )
        if isinstance(leido, dict):
            datos = leido
            if isinstance(leido.get("tasks"), list):
                existentes = leido["tasks"]
    existentes = [
        entrada
        for entrada in existentes
        if not (isinstance(entrada, dict) and entrada.get("label") == tarea["label"])
    ]
    existentes.append(tarea)
    datos["version"] = datos.get("version") or "2.0.0"
    datos["tasks"] = existentes
    try:
        _escribir(carpeta, ".vscode/tasks.json", json.dumps(datos, ensure_ascii=False, indent=2), True)
    except ValueError as exc:
        return "aviso: {}".format(exc)
    return "tarea de arranque escrita en .vscode/tasks.json"


# --------------------------------------------------------------------------
# Artefactos del bucle de mejora continua
# --------------------------------------------------------------------------
def esqueleto_informe(nombre: str) -> str:
    """Plantilla de ``INFORME.md``: lo que la IA del IDE escribe cada ronda."""
    return """# Informe de trabajo - {nombre}

Lo escribe la IA del IDE al cerrar cada ronda y lo lee el ARQUITECTO externo.
Regla de oro: la evidencia se pega tal cual salio de la terminal, sin resumir.

## Que se hizo

- (pendiente)

## Evidencia real (comando y salida)

```
(pega aqui el comando exacto y su salida)
```

## Archivos tocados

- (pendiente)

## Sugerencias propias para la siguiente ronda

1. (pendiente: prioridad alta / media / baja y por que)
""".format(nombre=nombre)


def esqueleto_sugerencias(nombre: str) -> str:
    """Plantilla de ``SUGERENCIAS.md``: lo que devuelve el arquitecto cada ronda."""
    return """# Sugerencias del Arquitecto - {nombre}

Aqui se acumulan las rondas del bucle: el arquitecto lee el informe, el
contexto real del repositorio y el historial, y devuelve el siguiente lote
priorizado. La sesion se cierra cuando dice `[[ARQUITECTO: FIN]]` o cuando el
usuario escribe PARAR.

## Estado de la sesion

- rondas: 0
- estado: abierta

## Ronda 1

- (pendiente)
""".format(nombre=nombre)


# --------------------------------------------------------------------------
# Activacion de una carpeta
# --------------------------------------------------------------------------
def _carpeta_a_activar(ruta=None) -> Path:
    """Carpeta que se va a activar: la indicada o la que tiene abierto el IDE."""
    texto = str(ruta or "").strip().strip('"')
    candidata = Path(texto).expanduser() if texto else Path.cwd()
    if not candidata.is_absolute():
        candidata = Path.cwd() / candidata
    try:
        return candidata.resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError("No se pudo resolver la carpeta '{}': {}".format(texto, exc))


def activar(
    ruta=None,
    nombre: str = "",
    descripcion: str = "",
    forzar: bool = False,
) -> str:
    """Enchufa una carpeta al sistema completo (registro + capa + kit de arranque).

    Es idempotente: si la carpeta ya estaba activada solo completa lo que falte
    y devuelve el kit actualizado (con el contexto real del repositorio) para
    que la IA del IDE sepa por donde empezar sin tocar nada a mano.

    Args:
        ruta: carpeta a activar; por defecto, el directorio de trabajo (el que
            abre el IDE).
        nombre: nombre con el que se registra (por defecto, el de la carpeta).
        descripcion: objetivo en una frase, si se conoce.
        forzar: reescribe la capa de orquestacion aunque ya exista.

    Returns:
        Kit de arranque en texto.

    Raises:
        ValueError: si la carpeta no existe o se sale de las raices permitidas.
    """
    carpeta = _carpeta_a_activar(ruta)
    if not carpeta.exists() or not carpeta.is_dir():
        raise ValueError(
            "No existe la carpeta {} (creala primero o revisa la ruta).".format(carpeta)
        )

    cfg = configuracion.cargar_fabrica()
    if not cfg.permitir_externo:
        permitidas = rutas.raices_permitidas()
        if not any(rutas.esta_dentro(carpeta, raiz) for raiz in permitidas):
            raise ValueError(
                "La carpeta {} esta fuera de las raices permitidas.\n"
                "Permitido: {}\n"
                "Para activar proyectos en cualquier sitio, pon "
                "ARQUITECTO_PERMITIR_EXTERNO=true en el .env y reinicia el "
                "servidor MCP.".format(
                    carpeta, ", ".join(str(raiz) for raiz in permitidas)
                )
            )

    stack = detectar_stack(carpeta)
    limpio = rutas.normalizar_nombre(nombre or carpeta.name)
    ficha = fabrica.registrar_proyecto_existente(
        carpeta, nombre=limpio, stack=stack["stack"], descripcion=descripcion
    )

    capa = plantillas.archivos_de_orquestacion(
        limpio,
        ficha.descripcion,
        plantillas._nombre_paquete(limpio),
        ficha.plantillas or ["activado"],
    )
    escritos: List[str] = []
    omitidos: List[str] = []
    avisos: List[str] = []
    for relativo in ARCHIVOS_ORQUESTACION:
        contenido = capa.get(relativo)
        if contenido is None:
            continue
        existia = (carpeta / relativo).exists()
        try:
            if _escribir(carpeta, relativo, contenido, forzar or not existia):
                escritos.append("{}{}".format(relativo, " (reemplazado)" if existia else ""))
            else:
                omitidos.append(relativo)
        except ValueError as exc:
            avisos.append("{}: {}".format(relativo, exc))

    avisos.append(_fusionar_tareas(carpeta))
    for relativo, esqueleto in (
        (ARCHIVO_INFORME, esqueleto_informe),
        (ARCHIVO_SUGERENCIAS, esqueleto_sugerencias),
    ):
        if (carpeta / relativo).exists():
            omitidos.append(relativo)
            continue
        try:
            _escribir(carpeta, relativo, esqueleto(limpio), False)
            escritos.append(relativo)
        except ValueError as exc:
            avisos.append("{}: {}".format(relativo, exc))

    lineas = [
        "=" * 68,
        " PROYECTO ACTIVADO: {} ".format(limpio).center(68, "="),
        "=" * 68,
        "carpeta    : {}".format(carpeta),
        "registro   : {}".format(ficha.resumen()),
        "stack      : {} ({})".format(stack["stack"], stack.get("marcador") or "sin marcador"),
        "prueba     : {}".format(
            stack["prueba"] or "(definela con el arquitecto antes de dar nada por hecho)"
        ),
        "",
        "capa de orquestacion (solo se escribe lo que faltaba):",
    ]
    lineas.extend(["  + {}".format(x) for x in escritos] or ["  (no habia nada que escribir)"])
    lineas.extend(["  = {}".format(x) for x in omitidos])
    lineas.extend("  ! {}".format(x) for x in avisos if x)
    lineas.extend(
        [
            "",
            "CONTEXTO DEL REPOSITORIO (esto es lo que va en contexto_del_codigo):",
            "-" * 68,
            contexto.contexto_del_repo(carpeta, stack),
            "-" * 68,
            "",
            "PROTOCOLO DE ARRANQUE (en este orden, sin saltarse pasos):",
            "  1. consultar_arquitecto(idea_del_usuario=<peticion LITERAL del usuario>,",
            "     contexto_del_codigo=<stack + comando de prueba + el arbol de arriba>).",
            "  2. Implementa el plan TU MISMO con proyecto=\"{}\" y rutas relativas.".format(limpio),
            "  3. Ejecuta la prueba de verdad: {}".format(
                stack["prueba"] or "(el comando que acuerdes con el arquitecto)"
            ),
            "  4. informe_de_trabajo(proyecto=\"{}\", ...) con la evidencia real.".format(limpio),
            "  5. sugerir_mejoras(proyecto=\"{}\") y vuelve al paso 2.".format(limpio),
            "  Para cuando el arquitecto diga [[ARQUITECTO: FIN]] o el usuario escriba PARAR.",
            "=" * 68,
        ]
    )
    return "\n".join(lineas)

