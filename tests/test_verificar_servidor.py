"""Pruebas del aislamiento de ``scripts/verificar_servidor.py``.

El paso 6 crea un proyecto de verdad a traves del tool ``crear_proyecto`` y
despues borra la carpeta temporal. El peligro esta en el registro: con
``ARQUITECTO_CARPETA_PROYECTOS`` redirigido pero ``ARQUITECTO_REGISTRO`` sin
tocar, la verificacion apuntaba al registro REAL y dejaba en el la ficha de un
temporal ya borrado (``ARQUITECTO_PERSISTIR=0`` solo protege el historial, no
``datos/proyectos.json``).

Estas pruebas fijan las dos redes: el aislamiento interno del paso 6, que no
escribe en el registro que la verificacion tenia al empezar, y el cinturon del
script (``entorno_aislado``), que apunta a un temporal propio cuando nadie ha
redirigido nada —el caso del CI— y que el paso 7 vigila con la huella SHA-256
del registro real.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import tempfile
from pathlib import Path

import pytest

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


# --------------------------------------------------------------------------
# El cinturon del script: ``entorno_aislado``
# --------------------------------------------------------------------------
def _entorno() -> dict:
    return {clave: os.environ.get(clave) for clave in verificador.ENTORNO_ISLAMIENTO}


def _sin_redireccion(monkeypatch) -> None:
    """Deja el entorno como una maquina normal: nada redirigido a mano."""
    for clave in verificador.ENTORNO_ISLAMIENTO:
        monkeypatch.delenv(clave, raising=False)


def test_el_cinturon_aisla_registro_y_carpeta_sin_redireccion(sandbox, monkeypatch):
    """Sin nada redirigido el script se apunta a un temporal suyo y lo borra."""
    monkeypatch.setattr(fabrica, "RUTA_REGISTRO", sandbox / "datos" / "proyectos.json")
    _sin_redireccion(monkeypatch)

    with verificador.entorno_aislado() as temporal:
        assert temporal is not None
        assert temporal.name.startswith(verificador.PREFIJO_TEMPORAL)
        registro = Path(os.environ["ARQUITECTO_REGISTRO"])
        carpeta = Path(os.environ["ARQUITECTO_CARPETA_PROYECTOS"])
        assert rutas.esta_dentro(carpeta, temporal)
        assert rutas.esta_dentro(registro, temporal)
        assert registro.name == verificador.NOMBRE_REGISTRO_AISLADO
        # La fabrica acepta ese registro: no se sale de sus raices permitidas.
        assert rutas.esta_dentro(fabrica.ruta_registro(), temporal)

    assert not temporal.exists(), "el cinturon dejo su temporal en disco"
    assert not (sandbox / "datos").exists()
    assert _entorno() == {clave: None for clave in verificador.ENTORNO_ISLAMIENTO}


def test_el_cinturon_respeta_lo_que_ya_venia_redirigido(sandbox):
    """En el CI y en las pruebas el entorno ya viene aislado: no se toca."""
    antes = _entorno()

    with verificador.entorno_aislado() as temporal:
        assert temporal is None
        assert _entorno() == antes

    assert _entorno() == antes


def test_el_cinturon_rellena_solo_la_carpeta_que_falta(sandbox, monkeypatch):
    monkeypatch.delenv("ARQUITECTO_CARPETA_PROYECTOS", raising=False)
    registro = os.environ["ARQUITECTO_REGISTRO"]

    with verificador.entorno_aislado() as temporal:
        assert temporal is not None
        assert os.environ["ARQUITECTO_REGISTRO"] == registro
        assert rutas.esta_dentro(Path(os.environ["ARQUITECTO_CARPETA_PROYECTOS"]), temporal)

    assert os.environ["ARQUITECTO_REGISTRO"] == registro


def test_el_cinturon_rellena_solo_el_registro_que_falta(sandbox, monkeypatch):
    """La carpeta del usuario manda: el registro temporal vive a su lado."""
    monkeypatch.delenv("ARQUITECTO_REGISTRO", raising=False)
    carpeta = os.environ["ARQUITECTO_CARPETA_PROYECTOS"]

    with verificador.entorno_aislado() as temporal:
        assert temporal is None
        assert os.environ["ARQUITECTO_CARPETA_PROYECTOS"] == carpeta
        registro = Path(os.environ["ARQUITECTO_REGISTRO"])
        assert registro.name == verificador.NOMBRE_REGISTRO_AISLADO
        assert registro.parent == Path(carpeta)
        # Dentro de las raices permitidas: la fabrica no lo rechaza.
        assert rutas.esta_dentro(fabrica.ruta_registro(), Path(carpeta))

    assert _entorno() == {
        "ARQUITECTO_CARPETA_PROYECTOS": carpeta,
        "ARQUITECTO_REGISTRO": None,
    }


def test_el_cinturon_restaura_el_entorno_si_un_paso_peta(sandbox, monkeypatch):
    _sin_redireccion(monkeypatch)
    antes = _entorno()

    class _Peta(Exception):
        pass

    with pytest.raises(_Peta):
        with verificador.entorno_aislado() as temporal:
            creado = str(temporal)
            raise _Peta("el paso revienta")

    assert _entorno() == antes
    assert not Path(creado).exists(), "el cinturon no limpio su temporal"


# --------------------------------------------------------------------------
# ``main``: el cinturon y el paso 7
# --------------------------------------------------------------------------
def _pasos_de_mentira(monkeypatch, paso_mcp) -> None:
    """Sustituye los pasos 1-5 por dobles: aqui se prueba el aislamiento."""
    monkeypatch.setattr(verificador, "_resultados", [])
    monkeypatch.setattr(verificador, "paso_dependencias", lambda: True)
    monkeypatch.setattr(verificador, "paso_modulos", lambda: (None, None))
    monkeypatch.setattr(verificador, "paso_servidor", lambda: None)
    monkeypatch.setattr(verificador, "paso_global", lambda: True)
    monkeypatch.setattr(verificador, "paso_invocacion", lambda servidor: True)
    monkeypatch.setattr(verificador, "paso_dependencias_mcp", paso_mcp)
    # ``main`` escribe en el entorno del proceso: monkeypatch lo devuelve a su
    # sitio al terminar la prueba.
    for clave in ("ARQUITECTO_LOG", "ARQUITECTO_MOCK", "ARQUITECTO_PERSISTIR"):
        monkeypatch.setenv(clave, os.environ.get(clave, ""))


def test_main_aisla_los_pasos_aunque_no_se_redirija_nada(sandbox, monkeypatch, capsys):
    """Un paso descuidado, sin su propio aislamiento, no llega al registro real.

    Es el escenario del CI: nada redirigido a mano y un paso que crea un
    proyecto como hacia el paso 6 antes de su arreglo. Ahora quien protege es el
    cinturon del script, no el aislamiento interno del paso.
    """
    monkeypatch.setattr(fabrica, "RUTA_REGISTRO", sandbox / "datos" / "proyectos.json")
    _sin_redireccion(monkeypatch)
    usados = []

    def _paso_descuidado(servidor):
        usados.append(os.environ.get("ARQUITECTO_CARPETA_PROYECTOS"))
        creado = rutas.ruta_de_proyecto("verificacion-descuidada")
        creado.mkdir(parents=True, exist_ok=True)
        fabrica.registrar_proyecto(
            fabrica.Proyecto(nombre="verificacion-descuidada", ruta=str(creado))
        )
        return True

    _pasos_de_mentira(monkeypatch, _paso_descuidado)

    codigo = verificador.main([])

    texto = capsys.readouterr().out
    assert codigo == 0
    assert "aislamiento" in texto
    # El paso descuidado trabajo en el temporal del cinturon, no en el sandbox.
    assert len(usados) == 1 and usados[0] and usados[0] != str(sandbox / "proyectos")
    assert not (sandbox / "datos").exists(), "el registro real acabo escrito"
    assert "PASO 7" in texto
    assert "0 FALLOS" in texto
    assert not list(Path(tempfile.gettempdir()).glob("{}*".format(verificador.PREFIJO_TEMPORAL)))


def test_main_canta_si_el_registro_real_cambia(sandbox, monkeypatch, capsys):
    """El paso 7 es el que avisa: un paso que escribe en el real se detecta."""
    real = sandbox / "datos" / "proyectos.json"
    monkeypatch.setattr(fabrica, "RUTA_REGISTRO", real)
    _sin_redireccion(monkeypatch)

    def _paso_traidor(servidor):
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_text("[]", encoding="utf-8")
        return True

    _pasos_de_mentira(monkeypatch, _paso_traidor)

    codigo = verificador.main([])

    texto = capsys.readouterr().out
    assert codigo == 1
    assert "PASO 7" in texto
    assert "la verificacion escribio en el registro real de proyectos" in texto


def test_main_avisa_si_no_puede_aislar_el_registro(sandbox, monkeypatch, capsys):
    """Sin temporal propio no hay cinturon: mejor fallar que escribir donde no toca."""
    _sin_redireccion(monkeypatch)
    _pasos_de_mentira(monkeypatch, lambda servidor: True)

    class _TemporalRoto:
        """Doble de ``tempfile`` que no puede crear la carpeta temporal."""

        def mkdtemp(self, *argumentos, **clave):
            raise OSError("no hay permisos en el temporal")

    monkeypatch.setattr(verificador, "tempfile", _TemporalRoto())

    codigo = verificador.main([])

    texto = capsys.readouterr().out
    assert codigo == 1
    assert "no se pudo aislar el registro" in texto
    assert os.environ.get("ARQUITECTO_REGISTRO") is None


# --------------------------------------------------------------------------
# La limpieza del temporal: ``_borrar_temporal``
# --------------------------------------------------------------------------
def _arbol_con_objeto_de_git(carpeta: Path) -> Path:
    """Arbol de prueba con un objeto de git de solo lectura, como los reales."""
    objetos = carpeta / ".git" / "objects" / "0d"
    objetos.mkdir(parents=True)
    fichero = objetos / "d9e58b4eee99b9416b19a6cf23b1de2f6cd450"
    fichero.write_text("objeto", encoding="utf-8")
    os.chmod(fichero, stat.S_IREAD)  # en Windows, atributo de solo lectura
    return fichero


def test_borrar_temporal_quita_arboles_con_solo_lectura(tmp_path):
    """El caso que se le escapaba a ``rmtree(ignore_errors=True)`` en Windows.

    Los objetos de git (``.git/objects``) van marcados de solo lectura y hacen
    que el borrado falle en silencio: sin quitarlos, el cinturon dejaria su
    temporal en disco y aun asi diria que lo limpio.
    """
    arbol = tmp_path / "verificacion-mcp-prueba"
    _arbol_con_objeto_de_git(arbol)

    assert verificador._borrar_temporal(arbol) is True
    assert not arbol.exists()


def test_borrar_temporal_avisa_si_no_pudo_borrar(tmp_path, monkeypatch):
    """Si el arbol sigue en disco, el ayudante no puede decir que lo limpio."""
    arbol = tmp_path / "verificacion-mcp-testarudo"
    _arbol_con_objeto_de_git(arbol)
    monkeypatch.setattr(verificador.shutil, "rmtree", lambda *argumentos, **clave: None)

    assert verificador._borrar_temporal(arbol, intentos=1) is False
    assert arbol.exists()


def test_limpiar_borra_ficheros_de_solo_lectura(tmp_path, capsys):
    """El fichero que crea el paso 5 se borra aunque este marcado de solo lectura."""
    fichero = tmp_path / ".verificacion_plan.md"
    fichero.write_text("plan", encoding="utf-8")
    os.chmod(fichero, stat.S_IREAD)  # en Windows, atributo de solo lectura

    verificador._limpiar(fichero)

    assert not fichero.exists()
    assert "AVISO" not in capsys.readouterr().out


def test_limpiar_avisa_si_no_pudo_borrar(tmp_path, capsys):
    """Si no se puede borrar (aqui, porque es una carpeta), el paso lo dice.

    Antes el ``except OSError: pass`` lo escondia y el paso 5 daba el OK con el
    fichero todavia en la raiz del repositorio.
    """
    estorbo = tmp_path / ".verificacion_plan.md"
    estorbo.mkdir()

    verificador._limpiar(estorbo, intentos=1)

    assert "AVISO: no se pudo borrar" in capsys.readouterr().out
    assert estorbo.exists()
