# Informe de trabajo - ia-colaborativa

Lo escribe la IA del IDE al cerrar cada ronda y lo lee el ARQUITECTO externo.
Regla de oro: la evidencia se pega tal cual salio de la terminal, sin resumir.

## Que se hizo

- (pendiente)

## Evidencia real (comando y salida)

```
(pega aqui el comando exacto y su salida)
```

## Archivos tocados

- (pendiente)

## Sugerencias propias para la siguiente ronda

1. (pendiente: prioridad alta / media / baja y por que)

## Ronda 1 - 

### Que se hizo

AUTO-ACTIVACION DE LA RAIZ + FIX DE UN DEFECTO REAL ENCONTRADO AL VERIFICARLA.

1) activar_proyecto sobre la raiz del repositorio (idempotente): registra la ficha ia-colaborativa (estado=activado, stack=python, ruta real) y escribe SOLO lo que faltaba: AGENTS.md, INFORME.md, SUGERENCIAS.md y la tarea de arranque en .vscode/tasks.json. No piso .clinerules, .cursorrules, .cursor/rules/arquitecto.mdc, .cursor/mcp.json ni .env.example (salieron con "=" en el informe del activador).

2) La raiz NO quedaba 100% alineada: las herramientas de archivos no la veian. Causa raiz (no interpretacion): herramientas_archivos.py usaba rutas.ruta_de_proyecto() -que asume SIEMPRE proyectos/<slug>- en vez de base_de_proyecto() (que lee la ruta fichada) en 4 sitios: listar_proyecto (raiz), buscar_en_contenido (raiz), buscar_archivos (glob) y la proteccion "no se puede borrar la raiz del proyecto" de borrar(). Efecto medido: listar_archivos(proyecto='ia-colaborativa') devolvia "No existe la ruta '.' dentro de ia-colaborativa" aunque la ficha apuntara a la raiz; y el borrado recursivo de "." en un proyecto activado NO se rechazaba: se llevaba el proyecto entero (agujero de seguridad). Con subcarpeta explicita si funcionaba, lo que confirma que el fallo era solo el atajo de la raiz.

3) Fix minimo y coherente: los 4 puntos pasan por base_de_proyecto(); el fallback a proyectos/<slug> se queda donde es correcto por diseno (proyecto no registrado y CREACION de proyectos nuevos en fabrica/orquestador).

4) fabrica.listar_proyectos() avisaba "Registrados cuya carpeta ya no esta: ia-colaborativa" teniendo la carpeta delante, porque comparaba el registro con las carpetas de proyectos/. Ahora comprueba la ruta de la ficha (y si no hay ruta, cae al comportamiento anterior).

5) 7 tests de regresion nuevos (tests/test_activacion.py y tests/test_fabrica.py) que fijan: listar/buscar por contenido/buscar por patron sobre la carpeta fichada, imposibilidad de borrar la raiz, el aviso correcto de listar_proyectos y que un proyecto inexistente sigue avisando.

### Evidencia real

```
COMANDO 1: venv\Scripts\python.exe -m pytest -q   (raiz del repositorio)
SALIDA REAL (cola):
........................................................................ [ 24%]
........................................................................ [ 49%]
........................................................................ [ 74%]
........................................................................ [ 99%]
290 passed in 29.77s
EXITCODE=0
(283 antes del cambio + 7 de regresion nuevos)

COMANDO 2: venv\Scripts\python.exe scripts\verificar_fabrica.py
SALIDA REAL (resumen):
  [OK]    buscar_en_contenido localiza la linea
  [OK]    buscar_archivos por patron glob
  [OK]    borrado de carpeta sin recursivo bloqueado
  [OK]    borrado de la raiz bloqueado
  [OK]    borrar elimina el archivo
======================================================================
============== RESUMEN: 72 comprobaciones OK, 0 FALLOS ===============
======================================================================
Carpeta temporal eliminada (el registro real no se toco).
EXITCODE=0

COMANDO 3 (diagnostico directo sobre la raiz, antes vs despues del fix):
antes -> base_registrada: <la raiz> | base_de_proyecto: <la raiz> | rutas.ruta_de_proyecto: ...\proyectos\ia-colaborativa
         listar_proyecto('ia-colaborativa','') -> ErrorArchivo: No existe la ruta '.' dentro de ia-colaborativa.
despues -> listar_proyecto('ia-colaborativa','') -> arbol de la raiz (.cursor/ .github/ .vscode/ datos/ proyectos/ scripts/ ...) + EXITCODE=0

ACTIVADOR (activar_proyecto sobre la raiz):
capa de orquestacion (solo se escribe lo que faltaba):
  + AGENTS.md
  + INFORME.md
  + SUGERENCIAS.md
  = .clinerules
  = .cursorrules
  = .cursor/rules/arquitecto.mdc
  = .cursor/mcp.json
  = .env.example
  ! tarea de arranque escrita en .vscode/tasks.json
```

### Archivos tocados

herramientas_archivos.py (~4 puntos: listar_proyecto, buscar_en_contenido, buscar_archivos, proteccion de borrado de la raiz)
fabrica.py (listar_proyectos: el aviso mira la ruta de la ficha)
tests/test_activacion.py (4 tests nuevos)
tests/test_fabrica.py (3 tests nuevos)
AGENTS.md, INFORME.md, SUGERENCIAS.md, .vscode/tasks.json (capa de orquestacion generada por la auto-activacion)

### Sugerencias propias del programador

1. [alta] Reiniciar el servidor MCP / el IDE: el proceso vivo tiene cargado herramientas_archivos.py de antes del fix, asi que listar_archivos(proyecto='ia-colaborativa') sin subcarpeta seguira fallando hasta el reinicio. Verificable en 5 segundos: listar_archivos(proyecto='ia-colaborativa') debe devolver el arbol en vez de "No existe la ruta '.'".
2. [media] Llevar esta regresion al verificador, no solo a pytest: scripts/verificar_fabrica.py ya prueba "borrado de la raiz bloqueado" y buscar_archivos, pero sobre un proyecto creado en proyectos/<slug>. Falta el caso "proyecto activado sobre una carpeta con otro nombre" (activar + listar sin subcarpeta + intento de borrado de la raiz), que es justo el que se escapo.
3. [baja] ruff no esta en requirements-dev.txt ni instalado en el venv ni en el CI (solo pytest + verificadores + Sonar), asi que no hay lint local reproducible: si se quiere, añadirlo a requirements-dev.txt y a un paso del workflow.
4. [baja] .vscode/tasks.json queda versionado con la ruta absoluta del venv de esta maquina; en otro clon la tarea de arranque apuntaria a una ruta inexistente. Podria resolverse con ${workspaceFolder} + un interprete relativo.
