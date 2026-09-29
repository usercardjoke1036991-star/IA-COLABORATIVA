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

## Ronda 2 - 

### Que se hizo

BLOQUE CERRADO Y PUBLICADO. Commit 0e4888e (7 archivos, +490/-8), push a origin/main OK y CI verde.

1) OPcion C ejecutada: candado nuevo en rutas.resolver llamado confinar_a_base. Con el activo (lo que piden las herramientas de archivos) se rechaza (a) cualquier segmento '..' en la ruta -porque resolve() colapsa './sub/..' a la propia raiz y confiar solo en la comparacion de rutas dejaba pasar esa forma- y (b) cualquier ruta resuelta que caiga fuera de la base declarada, incluidos los enlaces que apuntan fuera. El candado se comprueba ANTES de crear carpetas madres, asi que un intento rechazado no deja rastro. NO lo relaja ARQUITECTO_PERMITIR_EXTERNO a proposito: ese permiso sirve para elegir donde vive una carpeta, no para que una herramienta se salga de su proyecto (documentado en codigo y README).

2) Superficie entera cubierta: herramientas_archivos._resolver pasa confinar_a_base=True, asi que leer, escribir, crear_carpeta, mover (origen y destino), borrar, listar_proyecto, buscar_en_contenido, buscar_archivos e info_archivo quedan dentro del proyecto activo. activacion._escribir tambien lo pasa (misma politica al inyectar la capa).

3) Fuga por enlaces cerrada: nuevo filtro _fuera_del_proyecto + _recorrer(base=...) para que un symlink o junction hacia fuera no se liste, ni se busque, ni se lea; y mover ya no puede llevarse la raiz del proyecto.

4) Tests de regresion: 61 nuevos. tests/test_sandbox_herramientas.py recorre las 8 herramientas con los 5 ataques clasicos, comprueba rastro cero, vecino intacto (incluido el borrado recursivo de '..', que antes se llevaba la fabrica entera), enlaces de fichero y de carpeta, y el caso de proyecto ACTIVADO sobre ruta fichada. tests/test_rutas.py añade el candado a nivel unidad (incluido el caso Windows con barras invertidas, marcado skipif para que Linux siga verde).

5) scripts/verificar_fabrica.py paso 3: 5 comprobaciones nuevas de path traversal (leer/crear/borrar con '..' y '../vecino-secreto', vecino intacto, rastro cero). README: politica de sandbox documentada en las reglas de seguridad, en la seccion de sandbox y en la tabla de problemas.

6) PUBLICACION (Opcion A): git push 88905ff..0e4888e main -> main (subio tambien 9060490). git ls-remote origin: refs/heads/main = 0e4888ef6205e49045727a409a11c6e34b47813c. Arbol limpio y datos/ y proyectos/ sin tocar.

7) CI del SHA 0e4888e (run 36504285891): completed/success. Jobs: "Pruebas (windows-latest)" success, "Pruebas (ubuntu-latest)" success, "SonarQube" success; check-runs: SonarCloud Code Analysis = success. Sin solo-lectura de logs: leidos por API publica (gh esta instalado pero sin sesion).

Nota de metodo: el terminal integrado del IDE sigue roto (PSReadLine) y no captura stdout; todo se ha ejecutado con scripts .ps1 lanzados fuera del arbol del terminal (WMI) y leido de fichero. Una primera ejecucion concurrente ensucio los ficheros de evidencia y hubo que parar procesos y repetir con nombres versionados: los resultados que se pegan abajo son de la ejecucion unica final.

### Evidencia real

```
$ venv\Scripts\python.exe -m pytest -q
........................................................................ [ 20%]
........................................................................ [ 40%]
........................................................................ [ 61%]
........................................................................ [ 81%]
.............s..................................................         [100%]
SKIPPED [1] tests\test_sandbox_herramientas.py:177: esta maquina no permite crear enlaces
351 passed, 1 skipped in 117.10s (0:01:57)          -> pytest_exitcode=0
(antes de este bloque: 290 passed; los +61 son los tests nuevos)

$ venv\Scripts\python.exe -m pytest -q tests\test_sandbox_herramientas.py tests\test_rutas.py
82 passed, 1 skipped in 99.44s (0:01:39)           -> focus_exitcode=0

$ venv\Scripts\python.exe scripts\verificar_fabrica.py
PASO 3: Herramientas de archivos
  [OK]    escritura en .git bloqueada
  [OK]    ruta con '..' bloqueada
  [OK]    path traversal bloqueado en las herramientas (confinar_a_base)
  [OK]    borrado de '..' bloqueado
  [OK]    el proyecto vecino sigue intacto tras el intento
  [OK]    escritura en el proyecto vecino bloqueada
  [OK]    el intento rechazado no dejo rastro en el vecino
  [OK]    borrado de carpeta sin recursivo bloqueado
  [OK]    borrado de la raiz bloqueado
============== RESUMEN: 77 comprobaciones OK, 0 FALLOS ===============

$ git commit -m "fix(seguridad): confinar las herramientas de archivos al proyecto activo (path traversal)"
[main 0e4888e] 7 files changed, 490 insertions(+), 8 deletions(-)
 create mode 100644 tests/test_sandbox_herramientas.py
$ git push
To https://github.com/usercardjoke1036991-star/IA-COLABORATIVA.git
   88905ff..0e4888e  main -> main             -> push_exit=0
$ git ls-remote origin
0e4888ef6205e49045727a409a11c6e34b47813c        refs/heads/main

$ git status --porcelain          -> (vacio)
$ git status --porcelain -- datos proyectos -> (vacio)

API GitHub para 0e4888ef6205e49045727a409a11c6e34b47813c:
run=36504285891 | CI | status=completed | conclusion=success
  job=Pruebas (windows-latest) | completed | success
  job=Pruebas (ubuntu-latest)  | completed | success
  job=SonarQube                | completed | success
check_runs=4
  check=SonarCloud Code Analysis | completed | success

Fallo real encontrado y corregido durante el bloque (para que quede constancia):
  with pytest.raises(ErrorRuta, match="fuera del proyecto"): rutas.resolver("./sub/..", ...)
  E  Failed: DID NOT RAISE ErrorRuta
-> pathlib colapsa './sub/..' a la propia raiz del proyecto, asi que la comprobacion por
   comparacion de rutas no lo atrapaba: de ahi la regla explicita de rechazar '..' en parts.
```

### Archivos tocados

rutas.py
herramientas_archivos.py
activacion.py
scripts/verificar_fabrica.py
tests/test_rutas.py
tests/test_sandbox_herramientas.py (nuevo)
README.md

### Sugerencias propias del programador

1. Blindar el canal auxiliar de scripts: scripts/instalar.sh sigue llamando al interprete con ruta relativa sin comillas (venv/bin/python). Citar "$RAIZ/venv/bin/python" y anadir un guardian en verificar_fabrica.py + test que exija que toda llamada al interprete del venv en los scripts generados vaya entrecomillada. Es la clase de fallo que ya nos costo caro en la maquina de desarrollo.

2. Escribir la politica como regla, no como costumbre: "todo contenido EXISTENTE de un proyecto se lee/escribe via base_de_proyecto() (la ruta fichada)". Quedan llamadas a rutas.ruta_de_proyecto en orquestador.py y scripts/verificar_servidor.py (legitimas porque CREAN proyectos), pero conviene documentarlo en README/AGENTS y añadir un test que falle si una herramienta de archivos vuelve a asumir proyectos/<slug>.

3. Mismo tipo de riesgo en el registro: fabrica._carpeta_registro acepta una carpeta arbitraria del entorno cuando permitir_externo esta activo. Se podria exigir que el registro viva dentro de las raices o que el flag venga acompañado de una ruta explicita validada.

4. Endurecer buscar_archivos (y listar_proyecto) con patrones raros: '..' en el patron, rutas con separadores, patrones absolutos. Hoy el glob se evalua sobre raiz.rglob y no puede escapar, pero rechazarlos con mensaje claro evita sorpresas futuras.

5. CI: no hay lint. Anadir ruff (config minima en pyproject/ruff.toml) como paso del job pruebas daria una red barata contra errores de import/estilo en 30 s.

6. Opcional: repetir la suite en POSIX a mano no hace falta ya (ubuntu-latest paso en verde), pero el test de enlaces de fichero solo se ejecuta donde el sistema permite symlinks; en Windows se cubre con la junction. Documentarlo en el README de tests para que nadie borre ese skip pensando que no prueba nada.
