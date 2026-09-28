"""Memoria de la sesion de mejora continua de cada proyecto.

El bucle IDE <-> API no converge si cada ronda empieza en blanco: el arquitecto
repetiria sugerencias ya resueltas y el coste por ronda subiria. Aqui se guarda,
por proyecto, un turno por ronda en ``datos/sesiones/<slug>/turno-NN.json``:

    {ronda, momento, hechos, evidencia, archivos_tocados, sugerencias_propias,
     directriz, estado, motivo_de_cierre}

Con eso se puede reconstruir el hilo (que se manda al arquitecto como memoria
acotada), cerrar la sesion con un motivo y sobrevivir a reinicios del IDE. No
hay ninguna dependencia de MCP ni de red: es disco puro.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import config as configuracion
import rutas

#: Estados validos de una ronda.
ESTADO_ABIERTA = "abierta"
ESTADO_CERRADA = "cerrada"

#: Rondas que se resumen al arquitecto por defecto.
RONDAS_EN_MEMORIA = 3

#: Marcadores con los que el usuario puede cortar el bucle desde el informe.
PALABRAS_DE_PARADA = ("parar", "stop", "basta", "suficiente")


def raiz_sesiones() -> Path:
    """Carpeta donde viven las sesiones (``datos/sesiones`` por defecto)."""
    personalizada = (os.getenv("ARQUITECTO_CARPETA_SESIONES") or "").strip()
    if personalizada:
        carpeta = Path(personalizada).expanduser()
        if not carpeta.is_absolute():
            carpeta = configuracion.RAIZ_PROYECTO / carpeta
        return carpeta
    return configuracion.RAIZ_PROYECTO / "datos" / "sesiones"


def carpeta_sesion(proyecto: str) -> Path:
    """Carpeta de la sesion de un proyecto (creada si hace falta)."""
    limpio = rutas.normalizar_nombre(proyecto)
    carpeta = raiz_sesiones() / limpio
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _archivo_turno(proyecto: str, ronda: int) -> Path:
    return carpeta_sesion(proyecto) / "turno-{:02d}.json".format(max(1, int(ronda)))


def leer_turnos(proyecto: str, rondas: int = 0) -> List[Dict]:
    """Turnos guardados, de la ronda 1 a la ultima (o solo los ultimos N)."""
    carpeta = carpeta_sesion(proyecto)
    turnos: List[Dict] = []
    for ruta in sorted(carpeta.glob("turno-*.json")):
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(datos, dict):
            turnos.append(datos)
    if rondas and rondas > 0:
        return turnos[-rondas:]
    return turnos


def ultimo_turno(proyecto: str) -> Dict:
    """Ultimo turno guardado (``{}`` si la sesion es nueva)."""
    turnos = leer_turnos(proyecto, 1)
    return turnos[0] if turnos else {}


def siguiente_ronda(proyecto: str) -> int:
    """Numero de ronda que toca (1 si no hay nada guardado)."""
    turnos = leer_turnos(proyecto)
    if not turnos:
        return 1
    try:
        return int(turnos[-1].get("ronda", len(turnos))) + 1
    except (TypeError, ValueError):
        return len(turnos) + 1


def guardar_turno(proyecto: str, turno: Dict) -> Path:
    """Guarda un turno de forma atomica (fichero temporal + reemplazo)."""
    ronda = int(turno.get("ronda") or siguiente_ronda(proyecto))
    datos = dict(turno)
    datos["ronda"] = ronda
    datos.setdefault("momento", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    destino = _archivo_turno(proyecto, ronda)
    temporal = destino.with_suffix(".tmp")
    temporal.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporal.replace(destino)
    return destino


def resumen_para_arquitecto(proyecto: str, rondas: int = RONDAS_EN_MEMORIA) -> str:
    """Memoria acotada de la sesion: lo que el arquitecto debe recordar.

    No repite el repositorio entero: solo las ultimas rondas (que se hizo y que
    directriz salio) y si la sesion ya estaba cerrada.
    """
    turnos = leer_turnos(proyecto)
    if not turnos:
        return "(sesion nueva: sin rondas previas)"
    recientes = turnos[-max(1, rondas) :]
    cerrada = any(turno.get("estado") == ESTADO_CERRADA for turno in turnos)
    lineas = [
        "rondas totales: {}".format(len(turnos)),
        "estado: {}".format("cerrada" if cerrada else "abierta"),
    ]
    for turno in recientes:
        lineas.append("")
        lineas.append("--- ronda {} ({}) ---".format(turno.get("ronda"), turno.get("momento", "")))
        if turno.get("hechos"):
            lineas.append("hechos: {}".format(turno["hechos"]))
        if turno.get("evidencia"):
            lineas.append("evidencia: {}".format(turno["evidencia"]))
        if turno.get("archivos_tocados"):
            lineas.append("archivos: {}".format(turno["archivos_tocados"]))
        if turno.get("sugerencias_propias"):
            lineas.append("sugerencias del programador: {}".format(turno["sugerencias_propias"]))
        if turno.get("directriz"):
            lineas.append("directriz del arquitecto: {}".format(turno["directriz"]))
        if turno.get("motivo_de_cierre"):
            lineas.append("cierre: {}".format(turno["motivo_de_cierre"]))
    return "\n".join(lineas)


def cerrar_sesion(proyecto: str, motivo: str) -> Dict:
    """Marca la sesion como cerrada (con el motivo) y devuelve el ultimo turno."""
    turno = ultimo_turno(proyecto) or {"ronda": 1}
    turno["estado"] = ESTADO_CERRADA
    turno["motivo_de_cierre"] = motivo
    guardar_turno(proyecto, turno)
    return turno


def sesion_cerrada(proyecto: str) -> bool:
    """True si la ultima ronda dejo la sesion cerrada."""
    return (ultimo_turno(proyecto) or {}).get("estado") == ESTADO_CERRADA


def pide_parar(texto: str) -> bool:
    """True si el texto (normalmente el informe) contiene una palabra de parada."""
    limpio = (texto or "").strip().lower()
    if not limpio:
        return False
    rodeado = " {} ".format(limpio)
    return any(
        limpio == palabra or " {} ".format(palabra) in rodeado
        for palabra in PALABRAS_DE_PARADA
    )

