"""Pruebas del contexto saneado que se manda al arquitecto (:mod:`contexto`).

El contexto es la unica ventana que el arquitecto tiene al repositorio: tiene
que ser real, acotado en tamano y **sin credenciales**. Estas pruebas fijan las
tres cosas.
"""

from __future__ import annotations

import contexto


def test_sanea_tacha_claves_de_los_patrones_conocidos():
    texto = "clave sk-abcdef1234567890abcd y token ghp_abcdefghijklmnopqrstuvwxyz01"

    limpio = contexto.sanea(texto)

    assert "sk-abcdef1234567890abcd" not in limpio
    assert "ghp_abcdefghijklmnopqrstuvwxyz01" not in limpio
    assert "***" in limpio


def test_sanea_tacha_asignaciones_sospechosas():
    limpio = contexto.sanea('API_KEY: "abcdef123456" y password=otraclave123')

    assert "abcdef123456" not in limpio
    assert "otraclave123" not in limpio


def test_sanea_quita_el_bom():
    assert contexto.sanea("\ufeffhola") == "hola"


def test_secretos_del_proyecto_lee_el_env_y_descarta_lo_publico(sandbox):
    carpeta = sandbox / "proyectos" / "app"
    carpeta.mkdir(parents=True)
    (carpeta / ".env").write_text(
        "MI_TOKEN=valor-secreto-123456\nNOMBRE=proyecto\nCLAVE_CORTA=abc\n", encoding="utf-8"
    )

    secretos = contexto.secretos_del_proyecto(carpeta)

    assert "valor-secreto-123456" in secretos
    assert "proyecto" not in secretos
    assert "abc" not in secretos


def test_contexto_del_repo_tacha_los_secretos_del_env(sandbox):
    carpeta = sandbox / "proyectos" / "app"
    carpeta.mkdir(parents=True)
    (carpeta / ".env").write_text("MI_TOKEN=valor-secreto-123456\n", encoding="utf-8")
    (carpeta / "README.md").write_text(
        "# app\n\nusa valor-secreto-123456 para conectar\n", encoding="utf-8"
    )

    texto = contexto.contexto_del_repo(carpeta)

    assert "valor-secreto-123456" not in texto
    assert "***SECRETO***" in texto


def test_contexto_del_repo_ignora_el_ruido(sandbox):
    carpeta = sandbox / "proyectos" / "app"
    (carpeta / "venv" / "Scripts").mkdir(parents=True)
    (carpeta / "venv" / "Scripts" / "python.exe").write_text("binario\n", encoding="utf-8")
    (carpeta / "src").mkdir()
    (carpeta / "src" / "main.py").write_text("print(1)\n", encoding="utf-8")

    texto = contexto.contexto_del_repo(carpeta)

    assert "src/main.py" in texto
    assert "venv" not in texto


def test_contexto_del_repo_respeta_el_tope(sandbox):
    carpeta = sandbox / "proyectos" / "app"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "README.md").write_text("x" * 5000, encoding="utf-8")

    texto = contexto.contexto_del_repo(carpeta, tope_bytes=500)

    assert len(texto) <= 600
    assert "recortado" in texto


def test_contexto_incluye_stack_y_comando_de_prueba(sandbox):
    carpeta = sandbox / "proyectos" / "app"
    carpeta.mkdir(parents=True, exist_ok=True)

    texto = contexto.contexto_del_repo(
        carpeta, {"stack": "python", "prueba": "python -m pytest -q", "marcador": "pyproject.toml"}
    )

    assert "stack: python" in texto
    assert "python -m pytest -q" in texto
