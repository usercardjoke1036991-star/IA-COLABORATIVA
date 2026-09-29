"""Pruebas del sandbox de rutas (:mod:`rutas`): la red de seguridad de la fabrica."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import rutas
from conftest import alias_de_carpeta
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


def test_esta_dentro_admite_la_misma_carpeta_escrita_de_otra_forma(sandbox):
    """Un enlace (o un nombre 8.3) apunta a la misma carpeta: sigue estando dentro.

    En el runner de Windows el temporal se escribe con el nombre corto
    (``...\\RUNNER~1\\...``) y la raiz permitida se resuelve al largo
    (``...\\runneradmin\\...``), de modo que las dos escrituras tienen que
    valer igual.
    """
    real = Path(sandbox).resolve()
    alias = alias_de_carpeta(real)
    if alias is None:
        pytest.skip("esta maquina no ofrece otra forma de nombrar la carpeta")

    assert rutas.esta_dentro(alias / "proyectos" / "nuevo.txt", real / "proyectos")
    assert rutas.esta_dentro(alias / "registro.json", real)
    assert not rutas.esta_dentro(alias / "fuera.txt", real / "proyectos")


# --------------------------------------------------------------------------
# Confinamiento: la ruta no puede salir de la base declarada
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "ataque",
    [
        "..",
        "../",
        "./sub/..",
        "../otro-proyecto",
        "../otro-proyecto/colado.txt",
        "sub/../../colado.txt",
    ],
)
def test_resolver_confinado_bloquea_el_traversal_con_puntos(sandbox, ataque):
    """Los ataques clasicos caen, aunque el destino siga dentro de la fabrica."""
    base = sandbox / "proyectos" / "demo"

    with pytest.raises(ErrorRuta, match="fuera del proyecto"):
        rutas.resolver(ataque, base=base, confinar_a_base=True)


@pytest.mark.skipif(os.name != "nt", reason="las barras invertidas solo son ruta en Windows")
def test_resolver_confinado_bloquea_el_traversal_con_barras_invertidas(sandbox):
    base = sandbox / "proyectos" / "demo"

    with pytest.raises(ErrorRuta, match="fuera del proyecto"):
        rutas.resolver("..\\otro-proyecto\\colado.txt", base=base, confinar_a_base=True)


def test_resolver_confinado_admite_la_base_y_sus_hijos(sandbox):
    base = sandbox / "proyectos" / "demo"

    assert rutas.resolver(".", base=base, confinar_a_base=True) == base.resolve()
    interno = rutas.resolver("src/app.py", base=base, crear_padres=True, confinar_a_base=True)

    assert interno.parent.is_dir()
    assert rutas.esta_dentro(interno, base)


def test_resolver_confinado_bloquea_una_ruta_absoluta_de_fuera(sandbox):
    base = sandbox / "proyectos" / "demo"
    base.mkdir(parents=True)
    vecino = sandbox / "proyectos" / "vecino"
    vecino.mkdir()

    with pytest.raises(ErrorRuta, match="fuera del proyecto"):
        rutas.resolver(str(vecino / "secreto.txt"), base=base, confinar_a_base=True)


@pytest.mark.parametrize(
    "ataque",
    [
        "/etc/passwd",
        "/tmp/secreto.txt",
        "//otro/share/x.txt",
    ],
)
def test_resolver_confinado_bloquea_absolutas_y_red(sandbox, ataque):
    """Una ruta absoluta no es "relativa al proyecto": se rechaza sin resolver."""
    base = sandbox / "proyectos" / "demo"

    with pytest.raises(ErrorRuta, match="fuera del proyecto"):
        rutas.resolver(ataque, base=base, confinar_a_base=True)


@pytest.mark.skipif(os.name != "nt", reason="vectores de ruta propios de Windows")
@pytest.mark.parametrize(
    "ataque",
    [
        "C:\\Windows\\win.ini",
        "C:/Windows/win.ini",
        "\\\\?\\C:\\Windows\\win.ini",
        "\\\\.\\NUL",
        "\\\\localhost\\c$\\secreto.txt",
        "..\\..\\colado.txt",
    ],
)
def test_resolver_confinado_bloquea_los_vectores_de_windows(sandbox, ataque):
    """Letra de unidad, dispositivo (``\\\\?\\``, ``\\\\.\\``), recurso de red y ``..``."""
    base = sandbox / "proyectos" / "demo"

    with pytest.raises(ErrorRuta, match="fuera del proyecto"):
        rutas.resolver(ataque, base=base, confinar_a_base=True)


@pytest.mark.parametrize("ataque", ["CON", "con.txt", "NUL", "aux.md", "COM1", "carpeta/nul/x.txt"])
def test_resolver_confinado_bloquea_los_nombres_reservados(sandbox, ataque):
    """Un nombre reservado apunta a un dispositivo, aunque no sea el ultimo tramo."""
    base = sandbox / "proyectos" / "demo"

    with pytest.raises(ErrorRuta, match="fuera del proyecto"):
        rutas.resolver(ataque, base=base, confinar_a_base=True)


def test_resolver_confinado_no_rechaza_rutas_legitimas_raras(sandbox):
    """El candado no puede pasarse de listo: espacios, acentos y puntos valen."""
    base = sandbox / "proyectos" / "demo"

    for valida in ("docs/notas finales.md", "src/ñandú/áéí.py", "api/v2.1/x.json", "a_b-c/d.txt"):
        destino = rutas.resolver(valida, base=base, crear_padres=True, confinar_a_base=True)

        assert rutas.esta_dentro(destino, base.resolve()), valida
        assert destino.exists() is False  # el candado no crea el archivo

    assert (base / "src" / "ñandú").is_dir()


def test_una_absoluta_tampoco_se_cuela_con_permitir_externo(sandbox):
    """El permiso de escritura externa no convierte una absoluta en ruta valida."""
    base = sandbox / "proyectos" / "demo"

    with pytest.raises(ErrorRuta, match="fuera del proyecto"):
        rutas.resolver(
            str(sandbox / "fuera.txt"),
            base=base,
            permitir_externo=True,
            confinar_a_base=True,
        )


def test_el_intento_confinado_no_crea_carpetas(sandbox):
    """El candado se comprueba antes de crear padres: no deja rastro."""
    base = sandbox / "proyectos" / "demo"

    with pytest.raises(ErrorRuta):
        rutas.resolver(
            "../otro-proyecto/colado.txt",
            base=base,
            crear_padres=True,
            confinar_a_base=True,
        )

    assert not (sandbox / "proyectos" / "otro-proyecto").exists()


def test_confinar_a_base_manda_sobre_permitir_externo(sandbox):
    """El permiso de escritura externa no abre la puerta al proyecto vecino."""
    base = sandbox / "proyectos" / "demo"

    with pytest.raises(ErrorRuta, match="fuera del proyecto"):
        rutas.resolver(
            "../otro-proyecto/colado.txt",
            base=base,
            permitir_externo=True,
            confinar_a_base=True,
        )


def test_sin_confinar_se_conserva_el_comportamiento_anterior(sandbox):
    """El candado es explicito: quien no lo pide mantiene lo de antes."""
    destino = rutas.resolver("../otro-proyecto/x.txt", base=sandbox / "proyectos" / "demo")

    assert destino == (sandbox / "proyectos" / "otro-proyecto" / "x.txt").resolve()


@pytest.mark.parametrize("ataque", ["..", "./sub/..", "../otro-proyecto"])
def test_resolver_en_proyecto_no_salta_al_proyecto_vecino(sandbox, ataque):
    (sandbox / "proyectos" / "vecino").mkdir(parents=True)

    with pytest.raises(ErrorRuta):
        resolver_en_proyecto("demo", ataque)
