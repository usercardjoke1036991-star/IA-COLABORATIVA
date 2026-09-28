<#
.SYNOPSIS
    Analiza el proyecto con SonarQube (servidor local en Docker o SonarQube Cloud).

.DESCRIPTION
    Flujo completo, sin instalar nada mas que Docker:
      1. Arranca SonarQube Community en Docker (docker-compose.sonarqube.yml) y
         espera a que el servidor responda UP.
      2. Ejecuta la suite de pruebas y genera coverage.xml + pytest-report.xml.
      3. Lanza el scanner oficial dentro de un contenedor (sonar-scanner-cli).
      4. Muestra la URL del informe y el estado del quality gate.

.PARAMETER Servidor
    URL del servidor. Por defecto http://localhost:9000. Para la nube, pasa
    https://sonarcloud.io.

.PARAMETER Token
    Token de analisis. Si se omite se usa SONAR_TOKEN (entorno o .env).

.PARAMETER Clave
    sonar.projectKey. Por defecto se lee de sonar-project.properties.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\sonar.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\sonar.ps1 -Servidor https://sonarcloud.io
#>
[CmdletBinding()]
param(
    [string]$Servidor = "",
    [string]$Token = "",
    [string]$Clave = "",
    [string]$Compose = "docker-compose.sonarqube.yml",
    [switch]$SinPruebas,
    [switch]$SinArrancar
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Aviso($texto) { Write-Host "   $texto" -ForegroundColor Yellow }
function Bien($texto) { Write-Host "   $texto" -ForegroundColor Green }

function Leer-DelEnv([string]$nombre) {
    $archivo = Join-Path $raiz ".env"
    if (-not (Test-Path $archivo)) { return "" }
    foreach ($linea in Get-Content $archivo) {
        if ($linea -match ("^\s*" + [regex]::Escape($nombre) + "\s*=\s*(.+?)\s*$")) {
            return $Matches[1].Trim('"').Trim("'")
        }
    }
    return ""
}

function Docker-Vivo {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $false }
    docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

# --------------------------------------------------------------------------
# 0. Parametros: servidor, clave y token
# --------------------------------------------------------------------------
if (-not $Clave) {
    $propiedades = Join-Path $raiz "sonar-project.properties"
    if (Test-Path $propiedades) {
        foreach ($linea in Get-Content $propiedades) {
            if ($linea -match "^\s*sonar\.projectKey\s*=\s*(.+?)\s*$") { $Clave = $Matches[1]; break }
        }
    }
    if (-not $Clave) { $Clave = "usercardjoke1036991-star_IA-COLABORATIVA" }
}

if (-not $Servidor) { $Servidor = $env:SONAR_HOST_URL }
if (-not $Servidor) { $Servidor = Leer-DelEnv "SONAR_HOST_URL" }
if (-not $Servidor) { $Servidor = "http://localhost:9000" }

$local = $Servidor -match "localhost|127\.0\.0\.1"
if ($local) { $Servidor = "http://localhost:9000" }

if (-not $Token) { $Token = $env:SONAR_TOKEN }
if (-not $Token) { $Token = Leer-DelEnv "SONAR_TOKEN" }

Write-Host "Proyecto : $Clave"
Write-Host "Servidor : $Servidor"

# --------------------------------------------------------------------------
# 1. Servidor local en Docker (se omite si el servidor es remoto)
# --------------------------------------------------------------------------
if ($local -and -not $SinArrancar) {
    Paso "1/4 SonarQube local en Docker"
    if (-not (Docker-Vivo)) {
        $atajo = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
        if (Test-Path $atajo) {
            Aviso "Docker no responde: arrancando Docker Desktop (puede tardar un minuto)..."
            Start-Process $atajo | Out-Null
            for ($i = 0; $i -lt 40; $i++) { Start-Sleep -Seconds 5; if (Docker-Vivo) { break } }
        }
    }
    if (-not (Docker-Vivo)) {
        throw ("Docker no esta disponible. Arranca Docker Desktop y repite, " +
               "o analiza contra la nube: scripts\sonar.ps1 -Servidor https://sonarcloud.io")
    }

    docker compose -f $Compose up -d
    if ($LASTEXITCODE -ne 0) { throw "docker compose up fallo (codigo $LASTEXITCODE)." }

    Aviso "Esperando a que SonarQube responda en $Servidor (la primera vez tarda un par de minutos)..."
    $arriba = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            if ((Invoke-RestMethod -Uri "$Servidor/api/system/status" -TimeoutSec 10).status -eq "UP") {
                $arriba = $true
                break
            }
        } catch { }
        Start-Sleep -Seconds 5
    }
    if (-not $arriba) { throw "SonarQube no llego a UP. Revisa el log con: docker logs sonarqube" }
    Bien "SonarQube esta UP."
}

if (-not $Token) {
    Write-Host ""
    Write-Host "Falta el token de analisis (SONAR_TOKEN)." -ForegroundColor Red
    if ($local) {
        Write-Host "  1. Abre $Servidor e inicia sesion (admin / admin la primera vez)."
        Write-Host "  2. My Account -> Security -> Generate Tokens (nombre: ia-colaborativa, tipo: Analysis)."
        Write-Host "  3. Anade la linea  SONAR_TOKEN=<el token>  al archivo .env y repite este script."
    } else {
        Write-Host "  Crealo en $Servidor (My Account -> Security) y guardalo en .env."
    }
    exit 1
}

# --------------------------------------------------------------------------
# 2. Pruebas con cobertura
# --------------------------------------------------------------------------
if (-not $SinPruebas) {
    Paso "2/4 Pruebas con cobertura"
    $python = Join-Path $raiz "venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { $python = "python" }
    & $python -m pytest -q --cov --cov-report=xml:coverage.xml --junitxml=pytest-report.xml
    if ($LASTEXITCODE -ne 0) {
        Aviso "Alguna prueba ha fallado: el analisis continua para que veas el detalle."
    } else {
        Bien "Suite en verde."
    }
} else {
    Aviso "Pruebas omitidas (-SinPruebas): se reutiliza el coverage.xml que exista."
}

# --------------------------------------------------------------------------
# 3. Analisis con el scanner oficial (en contenedor)
# --------------------------------------------------------------------------
Paso "3/4 Analisis con sonar-scanner"
$servidorParaContenedor = $Servidor
if ($local) { $servidorParaContenedor = $Servidor -replace "localhost|127\.0\.0\.1", "host.docker.internal" }

docker run --rm `
    -e "SONAR_HOST_URL=$servidorParaContenedor" `
    -e "SONAR_TOKEN=$Token" `
    -v "${raiz}:/usr/src" `
    -v "sonar_cache:/opt/sonar-scanner/.sonar/cache" `
    -w /usr/src `
    sonarsource/sonar-scanner-cli
if ($LASTEXITCODE -ne 0) { throw "El scanner fallo (codigo $LASTEXITCODE)." }

# --------------------------------------------------------------------------
# 4. Resultado
# --------------------------------------------------------------------------
Paso "4/4 Resultado"
try {
    $cabecera = @{ Authorization = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${Token}:")) }
    $consulta = "$Servidor/api/qualitygates/project_status?projectKey=$Clave"
    $estado = (Invoke-RestMethod -Uri $consulta -Headers $cabecera -TimeoutSec 30).projectStatus.status
    Bien "Quality gate: $estado"
} catch {
    Aviso "No se pudo consultar el quality gate (mira el informe en el navegador)."
}
Bien "Informe: $Servidor/dashboard?id=$Clave"

