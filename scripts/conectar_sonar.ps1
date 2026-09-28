<#
.SYNOPSIS
    Deja un SonarQube local listo para el proyecto: contrasena de admin y token.

.DESCRIPTION
    Se ejecuta una sola vez, despues de arrancar el servidor (scripts\sonar.ps1 o
    docker compose). Hace tres cosas:

      1. Espera a que el servidor responda en /api/system/status.
      2. Genera un token de analisis con el usuario admin. En el primer acceso
         SonarQube obliga a cambiar la contrasena, asi que la cambia por una
         aleatoria robusta y vuelve a intentarlo.
      3. Guarda SONAR_HOST_URL, SONAR_TOKEN y SONAR_ADMIN_PASSWORD en el .env
         (ignorado por git) y muestra la URL del panel.

    El token no se imprime en pantalla: queda en el .env para que lo lea
    scripts\sonar.ps1. Si el servidor ya tiene contrasena propia, pasala con
    -Contrasena.

.PARAMETER Servidor
    URL del servidor (def. http://localhost:9000).
.PARAMETER Usuario
    Usuario administrador (def. admin).
.PARAMETER Contrasena
    Contrasena actual de ese usuario. Si se omite se reutiliza la del .env
    (SONAR_ADMIN_PASSWORD) y, si no hay, la de fabrica (admin).
.PARAMETER NuevaContrasena
    Contrasena nueva (def. una aleatoria robusta que se guarda en el .env).
.PARAMETER NombreToken
    Nombre del token en SonarQube (def. ia-colaborativa).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\conectar_sonar.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\conectar_sonar.ps1 -Contrasena "la-que-puse"
#>
[CmdletBinding()]
param(
    [string]$Servidor = "http://localhost:9000",
    [string]$Usuario = "admin",
    [string]$Contrasena = "",
    [string]$NuevaContrasena = "",
    [string]$NombreToken = "ia-colaborativa"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$raiz = Split-Path -Parent $PSScriptRoot
$archivoEnv = Join-Path $raiz ".env"
$base = $Servidor.TrimEnd("/")

function Leer-Env([string]$clave) {
    if (-not (Test-Path $archivoEnv)) { return "" }
    foreach ($linea in Get-Content $archivoEnv) {
        if ($linea -match ("^\s*" + [regex]::Escape($clave) + "\s*=\s*(.*)$")) { return $Matches[1].Trim() }
    }
    return ""
}

# Sin -Contrasena se reutiliza la de una ejecucion anterior (.env) y, si no hay
# ninguna, la de fabrica del servidor recien instalado.
if (-not $Contrasena) { $Contrasena = Leer-Env "SONAR_ADMIN_PASSWORD" }
if (-not $Contrasena) { $Contrasena = "admin" }

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Aviso($texto) { Write-Host "   $texto" -ForegroundColor Yellow }
function Bien($texto) { Write-Host "   $texto" -ForegroundColor Green }

function Basico([string]$usuario, [string]$clave) {
    $pareja = [Text.Encoding]::ASCII.GetBytes("${usuario}:${clave}")
    return @{ Authorization = "Basic " + [Convert]::ToBase64String($pareja) }
}

function Aleatoria([int]$largo = 20) {
    # Contrasena que cumple la politica por defecto (mayuscula, minuscula,
    # digito y simbolo) y sin caracteres ambiguos.
    $mayusculas = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    $minusculas = "abcdefghijkmnopqrstuvwxyz"
    $digitos = "23456789"
    $simbolos = "!@#%+*?"
    $todos = $mayusculas + $minusculas + $digitos + $simbolos
    $azar = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $salida = New-Object System.Text.StringBuilder
    foreach ($juego in @($mayusculas, $minusculas, $digitos, $simbolos)) {
        $byte = New-Object byte[] 1
        $azar.GetBytes($byte)
        [void]$salida.Append($juego[$byte[0] % $juego.Length])
    }
    while ($salida.Length -lt $largo) {
        $byte = New-Object byte[] 1
        $azar.GetBytes($byte)
        [void]$salida.Append($todos[$byte[0] % $todos.Length])
    }
    $letras = $salida.ToString().ToCharArray()
    $bufer = New-Object byte[] $letras.Length
    $azar.GetBytes($bufer)
    for ($i = $letras.Length - 1; $i -gt 0; $i--) {
        $j = $bufer[$i] % ($i + 1)
        $temporal = $letras[$i]
        $letras[$i] = $letras[$j]
        $letras[$j] = $temporal
    }
    return -join $letras
}

function Invocar-Sonar([string]$metodo, [string]$ruta, $cabecera, $cuerpo) {
    $opciones = @{ Method = $metodo; Uri = ($base + $ruta); TimeoutSec = 60 }
    if ($cabecera) { $opciones.Headers = $cabecera }
    if ($cuerpo) { $opciones.Body = $cuerpo }
    return Invoke-RestMethod @opciones
}

function Fijar-Env([string]$clave, [string]$valor) {
    $lineas = @()
    if (Test-Path $archivoEnv) { $lineas = @(Get-Content $archivoEnv) }
    $patron = "^\s*" + [regex]::Escape($clave) + "\s*="
    $encontrado = $false
    for ($i = 0; $i -lt $lineas.Count; $i++) {
        if ($lineas[$i] -match $patron) {
            $lineas[$i] = "$clave=$valor"
            $encontrado = $true
            break
        }
    }
    if (-not $encontrado) { $lineas += "$clave=$valor" }
    [IO.File]::WriteAllLines($archivoEnv, $lineas, (New-Object Text.UTF8Encoding($false)))
}

# --------------------------------------------------------------------------
# 1. Esperar al servidor
# --------------------------------------------------------------------------
Paso "1/3 Esperando a SonarQube en $base"
$arriba = $false
for ($i = 0; $i -lt 90; $i++) {
    try {
        if ((Invoke-RestMethod -Uri "$base/api/system/status" -TimeoutSec 10).status -eq "UP") {
            $arriba = $true
            break
        }
    } catch { }
    Start-Sleep -Seconds 5
}
if (-not $arriba) {
    throw ("El servidor no responde en $base. Arrancalo con scripts\sonar.ps1 o " +
           "con: docker compose -f docker-compose.sonarqube.yml up -d")
}
Bien "Servidor UP."

# --------------------------------------------------------------------------
# 2. Token de analisis (cambiando la contrasena si es el primer acceso)
# --------------------------------------------------------------------------
Paso "2/3 Token de analisis"
$actual = $Contrasena
if (-not $NuevaContrasena) { $NuevaContrasena = Aleatoria 20 }

function Nuevo-Token([string]$clave) {
    # Se pide primero un token de usuario normal: sirve para analizar y ademas
    # deja leer el quality gate. Si el servidor ya no admite ese tipo (versiones
    # nuevas), se cae al token de analisis global.
    $rutas = @(
        "/api/user_tokens/generate?name=$NombreToken",
        "/api/user_tokens/generate?name=$NombreToken&type=GLOBAL_ANALYSIS_TOKEN"
    )
    try {
        Invocar-Sonar "Post" "/api/user_tokens/revoke?name=$NombreToken" (Basico $Usuario $clave) $null | Out-Null
    } catch { }
    foreach ($ruta in $rutas) {
        try {
            return (Invocar-Sonar "Post" $ruta (Basico $Usuario $clave) $null).token
        } catch {
            Aviso ("SonarQube responde: " + $_.Exception.Message)
        }
    }
    return $null
}

$token = Nuevo-Token $actual
if (-not $token) {
    Aviso "Primer acceso (contrasena de fabrica): la cambio por una aleatoria."
    try {
        Invocar-Sonar "Post" "/api/users/change_password" (Basico $Usuario $actual) @{
            login = $Usuario
            previousPassword = $actual
            password = $NuevaContrasena
        } | Out-Null
        $actual = $NuevaContrasena
        Bien "Contrasena cambiada."
    } catch {
        Aviso ("No he podido cambiarla: " + $_.Exception.Message)
    }
    $token = Nuevo-Token $actual
}
if (-not $token) {
    throw ("No he podido obtener un token. Entra en $base con $Usuario / $actual, " +
           "cambia la contrasena y repite: scripts\conectar_sonar.ps1 -Contrasena <la nueva>")
}
Bien "Token generado (no se muestra: queda en el .env)."

# --------------------------------------------------------------------------
# 3. Guardar en .env
# --------------------------------------------------------------------------
Paso "3/3 Guardando la configuracion en .env"
Fijar-Env "SONAR_HOST_URL" $base
Fijar-Env "SONAR_TOKEN" $token
Fijar-Env "SONAR_ADMIN_PASSWORD" $actual
Bien "Escrito en $archivoEnv (ignorado por git)."
Write-Host ""
Bien "Usuario    : $Usuario"
Bien "Contrasena : $actual   (tambien en .env como SONAR_ADMIN_PASSWORD)"
Bien "Panel      : $base"
Write-Host ""
Bien "Siguiente paso: powershell -ExecutionPolicy Bypass -File scripts\sonar.ps1"
