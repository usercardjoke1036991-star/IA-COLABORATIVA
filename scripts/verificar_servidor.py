"""Verificacion de la instalacion del Arquitecto Externo.

Comprueba, de verdad y paso a paso, que todo el sistema funciona:

1. Dependencias instaladas (mcp + requests) y sus versiones.
2. Modulos del proyecto importables y configuracion cargada.
3. El servidor MCP se construye y registra sus 31 herramientas.
4. El arranque GLOBAL esta instalado en el IDE: reglas de Cursor y servidor en
   ``~/.cursor/mcp.json`` y en los ``cline_mcp_settings.json`` que existan.
5. Se invoca una herramienta A TRAVES del gestor de MCP (no llamando a la
   funcion de Python directamente), para validar el camino real que usa Cursor.
6. Se crea un proyecto con ``instalar_dependencias=true`` a traves del tool,
   con pip apuntado a un puerto cerrado: la respuesta debe traer el estado
   pendiente, el comando exacto y como reintentar.
7. El registro real de proyectos (``datos/proyectos.json``) sigue igual que al
   empezar: se compara su SHA-256 antes y despues de toda la verificacion.

Ademas, el script se aisla a si mismo: mientras dura la verificacion el registro
y la carpeta de proyectos viven en un temporal propio (``entorno_aislado``) y el
entorno se restaura al terminar. Asi un paso futuro que cree un proyecto, o
cualquier tool que escriba en el registro, no puede tocar ``datos/`` ni
``proyectos/`` ni aunque se olvide de redirigirlos.

Por defecto se ejecuta en modo simulado (sin red ni API key). Con --real usa el
proveedor configurado en tu .env y si consume tokens.

Uso:
    venv\\Scripts\\python.exe scripts\\verificar_servidor.py
    venv\\Scripts\\python.exe scripts\\verificar_servidor.py --real
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

HERRAMIENTAS_ESPERADAS = {
    # Arquitecto (planifica)
    "consultar_arquitecto",
    "reportar_progreso",
    "ver_estado",
    "exportar_plan",
    "reiniciar_sesion",
    # Fabrica de proyectos
    "estado_fabrica",
    "catalogo_plantillas",
    "crear_proyecto",
    "listar_proyectos",
    "ver_proyecto",
    # Archivos
    "listar_archivos",
    "leer_archivo",
    "escribir_archivo",
    "crear_carpeta",
    "mover_archivo",
    "borrar_archivo",
    "buscar_en_proyecto",
    "buscar_archivos",
    # Entorno, git y GitHub
    "preparar_entorno",
    "estado_git",
    "commit_proyecto",
    "publicar_en_github",
    # Activacion automatica y bucle de mejora continua
    "activar_proyecto",
    "informe_de_trabajo",
    "sugerir_mejoras",
    "estado_de_sesion",
    # Programador externo
    "estado_programador",
    "pedir_codigo_al_programador",
    "aplicar_codigo_del_programador",
    "corregir_con_el_programador",
    "reiniciar_programador",
}

_anchos = (70,)
_resultados = []


def _ok(titulo: str, detalle: str = "") -> None:
    _resultados.append(True)
    print("  [OK]   {}{}".format(titulo, " -> " + detalle if detalle else ""))


def _fallo(titulo: str, detalle: str = "") -> None:
    _resultados.append(False)
    print("  [FALLO] {}{}".format(titulo, " -> " + detalle if detalle else ""))


def _paso(numero: int, titulo: str) -> None:
    print("")
    print("-" * _anchos[0])
    print("PASO {}: {}".format(numero, titulo))


def _borrar_temporal(ruta: Path, intentos: int = 3) -> bool:
    """Borra la carpeta temporal de verdad y dice si lo consiguio.

    ``shutil.rmtree(ignore_errors=True)`` se calla en Windows cuando el arbol
    trae objetos de git de solo lectura (``.git/objects``) o un fichero
    bloqueado por un proceso recien terminado (un ``venv`` que acaba de
    crearse, el antivirus...): el borrado falla y el script seguia diciendo que
    habia limpiado. Aqui se quita el solo-lectura, se reintenta con una espera
    corta y se devuelve el resultado real.
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


# --------------------------------------------------------------------------
# Cinturon del script: registro y carpeta de proyectos en un temporal
# --------------------------------------------------------------------------
#: Prefijo de la carpeta temporal que usa el cinturon (facil de reconocer y de
#: borrar si una ejecucion se corta a lo bruto).
PREFIJO_TEMPORAL = "verificacion-servidor-"

#: Claves de entorno que deciden DONDE escribe la fabrica. Si el script no las
#: redirige, cualquier paso que cree o registre un proyecto escribe en el
#: registro real (``datos/proyectos.json``) y en ``proyectos/``.
ENTORNO_ISLAMIENTO = ("ARQUITECTO_REGISTRO", "ARQUITECTO_CARPETA_PROYECTOS")

#: Nombre del registro temporal. Distinto de ``proyectos.json`` a proposito: asi
#: nunca puede coincidir con un registro de verdad que viviera en esa carpeta.
NOMBRE_REGISTRO_AISLADO = "verificacion-servidor.json"


@contextlib.contextmanager
def entorno_aislado():
    """Deja el registro y la carpeta de proyectos en un temporal del script.

    El paso 6 ya aisla lo suyo, pero eso obliga a acordarse en cada paso nuevo:
    basta que alguien anada un paso que cree un proyecto (o que invoque un tool
    que lo haga) para que ``datos/proyectos.json`` de verdad acabe con la ficha
    de un temporal ya borrado. Este cinturon va una capa por fuera: mientras dure
    el bloque, *cualquier* paso ve un registro y una carpeta temporales, y al
    salir se restaura el entorno y se borra lo que se creo.

    Se respeta lo que el usuario (o el CI) ya haya redirigido a mano: en ese caso
    lo que venga puesto no se toca y solo se rellena lo que falte. Cuando el
    registro se redirige y la carpeta ya venia puesta, el registro temporal vive
    junto a ella, que es una de las raices que :func:`fabrica.raices_registro`
    admite.

    Yields:
        La carpeta temporal del cinturon, o ``None`` si no hizo falta crear
        ninguna (el entorno ya venia redirigido, o solo faltaba el registro).
    """
    antes = {clave: os.environ.get(clave) for clave in ENTORNO_ISLAMIENTO}
    falta_registro = not antes["ARQUITECTO_REGISTRO"]
    falta_carpeta = not antes["ARQUITECTO_CARPETA_PROYECTOS"]
    if not falta_registro and not falta_carpeta:
        yield None
        return

    temporal = None
    if falta_carpeta:
        temporal = Path(tempfile.mkdtemp(prefix=PREFIJO_TEMPORAL)).resolve()
        os.environ["ARQUITECTO_CARPETA_PROYECTOS"] = str(temporal / "proyectos")
    if falta_registro:
        # Junto a la carpeta de proyectos: asi el registro tambien cae dentro de
        # las raices que la fabrica admite, venga la carpeta del cinturon o del
        # usuario.
        os.environ["ARQUITECTO_REGISTRO"] = str(
            Path(os.environ["ARQUITECTO_CARPETA_PROYECTOS"]) / NOMBRE_REGISTRO_AISLADO
        )
    try:
        yield temporal
    finally:
        for clave, valor in antes.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        if temporal is not None:
            _borrar_temporal(temporal)


# --------------------------------------------------------------------------
# Paso 1: dependencias
# --------------------------------------------------------------------------
def paso_dependencias() -> bool:
    _paso(1, "Dependencias")
    valido = True
    try:
        import importlib.metadata as metadatos

        print("  python  : {}".format(sys.version.split()[0]))
        print("  ejecutable: {}".format(sys.executable))
        for paquete in ("mcp", "requests"):
            try:
                print("  {}      : {}".format(paquete.ljust(8), metadatos.version(paquete)))
                _ok("paquete '{}' presente".format(paquete))
            except Exception:
                _fallo(
                    "paquete '{}' ausente".format(paquete),
                    "ejecuta: pip install -r requirements.txt",
                )
                valido = False
    except Exception as exc:  # pragma: no cover
        _fallo("no se pudo leer la version de los paquetes", str(exc))
        valido = False
    return valido


# --------------------------------------------------------------------------
# Paso 2: modulos y configuracion
# --------------------------------------------------------------------------
def paso_modulos():
    _paso(2, "Modulos del proyecto y configuracion")
    try:
        import config as configuracion
        import historial  # noqa: F401
        import protocolo  # noqa: F401
        import proveedores  # noqa: F401
        from arquitecto import Arquitecto
    except Exception as exc:
        _fallo("import de los modulos del proyecto", str(exc))
        return None, None

    _ok("modulos importados", "config, protocolo, proveedores, historial, arquitecto")

    conf = configuracion.cargar()
    print("  configuracion: {}".format(conf.resumen()))
    problemas = conf.problemas()
    if problemas:
        for fallo in problemas:
            print("  aviso: {}".format(fallo))
        _ok("configuracion cargada (sin credenciales; usa --real solo si las tienes)")
    else:
        _ok("configuracion valida para el proveedor '{}'".format(conf.proveedor))

    try:
        arquitecto = Arquitecto(config=conf)
        _ok("nucleo del Arquitecto instanciado")
    except Exception as exc:
        _fallo("instanciar el Arquitecto", str(exc))
        return conf, None
    return conf, arquitecto


# --------------------------------------------------------------------------
# Paso 3: construccion del servidor MCP
# --------------------------------------------------------------------------
def paso_servidor():
    _paso(3, "Servidor MCP y herramientas registradas")
    try:
        import arquitecto_mcp
    except Exception as exc:
        _fallo("import de arquitecto_mcp", str(exc))
        return None

    try:
        servidor = arquitecto_mcp.construir_servidor()
    except SystemExit as exc:
        _fallo("construir el servidor MCP", str(exc))
        return None
    _ok("servidor FastMCP 'ArquitectoExterno' creado")

    listadas = _listar_herramientas(servidor)
    if not listadas:
        _fallo("no se pudieron listar las herramientas del servidor")
        return servidor

    print("  herramientas: {}".format(", ".join(listadas)))
    faltan = HERRAMIENTAS_ESPERADAS - set(listadas)
    sobran = set(listadas) - HERRAMIENTAS_ESPERADAS
    if faltan:
        _fallo("faltan herramientas", ", ".join(sorted(faltan)))
    else:
        _ok("las {} herramientas esperadas estan registradas".format(len(HERRAMIENTAS_ESPERADAS)))
    if sobran:
        print("  nota: hay herramientas adicionales: {}".format(", ".join(sorted(sobran))))

    _comprobar_esquema_instalar(servidor)
    return servidor


def _comprobar_esquema_instalar(servidor) -> None:
    """Verifica que el tool expone ``instalar_dependencias`` como opcional.

    El contrato es ``bool | None`` con ``default=None``: sin argumento, el tool
    decide segun ``ARQUITECTO_INSTALAR_DEPENDENCIAS``; con ``true``/``false``,
    manda el usuario. Si el esquema no dejara el campo opcional, el agente del
    IDE no podria distinguir "no lo he pedido" de "que se instale".
    """
    herramientas = getattr(getattr(servidor, "_tool_manager", None), "_tools", {})
    herramienta = herramientas.get("crear_proyecto")
    if herramienta is None:
        _fallo("no se pudo leer el esquema de crear_proyecto")
        return
    esquema = getattr(herramienta, "parameters", None)
    if hasattr(esquema, "model_json_schema"):
        esquema = esquema.model_json_schema()
    propiedades = (esquema or {}).get("properties", {}) if isinstance(esquema, dict) else {}
    campo = propiedades.get("instalar_dependencias")
    if not isinstance(campo, dict):
        _fallo("crear_proyecto no declara instalar_dependencias en su esquema")
        return
    texto = json.dumps(campo)
    if "boolean" in texto and "null" in texto and campo.get("default", "ausente") is None:
        _ok("el esquema de crear_proyecto deja instalar_dependencias opcional", texto)
    else:
        _fallo("el esquema de instalar_dependencias no es opcional", texto)


def _listar_herramientas(servidor):
    try:
        return sorted(servidor._tool_manager._tools.keys())
    except AttributeError:
        pass
    try:
        return sorted(herramienta.name for herramienta in asyncio.run(servidor.list_tools()))
    except Exception:
        return []


def _a_texto(resultado) -> str:
    """Extrae el texto de la respuesta de una herramienta MCP."""
    if isinstance(resultado, tuple) and resultado:
        resultado = resultado[0]
    bloques = resultado if isinstance(resultado, (list, tuple)) else [resultado]
    partes = []
    for bloque in bloques:
        texto = getattr(bloque, "text", None)
        partes.append(texto if texto is not None else str(bloque))
    return "\n".join(partes)


def _invocar(servidor, nombre: str, argumentos: dict):
    """Invoca una herramienta a traves del gestor real de MCP."""
    gestor = getattr(servidor, "_tool_manager", None)
    if gestor is None or not hasattr(gestor, "call_tool"):
        return None, "el SDK no expone _tool_manager.call_tool"
    try:
        resultado = asyncio.run(gestor.call_tool(nombre, argumentos))
    except Exception as exc:
        return None, "{}: {}".format(type(exc).__name__, exc)
    return _a_texto(resultado), None


# --------------------------------------------------------------------------
# Paso 4: arranque global en el IDE (Cursor y Cline)
# --------------------------------------------------------------------------
def paso_global() -> bool:
    """Comprueba que el arranque automatico esta instalado en ESTA maquina.

    Sin este paso, abrir una carpeta virgen no enchufa nada: el agente del IDE no
    veria ``activar_proyecto`` y las reglas globales no se leerian solas. Se mira
    el disco (reglas + `mcp.json` de Cursor + settings de Cline), no la memoria
    del proceso.
    """
    _paso(4, "Arranque global instalado en el IDE (Cursor y Cline)")
    try:
        import activacion
    except Exception as exc:  # noqa: BLE001 - verificacion: se informa del fallo
        _fallo("import de activacion", str(exc))
        return False

    valido = True

    # 1) Reglas globales de Cursor: son el disparador del arranque.
    reglas = activacion.raiz_cursor() / "rules" / activacion.NOMBRE_REGLAS_GLOBALES
    if not reglas.is_file():
        _fallo("faltan las reglas globales de Cursor", str(reglas))
        valido = False
    else:
        texto = reglas.read_text(encoding="utf-8", errors="replace")
        if "alwaysApply: true" in texto and "activar_proyecto" in texto:
            _ok("reglas globales de Cursor", "alwaysApply + activar_proyecto")
        else:
            _fallo("reglas globales incompletas (revisa el frontmatter)", str(reglas))
            valido = False

    # 2) Servidor MCP en la configuracion personal de cada agente.
    registrador = activacion._registrador()
    casa = activacion.raiz_cursor()
    destinos = [casa / "mcp.json"] + registrador._destinos_cline()
    presentes = [ruta for ruta in destinos if ruta.exists()]
    if not presentes and not casa.exists():
        _ok("no se detecto Cursor ni Cline en esta maquina (nada que comprobar)")
        return valido
    if not presentes:
        _fallo("Cursor esta instalado pero no hay mcp.json global", str(casa / "mcp.json"))
        valido = False
        return valido

    for ruta in presentes:
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _fallo("config MCP ilegible", "{}: {}".format(ruta, exc))
            valido = False
            continue
        servidores = datos.get("mcpServers") if isinstance(datos, dict) else None
        if isinstance(servidores, dict) and activacion.NOMBRE_MCP in servidores:
            _ok("servidor '{}' en {}".format(activacion.NOMBRE_MCP, ruta.parent.name), str(ruta))
        else:
            _fallo("el servidor no esta en {}".format(ruta), str(ruta))
            valido = False

    if not valido:
        print("  arreglo: venv\\Scripts\\python.exe scripts\\instalar_global.py")
    return valido


# --------------------------------------------------------------------------
# Paso 5: invocacion real a traves del protocolo MCP
# --------------------------------------------------------------------------
def paso_invocacion(servidor) -> bool:
    _paso(5, "Invocacion de las herramientas a traves del gestor MCP")
    if servidor is None:
        _fallo("se omite: el servidor no se pudo construir")
        return False

    idea = (
        "Necesito una API en FastAPI con login JWT y un endpoint de salud, "
        "con pruebas automatizadas."
    )
    texto, error = _invocar(
        servidor, "consultar_arquitecto", {"idea_del_usuario": idea}
    )
    if error:
        _fallo("consultar_arquitecto", error)
        return False
    if "ARQUITECTO EXTERNO" not in texto:
        _fallo("consultar_arquitecto devolvio un texto inesperado", texto[:120])
        return False
    _ok("consultar_arquitecto respondio con el plan")
    print("      estado: {}".format(_estado_del_loop(texto)))

    terminada = False
    for intento in range(1, 4):
        texto, error = _invocar(
            servidor,
            "reportar_progreso",
            {
                "resumen_de_lo_hecho": "Implementado el bloque {} del plan y verificado localmente.".format(intento),
                "prompt_original": idea,
                "archivos_tocados": "app/main.py, tests/test_main.py",
            },
        )
        if error:
            _fallo("reportar_progreso", error)
            return False
        print("      informe {}: {}".format(intento, _estado_del_loop(texto)))
        if "TAREA TERMINADA" in texto:
            terminada = True
            break

    if terminada:
        _ok("el loop se cierra solo: el programador deja de iterar")
    else:
        _fallo("el arquitecto no cerro el loop en 3 informes (revisa el modo simulado)")

    texto, error = _invocar(servidor, "ver_estado", {})
    if error or "ESTADO" not in (texto or ""):
        _fallo("ver_estado", error or "respuesta inesperada")
    else:
        _ok("ver_estado responde con el diagnostico")

    texto, error = _invocar(servidor, "exportar_plan", {"ruta": ".verificacion_plan.md"})
    if error or "exportado" not in (texto or "").lower():
        _fallo("exportar_plan", error or "respuesta inesperada")
    else:
        _ok("exportar_plan escribe el archivo")
        _limpiar(RAIZ / ".verificacion_plan.md")

    # El reinicio se prueba al final: borra la memoria y deja el servidor limpio.
    texto, error = _invocar(servidor, "reiniciar_sesion", {})
    if error or "borrada" not in (texto or "").lower():
        _fallo("reiniciar_sesion", error or "respuesta inesperada")
    else:
        _ok("reiniciar_sesion limpia la memoria")

    return terminada


#: Entorno que hace fallar a pip al instante: un indice en un puerto cerrado de
#: la propia maquina. El paso 6 lo usa para ejercitar la ruta de fallo real a
#: traves del tool, sin salir a Internet.
ENTORNO_INDICE_MUERTO_MCP = {
    "PIP_INDEX_URL": "http://127.0.0.1:1/simple",
    "PIP_RETRIES": "0",
    "PIP_TIMEOUT": "2",
    "PIP_NO_CACHE_DIR": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
}


def paso_dependencias_mcp(servidor) -> bool:
    """Crea un proyecto con dependencias A TRAVES del tool, no llamando a Python.

    Se crea en una carpeta temporal (el ``proyectos/`` real no se toca) y con pip
    apuntado a un puerto cerrado, asi que se ejercita la ruta de fallo: lo que se
    verifica es que la respuesta del tool lleva el estado, el comando exacto y
    como reintentar, y que despues no queda nada en disco.

    El registro de proyectos se aisla igual que la carpeta. ``ARQUITECTO_PERSISTIR=0``
    solo protege el historial del arquitecto, no ``datos/proyectos.json``: sin
    redirigir ``ARQUITECTO_REGISTRO`` este paso dejaba en el registro REAL la ficha
    de un proyecto temporal que se borra unas lineas mas abajo.

    El cinturon del script (``entorno_aislado``) ya deja el registro real fuera de
    alcance, asi que esta capa interna cubre el error contrario: que un cambio de
    este paso escriba en el registro que la verificacion tenia al empezar. El de
    verdad lo vigila el paso 7.
    """
    _paso(6, "Dependencias a traves del tool crear_proyecto")
    if servidor is None:
        _fallo("se omite: el servidor no se pudo construir")
        return False

    import fabrica
    import rutas

    temporal = Path(tempfile.mkdtemp(prefix="verificacion-mcp-")).resolve()
    nombre = "verificacion-mcp-deps"
    registro_temporal = temporal / "proyectos.json"
    try:
        # Foto del registro real ANTES de tocar nada: si al final no coincide, la
        # verificacion ha escrito donde no debia.
        registro_real = fabrica.cargar_registro()
        error_registro = ""
    except Exception as exc:  # noqa: BLE001 - la verificacion informa del fallo
        registro_real = None
        error_registro = "{}: {}".format(type(exc).__name__, exc)

    claves = list(ENTORNO_INDICE_MUERTO_MCP) + [
        "ARQUITECTO_CARPETA_PROYECTOS",
        "ARQUITECTO_REGISTRO",
    ]
    anteriores = {clave: os.environ.get(clave) for clave in claves}
    os.environ.update(ENTORNO_INDICE_MUERTO_MCP)
    os.environ["ARQUITECTO_CARPETA_PROYECTOS"] = str(temporal)
    os.environ["ARQUITECTO_REGISTRO"] = str(registro_temporal)
    try:
        creado = rutas.ruta_de_proyecto(nombre)  # se calcula con el temporal ya activo
        texto, error = _invocar(
            servidor,
            "crear_proyecto",
            {
                "nombre": nombre,
                "descripcion": "proyecto temporal de la verificacion MCP",
                "plantillas_seleccion": "python",
                "con_git": False,
                "publicar": False,
                "instalar_dependencias": True,
            },
        )
    finally:
        for clave, valor in anteriores.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor

    if error:
        _fallo("crear_proyecto con instalar_dependencias=true", error)
        _borrar_temporal(temporal)
        return False

    print("\n".join("      " + linea for linea in (texto or "").splitlines()[:14]))
    valido = True
    for esperado, titulo in (
        ("estado_dependencias=pendiente_error_red", "el tool informa del fallo real de pip"),
        ("Comando exacto:", "el tool devuelve el comando exacto ejecutado"),
        ("Reintenta con preparar_entorno", "el tool dice como reintentar la instalacion"),
        (str(creado), "el tool informa de la ruta del proyecto"),
    ):
        if esperado in (texto or ""):
            _ok(titulo)
        else:
            _fallo(titulo, "no aparece '{}' en la respuesta".format(esperado))
            valido = False

    if str(creado).startswith(str(temporal)):
        _ok("el proyecto de prueba vive en la carpeta temporal", str(creado))
    else:
        _fallo("el proyecto de prueba se salio de la carpeta temporal", str(creado))
        valido = False

    if registro_temporal.is_file():
        _ok(
            "el tool registro el proyecto en el registro temporal",
            str(registro_temporal),
        )
    else:
        _fallo(
            "el tool no registro el proyecto en el registro temporal",
            "esperado: {}".format(registro_temporal),
        )
        valido = False

    if _borrar_temporal(temporal):
        _ok("el proyecto temporal de la prueba se limpio")
    else:
        _fallo("no se pudo limpiar el proyecto temporal", str(temporal))
        valido = False

    if registro_real is None:
        _fallo("no se pudo leer el registro real de proyectos", error_registro)
        valido = False
    else:
        try:
            despues = fabrica.cargar_registro()
        except Exception as exc:  # noqa: BLE001 - la verificacion informa del fallo
            despues = None
            error_registro = "{}: {}".format(type(exc).__name__, exc)
        if despues is None:
            _fallo("no se pudo releer el registro real de proyectos", error_registro)
            valido = False
        elif despues == registro_real:
            _ok(
                "el paso no escribio en el registro que tenia al empezar",
                str(fabrica.ruta_registro()),
            )
        else:
            _fallo(
                "el paso escribio en el registro que tenia al empezar",
                "revisa {}".format(fabrica.ruta_registro()),
            )
            valido = False
    return valido


def _estado_del_loop(texto: str) -> str:
    for linea in (texto or "").splitlines():
        if "estado del loop" in linea:
            return linea.strip()
    return "(sin estado)"


def _limpiar(ruta: Path) -> None:
    try:
        ruta.unlink(missing_ok=True)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Paso 7: el registro real de proyectos sigue intacto
# --------------------------------------------------------------------------
def _huella(ruta: Path) -> str:
    """SHA-256 del registro (o ``"sin registro"`` si todavia no existe)."""
    try:
        contenido = ruta.read_bytes()
    except FileNotFoundError:
        return "sin registro"
    except OSError as exc:
        raise RuntimeError("no se pudo leer {}: {}".format(ruta, exc))
    return hashlib.sha256(contenido).hexdigest()


def vigilar_registro_real():
    """Foto del registro REAL, tomada ANTES de que el cinturon toque el entorno.

    Hay que leerla mientras el entorno es el de verdad: en cuanto el cinturon
    entra en accion, ``fabrica.ruta_registro()`` devuelve el temporal y el
    registro real deja de ser visible para el script.

    Returns:
        ``(ruta, huella, error)``. La ruta es ``None`` si no se pudo resolver.
    """
    try:
        import fabrica

        ruta = Path(fabrica.ruta_registro())
    except Exception as exc:  # noqa: BLE001 - la verificacion informa del fallo
        return None, "", "{}: {}".format(type(exc).__name__, exc)
    try:
        return ruta, _huella(ruta), ""
    except RuntimeError as exc:
        return ruta, "", str(exc)


def paso_registro_real(ruta, huella: str, error: str) -> bool:
    """Paso 7: el registro real no ha cambiado ni un byte durante la verificacion.

    Cierra el circulo del cinturon: los pasos 1-6 corren con el registro
    temporal, asi que si el real acaba con la misma huella, esta verificacion no
    le ha tocado.
    """
    _paso(7, "El registro real de proyectos no se ha tocado")
    if ruta is None:
        _fallo("no se pudo localizar el registro real de proyectos", error)
        return False
    print("  registro vigilado: {}".format(ruta))
    print("  huella antes     : {}".format(huella))
    if not huella:
        _fallo("no se pudo leer el registro real antes de empezar", error)
        return False
    try:
        despues = _huella(ruta)
    except RuntimeError as exc:
        _fallo("no se pudo releer el registro real de proyectos", str(exc))
        return False
    if despues == huella:
        _ok("misma huella SHA-256 antes y despues de la verificacion", despues)
        return True
    _fallo(
        "la verificacion escribio en el registro real de proyectos",
        "antes {} | despues {}".format(huella, despues),
    )
    return False


# --------------------------------------------------------------------------
# Principal
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    analizador = argparse.ArgumentParser(
        prog="verificar_servidor", description="Verifica la instalacion del Arquitecto Externo."
    )
    analizador.add_argument(
        "--real", action="store_true", help="usa el proveedor real del .env (consume tokens)"
    )
    argumentos = analizador.parse_args(argv)

    os.environ.setdefault("ARQUITECTO_LOG", "WARNING")
    if not argumentos.real:
        os.environ["ARQUITECTO_MOCK"] = "1"
    os.environ["ARQUITECTO_PERSISTIR"] = "0"

    # La foto del registro REAL se toma antes de aislar nada: en cuanto el
    # cinturon entra en accion, el script solo ve su propio temporal.
    ruta_registro, huella_registro, error_registro = vigilar_registro_real()
    entorno_inicial = {clave: os.environ.get(clave) for clave in ENTORNO_ISLAMIENTO}

    print("=" * 70)
    print(" VERIFICACION DEL ARQUITECTO EXTERNO ".center(70, "="))
    print("=" * 70)
    print("modo: {}".format("REAL (consume tokens)" if argumentos.real else "SIMULADO (sin red)"))
    print("registro real: {}".format(ruta_registro or "(sin localizar)"))

    try:
        with entorno_aislado():
            if any(
                os.environ.get(clave) != entorno_inicial[clave] for clave in ENTORNO_ISLAMIENTO
            ):
                print("aislamiento: el script usa su propio temporal (los de verdad no se tocan)")
                print("  registro : {}".format(os.environ["ARQUITECTO_REGISTRO"]))
                print("  proyectos: {}".format(os.environ["ARQUITECTO_CARPETA_PROYECTOS"]))

            paso_dependencias()
            paso_modulos()
            servidor = paso_servidor()
            paso_global()
            paso_invocacion(servidor)
            paso_dependencias_mcp(servidor)
            paso_registro_real(ruta_registro, huella_registro, error_registro)
    except OSError as exc:
        # Sin temporal no hay cinturon: mejor avisar que seguir escribiendo
        # donde no se debe.
        _fallo(
            "no se pudo aislar el registro de proyectos del script",
            "{}: {}".format(type(exc).__name__, exc),
        )

    print("")
    print("=" * 70)
    fallos = _resultados.count(False)
    print(
        " RESUMEN: {} comprobaciones OK, {} FALLOS ".format(
            _resultados.count(True), fallos
        ).center(70, "=")
    )
    print("=" * 70)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
