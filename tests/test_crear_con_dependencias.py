"""Pruebas del flujo "crear un proyecto con sus librerias dentro de su carpeta".

Ninguna de estas pruebas instala nada real: se doblan ``procesos.ejecutar`` (el
unico punto de salida de procesos de la fabrica) y ``fabrica._crear_venv`` (que
tardaria segundos por proyecto). Lo que se comprueba es el comportamiento
observable del flujo:

* sin el flag, el comportamiento anterior no cambia (nada de pip);
* con el flag, pip se ejecuta **dentro** de la carpeta del proyecto;
* un fallo de red, de compilacion o de tiempo **nunca** aborta la creacion ni
  borra el proyecto: queda registrado como ``estado_dependencias=pendiente_*``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import config
import fabrica
import procesos


# --------------------------------------------------------------------------
# Dobles
# --------------------------------------------------------------------------
def _espia_instalacion(monkeypatch, codigo=0, salida="", error="", excepcion=None):
    """Sustituye ``procesos.ejecutar`` por un espia que solo finge ``pip``.

    Los comandos que no son de pip (git, venv) se delegan al ejecutor real, asi
    que el resto del flujo se prueba igual.

    Returns:
        Lista de llamadas a pip: ``{"comando", "cwd", "timeout"}``.
    """
    llamadas = []
    original = procesos.ejecutar

    def falso(comando, cwd, timeout=300, entorno_extra=None):
        if "pip" in " ".join(str(pieza) for pieza in comando):
            llamadas.append(
                {"comando": [str(pieza) for pieza in comando], "cwd": Path(cwd), "timeout": timeout}
            )
            if excepcion is not None:
                raise excepcion
            return (codigo, salida, error)
        return original(comando, cwd, timeout=timeout, entorno_extra=entorno_extra)

    monkeypatch.setattr(procesos, "ejecutar", falso)
    return llamadas


def _sin_venv_real(monkeypatch):
    """Evita crear un ``venv/`` de verdad (tardaria segundos en los tests)."""
    monkeypatch.setattr(fabrica, "_crear_venv", lambda destino: "venv/ creado (doble de prueba)")


# --------------------------------------------------------------------------
# Creacion con y sin dependencias
# --------------------------------------------------------------------------
def test_crear_sin_flag_mantiene_comportamiento_actual(sandbox, monkeypatch):
    llamadas = _espia_instalacion(monkeypatch)
    _sin_venv_real(monkeypatch)

    informe = fabrica.crear_proyecto("Sin Flag", plantillas_seleccion="vacio")

    raiz = Path(fabrica.ficha_proyecto("sin-flag").ruta)
    assert llamadas == [], "sin pedir dependencias no se debe ejecutar pip"
    assert "Dependencias:" not in informe
    assert not (raiz / "venv").exists()
    assert fabrica.ficha_proyecto("sin-flag").estado == "creado"


def test_crear_con_flag_instala_y_registra_estado_ok(sandbox, monkeypatch):
    llamadas = _espia_instalacion(monkeypatch, salida="Successfully installed demo-1.0")
    _sin_venv_real(monkeypatch)

    informe = fabrica.crear_proyecto(
        "Con Flag",
        plantillas_seleccion="python",
        con_git=False,
        instalar_dependencias=True,
    )

    raiz = Path(fabrica.ficha_proyecto("con-flag").ruta)
    assert len(llamadas) == 1, "se esperaba exactamente un pip install"
    assert llamadas[0]["cwd"] == raiz, "las librerias deben caer en la carpeta del proyecto"
    assert llamadas[0]["comando"][0] == str(fabrica.interprete_venv(raiz))
    assert llamadas[0]["comando"][-2:] == ["-r", "requirements.txt"]
    assert llamadas[0]["timeout"] == fabrica.TIMEOUT_INSTALACION
    assert "estado_dependencias=ok" in informe
    assert "Comando exacto:" not in informe, "con exito no hay nada que reintentar"
    assert fabrica.ficha_proyecto("con-flag").estado == "creado"


def test_crear_con_flag_sin_manifest_marca_sin_manifest_y_no_aborta(sandbox, monkeypatch):
    llamadas = _espia_instalacion(monkeypatch)
    _sin_venv_real(monkeypatch)

    informe = fabrica.crear_proyecto(
        "Sin Manifest",
        plantillas_seleccion="vacio",
        con_git=False,
        instalar_dependencias=True,
    )

    raiz = Path(fabrica.ficha_proyecto("sin-manifest").ruta)
    assert (raiz / "README.md").exists(), "el proyecto debe existir igualmente"
    assert llamadas == [], "sin manifiesto no hay nada que instalar"
    assert "estado_dependencias=pendiente_sin_requirements" in informe
    assert fabrica.ficha_proyecto("sin-manifest").estado == "creado (dependencias pendientes)"


def test_crear_con_flag_red_caida_deja_proyecto_creado_y_estado_pendiente(sandbox, monkeypatch):
    _espia_instalacion(
        monkeypatch,
        codigo=1,
        error="Could not fetch URL https://pypi.org: connection error",
    )
    _sin_venv_real(monkeypatch)

    informe = fabrica.crear_proyecto(
        "Red Caida",
        plantillas_seleccion="python",
        con_git=False,
        instalar_dependencias=True,
    )

    raiz = Path(fabrica.ficha_proyecto("red-caida").ruta)
    assert raiz.is_dir() and (raiz / "README.md").exists(), "el fallo de red no borra el proyecto"
    assert "estado_dependencias=pendiente_error_red" in informe
    assert "connection error" in informe, "el error de pip no debe perderse"
    assert "Comando exacto:" in informe, "el informe debe dejar el comando para reintentar"
    assert "-r requirements.txt" in informe
    assert "Reintenta con preparar_entorno(proyecto='red-caida', instalar=true)." in informe
    assert fabrica.ficha_proyecto("red-caida").estado == "creado (dependencias pendientes)"


# --------------------------------------------------------------------------
# Prioridad entre el flag y la configuracion
# --------------------------------------------------------------------------
def test_instalar_dependencias_se_omite_si_cfg_false_y_flag_none(sandbox, monkeypatch):
    monkeypatch.setenv("ARQUITECTO_INSTALAR_DEPENDENCIAS", "false")
    llamadas = _espia_instalacion(monkeypatch)

    fabrica.crear_proyecto("Callado", plantillas_seleccion="python", con_git=False)

    assert llamadas == [], "con la configuracion en false y sin flag no se instala nada"


def test_la_variable_de_entorno_activa_la_instalacion_si_el_flag_es_none(sandbox, monkeypatch):
    monkeypatch.setenv("ARQUITECTO_INSTALAR_DEPENDENCIAS", "true")
    llamadas = _espia_instalacion(monkeypatch)
    _sin_venv_real(monkeypatch)

    fabrica.crear_proyecto("Por Entorno", plantillas_seleccion="python", con_git=False)

    assert len(llamadas) == 1, "ARQUITECTO_INSTALAR_DEPENDENCIAS=true debe instalar"


def test_el_flag_false_gana_sobre_la_variable_de_entorno(sandbox, monkeypatch):
    monkeypatch.setenv("ARQUITECTO_INSTALAR_DEPENDENCIAS", "true")
    llamadas = _espia_instalacion(monkeypatch)

    fabrica.crear_proyecto(
        "Explicito", plantillas_seleccion="python", con_git=False, instalar_dependencias=False
    )

    assert llamadas == [], "el flag explicito manda sobre la variable de entorno"


# --------------------------------------------------------------------------
# Robustez del instalador
# --------------------------------------------------------------------------
def test_instalar_dependencias_reporta_timeout_sin_lanzar_excepcion(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text("demo==1.0\n", encoding="utf-8")
    _espia_instalacion(monkeypatch, excepcion=subprocess.TimeoutExpired("pip", 5))

    resultado = fabrica._instalar_dependencias(tmp_path, timeout=5)

    assert resultado["estado"] == "pendiente_timeout"
    assert resultado["manifiesto"] == "requirements.txt"
    assert "5s" in resultado["stderr_resumen"]
    assert "preparar_entorno" in resultado["reintento"]


def test_instalar_dependencias_usa_pyproject_cuando_no_hay_requirements(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    llamadas = _espia_instalacion(monkeypatch)

    resultado = fabrica._instalar_dependencias(tmp_path)

    assert resultado["estado"] == "ok"
    assert resultado["manifiesto"] == "pyproject.toml"
    assert llamadas[0]["comando"][-2:] == ["-e", "."]


def test_instalar_dependencias_avisa_si_el_ejecutable_no_existe(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text("demo==1.0\n", encoding="utf-8")
    _espia_instalacion(monkeypatch, excepcion=FileNotFoundError("no existe el interprete"))

    resultado = fabrica._instalar_dependencias(tmp_path)

    assert resultado["estado"] == "pendiente_error_red"
    assert "no existe el interprete" in resultado["stderr_resumen"]


def test_preparar_entorno_informa_del_fallo_sin_levantar_excepcion(sandbox, monkeypatch):
    _sin_venv_real(monkeypatch)
    fabrica.crear_proyecto("Preparar", plantillas_seleccion="python", con_git=False)
    _espia_instalacion(monkeypatch, codigo=1, error="ERROR: no matching distribution found")

    salida = fabrica.preparar_entorno("preparar", instalar=True)

    assert "AVISO" in salida, "un pip roto no puede parecer una instalacion correcta"
    assert "estado=pendiente_error_red" in salida
    assert "no matching distribution found" in salida
    assert "preparar_entorno(proyecto='preparar', instalar=true)" in salida


# --------------------------------------------------------------------------
# Configuracion por defecto
# --------------------------------------------------------------------------
def test_crear_venv_es_true_por_defecto_e_instalar_dependencias_false(monkeypatch, tmp_path):
    monkeypatch.delenv("ARQUITECTO_CREAR_VENV", raising=False)
    monkeypatch.delenv("ARQUITECTO_INSTALAR_DEPENDENCIAS", raising=False)

    cfg = config.cargar_fabrica(tmp_path / "sin.env")

    assert cfg.crear_venv is True, "el entorno virtual del proyecto es lo normal"
    assert cfg.instalar_dependencias is False, "instalar es opt-in (puede tardar o fallar)"


def test_la_variable_de_entorno_activa_la_instalacion_en_la_config(monkeypatch, tmp_path):
    monkeypatch.setenv("ARQUITECTO_INSTALAR_DEPENDENCIAS", "true")

    cfg = config.cargar_fabrica(tmp_path / "sin.env")

    assert cfg.instalar_dependencias is True
    assert "instalar=True" in cfg.resumen()
