"""Politica de rutas de la fabrica: contenido existente = carpeta FICHADA.

Regla que fija esta suite (nacio de un defecto real, no de una hipotesis): cuando
una herramienta toca contenido que **ya existe**, la carpeta del proyecto se
pregunta a ``herramientas_archivos.base_de_proyecto()`` (la ruta de la ficha, que
puede ser cualquier carpeta activada), nunca a ``rutas.ruta_de_proyecto()`` (que
asume ``proyectos/<slug>``). Crear un proyecto nuevo por su slug si es legitimo, y
para eso esta la allowlist de abajo.

La comprobacion es estatica (AST) a proposito: no depende de tener un proyecto
registrado y falla en el mismo momento en que alguien reincide, no cuando el
usuario abre una carpeta activada.

Si tu uso de ``ruta_de_proyecto`` es legitimo (estas CREANDO un proyecto), anade
el modulo a :data:`PUEDEN_CREAR` con un comentario que lo justifique.
"""

from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Modulos que SI pueden crear proyectos con ``rutas.ruta_de_proyecto``.
PUEDEN_CREAR = {
    "rutas.py",                        # definicion y helper de creacion
    "fabrica.py",                      # crear_proyecto
    "orquestador.py",                  # asegurar_proyecto (modo consola)
    "herramientas_archivos.py",        # SOLO el fallback de base_de_proyecto()
    "scripts/verificar_servidor.py",   # verifica creando un proyecto temporal
    "scripts/verificar_fabrica.py",    # idem
    "tests/test_fabrica.py",           # dobles de prueba
    "tests/test_rutas.py",             # prueba del propio helper
    "tests/test_verificar_servidor.py",
}

#: El unico punto del modulo de archivos donde el slug esta justificado: el
#: fallback para un proyecto que no tiene ficha (todavia no registrado). Todo lo
#: demas -listar, buscar, leer, escribir, borrar- tiene que pasar por
#: ``base_de_proyecto()``.
FUNCIONES_CON_SLUG_JUSTIFICADO = {"base_de_proyecto"}

#: Modulos que solo tocan contenido EXISTENTE: el atajo del slug esta prohibido.
CON_POLITICA = ("herramientas_archivos.py",)


def _nombre_de_llamada(nodo: ast.AST) -> str:
    """Nombre cualificado de una llamada: ``rutas.ruta_de_proyecto``."""
    partes = []
    actual = nodo
    while isinstance(actual, ast.Attribute):
        partes.append(actual.attr)
        actual = actual.value
    if not isinstance(actual, ast.Name):
        return ""
    partes.append(actual.id)
    return ".".join(reversed(partes))


def _llamadas(arbol: ast.AST) -> set:
    """Todas las llamadas del arbol (sin duplicados)."""
    nombres = {
        _nombre_de_llamada(nodo.func)
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call)
    }
    return {nombre for nombre in nombres if nombre}


def _llamadas_de(arbol: ast.AST, funcion: str) -> set:
    """Llamadas que hay dentro de una funcion concreta."""
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.name == funcion:
            nombres |= _llamadas(nodo)
    return nombres


def _modulos_del_repositorio() -> list:
    """Modulos Python propios del repositorio (raiz, ``scripts/`` y ``tests/``)."""
    ficheros = list(RAIZ.glob("*.py"))
    ficheros += list((RAIZ / "scripts").glob("*.py"))
    ficheros += list((RAIZ / "tests").glob("*.py"))
    return sorted(f for f in ficheros if f.name != "conftest.py")


def _funciones_que_llaman(arbol: ast.AST, nombre: str) -> set:
    """Nombres de las funciones desde las que se llama a ``nombre``."""
    culpables = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nombre in _llamadas(nodo):
            culpables.add(nodo.name)
    return culpables


def test_las_herramientas_de_archivos_no_derivan_rutas_con_el_slug():
    """Regresion del defecto real: 4 sitios pedian la carpeta al slug.

    El modulo SI puede nombrar ``rutas.ruta_de_proyecto`` dentro de
    ``base_de_proyecto`` (fallback de un proyecto sin ficha todavia), pero
    ninguna otra funcion: ahi el slug dejaba invisibles los proyectos activados
    en otra carpeta y permitia borrar la raiz equivocada.
    """
    for relativo in CON_POLITICA:
        arbol = ast.parse((RAIZ / relativo).read_text(encoding="utf-8"))
        llamadas = _llamadas(arbol)

        assert "rutas.ruta_de_proyecto" in llamadas, (
            "{} deberia seguir preguntando la carpeta a la ficha (base_de_proyecto)".format(
                relativo
            )
        )
        con_slug = _funciones_que_llaman(arbol, "rutas.ruta_de_proyecto")
        assert con_slug <= FUNCIONES_CON_SLUG_JUSTIFICADO, (
            "{} llama a rutas.ruta_de_proyecto desde {}: para contenido que ya existe "
            "usa base_de_proyecto()".format(relativo, ", ".join(sorted(con_slug)))
        )
        assert "base_de_proyecto" in _llamadas(arbol)


def test_el_resolutor_central_de_las_herramientas_usa_la_ruta_fichada():
    """El candado no sirve de nada si el resolutor se salta la ficha."""
    arbol = ast.parse((RAIZ / "herramientas_archivos.py").read_text(encoding="utf-8"))

    assert "base_de_proyecto" in _llamadas_de(arbol, "_resolver")


def test_nadie_mas_crea_proyectos_por_slug_sin_declararlo():
    """Si un modulo empieza a usar el slug, hay que justificarlo aqui."""
    culpables = []
    for fichero in _modulos_del_repositorio():
        relativo = fichero.relative_to(RAIZ).as_posix()
        try:
            arbol = ast.parse(fichero.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            # Un fichero que no es Python valido no puede llamar a nada: se
            # salta. Si ademas tiene pinta de codigo roto, eso se arregla aparte
            # (no lo decide una prueba de politica de rutas).
            continue
        if "rutas.ruta_de_proyecto" in _llamadas(arbol) and relativo not in PUEDEN_CREAR:
            culpables.append(relativo)

    assert not culpables, (
        "usan rutas.ruta_de_proyecto sin estar en PUEDEN_CREAR: {}. Si es para CREAR "
        "un proyecto, anadelo a la lista con un comentario; si es contenido que ya "
        "existe, usa base_de_proyecto()".format(", ".join(culpables))
    )
