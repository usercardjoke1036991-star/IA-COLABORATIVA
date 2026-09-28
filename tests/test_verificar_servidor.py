"""Pruebas del aislamiento de ``scripts/verificar_servidor.py``.

El paso 6 crea un proyecto de verdad a traves del tool ``crear_proyecto`` y
despues borra la carpeta temporal. El peligro esta en el registro: con
``ARQUITECTO_CARPETA_PROYECTOS`` redirigido pero ``ARQUITECTO_REGISTRO`` sin
tocar, la verificacion apuntaba al registro REAL y dejaba en el la ficha de un
temporal ya borrado (``ARQUITECTO_PERSISTIR=0`` solo protege el historial, no
``datos/proyectos.json``). Estas pruebas fijan que el paso nunca escribe en el
registro real y que devuelve el entorno como estaba.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path

import fabrica
import rutas

RAIZ = Path(__file__).resolve().parent.parent
RUTA_SCRIPT = RAIZ / "scripts" / "verificar_servidor.py"

#: Claves del entorno que el paso 6 redirige durante la prueba.
CLAVES_VIGILADAS = (
    "ARQUITECTO_CARPETA_PROYECTOS",
    "ARQUITECTO_REGISTRO",
    "PIP_INDEX_URL",
    "PIP_RETRIES",
)


def _cargar_script():
    """Importa ``scripts/verificar_servidor.py`` sin que forme parte del paquete."""
    especificacion = importlib.util.spec_from_file_location("verificar_servidor", RUTA_SCRIPT)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


verificador = _cargar_script()


class _Bloque:
    """Bloque de texto de una respuesta MCP (lo que lee ``_a_texto``)."""

    def __init__(self, texto: str):
        self.text = texto


class _ServidorFalso:
    """Doble del servidor MCP: el gestor registra el proyecto como el tool real.

    No se llama a ``fabrica.crear_proyecto`` porque esa ruta instala dependencias
    de verdad (pip, lento y con red). Lo que se prueba aqui es en que registro
    acaba la ficha, y eso solo depende de ``fabrica.ruta_registro()``, que lee el
    entorno del proceso igual que en la ejecucion real.
    """

    def __init__(self):
        self.llamadas = []
        self.entorno = {}
        self._tool_manager = self  # _invocar busca servidor._tool_manager.call_tool

    async def call_tool(self, nombre, argumentos):
        argumentos = dict(argumentos or {})
        self.llamadas.append((nombre, argumentos))
        self.entorno = {clave: os.environ.get(clave) for clave in CLAVES_VIGILADAS}
        creado = rutas.ruta_de_proyecto(argumentos["nombre"])
        creado.mkdir(parents=True, exist_ok=True)
        fabrica.registrar_proyecto(
            fabrica.Proyecto(
                nombre=argumentos["nombre"],
                ruta=str(creado),
                descripcion=argumentos.get("descripcion", ""),
                estado="creado (dependencias pendientes)",
            )
        )
        return [
            _Bloque(
                "\n".join(
                    [
                        "estado_dependencias=pendiente_error_red",
                        "Comando exacto: python -m pip install -r requirements.txt",
                        "Reintenta con preparar_entorno cuando vuelva la red",
                        str(creado),
                    ]
                )
            )
        ]


# --------------------------------------------------------------------------
# El registro real no se toca
# --------------------------------------------------------------------------
def test_el_paso_no_escribe_en_el_registro_real(sandbox):
    registro_real = Path(os.environ["ARQUITECTO_REGISTRO"])
    servidor = _ServidorFalso()

    assert verificador.paso_dependencias_mcp(servidor) is True

    assert [nombre for nombre, _ in servidor.llamadas] == ["crear_proyecto"]
    assert servidor.llamadas[0][1]["instalar_dependencias"] is True
    # El tool vio el registro temporal: la ficha no puede acabar en el real.
    assert servidor.entorno["ARQUITECTO_REGISTRO"] != str(registro_real)
    assert servidor.entorno["ARQUITECTO_REGISTRO"].startswith(
        servidor.entorno["ARQUITECTO_CARPETA_PROYECTOS"]
    )
    assert not registro_real.exists(), "la verificacion creo el registro real"
    assert "verificacion-mcp-deps" not in fabrica.cargar_registro()


def test_el_paso_aisla_tambien_el_registro_por_defecto(sandbox, monkeypatch):
    """Sin ``ARQUITECTO_REGISTRO`` el registro es ``datos/proyectos.json``."""
    monkeypatch.delenv("ARQUITECTO_REGISTRO", raising=False)
    por_defecto = sandbox / "datos" / "proyectos.json"
    # ``RUTA_REGISTRO`` del modulo es el archivo de verdad: se apunta al temporal
    # para que una regresion no pueda ensuciar el repositorio al ejecutar la suite.
    monkeypatch.setattr(fabrica, "RUTA_REGISTRO", por_defecto)

    assert verificador.paso_dependencias_mcp(_ServidorFalso()) is True

    assert not por_defecto.exists(), "la verificacion creo el registro por defecto"


def test_el_paso_restaura_el_entorno(sandbox):
    antes = {clave: os.environ.get(clave) for clave in CLAVES_VIGILADAS}

    verificador.paso_dependencias_mcp(_ServidorFalso())

    assert {clave: os.environ.get(clave) for clave in CLAVES_VIGILADAS} == antes


def test_el_paso_limpia_la_carpeta_temporal(sandbox):
    # El paso crea su carpeta en el temporal del sistema: se compara contra lo
    # que ya habia (los restos de otras ejecuciones no son culpa de este paso).
    antes = {ruta.name for ruta in Path(tempfile.gettempdir()).glob("verificacion-mcp-*")}
    servidor = _ServidorFalso()

    verificador.paso_dependencias_mcp(servidor)

    carpeta = Path(servidor.entorno["ARQUITECTO_CARPETA_PROYECTOS"])
    assert carpeta.name not in antes, "el paso no creo su propia carpeta temporal"
    assert not carpeta.exists(), "quedo el proyecto temporal en disco"
    assert not (carpeta / "verificacion-mcp-deps").exists()
    despues = {ruta.name for ruta in Path(tempfile.gettempdir()).glob("verificacion-mcp-*")}
    assert despues == antes, "el paso dejo temporales en disco"


def test_el_paso_informa_si_la_respuesta_del_tool_no_es_la_esperada(sandbox):
    """Si el tool no devuelve lo pactado, el paso falla (no es un OK silencioso)."""
    class _GestorRoto:
        """Gestor sin ``call_tool``: el mismo caso que un SDK distinto del esperado."""

    servidor = _ServidorFalso()
    servidor._tool_manager = _GestorRoto()

    assert verificador.paso_dependencias_mcp(servidor) is False
