# ia-colaborativa - contexto para agentes (IA colaborativa)

Orquestacion de dos IAs (arquitecto externo por API + programador del IDE) y fabrica de proyectos aislados

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
3. Trabaja siempre con `proyecto="ia-colaborativa"` y rutas relativas.
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
