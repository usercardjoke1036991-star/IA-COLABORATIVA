# Arquitecto Externo (MCP) — dos IAs que piensan, programan y **crean proyectos**

Convierte un **chat con una IA externa** en un **loop de trabajo real** dentro de
Cursor (o de Cline): la IA externa (el *Arquitecto*) piensa, dimensiona, valida y
aconseja; la IA integrada del IDE (el *Programador*) escribe el codigo. El ciclo
se repite hasta que el Arquitecto declara la tarea terminada.

Encima de ese loop hay ahora una **fabrica de proyectos**: el mismo sistema puede
crear una carpeta aislada para una idea nueva, rellenarla con plantillas
(Python, Flask, FastAPI, Web3, Playwright, MCP), inicializar su git, publicarla en
GitHub y trabajar dentro de ella con herramientas de archivos sandboxeadas.

Y todo eso se puede lanzar de una vez desde la consola: el **orquestador** coge una
idea, pide el plan, escribe el codigo, ejecuta las pruebas, corrige los fallos y
hace commits, sin abrir el IDE.

> Sustituye al archivo `IA COLABORATIVA.py`, que era una **transcripcion de chat**
> (no codigo Python) describiendo esta idea. Aqui esta la implementacion real.

---

## Los tres papeles

| Papel | Quien es | Modelo recomendado | Que hace |
|---|---|---|---|
| **ARQUITECTO** | IA externa (rol `arquitecto`) | `deepseek-reasoner` (R1) | Dimensiona la idea, decide el plan, valida cada informe de progreso. |
| **PROGRAMADOR** | IA del IDE *y/o* rol `ejecutor` | `deepseek-chat` (V3) | Escribe los archivos completos y corrige los errores reales. |
| **FABRICA** | Este repositorio | — | Crea carpetas, plantillas, git, venv, GitHub y registro de proyectos. |

El *cross-model* es la gracia: paga el razonamiento caro solo para pensar, y usa
el modelo barato y rapido para producir codigo.

---

## Como funciona el loop

```
   TU escribes 1 prompt en Cursor
            |
            v
   [IA de Cursor = PROGRAMADOR]
            |  1) consultar_arquitecto(idea, contexto)
            v
   [IA externa = ARQUITECTO]  ---> plan accionable (dimensiona, riesgos, pasos)
            |
            v
   PROGRAMADOR escribe el codigo en el IDE
            |  2) reportar_progreso(resumen, archivos, bloqueo)
            v
   ARQUITECTO valida lo hecho ---> siguientes pasos
            |
            v
   PROGRAMADOR programa otra vez ... y repite hasta que el ARQUITECTO responda
   "estado del loop: TAREA TERMINADA" (marcador [[ARQUITECTO: FIN]])
```

Diferencia clave frente al diseno original: **no hace falta Flask ni webhooks**.
El transporte `stdio` de MCP no puede compartir proceso con un servidor HTTP, y
ademas es innecesario: el ciclo se cierra con una **segunda herramienta MCP**
(`reportar_progreso`) que la propia IA de Cursor invoca. Menos piezas, cero
puertos abiertos, y el loop termina solo (nada de bucles infinitos de cortesia).

---

## Puesta en marcha (5 minutos)

### 1. Instalar

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
```

macOS / Linux:

```bash
chmod +x scripts/instalar.sh && ./scripts/instalar.sh
```

O manualmente:

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

### 2. Poner tu API key

Abre `.env` y rellena **solo** la clave del proveedor que vayas a usar:

```ini
ARQUITECTO_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-tu-clave-aqui
```

`.env` esta en `.gitignore`: tus claves nunca se suben al repositorio.

### 3. Comprobar que todo funciona

```powershell
venv\Scripts\python.exe arquitecto_mcp.py --check
```

Hace un ping real al modelo y te dice si la clave, el modelo y la URL estan bien.

Y para comprobar que la fabrica de proyectos funciona de verdad (crea un proyecto
completo en una carpeta temporal, con plantillas, git y archivos):

```powershell
venv\Scripts\python.exe scripts\verificar_fabrica.py
venv\Scripts\python.exe scripts\verificar_fabrica.py --venv   # crea tambien el venv
```

### 4. Conectar Cursor

**Opcion A — archivo del proyecto (ya incluido).** `.cursor/mcp.json` apunta al
interprete del venv y al servidor:

```json
{
  "mcpServers": {
    "arquitecto-externo": {
      "command": "C:\\ruta\\a\\tu\\proyecto\\venv\\Scripts\\python.exe",
      "args": ["C:\\ruta\\a\\tu\\proyecto\\arquitecto_mcp.py"],
      "env": { "ARQUITECTO_LOG": "INFO" }
    }
  }
}
```

Si copias la carpeta a otra ruta, actualiza esas dos rutas absolutas.

**Opcion B — interfaz de Cursor.** `Ctrl+Shift+P` → *Cursor: Open MCP Settings*
(o *Settings → MCP*) → añade un servidor con:
`command` = `...\venv\Scripts\python.exe`, `args` = `...\arquitecto_mcp.py`.

Despues, en Cursor: *Settings → MCP* debe mostrar `arquitecto-externo` en verde
con **27 herramientas**. Si sale en rojo, mira la seccion *Problemas frecuentes*.

### 5. Conectar Cline (opcional, recomendado)

Cline tambien puede usar el mismo servidor (CLI y extension):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\registrar_en_cline.ps1
```

Registra el servidor en el CLI (`cline mcp add ...`) y en los
`cline_mcp_settings.json` que encuentre, **sin borrar** los servidores que ya
tuvieras. Alternativa multiplataforma: `venv\Scripts\python.exe scripts\registrar_mcp.py`
(registra a la vez Cursor y Cline).

### 6. Las reglas de orquestacion

Ya estan incluidas y activas:

- `.clinerules` — reglas para Cline: cuando consultar al Arquitecto, cuando crear
  un proyecto con la fabrica, cuando delegar en el Programador externo y cuando
  commitear.
- `.cursorrules` — formato clasico para Cursor (sigue funcionando).
- `.cursor/rules/arquitecto.mdc` — formato moderno de Cursor.

Le dicen a la IA del IDE **cuando** consultar al Arquitecto, **cuando** reportar
progreso y **cuando** detenerse. Sin ellas, la IA nunca llegaria a llamar a las
herramientas.

---

## Estructura del proyecto

| Archivo | Responsabilidad |
|---|---|
| `arquitecto_mcp.py` | Servidor MCP (FastMCP + stdio). Capa fina: declara las 27 herramientas y las expone. |
| `arquitecto.py` | Nucleo del rol ARQUITECTO: `consultar()`, `reportar_progreso()`, estado, reinicio, exportar plan. |
| `ejecutor.py` | Nucleo del rol PROGRAMADOR externo: pide los archivos completos y las correcciones. |
| `protocolo.py` | Contrato entre las IAs: system prompts, marcadores, formato de salida y parser de `### ARCHIVO:`. |
| `proveedores.py` | Cliente HTTP (timeout, reintentos, errores legibles) + proveedor simulado (que tambien "programa"). |
| `historial.py` | Memoria de cada rol, ventana acotada y persistencia en `datos/`. |
| `config.py` | Configuracion de los dos roles y de la fabrica, desde `.env`. |
| `rutas.py` | **Sandbox**: normaliza nombres y valida que todo quede dentro de las raices permitidas. |
| `plantillas.py` | Catalogo de plantillas (7): archivos, notas y requirements fusionables. |
| `herramientas_archivos.py` | Unica puerta a disco: leer, escribir, listar, buscar, mover y borrar. |
| `fabrica.py` | Crea proyectos, aplica plantillas, `git init`, commits, registro y GitHub. |
| `orquestador.py` | Bucle autonomo desde consola: idea -> proyecto -> plan -> codigo -> pruebas -> commit. |
| `prueba_loop.py` | Simulador del loop completo desde consola (sin abrir Cursor). |
| `scripts/verificar_servidor.py` | Diagnostico de la instalacion + invocacion de herramientas por MCP. |
| `scripts/verificar_fabrica.py` | Verificacion end-to-end de la fabrica en una carpeta temporal. |
| `scripts/prueba_cliente_mcp.py` | Cliente MCP por `stdio` que habla con el servidor como lo hace Cursor. |
| `scripts/registrar_mcp.py` | Registra el servidor en Cursor y en Cline (fusionando JSON). |
| `scripts/registrar_en_cline.ps1` | Registro especifico para Cline (CLI + settings). |
| `scripts/instalar.ps1` / `.sh` | Instaladores automaticos. |
| `scripts/probar.ps1` | Bateria de pruebas completa. |
| `.clinerules`, `.cursorrules`, `.cursor/rules/*.mdc` | Reglas de orquestacion para la IA del IDE. |
| `.cursor/mcp.json` | Registro del servidor MCP en el proyecto. |

Separacion deliberada: **nada del nucleo importa `mcp`**. Asi el mismo motor se
puede usar desde el servidor MCP, desde consola o desde una futura API web.

---

## La fabrica de proyectos

Cada idea nueva vive en **su propia carpeta** dentro de `proyectos/`, con su git,
su README y su venv. El servidor MCP la gestiona; tu tambien puedes hacerlo desde
la consola.

```powershell
# desde el chat del IDE (herramientas MCP):
#   catalogo_plantillas()                 -> que plantillas hay
#   crear_proyecto("Bot de arbitraje", "Vigila precios y avisa", "python,web3")
#   preparar_entorno("bot-de-arbitraje")  -> venv + dependencias
#   escribir_archivo("bot-de-arbitraje", "src/bot/main.py", "...")
#   commit_proyecto("bot-de-arbitraje", "feat: primer vigilante de precios")
#   publicar_en_github("bot-de-arbitraje")
```

### Plantillas disponibles

| Clave | Que crea |
|---|---|
| `vacio` | Solo la base: README, `.gitignore`, `docs/decisiones.md`, carpetas de trabajo. |
| `python` | Paquete en `src/`, `pyproject.toml`, tests, scripts de PowerShell. |
| `flask` | App Flask con endpoint de salud, index y pruebas con `test_client`. |
| `fastapi` | API tipada con Pydantic, `/salud`, `uvicorn` y pruebas con `TestClient`. |
| `web3` | Cliente Web3, vigilante de bloques y `.env.example` con `RPC_URL`. |
| `playwright` | Pruebas de navegador (Chromium headless) con `conftest.py`. |
| `mcp` | Servidor MCP minimo + `scripts/registrar_mcp.ps1`. |

**Se combinan**: `"python,web3"`, `"python,fastapi,playwright"`... El `README.md`,
el `.gitignore` y el `requirements.txt` se fusionan solos (sin dependencias
duplicadas).

### Reglas de seguridad de la fabrica

- Todo pasa por `rutas.py`: los nombres se normalizan a *slug* y cualquier ruta
  que se salga de `proyectos/` (o del propio repositorio) se **rechaza**.
- Solo si pones `ARQUITECTO_PERMITIR_EXTERNO=true` se relaja el sandbox. Es
  comodo y es peligroso: dejalo en `false`.
- La carpeta `.git` esta **protegida**: la IA no puede escribir dentro.
- Las extensiones ejecutables (`.exe`, `.dll`, `.msi`, `.scr`) estan bloqueadas.
- `borrar_archivo` sobre una carpeta exige `recursivo=true`; borrar la raiz del
  proyecto esta prohibido.

### Git y GitHub

- `crear_proyecto` hace `git init -b main` y el primer commit (con la identidad de
  `ARQUITECTO_GIT_USUARIO`/`ARQUITECTO_GIT_EMAIL` si las defines). Con
  `ARQUITECTO_CREAR_VENV=true` crea tambien el `venv/` (sin instalar nada); las
  dependencias las instala `preparar_entorno`.
- `estado_git` muestra rama, cambios, ultimos commits y remotos.
- `commit_proyecto` guarda cada bloque de trabajo: es tu red de seguridad.
- `publicar_en_github` usa **GitHub CLI**:

  ```powershell
  winget install --id GitHub.cli
  gh auth login
  ```

  Si `gh` no esta, la herramienta te lo dice con esas instrucciones y el proyecto
  sigue funcionando en local (no rompe nada).

El registro de proyectos vive en `datos/proyectos.json` (configurable con
`ARQUITECTO_REGISTRO`) y `listar_proyectos` avisa de carpetas creadas a mano que
no esten registradas (y al reves).

---

## El orquestador autonomo

Lanza una idea completa de principio a fin, sin IDE:

```powershell
# modo interno: los dos modelos externos trabajan solos (defecto)
venv\Scripts\python.exe orquestador.py --idea "Bot que vigila precios y avisa por Telegram"

# con venv y dependencias del proyecto, 3 rondas y 2 correcciones por ronda
venv\Scripts\python.exe orquestador.py --idea "API de tareas" --plantillas python,fastapi `
    --preparar --turnos 3 --intentos 2

# delegando cada ronda a Cline CLI (agente del IDE con acceso a las herramientas)
venv\Scripts\python.exe orquestador.py --idea "Scraper de noticias" --modo cline --auto --publicar
```

Que hace, en orden:

1. Crea el proyecto (plantillas + `git init` + registro).
2. Pide el **plan** al ARQUITECTO.
3. El PROGRAMADOR entrega los archivos completos; se escriben en el proyecto.
4. Ejecuta `pytest` y, si falla, le devuelve el error real al PROGRAMADOR
   (`--intentos` correcciones por ronda).
5. `commit` de la ronda y **informe de progreso** al ARQUITECTO, que dicta los
   siguientes pasos.
6. Repite hasta `TAREA TERMINADA` o agotar `--turnos`, y escribe el resumen en
   `datos/orquestador_<proyecto>.txt`.

Opciones utiles: `--sin-probar`, `--publicar`, `--modo interno|cline`, `--auto`,
`--turnos N`, `--intentos N`, `--preparar`.

---

## El PROGRAMADOR externo (segundo modelo)

El rol `ejecutor` permite que el codigo no lo escriba la IA del IDE, sino un
segundo modelo mas barato. El contrato es un formato analizable:

````
### ARCHIVO: src/saludar.py
```python
def saludar(nombre: str = "mundo") -> str:
    """Devuelve un saludo."""
    return "hola " + nombre
```

### PASOS
1. venv\Scripts\python.exe -m pytest -q
````

`protocolo.extraer_archivos()` lo convierte en `[(ruta, contenido)]` y las
herramientas MCP `pedir_codigo_al_programador` / `aplicar_codigo_del_programador`
(o `aplicar=true`) escriben los archivos con la validacion de rutas de siempre.
Con `corregir_con_el_programador` le pasas la traza del error real.

---

---

## Publicar en GitHub y calidad (SonarQube)

### Subir este proyecto a un repositorio

El repositorio ya viene preparado: `.gitignore` deja fuera `.env`, `venv/`,
`datos/` y `proyectos/`, y `.gitattributes` fija LF para el codigo y CRLF para los
`.ps1`.

```powershell
git init -b main                     # solo si aun no es un repositorio
git add -A
git commit -m "feat: arquitecto externo con fabrica de proyectos"
git remote add origin https://github.com/<usuario>/<repo>.git
git push -u origin main
```

La primera vez, Git Credential Manager abre el navegador para autenticarte y
despues guarda la credencial (no vuelve a pedirla).

Ademas hay integracion continua en `.github/workflows/ci.yml`:

- **pruebas**: `pytest` con cobertura en Linux y Windows (matriz de runners) y, en
  Windows, los dos verificadores (`verificar_servidor.py` y `verificar_fabrica.py`).
- **calidad**: analisis con `SonarSource/sonarqube-scan-action`, que solo se
  ejecuta si existe el secreto `SONAR_TOKEN`; sin el, el CI sigue en verde.

### Analisis con SonarQube

**Opcion A - local en Docker** (no hace falta instalar nada mas):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sonar.ps1
```

El script levanta SonarQube Community (`docker-compose.sonarqube.yml`), espera a
que este `UP`, ejecuta las pruebas con cobertura y lanza el scanner oficial dentro
de un contenedor.

**La primera vez** el servidor no tiene token, asi que dejalo listo con:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\conectar_sonar.ps1
```

Ese script espera al servidor, cambia la contrasena de fabrica de `admin` por una
aleatoria robusta, genera un token de analisis y escribe `SONAR_HOST_URL`,
`SONAR_TOKEN` y `SONAR_ADMIN_PASSWORD` en tu `.env`. A partir de ahi
`scripts\sonar.ps1` funciona solo. Si prefieres hacerlo a mano: abre
http://localhost:9000, entra con `admin` / `admin`, cambia la contrasena y crea el
token en `My Account` -> `Security` -> `Generate Tokens`.

La primera ejecucion tarda unos minutos: descarga la imagen del scanner y todos
los plugins del servidor (quedan en cache para las siguientes veces).

El informe queda en
http://localhost:9000/dashboard?id=usercardjoke1036991-star_IA-COLABORATIVA

Para parar el servidor cuando termines (los datos se conservan en volumenes):

```powershell
docker compose -f docker-compose.sonarqube.yml down       # parar
docker compose -f docker-compose.sonarqube.yml down -v    # parar y borrar todo
```

**Opcion B - SonarQube Cloud** (repositorio publico, sin Docker):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sonar.ps1 -Servidor https://sonarcloud.io
```

Para el CI: crea el proyecto en <https://sonarcloud.io> (organizacion
`usercardjoke1036991-star`, clave `usercardjoke1036991-star_IA-COLABORATIVA`) y
anade el secreto `SONAR_TOKEN` en `Settings -> Secrets and variables -> Actions`.

| Archivo | Para que sirve |
|---|---|
| `sonar-project.properties` | Clave del proyecto, fuentes, exclusiones y rutas de cobertura. |
| `docker-compose.sonarqube.yml` | SonarQube Community local (puerto 9000, volumenes persistentes). |
| `scripts/sonar.ps1` | Flujo completo: servidor + pruebas + scanner + quality gate. |
| `scripts/conectar_sonar.ps1` | Primera puesta en marcha: contrasena de admin y token en el `.env`. |
| `.coveragerc` | Que mide la cobertura y que excluye (venv, tests, scripts, plantillas). |
| `.github/workflows/ci.yml` | Pruebas en CI y analisis en SonarQube. |

---

## Referencia de las herramientas MCP

### `consultar_arquitecto(idea_del_usuario, contexto_del_codigo="")`

Se llama **antes** de escribir codigo. El Arquitecto no programa: dimensiona,
detecta riesgos y devuelve un plan accionable.

- `idea_del_usuario`: el prompt del usuario, literal.
- `contexto_del_codigo`: stack, estructura de archivos, restricciones.

### `reportar_progreso(resumen_de_lo_hecho, prompt_original="", archivos_tocados="", bloqueo="")`

Cierra el ciclo. Se llama al terminar cada bloque de trabajo **y tambien** cuando
te bloqueas (pasando `bloqueo`).

### `ver_estado()`

Diagnostico local sin gastar tokens: proveedor, modelo, turnos y ultimos turnos.

### `exportar_plan(ruta="PLAN_ARQUITECTO.md")`

Vuelca el ultimo plan a un Markdown del proyecto: sirve de "contrato" que la IA
puede releer sin gastar tokens.

### `reiniciar_sesion()`

Borra la memoria para empezar un trabajo totalmente nuevo (evita arrastrar
contexto viejo a un proyecto distinto).

### Fabrica de proyectos

| Herramienta | Que hace |
|---|---|
| `estado_fabrica()` | Diagnostico: carpeta de proyectos, plantillas, git, gh y los dos modelos. |
| `catalogo_plantillas()` | Lista las plantillas y sus notas de instalacion. |
| `crear_proyecto(nombre, descripcion, plantillas_seleccion, con_git, publicar, visor)` | Crea la carpeta aislada, escribe el andamiaje, `git init` + commit y registra. |
| `listar_proyectos()` | Registro + carpetas reales (avisa de desajustes). |
| `ver_proyecto(proyecto, profundidad)` | Ficha, arbol de archivos y estado de git. |

### Archivos (siempre dentro de un proyecto)

| Herramienta | Que hace |
|---|---|
| `listar_archivos(proyecto, subcarpeta, profundidad, max_entradas)` | Arbol de archivos. |
| `leer_archivo(proyecto, ruta, desde, hasta)` | Lee con numeros de linea. |
| `escribir_archivo(proyecto, ruta, contenido, sobreescribir)` | Escribe el archivo completo (UTF-8, LF). |
| `crear_carpeta(proyecto, ruta)` | Crea carpetas. |
| `mover_archivo(proyecto, origen, destino)` | Mueve o renombra. |
| `borrar_archivo(proyecto, ruta, recursivo)` | Borra archivo o carpeta (carpeta exige `recursivo=true`). |
| `buscar_en_proyecto(proyecto, texto, subcarpeta, max_resultados)` | Grep con `ruta:linea:contenido`. |
| `buscar_archivos(proyecto, patron, max_resultados)` | Busqueda por patron glob. |

### Entorno, git y GitHub

| Herramienta | Que hace |
|---|---|
| `preparar_entorno(proyecto, instalar)` | Crea `venv/` e instala `requirements.txt`. |
| `estado_git(proyecto)` | Rama, cambios, commits y remotos. |
| `commit_proyecto(proyecto, mensaje)` | Guarda los cambios en un commit. |
| `publicar_en_github(proyecto, visor, organizacion, nombre_repo)` | Crea el repo remoto con `gh` y lo sube. |

### Rol PROGRAMADOR externo

| Herramienta | Que hace |
|---|---|
| `estado_programador()` | Diagnostico del segundo rol. |
| `pedir_codigo_al_programador(tarea, plan, contexto, proyecto, aplicar)` | Pide los archivos completos de una tarea. |
| `aplicar_codigo_del_programador(proyecto, codigo)` | Aplica un texto con bloques `### ARCHIVO:`. |
| `corregir_con_el_programador(proyecto, error, codigo_previo, intento, aplicar)` | Devuelve un error real para que lo arregle. |
| `reiniciar_programador()` | Olvida solo la memoria del programador. |

---

## Como se corta el loop (y no se queda girando)

El Arquitecto escribe el literal

```
[[ARQUITECTO: FIN]]
```

cuando el objetivo ya esta cumplido. Entonces la respuesta incluye
`estado del loop: TAREA TERMINADA` y el Programador deja de iterar: verifica los
criterios de aceptacion y entrega el resumen final al usuario.

El system prompt **prohibe** explicitamente las despedidas de relleno del tipo
*"quedo a la espera de tus comentarios"* o *"avisame cuando lo tengas"*, que son
las que convierten estos loops en un ping-pong eterno sin trabajo util.

---

## Proveedores soportados

| `ARQUITECTO_PROVIDER` | Clave que usa | Modelo por defecto |
|---|---|---|
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| `openrouter` | `OPENROUTER_API_KEY` | `anthropic/claude-3.5-sonnet` |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` |
| `custom` | `ARQUITECTO_API_KEY` | el que pongas en `ARQUITECTO_MODEL` |
| `mock` | (ninguna) | respuestas simuladas, sin red |

### Los dos roles (cross-model)

El arquitecto y el programador se configuran por separado. Si no defines las
variables `ARQUITECTO_EJECUTOR_*`, el programador hereda el proveedor del
arquitecto y usa el modelo por defecto del proveedor.

| Variable | Rol | Ejemplo |
|---|---|---|
| `ARQUITECTO_MODEL` | arquitecto (planifica) | `deepseek-reasoner` (R1) |
| `ARQUITECTO_EJECUTOR_MODEL` | programador (escribe) | `deepseek-chat` (V3) |
| `ARQUITECTO_EJECUTOR_PROVIDER` | proveedor del programador | `openrouter`, `custom`... |
| `ARQUITECTO_EJECUTOR_API_KEY` | clave propia del programador | opcional |
| `ARQUITECTO_EJECUTOR_TEMPERATURA` | creatividad del programador | `0.2` (def.) |
| `ARQUITECTO_EJECUTOR_MAX_TOKENS` | tamano de sus respuestas | `8192` |
| `ARQUITECTO_EJECUTOR_TIMEOUT` | segundos por peticion | `600` |

Comprobacion rapida de que ambos roles ven la configuracion:

```powershell
venv\Scripts\python.exe arquitecto_mcp.py --estado
```

`custom` sirve para cualquier endpoint compatible con `/chat/completions`
(Ollama, LM Studio, vLLM, Groq, Azure...). Ejemplo con Ollama local, sin clave:

```ini
ARQUITECTO_PROVIDER=custom
ARQUITECTO_API_URL=http://127.0.0.1:11434/v1/chat/completions
ARQUITECTO_MODEL=qwen2.5-coder:14b
```

Para cambiar de modelo sin tocar codigo: `ARQUITECTO_MODEL=...` en `.env`.

---

## Pruebas y comandos de consola

Todos los comandos asumen que estas en la raiz del proyecto con el venv creado.

```powershell
# Diagnostico de configuracion + ping real al modelo
venv\Scripts\python.exe arquitecto_mcp.py --check
venv\Scripts\python.exe arquitecto_mcp.py --check --no-ping   # sin gastar tokens

# Estado del loop y reinicio de la memoria
venv\Scripts\python.exe arquitecto_mcp.py --estado
venv\Scripts\python.exe arquitecto_mcp.py --reiniciar

# Simulacion del loop completo, sin red (mecanica del contrato)
venv\Scripts\python.exe prueba_loop.py --mock
venv\Scripts\python.exe prueba_loop.py --mock --bloqueo --exportar

# Verificacion de la instalacion (12 comprobaciones)
venv\Scripts\python.exe scripts\verificar_servidor.py

# Cliente MCP por stdio: la misma conversacion que hara Cursor
venv\Scripts\python.exe scripts\prueba_cliente_mcp.py

# Suite de pruebas con cobertura (la que alimenta a SonarQube)
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m pytest -q --cov --cov-report=xml:coverage.xml --cov-report=term-missing

# Analisis de calidad: SonarQube local en Docker (o SonarQube Cloud)
powershell -ExecutionPolicy Bypass -File scripts\conectar_sonar.ps1   # solo la primera vez
powershell -ExecutionPolicy Bypass -File scripts\sonar.ps1
powershell -ExecutionPolicy Bypass -File scripts\sonar.ps1 -Servidor https://sonarcloud.io

# Todo de golpe
powershell -ExecutionPolicy Bypass -File scripts\probar.ps1
```

Los modos simulados (`--mock`) **no gastan tokens ni necesitan API key**: sirven
para validar que el contrato del loop, el cierre automatico y el servidor MCP
funcionan antes de conectar el modelo real.

---

## Problemas frecuentes

| Sintoma | Causa y solucion |
|---|---|
| Cursor muestra el servidor en rojo | La ruta de `.cursor/mcp.json` no es la de tu maquina, o el `python.exe` no tiene el paquete `mcp`. Comprueba con `venv\Scripts\python.exe scripts\verificar_servidor.py`. |
| `No se encontro el SDK de MCP` | Falta instalar dependencias: `venv\Scripts\python.exe -m pip install -r requirements.txt`. |
| `Falta la API key` | Abre `.env` y rellena la variable del proveedor elegido. Comprueba con `--check`. |
| `HTTP 401` | Clave invalida o revocada. `HTTP 402` = sin saldo. |
| `HTTP 404` | Modelo o URL incorrectos: revisa `ARQUITECTO_MODEL` y `ARQUITECTO_API_URL`. |
| `HTTP 429` | Limite de peticiones: el cliente ya reintenta con espera progresiva. Sube `ARQUITECTO_REINTENTOS` o baja la frecuencia. |
| La IA de Cursor no llama nunca al Arquitecto | Faltan las reglas: comprueba que `.cursorrules` y/o `.cursor/rules/arquitecto.mdc` estan en el proyecto y que las reglas MCP estan activas. |
| El loop no termina nunca | El modelo no esta emitiendo `[[ARQUITECTO: FIN]]`. Refuerza la regla en `protocolo.py` (SYSTEM_PROMPT) o baja `ARQUITECTO_MAX_TURNOS` y reinicia con `--reiniciar`. |
| Las respuestas son enormes y caras | Baja `ARQUITECTO_MAX_TOKENS` y `ARQUITECTO_MAX_TURNOS` (menos contexto por peticion). |
| Quiero probar sin gastar nada | Pon `ARQUITECTO_MOCK=true` en `.env` (respuestas simuladas, sin red). El simulador tambien "programa": entrega archivos de ejemplo para probar la fabrica completa. |
| `crear_proyecto` dice que la carpeta no esta vacia | Ya existe un proyecto con ese nombre. Usa `forzar=true` para reutilizarla o elige otro nombre: `listar_proyectos` te los lista. |
| `Ruta fuera de las raices permitidas` | El sandbox funcionando: la fabrica solo escribe en `proyectos/` y en este repositorio. Si de verdad necesitas otra ruta, `ARQUITECTO_PERMITIR_EXTERNO=true` y reinicia el servidor MCP. |
| `La carpeta .git esta protegida` | Es a proposito. Para el estado del repositorio usa `estado_git` / `commit_proyecto`, no `escribir_archivo`. |
| `gh repo create fallo` | GitHub CLI sin sesion o nombre ocupado: `gh auth login` y comprueba el nombre con `gh repo view`. |
| El orquestador se para en la primera ronda | Revisa `datos/orquestador_<proyecto>.txt` y la ultima salida: o falta la API key (`arquitecto_mcp.py --check`) o el modelo no devolvio el formato `### ARCHIVO:`. |
| El orquestador no encuentra `cline` | Instala Cline CLI o usa `--modo interno` (`ARQUITECTO_ORQUESTADOR=interno`). |
| Quiero verificar que la fabrica funciona antes de usarla | `venv\Scripts\python.exe scripts\verificar_fabrica.py` (crea todo en una carpeta temporal y no toca tu registro real). |

Los logs del servidor van **siempre a stderr** (con `ARQUITECTO_LOG=DEBUG` para
mas detalle), porque `stdout` esta reservado al protocolo MCP. En Cursor los ves
en *Output → MCP Logs*.

---

## Seguridad y coste

- La API key vive en `.env` (ignorado por git) o en el entorno. Nunca en el codigo
  ni en el repositorio. `config.py` solo la lee del entorno.
- Las claves nunca se registran en logs: se muestran enmascaradas (`sk-a...1234`).
- Envia al Arquitecto solo el contexto necesario: no pegues credenciales,
  cadenas de conexion ni datos personales en `contexto_del_codigo`.
- El historial persistente (`datos/historial_arquitecto.json`) guarda la
  conversacion en disco local. Bórralo o pon `ARQUITECTO_PERSISTIR=false` si no
  lo quieres.
- Coste: cada llamada reenvia la ventana de historial. `ARQUITECTO_MAX_TURNOS`
  (12 por defecto) y `ARQUITECTO_MAX_CARACTERES` (24 000) acotan el gasto.
- **Sandbox de la fabrica**: `rutas.py` es el unico punto por el que pasan las
  rutas de disco. Solo se puede escribir dentro de `proyectos/` y de este
  repositorio; `.git` y los binarios estan bloqueados. Los proyectos generados
  son carpetas independientes con su propio git, asi que un error de la IA no
  puede tocar tus otros repositorios.
- `proyectos/` esta en `.gitignore`: no se anida dentro de este repositorio.

---

## Modo HTTP opcional (avanzado)

Cursor usa `stdio`, que es lo recomendado. Si necesitas exponer el Arquitecto a
otros clientes:

```powershell
venv\Scripts\python.exe arquitecto_mcp.py --http
```

Levanta el servidor MCP sobre HTTP en `http://127.0.0.1:8765/mcp`
(configurable con `ARQUITECTO_HTTP_HOST` y `ARQUITECTO_HTTP_PORT`). Si tu version
del SDK no soporta `streamable-http`, cae automaticamente a SSE.

---

## Notas sobre el material original

- `IA COLABORATIVA.py` es la transcripcion de la conversacion donde se ideo este
  sistema. **No es codigo Python** (falla `py_compile`) y ademas contiene errores
  de dictado que contaminaban el diseno (por ejemplo, confundir *DeepSeek*, "la
  de la ballenita", con **Docker**). Se recomienda renombrarlo a
  `docs/transcripcion_original.md` para que no lo analicen herramientas de Python.
- Correcciones aplicadas respecto a aquella transcripcion: la API key ya no esta
  hardcodeada, hay `try/except`, timeout, reintentos y comprobacion de estado; se
  elimino la contradiccion `stdio` + Flask; y el loop tiene una salida explicita
  en lugar de girar con cortesias vacias.

---

## Licencia y uso

Codigo de ejemplo sin garantia: revisa el plan que proponga el Arquitecto antes de
aplicarlo y verifica siempre los cambios en tu repositorio (usa git).
