"""Pruebas del sandbox de rutas (:mod:`rutas`): la red de seguridad de la fabrica."""

from __future__ import annotations

from pathlib import Path

import pytest

import rutas
from rutas import ErrorRuta, normalizar_nombre, resolver_en_proyecto


@pytest.mark.parametrize(
    "crudo, esperado",
    [
        ("Bot de Arbitraje", "bot-de-arbitraje"),
        ("  Mi Proyecto_2  ", "mi-proyecto-2"),
        ("Acentos y Ñ", "acentos-y-n"),
        ("a/b/c", "a-b-c"),
        ("api.v2", "api.v2"),
    ],
)
def test_normalizar_nombre_produce_slug(crudo, esperado):
    assert normalizar_nombre(crudo) == esperado


@pytest.mark.parametrize("crudo", ["", "   ", "...", "***", "///"])
def test_normalizar_nombre_rechaza_nombres_vacios(crudo):
    with pytest.raises(ErrorRuta):
        normalizar_nombre(crudo)


def test_normalizar_nombre_esquiva_los_reservados_de_windows():
    assert normalizar_nombre("CON") == "con-app"
    assert normalizar_nombre("nul") == "nul-app"


def test_normalizar_nombre_recorta_longitudes_largas():
    assert len(normalizar_nombre("a" * 300)) == 64


def test_raices_permitidas_incluye_la_carpeta_de_la_fabrica(sandbox):
    assert (sandbox / "proyectos").resolve() in rutas.raices_permitidas()


def test_esta_dentro_no_confunde_carpetas_hermanas(sandbox):
    assert rutas.esta_dentro(sandbox / "proyectos" / "a" / "b.txt", sandbox / "proyectos")
    assert not rutas.esta_dentro(sandbox / "fuera.txt", sandbox / "proyectos")
    assert not rutas.esta_dentro(sandbox / "proyectos-otros", sandbox / "proyectos")


def test_resolver_en_proyecto_permite_rutas_internas(sandbox):
    destino = resolver_en_proyecto("demo", "src/app.py", crear_padres=True)

    assert rutas.esta_dentro(destino, sandbox / "proyectos")
    assert destino.parent.is_dir()


def test_resolver_en_proyecto_bloquea_el_escape_de_la_raiz(sandbox):
    with pytest.raises(ErrorRuta):
        resolver_en_proyecto("demo", "../../secreto.txt")


def test_resolver_bloquea_extensiones_peligrosas(sandbox):
    with pytest.raises(ErrorRuta):
        resolver_en_proyecto("demo", "carpeta/instalador.exe")


def test_resolver_bloquea_nombres_reservados_del_sistema(sandbox):
    with pytest.raises(ErrorRuta):
        resolver_en_proyecto("demo", "nul")


def test_resolver_rechaza_rutas_vacias(sandbox):
    with pytest.raises(ErrorRuta):
        resolver_en_proyecto("demo", "   ")


def test_resolver_rechaza_bytes_nulos(sandbox):
    with pytest.raises(ErrorRuta):
        resolver_en_proyecto("demo", "app/ma\x00in.py")


def test_ruta_de_proyecto_crea_la_carpeta(sandbox):
    carpeta = rutas.ruta_de_proyecto("Mi Proyecto", crear=True)

    assert carpeta.is_dir()
    assert carpeta.name == "mi-proyecto"
