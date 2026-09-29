r"""Verificacion end-to-end de la fabrica de proyectos.

Comprueba, contra el disco de verdad y en una carpeta temporal (nada se crea en
tu carpeta ``proyectos/``), que toda la maquinaria nueva funciona:

1. Seguridad de rutas: normalizacion de nombres, sandbox, binarios bloqueados.
2. Plantillas: catalogo, combinacion, requirements fusionado y contenido limpio
   (sin dobles barras ni caracteres de control en los .ps1 generados).
3. Herramientas de archivos: crear, leer, buscar, mover, borrar y protecciones.
4. Fabrica: crear proyecto, git init + commit, registro y arbol del proyecto,
   incluido el flujo de dependencias: sin manifiesto, fallo real de ``pip``
   (indice muerto), timeout real y, con ``--pip``, instalacion de verdad desde
   PyPI; siempre con el proyecto intacto.
5. Rol PROGRAMADOR: parser del formato '### ARCHIVO:' y aplicacion al proyecto.

Uso:
    venv\Scripts\python.exe scripts\verificar_fabrica.py
    venv\Scripts\python.exe scripts\verificar_fabrica.py --venv      (crea el venv real)
    venv\Scripts\python.exe scripts\verificar_fabrica.py --pip       (instala de verdad desde PyPI)
    venv\Scripts\python.exe scripts\verificar_fabrica.py --real      (usa el modelo real)
    venv\Scripts\python.exe scripts\verificar_fabrica.py --conservar (no borra el temporal)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

ANCHO = 70
_resultados = []


def _ok(titulo: str, detalle: str = "") -> None:
    _resultados.append(True)
    print("  [OK]    {}{}".format(titulo, " -> " + detalle if detalle else ""))


def _fallo(titulo: str, detalle: str = "") -> None:
    _resultados.append(False)
    print("  [FALLO] {}{}".format(titulo, " -> " + detalle if detalle else ""))


def _comprobar(condicion: bool, titulo: str, detalle: str = "") -> bool:
    (_ok if condicion else _fallo)(titulo, detalle)
    return bool(condicion)


def _paso(numero: int, titulo: str) -> None:
    print("")
    print("-" * ANCHO)
    print("PASO {}: {}".format(numero, titulo))


def _borrar_temporal(ruta: Path, intentos: int = 3) -> bool:
    """Borra la carpeta temporal de verdad y dice si lo consiguio.

    ``shutil.rmtree(ignore_errors=True)`` se calla en Windows cuando el arbol
    trae objetos de git de solo lectura (``.git/objects``) o un fichero
    bloqueado por un proceso recien terminado (el ``venv`` que acaba de crear
    ``--venv``, el antivirus...): el borrado fallaba y el resumen seguia
    diciendo que la carpeta estaba eliminada. Aqui se quita el solo-lectura, se
    reintenta con una espera corta y se devuelve el resultado real, para poder
    avisar en vez de mentir.
    """
    for espera in (0.0, 0.3, 0.9, 1.5)[:intentos]:
        if espera:
            time.sleep(espera)
        for entrada in (ruta, *ruta.rglob("*")):
            try:
                modo = stat.S_IWRITE
                if entrada.is_dir():
                    # En POSIX un directorio con solo permiso de escritura no se
                    # puede recorrer ni borrar (``rmtree`` lo deja atras): hacen
                    # falta tambien lectura y busqueda. En Windows chmod solo usa
                    # el bit de solo lectura, asi que estos bits no molestan.
                    modo |= stat.S_IREAD | stat.S_IEXEC
                os.chmod(entrada, modo)
            except OSError:  # pragma: no cover - entrada ya borrada o sin permisos
                pass
        shutil.rmtree(ruta, ignore_errors=True)
        if not ruta.exists():
            return True
    return False


# --------------------------------------------------------------------------
# Interprete del venv en scripts de shell: siempre entre comillas
# --------------------------------------------------------------------------
#: Cualquier forma de nombrar el interprete de un venv (posix o Windows).
_INTERPRETE_SH = re.compile(
    r"(?:\$\{?RAIZ\}?/|\./)?venv/(?:bin|Scripts)/pythonw?(?:[0-9]+\.[0-9]+)?(?:\.exe)?"
)

#: Ordenes que solo imprimen texto: lo que va dentro no se ejecuta.
_SOLO_IMPRIME = ("echo", "printf")


def _lineas_sin_comillas(texto: str) -> list:
    """Lineas que invocan el interprete del venv sin comillas alrededor.

    ``venv/bin/python`` sin comillas se parte en dos argumentos en cuanto la
    carpeta del proyecto lleva un espacio (aqui: ``IA COLABORATIVA``) y el script
    muere con "No such file or directory". Las lineas de ``echo``/``printf`` se
    ignoran a proposito: solo imprimen la recomendacion, no ejecutan nada.
    """
    sospechosas: list = []
    for numero, linea in enumerate(texto.splitlines(), 1):
        limpia = linea.split(" #", 1)[0].strip()
        if not limpia or limpia.startswith("#"):
            continue
        if limpia.split()[0].lower() in _SOLO_IMPRIME:
            continue
        for hallazgo in _INTERPRETE_SH.finditer(limpia):
            antes = limpia[hallazgo.start() - 1] if hallazgo.start() else ""
            despues = limpia[hallazgo.end()] if hallazgo.end() < len(limpia) else ""
            if antes and antes in "\"'" and despues and despues in "\"'":
                continue
            sospechosas.append("linea {}: {}".format(numero, limpia))
    return sospechosas


def _textos_sh(rutas, generados=None) -> dict:
    """Junta ``nombre -> texto`` de los .sh de disco y de los generados.

    Los generados llegan como ``nombre -> contenido`` (todavia no existen en
    disco), asi que se revisan igual que los del repositorio.
    """
    textos: dict = {}
    for ruta in rutas:
        try:
            textos[str(ruta)] = Path(ruta).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
    for nombre, contenido in (generados or {}).items():
        if str(nombre).endswith(".sh"):
            textos[str(nombre)] = contenido
    return textos


def _revisar_scripts_sh(textos: dict) -> tuple:
    """Revisa los textos de shell: devuelve ``(fallos, revisados)``."""
    fallos: list = []
    for nombre, contenido in textos.items():
        for problema in _lineas_sin_comillas(contenido):
            fallos.append("{} -> {}".format(nombre, problema))
    return fallos, len(textos)


# --------------------------------------------------------------------------
# Paso 1: seguridad de rutas
# --------------------------------------------------------------------------
def paso_rutas(rutas, fabrica) -> None:
    _paso(1, "Seguridad de rutas (sandbox)")
    casos = {
        "Bot de Arbitraje!": "bot-de-arbitraje",
        "  Mi_Proyecto  2026 ": "mi-proyecto-2026",
        "CON": "con-app",
        "a/b/../c": "a-b-c",
    }
    for entrada, esperado in casos.items():
        obtenido = rutas.normalizar_nombre(entrada)
        _comprobar(
            obtenido == esperado,
            "normalizar_nombre({!r})".format(entrada),
            "{} (esperado {})".format(obtenido, esperado),
        )

    for entrada in ("", "   ", "..", "."):
        try:
            rutas.normalizar_nombre(entrada)
            _fallo("nombre invalido {!r} deberia fallar".format(entrada))
        except rutas.ErrorRuta:
            _ok("nombre invalido {!r} rechazado".format(entrada))

    try:
        rutas.resolver("../../../evil.py", base=rutas.raiz_fabrica())
        _fallo("ruta fuera de la raiz permitida", "no se bloqueo")
    except rutas.ErrorRuta:
        _ok("ruta fuera de la raiz bloqueada")

    try:
        rutas.resolver("payload.exe", base=rutas.raiz_fabrica())
        _fallo("extension .exe", "no se bloqueo")
    except rutas.ErrorRuta:
        _ok("extension .exe bloqueada")
    print("  raices permitidas: {}".format(", ".join(str(r) for r in rutas.raices_permitidas())))
    print("  version de git   : {}".format(fabrica.git_disponible() or "no instalado"))
    print("  gh disponible    : {}".format(fabrica.hay_gh()))


# --------------------------------------------------------------------------
# Paso 2: plantillas
# --------------------------------------------------------------------------
def paso_plantillas(plantillas) -> None:
    _paso(2, "Catalogo de plantillas")
    disponibles = plantillas.disponibles()
    print("  plantillas: {}".format(", ".join(disponibles)))
    _comprobar(
        {"vacio", "python", "flask", "fastapi", "web3", "playwright", "mcp"}.issubset(set(disponibles)),
        "estan registradas las 7 plantillas esperadas",
        "{} encontradas".format(len(disponibles)),
    )
    _comprobar("Plantillas disponibles" in plantillas.describir(), "describir() produce la tabla")

    andamiaje = plantillas.construir("python,web3,fastapi", "Mi Bot Arbitraje", "Bot de prueba")
    _comprobar(andamiaje.paquete == "mi_bot_arbitraje", "nombre de paquete", andamiaje.paquete)
    _comprobar(not andamiaje.avisos, "sin avisos con plantillas validas")
    _comprobar(
        "requirements.txt" in andamiaje.archivos,
        "requirements.txt fusionado",
        "{} dependencias".format(len(andamiaje.archivos.get("requirements.txt", "").splitlines())),
    )

    lineas = [
        linea.lower()
        for linea in andamiaje.archivos["requirements.txt"].splitlines()
        if linea.strip()
    ]
    _comprobar(len(lineas) == len(set(lineas)), "sin dependencias duplicadas")

    malo = plantillas.construir("python,inexistente", "x", "y")
    _comprobar(bool(malo.avisos) and "inexistente" in malo.avisos[0], "avisa de plantilla desconocida")

    # Contenido limpio: ni barras dobles ni caracteres de control en lo generado.
    sucios = []
    for ruta, contenido in andamiaje.archivos.items():
        if "\\\\" in contenido:
            sucios.append("{}: barras dobles".format(ruta))
        for caracter in ("\x0b", "\x0c", "\r"):
            if caracter in contenido:
                sucios.append("{}: caracter de control".format(ruta))
    _comprobar(not sucios, "contenido generado sin barras dobles ni controles", "; ".join(sucios))

    scripts = [r for r in andamiaje.archivos if r.endswith(".ps1")]
    if scripts:
        correctos = all(
            'venv\\Scripts\\python.exe' in andamiaje.archivos[r] or "venv" not in andamiaje.archivos[r]
            for r in scripts
        )
        _comprobar(correctos, "rutas del venv correctas en los .ps1", ", ".join(scripts))

    # Scripts de shell: el interprete del venv SIEMPRE entre comillas. Sin ellas
    # el shell parte la orden en el primer espacio de la ruta del proyecto (esta
    # carpeta se llama "IA COLABORATIVA") y el script no arranca. Se revisan los
    # .sh del repositorio y los que genere la fabrica (hoy: ninguno, pero el
    # guardian queda puesto para el dia que existan).
    propios = sorted(RAIZ.glob("*.sh")) + sorted((RAIZ / "scripts").glob("*.sh"))
    fallos_sh, revisados_sh = _revisar_scripts_sh(_textos_sh(propios, andamiaje.archivos))
    _comprobar(
        not fallos_sh,
        "interprete del venv entrecomillado en los scripts de shell",
        "{} script(s) revisados{}".format(
            revisados_sh, " // " + " // ".join(fallos_sh) if fallos_sh else ""
        ),
    )


# --------------------------------------------------------------------------
# Paso 3: herramientas de archivos
# --------------------------------------------------------------------------
def paso_archivos(archivos, rutas, nombre: str) -> None:
    _paso(3, "Herramientas de archivos")

    print("  " + archivos.escribir_archivo(nombre, "src/saludo.py", "def hola() -> str:\n    return 'hola'\n"))
    print("  " + archivos.escribir_archivo(nombre, "docs/notas.md", "# Notas\n\n- una\n"))
    print("  " + archivos.crear_carpeta(nombre, "pruebas"))

    leido = archivos.leer_archivo(nombre, "src/saludo.py")
    _comprobar("return 'hola'" in leido, "leer_archivo devuelve el contenido")

    encontrado = archivos.buscar_en_contenido(nombre, "hola")
    _comprobar("src/saludo.py:2" in encontrado, "buscar_en_contenido localiza la linea")

    hallados = archivos.buscar_archivos(nombre, "*.md")
    _comprobar("docs/notas.md" in hallados, "buscar_archivos por patron glob")

    print("  " + archivos.info_archivo(nombre, "src/saludo.py"))
    print("  " + archivos.mover(nombre, "docs/notas.md", "docs/notas-v2.md"))
    _comprobar(
        "notas-v2" in archivos.listar_proyecto(nombre, profundidad=2),
        "mover renombra y listar_proyecto refleja el cambio",
    )

    try:
        archivos.escribir_archivo(nombre, ".git/config", "x")
        _fallo("escritura en .git", "no se bloqueo")
    except archivos.ErrorArchivo:
        _ok("escritura en .git bloqueada")

    try:
        archivos.escribir_archivo(nombre, "..", "x")
        _fallo("ruta con '..'", "no se bloqueo")
    except (archivos.ErrorArchivo, rutas.ErrorRuta):
        _ok("ruta con '..' bloqueada")

    # Path traversal de verdad: el proyecto vecino y la raiz comun de la fabrica
    # estan dentro de las raices permitidas, asi que el sandbox global no basta.
    vecino = rutas.raiz_fabrica() / "vecino-secreto"
    vecino.mkdir(parents=True, exist_ok=True)
    secreto = vecino / "secreto.txt"
    secreto.write_text("no me toques\n", encoding="utf-8")

    colados = []
    for ataque in ("..", "./sub/..", "../vecino-secreto", "../vecino-secreto/secreto.txt"):
        try:
            archivos.leer_archivo(nombre, ataque)
            colados.append("leer " + ataque)
        except (archivos.ErrorArchivo, rutas.ErrorRuta):
            pass
        try:
            archivos.crear_carpeta(nombre, "{}/nueva".format(ataque))
            colados.append("crear " + ataque)
        except (archivos.ErrorArchivo, rutas.ErrorRuta):
            pass
    _comprobar(
        not colados,
        "path traversal bloqueado en las herramientas (confinar_a_base)",
        "; ".join(colados),
    )

    # Vectores de ruta absoluta, de dispositivo y de recurso de red: no son
    # "relativas al proyecto" ni con el permiso de escritura externa activo. Las
    # absolutas se construyen con el temporal del sistema: una ruta literal de un
    # directorio publicamente escribible (/tmp, /var/tmp...) es una vulnerabilidad
    # real (python:S5443) y aqui no hace falta para nada.
    if os.name == "nt":
        absolutos = (
            "C:\\Windows\\win.ini",
            "\\\\?\\C:\\Windows\\win.ini",
            "\\\\localhost\\c$\\secreto.txt",
        )
    else:
        base_temporal = Path(tempfile.gettempdir())
        absolutos = (
            str(base_temporal / "secreto.txt"),
            str(base_temporal / "otro" / "secreto.txt"),
        )
    con_absolutas = []
    for ataque in absolutos:
        try:
            archivos.leer_archivo(nombre, ataque)
            con_absolutas.append("leer " + ataque)
        except (archivos.ErrorArchivo, rutas.ErrorRuta):
            pass
        try:
            archivos.crear_carpeta(nombre, "{}/nueva".format(ataque))
            con_absolutas.append("crear " + ataque)
        except (archivos.ErrorArchivo, rutas.ErrorRuta):
            pass
    _comprobar(
        not con_absolutas,
        "rutas absolutas, de dispositivo y de red bloqueadas",
        "; ".join(con_absolutas),
    )

    try:
        archivos.borrar(nombre, "..", recursivo=True)
        _fallo("borrado de '..'", "no se bloqueo")
    except (archivos.ErrorArchivo, rutas.ErrorRuta):
        _ok("borrado de '..' bloqueado")
    _comprobar(secreto.exists(), "el proyecto vecino sigue intacto tras el intento")

    try:
        archivos.escribir_archivo(nombre, "../vecino-secreto/colado.txt", "x")
        _fallo("escritura en el proyecto vecino", "no se bloqueo")
    except (archivos.ErrorArchivo, rutas.ErrorRuta):
        _ok("escritura en el proyecto vecino bloqueada")
    _comprobar(
        not (vecino / "colado.txt").exists(),
        "el intento rechazado no dejo rastro en el vecino",
    )

    try:
        archivos.borrar(nombre, "docs", recursivo=False)
        _fallo("borrado de carpeta sin recursivo", "no se bloqueo")
    except archivos.ErrorArchivo:
        _ok("borrado de carpeta sin recursivo bloqueado")

    try:
        archivos.borrar(nombre, ".", recursivo=True)
        _fallo("borrado de la raiz", "no se bloqueo")
    except archivos.ErrorArchivo:
        _ok("borrado de la raiz bloqueado")

    try:
        archivos.leer_archivo(nombre, "no/existe.py")
        _fallo("lectura inexistente", "no fallo")
    except archivos.ErrorArchivo:
        _ok("lectura inexistente falla con pista")

    print("  " + archivos.borrar(nombre, "docs/notas-v2.md"))
    _comprobar("notas-v2" not in archivos.listar_proyecto(nombre, profundidad=2), "borrar elimina el archivo")


# --------------------------------------------------------------------------
# Paso 4: fabrica de proyectos
# --------------------------------------------------------------------------
def paso_fabrica(
    fabrica, archivos, procesos, nombre: str, con_venv: bool, con_pip: bool = False
) -> None:
    _paso(4, "Fabrica: crear proyecto, git y registro")

    informe = fabrica.crear_proyecto(
        nombre,
        "Proyecto de verificacion de la fabrica",
        ["python", "playwright"],
        con_git=True,
        publicar=False,
    )
    print(informe)
    ficha = fabrica.ficha_proyecto(nombre)
    _comprobar(Path(ficha.ruta).exists(), "la carpeta del proyecto existe", ficha.ruta)
    _comprobar("python" in ficha.plantillas and "playwright" in ficha.plantillas, "plantillas registradas")
    _comprobar(bool(ficha.commit), "primer commit creado", ficha.commit)

    registro = fabrica.cargar_registro()
    _comprobar(nombre in registro, "el proyecto queda en datos/proyectos.json")

    if fabrica.hay_git():
        _comprobar((Path(ficha.ruta) / ".git").exists(), "repositorio git inicializado")
        estado = fabrica.estado_git(nombre)
        _comprobar("## main" in estado, "estado_git muestra la rama main")
        _comprobar("fabrica" in fabrica.hacer_commit(nombre, "test: commit de la verificacion").lower(),
                   "hacer_commit guarda cambios")
    else:
        print("  nota: git no esta instalado, se omite la parte de repositorio")

    duplicado = False
    try:
        fabrica.crear_proyecto(nombre, "otra vez", ["python"])
    except fabrica.ErrorFabrica:
        duplicado = True
    _comprobar(duplicado, "no se puede recrear un proyecto con contenido")

    arbol = fabrica.informe_proyecto(nombre, profundidad=1)
    _comprobar("Ficha:" in arbol and "README.md" in arbol, "informe_proyecto resume ficha y archivos")

    comprobar_publicacion(fabrica, nombre)
    comprobar_dependencias(fabrica, nombre)
    comprobar_dependencias_reales(fabrica, archivos, procesos, nombre, con_pip)

    if con_venv:
        print(preparar_entorno(fabrica, nombre))
    else:
        print("  nota: usa --venv para crear el entorno virtual real (tarda un poco)")


def comprobar_publicacion(fabrica, nombre: str) -> None:
    """Comprueba las tres respuestas correctas de ``publicar_en_github``.

    1. Sin ``gh``: la fabrica explica como instalarlo y autenticarse.
    2. ``gh`` instalado pero sin sesion: es el estado normal de un runner de CI,
       y la fabrica debe pedir ``gh auth login`` en vez de reventar.
    3. ``gh`` con sesion: devuelve la URL del repositorio creado.
    """
    hay_gh = fabrica.hay_gh()
    if hay_gh:
        print("  nota: hay gh instalado; si tiene sesion, esta comprobacion crea de")
        print("        verdad el repositorio remoto del proyecto temporal de prueba.")
    try:
        publicar = fabrica.publicar_en_github(nombre)
    except fabrica.ErrorFabrica as exc:
        mensaje = str(exc)
        bajo = mensaje.lower()
        if not hay_gh:
            _comprobar(
                "gh" in bajo and "auth login" in bajo,
                "sin gh informa de como instalarlo y autenticarse",
            )
        elif "sin sesion" in bajo:
            _comprobar(
                "gh auth login" in bajo,
                "gh sin sesion pide 'gh auth login' en vez de reventar",
                mensaje[:120],
            )
        else:
            _fallo("publicacion en GitHub", mensaje[:160])
            return
        print(
            "  mensaje de la fabrica sobre gh:\n{}".format(
                "\n".join("    " + linea for linea in mensaje.splitlines()[:4])
            )
        )
        return

    if not hay_gh:
        _fallo("sin gh la publicacion deberia fallar", publicar[:80])
        return
    _comprobar("github.com" in publicar, "publicacion en GitHub", publicar[:120])


def comprobar_dependencias(fabrica, nombre: str) -> None:
    """Comprueba que las librerias caen dentro del proyecto, sin usar la red.

    Se crea un segundo proyecto con una plantilla sin ``requirements.txt`` y
    ``instalar_dependencias=True``: eso fuerza el ``venv/`` del propio proyecto
    (aunque ``ARQUITECTO_CREAR_VENV`` este en ``false``) y no llega a ejecutar
    ``pip`` porque no hay manifiesto. Lo que se verifica es la decision de
    diseno: la instalacion nunca aborta la creacion y el venv vive en el
    proyecto, no en el Python global.
    """
    _comprobar(
        hasattr(fabrica.configuracion.cargar_fabrica(), "instalar_dependencias"),
        "la config de la fabrica expone instalar_dependencias",
    )
    _comprobar(
        "instalar=" in fabrica.configuracion.cargar_fabrica().resumen(),
        "el resumen de la fabrica muestra el flag de instalacion",
    )

    sin_deps = "{}-sin-deps".format(nombre)
    informe = fabrica.crear_proyecto(
        sin_deps,
        "proyecto sin manifiesto, para verificar el estado pendiente",
        ["vacio"],
        con_git=False,
        publicar=False,
        instalar_dependencias=True,
    )
    print(informe)
    raiz = Path(fabrica.ficha_proyecto(sin_deps).ruta)
    _comprobar(
        "estado_dependencias=pendiente_sin_requirements" in informe,
        "sin manifiesto avisa con estado pendiente en vez de fallar",
    )
    _comprobar(raiz.is_dir(), "el proyecto existe pese al estado pendiente", str(raiz))
    _comprobar(
        (raiz / "venv").is_dir(),
        "pedir dependencias fuerza el venv/ dentro del proyecto",
        str(fabrica.interprete_venv(raiz)),
    )
    _comprobar(
        str(fabrica.interprete_venv(raiz)).startswith(str(raiz)),
        "el interprete que se usaria vive dentro del proyecto (nunca el global)",
        str(fabrica.interprete_venv(raiz)),
    )
    # Sin manifiesto no hay nada que instalar: ni comando ni diagnostico de pip.
    _comprobar(
        "pip install" not in informe and "Comando exacto" not in informe,
        "sin manifiesto no se llama a pip ni se ofrece un comando",
    )
    # La regla de orquestacion (criterio "un solo camino") es comprobable por lectura.
    reglas = RAIZ / ".clinerules"
    if reglas.is_file():
        texto_reglas = reglas.read_text(encoding="utf-8", errors="replace").lower()
        _comprobar(
            "un solo camino" in texto_reglas and "no uses los dos" in texto_reglas,
            "la regla de orquestacion prohibe instalar por los dos caminos a la vez",
        )
    else:
        print("  nota: no hay .clinerules en la raiz, se omite la regla de orquestacion")


# --------------------------------------------------------------------------
# Dependencias con pip REAL (rutas de fallo)
# --------------------------------------------------------------------------
#: Entorno para forzar un fallo inmediato y determinista de ``pip``: se le da un
#: indice en un puerto cerrado de la propia maquina (sin tocar red externa), sin
#: reintentos y sin cache, y se neutraliza cualquier proxy del sistema.
ENTORNO_INDICE_MUERTO = {
    "PIP_INDEX_URL": "http://127.0.0.1:1/simple",
    "PIP_RETRIES": "0",
    "PIP_TIMEOUT": "2",
    "PIP_NO_CACHE_DIR": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "NO_PROXY": "127.0.0.1,localhost",
    "no_proxy": "127.0.0.1,localhost",
    "HTTP_PROXY": "",
    "HTTPS_PROXY": "",
    "http_proxy": "",
    "https_proxy": "",
}

#: Paquete que no existe en ningun indice: prueba el error real de ``pip``.
PAQUETE_INEXISTENTE = "paquete-que-no-existe-xyzzy"

#: Paquete real, minusculo y sin compilacion: prueba el exito real de ``pip``.
PAQUETE_REAL = "six==1.16.0"
PAQUETE_REAL_NOMBRE = "six"


def _activar_entorno(extra: dict) -> dict:
    """Pisa variables del proceso (pip las hereda) y devuelve las anteriores."""
    anteriores = {clave: os.environ.get(clave) for clave in extra}
    os.environ.update(extra)
    return anteriores


def _restaurar_entorno(anteriores: dict) -> None:
    """Deja ``os.environ`` como estaba antes de :func:`_activar_entorno`."""
    for clave, valor in anteriores.items():
        if valor is None:
            os.environ.pop(clave, None)
        else:
            os.environ[clave] = valor


def _config_pip_vacia(carpeta: Path) -> str:
    """Devuelve un ``pip.ini`` vacio: aisla la prueba de la config global del usuario."""
    ini = carpeta / "pip.ini"
    if not ini.exists():
        ini.write_text("# vacio a proposito: aisla la prueba de la config global\n", encoding="utf-8")
    return str(ini)


def _paquetes_del_venv(procesos, fabrica, raiz: Path) -> list:
    """Paquetes instalados en el ``venv/`` del proyecto, leidos por su interprete.

    Se pregunta al interprete del propio proyecto (no al global) que liste sus
    ``*.dist-info``: asi se comprueba de verdad donde cayeron las librerias.
    """
    return _paquetes_del_interprete(procesos, fabrica.interprete_venv(raiz), raiz)


def _paquetes_del_interprete(procesos, interprete: Path, cwd: Path) -> list:
    """Paquetes instalados en el ``site-packages`` de un interprete concreto.

    Se pregunta al interprete (``-c``) por sus ``*.dist-info``: sirve tanto para
    ver donde cayeron las librerias del proyecto como para comprobar que **no**
    cayeron en el interprete que ejecuta la verificacion. Todo en una sola linea
    con ``;`` para que el guion no necesite saltos escapados.
    """
    guion = (
        "import pathlib, sysconfig; "
        "print(chr(10).join(sorted(p.name for p in "
        "pathlib.Path(sysconfig.get_paths()['purelib']).glob('*.dist-info'))))"
    )
    try:
        codigo, salida, _ = procesos.ejecutar([str(interprete), "-c", guion], cwd=cwd, timeout=120)
    except Exception:  # noqa: BLE001 - un fallo aqui no puede romper la verificacion
        return []
    if codigo != 0:
        return []
    return [linea.strip() for linea in salida.splitlines() if linea.strip()]


def _procesos_python_vivos(procesos) -> int:
    """Cuenta los ``python.exe`` vivos (Windows); ``-1`` si no se puede consultar."""
    if os.name != "nt":
        return -1
    try:
        codigo, salida, _ = procesos.ejecutar(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/NH"], cwd=RAIZ, timeout=120
        )
    except Exception:  # noqa: BLE001
        return -1
    if codigo != 0:
        return -1
    return salida.lower().count("python.exe")


class _ServidorMudo:
    """Escucha en un puerto local pero nunca responde: fuerza el timeout de pip.

    Es la unica forma de provocar un timeout de verdad sin salir a la red: pip
    conecta, espera la respuesta del indice y se queda colgado hasta que
    ``preparar_entorno`` corta por tiempo y mata el arbol de procesos.
    """

    def __init__(self) -> None:
        self._socket = socket.socket()
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(8)
        self.puerto = int(self._socket.getsockname()[1])
        self._conexiones = []
        self._hilo = threading.Thread(target=self._atender, daemon=True)
        self._hilo.start()

    @property
    def direccion(self) -> str:
        return "http://127.0.0.1:{}/simple".format(self.puerto)

    def _atender(self) -> None:
        while True:
            try:
                conexion, _ = self._socket.accept()
            except OSError:
                return
            self._conexiones.append(conexion)  # aceptada y muda a proposito

    def cerrar(self) -> None:
        try:
            self._socket.close()
        except OSError:
            pass
        for conexion in self._conexiones:
            try:
                conexion.close()
            except OSError:
                pass


def comprobar_dependencias_reales(
    fabrica, archivos, procesos, nombre: str, instalar_real: bool = False
) -> None:
    """Provoca fallos REALES de ``pip`` contra el ``venv/`` de un proyecto.

    Todo apunta a un puerto cerrado o a un servidor mudo de la propia maquina:
    no se sale a Internet. En cada ruta de fallo se verifica lo mismo: el
    proyecto y su ``venv/`` sobreviven, el estado queda en ``pendiente_*``, el
    comando exacto aparece en el informe y **no** queda instalado ningun paquete
    del manifiesto ni procesos de pip vivos.

    Con ``instalar_real`` (bandera ``--pip``) se anade el caso contrario: una
    instalacion de verdad desde PyPI, en la que la libreria tiene que quedar
    dentro del ``venv/`` del proyecto y no aparecer en ningun otro entorno.
    """
    raiz = Path(fabrica.ficha_proyecto(nombre).ruta)
    requirements = raiz / "requirements.txt"
    original = requirements.read_text(encoding="utf-8") if requirements.is_file() else ""
    paquetes_esperados = [
        linea.split("=")[0].split(">")[0].split("<")[0].strip().lower()
        for linea in original.splitlines()
        if linea.strip() and not linea.strip().startswith("#")
    ]
    if not paquetes_esperados:
        print("  nota: el manifiesto no declara paquetes, se comprueba solo el estado")

    config_pip = Path(tempfile.mkdtemp(prefix="pip-ini-"))
    entorno_muerto = dict(ENTORNO_INDICE_MUERTO, PIP_CONFIG_FILE=_config_pip_vacia(config_pip))
    try:
        print("  4a) pip real contra un indice imposible (puerto cerrado)")
        ficha = fabrica.ficha_proyecto(nombre)
        anteriores = _activar_entorno(entorno_muerto)
        try:
            primero = fabrica.preparar_entorno(nombre, instalar=True, timeout=60)
        finally:
            _restaurar_entorno(anteriores)
        print("\n".join("     " + linea for linea in primero.splitlines()[:14]))

        _comprobar(
            "estado=pendiente_error_red" in primero,
            "indice muerto: pip real queda como pendiente_error_red",
        )
        _comprobar("Comando exacto:" in primero, "indice muerto: el informe deja el comando exacto")
        _comprobar(
            "pip install" in primero and str(raiz) in primero,
            "indice muerto: el comando usa el interprete del propio proyecto",
        )
        _comprobar(
            "Salida de pip" in primero,
            "indice muerto: el error de pip viaja en el informe (no se pierde)",
        )
        _comprobar(
            "Reintenta con preparar_entorno" in primero,
            "indice muerto: el informe dice como reintentar",
        )
        _comprobar(
            raiz.is_dir() and (raiz / "venv").is_dir() and (raiz / "README.md").is_file(),
            "indice muerto: el proyecto y su venv siguen intactos",
        )
        _comprobar(
            str(ficha.ruta) == str(raiz) and ficha.estado.startswith("creado"),
            "indice muerto: la ficha del proyecto no se degrada",
            ficha.estado,
        )
        instalados = _paquetes_del_venv(procesos, fabrica, raiz)
        _comprobar(
            bool(instalados) and not any(
                instalado.lower().startswith(paquete.replace("_", "-"))
                for paquete in paquetes_esperados
                for instalado in instalados
            ),
            "indice muerto: ningun paquete del manifiesto acabo instalado",
            "site-packages: {}".format(", ".join(instalados) or "(vacio)"),
        )

        print("  4b) pip real, paquete inexistente en el indice")
        archivos.escribir_archivo(nombre, "requirements.txt", "{}==9.9.9\n".format(PAQUETE_INEXISTENTE))
        anteriores = _activar_entorno(entorno_muerto)
        try:
            segundo = fabrica.preparar_entorno(nombre, instalar=True, timeout=60)
        finally:
            _restaurar_entorno(anteriores)
            if original.strip():
                archivos.escribir_archivo(nombre, "requirements.txt", original)
        print("\n".join("     " + linea for linea in segundo.splitlines()[:14]))

        _comprobar(
            "estado=pendiente_error_red" in segundo,
            "paquete inexistente: queda como pendiente_error_red",
        )
        _comprobar(
            "Salida de pip" in segundo and PAQUETE_INEXISTENTE in segundo,
            "paquete inexistente: el informe nombra el paquete que no se encontro",
        )
        _comprobar("estado=ok" not in segundo, "paquete inexistente: no se informa de exito")
        instalados = _paquetes_del_venv(procesos, fabrica, raiz)
        _comprobar(
            not any(PAQUETE_INEXISTENTE.replace("-", "_") in instalado for instalado in instalados),
            "paquete inexistente: no se instalo nada parecido",
            "site-packages: {}".format(", ".join(instalados) or "(vacio)"),
        )

        print("  4c) pip real, servidor que acepta y nunca responde (timeout)")
        servidor = _ServidorMudo()
        antes = _procesos_python_vivos(procesos)
        entorno_timeout = dict(ENTORNO_INDICE_MUERTO)
        entorno_timeout.update(
            {
                "PIP_INDEX_URL": servidor.direccion,
                "PIP_TIMEOUT": "600",
                "PIP_CONFIG_FILE": _config_pip_vacia(config_pip),
            }
        )
        anteriores = _activar_entorno(entorno_timeout)
        try:
            inicio = time.time()
            tercero = fabrica.preparar_entorno(nombre, instalar=True, timeout=2)
            tardanza = time.time() - inicio
        finally:
            _restaurar_entorno(anteriores)
            servidor.cerrar()
        print("\n".join("     " + linea for linea in tercero.splitlines()[:14]))

        _comprobar(
            "estado=pendiente_timeout" in tercero,
            "timeout: pip real queda como pendiente_timeout",
        )
        _comprobar(
            "cancel" in tercero.lower(),
            "timeout: el informe explica que se corto a proposito",
        )
        _comprobar(
            tardanza < 30,
            "timeout: se corta de verdad y no espera a pip ({}s)".format(round(tardanza, 1)),
        )
        _comprobar(
            raiz.is_dir() and (raiz / "venv").is_dir() and (raiz / "requirements.txt").is_file(),
            "timeout: el proyecto, su venv y su manifiesto siguen ahi",
        )
        _comprobar(
            str(fabrica.interprete_venv(raiz)).startswith(str(raiz)),
            "timeout: el interprete sigue siendo el del proyecto",
        )
        if antes >= 0:
            time.sleep(2)  # margen para que el sistema refleje la muerte del arbol
            despues = _procesos_python_vivos(procesos)
            _comprobar(
                despues <= antes,
                "timeout: el corte no deja procesos python colgados ({} -> {})".format(antes, despues),
            )
        else:
            print("     nota: tasklist no disponible, no se cuentan procesos vivos")

        if not instalar_real:
            print("     nota: sin --pip no se sale a Internet (solo se prueban los fallos)")
        else:
            print("  4d) pip real contra PyPI: la libreria debe caer en el venv/ del proyecto")
            sitio_antes = _paquetes_del_interprete(procesos, Path(sys.executable), RAIZ)
            archivos.escribir_archivo(nombre, "requirements.txt", PAQUETE_REAL + chr(10))
            # Aqui SI se sale a Internet: solo se neutraliza la config global de pip
            # (indice corporativo del usuario) para que la prueba sea reproducible.
            entorno_pypi = {
                "PIP_CONFIG_FILE": _config_pip_vacia(config_pip),
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_TIMEOUT": "60",
            }
            anteriores = _activar_entorno(entorno_pypi)
            try:
                cuarto = fabrica.preparar_entorno(nombre, instalar=True, timeout=300)
            finally:
                _restaurar_entorno(anteriores)
                if original.strip():
                    archivos.escribir_archivo(nombre, "requirements.txt", original)
            print("\n".join("     " + linea for linea in cuarto.splitlines()[:14]))

            _comprobar(
                "Dependencias instaladas" in cuarto,
                "PyPI real: el informe confirma la instalacion",
            )
            _comprobar(
                "Comando exacto:" not in cuarto and "AVISO" not in cuarto,
                "PyPI real: con exito no hay comando de reintento",
            )
            instalados = _paquetes_del_venv(procesos, fabrica, raiz)
            _comprobar(
                any(
                    instalado.lower().startswith(PAQUETE_REAL_NOMBRE + "-")
                    for instalado in instalados
                ),
                "PyPI real: la libreria cae en el site-packages del proyecto",
                "site-packages: {}".format(", ".join(instalados) or "(vacio)"),
            )
            guion = "import pathlib, {0}; print(pathlib.Path({0}.__file__).resolve())".format(
                PAQUETE_REAL_NOMBRE
            )
            codigo, salida, error = procesos.ejecutar(
                [str(fabrica.interprete_venv(raiz)), "-c", guion], cwd=raiz, timeout=120
            )
            importado = salida.strip().splitlines()[-1] if codigo == 0 and salida.strip() else ""
            _comprobar(
                bool(importado) and importado.lower().startswith(str(raiz).lower()),
                "PyPI real: el interprete del proyecto importa la libreria desde su venv",
                importado or error.strip()[:200],
            )
            sitio_despues = _paquetes_del_interprete(procesos, Path(sys.executable), RAIZ)
            _comprobar(
                sitio_antes == sitio_despues,
                "PyPI real: nada queda instalado fuera del venv del proyecto",
                "site-packages del interprete de la verificacion: igual antes y despues",
            )
    finally:
        _borrar_temporal(config_pip)


def preparar_entorno(fabrica, nombre: str) -> str:
    """Crea el venv del proyecto sin instalar dependencias (rapido y sin red)."""
    try:
        return fabrica.preparar_entorno(nombre, instalar=False)
    except fabrica.ErrorFabrica as exc:
        return "aviso: no se pudo crear el venv ({})".format(exc)


# --------------------------------------------------------------------------
# Paso 5: rol PROGRAMADOR
# --------------------------------------------------------------------------
def paso_programador(protocolo, archivos, nombre: str, usar_real: bool) -> None:
    _paso(5, "Rol PROGRAMADOR (contrato de archivos)")
    texto = "\n".join(
        [
            "### ARCHIVO: src/saludo.py",
            "```python",
            "def hola() -> str:",
            '    return "hola"',
            "```",
            "",
            "### ARCHIVO: docs/entrega.md",
            "```markdown",
            "# Entrega",
            "```",
            "",
            "### PASOS",
            "1. venv/Scripts/python.exe -m pytest -q",
        ]
    )
    entregados = protocolo.extraer_archivos(texto)
    _comprobar(len(entregados) == 2, "el parser extrae los 2 archivos", str([r for r, _ in entregados]))
    _comprobar("pytest" in protocolo.pasos_sugeridos(texto), "el parser encuentra el bloque de pasos")
    _comprobar(protocolo.esta_listo(texto), "esta_listo() detecta la entrega")
    _comprobar(not protocolo.esta_listo("sin archivos"), "esta_listo() rechaza texto sin archivos")

    mensajes = archivos.escribir_varios(nombre, dict(entregados))
    _comprobar(
        all("saludo.py" in m or "entrega.md" in m for m in mensajes),
        "los archivos del programador se escriben en el proyecto",
    )
    _comprobar(
        "return \"hola\"" in archivos.leer_archivo(nombre, "src/saludo.py"),
        "el contenido aplicado es el correcto",
    )

    import ejecutor

    rol = ejecutor.Ejecutor()
    print("  {}".format(rol.config.resumen()))
    print("  {}".format("; ".join(rol.config.problemas()) or "sin problemas de configuracion"))
    if usar_real:
        print("  lanzando una peticion REAL al modelo del programador (consume tokens)...")
        respuesta = rol.implementar(
            "Devuelve un unico archivo 'saludo_final.py' con una funcion hola() que "
            "devuelva el texto hola.",
            plan="1. Un archivo, una funcion, con type hints.",
            proyecto=nombre,
        )
        _comprobar(respuesta.error is None, "respuesta del modelo real", respuesta.error or "ok")
        if not respuesta.error:
            print("  archivos entregados: {}".format([r for r, _ in rol.archivos_de(respuesta)]))
    else:
        respuesta = rol.implementar("Tarea de ejemplo para el modo simulado.")
        _comprobar(respuesta.error is None, "el rol PROGRAMADOR responde en modo simulado")
        print("  {}".format(rol.estado().splitlines()[3]))


# --------------------------------------------------------------------------
# Principal
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    analizador = argparse.ArgumentParser(
        prog="verificar_fabrica", description="Verifica la fabrica de proyectos end-to-end."
    )
    analizador.add_argument("--venv", action="store_true", help="crea el entorno virtual real")
    analizador.add_argument(
        "--pip", action="store_true", help="instala de verdad desde PyPI (necesita Internet)"
    )
    analizador.add_argument("--real", action="store_true", help="usa el modelo real (consume tokens)")
    analizador.add_argument("--conservar", action="store_true", help="no borra la carpeta temporal")
    opciones = analizador.parse_args(argv)

    # Se guarda ya canonico: asi los avisos y la comprobacion de raices hablan
    # del mismo texto aunque el sistema tenga dos nombres para el temporal.
    temporal = Path(tempfile.mkdtemp(prefix="verificacion-fabrica-")).resolve()
    os.environ["ARQUITECTO_CARPETA_PROYECTOS"] = str(temporal)
    os.environ["ARQUITECTO_LOG"] = "WARNING"
    os.environ["ARQUITECTO_PERSISTIR"] = "0"
    os.environ["ARQUITECTO_PERMITIR_EXTERNO"] = "0"
    if not opciones.real:
        os.environ["ARQUITECTO_MOCK"] = "1"

    import fabrica
    import herramientas_archivos as archivos
    import plantillas
    import procesos
    import protocolo
    import rutas

    # El registro real no se toca: durante la verificacion vive en el temporal.
    fabrica.RUTA_REGISTRO = temporal / "datos" / "proyectos.json"

    nombre = "verificacion-fabrica"
    print("=" * ANCHO)
    print(" VERIFICACION DE LA FABRICA DE PROYECTOS ".center(ANCHO, "="))
    print("=" * ANCHO)
    print("carpeta temporal: {}".format(temporal))
    print("modelo          : {}".format("REAL (consume tokens)" if opciones.real else "SIMULADO"))

    try:
        paso_rutas(rutas, fabrica)
        paso_plantillas(plantillas)
        paso_fabrica(fabrica, archivos, procesos, nombre, opciones.venv, opciones.pip)
        paso_archivos(archivos, rutas, nombre)
        paso_programador(protocolo, archivos, nombre, opciones.real)
    except Exception as exc:  # cualquier fallo inesperado cuenta como fallo
        _fallo("excepcion inesperada durante la verificacion", "{}: {}".format(type(exc).__name__, exc))

    print("")
    print("=" * ANCHO)
    fallos = _resultados.count(False)
    print(
        " RESUMEN: {} comprobaciones OK, {} FALLOS ".format(
            _resultados.count(True), fallos
        ).center(ANCHO, "=")
    )
    print("=" * ANCHO)

    if opciones.conservar:
        print("Se conserva la carpeta temporal: {}".format(temporal))
    elif _borrar_temporal(temporal):
        print("Carpeta temporal eliminada (el registro real no se toco).")
    else:
        # Diagnostico util: que sigue habiendo dentro (asi el proximo intento sabe
        # si es un objeto de .git de solo lectura, un fichero bloqueado...).
        restos = sorted(str(ruta) for ruta in temporal.rglob("*")) if temporal.exists() else []
        print("AVISO: no se pudo borrar la carpeta temporal: {}".format(temporal))
        print(
            "       sigue habiendo {} entradas, por ejemplo: {}".format(
                len(restos), ", ".join(restos[:3]) or "(nada)"
            )
        )
        print("       borrala a mano; el registro real no se toco igualmente.")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
