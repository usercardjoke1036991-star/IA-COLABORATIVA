"""Catalogo de plantillas (scaffolds) que la fabrica sabe generar.

Cada plantilla es una lista de archivos con su contenido. Los marcadores
``__NOMBRE__``, ``__DESCRIPCION__`` y ``__PAQUETE__`` se sustituyen al crear el
proyecto, asi que las plantillas pueden contener codigo Python con llaves sin
que nada se rompa (no se usa ``str.format``).

Para anadir una plantilla nueva basta con registrar otra :class:`Plantilla` en
``PLANTILLAS``: la fabrica y las herramientas MCP la ofrecen automaticamente.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List

import rutas


@dataclass
class Plantilla:
    """Conjunto de archivos y notas que definen un andamiaje de proyecto."""

    clave: str
    titulo: str
    descripcion: str
    archivos: Dict[str, str] = field(default_factory=dict)
    notas: List[str] = field(default_factory=list)


PLANTILLAS: Dict[str, Plantilla] = {}


def registrar(plantilla: Plantilla) -> Plantilla:
    PLANTILLAS[plantilla.clave] = plantilla
    return plantilla


# --------------------------------------------------------------------------
# Piezas compartidas por varias plantillas
# --------------------------------------------------------------------------
GITIGNORE_PYTHON = """# Entornos virtuales
venv/
.venv/
env/

# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.mypy_cache/

# Secretos y estado local
.env
*.log
datos/
"""

README_BASE = r"""# __NOMBRE__

__DESCRIPCION__

Generado el __FECHA__ con la fabrica de proyectos (plantillas: __PLANTILLAS__).

## Puesta en marcha

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Estructura

- `src/` o `app/`: codigo de la aplicacion.
- `tests/` o `pruebas/`: pruebas automaticas.
- `docs/`: notas y decisiones tecnicas.

## Flujo de trabajo

1. Este proyecto nacio de una idea planteada en la plantilla orquestadora.
2. El ARQUITECTO (IA externa) definio el plan; el PROGRAMADOR lo implemento.
3. Cada bloque de trabajo se cierra con un informe de progreso.

## Credenciales y puntos de parada

La IA deja preparados los campos y **para** cuando necesita un dato tuyo:

1. Copia `.env.example` a `.env` (el `.env` no se sube a git).
2. Rellena solo las variables que te pida: en el chat vera el aviso
   `BLOQUEO: CREDENCIALES` con la lista exacta de variables y donde
   conseguirlas.
3. Responde "listo" y el trabajo continua desde ese mismo punto.

Nunca se inventan claves ni se dejan simulaciones silenciosas.

## Orquestacion con IA (Arquitecto externo + IDE)

Este proyecto nace enchufado a la fabrica de IA colaborativa:

- `.clinerules`, `.cursorrules` y `.cursor/rules/arquitecto.mdc`: reglas que
  obligan a la IA del IDE a consultar al ARQUITECTO antes de programar, a
  ejecutar las pruebas de verdad, a auto-repararse y a pararse si faltan
  credenciales.
- `AGENTS.md`: el mismo resumen en formato neutro.
- `.cursor/mcp.json`: registro del servidor MCP `arquitecto-externo` que
  gobierna el loop (el proyecto se trabaja con `proyecto="__NOMBRE__"`).

## Estado

- [ ] Primer alcance funcional
- [ ] Pruebas en verde
- [ ] Documentacion de uso
"""


def _nombre_paquete(nombre: str) -> str:
    """Nombre de paquete Python valido derivado del nombre del proyecto."""
    limpio = rutas.normalizar_nombre(nombre).replace("-", "_").replace(".", "_")
    if limpio[:1].isdigit():
        limpio = "p" + limpio
    return re.sub(r"_+", "_", limpio) or "app"


def _sustituir(texto: str, nombre: str, descripcion: str, paquete: str, claves: List[str]) -> str:
    """Reemplaza los marcadores de la plantilla por los datos del proyecto."""
    return (
        texto.replace("__NOMBRE__", nombre)
        .replace("__DESCRIPCION__", descripcion or "Proyecto generado por la fabrica de IA.")
        .replace("__PAQUETE__", paquete)
        .replace("__FECHA__", date.today().isoformat())
        .replace("__PLANTILLAS__", ", ".join(claves) or "base")
    )


# --------------------------------------------------------------------------
# Orquestacion: todo proyecto nuevo nace enchufado al Arquitecto externo
# --------------------------------------------------------------------------
def _ruta_posix(ruta) -> str:
    """Ruta con barras normales: JSON valido y sin escapes rotos."""
    return Path(ruta).as_posix()


def _interprete_mcp() -> str:
    """Interprete que arranca el servidor MCP (el venv de la fabrica si existe).

    El servidor MCP necesita las dependencias del proyecto orquestador, asi que
    se prefiere el python de su ``venv`` y solo se cae a ``python`` del PATH si
    ese entorno todavia no existe.
    """
    raiz = rutas.raiz_proyecto()
    piezas = (
        ("venv", "Scripts", "python.exe")
        if os.name == "nt"
        else ("venv", "bin", "python")
    )
    candidato = raiz.joinpath(*piezas)
    return _ruta_posix(candidato) if candidato.exists() else "python"


def _servidor_mcp() -> str:
    """Ruta del servidor MCP de la fabrica que gobierna la orquestacion."""
    return _ruta_posix(rutas.raiz_proyecto() / "arquitecto_mcp.py")


#: Reglas que recibe la IA del IDE dentro de cada proyecto nuevo.
REGLAS_ORQUESTACION = r"""# Orquestacion: IA colaborativa (Arquitecto externo + fabrica)

Proyecto: __NOMBRE__ (slug de la fabrica). __DESCRIPCION__

Eres el PROGRAMADOR PRINCIPAL: la IA del IDE que escribe TODO el codigo de este
proyecto. Existe ademas una IA externa, el ARQUITECTO (DeepSeek), expuesta como
las herramientas MCP del servidor `arquitecto-externo`, y una FABRICA DE
PROYECTOS que gestiona carpetas, git y GitHub. Reparto CERRADO de papeles: el
ARQUITECTO solo planifica, revisa y orquesta (no escribe codigo ni ejecuta
nada); TU escribes TODO el codigo y lo ejecutas en esta maquina.

Trabaja SIEMPRE contra la fabrica indicando el proyecto:

- `proyecto="__NOMBRE__"` en todas las herramientas de archivos y de git.
- Rutas relativas al proyecto (`src/...`, `tests/...`), nunca absolutas.

## 1. Antes de programar: pregunta al Arquitecto

1. Situate: `ver_proyecto(proyecto="__NOMBRE__")` (no gasta tokens).
2. Llama a `consultar_arquitecto` con la peticion LITERAL del usuario en
   `idea_del_usuario` y el contexto real en `contexto_del_codigo` (stack,
   estructura, restricciones). Nunca metas credenciales ahi.
3. Sigue su plan paso a paso, sin inventar pasos extra. Si algo es inviable,
   dilo con `reportar_progreso` y el `bloqueo` concreto en vez de improvisar.
4. Cuenta al usuario en 2-3 lineas que consultaste al arquitecto y que propone.

## 2. Si faltan credenciales: PARA y pide (nunca las inventes)

Cuando una tarea necesite una clave, token, cadena de conexion o un servicio
externo (API, base de datos, cuenta, dominio, tarjeta...):

1. NO inventes valores, NO dejes mocks silenciosos, NO des la tarea por hecha.
2. Deja el enganche ya programado y los campos VACIOS preparados:
   - `.env.example`: variable documentada (esto si se versiona).
   - `.env`: `NOMBRE_VARIABLE=` (vacio; `.env` nunca se sube a git).
3. Commit del trabajo parcial (`commit_proyecto`) y PARA el loop con este
   formato exacto, para que el usuario solo tenga que rellenar y decir "listo":

   BLOQUEO: CREDENCIALES
   Necesito que rellenes en `.env`:
   - `VARIABLE_1` -> donde se consigue (URL exacta) y formato esperado.
   - `VARIABLE_2` -> ...
   Cuando esten puestas, dime "listo" y continuo justo desde aqui.

4. Registralo tambien en `reportar_progreso(bloqueo="CREDENCIALES: ...")`.
5. Al recibirlas: no las repitas en tu respuesta ni las mandes al arquitecto;
   leelas del `.env` y continua.

## 3. Ejecutar y comprobar (tienes acceso a esta maquina)

- Prepara el entorno si hace falta: `preparar_entorno(proyecto="__NOMBRE__")`.
- Ejecuta comandos y pruebas de verdad en la terminal, por ejemplo:
  `venv/Scripts/python.exe -m pytest -q` (o el comando del stack).
- Pide confirmacion al usuario antes de acciones destructivas o irreversibles
  (borrados masivos, `git push --force`, instalar software del sistema).
- No anuncies un resultado sin haberlo ejecutado: pega la salida real.

## 4. El codigo y la ejecucion son TUYOS (delegar esta prohibido)

El reparto no se negocia: el ARQUITECTO piensa (planifica, revisa y orquesta) y
TU construyes (escribes los archivos y ejecutas). Por tanto:

- PROHIBIDO llamar a `pedir_codigo_al_programador`,
  `aplicar_codigo_del_programador` y `corregir_con_el_programador`: son el modo
  alternativo del orquestador de consola (`orquestador.py --modo interno`), no
  el flujo del IDE. No las uses nunca.
- Escribes tu, con `escribir_archivo` (el archivo COMPLETO, no parches), y
  ejecutas tu las pruebas.
- Si el plan del arquitecto sugiere que otro escriba el codigo, ignora esa parte
  y escribelo tu.

## 5. Auto-reparacion con tus propias manos

Si una prueba o un comando falla:

1. Lee la traza COMPLETA (no un resumen): no adivines.
2. Corrige el archivo tu mismo con `escribir_archivo` y vuelve a ejecutar
   `venv/Scripts/python.exe -m pytest -q`, pegando la salida real.
3. Si dudas del criterio, pide opinion al arquitecto (`consultar_arquitecto`) o
   reporta con `reportar_progreso(bloqueo=<traza>)`: el te orienta, pero el
   codigo lo escribes TU.
4. Tras 2-3 intentos en rojo, para y reporta el `bloqueo` con la traza exacta.

## 6. Bucle de mejora continua (informe -> sugerencias -> implementar)

Esto es lo que hace que el proyecto mejore solo, ronda a ronda. Tras CADA bloque
de trabajo (no solo al final del plan):

1. `informe_de_trabajo(proyecto="__NOMBRE__", hechos=..., evidencia=...,
   sugerencias_propias=..., archivos_tocados=...)`:
   - `hechos`: que implementaste, sin adornos.
   - `evidencia`: el comando exacto y su salida REAL (pega la traza tal cual).
   - `sugerencias_propias`: lo que TU ves mejorable, priorizado.
2. `sugerir_mejoras(proyecto="__NOMBRE__")`: el ARQUITECTO lee tu informe, el
   contexto real del repositorio y la memoria de la sesion, y devuelve el
   siguiente lote priorizado (queda escrito en `SUGERENCIAS.md`).
3. Implementa esas mejoras, ejecuta las pruebas de verdad y vuelve al paso 1.
4. El bucle se corta cuando `sugerir_mejoras` diga `TAREA TERMINADA` /
   `[[ARQUITECTO: FIN]]`, cuando el usuario escriba PARAR, o cuando se agote
   `ARQUITECTO_MAX_RONDAS` (el servidor lo controla solo).
5. Antes de parar definitivamente: entrega al usuario el informe final
   (`INFORME.md` y `SUGERENCIAS.md`) y como probarlo.

Nunca inventes evidencia: si una prueba falla, pega el fallo real y corrigelo.

## 7. Loop continuo hasta cerrar la tarea

Por cada bloque de trabajo:

6. `commit_proyecto(proyecto="__NOMBRE__", mensaje="feat: ...")`.
7. `reportar_progreso(resumen_de_lo_hecho=..., prompt_original=...,
   archivos_tocados=..., bloqueo=...)`.
8. Aplica los siguientes pasos que devuelva el arquitecto y repite 6-8 mientras
   diga `estado del loop: EN CURSO`.
9. Para cuando diga `estado del loop: TAREA TERMINADA` (o salga
   `[[ARQUITECTO: FIN]]`): verifica los criterios de aceptacion, ejecuta la
   verificacion final y entrega al usuario el resumen y como probarlo.

## 8. Publicar (solo si el usuario lo pide)

`publicar_en_github(proyecto="__NOMBRE__")` necesita `gh` instalado y con sesion
(`gh auth login`). Si no esta, explica al usuario como instalarlo.

## Prohibiciones

- No llames al arquitecto por cambios triviales (typos, formato, imports).
- No incluyas claves, tokens ni secretos en el contexto que le envies.
- No escribas fuera de `proyectos/` ni dentro de `.git`.
- No delegues el codigo ni la ejecucion en otro modelo: son tuyos (seccion 4).
- No dejes una tarea a medias sin reportar el bloqueo.
"""


#: Resumen neutro del mismo protocolo (lo leen Cursor, Cline y otras IAs).
AGENTS_MD = r"""# __NOMBRE__ - contexto para agentes (IA colaborativa)

__DESCRIPCION__

Este proyecto lo mantiene un equipo de dos IAs:

- **ARQUITECTO externo** (herramientas MCP `arquitecto-externo`): solo planifica,
  revisa y orquesta. No escribe codigo ni ejecuta nada.
- **PROGRAMADOR** (la IA del IDE, tu): escribe TODO el codigo y lo ejecuta; es la
  unica que toca los archivos. Delegar en otro modelo esta prohibido.

Las reglas completas estan en `.clinerules` (Cline) y en `.cursorrules` /
`.cursor/rules/arquitecto.mdc` (Cursor). Resumen operativo:

1. Si la carpeta no tiene `.clinerules` ni `.cursor/rules/arquitecto.mdc`, llama
   primero a `activar_proyecto` (registra la carpeta y te devuelve el kit de
   arranque con el contexto real del repositorio).
2. Antes de una tarea nueva o un cambio amplio: `consultar_arquitecto`.
3. Trabaja siempre con `proyecto="__NOMBRE__"` y rutas relativas.
4. Si falta una credencial: deja la variable vacia en `.env`, PARA y pide el
   valor al usuario con el formato `BLOQUEO: CREDENCIALES`. Nunca inventes
   claves ni dejes mocks silenciosos.
5. El arquitecto decide y la IA del IDE construye; ante un error real corrige
   ella misma con `escribir_archivo` y repite las pruebas (no delega el codigo:
   `corregir_con_el_programador` esta prohibido en el IDE).
6. Cierra cada bloque con `commit_proyecto` + `reportar_progreso` y continua
   mientras el loop diga `estado del loop: EN CURSO`.
7. Bucle de mejora continua: tras cada bloque, `informe_de_trabajo` (hechos +
   evidencia real + tus sugerencias) y despues `sugerir_mejoras`, que devuelve
   el siguiente lote priorizado del arquitecto. Repite hasta que el bucle cierre
   con `[[ARQUITECTO: FIN]]`, el usuario diga PARAR o se agoten las rondas.
8. Politica de rutas: al tocar contenido que **ya existe** la carpeta se pregunta
   a `base_de_proyecto()` (la ruta de la FICHA, que puede ser cualquier carpeta
   activada); `rutas.ruta_de_proyecto()` (que asume `proyectos/<slug>`) se reserva
   para CREAR proyectos nuevos. Las herramientas de archivos nunca salen de la
   carpeta del proyecto (`confinar_a_base`), ni al leer, ni al buscar, ni al
   listar: ni `..`, ni un enlace que apunte fuera.
"""

#: Plantilla de credenciales: campos vacios listos para rellenar.
ENV_EJEMPLO = r"""# Credenciales y ajustes locales de __NOMBRE__
# Copia este archivo a .env y rellena SOLO lo que necesites (el .env real no se
# sube a git).
#
# Regla del equipo: si falta una credencial, la IA deja aqui la variable vacia,
# PARA el trabajo y pide el valor al usuario. Nunca se inventan claves.

# --- Modelos (solo si el proyecto llama a un LLM) ---
DEEPSEEK_API_KEY=
OPENROUTER_API_KEY=
OPENAI_API_KEY=

# --- Servicios del proyecto (descomenta y anade los tuyos) ---
# DATABASE_URL=
# API_BASE_URL=
# TELEGRAM_BOT_TOKEN=

# --- Orquestacion (las lee el servidor MCP de la fabrica) ---
ARQUITECTO_PROVIDER=deepseek
ARQUITECTO_MODEL=deepseek-reasoner
ARQUITECTO_EJECUTOR_MODEL=deepseek-chat
# ARQUITECTO_MAX_TOKENS=8192   # sube el tope de salida si usas un modelo "reasoner"
# ARQUITECTO_MAX_RONDAS=10     # tope de rondas del bucle de mejora continua
# ARQUITECTO_MOCK=true   # modo simulado: sin API key y sin coste (solo pruebas)
"""


def archivos_de_orquestacion(
    nombre: str, descripcion: str, paquete: str, claves: List[str]
) -> Dict[str, str]:
    """Archivos comunes que enchufan un proyecto nuevo al Arquitecto externo.

    Se anaden a cualquier combinacion de plantillas (salvo que la propia
    plantilla ya defina ese archivo, en cuyo caso gana la plantilla).
    """
    cuerpo = _sustituir(REGLAS_ORQUESTACION, nombre, descripcion, paquete, claves)
    mdc = (
        "---\n"
        "description: Orquestacion con el Arquitecto externo (loop de IA colaborativa)\n"
        "globs:\n"
        "alwaysApply: true\n"
        "---\n\n"
    ) + cuerpo
    registro = {
        "mcpServers": {
            "arquitecto-externo": {
                "command": _interprete_mcp(),
                "args": [_servidor_mcp()],
                "env": {"ARQUITECTO_LOG": "INFO"},
            }
        }
    }
    return {
        ".clinerules": cuerpo,
        ".cursorrules": cuerpo,
        ".cursor/rules/arquitecto.mdc": mdc,
        ".cursor/mcp.json": json.dumps(registro, indent=2, ensure_ascii=False) + "\n",
        "AGENTS.md": _sustituir(AGENTS_MD, nombre, descripcion, paquete, claves),
        ".env.example": _sustituir(ENV_EJEMPLO, nombre, descripcion, paquete, claves),
    }


# --------------------------------------------------------------------------
# Plantilla: vacio
# --------------------------------------------------------------------------
registrar(
    Plantilla(
        clave="vacio",
        titulo="Proyecto vacio",
        descripcion="Solo la base: README, .gitignore y carpetas de trabajo.",
        archivos={
            "docs/decisiones.md": "# Decisiones tecnicas\n\n- (pendiente)\n",
            "src/.gitkeep": "",
            "tests/.gitkeep": "",
        },
        notas=["Util cuando el arquitecto definira la estructura desde cero."],
    )
)


# --------------------------------------------------------------------------
# Plantilla: python
# --------------------------------------------------------------------------
registrar(
    Plantilla(
        clave="python",
        titulo="Python (paquete + pytest)",
        descripcion="Paquete instalable en src/, punto de entrada y pruebas con pytest.",
        archivos={
            "src/__PAQUETE__/__init__.py": '''"""Paquete __NOMBRE__."""

__version__ = "0.1.0"
''',
            "src/__PAQUETE__/main.py": '''"""Punto de entrada de __NOMBRE__.

__DESCRIPCION__
"""

from __future__ import annotations

import argparse
import logging

log = logging.getLogger("__PAQUETE__")


def ejecutar(entrada: str) -> str:
    """Logica principal. Sustituye esto por el objetivo real del proyecto."""
    if not entrada or not entrada.strip():
        raise ValueError("La entrada no puede estar vacia.")
    return "procesado: {}".format(entrada.strip())


def main(argv=None) -> int:
    analizador = argparse.ArgumentParser(prog="__PAQUETE__")
    analizador.add_argument("texto", nargs="?", default="hola", help="texto de entrada")
    argumentos = analizador.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(ejecutar(argumentos.texto))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
            "tests/test___PAQUETE__.py": '''"""Pruebas de humo de __NOMBRE__."""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

from __PAQUETE__.main import ejecutar  # noqa: E402


def test_camino_feliz() -> None:
    assert ejecutar("dato") == "procesado: dato"


def test_entrada_vacia() -> None:
    try:
        ejecutar("  ")
    except ValueError:
        return
    raise AssertionError("se esperaba ValueError con entrada vacia")
''',
            "requirements.txt": "pytest>=8.0\n",
            "pyproject.toml": '''[project]
name = "__NOMBRE__"
version = "0.1.0"
description = "__DESCRIPCION__"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
''',
            "scripts/ejecutar.ps1": r'''# Atajo: ejecuta el proyecto con el interprete del entorno virtual.
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
& "$raiz\venv\Scripts\python.exe" -m __PAQUETE__.main @args
''',
        },
        notas=[
            "Instala en modo editable:  pip install -e .",
            r"Pruebas:  venv\Scripts\python.exe -m pytest -q",
        ],
    )
)


# --------------------------------------------------------------------------
# Plantilla: flask
# --------------------------------------------------------------------------
registrar(
    Plantilla(
        clave="flask",
        titulo="Flask (API + plantilla HTML)",
        descripcion="Aplicacion Flask con endpoint de salud, index y pruebas.",
        archivos={
            "app.py": '''"""Aplicacion Flask de __NOMBRE__.

__DESCRIPCION__
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html", nombre=os.getenv("NOMBRE_APP", "__NOMBRE__"))


@app.get("/salud")
def salud():
    return jsonify({"estado": "ok", "servicio": "__NOMBRE__", "version": "0.1.0"})


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("DEBUG", "1") == "1",
    )
''',
            "templates/index.html": '''<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <title>__NOMBRE__</title>
    <style>
      body { font-family: system-ui, sans-serif; margin: 4rem; line-height: 1.6; }
      code { background: #f2f2f2; padding: .2rem .4rem; border-radius: 4px; }
    </style>
  </head>
  <body>
    <h1>{{ nombre }}</h1>
    <p>__DESCRIPCION__</p>
    <p>Comprueba <code>/salud</code> para ver el estado del servicio.</p>
  </body>
</html>
''',
            "tests/test_app.py": '''"""Pruebas de la API Flask."""

from app import app


def test_index() -> None:
    cliente = app.test_client()
    assert cliente.get("/").status_code == 200


def test_salud() -> None:
    cliente = app.test_client()
    respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.get_json()["estado"] == "ok"
''',
            "requirements.txt": "flask>=3.0\npytest>=8.0\n",
            ".env.example": '''# Copia a .env y ajusta si hace falta.
HOST=127.0.0.1
PORT=5000
DEBUG=1
''',
        },
        notas=[r"Arranca con:  venv\Scripts\python.exe app.py"],
    )
)


# --------------------------------------------------------------------------
# Plantilla: fastapi
# --------------------------------------------------------------------------
registrar(
    Plantilla(
        clave="fastapi",
        titulo="FastAPI (API tipada + uvicorn)",
        descripcion="API con modelos Pydantic, endpoint de salud y pruebas con TestClient.",
        archivos={
            "app/__init__.py": "",
            "app/main.py": '''"""API FastAPI de __NOMBRE__.

__DESCRIPCION__
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="__NOMBRE__", version="0.1.0")


class Peticion(BaseModel):
    """Entrada tipada del endpoint principal."""

    texto: str = Field(min_length=1, description="Texto a procesar")


class Respuesta(BaseModel):
    resultado: str
    longitud: int


@app.get("/salud")
def salud() -> dict:
    return {"estado": "ok", "servicio": "__NOMBRE__"}


@app.post("/procesar", response_model=Respuesta)
def procesar(peticion: Peticion) -> Respuesta:
    if not peticion.texto.strip():
        raise HTTPException(status_code=422, detail="El texto no puede estar vacio.")
    return Respuesta(resultado=peticion.texto.strip().upper(), longitud=len(peticion.texto))
''',
            "tests/test_api.py": '''"""Pruebas de la API FastAPI."""

from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


def test_salud() -> None:
    assert cliente.get("/salud").json()["estado"] == "ok"


def test_procesar() -> None:
    respuesta = cliente.post("/procesar", json={"texto": "hola"})
    assert respuesta.status_code == 200
    assert respuesta.json()["resultado"] == "HOLA"
''',
            "requirements.txt": "fastapi>=0.110\nuvicorn[standard]>=0.29\nhttpx>=0.27\npytest>=8.0\n",
            "scripts/servidor.ps1": r'''# Levanta el servidor de desarrollo de la API.
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
& "$raiz\venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
''',
        },
        notas=["Documentacion automatica en http://127.0.0.1:8000/docs"],
    )
)


# --------------------------------------------------------------------------
# Plantilla: web3
# --------------------------------------------------------------------------
registrar(
    Plantilla(
        clave="web3",
        titulo="Web3 (RPC + vigilante de bloques)",
        descripcion="Cliente JSON-RPC, lectura de saldo y vigilante de bloques con reintentos.",
        archivos={
            "src/__PAQUETE__/__init__.py": "",
            "src/__PAQUETE__/cliente.py": '''"""Conexion Web3 y utilidades basicas.

Lee la configuracion de variables de entorno (.env):

    RPC_URL     endpoint JSON-RPC (Infura, Alchemy, nodo local...)
    DIRECCION   direccion por defecto para consultar saldo
"""

from __future__ import annotations

import logging
import os

from web3 import Web3

log = logging.getLogger(__name__)


def conectar(url: str | None = None) -> Web3:
    """Devuelve una conexion Web3 ya validada."""
    endpoint = url or os.getenv("RPC_URL", "")
    if not endpoint:
        raise RuntimeError("Falta RPC_URL en el entorno (.env).")
    w3 = Web3(Web3.HTTPProvider(endpoint, request_kwargs={"timeout": 20}))
    if not w3.is_connected():
        raise RuntimeError("No se pudo conectar al nodo: {}".format(endpoint))
    log.info("Conectado al nodo. Bloque actual: %s", w3.eth.block_number)
    return w3


def saldo(w3: Web3, direccion: str | None = None) -> float:
    """Saldo en ether de una direccion."""
    objetivo = direccion or os.getenv("DIRECCION", "")
    if not objetivo:
        raise ValueError("Falta DIRECCION (parametro o variable de entorno).")
    wei = w3.eth.get_balance(Web3.to_checksum_address(objetivo))
    return float(w3.from_wei(wei, "ether"))
''',
            "src/__PAQUETE__/vigilante.py": '''"""Vigilante de bloques: sondea la cadena y avisa de cada bloque nuevo.

Pensado para dejarlo corriendo en bucle; maneja fallos de red con espera
progresiva para no martillear el nodo.
"""

from __future__ import annotations

import argparse
import logging
import time

from .cliente import conectar

log = logging.getLogger(__name__)


def vigilar(intervalo: float = 12.0, max_bloques: int = 0) -> int:
    """Sondea la cadena y registra cada bloque nuevo. Devuelve los procesados."""
    w3 = conectar()
    ultimo = w3.eth.block_number
    procesados = 0
    espera = intervalo

    log.info("Vigilando desde el bloque %s (cada %.1fs).", ultimo, intervalo)
    while max_bloques == 0 or procesados < max_bloques:
        try:
            actual = w3.eth.block_number
            if actual > ultimo:
                for numero in range(ultimo + 1, actual + 1):
                    bloque = w3.eth.get_block(numero)
                    log.info(
                        "Bloque %s | %s tx | %s",
                        numero,
                        len(bloque.transactions),
                        bloque.timestamp,
                    )
                    procesados += 1
                ultimo = actual
            espera = intervalo
        except Exception as exc:  # red caida, rate limit, nodo reiniciando...
            espera = min(espera * 2, 120)
            log.warning("Fallo al leer el bloque (%s). Reintento en %.0fs.", exc, espera)
        time.sleep(espera)
    return procesados


def main(argv=None) -> int:
    analizador = argparse.ArgumentParser(prog="vigilante")
    analizador.add_argument("--intervalo", type=float, default=12.0)
    analizador.add_argument("--max-bloques", type=int, default=0)
    argumentos = analizador.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    procesados = vigilar(argumentos.intervalo, argumentos.max_bloques)
    print("Bloques procesados: {}".format(procesados))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
            "requirements.txt": "web3>=6.15\npython-dotenv>=1.0\n",
            ".env.example": "# Copia a .env y rellena tus valores.\nRPC_URL=\nDIRECCION=\n",
        },
        notas=[
            "Configura RPC_URL en el .env antes de conectar.",
            "Prueba con:  python -m __PAQUETE__.vigilante --max-bloques 1",
        ],
    )
)


# --------------------------------------------------------------------------
# Plantilla: playwright
# --------------------------------------------------------------------------
registrar(
    Plantilla(
        clave="playwright",
        titulo="Playwright (navegador + pytest)",
        descripcion="Pruebas de interfaz con Chromium, capturas ante fallo y utilidades.",
        archivos={
            "pruebas/test_navegador.py": '''"""Pruebas de interfaz con Playwright (Chromium en modo headless)."""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_la_pagina_carga(page: Page, base_url: str) -> None:
    page.goto(base_url)
    expect(page).to_have_title(lambda titulo: titulo is not None and titulo != "")


def test_busqueda_devuelve_resultados(page: Page, base_url: str) -> None:
    page.goto(base_url)
    if page.locator("input[type=search], input[name=q]").count() == 0:
        return  # la pagina objetivo no tiene buscador: nada que comprobar
    page.locator("input[type=search], input[name=q]").first.fill("prueba")
    page.keyboard.press("Enter")
    expect(page).not_to_have_url(base_url)
''',
            "pruebas/conftest.py": '''"""Fixtures compartidas: navegador, contexto y captura ante fallo."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

CAPTURAS = Path(__file__).resolve().parent.parent / "capturas"


@pytest.fixture(scope="session")
def base_url() -> str:
    """URL objetivo (variable de entorno BASE_URL o un valor local por defecto)."""
    return os.getenv("BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="session")
def navegador():
    with sync_playwright() as gestor:
        navegador = gestor.chromium.launch(headless=os.getenv("HEADLESS", "1") == "1")
        yield navegador
        navegador.close()


@pytest.fixture()
def page(navegador, request):
    contexto = navegador.new_context(viewport={"width": 1280, "height": 800})
    pagina = contexto.new_page()
    yield pagina
    if getattr(request.node, "rep_call", None) and request.node.rep_call.failed:
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        pagina.screenshot(path=str(CAPTURAS / "{}.png".format(request.node.name)))
    contexto.close()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    resultado = yield
    informe = resultado.get_result()
    setattr(item, "rep_{}".format(informe.when), informe)
''',
            "requirements.txt": "playwright>=1.44\npytest>=8.0\n",
            "scripts/instalar_navegadores.ps1": r'''# Instala el navegador Chromium que usa Playwright.
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
& "$raiz\venv\Scripts\python.exe" -m playwright install chromium
''',
        },
        notas=[
            r"Primero instala el navegador:  powershell -File scripts\instalar_navegadores.ps1",
            r"Ejecuta las pruebas con:  venv\Scripts\python.exe -m pytest pruebas -q",
        ],
    )
)


# --------------------------------------------------------------------------
# Plantilla: mcp
# --------------------------------------------------------------------------
registrar(
    Plantilla(
        clave="mcp",
        titulo="Servidor MCP (FastMCP)",
        descripcion="Servidor MCP por stdio con dos herramientas de ejemplo y registro automatico.",
        archivos={
            "servidor.py": '''"""Servidor MCP de __NOMBRE__.

__DESCRIPCION__

Arranca por stdio (lo que usan Cursor y Cline):
    python servidor.py
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

servidor = FastMCP("__NOMBRE__")


@servidor.tool()
def saludar(nombre: str) -> str:
    """Devuelve un saludo personalizado.

    Args:
        nombre: Nombre de la persona a saludar.
    """
    return "Hola, {}.".format((nombre or "mundo").strip() or "mundo")


@servidor.tool()
def sumar(a: float, b: float) -> str:
    """Suma dos numeros y devuelve el resultado con su comprobacion.

    Args:
        a: Primer sumando.
        b: Segundo sumando.
    """
    total = a + b
    return "{} + {} = {}".format(a, b, total)


if __name__ == "__main__":
    servidor.run(transport="stdio")
''',
            "requirements.txt": "mcp>=1.2\n",
            "scripts/registrar_mcp.ps1": r'''# Registra este servidor en Cursor (.cursor/mcp.json) y en Cline (si esta instalado).
$raiz = Split-Path -Parent $PSScriptRoot
$py = Join-Path $raiz "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }
$servidor = Join-Path $raiz "servidor.py"
$nombre = "__NOMBRE__"

$cursor = Join-Path $raiz ".cursor"
New-Item -ItemType Directory -Force -Path $cursor | Out-Null
$json = @{ mcpServers = @{ $nombre = @{ command = $py; args = @($servidor) } } } | ConvertTo-Json -Depth 6
$json | Set-Content -Encoding UTF8 (Join-Path $cursor "mcp.json")
Write-Host "Registrado en .cursor\mcp.json -> $servidor" -ForegroundColor Green

$cline = Get-Command cline -ErrorAction SilentlyContinue
if ($cline) {
    & cline mcp add $nombre --yes -- $py $servidor
    Write-Host "Registrado tambien en Cline." -ForegroundColor Green
}
''',
        },
        notas=[r"Registra el servidor con:  powershell -File scripts\registrar_mcp.ps1"],
    )
)


# --------------------------------------------------------------------------
# API publica del catalogo
# --------------------------------------------------------------------------
@dataclass
class Andamiaje:
    """Resultado de combinar varias plantillas: archivos listos para escribir."""

    archivos: Dict[str, str] = field(default_factory=dict)
    notas: List[str] = field(default_factory=list)
    plantillas: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    paquete: str = ""


def disponibles() -> List[str]:
    """Claves de plantilla registradas, en orden alfabetico."""
    return sorted(PLANTILLAS)


def describir() -> str:
    """Tabla legible del catalogo, pensada para que la IA elija plantillas."""
    lineas = ["Plantillas disponibles (coloca las claves en 'plantillas'):", ""]
    for clave in disponibles():
        plantilla = PLANTILLAS[clave]
        lineas.append(
            "- {}: {} -> {}".format(clave, plantilla.titulo, plantilla.descripcion)
        )
        for nota in plantilla.notas:
            lineas.append("    * {}".format(nota))
    lineas.append("")
    lineas.append(
        "Se pueden combinar (por ejemplo 'python,web3' o 'python,fastapi,playwright'): "
        "la base (README y .gitignore) y el requirements.txt se fusionan solos."
    )
    return "\n".join(lineas)


def interpretar_seleccion(seleccion) -> List[str]:
    """Acepta 'python,web3' o ['python', 'web3'] y devuelve claves validas."""
    if seleccion is None:
        return []
    if isinstance(seleccion, str):
        crudas = re.split(r"[,;\s]+", seleccion)
    else:
        crudas = []
        for elemento in seleccion:
            crudas.extend(re.split(r"[,;\s]+", str(elemento)))
    claves = []
    for cruda in crudas:
        clave = (cruda or "").strip().lower()
        if clave and clave not in claves:
            claves.append(clave)
    return claves


def _fusionar_requirements(textos: List[str]) -> str:
    """Une varios requirements.txt sin repetir dependencias."""
    lineas: List[str] = []
    vistas = set()
    for texto in textos:
        for linea in (texto or "").splitlines():
            limpia = linea.strip()
            if not limpia:
                continue
            comparable = limpia.lower().replace(" ", "").split("=")[0].split(">")[0].split("<")[0]
            if comparable in vistas:
                continue
            vistas.add(comparable)
            lineas.append(limpia)
    return ("\n".join(lineas) + "\n") if lineas else ""


def construir(
    seleccion, nombre: str, descripcion: str = ""
) -> Andamiaje:
    """Combina las plantillas indicadas y devuelve los archivos del proyecto.

    Args:
        seleccion: claves de plantilla ('python,web3', ['python', 'web3']...).
        nombre: nombre del proyecto (se normaliza a slug).
        descripcion: descripcion breve que se incrusta en README y pyproject.

    Returns:
        :class:`Andamiaje` con los archivos (ruta relativa -> contenido), las
        notas de instalacion y los avisos sobre plantillas desconocidas.
    """
    limpio = rutas.normalizar_nombre(nombre)
    paquete = _nombre_paquete(limpio)
    claves = interpretar_seleccion(seleccion)
    avisos: List[str] = []

    validas: List[str] = []
    for clave in claves:
        if clave in PLANTILLAS:
            validas.append(clave)
        else:
            avisos.append(
                "Plantilla desconocida '{}'. Disponibles: {}.".format(
                    clave, ", ".join(disponibles())
                )
            )

    claves_efectivas = validas or []
    archivos: Dict[str, str] = {
        "README.md": _sustituir(README_BASE, limpio, descripcion, paquete, claves_efectivas),
        ".gitignore": GITIGNORE_PYTHON,
    }
    notas: List[str] = []
    requirements: List[str] = []

    for clave in claves_efectivas:
        plantilla = PLANTILLAS[clave]
        for ruta_relativa, contenido in plantilla.archivos.items():
            if ruta_relativa.lower() == "requirements.txt":
                requirements.append(contenido)
                continue
            if ruta_relativa == ".gitignore":
                archivos[".gitignore"] = "{}\n{}".format(archivos[".gitignore"], contenido).strip() + "\n"
                continue
            ruta_final = _sustituir(ruta_relativa, limpio, descripcion, paquete, claves_efectivas)
            archivos[ruta_final] = _sustituir(
                contenido, limpio, descripcion, paquete, claves_efectivas
            )
        notas.extend(
            _sustituir(nota, limpio, descripcion, paquete, claves_efectivas)
            for nota in plantilla.notas
        )

    for ruta_orq, contenido_orq in archivos_de_orquestacion(
        limpio, descripcion, paquete, claves_efectivas
    ).items():
        archivos.setdefault(ruta_orq, contenido_orq)

    if requirements:
        archivos["requirements.txt"] = _fusionar_requirements(requirements)

    notas.append(
        "Orquestacion: el proyecto ya trae reglas para la IA (.clinerules, "
        ".cursorrules, AGENTS.md) y .cursor/mcp.json; copia .env.example a .env."
    )

    return Andamiaje(
        archivos=archivos,
        notas=notas,
        plantillas=claves_efectivas,
        avisos=avisos,
        paquete=paquete,
    )
