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

## Ronda 3 - 

### Que se hizo

RONDA 3 CERRADA Y PUBLICADA (commits 97430d0 y d05d3e7; CI en verde para los dos SHA). Se hicieron las dos sugerencias de valor alto que pediste, en el orden que marcaste.

1) [Sugerencia 1] Interprete del venv citado en scripts shell. En scripts/instalar.sh las 5 llamadas pasan a "$RAIZ/venv/bin/python" (y el test [[ -x ]] tambien), con un comentario que explica por que. Ojo: la ruta ABSOLUTA y citada, no "venv/bin/python", porque el cd del script no protege de una ruta con espacios si algo se ejecuta fuera de el.

2) [Sugerencia 1] Guardian en scripts/verificar_fabrica.py (paso 2): _lineas_sin_comillas() + _textos_sh() + _revisar_scripts_sh(). Revisa los .sh del repositorio Y los que genere la fabrica (hoy ninguno: la fabrica solo genera .ps1, pero el guardian queda puesto). Ignora a proposito las lineas de echo/printf y los comentarios (son texto, no llamadas) y soporta las cuatro formas del interprete: venv/bin/python, venv/bin/python3.14, venv/Scripts/python.exe y pythonw.exe. 4 tests unitarios nuevos en tests/test_verificar_fabrica.py (deteccion, casos correctos/echo/comentario, repositorio real, y scripts generados).

3) [Sugerencia 2] Candado de la politica base_de_proyecto() en tests/test_politica_rutas.py (3 tests, inspeccion estatica con ast): (a) en herramientas_archivos.py las UNICAS funciones que pueden llamar a rutas.ruta_de_proyecto son las de la allowlist FUNCIONES_CON_SLUG_JUSTIFICADO (hoy solo base_de_proyecto, el fallback de un proyecto sin ficha): si alguien reinserta el slug en listar/buscar/leer/escribir/borrar, el test falla con el nombre de la funcion culpable; (b) _resolver tiene que resolver via base_de_proyecto(); (c) allowlist PUEDEN_CREAR para los modulos donde crear proyecto por slug si es legitimo (fabrica, orquestador, verificadores y sus dobles). Documentada la regla en README (reglas de seguridad), en la plantilla AGENTS.md de plantillas.py (punto 8, propaga a todo proyecto nuevo) y en el AGENTS.md de este repo.

4) Hallazgo del test (mejor granularidad de la que yo habia disenado): herramientas_archivos.py SI nombra ruta_de_proyecto, dentro de base_de_proyecto() (fallback para un proyecto sin ficha). Mi primer intento prohibia el modulo entero y era falso positivo; ahora el candado es por FUNCION, que es exactamente el defecto real (4 funciones lo usaban donde no tocaba).

5) Hallazgo de higiene del repositorio: IA COLABORATIVA.py (raiz) NO es Python: es el volcado de la conversacion original guardado con extension .py (SyntaxError en la linea 12). El candado AST lo salta; propongo limpiarlo (moverlo a docs/ o borrarlo) en la proxima ronda.

6) Prueba negativa ejecutada de verdad (no solo afirmada): reintroduje el bug en listar_proyecto, el test fallo con el mensaje exacto, restaure la copia (hash SHA-256 identico) y volvio a verde. Es la evidencia de que el candado muerde.

7) PUBLICACION: push 97430d0 y d05d3e7 a origin/main; CI run 36506857344 (d05d3e7) completed/success con Pruebas (ubuntu-latest), Pruebas (windows-latest), SonarQube y SonarCloud Code Analysis en success; el run 36506496250 (97430d0) tambien en success. Arbol limpio; datos/ y proyectos/ intactos.

### Evidencia real

```
$ bash -n scripts/instalar.sh
bash -n scripts/instalar.sh -> OK (sin errores de sintaxis)

$ grep -n 'venv/bin/python' scripts/instalar.sh      (lo que queda)
19:if [[ ! -x "$RAIZ/venv/bin/python" ]]; then
29:"$RAIZ/venv/bin/python" -m pip install --upgrade pip --quiet
30:"$RAIZ/venv/bin/python" -m pip install -r requirements.txt --quiet
42:"$RAIZ/venv/bin/python" scripts/registrar_mcp.py
45:"$RAIZ/venv/bin/python" scripts/verificar_servidor.py
46:"$RAIZ/venv/bin/python" scripts/verificar_fabrica.py
51:echo "  $RAIZ/venv/bin/python"                      <- texto de echo (solo imprime)
55:echo "  venv/bin/python arquitecto_mcp.py --check"   <- idem
57:echo "  venv/bin/python orquestador.py --idea ..."   <- idem
No queda ninguna LLAMADA sin comillas.

$ prueba real con bash en una ruta con espacios (/tmp/prueba venv comillas/venv/bin/python)
=== 3. Ruta con espacios: CON comillas (lo que hace ahora instalar.sh) ===
interprete invocado: /tmp/prueba venv comillas/venv/bin/python
EXIT=0
=== 4. Ruta con espacios: SIN comillas (el fallo antiguo) ===
prueba_comillas.sh: line 36: /tmp/prueba: No such file or directory
EXIT=127

$ pytest foco (politica + shell + plantillas)
37 passed in 12.93s                                     -> focus_exitcode=0

$ venv\Scripts\python.exe -m pytest -q
364 passed, 1 skipped in 98.03s (0:01:38)
(el skip es el symlink de fichero, que en Windows pide privilegios; la fuga por junction SI se prueba)

$ venv\Scripts\python.exe scripts\verificar_fabrica.py
  [OK]    interprete del venv entrecomillado en los scripts de shell -> 1 script(s) revisados
============== RESUMEN: 78 comprobaciones OK, 0 FALLOS ===============

Prueba NEGATIVA del candado de politica (bug reintroducido a proposito en listar_proyecto):
$ pytest -q tests\test_politica_rutas.py
E  AssertionError: herramientas_archivos.py llama a rutas.ruta_de_proyecto desde
   base_de_proyecto, listar_proyecto: para contenido que ya existe usa base_de_proyecto()
E    assert {'base_de_pro...tar_proyecto'} <= {'base_de_proyecto'}
     Extra items in the left set: 'listar_proyecto'
1 failed, 2 passed                                       -> negativo_exitcode=1
hash_antes=927994B08C598D0F91D3102855CF140FA1760CD78ACFF823213257CC1829B0A6
hash_despues=927994B08C598D0F91D3102855CF140FA1760CD78ACFF823213257CC1829B0A6  (intacto)
$ pytest -q tests\test_politica_rutas.py
3 passed in 0.40s                                        -> revertido_exitcode=0

$ git log --oneline -3
d05d3e7 docs: corregir una palabra del docstring en tests/test_politica_rutas.py
97430d0 fix(scripts): citar el interprete del venv en los .sh y candado de la politica de rutas
0e4888e fix(seguridad): confinar las herramientas de archivos al proyecto activo (path traversal)
$ git push -> 97430d0..d05d3e7  main -> main (push_exit=0); git status --porcelain -> vacio
$ git status --porcelain -- datos proyectos -> vacio

CI (API GitHub):
run=36506496250 (97430d0) | completed | success -> Pruebas (ubuntu), Pruebas (windows), SonarQube
run=36506857344 (d05d3e7) | completed | success
  job=Pruebas (ubuntu-latest) | success
  job=Pruebas (windows-latest) | success
  job=SonarQube | success
  check=SonarCloud Code Analysis | completed | success
```

### Archivos tocados

scripts/instalar.sh
scripts/verificar_fabrica.py
tests/test_politica_rutas.py (nuevo)
tests/test_verificar_fabrica.py
plantillas.py
AGENTS.md
README.md

### Sugerencias propias del programador

1. Limpiar IA COLABORATIVA.py: no es Python valido (volcado de chat de la idea original). Moverlo a docs/idea-original.md y borrar el .py evita que cualquier herramienta futura (o un guardián AST mas estricto) tropiece con el.

2. Extender el guardián de comillas al canal PowerShell: hoy el paso 2 revisa los .ps1 con una comprobacion de texto simple ('venv\Scripts\python.exe' in contenido) y no verifica el entrecomillado. Un chequeo equivalente a _lineas_sin_comillas para .ps1/.bat/.cmd cerraria la misma clase de fallo en Windows.

3. Anadir `bash -n` de los .sh al CI (ubuntu-latest lo tiene): es un paso de 2 segundos que cierra el canal POSIX de verdad, en la plataforma donde esos scripts se ejecutan.

4. El guardián actual vive en verificar_fabrica.py (solo corre en Windows en el CI). Si quieres que el candado de comillas proteja tambien en Linux, moverlo a un modulo compartido (por ejemplo rutas.py o un nuevo scripts/revisar_scripts.py) y llamarlo desde los dos verificadores.

5. Fix rapido de coherencia: el [1/4]...[5/5] de scripts/instalar.sh esta desalineado (hay un [4/5] y un [5/5] despues de un [3/4]). Cosmetico, pero se ve en la primera instalacion del usuario.

## Ronda 4 - 

### Que se hizo

RONDA 4 CERRADA Y PUBLICADA. Tres commits: 750f447 (endurecimiento), 8565214 (fix del quality gate). CI en verde para el SHA final y SonarCloud en A.

1) [Sugerencia 3] Vectores de Windows cerrados en confinar_a_base, con rechazo TEMPRANO (antes de tocar disco) y mensaje propio: rutas absolutas y *rooted* -letra de unidad C:\, raices \ o /, dispositivo \\?\, \\.\, recurso de red \\host\recurso- y nombres reservados en CUALQUIER tramo (CON, NUL, COM1, aux.md, con.txt, carpeta/nul/x.txt). El candado se probo con 28 tests nuevos y con 1 comprobacion nueva en el verificador.

2) Hallazgo tecnico del propio test: en Windows Path("/etc/passwd") NO es is_absolute() (esta rooted pero sin unidad); al unirlo a la base se lleva por delante la raiz y acababa bloqueado por el mensaje equivocado. Ahora la condicion mira tambien si la ruta empieza por separador, con el comentario explicando por que. Es exactamente el tipo de evasion que pediste cubrir.

3) Coherencia del candado: el permiso ARQUITECTO_PERMITIR_EXTERNO NO abre ni las absolutas ni los recursos de red (test dedicado). Riesgo que señalaste (no romper rutas legitimas) cubierto al contrario: test nuevo con espacios, acentos/ñ, puntos y guiones ('docs/notas finales.md', 'src/ñandú/áéí.py', 'api/v2.1/x.json') que siguen pasando y no crean archivos.

4) INCIDENCIA REAL EN PRODUCCION durante esta ronda y como se resolvio: al leer el CI del primer push (750f447) el check 'SonarCloud Code Analysis' salio en FAILURE con Quality Gate fallado por 'D Security Rating on New Code'. Localice la regla por la API publica de SonarCloud: python:S5443 (CRITICAL) en scripts/verificar_fabrica.py:343 por usar el literal "/tmp/secreto.txt" (directorio publicamente escribible). Arreglado construyendo esas rutas con tempfile.gettempdir(), y de paso los tests de absolutas ahora plantan un SENUELO real (un archivo de verdad fuera del proyecto) para que pytest.raises no pueda pasar por el motivo equivocado.

5) Estado final verificado: SHA 8565214 publicado; CI run 36511234685 completed/success (Pruebas windows, Pruebas ubuntu y SonarQube); SonarCloud Code Analysis success con 0 New issues, 0 Security Hotspots y new_security_rating=1.0 (A, antes 4.0/D). Arbol limpio, datos/ y proyectos/ intactos.

6) BLOQUEO DEL ARQUITECTO (lo reporto aunque no es tuyo): dos llamadas a sugerir_mejoras devolvieron 'El proveedor devolvio una respuesta vacia' (loop en pausa). Segui el plan VIGENTE que ya habias dictado en la ronda 2 ('implementa 1 y 2 ... luego 3') en lugar de improvisar, y cierro aqui con este informe para que valides. Si el proveedor sigue caido, la ronda 5 (lint ruff + fabrica._carpeta_registro con permitir_externo) queda pendiente de tu OK.

7) Hallazgo de higiene: IA COLABORATIVA.py (raiz) no es Python valido, es el volcado de la conversacion original (SyntaxError linea 12). El candado AST lo salta; propongo moverlo a docs/idea-original.md.

8) Riesgo de la MAQUINA (no del repo): disco a ~300 MB libres. Con eso, el venv del verificador se crea sin pip y 4 comprobaciones de dependencias fallan con 'No module named pip'; el mismo codigo, tras limpiar temporales, da 79 OK / 0 FALLOS. Conviene liberar espacio antes de la proxima ronda larga.

### Evidencia real

```
$ pytest foco (rutas + sandbox + politica)
114 passed, 1 skipped in 133.67s                          -> focus_exitcode=0

$ venv\Scripts\python.exe -m pytest -q
392 passed, 1 skipped in 119.15s (0:01:59)                -> = 0 fallos

$ venv\Scripts\python.exe scripts\verificar_fabrica.py
  [OK]    path traversal bloqueado en las herramientas (confinar_a_base)
  [OK]    rutas absolutas, de dispositivo y de red bloqueadas
  [OK]    borrado de '..' bloqueado / vecino intacto / rastro cero
============== RESUMEN: 79 comprobaciones OK, 0 FALLOS ===============

FALLO REAL DURANTE LA RONDA (SonarCloud, detectado al leer el CI del push):
check=SonarCloud Code Analysis | completed | failure
  output_title=Quality Gate failed
  !!! [D Security Rating on New Code] (required >= A)
API SonarCloud (issues/search):
  [VULNERABILITY/CRITICAL] python:S5443 | scripts/verificar_fabrica.py | linea 343
   "Make sure publicly writable directories are used safely here."
  linea 343 -> absolutos = ("/etc/passwd", "/tmp/secreto.txt")   <- literal en /tmp
ARREGLO: construir esas rutas con tempfile.gettempdir() (nunca un literal de un
directorio publicamente escribible) y crear un senuelo real para que el test
muerda. Commit 8565214.

EVIDENCIA FINAL (SHA 8565214, el publicado):
$ git push -> 750f447..8565214 main -> main (push_exit=0); git status --porcelain vacio
$ git ls-remote origin refs/heads/main -> 8565214f9c36acfa618e0bb997939e01eeed0497
run=36511234685 | CI | status=completed | conclusion=success
  job=Pruebas (windows-latest) | success
  job=Pruebas (ubuntu-latest)  | success
  job=SonarQube                | success
check=SonarCloud Code Analysis | completed | success
  !!! 0 New issues | 0 Accepted issues | 0 Security Hotspots
medidas SonarCloud: security_rating=1.0 (bestValue=true) | new_security_rating=1.0 (bestValue=true)

AVISO DE ENTORNO (causa de 4 fallos que NO eran del codigo): el disco tiene
~300 MB libres (Get-PSDrive C -> Free=310431744). Con el disco asi, el venv
temporal del verificador se crea SIN pip ("No module named pip") y los 4 checks
de dependencias fallan. Tras borrar los temporales de verificaciones anteriores,
el mismo codigo da 79 OK / 0 FALLOS. Queda como riesgo de la maquina, no del repo.
```

### Archivos tocados

rutas.py
tests/test_rutas.py
tests/test_sandbox_herramientas.py
scripts/verificar_fabrica.py

### Sugerencias propias del programador

1. El incidente S5443 merece candado propio: añadir un test que prohiba literales de directorios publicamente escribibles (/tmp, /var/tmp, /dev/shm) en el codigo que ESCRIBE (no en tests que solo comprueban rechazos). Es la clase de fallo que acaba de tumbar el quality gate y no la caza ni pytest ni el verificador.

2. El verificador depende de pip real en el temporal: hoy, si el venv se crea sin pip (disco lleno, antivirus, timeout de ensurepip), 4 comprobaciones fallan por entorno y parecen fallos del codigo. Propongo que el paso 4 detecte 'No module named pip' y lo reporte como AVISO con causa (en vez de FALLO), o que reintente con -m ensurepip.

3. Los tests de rutas ahora plantan senuelos reales en %TEMP%. Convendria un fixture que los limpie siempre (hoy el del caso anidado deja %TEMP%/otro/ vacio), para no acumular basura en una maquina con el disco justo.

4. ruff como paso del CI sigue pendiente de tu OK; el repo tiene 392 tests y cero lint, y el incidente de hoy (una ruta literal) es justo lo que una regla de estilo/seguridad barata podria haber avisado antes.

5. IA COLABORATIVA.py (raiz) deberia salir del arbol: no es Python valido y cualquier herramienta que lo intente analizar tropieza. Mover a docs/idea-original.md y borrar el .py.

6. Documentar en README el limite conocido del candado: no resuelve el caso de un enlace/hardlink creado por el propio usuario dentro del proyecto antes de la sesion; el filtro corta los enlaces hacia fuera, pero un hardlink no es detectable en POSIX.
