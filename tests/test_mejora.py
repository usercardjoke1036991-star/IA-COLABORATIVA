"""Pruebas del bucle de mejora continua (:mod:`mejora`).

El bucle es el corazon de la idea: la IA del IDE informa (con evidencia real),
la IA de la API sugiere y se vuelve a implementar. Aqui se fija entero con un
arquitecto de mentira: sin red y sin gastar un solo token.
"""

from __future__ import annotations

import pytest

import activacion
import mejora
import sesiones
from arquitecto import Respuesta


class ArquitectoFalso:
    """Motor inyectado: devuelve una directriz fija y guarda lo que recibio."""

    proveedor = "falso"
    modelo = "falso"
    turno = 1

    def __init__(self, terminada: bool = False, error: str = "") -> None:
        self.terminada = terminada
        self.error = error
        self.vistos = []

    def revisar_mejoras(self, proyecto, informe, contexto="", memoria=""):
        self.vistos.append(
            {"proyecto": proyecto, "informe": informe, "contexto": contexto, "memoria": memoria}
        )
        if self.error:
            return Respuesta(error=self.error)
        return Respuesta(
            contenido="## Diagnostico\nok\n## Sugerencias\n1. [alto] anade tipado -> src/x.py",
            turno=len(self.vistos),
            proveedor="falso",
            modelo="falso",
            terminada=self.terminada,
            segundos=0.01,
        )


@pytest.fixture()
def proyecto(sandbox):
    """Proyecto activado y listo para el bucle."""
    carpeta = sandbox / "proyectos" / "app-bucle"
    carpeta.mkdir(parents=True)
    (carpeta / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    activacion.activar(ruta=carpeta)
    return "app-bucle"


def test_informe_exige_hechos_y_evidencia(proyecto):
    with pytest.raises(ValueError):
        mejora.informe_de_trabajo(proyecto, hechos="", evidencia="pytest")
    with pytest.raises(ValueError):
        mejora.informe_de_trabajo(proyecto, hechos="algo", evidencia="")


def test_informe_escribe_los_artefactos_y_la_ronda(proyecto, sandbox):
    texto = mejora.informe_de_trabajo(
        proyecto, hechos="cree el modulo", evidencia="pytest -q -> 3 passed"
    )

    assert "Ronda 1" in texto
    carpeta = sandbox / "proyectos" / "app-bucle"
    informe = (carpeta / activacion.ARCHIVO_INFORME).read_text(encoding="utf-8")
    assert "cree el modulo" in informe
    assert "pytest -q -> 3 passed" in informe
    assert sesiones.siguiente_ronda(proyecto) == 2


def test_sugerir_sin_informe_previo_avisa(proyecto):
    with pytest.raises(ValueError):
        mejora.sugerir_mejoras(proyecto, arquitecto=ArquitectoFalso())


def test_sugerir_guarda_la_directriz_y_pide_seguir(proyecto, sandbox):
    falso = ArquitectoFalso()
    mejora.informe_de_trabajo(proyecto, hechos="cree el modulo", evidencia="pytest -q -> 3 passed")

    texto = mejora.sugerir_mejoras(proyecto, enfoque="pruebas", arquitecto=falso)

    assert "EN CURSO" in texto
    assert "anade tipado" in texto
    carpeta = sandbox / "proyectos" / "app-bucle"
    assert "anade tipado" in (carpeta / activacion.ARCHIVO_SUGERENCIAS).read_text(encoding="utf-8")
    assert falso.vistos[0]["proyecto"] == proyecto
    assert "ENFOQUE" in falso.vistos[0]["contexto"]


def test_el_arquitecto_recibe_el_informe_y_la_memoria(proyecto):
    falso = ArquitectoFalso()
    mejora.informe_de_trabajo(
        proyecto, hechos="cree el modulo", evidencia="3 passed", sugerencias_propias="1. tipado"
    )

    mejora.sugerir_mejoras(proyecto, arquitecto=falso)

    visto = falso.vistos[0]
    assert "cree el modulo" in visto["informe"]
    assert "sugerencias propias" in visto["informe"]
    assert "ronda 1" in visto["memoria"]


def test_sugerir_cierra_el_bucle_cuando_el_arquitecto_dice_fin(proyecto):
    falso = ArquitectoFalso(terminada=True)
    mejora.informe_de_trabajo(proyecto, hechos="termine", evidencia="pytest -q -> 9 passed")

    texto = mejora.sugerir_mejoras(proyecto, arquitecto=falso)

    assert "TAREA TERMINADA" in texto
    assert sesiones.sesion_cerrada(proyecto)


def test_tras_cerrar_no_se_vuelve_a_llamar_al_arquitecto(proyecto):
    falso = ArquitectoFalso(terminada=True)
    mejora.informe_de_trabajo(proyecto, hechos="termine", evidencia="9 passed")
    mejora.sugerir_mejoras(proyecto, arquitecto=falso)

    otro = ArquitectoFalso()
    texto = mejora.sugerir_mejoras(proyecto, arquitecto=otro)

    assert "ya esta cerrada" in texto
    assert otro.vistos == []


def test_el_tope_de_rondas_cierra_la_sesion(proyecto, monkeypatch):
    monkeypatch.setenv("ARQUITECTO_MAX_RONDAS", "1")
    for _ in range(2):
        mejora.informe_de_trabajo(proyecto, hechos="ronda", evidencia="1 passed")

    mejora.sugerir_mejoras(proyecto, arquitecto=ArquitectoFalso())

    assert sesiones.sesion_cerrada(proyecto)
    assert "tope de rondas" in sesiones.ultimo_turno(proyecto)["motivo_de_cierre"]


def test_la_palabra_de_parada_en_el_informe_avisa(proyecto):
    texto = mejora.informe_de_trabajo(proyecto, hechos="terminado, PARAR", evidencia="1 passed")

    assert "PARAR" in texto


def test_el_error_del_arquitecto_no_rompe_el_bucle(proyecto):
    mejora.informe_de_trabajo(proyecto, hechos="algo", evidencia="1 passed")

    texto = mejora.sugerir_mejoras(proyecto, arquitecto=ArquitectoFalso(error="sin saldo"))

    assert "sin saldo" in texto
    assert not sesiones.sesion_cerrada(proyecto)


def test_estado_de_sesion_resume_las_rondas(proyecto):
    mejora.informe_de_trabajo(proyecto, hechos="cree el modulo", evidencia="1 passed")

    texto = mejora.estado_de_sesion(proyecto)

    assert "app-bucle" in texto
    assert "rondas: 1" in texto
