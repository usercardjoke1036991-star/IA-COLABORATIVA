# Bateria de pruebas del Arquitecto Externo (Windows).
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\probar.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\probar.ps1 -Real   (consume tokens)

param([switch]$Real)

$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$py = "venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "No existe el entorno virtual. Ejecuta primero scripts\instalar.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "== 1) Diagnostico de configuracion ==" -ForegroundColor Cyan
if ($Real) { & $py arquitecto_mcp.py --check } else { $env:ARQUITECTO_MOCK = "1"; & $py arquitecto_mcp.py --check }

Write-Host ""
Write-Host "== 2) Verificacion del servidor MCP ==" -ForegroundColor Cyan
if ($Real) { & $py scripts\verificar_servidor.py --real } else { & $py scripts\verificar_servidor.py }

Write-Host ""
Write-Host "== 3) Conversacion MCP por stdio (como Cursor) ==" -ForegroundColor Cyan
if ($Real) { & $py scripts\prueba_cliente_mcp.py --real } else { & $py scripts\prueba_cliente_mcp.py }

Write-Host ""
Write-Host "== 4) Simulacion del loop completo ==" -ForegroundColor Cyan
if ($Real) { & $py prueba_loop.py --turnos 3 } else { & $py prueba_loop.py --mock --turnos 4 }

Write-Host ""
Write-Host "== 5) Verificacion de la fabrica de proyectos ==" -ForegroundColor Cyan
if ($Real) { & $py scripts\verificar_fabrica.py --real } else { & $py scripts\verificar_fabrica.py }

Write-Host ""
Write-Host "== 6) Orquestador en seco (simulado, carpeta temporal) ==" -ForegroundColor Cyan
$temporal = Join-Path $env:TEMP ("orquestador-prueba-" + (Get-Random))
$env:ARQUITECTO_CARPETA_PROYECTOS = $temporal
$env:ARQUITECTO_REGISTRO = Join-Path $temporal "proyectos.json"
$env:ARQUITECTO_MOCK = "1"
& $py orquestador.py --idea "Proyecto de humo del orquestador" --proyecto "humo-orquestador" --plantillas python --turnos 1 --sin-probar
Remove-Item -Recurse -Force $temporal -ErrorAction SilentlyContinue
Remove-Item -Force "datos\orquestador_humo-orquestador.txt" -ErrorAction SilentlyContinue
Remove-Item Env:\ARQUITECTO_CARPETA_PROYECTOS -ErrorAction SilentlyContinue
Remove-Item Env:\ARQUITECTO_REGISTRO -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "== 7) Suite de pruebas (pytest) ==" -ForegroundColor Cyan
$tienePytest = & $py -c "import pytest, pytest_cov; print('si')" 2>$null
if ($tienePytest -eq "si") {
    & $py -m pytest -q
} else {
    Write-Host "pytest no esta instalado. Instalalo con: $py -m pip install -r requirements-dev.txt" -ForegroundColor Yellow
}


Write-Host ""
Write-Host "Pruebas terminadas." -ForegroundColor Green
