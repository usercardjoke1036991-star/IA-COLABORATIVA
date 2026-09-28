"""Verificacion end-to-end de la fabrica de proyectos.

Comprueba, contra el disco de verdad y en una carpeta temporal (nada se crea en
tu carpeta ``proyectos/``), que toda la maquinaria nueva funciona:

1. Seguridad de rutas: normalizacion de nombres, sandbox, binarios bloqueados.
2. Plantillas: catalogo, combinacion, requirements fusionado y contenido limpio
   (sin dobles barras ni caracteres de control en los .ps1 generados).
3. Herramientas de archivos: crear, leer, buscar, mover, borrar y protecciones.
4. Fabrica: crear proyecto, git init + commit, registro y arbol del proyecto.
5. Rol PROGRAMADOR: parser del formato '### ARCHIVO:' y aplicacion al proyecto.

Uso:
    venv\\\\Scripts\\\\python.exe scripts\\\\verificar_fabrica.py
    venv\\\\Scripts\\\\python.exe scripts\\\\verificar_fabrica.py --venv      (crea el venv real)
    venv\\\\Scripts\\\\python.exe scripts\\\\verificar_fabrica.py --real      (usa el modelo real)
    venv\\\\Scripts\\\\python.exe scripts\\\\verificar_fabrica.py --conservar (no borra el temporal)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
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
def paso_fabrica(fabrica, nombre: str, con_venv: bool) -> None:
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
        paso_fabrica(fabrica, nombre, opciones.venv)
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
    else:
        shutil.rmtree(temporal, ignore_errors=True)
        print("Carpeta temporal eliminada (el registro real no se toco).")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
