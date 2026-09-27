"""Servidor MCP: expone al Arquitecto Externo como herramientas de Cursor.

Es una capa **delgada**: toda la logica vive en ``arquitecto.py``. Aqui solo se
declaran las herramientas que la IA de Cursor puede llamar y se arranca el
transporte.

Herramientas expuestas
----------------------
ARQUITECTO (planifica)
  consultar_arquitecto    Dimensiona la idea y devuelve el plan de ataque inicial.
  reportar_progreso       Cierra el ciclo: valida lo hecho y dicta los siguientes pasos.
  ver_estado              Diagnostico del loop (configuracion e historial).
  exportar_plan           Vuelca el plan a PLAN_ARQUITECTO.md del proyecto.
  reiniciar_sesion        Olvida la memoria y empieza una sesion limpia.

FABRICA DE PROYECTOS
  estado_fabrica          Diagnostico: rutas, plantillas, git, gh y los dos modelos.
  catalogo_plantillas     Plantillas disponibles y sus notas de instalacion.
  crear_proyecto          Crea carpeta aislada + plantillas + git + registro.
  listar_proyectos        Proyectos creados por la fabrica.
  ver_proyecto            Ficha, arbol de archivos y estado de git.

ARCHIVOS (dentro de un proyecto, con sandbox)
  listar_archivos         Arbol de archivos de un proyecto.
  leer_archivo            Lee un archivo de texto con numeros de linea.
  escribir_archivo        Crea o reemplaza un archivo completo (UTF-8, LF).
  crear_carpeta           Crea carpetas dentro del proyecto.
  mover_archivo           Mueve o renombra.
  borrar_archivo          Borra archivo o carpeta (con recursivo=True).
  buscar_en_proyecto      Grep dentro del codigo del proyecto.
  buscar_archivos         Busqueda por patron glob.

ENTORNO, GIT Y GITHUB
  preparar_entorno        Crea el venv e instala requirements.txt.
  estado_git              Rama, cambios, commits y remotos.
  commit_proyecto         Guarda los cambios en un commit.
  publicar_en_github      Crea el repo remoto con gh y sube el proyecto.

PROGRAMADOR (segundo modelo: escribe el codigo)
  estado_programador        Diagnostico del rol (modelo, turnos, memoria).
  pedir_codigo_al_programador  Pide los archivos completos de una tarea.
  aplicar_codigo_del_programador  Aplica un texto con '### ARCHIVO:' al proyecto.
  corregir_con_el_programador  Devuelve un error real para que lo arregle.
  reiniciar_programador     Olvida la memoria del programador.

Uso
---
    python arquitecto_mcp.py             # arranca el servidor MCP por stdio (lo que usa Cursor)
    python arquitecto_mcp.py --check     # diagnostico de configuracion y conectividad
    python arquitecto_mcp.py --estado    # muestra el estado del loop actual
    python arquitecto_mcp.py --reiniciar # borra la memoria de la sesion

Nota: el transporte ``stdio`` reserva ``stdout`` para el protocolo JSON-RPC, por
eso todos los diagnosticos van a ``stderr`` y nunca se imprime en stdout mientras
el servidor esta en marcha.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading

import config as configuracion
import fabrica
import herramientas_archivos as archivos
import plantillas
import protocolo
import rutas
from arquitecto import NOMBRE_ARCHIVO_PLAN, Arquitecto
from ejecutor import Ejecutor

log = logging.getLogger("arquitecto.mcp")

_CERROJO = threading.Lock()
_ARQUITECTO = None
_EJECUTOR = None


# --------------------------------------------------------------------------
# Instancia unica (singleton) del Arquitecto
# --------------------------------------------------------------------------
def obtener_arquitecto() -> Arquitecto:
    """Devuelve la instancia compartida, creandola la primera vez."""
    global _ARQUITECTO
    with _CERROJO:
        if _ARQUITECTO is None:
            _ARQUITECTO = Arquitecto()
        return _ARQUITECTO


def obtener_ejecutor() -> Ejecutor:
    """Devuelve la instancia compartida del PROGRAMADOR (segundo modelo)."""
    global _EJECUTOR
    with _CERROJO:
        if _EJECUTOR is None:
            _EJECUTOR = Ejecutor()
        return _EJECUTOR


# --------------------------------------------------------------------------
# Construccion del servidor MCP
# --------------------------------------------------------------------------
def _importar_fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP  # import diferido a proposito
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "No se encontro el SDK de MCP.\n"
            "Instala las dependencias con:  pip install -r requirements.txt\n"
            "Detalle: {}".format(exc)
        )
    return FastMCP


def construir_servidor():
    """Crea el servidor FastMCP con todas las herramientas registradas."""
    FastMCP = _importar_fastmcp()
    servidor = FastMCP("ArquitectoExterno")

    @servidor.tool()
    def consultar_arquitecto(
        idea_del_usuario: str, contexto_del_codigo: str = ""
    ) -> str:
        """Llama al ARQUITECTO EXTERNO ANTES de escribir codigo para una idea nueva.

        El arquitecto NO programa: dimensiona el problema, detecta riesgos y
        devuelve un plan accionable que tu (PROGRAMADOR) debes implementar.

        Args:
            idea_del_usuario: El prompt o peticion original del usuario, tal cual.
            contexto_del_codigo: Opcional. Stack, estructura de archivos, restricciones
                o fragmentos relevantes del proyecto actual.

        Returns:
            El plan del arquitecto. Si el texto incluye
            "estado del loop: TAREA TERMINADA", deja de iterar.
        """
        try:
            respuesta = obtener_arquitecto().consultar(
                idea_del_usuario, contexto_del_codigo
            )
            return respuesta.formatear()
        except Exception as exc:  # nunca tumbar el servidor MCP
            log.exception("Fallo consultar_arquitecto")
            return protocolo.formatear_error(
                "Error en consultar_arquitecto: {}".format(exc)
            )

    @servidor.tool()
    def reportar_progreso(
        resumen_de_lo_hecho: str,
        prompt_original: str = "",
        archivos_tocados: str = "",
        bloqueo: str = "",
    ) -> str:
        """Cierra el ciclo: reporta al ARQUITECTO lo que acabas de implementar.

        Llamala SIEMPRE que termines un bloque de trabajo del plan, o cuando te
        bloquees. El arquitecto validara lo hecho y dictara los siguientes pasos.

        Args:
            resumen_de_lo_hecho: Que se implemento y con que resultado (obligatorio).
            prompt_original: La peticion original del usuario, para dar contexto.
            archivos_tocados: Rutas de los archivos creados o modificados.
            bloqueo: Opcional. El error o la duda concreta que te impide avanzar.

        Returns:
            Validacion y siguientes pasos. Si incluye
            "estado del loop: TAREA TERMINADA", deja de llamar al arquitecto.
        """
        try:
            respuesta = obtener_arquitecto().reportar_progreso(
                resumen_de_lo_hecho, prompt_original, archivos_tocados, bloqueo
            )
            return respuesta.formatear()
        except Exception as exc:
            log.exception("Fallo reportar_progreso")
            return protocolo.formatear_error(
                "Error en reportar_progreso: {}".format(exc)
            )

    @servidor.tool()
    def ver_estado() -> str:
        """Muestra el estado del loop: proveedor, modelo, turnos y ultimos turnos.

        No consume tokens: es solo diagnostico local.
        """
        try:
            return obtener_arquitecto().estado()
        except Exception as exc:
            return protocolo.formatear_error("Error en ver_estado: {}".format(exc))

    @servidor.tool()
    def exportar_plan(ruta: str = NOMBRE_ARCHIVO_PLAN) -> str:
        """Guarda el ultimo plan del arquitecto en un archivo Markdown del proyecto.

        Args:
            ruta: Ruta de destino, relativa al proyecto (def. PLAN_ARQUITECTO.md).
        """
        try:
            return obtener_arquitecto().exportar_plan(ruta)
        except Exception as exc:
            return protocolo.formatear_error("Error en exportar_plan: {}".format(exc))

    @servidor.tool()
    def reiniciar_sesion() -> str:
        """Borra la memoria del arquitecto para empezar un trabajo totalmente nuevo."""
        try:
            return obtener_arquitecto().reiniciar()
        except Exception as exc:
            return protocolo.formatear_error("Error en reiniciar_sesion: {}".format(exc))

    # ----------------------------------------------------------------------
    # FABRICA DE PROYECTOS: ciclo de vida del proyecto
    # ----------------------------------------------------------------------
    @servidor.tool()
    def estado_fabrica() -> str:
        """Diagnostico de la fabrica: rutas, plantillas, git, gh y los dos modelos.

        Llamalo al empezar una sesion de trabajo. No gasta tokens.
        """
        try:
            fabrica_cfg = configuracion.cargar_fabrica()
            planificador = configuracion.cargar()
            escritor = configuracion.cargar_ejecutor()
            return "\n".join(
                [
                    "=" * 58,
                    " FABRICA DE PROYECTOS ".center(58, "="),
                    "=" * 58,
                    "carpeta de proyectos   : {}".format(fabrica_cfg.raiz_proyectos),
                    "ya existe la carpeta   : {}".format(fabrica_cfg.raiz_proyectos.exists()),
                    "plantillas por defecto : {}".format(", ".join(fabrica_cfg.plantillas_por_defecto)),
                    "plantillas disponibles : {}".format(", ".join(plantillas.disponibles())),
                    "escritura externa      : {}".format(fabrica_cfg.permitir_externo),
                    "git                    : {}".format(fabrica.git_disponible() or "no instalado"),
                    "gh (GitHub CLI)        : {}".format(
                        "disponible" if fabrica.hay_gh() else "no instalado"
                    ),
                    "publicar en github     : {} ({})".format(
                        fabrica_cfg.github, fabrica_cfg.github_visor
                    ),
                    "orquestador            : {} (auto={}, turnos={})".format(
                        fabrica_cfg.orquestador, fabrica_cfg.cline_auto, fabrica_cfg.limite_turnos
                    ),
                    "ARQUITECTO (planifica) : {} / {}".format(
                        planificador.proveedor, planificador.modelo
                    ),
                    "PROGRAMADOR (escribe)  : {} / {}".format(
                        escritor.proveedor, escritor.modelo
                    ),
                    "=" * 58,
                    fabrica.listar_proyectos(),
                ]
            )
        except Exception as exc:  # el servidor MCP nunca debe caerse
            return protocolo.formatear_error("Error en estado_fabrica: {}".format(exc))

    @servidor.tool()
    def catalogo_plantillas() -> str:
        """Lista las plantillas de proyecto disponibles y sus notas de instalacion.

        Usalo antes de crear un proyecto para elegir bien las claves (se pueden
        combinar: 'python,web3' o 'python,fastapi,playwright').
        """
        try:
            return plantillas.describir()
        except Exception as exc:
            return protocolo.formatear_error("Error en catalogo_plantillas: {}".format(exc))

    @servidor.tool()
    def crear_proyecto(
        nombre: str,
        descripcion: str = "",
        plantillas_seleccion: str = "",
        con_git: bool = True,
        publicar: bool = False,
        visor: str = "",
    ) -> str:
        """Crea un proyecto nuevo en su carpeta aislada, con plantillas y git.

        Es el primer paso de cualquier idea que merezca su propio proyecto. La
        fabrica escribe solo dentro de su carpeta de proyectos (sandbox) y
        registra el proyecto en datos/proyectos.json.

        Args:
            nombre: nombre libre ('Bot de arbitraje'); se normaliza a slug.
            descripcion: una frase con el objetivo; acaba en el README.
            plantillas_seleccion: claves separadas por comas ('python,web3').
                Vacio = plantillas por defecto del .env.
            con_git: inicializa el repositorio y hace el primer commit.
            publicar: intenta crear y subir el repositorio en GitHub (requiere gh).
            visor: 'private' o 'public' (por defecto, lo del .env).

        Returns:
            Informe con la ruta, los archivos creados y los siguientes pasos.
        """
        try:
            return fabrica.crear_proyecto(
                nombre=nombre,
                descripcion=descripcion,
                plantillas_seleccion=plantillas.interpretar_seleccion(plantillas_seleccion) or None,
                con_git=con_git,
                publicar=publicar,
                visor=visor,
            )
        except (fabrica.ErrorFabrica, rutas.ErrorRuta, archivos.ErrorArchivo) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error inesperado en crear_proyecto: {}".format(exc))

    @servidor.tool()
    def listar_proyectos() -> str:
        """Lista los proyectos creados por la fabrica (registro + carpetas reales)."""
        try:
            return fabrica.listar_proyectos()
        except Exception as exc:
            return protocolo.formatear_error("Error en listar_proyectos: {}".format(exc))

    @servidor.tool()
    def ver_proyecto(proyecto: str, profundidad: int = 2) -> str:
        """Ficha, arbol de archivos y estado de git de un proyecto.

        Args:
            proyecto: nombre registrado del proyecto (slug).
            profundidad: niveles del arbol de archivos a mostrar.
        """
        try:
            return fabrica.informe_proyecto(proyecto, profundidad=profundidad)
        except (fabrica.ErrorFabrica, rutas.ErrorRuta, archivos.ErrorArchivo) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en ver_proyecto: {}".format(exc))

    # ----------------------------------------------------------------------
    # HERRAMIENTAS DE ARCHIVOS (siempre dentro de un proyecto de la fabrica)
    # ----------------------------------------------------------------------
    @servidor.tool()
    def listar_archivos(
        proyecto: str,
        subcarpeta: str = "",
        profundidad: int = 3,
        max_entradas: int = 200,
    ) -> str:
        """Arbol de archivos de un proyecto (o de una subcarpeta suya).

        Args:
            proyecto: nombre del proyecto; vacio lista los proyectos existentes.
            subcarpeta: subruta concreta ('src/app'), vacio = raiz del proyecto.
            profundidad: niveles a mostrar.
            max_entradas: tope de lineas para no llenar el contexto.
        """
        try:
            return archivos.listar_proyecto(proyecto, subcarpeta, profundidad, max_entradas)
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en listar_archivos: {}".format(exc))

    @servidor.tool()
    def leer_archivo(
        proyecto: str,
        ruta: str,
        desde: int = 1,
        hasta: int = 0,
    ) -> str:
        """Lee un archivo de texto del proyecto, con numeros de linea.

        Args:
            proyecto: nombre del proyecto.
            ruta: ruta relativa dentro del proyecto ('src/app/main.py').
            desde: primera linea (1 = principio).
            hasta: ultima linea (0 = hasta el final).
        """
        try:
            return archivos.leer_archivo(proyecto, ruta, desde=desde, hasta=hasta)
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en leer_archivo: {}".format(exc))

    @servidor.tool()
    def escribir_archivo(
        proyecto: str,
        ruta: str,
        contenido: str,
        sobreescribir: bool = True,
    ) -> str:
        """Crea o reemplaza un archivo de texto dentro del proyecto.

        Escribe el archivo COMPLETO en UTF-8 con saltos LF, creando las carpetas
        que falten. Rechaza rutas fuera del sandbox y la carpeta .git.

        Args:
            proyecto: nombre del proyecto.
            ruta: ruta relativa dentro del proyecto.
            contenido: texto completo del archivo.
            sobreescribir: False = falla si el archivo ya existe.
        """
        try:
            return archivos.escribir_archivo(proyecto, ruta, contenido, sobreescribir)
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en escribir_archivo: {}".format(exc))

    @servidor.tool()
    def crear_carpeta(proyecto: str, ruta: str) -> str:
        """Crea una carpeta (con sus padres) dentro del proyecto.

        Args:
            proyecto: nombre del proyecto.
            ruta: ruta relativa de la carpeta ('docs/notas').
        """
        try:
            return archivos.crear_carpeta(proyecto, ruta)
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en crear_carpeta: {}".format(exc))

    @servidor.tool()
    def mover_archivo(proyecto: str, origen: str, destino: str) -> str:
        """Mueve o renombra un archivo o carpeta dentro del proyecto.

        Args:
            proyecto: nombre del proyecto.
            origen: ruta relativa actual.
            destino: ruta relativa nueva (no debe existir).
        """
        try:
            return archivos.mover(proyecto, origen, destino)
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en mover_archivo: {}".format(exc))

    @servidor.tool()
    def borrar_archivo(proyecto: str, ruta: str, recursivo: bool = False) -> str:
        """Borra un archivo o carpeta del proyecto (con confirmacion explicita).

        Args:
            proyecto: nombre del proyecto.
            ruta: ruta relativa a borrar.
            recursivo: obligatorio (True) para borrar una carpeta con contenido.
        """
        try:
            return archivos.borrar(proyecto, ruta, recursivo)
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en borrar_archivo: {}".format(exc))

    @servidor.tool()
    def buscar_en_proyecto(
        proyecto: str,
        texto: str,
        subcarpeta: str = "",
        max_resultados: int = 40,
    ) -> str:
        """Busca un texto dentro del codigo del proyecto (estilo grep).

        Indispensable antes de reescribir un archivo: devuelve ruta:linea:contenido
        y omite ruido (venv, node_modules, .git).

        Args:
            proyecto: nombre del proyecto.
            texto: fragmento a buscar (nombres de funcion, imports, cadenas...).
            subcarpeta: limita la busqueda a una subruta.
            max_resultados: tope de coincidencias devueltas.
        """
        try:
            return archivos.buscar_en_contenido(proyecto, texto, subcarpeta, max_resultados)
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en buscar_en_proyecto: {}".format(exc))

    @servidor.tool()
    def buscar_archivos(proyecto: str, patron: str, max_resultados: int = 60) -> str:
        """Busca archivos por patron glob ('*.py', '**/test_*.py', 'main?.js').

        Args:
            proyecto: nombre del proyecto.
            patron: patron glob a buscar.
            max_resultados: tope de resultados.
        """
        try:
            return archivos.buscar_archivos(proyecto, patron, max_resultados)
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en buscar_archivos: {}".format(exc))

    # ----------------------------------------------------------------------
    # ENTORNO VIRTUAL, GIT Y GITHUB
    # ----------------------------------------------------------------------
    @servidor.tool()
    def preparar_entorno(proyecto: str, instalar: bool = True) -> str:
        """Crea el venv del proyecto e instala sus dependencias.

        Es un paso aparte (y lento) para que crear el proyecto sea instantaneo.
        Llamalo una vez despues de crear_proyecto.

        Args:
            proyecto: nombre del proyecto registrado.
            instalar: instala las dependencias del requirements.txt.
        """
        try:
            return fabrica.preparar_entorno(proyecto, instalar=instalar)
        except (fabrica.ErrorFabrica, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en preparar_entorno: {}".format(exc))

    @servidor.tool()
    def estado_git(proyecto: str) -> str:
        """Rama, cambios pendientes, ultimos commits y remotos del proyecto.

        Args:
            proyecto: nombre del proyecto registrado.
        """
        try:
            return fabrica.estado_git(proyecto)
        except (fabrica.ErrorFabrica, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en estado_git: {}".format(exc))

    @servidor.tool()
    def commit_proyecto(proyecto: str, mensaje: str) -> str:
        """Guarda los cambios del proyecto en un commit.

        Cierra cada bloque de trabajo con un commit: es la red de seguridad que
        permite volver atras si la siguiente iteracion rompe algo.

        Args:
            proyecto: nombre del proyecto registrado.
            mensaje: resumen corto del cambio (estilo 'feat: ...' o 'fix: ...').
        """
        try:
            return fabrica.hacer_commit(proyecto, mensaje)
        except (fabrica.ErrorFabrica, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en commit_proyecto: {}".format(exc))

    @servidor.tool()
    def publicar_en_github(
        proyecto: str,
        visor: str = "",
        organizacion: str = "",
        nombre_repo: str = "",
    ) -> str:
        """Crea el repositorio remoto en GitHub y sube el proyecto.

        Requiere GitHub CLI ('gh') instalado y con sesion iniciada ('gh auth login').
        Si no esta, devuelve las instrucciones exactas sin romper nada.

        Args:
            proyecto: nombre del proyecto registrado.
            visor: 'private' o 'public' (vacio = lo del .env).
            organizacion: usuario u organizacion destino (vacio = la de gh).
            nombre_repo: nombre del repositorio remoto (vacio = el del proyecto).
        """
        try:
            url = fabrica.publicar_en_github(proyecto, visor, organizacion, nombre_repo)
            return "Repositorio publicado: {}".format(url)
        except (fabrica.ErrorFabrica, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en publicar_en_github: {}".format(exc))

    # ----------------------------------------------------------------------
    # ROL PROGRAMADOR EXTERNO (segundo modelo: escribe el codigo)
    # ----------------------------------------------------------------------
    @servidor.tool()
    def estado_programador() -> str:
        """Diagnostico del rol PROGRAMADOR (modelo, turnos y memoria). No gasta tokens."""
        try:
            return obtener_ejecutor().estado()
        except Exception as exc:
            return protocolo.formatear_error("Error en estado_programador: {}".format(exc))

    @servidor.tool()
    def pedir_codigo_al_programador(
        tarea: str,
        plan: str = "",
        contexto: str = "",
        proyecto: str = "",
        aplicar: bool = False,
    ) -> str:
        """Pide al PROGRAMADOR EXTERNO (segundo modelo) el codigo completo de una tarea.

        El ARQUITECTO decide y el PROGRAMADOR escribe. Usalo cuando la tarea este
        bien definida y quieras los archivos completos de una vez.

        Args:
            tarea: que hay que implementar, en concreto.
            plan: plan del arquitecto (pega el resultado de consultar_arquitecto).
            contexto: codigo actual, convenciones, restricciones o salida de error.
            proyecto: nombre del proyecto; se usa como contexto y, con
                aplicar=True, para escribir los archivos en su carpeta.
            aplicar: True = guarda en el proyecto los archivos entregados.

        Returns:
            La respuesta del programador (archivos + pasos) y, si aplicar=True, el
            detalle de lo que se escribio.
        """
        try:
            rol = obtener_ejecutor()
            respuesta = rol.implementar(tarea, plan=plan, contexto=contexto, proyecto=proyecto)
            texto = rol.formatear(respuesta)
            if not aplicar:
                return texto
            if not (proyecto or "").strip():
                return texto + "\n\n[aplicar=True exige indicar 'proyecto': no se escribio nada]"
            entregados = rol.archivos_de(respuesta)
            if not entregados:
                return texto + "\n\n[no se detectaron archivos que aplicar]"
            mensajes = archivos.escribir_varios(proyecto, dict(entregados))
            return "{}\n\nAPLICADO en '{}':\n{}".format(
                texto, proyecto, "\n".join("  - {}".format(m) for m in mensajes)
            )
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en pedir_codigo_al_programador: {}".format(exc))

    @servidor.tool()
    def aplicar_codigo_del_programador(proyecto: str, codigo: str) -> str:
        """Escribe en el proyecto los archivos de un texto con formato '### ARCHIVO:'.

        Sirve cuando el codigo viene de fuera (otra IA, un chat, el orquestador):
        se validan las rutas contra el sandbox y se guardan los archivos completos.

        Args:
            proyecto: nombre del proyecto destino.
            codigo: texto con bloques '### ARCHIVO: ruta' seguidos de un bloque de
                codigo cercado con triple comilla.

        Returns:
            La lista de archivos escritos, o el aviso de que no se detecto ninguno.
        """
        try:
            entregados = protocolo.extraer_archivos(codigo)
            if not entregados:
                return (
                    "No se detecto ningun archivo: usa el formato '### ARCHIVO: ruta' "
                    "seguido de un bloque de codigo cercado con triple comilla."
                )
            mensajes = archivos.escribir_varios(proyecto, dict(entregados))
            return "Archivos aplicados en '{}':\n{}".format(
                proyecto, "\n".join("  - {}".format(m) for m in mensajes)
            )
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error(
                "Error en aplicar_codigo_del_programador: {}".format(exc)
            )

    @servidor.tool()
    def corregir_con_el_programador(
        proyecto: str,
        error: str,
        codigo_previo: str = "",
        intento: int = 1,
        aplicar: bool = False,
    ) -> str:
        """Devuelve un error real de ejecucion al PROGRAMADOR para que lo corrija.

        Args:
            proyecto: nombre del proyecto.
            error: salida real del fallo (traza de pytest, stderr, sintoma).
            codigo_previo: codigo que fallo (opcional, ayuda a acertar antes).
            intento: numero de intento, para que sepa que ya fallo antes.
            aplicar: True = escribe los archivos corregidos en el proyecto.
        """
        try:
            rol = obtener_ejecutor()
            respuesta = rol.corregir(error, codigo_previo=codigo_previo, intento=intento)
            texto = rol.formatear(respuesta)
            if not aplicar:
                return texto
            entregados = rol.archivos_de(respuesta)
            if not entregados:
                return texto + "\n\n[no se detectaron archivos que aplicar]"
            mensajes = archivos.escribir_varios(proyecto, dict(entregados))
            return "{}\n\nAPLICADO en '{}':\n{}".format(
                texto, proyecto, "\n".join("  - {}".format(m) for m in mensajes)
            )
        except (archivos.ErrorArchivo, rutas.ErrorRuta) as exc:
            return protocolo.formatear_error(str(exc))
        except Exception as exc:
            return protocolo.formatear_error("Error en corregir_con_el_programador: {}".format(exc))

    @servidor.tool()
    def reiniciar_programador() -> str:
        """Olvida la memoria del PROGRAMADOR sin tocar la del ARQUITECTO."""
        try:
            return obtener_ejecutor().reiniciar()
        except Exception as exc:
            return protocolo.formatear_error("Error en reiniciar_programador: {}".format(exc))

    # -- fin de las herramientas del programador ---------------------------
    return servidor
    return servidor


# --------------------------------------------------------------------------
# Diagnostico y linea de comandos
# --------------------------------------------------------------------------
def _recorte(texto: str, limite: int = 160) -> str:
    limpio = " ".join((texto or "").split())
    return limpio if len(limpio) <= limite else limpio[:limite] + "..."


def _diagnostico(config, hacer_ping: bool = True) -> int:
    """Comprueba configuracion y, opcionalmente, conectividad real. Devuelve codigo de salida."""
    from proveedores import ErrorProveedor, ProveedorLLM, ProveedorMock

    ancho = 58
    print("=" * ancho)
    print(" ARQUITECTO EXTERNO - DIAGNOSTICO ".center(ancho, "="))
    print("-" * ancho)
    print("configuracion: {}".format(config.resumen()))
    print(
        "archivo .env: {}".format(
            configuracion.RUTA_ENV
            if configuracion.RUTA_ENV.exists()
            else "(no existe; solo se leyo el entorno del sistema)"
        )
    )

    problemas = config.problemas()
    if problemas:
        print("-" * ancho)
        print("PROBLEMAS DE CONFIGURACION:")
        for fallo in problemas:
            print(" - {}".format(fallo))
        print("-" * ancho)
        print("Solucion: copia .env.example a .env, rellena la clave y reintenta.")
        return 2

    print("configuracion valida: sin problemas detectados.")
    if not hacer_ping:
        print("ping omitido (--no-ping).")
        return 0

    print("-" * ancho)
    print("probando la cadena completa (mensaje -> modelo -> respuesta)...")
    try:
        import time

        if config.modo_mock:
            proveedor = ProveedorMock(config)
            mensaje = "Diagnostico del modo simulado."
        else:
            proveedor = ProveedorLLM(config)
            mensaje = "Responde unicamente con la palabra OK."
        inicio = time.time()
        texto = proveedor.consultar([{"role": "user", "content": mensaje}], max_tokens=32)
        print(
            "OK en {:.1f}s | modelo={} | respuesta: {}".format(
                time.time() - inicio, config.modelo, _recorte(texto)
            )
        )
        return 0
    except ErrorProveedor as exc:
        print("FALLO: {}".format(exc))
        print("-" * ancho)
        print("Revisa modelo, URL y clave. Detalle completo en los logs (stderr).")
        return 1
    except Exception as exc:  # defensivo
        print("FALLO inesperado: {}".format(exc))
        return 1


def main(argv=None) -> int:
    """Punto de entrada: arranca el servidor MCP o ejecuta las tareas de diagnostico."""
    import os

    analizador = argparse.ArgumentParser(
        prog="arquitecto_mcp",
        description=(
            "Arquitecto Externo MCP: una IA externa que planifica y aconseja "
            "mientras la IA de Cursor programa."
        ),
    )
    analizador.add_argument(
        "--check", action="store_true", help="diagnostico de configuracion y conectividad"
    )
    analizador.add_argument(
        "--no-ping", action="store_true", help="con --check, no llama a la API externa"
    )
    analizador.add_argument(
        "--estado", action="store_true", help="muestra el estado del loop y sale"
    )
    analizador.add_argument(
        "--reiniciar", action="store_true", help="borra la memoria del arquitecto y sale"
    )
    analizador.add_argument(
        "--http", action="store_true", help="modo HTTP opcional (por defecto stdio, lo que usa Cursor)"
    )
    argumentos = analizador.parse_args(argv)

    config = configuracion.cargar()
    configuracion.configurar_log(config.nivel_log)

    if argumentos.check:
        return _diagnostico(config, hacer_ping=not argumentos.no_ping)
    if argumentos.estado:
        print(obtener_arquitecto().estado())
        return 0
    if argumentos.reiniciar:
        print(obtener_arquitecto().reiniciar())
        return 0

    servidor = construir_servidor()

    if argumentos.http:
        try:
            servidor.settings.host = os.getenv("ARQUITECTO_HTTP_HOST", "127.0.0.1")
            servidor.settings.port = int(os.getenv("ARQUITECTO_HTTP_PORT", "8765"))
        except (AttributeError, ValueError):
            pass
        log.info(
            "Servidor MCP en modo HTTP: http://%s:%s/mcp",
            os.getenv("ARQUITECTO_HTTP_HOST", "127.0.0.1"),
            os.getenv("ARQUITECTO_HTTP_PORT", "8765"),
        )
        try:
            servidor.run(transport="streamable-http")
            return 0
        except (ValueError, KeyError):
            log.warning("Este SDK no soporta 'streamable-http'; se usa el transporte SSE.")
            servidor.run(transport="sse")
            return 0

    log.info("Servidor MCP listo por stdio. %s", config.resumen())
    servidor.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
