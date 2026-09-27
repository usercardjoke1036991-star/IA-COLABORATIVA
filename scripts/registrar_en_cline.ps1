# Registra el servidor MCP del Arquitecto Externo en Cline (CLI y aplicacion).
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\registrar_en_cline.ps1

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$py = Join-Path $raiz "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }
$servidor = Join-Path $raiz "arquitecto_mcp.py"
$nombre = "arquitecto-externo"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " REGISTRO EN CLINE - Arquitecto Externo" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "interprete: $py"
Write-Host "servidor  : $servidor"
Write-Host ""

# --- 1) Cline CLI -----------------------------------------------------------
$cline = Get-Command cline -ErrorAction SilentlyContinue
if ($cline) {
    Write-Host "[1/2] Registrando en Cline CLI ..." -ForegroundColor Yellow
    try {
        & cline mcp add $nombre --yes -- $py $servidor
        Write-Host "      ok: usa 'cline mcp list' para comprobarlo."
    } catch {
        Write-Host "      aviso: el CLI fallo ($_). Se intenta el archivo de settings." -ForegroundColor Yellow
    }
} else {
    Write-Host "[1/2] Cline CLI no esta en el PATH: se omite este paso." -ForegroundColor Yellow
    Write-Host "      Instalalo con: winget install Cline.Cline"
}

# --- 2) Archivo de settings de Cline ---------------------------------------
$destinos = @(
    @{
        Ruta  = Join-Path $env:USERPROFILE ".cline\data\settings\cline_mcp_settings.json"
        Marca = Join-Path $env:USERPROFILE ".cline"
    },
    @{
        Ruta  = Join-Path $env:APPDATA "Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json"
        Marca = Join-Path $env:APPDATA "Code"
    }
)

$entrada = [pscustomobject]@{
    command    = $py
    args       = @($servidor)
    env        = [pscustomobject]@{ ARQUITECTO_LOG = "INFO" }
    disabled   = $false
    autoApprove = @()
}

Write-Host "[2/2] Archivos de settings de Cline ..." -ForegroundColor Yellow
$tocados = 0
foreach ($destino in $destinos) {
    if (-not (Test-Path $destino.Marca)) {
        Write-Host "      omitido (no existe $($destino.Marca))"
        continue
    }
    $carpeta = Split-Path -Parent $destino.Ruta
    New-Item -ItemType Directory -Force -Path $carpeta | Out-Null

    if (Test-Path $destino.Ruta) {
        $contenido = Get-Content $destino.Ruta -Raw
        if ([string]::IsNullOrWhiteSpace($contenido)) {
            $json = [pscustomobject]@{}
        } else {
            try {
                $json = $contenido | ConvertFrom-Json
            } catch {
                Write-Host "      aviso: no se pudo leer $($destino.Ruta); se recrea." -ForegroundColor Yellow
                $json = [pscustomobject]@{}
            }
        }
    } else {
        $json = [pscustomobject]@{}
    }

    if (-not ($json.PSObject.Properties.Name -contains "mcpServers")) {
        $json | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
    }
    if ($json.mcpServers.PSObject.Properties.Name -contains $nombre) {
        $json.mcpServers.$nombre = $entrada
    } else {
        $json.mcpServers | Add-Member -NotePropertyName $nombre -NotePropertyValue $entrada
    }

    $json | ConvertTo-Json -Depth 10 | Set-Content -Path $destino.Ruta -Encoding UTF8
    Write-Host "      actualizado: $($destino.Ruta)" -ForegroundColor Green
    $tocados++
}

Write-Host ""
if ($tocados -eq 0) {
    Write-Host "No se encontro ninguna instalacion de Cline." -ForegroundColor Yellow
    Write-Host "Instala la extension o el CLI y repite el script." 
} else {
    Write-Host "Listo: reinicia Cline para que cargue el servidor MCP." -ForegroundColor Green
}
