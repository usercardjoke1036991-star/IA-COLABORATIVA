"""Saneado de secretos de punta a punta: lo que sale de esta maquina.

Al proveedor solo viajan dos cosas: el contexto real del repositorio (que
construye :mod:`contexto`) y el informe de la ronda. Estas pruebas colocan
secretos de verdad en el proyecto, interceptan el proveedor con un espia y
comprueban que NINGUNA de esas cadenas aparece en el payload que se enviaria a
la API, ni siquiera si la clave se le escapa al programador dentro del informe.
"""

from __future__ import annotations

import dataclasses

import pytest

import activacion
import config as configuracion
import mejora
from arquitecto import Arquitecto
from historial import Historial

#: Secretos de mentira con la forma exacta de los de verdad.
CLAVE_FAKE = "sk-FAKE1234567890abcdef"
TOKEN_FAKE = "ghp_FAKEabcdefghijklmnopqrstuvwxyz01"
PEM_FAKE = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0B\n-----END PRIVATE KEY-----"


class ProveedorEspia:
    """Proveedor de mentira: guarda los mensajes en vez de llamar a la API."""

    nombre = "espia"

    def __init__(self) -> None:
        self.mensajes = []

    def consultar(self, mensajes, max_tokens=None) -> str:  # noqa: ARG002 - firma del proveedor
        self.mensajes.append(mensajes)
        return "## Diagnostico\nok\n## Sugerencias\n1. [alto] sigue con el modulo"

    def payload(self) -> str:
        """Todo lo que se habria enviado, como un unico texto."""
        return "\n".join(
            mensaje.get("content", "")
            for conversacion in self.mensajes
            for mensaje in conversacion
        )


@pytest.fixture()
def proyecto(sandbox):
    """Proyecto activado con secretos repartidos por el repo."""
    carpeta = sandbox / "proyectos" / "app-secretos"
    carpeta.mkdir(parents=True)
    (carpeta / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (carpeta / ".env").write_text(
        "DEEPSEEK_API_KEY={}\nGITHUB_TOKEN={}\nNOMBRE=app\n".format(CLAVE_FAKE, TOKEN_FAKE),
        encoding="utf-8",
    )
    (carpeta / "README.md").write_text(
        "# app\n\nclave: {}\ntoken: {}\n\n{}\n".format(CLAVE_FAKE, TOKEN_FAKE, PEM_FAKE),
        encoding="utf-8",
    )
    activacion.activar(ruta=carpeta)
    return "app-secretos"


def _arquitecto_espia(tmp_path):
    """Arquitecto real (misma ruta de codigo) con el proveedor interceptado."""
    base = configuracion.cargar()
    config = dataclasses.replace(
        base, persistir=False, ruta_historial=tmp_path / "historial.json"
    )
    espia = ProveedorEspia()
    return Arquitecto(config=config, proveedor=espia, historial=Historial(config)), espia


def test_ningun_secreto_del_repo_llega_al_proveedor(proyecto, tmp_path):
    motor, espia = _arquitecto_espia(tmp_path)
    mejora.informe_de_trabajo(
        proyecto, hechos="anadi el modulo", evidencia="pytest -q -> 3 passed"
    )

    mejora.sugerir_mejoras(proyecto, arquitecto=motor)

    carga = espia.payload()
    assert CLAVE_FAKE not in carga
    assert TOKEN_FAKE not in carga
    assert "MIIEvQIBADANBgkqhkiG9w0B" not in carga
    assert "***" in carga  # el saneador trabajo de verdad


def test_una_clave_colada_en_el_informe_no_sale_de_la_maquina(proyecto, tmp_path):
    motor, espia = _arquitecto_espia(tmp_path)
    mejora.informe_de_trabajo(
        proyecto,
        hechos="toque la config del cliente y deje la clave {}".format(CLAVE_FAKE),
        evidencia="pytest -q -> 1 passed (token usado: {})".format(TOKEN_FAKE),
    )

    mejora.sugerir_mejoras(proyecto, arquitecto=motor)

    carga = espia.payload()
    assert CLAVE_FAKE not in carga
    assert TOKEN_FAKE not in carga


def test_el_payload_sigue_llevando_el_contexto_util(proyecto, tmp_path):
    """Saneado no es censura: el stack y la evidencia siguen llegando."""
    motor, espia = _arquitecto_espia(tmp_path)
    mejora.informe_de_trabajo(
        proyecto, hechos="anadi el modulo", evidencia="pytest -q -> 3 passed"
    )

    mejora.sugerir_mejoras(proyecto, arquitecto=motor)

    carga = espia.payload()
    assert "app-secretos" in carga
    assert "3 passed" in carga
