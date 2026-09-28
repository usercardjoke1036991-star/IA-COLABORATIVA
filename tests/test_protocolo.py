"""Pruebas del contrato con el PROGRAMADOR externo (:mod:`protocolo`)."""

from __future__ import annotations

from protocolo import (
    MARCADOR_ARCHIVO,
    extraer_archivos,
    formatear_respuesta_programador,
    pasos_sugeridos,
)

RESPUESTA = '''Listo: he creado los dos archivos que pediste.

### ARCHIVO: app/main.py
```python
def main():
    return "hola"
```

### ARCHIVO: docs/notas.md
```markdown
# Notas
```

### PASOS
1. Instala dependencias.
2. Ejecuta el script.
'''


def test_marcador_de_archivo_es_el_del_contrato():
    assert MARCADOR_ARCHIVO == "### ARCHIVO:"


def test_extraer_archivos_detecta_rutas_y_contenido():
    archivos = extraer_archivos(RESPUESTA)

    assert [ruta for ruta, _ in archivos] == ["app/main.py", "docs/notas.md"]
    assert archivos[0][1] == 'def main():\n    return "hola"\n'
    assert archivos[1][1] == "# Notas\n"


def test_extraer_archivos_normaliza_la_ruta_anunciada():
    texto = '### ARCHIVO:  `./src\\app.py`  \n```python\nx = 1\n```\n'

    assert extraer_archivos(texto) == [("src/app.py", "x = 1\n")]


def test_extraer_archivos_gana_la_ultima_version_de_cada_archivo():
    texto = (
        "### ARCHIVO: main.py\n```python\nviejo = True\n```\n\n"
        "### ARCHIVO: main.py\n```python\nnuevo = True\n```\n"
    )

    archivos = extraer_archivos(texto)

    assert len(archivos) == 1
    assert archivos[0] == ("main.py", "nuevo = True\n")


def test_extraer_archivos_ignora_bloques_sin_cerca_de_cierre():
    texto = "### ARCHIVO: roto.py\nesto no lleva cerca\n"

    assert extraer_archivos(texto) == []


def test_extraer_archivos_tolera_texto_vacio():
    assert extraer_archivos("") == []
    assert extraer_archivos(None) == []


def test_pasos_sugeridos_devuelve_el_bloque_final():
    pasos = pasos_sugeridos(RESPUESTA)

    assert pasos.startswith("1. Instala dependencias.")
    assert "2. Ejecuta el script." in pasos


def test_pasos_sugeridos_vacio_cuando_no_hay_bloque():
    assert pasos_sugeridos("solo codigo, sin pasos") == ""


def test_formatear_respuesta_programador_resume_los_archivos():
    salida = formatear_respuesta_programador(
        RESPUESTA, turno=3, proveedor="mock", modelo="modelo-x", archivos=extraer_archivos(RESPUESTA)
    )

    assert "PROGRAMADOR EXTERNO" in salida
    assert "modelo-x" in salida
    assert "turno: 3" in salida
    assert "app/main.py" in salida
    assert "Archivos entregados (2)" in salida


def test_formatear_respuesta_programador_avisa_sin_archivos():
    salida = formatear_respuesta_programador(
        "no hay bloques", turno=1, proveedor="mock", modelo="m", archivos=[]
    )

    assert "AVISO" in salida
