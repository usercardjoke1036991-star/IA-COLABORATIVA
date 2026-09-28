"""Fabrica de proyectos: crea carpetas aisladas, las rellena y las publica.

Responsabilidades
-----------------
1. **Crear** la carpeta del proyecto bajo ``ARQUITECTO_CARPETA_PROYECTOS``
   (nunca fuera: todo pasa por :mod:`rutas`).
2. **Rellenar** con las plantillas elegidas mediante :mod:`plantillas`.
3. **Inicializar git** y dejar un primer commit limpio.
4. **Registrar** el proyecto en ``datos/proyectos.json`` para que el orquestador
   sepa que existe, con que plantillas nacio y donde vive.
5. **Publicar** opcionalmente en GitHub con ``gh`` (si esta instalado y hay
   sesion iniciada). Sin ``gh`` la fabrica no falla: informa y sigue.

Todo el modulo es sincrono y sin dependencias externas mas alla de ``git`` y
``gh``, que se invocan como procesos aparte.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config as configuracion
import herramientas_archivos as archivos
import plantillas
import rutas

RUTA_REGISTRO = configuracion.RAIZ_PROYECTO / "datos" / "proyectos.json"


def raices_registro() -> List[Path]:
    """Carpetas dentro de las que puede vivir el registro de proyectos.

    Defensa contra *path traversal* (regla SonarQube ``pythonsecurity:S2083``):
    ``ARQUITECTO_REGISTRO`` es una variable de entorno, o sea una entrada
    externa, y no puede acabar escribiendo en cualquier punto del disco. Se
    admiten la raiz del proyecto y la carpeta que la contiene a la de proyectos
    (ahi viven los sandboxes de pruebas y los cerebros alternativos).
    """
    raiz_proyecto = rutas.raiz_proyecto()
    contenedora = rutas.raiz_fabrica().parent
    raices = [raiz_proyecto]
    if contenedora != raiz_proyecto:
        raices.append(contenedora)
    return raices


def _exigir_raiz_permitida(destino: Path) -> Path:
    """Comprueba que ``destino`` cuelga de una raiz permitida.

    Es el saneado central: la ruta tiene que caer dentro de alguna de las
    carpetas de :func:`raices_registro`. Si no, se lanza :class:`ErrorFabrica`
    antes de tocar el disco.

    La comparacion la hace :func:`rutas.esta_dentro`, que canoniza los dos
    textos antes de mirarlos. La misma carpeta se puede escribir de varias
    maneras (nombre corto 8.3 del temporal del runner, enlaces, mayusculas) y
    un ``is_relative_to`` sobre el texto en crudo rechaza una ruta valida solo
    porque llega sin resolver: eso fue lo que tumbo el CI en Windows.
    """
    if configuracion.cargar_fabrica().permitir_externo:
        return destino
    permitidas = raices_registro()
    if any(rutas.esta_dentro(destino, raiz) for raiz in permitidas):
        return destino
    raise ErrorFabrica(
        "ARQUITECTO_REGISTRO apunta fuera de las raices permitidas: {}\n"
        "Permitido: {}.\n"
        "Si de verdad quieres escribir ahi, pon ARQUITECTO_PERMITIR_EXTERNO=true "
        "en el .env y reinicia.".format(destino, ", ".join(str(raiz) for raiz in permitidas))
    )


def _carpeta_registro(directorio: Path) -> Path:
    """Resuelve la carpeta del registro y la valida contra las raices."""
    if "\0" in str(directorio):
        raise ErrorFabrica("ARQUITECTO_REGISTRO invalido: contiene un byte nulo.")
    try:
        carpeta = Path(directorio).expanduser().resolve()
    except (OSError, RuntimeError) as exc:  # pragma: no cover - defensivo
        raise ErrorFabrica("No se pudo resolver ARQUITECTO_REGISTRO: {}".format(exc))
    return _exigir_raiz_permitida(carpeta)


def _archivo_registro(nombre: str) -> str:
    """Valida el nombre del archivo del registro (solo el nombre, sin rutas)."""
    if not nombre or nombre in {".", ".."}:
        raise ErrorFabrica("ARQUITECTO_REGISTRO invalido: falta el nombre del archivo.")
    # Windows reserva el nombre con cualquier extension ('nul.json' tambien
    # apunta al dispositivo), asi que se comprueba el nombre y su raiz.
    if nombre.lower() in rutas.RESERVADOS or Path(nombre).stem.lower() in rutas.RESERVADOS:
        raise ErrorFabrica("Nombre reservado del sistema: '{}'. Cambialo.".format(nombre))
    if Path(nombre).suffix.lower() in rutas.EXTENSIONES_PROHIBIDAS:
        raise ErrorFabrica(
            "El registro no puede ser un binario '{}': usa un .json.".format(nombre)
        )
    return nombre


def ruta_registro() -> Path:
    """Ruta del registro de proyectos, ya saneada.

    Se puede cambiar con ``ARQUITECTO_REGISTRO`` (util para pruebas o para
    mantener varios cerebros de la fabrica aislados). Del valor recibido solo
    se aprovechan **la carpeta validada y el nombre del archivo**: nunca se
    escribe una ruta que venga tal cual del entorno.
    """
    personalizada = (os.getenv("ARQUITECTO_REGISTRO") or "").strip()
    if not personalizada:
        return RUTA_REGISTRO
    indicada = Path(personalizada)
    if not indicada.is_absolute():
        indicada = configuracion.RAIZ_PROYECTO / indicada
    return _carpeta_registro(indicada.parent) / _archivo_registro(indicada.name)

#: Mensaje del primer commit de cada proyecto nuevo.
MENSAJE_INICIAL = "chore: proyecto creado por la fabrica de IA"


class ErrorFabrica(RuntimeError):
    """La fabrica no pudo completar una operacion (git, gh, nombre ocupado...)."""


@dataclass
class Proyecto:
    """Ficha de un proyecto creado por la fabrica."""

    nombre: str
    ruta: str
    descripcion: str = ""
    plantillas: List[str] = field(default_factory=list)
    creado: str = ""
    con_git: bool = False
    commit: str = ""
    github: str = ""
    estado: str = "creado"

    def resumen(self) -> str:
        """Linea de resumen para el modelo o para la consola."""
        piezas = [
            self.nombre,
            "plantillas={}".format(",".join(self.plantillas) or "base"),
            "git={}".format("si" if self.con_git else "no"),
            "estado={}".format(self.estado),
        ]
        if self.commit:
            piezas.append("commit={}".format(self.commit[:8]))
        if self.github:
            piezas.append("github={}".format(self.github))
        return " | ".join(piezas)


# --------------------------------------------------------------------------
# Registro de proyectos
# --------------------------------------------------------------------------
def cargar_registro() -> Dict[str, dict]:
    """Lee el registro de proyectos creados por la fabrica."""
    try:
        contenido = ruta_registro().read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {}
    try:
        datos = json.loads(contenido)
    except json.JSONDecodeError:
        return {}
    if isinstance(datos, dict) and isinstance(datos.get("proyectos"), dict):
        return datos["proyectos"]
    return {}


def guardar_registro(registro: Dict[str, dict]) -> None:
    """Escribe el registro (crea ``datos/`` si hace falta).

    La ruta se vuelve a validar aqui, en el punto exacto de la escritura: si
    alguien llama a esta funcion con una ruta manipulada, se rechaza antes de
    tocar el disco (regla SonarQube ``pythonsecurity:S2083``).
    """
    destino = _exigir_raiz_permitida(ruta_registro())
    destino.parent.mkdir(parents=True, exist_ok=True)
    volcado = {
        "actualizado": datetime.now().isoformat(timespec="seconds"),
        "proyectos": registro,
    }
    destino.write_text(
        json.dumps(volcado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def registrar_proyecto(proyecto: Proyecto) -> None:
    """Anade o actualiza la ficha del proyecto en el registro."""
    registro = cargar_registro()
    registro[proyecto.nombre] = asdict(proyecto)
    guardar_registro(registro)


def olvidar_proyecto(nombre: str) -> str:
    """Quita el proyecto del registro sin tocar su carpeta en disco."""
    limpio = rutas.normalizar_nombre(nombre)
    registro = cargar_registro()
    if limpio not in registro:
        raise ErrorFabrica(
            "El proyecto '{}' no esta en el registro. Registrados: {}.".format(
                limpio, ", ".join(sorted(registro)) or "(ninguno)"
            )
        )
    del registro[limpio]
    guardar_registro(registro)
    return "Quitado del registro '{}' (la carpeta sigue en disco).".format(limpio)


def ficha_proyecto(nombre: str) -> Proyecto:
    """Devuelve la ficha registrada de un proyecto."""
    limpio = rutas.normalizar_nombre(nombre)
    datos = cargar_registro().get(limpio)
    if not datos:
        raise ErrorFabrica(
            "Proyecto '{}' no registrado. Usa listar_proyectos para ver los disponibles.".format(
                limpio
            )
        )
    permitidos = {campo for campo in Proyecto.__dataclass_fields__}
    return Proyecto(**{clave: valor for clave, valor in datos.items() if clave in permitidos})


# --------------------------------------------------------------------------
# Procesos externos (git, gh, python)
# --------------------------------------------------------------------------
def hay_git() -> bool:
    """True si ``git`` esta disponible en el PATH."""
    return shutil.which("git") is not None


def hay_gh() -> bool:
    """True si ``gh`` (GitHub CLI) esta disponible en el PATH."""
    return shutil.which("gh") is not None


def _ejecutar(comando: List[str], cwd: Path, timeout: int = 300) -> Tuple[int, str]:
    """Ejecuta un proceso y devuelve ``(codigo, salida combinada)``.

    Raises:
        ErrorFabrica: si el ejecutable no existe o se pasa del tiempo.
    """
    try:
        proceso = subprocess.run(
            comando,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError:
        raise ErrorFabrica(
            "No se encontro el ejecutable '{}'. Instalalo o anadelo al PATH.".format(comando[0])
        )
    except subprocess.TimeoutExpired:
        raise ErrorFabrica(
            "'{}' tardo mas de {}s y se cancelo. Revisa la tarea a mano.".format(
                " ".join(comando), timeout
            )
        )
    salida = "{}\n{}".format(proceso.stdout or "", proceso.stderr or "").strip()
    return proceso.returncode, salida


def git_disponible() -> str:
    """Version de git instalada ('' si no hay git)."""
    if not hay_git():
        return ""
    codigo, salida = _ejecutar(["git", "--version"], cwd=configuracion.RAIZ_PROYECTO, timeout=30)
    return salida.splitlines()[0] if codigo == 0 and salida else ""


def _git(destino: Path, *argumentos: str, timeout: int = 300) -> Tuple[int, str]:
    """Ejecuta ``git`` con los argumentos indicados dentro del proyecto."""
    return _ejecutar(["git"] + list(argumentos), cwd=destino, timeout=timeout)


def _git_con_usuario(destino: Path, *argumentos: str) -> Tuple[int, str]:
    """Ejecuta git anadiendo la identidad configurada en el .env (si la hay)."""
    cfg = configuracion.cargar_fabrica()
    previos: List[str] = []
    if cfg.git_usuario:
        previos += ["-c", "user.name={}".format(cfg.git_usuario)]
    if cfg.git_email:
        previos += ["-c", "user.email={}".format(cfg.git_email)]
    return _git(destino, *(previos + list(argumentos)))


def inicializar_git(destino: Path, mensaje: str = MENSAJE_INICIAL) -> Tuple[bool, str, str]:
    """Hace ``git init`` + primer commit.

    Returns:
        ``(ok, detalle, hash_del_commit)``. Si algo falla, ``ok`` es ``False`` y
        ``detalle`` explica que paso sin lanzar excepcion: la fabrica prefiere
        entregar un proyecto sin git que ningun proyecto.
    """
    if not hay_git():
        return False, "git no esta instalado: proyecto creado sin repositorio.", ""

    codigo, salida = _git(destino, "init", "-b", "main")
    if codigo != 0:
        codigo, salida = _git(destino, "init")  # git antiguo sin soporte de -b
        if codigo != 0:
            return False, "git init fallo: {}".format(salida), ""

    codigo, salida = _git(destino, "add", "-A")
    if codigo != 0:
        return False, "git add fallo: {}".format(salida), ""

    codigo, salida = _git_con_usuario(destino, "commit", "-m", mensaje)
    if codigo != 0:
        if "user.email" in salida or "Please tell me who you are" in salida:
            return (
                False,
                "git no tiene identidad configurada. Define ARQUITECTO_GIT_USUARIO y "
                "ARQUITECTO_GIT_EMAIL en el .env (o ejecuta git config --global user.email "
                "\"tu@correo\"). El proyecto quedo con git init pero sin commit.",
                "",
            )
        if "nothing to commit" in salida:
            return True, "git inicializado (no habia nada que commitear).", ""
        return False, "git commit fallo: {}".format(salida), ""

    codigo, hash_commit = _git(destino, "rev-parse", "--short", "HEAD")
    return True, "git init + primer commit OK.", hash_commit.strip() if codigo == 0 else ""


# --------------------------------------------------------------------------
# Creacion de proyectos
# --------------------------------------------------------------------------
def crear_proyecto(
    nombre: str,
    descripcion: str = "",
    plantillas_seleccion=None,
    con_git: bool = True,
    publicar: Optional[bool] = None,
    visor: str = "",
    forzar: bool = False,
) -> str:
    """Crea un proyecto nuevo, lo rellena con plantillas y lo registra.

    Args:
        nombre: nombre libre del proyecto (se normaliza a slug seguro).
        descripcion: frase corta con el objetivo (va al README).
        plantillas_seleccion: claves de :mod:`plantillas` (por defecto, las del
            ``.env`` / ``ARQUITECTO_PLANTILLAS``).
        con_git: inicializa el repositorio y hace el primer commit.
        publicar: crea el repositorio remoto en GitHub con ``gh`` (``None`` =
            lo que diga ``ARQUITECTO_GITHUB``).
        visor: ``private`` o ``public`` (por defecto, ``ARQUITECTO_GITHUB_VISOR``).
        forzar: permite reutilizar una carpeta que ya tiene archivos.

    Returns:
        Informe en texto con lo que se creo, lo que fallo y los siguientes pasos.

    Raises:
        ErrorFabrica: si el nombre es invalido o la carpeta ya esta en uso.
    """
    limpio = rutas.normalizar_nombre(nombre)
    cfg = configuracion.cargar_fabrica()
    seleccion = plantillas_seleccion if plantillas_seleccion else cfg.plantillas_por_defecto

    destino = rutas.ruta_de_proyecto(limpio)
    if destino.exists():
        contenido = [hijo for hijo in destino.iterdir() if hijo.name not in {".git"}]
        if contenido and not forzar:
            raise ErrorFabrica(
                "Ya existe {} y no esta vacio ({} elementos). Usa forzar=True para reutilizarlo "
                "o elige otro nombre.".format(destino, len(contenido))
            )

    andamiaje = plantillas.construir(seleccion, limpio, descripcion)
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ErrorFabrica("No se pudo crear la carpeta {}: {}".format(destino, exc))

    escritos = archivos.escribir_varios(limpio, andamiaje.archivos)

    detalle_venv = "no creado (ARQUITECTO_CREAR_VENV=false)"
    if cfg.crear_venv:
        try:
            detalle_venv = _crear_venv(destino)
        except ErrorFabrica as exc:
            detalle_venv = "aviso: {}".format(exc)

    con_git_real = bool(con_git and hay_git())
    commit = ""
    detalle_git = "git desactivado por peticion."
    if con_git_real:
        _, detalle_git, commit = inicializar_git(destino)

    ficha = Proyecto(
        nombre=limpio,
        ruta=str(destino),
        descripcion=descripcion,
        plantillas=andamiaje.plantillas,
        creado=datetime.now().isoformat(timespec="seconds"),
        con_git=con_git_real and bool(commit),
        commit=commit,
        estado="creado",
    )

    quiere_publicar = cfg.github if publicar is None else bool(publicar)
    lineas = [
        "Proyecto '{}' creado en {}".format(limpio, destino),
        "- Archivos escritos: {}".format(len(escritos)),
        "- Plantillas: {}".format(", ".join(andamiaje.plantillas) or "base"),
        "- Entorno: {}".format(detalle_venv),
        "- Git: {}".format(detalle_git),
    ]
    if andamiaje.avisos:
        lineas.append("- Avisos: {}".format("; ".join(andamiaje.avisos)))

    if quiere_publicar:
        try:
            url = publicar_en_github(limpio, visor)
            lineas.append("- GitHub: publicado en {}".format(url or "(sin URL)"))
            ficha.github = url
        except ErrorFabrica as exc:
            lineas.append("- GitHub: no se pudo publicar ({})".format(exc))
            ficha.estado = "creado (sin publicar)"
    else:
        lineas.append(
            "- GitHub: omitido (activa ARQUITECTO_GITHUB=true o pasa publicar=True cuando "
            "quieras subirlo)."
        )

    registrar_proyecto(ficha)
    if andamiaje.notas:
        lineas.append("Siguientes pasos:")
        lineas.extend("  * {}".format(nota) for nota in andamiaje.notas)
    lineas.append(
        "Recuerda: el PROGRAMADOR trabaja siempre con proyecto='{}' y rutas relativas.".format(
            limpio
        )
    )
    return "\n".join(lineas)


# --------------------------------------------------------------------------
# Entorno virtual del proyecto
# --------------------------------------------------------------------------
def interprete_venv(destino: Path) -> Path:
    """Interprete del entorno virtual de un proyecto (Windows o POSIX).

    Devuelve el que ya exista; si todavia no hay ``venv/``, el que le tocaria
    segun la plataforma (``venv/Scripts/python.exe`` en Windows,
    ``venv/bin/python`` en macOS y Linux). Asi el mismo codigo funciona tanto en
    la maquina local como en un runner de GitHub Actions.
    """
    if os.name == "nt":
        candidatos = [destino / "venv" / "Scripts" / "python.exe", destino / "venv" / "bin" / "python"]
    else:
        candidatos = [destino / "venv" / "bin" / "python", destino / "venv" / "Scripts" / "python.exe"]
    for candidata in candidatos:
        if candidata.exists():
            return candidata
    return candidatos[0]


def _crear_venv(destino: Path) -> str:
    """Crea ``venv/`` dentro del proyecto (sin instalar dependencias).

    Returns:
        Mensaje legible del resultado.

    Raises:
        ErrorFabrica: si no se pudo crear el entorno virtual.
    """
    import sys

    if interprete_venv(destino).exists():
        return "ya existia venv/"

    codigo, salida = _ejecutar([sys.executable, "-m", "venv", "venv"], cwd=destino, timeout=300)
    if codigo != 0:
        raise ErrorFabrica("no se pudo crear el venv: {}".format(salida[-400:]))
    return "venv/ creado (dependencias pendientes: usa preparar_entorno)"


def preparar_entorno(nombre: str, instalar: bool = True, timeout: int = 900) -> str:
    """Crea ``venv/`` dentro del proyecto e instala ``requirements.txt``.

    Es un paso aparte (y lento) a proposito: crear el proyecto debe ser rapido e
    infalible; instalar dependencias puede tardar minutos o fallar por red.

    Args:
        nombre: proyecto registrado.
        instalar: instala las dependencias del ``requirements.txt`` si existe.
        timeout: segundos maximos para la instalacion.
    """
    import sys

    ficha = ficha_proyecto(nombre)
    destino = Path(ficha.ruta)
    if not destino.exists():
        raise ErrorFabrica("La carpeta del proyecto no existe: {}".format(destino))

    interprete = interprete_venv(destino)
    if not interprete.exists():
        codigo, salida = _ejecutar([sys.executable, "-m", "venv", "venv"], cwd=destino, timeout=300)
        if codigo != 0:
            raise ErrorFabrica("No se pudo crear el entorno virtual: {}".format(salida))
        lineas = ["Entorno virtual creado en venv/"]
    else:
        lineas = ["El entorno virtual ya existia."]

    requerimientos = destino / "requirements.txt"
    if instalar and requerimientos.exists():
        codigo, salida = _ejecutar(
            [
                str(interprete),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                "requirements.txt",
            ],
            cwd=destino,
            timeout=timeout,
        )
        if codigo != 0:
            raise ErrorFabrica("pip install fallo: {}".format(salida[-1500:]))
        lineas.append("Dependencias instaladas ({}).".format("requirements.txt"))
    elif not requerimientos.exists():
        lineas.append("Sin requirements.txt: nada que instalar.")

    lineas.append(
        "Usa el interprete del proyecto: {}".format(interprete)
    )
    return "\n".join("- {}".format(linea) for linea in lineas)


# --------------------------------------------------------------------------
# Git del proyecto
# --------------------------------------------------------------------------
def estado_git(nombre: str) -> str:
    """Muestra rama, cambios pendientes, ultimos commits y remotos."""
    ficha = ficha_proyecto(nombre)
    destino = Path(ficha.ruta)
    if not hay_git():
        return "git no esta instalado en esta maquina."
    if not (destino / ".git").exists():
        return "El proyecto '{}' no tiene repositorio git.".format(ficha.nombre)

    partes = []
    for etiqueta, argumentos in (
        ("Rama y cambios", ("status", "--short", "--branch")),
        ("Ultimos commits", ("log", "--oneline", "-5")),
        ("Remotos", ("remote", "-v")),
    ):
        codigo, salida = _git(destino, *argumentos, timeout=60)
        if codigo != 0:
            salida = salida or "(git devolvio un error)"
        partes.append("{}:\n{}".format(etiqueta, salida or "(sin informacion)"))
    return "Proyecto {}\n{}".format(ficha.nombre, "\n\n".join(partes))


def hacer_commit(nombre: str, mensaje: str) -> str:
    """Guarda todos los cambios del proyecto en un commit con el mensaje dado."""
    if not mensaje or not mensaje.strip():
        raise ErrorFabrica("Un commit necesita mensaje: describe brevemente el cambio.")
    ficha = ficha_proyecto(nombre)
    destino = Path(ficha.ruta)
    if not (destino / ".git").exists():
        raise ErrorFabrica("El proyecto '{}' no tiene repositorio git.".format(ficha.nombre))

    codigo, salida = _git(destino, "add", "-A")
    if codigo != 0:
        raise ErrorFabrica("git add fallo: {}".format(salida))

    codigo, salida = _git_con_usuario(destino, "commit", "-m", mensaje.strip())
    if codigo != 0:
        if "nothing to commit" in salida:
            return "Sin cambios que commitear en '{}'.".format(ficha.nombre)
        raise ErrorFabrica("git commit fallo: {}".format(salida))

    codigo, hash_commit = _git(destino, "rev-parse", "--short", "HEAD")
    if hash_commit:
        ficha.commit = hash_commit.strip()
        ficha.estado = "en progreso"
        registrar_proyecto(ficha)
    return "Commit {}: {}".format(hash_commit.strip(), mensaje.strip())


# --------------------------------------------------------------------------
# GitHub
# --------------------------------------------------------------------------
def publicar_en_github(
    nombre: str,
    visor: str = "",
    organizacion: str = "",
    nombre_repo: str = "",
) -> str:
    """Crea el repositorio remoto y sube el proyecto con ``gh``.

    Requiere GitHub CLI instalado y sesion iniciada (``gh auth login``). Si no lo
    esta, se lanza :class:`ErrorFabrica` con las instrucciones exactas.

    Returns:
        URL del repositorio creado.
    """
    cfg = configuracion.cargar_fabrica()
    ficha = ficha_proyecto(nombre)
    destino = Path(ficha.ruta)

    if not hay_gh():
        raise ErrorFabrica(
            "GitHub CLI (gh) no esta instalado. Instalalo y autenticate con:\n"
            "  winget install --id GitHub.cli\n"
            "  gh auth login\n"
            "Mientras tanto el proyecto vive perfectamente en local (git ya esta "
            "inicializado)."
        )

    codigo, salida = _ejecutar(["gh", "auth", "status"], cwd=destino, timeout=60)
    if codigo != 0:
        raise ErrorFabrica(
            "gh esta instalado pero sin sesion iniciada. Ejecuta 'gh auth login' y "
            "repitelo. Detalle: {}".format(salida[:400])
        )

    if not (destino / ".git").exists():
        _, detalle, _ = inicializar_git(destino)
        if not detalle:
            raise ErrorFabrica("No se pudo preparar el repositorio git del proyecto.")
    if not ficha.commit:
        hacer_commit(nombre, MENSAJE_INICIAL)

    repo = rutas.normalizar_nombre(nombre_repo or ficha.nombre)
    organizacion = (organizacion or cfg.github_org).strip().strip("/")
    destino_repo = "{}/{}".format(organizacion, repo) if organizacion else repo
    privacidad = "--private" if (visor or cfg.github_visor).lower() != "public" else "--public"

    comando = [
        "gh", "repo", "create", destino_repo,
        "--source", ".", "--remote", "origin", "--push", privacidad,
        "--description", (ficha.descripcion or "Proyecto creado por la fabrica de IA")[:350],
    ]
    codigo, salida = _ejecutar(comando, cwd=destino, timeout=300)
    if codigo != 0:
        raise ErrorFabrica(
            "gh repo create fallo: {}\n"
            "Revisa que el nombre '{}' este libre y que tu token tenga permiso para "
            "crear repositorios.".format(salida[-800:], destino_repo)
        )

    url = ""
    codigo, salida_url = _ejecutar(
        ["gh", "repo", "view", "--json", "url", "--jq", ".url"], cwd=destino, timeout=60
    )
    if codigo == 0:
        url = salida_url.strip()

    ficha.github = url
    ficha.estado = "publicado"
    registrar_proyecto(ficha)
    return url or "https://github.com/{}".format(destino_repo)


# --------------------------------------------------------------------------
# Consultas
# --------------------------------------------------------------------------
def listar_proyectos() -> str:
    """Lista los proyectos registrados y avisa de carpetas sin registrar."""
    cfg = configuracion.cargar_fabrica()
    registro = cargar_registro()

    lineas = ["Proyectos registrados ({}):".format(len(registro))]
    if not registro:
        lineas.append("  (ninguno todavia: usa crear_proyecto para nacer uno)")
    for nombre in sorted(registro):
        datos = registro[nombre]
        lineas.append("  - {}".format(Proyecto(**{
            clave: valor for clave, valor in datos.items()
            if clave in Proyecto.__dataclass_fields__
        }).resumen()))

    existentes = set()
    if cfg.raiz_proyectos.exists():
        existentes = {
            carpeta.name
            for carpeta in cfg.raiz_proyectos.iterdir()
            if carpeta.is_dir() and carpeta.name not in archivos.IGNORAR
        }
    sueltas = sorted(existentes - set(registro))
    if sueltas:
        lineas.append("Carpetas sin registrar (creadas a mano):")
        lineas.extend("  - {}".format(nombre) for nombre in sueltas)
    faltantes = sorted(set(registro) - existentes)
    if faltantes:
        lineas.append("Registrados cuya carpeta ya no esta:")
        lineas.extend("  - {}".format(nombre) for nombre in faltantes)
    lineas.append("Raiz de proyectos: {}".format(cfg.raiz_proyectos))
    return "\n".join(lineas)


def informe_proyecto(nombre: str, profundidad: int = 2) -> str:
    """Ficha, arbol de archivos y estado de git en un unico texto."""
    ficha = ficha_proyecto(nombre)
    partes = [
        "Ficha: {}".format(ficha.resumen()),
        "Ruta: {}".format(ficha.ruta),
        "Creado: {}".format(ficha.creado or "(sin fecha)"),
        "Plantillas: {}".format(", ".join(ficha.plantillas) or "base"),
    ]
    if ficha.descripcion:
        partes.append("Objetivo: {}".format(ficha.descripcion))
    try:
        partes.append(archivos.listar_proyecto(ficha.nombre, profundidad=profundidad))
    except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
        partes.append("No se pudo listar el contenido: {}".format(exc))
    try:
        partes.append(estado_git(ficha.nombre))
    except (ErrorFabrica, rutas.ErrorRuta) as exc:
        partes.append("Sin informacion de git: {}".format(exc))
    return "\n\n".join(partes)
