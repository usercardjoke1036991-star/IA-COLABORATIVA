"""Bucle de mejora continua: informe del IDE -> sugerencias de la API -> implementar.

Este modulo es el pegamento del ciclo completo:

1. La IA del IDE programa y llama a :func:`informe_de_trabajo` con lo que hizo,
   la evidencia REAL de las pruebas y sus propias sugerencias.
2. :func:`sugerir_mejoras` manda al arquitecto ese informe + el contexto real del
   repositorio + la memoria de la sesion, guarda su directriz y devuelve el
   siguiente lote priorizado (o el cierre del bucle).
3. La IA del IDE implementa y vuelve al paso 1 hasta que el arquitecto dice
   `[[ARQUITECTO: FIN]]`, el usuario escribe PARAR o se agotan las rondas.

Todo queda escrito en el proyecto (``INFORME.md`` y ``SUGERENCIAS.md``) y en la
sesion (``datos/sesiones/<slug>/turno-NN.json``), asi que el hilo del trabajo no
se pierde aunque se reinicie el IDE o cambie la sesion del modelo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import activacion
import config as configuracion
import contexto
import protocolo
import rutas
import sesiones
from arquitecto import Arquitecto

#: Tope de caracteres del informe que se manda al arquitecto.
TOPE_INFORME = 8_000


def _carpeta(proyecto: str) -> Path:
    """Carpeta real del proyecto activado o creado por la fabrica."""
    return activacion.carpeta_de(proyecto)


def _anexar(carpeta: Path, nombre: str, bloque: str, cabecera: str) -> None:
    """Anade un bloque al final de un Markdown del proyecto (lo crea si falta)."""
    destino = carpeta / nombre
    try:
        existente = destino.read_text(encoding="utf-8-sig") if destino.exists() else ""
    except OSError:
        existente = ""
    if not existente.strip():
        existente = cabecera
    if not existente.endswith("\n"):
        existente += "\n"
    destino.write_text(existente + "\n" + bloque.strip() + "\n", encoding="utf-8", newline="\n")


def _bloque_informe(turno: dict) -> str:
    """Markdown de una ronda para ``INFORME.md``."""
    return """## Ronda {ronda} - {momento}

### Que se hizo

{hechos}

### Evidencia real

```
{evidencia}
```

### Archivos tocados

{archivos}

### Sugerencias propias del programador

{sugerencias}
""".format(
        ronda=turno.get("ronda", "?"),
        momento=turno.get("momento", ""),
        hechos=turno.get("hechos") or "(sin detallar)",
        evidencia=turno.get("evidencia") or "(sin evidencia: falta)",
        archivos=turno.get("archivos_tocados") or "(sin listar)",
        sugerencias=turno.get("sugerencias_propias") or "(ninguna)",
    )


def _bloque_sugerencias(turno: dict, directriz: str, estado: str) -> str:
    """Markdown de una ronda para ``SUGERENCIAS.md``."""
    return """## Ronda {ronda} - {momento}

- estado de la sesion: {estado}
- informe de referencia: ronda {ronda} de INFORME.md

{directriz}
""".format(
        ronda=turno.get("ronda", "?"),
        momento=turno.get("momento", ""),
        estado=estado,
        directriz=(directriz or "(sin respuesta del arquitecto)").strip(),
    )


# --------------------------------------------------------------------------
# API del bucle
# --------------------------------------------------------------------------
def informe_de_trabajo(
    proyecto: str,
    hechos: str,
    evidencia: str,
    sugerencias_propias: str = "",
    archivos_tocados: str = "",
) -> str:
    """Cierra una ronda: guarda lo hecho (con pruebas) y abre la revision.

    Args:
        proyecto: proyecto registrado en la fabrica.
        hechos: que se implemento, en 3-8 lineas.
        evidencia: comando ejecutado y su salida real (sin resumir).
        sugerencias_propias: tus propias ideas de mejora, priorizadas.
        archivos_tocados: rutas relativas de lo que se creo o cambio.

    Returns:
        Texto con la ronda registrada y la siguiente llamada exacta.

    Raises:
        ValueError: si falta el informe o la evidencia (nada de informes vacios).
        rutas.ErrorRuta: si el nombre del proyecto no es valido.
    """
    limpio = rutas.normalizar_nombre(proyecto)
    if not (hechos or "").strip():
        raise ValueError("Falta 'hechos': cuenta que se hizo en esta ronda.")
    if not (evidencia or "").strip():
        raise ValueError(
            "Falta 'evidencia': pega el comando exacto y su salida real. "
            "Un informe sin pruebas no le sirve de nada al arquitecto."
        )

    carpeta = _carpeta(limpio)
    if not carpeta.is_dir():
        raise ValueError(
            "El proyecto '{}' no tiene carpeta ({}). Activarlo primero con "
            "activar_proyecto.".format(limpio, carpeta)
        )

    ronda = sesiones.siguiente_ronda(limpio)
    turno = {
        "ronda": ronda,
        "proyecto": limpio,
        "hechos": hechos.strip(),
        "evidencia": evidencia.strip()[:TOPE_INFORME],
        "archivos_tocados": (archivos_tocados or "").strip(),
        "sugerencias_propias": (sugerencias_propias or "").strip(),
        "estado": sesiones.ESTADO_ABIERTA,
    }
    sesiones.guardar_turno(limpio, turno)
    _anexar(
        carpeta,
        activacion.ARCHIVO_INFORME,
        _bloque_informe(turno),
        activacion.esqueleto_informe(limpio),
    )

    parar = sesiones.pide_parar(hechos) or sesiones.pide_parar(sugerencias_propias)
    siguiente = (
        "PARAR: se detecto la palabra de parada en el informe. Cierra la sesion con "
        "sugerir_mejoras(proyecto=\"{}\") solo si quieres la valoracion final, o entrega "
        "el resumen al usuario.".format(limpio)
        if parar
        else "siguiente: sugerir_mejoras(proyecto=\"{}\")".format(limpio)
    )

    return "\n".join(
        [
            "Ronda {} registrada para '{}'.".format(ronda, limpio),
            "- informe: {} y {}".format(
                activacion.ARCHIVO_INFORME, "turno-{:02d}.json".format(ronda)
            ),
            "- evidencia: {} caracteres".format(len(turno["evidencia"])),
            "- memorizado: {} sugerencias propias del programador".format(
                "con" if turno["sugerencias_propias"] else "sin"
            ),
            "",
            siguiente,
        ]
    )


def estado_de_sesion(proyecto: str) -> str:
    """Resumen local (sin gastar tokens) de la sesion de un proyecto."""
    limpio = rutas.normalizar_nombre(proyecto)
    turnos = sesiones.leer_turnos(limpio)
    cfg = configuracion.cargar_fabrica()
    if not turnos:
        return (
            "Proyecto '{}': sesion nueva (0 rondas). Empieza con informe_de_trabajo "
            "tras tu primer bloque de trabajo.".format(limpio)
        )
    ultimo = turnos[-1]
    return "\n".join(
        [
            "=" * 60,
            " SESION DE MEJORA CONTINUA: {} ".format(limpio).center(60, "="),
            "-" * 60,
            "rondas: {} de {} (tope ARQUITECTO_MAX_RONDAS)".format(len(turnos), cfg.max_rondas),
            "estado: {}".format(ultimo.get("estado", "abierta")),
            "ultima ronda: {} ({})".format(ultimo.get("ronda"), ultimo.get("momento", "")),
            "ultimo cierre: {}".format(ultimo.get("motivo_de_cierre") or "(no cerrada)"),
            "-" * 60,
            sesiones.resumen_para_arquitecto(limpio),
            "=" * 60,
        ]
    )


def _informe_para_arquitecto(turno: dict) -> str:
    """Texto del informe que se manda al arquitecto (hechos + evidencia + ideas)."""
    return "\n".join(
        [
            "hechos: {}".format(turno.get("hechos") or "(sin detallar)"),
            "archivos tocados: {}".format(turno.get("archivos_tocados") or "(sin listar)"),
            "",
            "evidencia real (comando y salida):",
            turno.get("evidencia") or "(sin evidencia)",
            "",
            "sugerencias propias del programador:",
            turno.get("sugerencias_propias") or "(ninguna)",
        ]
    )


def sugerir_mejoras(
    proyecto: str,
    enfoque: str = "",
    arquitecto: Optional[Arquitecto] = None,
) -> str:
    """Pide al arquitecto el siguiente lote de mejoras para el proyecto.

    Toma el ultimo informe de la sesion, lo manda junto al contexto real del
    repositorio y la memoria de la sesion, guarda la directriz y devuelve el
    texto listo para implementar (o el cierre del bucle).

    Args:
        proyecto: proyecto registrado en la fabrica.
        enfoque: opcional; a que area quieres que dedique la revision.
        arquitecto: motor del arquitecto (inyectable en pruebas).

    Returns:
        Sugerencias priorizadas + estado de la sesion + siguiente accion.

    Raises:
        ValueError: si todavia no hay informe (primero ``informe_de_trabajo``).
        rutas.ErrorRuta: si el nombre del proyecto no es valido.
    """
    limpio = rutas.normalizar_nombre(proyecto)
    turno = sesiones.ultimo_turno(limpio)
    if not turno:
        raise ValueError(
            "No hay ningun informe de '{}': llama primero a informe_de_trabajo "
            "(hechos + evidencia real) y despues a esta herramienta.".format(limpio)
        )
    if sesiones.sesion_cerrada(limpio):
        return (
            "La sesion de '{}' ya esta cerrada ({}).\n"
            "Para seguir mejorando, abre una ronda nueva con informe_de_trabajo.".format(
                limpio, turno.get("motivo_de_cierre") or "sin motivo registrado"
            )
        )

    cfg = configuracion.cargar_fabrica()
    rondas = len(sesiones.leer_turnos(limpio))
    if rondas > cfg.max_rondas:
        sesiones.cerrar_sesion(limpio, "tope de rondas alcanzado ({})".format(cfg.max_rondas))
        return (
            "Sesion de '{}' cerrada por tope de rondas ({}).\n"
            "Revisa {} y decide si abrir otra sesion.".format(
                limpio, cfg.max_rondas, activacion.ARCHIVO_SUGERENCIAS
            )
        )

    carpeta = _carpeta(limpio)
    stack = activacion.detectar_stack(carpeta)
    memoria = sesiones.resumen_para_arquitecto(limpio)
    extra = "ENFOQUE pedido por el usuario: {}".format(enfoque.strip()) if enfoque.strip() else ""
    resumen = contexto.contexto_del_repo(carpeta, stack, extra=extra)

    motor = arquitecto or Arquitecto()
    respuesta = motor.revisar_mejoras(
        proyecto=limpio,
        informe=_informe_para_arquitecto(turno),
        contexto=resumen,
        memoria=memoria,
    )
    if respuesta.error:
        return protocolo.formatear_error(respuesta.error)

    directriz = respuesta.contenido
    cerrada = bool(respuesta.terminada)
    if cerrada:
        turno["estado"] = sesiones.ESTADO_CERRADA
        turno["motivo_de_cierre"] = "el arquitecto cerro el bucle con {}".format(
            protocolo.MARCADOR_FIN
        )
    turno["directriz"] = directriz
    sesiones.guardar_turno(limpio, turno)
    _anexar(
        carpeta,
        activacion.ARCHIVO_SUGERENCIAS,
        _bloque_sugerencias(turno, directriz, "cerrada" if cerrada else "abierta"),
        activacion.esqueleto_sugerencias(limpio),
    )

    estado = "TAREA TERMINADA" if cerrada else "EN CURSO"
    cabecera = [
        "=" * 68,
        " RONDA {} REVISADA ({}) ".format(turno.get("ronda"), estado).center(68, "="),
        "=" * 68,
        "arquitecto: {} | modelo: {} | turno: {} | {:.1f}s".format(
            respuesta.proveedor, respuesta.modelo, respuesta.turno, respuesta.segundos
        ),
        "guardado en: {}".format(activacion.ARCHIVO_SUGERENCIAS),
        "memoria de la sesion: {} rondas".format(rondas),
        "-" * 68,
    ]
    pie = (
        [
            "",
            "BUCLE CERRADO por el arquitecto: verifica los criterios de aceptacion,",
            "ejecuta la comprobacion final y entrega el resumen al usuario.",
        ]
        if cerrada
        else [
            "",
            "siguiente: implementa las sugerencias de arriba y llama despues a",
            "informe_de_trabajo(proyecto=\"{}\", ...) con la evidencia real.".format(limpio),
        ]
    )
    return "\n".join(cabecera + [directriz.strip()] + pie)

