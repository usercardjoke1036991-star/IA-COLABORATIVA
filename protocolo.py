"""Contrato de comunicacion entre el PROGRAMADOR (Cursor) y el ARQUITECTO.

Aqui vive todo lo que define *como se hablan* las dos IAs:

* Los marcadores de seccion que llevan los mensajes enviados al Arquitecto.
* El system prompt que convierte al modelo externo en un arquitecto que
  aconseja y no programa.
* El formato de la respuesta que devuelve al PROGRAMADOR.
* El marcador de fin de tarea, que corta el loop continuo cuando ya no hay
  nada mas que hacer (evita el bucle infinito de "quedo a la espera").
"""

from __future__ import annotations

MARCADOR_PLAN = "[PLAN INICIAL]"
MARCADOR_PROGRESO = "[INFORME DE PROGRESO]"

#: Marcador del informes del bucle de mejora continua (ronda a ronda).
MARCADOR_MEJORA = "[INFORME DE MEJORA CONTINUA]"

#: Marcadores del contrato con el rol PROGRAMADOR (segundo modelo, el que codifica).
MARCADOR_TAREA = "[TAREA DE CODIGO]"
MARCADOR_CORRECCION = "[CORRECCION DE ERROR]"
MARCADOR_ARCHIVO = "### ARCHIVO:"
MARCADOR_PASOS = "### PASOS"

#: El Arquitecto escribe este literal cuando el objetivo del usuario ya se
#: cumplio. El PROGRAMADOR debe dejar de iterar al verlo.
MARCADOR_FIN = "[[ARQUITECTO: FIN]]"

SYSTEM_PROMPT = """Eres el ARQUITECTO EXTERNO: un arquitecto de software senior que \
colabora con otra IA llamada PROGRAMADOR (la IA integrada en el IDE Cursor).

REPARTO DE RESPONSABILIDADES
- TU: piensas, dimensionas, disenas, decides, detectas riesgos y aconsejas.
- EL PROGRAMADOR: escribe el codigo real en el IDE siguiendo tus directrices.
- Tu NO entregas el codigo final. Escribes directrices, no implementaciones.

COMO DEBES RESPONDER
1. Responde SIEMPRE en el mismo idioma en que se te escribe.
2. Dimensiona antes de decidir: objetivo, alcance, supuestos, riesgos y casos limite.
3. Entrega un plan ACCIONABLE con pasos numerados; cada paso debe ser ejecutable
   por el PROGRAMADOR sin ambiguedad.
4. Recomienda stack, librerias, estructura de archivos, patrones y criterios de
   aceptacion verificables.
5. Usa pseudocodigo, firmas de funciones o esquemas de datos. Nunca pegues
   archivos completos de codigo.
6. Si falta informacion critica, declara tu supuesto explicitamente y continua.
   No bloquees el trabajo haciendo preguntas y esperando respuesta.
7. Se denso y util: listas, tablas y verbos de accion. Nada de relleno.
8. PROHIBIDO cerrar con cortesias vacias tipo "quedo a la espera de tus
   comentarios", "avisame cuando lo tengas" o "aqui estare". No pidas permiso:
   da la orden tecnica y termina.
9. Si un mensaje no aporta informacion tecnica nueva, no lo comentes.

CUANDO RECIBAS UN INFORME DE PROGRESO
1. Valida lo hecho: que esta bien, que esta mal y que riesgos aparecen.
2. Si detectas un error, indica el sintoma probable, la causa y la correccion.
3. Dicta los SIGUIENTES pasos concretos, en orden, con criterio de "terminado".
4. Si el objetivo original ya esta cumplido, cierra con el marcador exacto
   {marcador} y una lista breve de verificaciones finales sugeridas.

ESTRUCTURA SUGERIDA DE RESPUESTA
## Diagnostico
(1-4 lineas: estado actual, riesgo principal)
## Plan
1. Paso concreto -> entregable y criterio de aceptacion.
2. ...
## Riesgos y decisiones tecnicas
- ...

MODO MEJORA CONTINUA (bucle informe -> sugerencias -> implementacion)
-------------------------------------------------------------------
El PROGRAMADOR puede trabajar en RONDAS dentro del mismo objetivo. En cada
ronda te manda: su informe (que hizo, con la evidencia REAL de las pruebas), el
contexto del repositorio y la memoria de la sesion (las ultimas rondas y tus
directrices anteriores). Tu respondes en este formato exacto:

## Diagnostico
(que mejora de verdad y que no, con criterio tecnico; nada de complacencia)
## Sugerencias
1. [valor alto] QUE -> DONDE -> criterio de terminado.
2. [valor medio] ...
(maximo 5 por ronda, de mas valor a menos; nada de relleno)
## Riesgos
(lo que puede romperse al tocar esos puntos y como verificarlo)

Reglas del bucle: no repitas una sugerencia que la memoria de la sesion ya da
por resuelta; exige evidencia real en vez de promesas; y si no queda ninguna
mejora de valor, NO inventes trabajo: cierra la respuesta con el marcador
exacto {marcador}.
""".format(marcador=MARCADOR_FIN)


# --------------------------------------------------------------------------
# Constructores de mensajes (lo que el PROGRAMADOR envia)
# --------------------------------------------------------------------------
def bloque_idea(idea_del_usuario: str, contexto_del_codigo: str = "") -> str:
    """Mensaje inicial: dimensionar una idea antes de escribir codigo."""
    partes = [
        MARCADOR_PLAN,
        "IDEA / PETICION DEL USUARIO:\n{}".format(idea_del_usuario.strip()),
    ]
    if contexto_del_codigo and contexto_del_codigo.strip():
        partes.append(
            "CONTEXTO DEL CODIGO O DEL PROYECTO:\n{}".format(
                contexto_del_codigo.strip()
            )
        )
    partes.append("Entrega el plan de ataque inicial y arranca el loop.")
    return "\n\n".join(partes)


def bloque_progreso(
    resumen_de_lo_hecho: str,
    prompt_original: str = "",
    archivos_tocados: str = "",
    bloqueo: str = "",
) -> str:
    """Mensaje de seguimiento: cerrar el ciclo tras cada paso del PROGRAMADOR."""
    partes = [MARCADOR_PROGRESO]
    if prompt_original and prompt_original.strip():
        partes.append("OBJETIVO ORIGINAL:\n{}".format(prompt_original.strip()))
    partes.append(
        "LO QUE EL PROGRAMADOR ACABA DE HACER:\n{}".format(resumen_de_lo_hecho.strip())
    )
    if archivos_tocados and archivos_tocados.strip():
        partes.append("ARCHIVOS TOCADOS:\n{}".format(archivos_tocados.strip()))
    if bloqueo and bloqueo.strip():
        partes.append("BLOQUEO O DUDA DEL PROGRAMADOR:\n{}".format(bloqueo.strip()))
    partes.append(
        "Valida lo anterior y dicta los SIGUIENTES pasos concretos. Si el objetivo "
        "ya se cumplio, escribe el marcador {} y deten el loop.".format(MARCADOR_FIN)
    )
    return "\n\n".join(partes)


def tarea_terminada(contenido: str) -> bool:
    """True si el Arquitecto declaro terminada la tarea."""
    return MARCADOR_FIN in (contenido or "")


# --------------------------------------------------------------------------
# Rol PROGRAMADOR: el segundo modelo, el que escribe el codigo
# --------------------------------------------------------------------------
SYSTEM_PROMPT_PROGRAMADOR = """Eres el PROGRAMADOR EXTERNO: un ingeniero de software \
senior que escribe el codigo real de un proyecto Python que vive en disco.

REPARTO DE RESPONSABILIDADES
- EL ARQUITECTO: ya decidio el plan, el stack y los criterios de aceptacion.
- TU: escribes el codigo completo y listo para ejecutar, archivo por archivo.
- El sistema guardara tus archivos automaticamente: no expliques como copiarlos.

FORMATO DE RESPUESTA (obligatorio, se analiza automaticamente)
Por cada archivo que crees o modifiques escribe exactamente:

### ARCHIVO: ruta/relativa/del/archivo.py
```python
contenido COMPLETO del archivo, sin recortes ni "..." ni comentarios de relleno
```

Despues de los archivos anade:

### PASOS
1. comando exacto para ejecutar o probar (por ejemplo:
   venv\\Scripts\\python.exe -m pytest -q)

REGLAS
1. Escribe SIEMPRE el archivo completo: se sobrescribe tal cual, no hay parches.
2. Rutas relativas a la raiz del proyecto, con barras normales (/).
3. Nada de texto fuera del formato: corto, tecnico y en el idioma del usuario.
4. Codigo ejecutable de verdad: imports completos, manejo de errores, sin
   pseudo-codigo, sin TODOs, sin dependencias que no esten en requirements.txt.
5. Usa solo la libreria estandar y las dependencias que indique el plan.
6. Anade tipos en las firmas y docstrings breves en las funciones publicas.
7. Si el plan pide pruebas, incluye el archivo de pruebas completo.
8. Si algo del plan es imposible o arriesgado, escribe una seccion final
   ## NOTAS con el motivo y la alternativa que aplicaste.
"""


# --------------------------------------------------------------------------
# Constructores de mensajes para el PROGRAMADOR
# --------------------------------------------------------------------------
def bloque_implementacion(
    tarea: str,
    plan: str = "",
    contexto: str = "",
    proyecto: str = "",
) -> str:
    """Mensaje con la tarea de codigo que debe resolver el PROGRAMADOR externo."""
    partes = [MARCADOR_TAREA]
    if proyecto and proyecto.strip():
        partes.append("PROYECTO (raiz en disco): {}".format(proyecto.strip()))
    partes.append("TAREA A IMPLEMENTAR:\n{}".format((tarea or "").strip()))
    if plan and plan.strip():
        partes.append("PLAN DEL ARQUITECTO:\n{}".format(plan.strip()))
    if contexto and contexto.strip():
        partes.append("CONTEXTO (codigo actual, restricciones, entorno):\n{}".format(contexto.strip()))
    partes.append(
        "Devuelve los archivos completos en el formato '{} ruta' + bloque de codigo, "
        "y termina con la seccion '{}'.".format(MARCADOR_ARCHIVO, MARCADOR_PASOS)
    )
    return "\n\n".join(partes)


def bloque_correccion(
    error: str,
    codigo_previo: str = "",
    intento: int = 1,
) -> str:
    """Mensaje de correccion: el codigo anterior fallo, esto es el error real."""
    partes = [
        MARCADOR_CORRECCION,
        "INTENTO: {}".format(intento),
        "ERROR OBSERVADO (salida real de la ejecucion):\n{}".format((error or "").strip()),
    ]
    if codigo_previo and codigo_previo.strip():
        partes.append("CODIGO QUE FALLO:\n{}".format(codigo_previo.strip()))
    partes.append(
        "Corrige la causa raiz y devuelve los archivos COMPLETOS afectados, en el mismo "
        "formato '{} ruta' + bloque de codigo.".format(MARCADOR_ARCHIVO)
    )
    return "\n\n".join(partes)


def esta_listo(contenido: str) -> bool:
    """True si el PROGRAMADOR entrego al menos un archivo en el formato acordado."""
    return bool(extraer_archivos(contenido))


# --------------------------------------------------------------------------
# Formato de salida (lo que el PROGRAMADOR recibe)
# --------------------------------------------------------------------------
_ANCHO = 58


def formatear_respuesta(
    contenido: str,
    turno: int,
    proveedor: str,
    modelo: str,
    terminada: bool,
    segundos: float = 0.0,
) -> str:
    """Envuelve el consejo del Arquitecto con metadatos utiles para el IDE."""
    cabecera = " ARQUITECTO EXTERNO ".center(_ANCHO, "=")
    pie = "=" * _ANCHO
    meta = "proveedor: {}  |  modelo: {}  |  turno: {}".format(proveedor, modelo, turno)
    if segundos:
        meta += "  |  {:.1f}s".format(segundos)

    if terminada:
        estado = [
            "estado del loop: TAREA TERMINADA.",
            "El PROGRAMADOR debe dejar de llamar al arquitecto, verificar los",
            "criterios de aceptacion y entregar el resumen final al usuario.",
        ]
    else:
        estado = [
            "estado del loop: EN CURSO.",
            "El PROGRAMADOR debe implementar los pasos indicados y despues llamar",
            "a la herramienta `reportar_progreso` con un resumen y archivos tocados.",
        ]

    return "\n".join(
        [cabecera, meta, "-" * _ANCHO, contenido.strip(), "-" * _ANCHO] + estado + [pie]
    )


def formatear_error(mensaje: str) -> str:
    """Devuelve un error legible al PROGRAMADOR sin tumbar el servidor MCP."""
    return "\n".join(
        [
            "=" * _ANCHO,
            " ARQUITECTO EXTERNO - ERROR ".center(_ANCHO, "="),
            "-" * _ANCHO,
            str(mensaje).strip(),
            "-" * _ANCHO,
            "Sugerencias:",
            "1. Revisa el archivo .env (proveedor, modelo y API key).",
            "2. Ejecuta:  python arquitecto_mcp.py --check",
            "3. Revisa los logs de MCP en Cursor (Output -> MCP Logs).",
            "El loop queda en pausa; corrige y vuelve a llamar la herramienta.",
            "=" * _ANCHO,
        ]
    )


# --------------------------------------------------------------------------
# Analisis de la respuesta del PROGRAMADOR
# --------------------------------------------------------------------------
def bloque_mejora(
    proyecto: str,
    informe: str,
    contexto: str = "",
    memoria: str = "",
) -> str:
    """Mensaje del bucle de mejora continua: informe + contexto + memoria.

    Args:
        proyecto: nombre del proyecto registrado en la fabrica.
        informe: que hizo el PROGRAMADOR, con la evidencia real (obligatorio).
        contexto: resumen real del repositorio (ya saneado de secretos).
        memoria: resumen de la sesion (rondas previas y directrices).

    Returns:
        Texto listo para enviar al Arquitecto, con el marcador del bucle.
    """
    partes = [
        MARCADOR_MEJORA,
        "",
        "PROYECTO: {}".format((proyecto or "").strip() or "(sin nombre)"),
        "",
        "INFORME DEL PROGRAMADOR (ronda cerrada):",
        (informe or "").strip(),
    ]
    if contexto:
        partes += ["", "CONTEXTO REAL DEL REPOSITORIO:", contexto.strip()]
    if memoria:
        partes += ["", "MEMORIA DE LA SESION:", memoria.strip()]
    partes += [
        "",
        "TAREA: devuelve el siguiente lote priorizado de mejoras para este proyecto",
        "siguiendo el MODO MEJORA CONTINUA. Si no queda ninguna mejora de valor,",
        "cierra la respuesta con {}.".format(MARCADOR_FIN),
    ]
    return "\n".join(partes)


def _limpiar_ruta(ruta: str) -> str:
    """Normaliza la ruta anunciada por el modelo (barras, comillas, espacios)."""
    limpia = (ruta or "").strip().strip("`'\"").strip()
    limpia = limpia.replace("\\", "/")
    while limpia.startswith("./"):
        limpia = limpia[2:]
    return limpia.strip("/")


def extraer_archivos(texto: str) -> list:
    """Extrae los archivos que el PROGRAMADOR entrego en su respuesta.

    Formato reconocido::

        ### ARCHIVO: src/app.py
        ```python
        ...contenido completo...
        ```

    Returns:
        Lista de ``(ruta, contenido)`` en orden de aparicion. Si un archivo se
        repite, gana la ultima version (es lo habitual al corregir).
    """
    lineas = (texto or "").splitlines()
    archivos: List[tuple] = []

    for indice, linea in enumerate(lineas):
        desnuda = linea.strip()
        if not desnuda.upper().startswith(MARCADOR_ARCHIVO.upper()):
            continue
        ruta = _limpiar_ruta(desnuda[len(MARCADOR_ARCHIVO):])
        if not ruta:
            continue

        contenido: List[str] = []
        abierto = False
        for siguiente in lineas[indice + 1:]:
            marca = siguiente.strip()
            if not abierto:
                if marca.startswith("```"):
                    abierto = True
                    continue
                if marca.upper().startswith(MARCADOR_ARCHIVO.upper()) or marca.startswith("###"):
                    break
                continue
            if marca == "```":
                break
            contenido.append(siguiente)

        if abierto:
            archivos.append((ruta, "\n".join(contenido).rstrip() + "\n"))

    # Gana la ultima version de cada ruta, conservando el orden original.
    unicos = []
    for ruta, contenido in archivos:
        unicos = [(r, c) for r, c in unicos if r != ruta]
        unicos.append((ruta, contenido))
    return unicos


def pasos_sugeridos(texto: str) -> str:
    """Devuelve el bloque '### PASOS' de la respuesta del PROGRAMADOR (si existe)."""
    lineas = (texto or "").splitlines()
    for indice, linea in enumerate(lineas):
        if linea.strip().upper().startswith(MARCADOR_PASOS.upper()):
            return "\n".join(lineas[indice + 1 :]).strip()
    return ""


def formatear_respuesta_programador(
    contenido: str,
    turno: int,
    proveedor: str,
    modelo: str,
    archivos: List[tuple],
    segundos: float = 0.0,
) -> str:
    """Envuelve el codigo del PROGRAMADOR con metadatos y el resumen de archivos."""
    cabecera = " PROGRAMADOR EXTERNO ".center(_ANCHO, "=")
    pie = "=" * _ANCHO
    meta = "proveedor: {}  |  modelo: {}  |  turno: {}".format(proveedor, modelo, turno)
    if segundos:
        meta += "  |  {:.1f}s".format(segundos)

    if archivos:
        resumen = ["Archivos entregados ({}):".format(len(archivos))]
        resumen.extend("  - {} ({} caracteres)".format(r, len(c)) for r, c in archivos)
    else:
        resumen = [
            "AVISO: no se detecto ningun bloque '{} ruta' en la respuesta.".format(
                MARCADOR_ARCHIVO
            ),
            "Revisala a mano antes de aplicar nada.",
        ]

    return "\n".join(
        [cabecera, meta, "-" * _ANCHO, contenido.strip(), "-" * _ANCHO] + resumen + [pie]
    )
