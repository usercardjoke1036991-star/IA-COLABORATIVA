"""Pruebas de lectura de configuracion (:mod:`config`)."""

from __future__ import annotations

import pytest

import config


def test_bool_vacio_se_interpreta_como_no_definido(monkeypatch):
    """Cadena vacia = hereda del rol base (clave para ``ARQUITECTO_EJECUTOR_*``)."""
    monkeypatch.setenv("ARQUITECTO_PRUEBA_BOOL", "")

    assert config._bool("ARQUITECTO_PRUEBA_BOOL", True) is True


def test_bool_ausente_usa_el_valor_por_defecto(monkeypatch):
    monkeypatch.delenv("ARQUITECTO_PRUEBA_BOOL", raising=False)

    assert config._bool("ARQUITECTO_PRUEBA_BOOL", False) is False


@pytest.mark.parametrize(
    "valor, esperado",
    [
        ("1", True),
        ("si", True),
        ("SI", True),
        ("true", True),
        ("on", True),
        ("0", False),
        ("no", False),
        ("cualquier-cosa", False),
    ],
)
def test_bool_interpreta_valores_habituales(monkeypatch, valor, esperado):
    monkeypatch.setenv("ARQUITECTO_PRUEBA_BOOL", valor)

    assert config._bool("ARQUITECTO_PRUEBA_BOOL", not esperado) is esperado


def test_int_y_float_toleran_valores_invalidos(monkeypatch):
    monkeypatch.setenv("ARQUITECTO_PRUEBA_NUM", "no-es-un-numero")

    assert config._int("ARQUITECTO_PRUEBA_NUM", 7) == 7
    assert config._float("ARQUITECTO_PRUEBA_NUM", 1.5) == 1.5


def test_cargar_env_no_sobreescribe_el_entorno_real(tmp_path, monkeypatch):
    archivo = tmp_path / ".env"
    archivo.write_text("ARQUITECTO_PRUEBA_CLAVE=del-archivo\n", encoding="utf-8")
    monkeypatch.setenv("ARQUITECTO_PRUEBA_CLAVE", "del-sistema")

    config.cargar_env(archivo)

    assert config._texto("ARQUITECTO_PRUEBA_CLAVE") == "del-sistema"


def test_modo_mock_no_exige_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("ARQUITECTO_MOCK", "1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    cfg = config.cargar(tmp_path / "inexistente.env")

    assert cfg.modo_mock is True
    assert cfg.proveedor == "mock"
    assert cfg.problemas() == []


def test_sin_api_key_el_diagnostico_avisa(monkeypatch, tmp_path):
    monkeypatch.delenv("ARQUITECTO_MOCK", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("ARQUITECTO_PROVIDER", "deepseek")

    cfg = config.cargar(tmp_path / "inexistente.env")

    assert cfg.modelo
    assert any("API key" in problema for problema in cfg.problemas())


def test_clave_enmascarada_no_expone_el_secreto():
    cfg = config.Config(api_key="sk-1234567890abcdef")

    assert cfg.clave_enmascarada() == "sk-1...cdef"
    assert "1234567890" not in cfg.resumen()


def test_es_local_reconoce_endpoints_de_la_maquina():
    assert config.Config(url="http://localhost:11434/v1").es_local()
    assert not config.Config(url="https://api.deepseek.com/v1").es_local()


def test_cargar_fabrica_respeta_la_carpeta_del_entorno(monkeypatch, tmp_path):
    destino = tmp_path / "mis-proyectos"
    monkeypatch.setenv("ARQUITECTO_CARPETA_PROYECTOS", str(destino))

    cfg = config.cargar_fabrica(tmp_path / "inexistente.env")

    assert cfg.raiz_proyectos == destino


def test_cargar_fabrica_interpreta_la_lista_de_plantillas(monkeypatch, tmp_path):
    monkeypatch.setenv("ARQUITECTO_PLANTILLAS", "python, web3")

    cfg = config.cargar_fabrica(tmp_path / "inexistente.env")

    assert cfg.plantillas_por_defecto == ["python", "web3"]


def test_cargar_ejecutor_hereda_del_arquitecto(monkeypatch, tmp_path):
    monkeypatch.setenv("ARQUITECTO_PROVIDER", "mock")
    monkeypatch.setenv("ARQUITECTO_EJECUTOR_MODEL", "modelo-programador")

    cfg = config.cargar_ejecutor()

    assert cfg.modelo == "modelo-programador"
    assert cfg.proveedor == "mock"
    assert cfg.ruta_historial.name == "historial_ejecutor.json"


def test_cargar_por_rol_elige_el_rol_correcto(monkeypatch, tmp_path):
    monkeypatch.setenv("ARQUITECTO_PROVIDER", "mock")

    assert config.cargar_por_rol("programador").ruta_historial.name == "historial_ejecutor.json"
    assert config.cargar_por_rol("arquitecto").ruta_historial.name == "historial_arquitecto.json"
