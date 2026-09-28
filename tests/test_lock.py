"""Pruebas del lock de dependencias que usa el CI.

El CI instala con ``--only-binary :all: --require-hashes -r requirements.lock.txt``
(cadena de suministro: reglas ``githubactions:S8541`` y ``:S8544``). Si el lock se
rompe -una dependencia sin pin, una linea sin hash, o el paquete
``pywin32`` sin su marcador de plataforma- el job de Linux falla al instalar.
Aqui se comprueba antes de subir y sin necesidad de red.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LOCK = RAIZ / "requirements.lock.txt"
WORKFLOW = RAIZ / ".github" / "workflows" / "ci.yml"

#: ``paquete[extra]==version ; marcador`` al principio de un bloque de continuacion.
DEPENDENCIA = re.compile(r"^([A-Za-z0-9._-]+)(\[[^\]]+\])?==([^ ;\\]+)(\s*;.+\S)?$")
HASH = re.compile(r"--hash=sha256:[0-9a-f]{64}")

#: Dependencias que el proyecto usa de verdad (requirements.txt + -dev).
ESPERADAS = {"mcp", "requests", "pytest", "pytest-cov", "pyyaml", "python-dotenv"}


def _paquetes() -> dict:
    """Devuelve ``{nombre: {'marcador': str | None, 'hashes': int}}`` del lock."""
    paquetes = {}
    actual = None
    for linea in LOCK.read_text(encoding="utf-8").splitlines():
        texto = linea.strip()
        if not texto or texto.startswith("#"):
            continue
        if not linea[0].isspace() and "==" in linea:
            encontrado = DEPENDENCIA.match(texto.rstrip("\\ ").strip())
            assert encontrado, "linea de dependencia ilegible en el lock: {}".format(linea)
            actual = encontrado.group(1).lower()
            paquetes[actual] = {"marcador": encontrado.group(4) or None, "hashes": 0}
        elif actual is not None:
            paquetes[actual]["hashes"] += len(HASH.findall(linea))
    return paquetes


# --------------------------------------------------------------------------
# Contrato con el CI
# --------------------------------------------------------------------------
def test_el_ci_instala_el_lock_con_hashes():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert LOCK.exists()
    assert "requirements.lock.txt" in workflow
    assert "--require-hashes" in workflow
    assert "--only-binary :all:" in workflow


def test_el_lock_prohibe_los_sdist():
    assert "--only-binary :all:" in LOCK.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Contenido del lock
# --------------------------------------------------------------------------
def test_todas_las_dependencias_van_pinneadas_con_hash():
    paquetes = _paquetes()

    assert len(paquetes) > 20
    sin_hash = sorted(nombre for nombre, datos in paquetes.items() if not datos["hashes"])
    assert not sin_hash, "dependencias sin hash: {}".format(", ".join(sin_hash))


def test_el_lock_cubre_las_dependencias_del_proyecto():
    paquetes = _paquetes()

    faltan = sorted(ESPERADAS - set(paquetes))
    assert not faltan, "dependencias sin pin en el lock: {}".format(", ".join(faltan))


def test_los_paquetes_de_una_sola_plataforma_llevan_marcador():
    """``pywin32`` solo existe para Windows: sin marcador el job de ubuntu falla."""
    paquetes = _paquetes()

    marcador = paquetes["pywin32"]["marcador"]
    assert marcador, (
        "pywin32 necesita '; sys_platform == \"win32\"' o el CI de Linux no instala"
    )
    assert "win32" in marcador
