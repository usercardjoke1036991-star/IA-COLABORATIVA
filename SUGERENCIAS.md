# Sugerencias del Arquitecto - ia-colaborativa

Aqui se acumulan las rondas del bucle: el arquitecto lee el informe, el
contexto real del repositorio y el historial, y devuelve el siguiente lote
priorizado. La sesion se cierra cuando dice `[[ARQUITECTO: FIN]]` o cuando el
usuario escribe PARAR.

## Estado de la sesion

- rondas: 0
- estado: abierta

## Ronda 1

- (pendiente)

## Ronda 2 - 2026-09-28 20:48:33

- estado de la sesion: abierta
- informe de referencia: ronda 2 de INFORME.md

## Diagnostico
La vulnerabilidad de path traversal queda cerrada y con evidencia real: candado en `rutas.resolver` (rechazo de `..` en `parts` + confinamiento de la ruta resuelta), cobertura de las 8 herramientas + `activacion._escribir`, fuga por symlink/junction filtrada, 61 tests nuevos, verificador ampliado y CI verde en Windows/POSIX/Sonar. El objetivo del ciclo esta cumplido; NO se marca FIN porque queda un defecto real sin cerrar (el interprete sin comillas en scripts shell, que explota justo en rutas con espacio como la de este proyecto) y un par de candados baratos de alto valor. El resto de tus 6 propuestas son correctas en concepto pero de valor desigual: descarto (4) patrones de `buscar_archivos` (hoy `rglob` no puede escapar; ruido defensivo) y (6) documentar el skip (solo doc).

## Sugerencias
1. [valor alto] Citar el interprete del venv en scripts shell.
   QUE -> toda ruta al interprete (`venv/bin/python`, `"$RAIZ/venv/bin/python"`) va entrecomillada en los `.sh` del repo Y en cualquier comando sh que genere la fabrica.
   DONDE -> `scripts/instalar.sh` y plantillas/comandos sh en `fabrica.py`.
   TERMINADO -> `grep -rn 'venv/bin/python' scripts/` sin ocurrencias sin comillas; el script se ejecuta OK en una ruta con espacio. Añadir guardián en `scripts/verificar_fabrica.py` (falla si una llamada al interprete del venv no esta entrecomillada) + test unitario que lo fije.

2. [valor alto] Candado de regresion sobre la politica `base_de_proyecto()`.
   QUE -> un test que falle si una herramienta de archivos vuelve a derivar rutas de contenido EXISTENTE con `rutas.ruta_de_proyecto()` en vez de `base_de_proyecto()`.
   DONDE -> nuevo `tests/test_politica_rutas.py` (inspeccion estatica via `ast` sobre `herramientas_archivos.py`) o test en `test_sandbox_herramientas.py`; documentar la regla en `README.md`/`AGENTS.md`.
   TERMINADO -> el test pasa hoy y falla si se reinserta `ruta_de_proyecto` para contenido existente (usar allowlist explicita de los sitios donde CREAR proyecto si quieres permitirlo).

3. [valor medio] Endurecer `confinar_a_base` contra vectores Windows.
   QUE -> rechazo temprano y con mensaje claro de rutas absolutas, con letra de unidad (`C:\...`), UNC/device (`\\?\`, `\\.\`, `\\host\share`) y nombres reservados (`CON`, `NUL`, `AUX`, `COM1`...).
   DONDE -> `rutas.resolver`/`confinar_a_base`.
   TERMINADO -> tests nuevos: `C:\Windows\...`, `\\?\C:\...`, `\\host\share\x`, `/etc/passwd`, y `..\..\x` con barras invertidas -> todos `ErrorRuta`; añadir al menos un caso a `verificar_fabrica.py` paso 3.

4. [valor medio] Lint barato en CI.
   QUE -> `ruff` con config minima como paso del job de pruebas.
   DONDE -> `pyproject.toml`/`ruff.toml` + `.github/workflows`.
   TERMINADO -> `ruff check .` exit 0 local y en CI; limitar a `E,F,I` (pyflakes/imports) para no inundar de estilo.

5. [valor bajo] Validar `fabrica._carpeta_registro` con `permitir_externo`.
   QUE -> exigir que la carpeta de registro viva dentro de las raices declaradas, o que el flag venga con ruta explicita validada.
   DONDE -> `fabrica._carpeta_registro`.
   TERMINADO -> test: `permitir_externo=True` con ruta fuera -> error claro; ninguna carpeta arbitraria del entorno se acepta implicitamente.

## Riesgos
- Comillas en scripts: romperia si algun script dependia de word-splitting deliberado (improbable). Verificar ejecutando en ruta con espacio Y sin espacio.
- Guardián `base_de_proyecto`: falsos positivos si hay usos legitimos futuros; mitigar con allowlist de modulos/funciones permitidas, no prohibicion ciega.
- Endurecer `confinar_a_base`: no debe rechazar la raiz fichada ni rutas validas con caracteres no ASCII/espacios; correr suite completa + `verificar_fabrica.py` y confirmar que el caso legitimo sigue pasando antes de commit.
- `ruff`: puede marcar re-exportaciones en `__init__`; añadir `ignore` acotado y no tocar logica para que el paso no obligue a refactors.

Orden tecnico: implementa 1 y 2 en la misma ronda (ambos son "no repetir el fallo que ya costo caro"), luego 3, y 4/5 en una ronda de cierre. Publica con el mismo ritual: suite completa + `verificar_fabrica.py` + push + verificar CI del SHA y `datos/`/`proyectos/` intactos.
