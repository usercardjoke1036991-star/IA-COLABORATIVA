# Instalador del Arquitecto Externo para Windows (PowerShell).
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " ARQUITECTO EXTERNO - INSTALACION" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

Write-Host "[1/5] Entorno virtual en .\venv ..."
if (-not (Test-Path "venv\Scripts\python.exe")) {
    python -m venv venv
    Write-Host "      creado."
} else {
    Write-Host "      ya existe, se reutiliza."
}

Write-Host "[2/5] Instalando dependencias ..."
& "venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& "venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
Write-Host "      mcp + requests instalados."

Write-Host "[3/5] Archivo .env ..."
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "      se creo .env: abrelo y pega tu API key." -ForegroundColor Yellow
} else {
    Write-Host "      .env ya existe, no se modifica."
}

Write-Host "[4/5] Registrando el servidor MCP en Cline y Cursor ..."
& "venv\Scripts\python.exe" "scripts\registrar_mcp.py"
try { & powershell -ExecutionPolicy Bypass -File "scripts\registrar_en_cline.ps1" } catch { Write-Host "      aviso: $($_.Exception.Message)" -ForegroundColor Yellow }

Write-Host "[5/5] Verificando el servidor MCP y la fabrica de proyectos ..."
& "venv\Scripts\python.exe" "scripts\verificar_servidor.py"
& "venv\Scripts\python.exe" "scripts\verificar_fabrica.py"

Write-Host ""
Write-Host "Instalacion terminada." -ForegroundColor Green
Write-Host "Interprete para Cursor:"
Write-Host "  $raiz\venv\Scripts\python.exe"
Write-Host "Configuracion MCP: .cursor\mcp.json y los settings de Cline."
Write-Host ""
Write-Host "Siguiente paso: pega tu API key en .env y ejecuta"
Write-Host "  venv\Scripts\python.exe arquitecto_mcp.py --check"
Write-Host "Para lanzar una idea completa de principio a fin:"
Write-Host "  venv\Scripts\python.exe orquestador.py --idea \"tu idea\""
