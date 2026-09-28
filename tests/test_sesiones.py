"""Pruebas de la memoria de sesion del bucle (:mod:`sesiones`).

Sin esta memoria el arquitecto repetiria sugerencias ya resueltas: es lo que
hace que el bucle converja en vez de dar vueltas.
"""

from __future__ import annotations

import sesiones


def test_sesion_nueva_empieza_en_la_ronda_1(sandbox):
    assert sesiones.siguiente_ronda("mi-app") == 1
    assert sesiones.ultimo_turno("mi-app") == {}
    assert sesiones.resumen_para_arquitecto("mi-app").startswith("(sesion nueva")


def test_guardar_y_leer_turnos_en_orden(sandbox):
    sesiones.guardar_turno("mi-app", {"hechos": "uno"})
    sesiones.guardar_turno("mi-app", {"hechos": "dos"})

    turnos = sesiones.leer_turnos("mi-app")

    assert [turno["ronda"] for turno in turnos] == [1, 2]
    assert turnos[1]["hechos"] == "dos"
    assert sesiones.siguiente_ronda("mi-app") == 3


def test_el_resumen_lleva_hechos_y_directrices(sandbox):
    sesiones.guardar_turno(
        "mi-app",
        {"hechos": "cree el modulo", "directriz": "anade pruebas", "evidencia": "3 passed"},
    )

    resumen = sesiones.resumen_para_arquitecto("mi-app")

    assert "cree el modulo" in resumen
    assert "anade pruebas" in resumen
    assert "3 passed" in resumen


def test_cerrar_sesion_queda_registrado(sandbox):
    sesiones.guardar_turno("mi-app", {"hechos": "uno"})

    sesiones.cerrar_sesion("mi-app", "el arquitecto dijo FIN")

    assert sesiones.sesion_cerrada("mi-app")
    assert "el arquitecto dijo FIN" in sesiones.resumen_para_arquitecto("mi-app")


def test_guardar_turno_es_atomico_y_reanudable(sandbox):
    destino = sesiones.guardar_turno("mi-app", {"hechos": "uno"})

    assert destino.name == "turno-01.json"
    assert not list(destino.parent.glob("*.tmp"))


def test_los_turnos_corruptos_no_rompen_la_memoria(sandbox):
    carpeta = sesiones.carpeta_sesion("mi-app")
    (carpeta / "turno-01.json").write_text("{esto no es json", encoding="utf-8")

    assert sesiones.leer_turnos("mi-app") == []
    assert sesiones.siguiente_ronda("mi-app") == 1


def test_pide_parar_reconoce_las_palabras_de_parada():
    assert sesiones.pide_parar("vale, PARAR")
    assert sesiones.pide_parar("stop")
    assert not sesiones.pide_parar("seguimos con la ronda")
    assert not sesiones.pide_parar("")
