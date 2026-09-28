"""Pruebas del saneado de argumentos del orquestador (inyeccion de argumentos).

El orquestador lanza la CLI de Cline con valores que vienen de fuera: la idea del
usuario, el numero de turnos, el ejecutable del ``.env``. Un valor que empiece
por ``-`` lo leeria el CLI de destino como una OPCION y un byte NUL corta la
cadena al llegar al sistema. Son los dos casos de la regla ``pythonsecurity:S8705``
("Agentic workflows should not be vulnerable to argument injection attacks").
"""

from __future__ import annotations

import pytest

import orquestador


# --------------------------------------------------------------------------
# Turnos: el numero de rondas es un entero acotado, nunca texto sin validar
# --------------------------------------------------------------------------
def test_los_turnos_se_convierten_en_entero():
    assert orquestador._turnos_validados("3") == 3  # noqa: SLF001 - contrato interno
    assert orquestador._turnos_validados(2) == 2  # noqa: SLF001


@pytest.mark.parametrize("valor", [0, -1, orquestador.TURNOS_MAXIMOS + 1])
def test_los_turnos_fuera_de_rango_se_rechazan(valor):
    with pytest.raises(ValueError):
        orquestador._turnos_validados(valor)  # noqa: SLF001


@pytest.mark.parametrize("valor", ["--yolo", "muchos", None])
def test_unos_turnos_que_no_son_numero_se_rechazan(valor):
    with pytest.raises(ValueError):
        orquestador._turnos_validados(valor)  # noqa: SLF001


# --------------------------------------------------------------------------
# Argumentos: el saneado que exige la regla de inyeccion de argumentos
# --------------------------------------------------------------------------
def test_un_argumento_que_empieza_por_guion_se_rechaza():
    """El CLI de destino lo leeria como una opcion, no como un valor."""
    with pytest.raises(ValueError):
        orquestador._argumento_seguro("--yolo", "el ejecutable de cline")  # noqa: SLF001


def test_un_argumento_con_byte_nulo_se_rechaza():
    with pytest.raises(ValueError):
        orquestador._argumento_seguro("hola\x00--yolo", "el prompt")  # noqa: SLF001


def test_un_argumento_vacio_se_rechaza():
    with pytest.raises(ValueError):
        orquestador._argumento_seguro("", "el prompt")  # noqa: SLF001


def test_un_argumento_normal_pasa_tal_cual():
    assert orquestador._argumento_seguro("cline", "el ejecutable") == "cline"  # noqa: SLF001
    ruta = r"C:\proyectos\demo"
    assert orquestador._argumento_seguro(ruta, "la ruta") == ruta  # noqa: SLF001
    # El prompt del turno es multilinea y lleva guiones dentro: sigue siendo valido.
    multilinea = "TURNO 1/3\n\nOBJETIVO:\n- haz A\n- haz B"
    assert orquestador._argumento_seguro(multilinea, "el prompt") == multilinea  # noqa: SLF001
