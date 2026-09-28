#!/usr/bin/env bash
# Instalador del Arquitecto Externo para macOS / Linux.
#
# Uso:
#   chmod +x scripts/instalar.sh && ./scripts/instalar.sh

set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

echo "=================================================="
echo " ARQUITECTO EXTERNO - INSTALACION"
echo "=================================================="

PY="python3"
command -v "$PY" >/dev/null 2>&1 || PY="python"

echo "[1/4] Entorno virtual en ./venv ..."
if [[ ! -x "venv/bin/python" ]]; then
    "$PY" -m venv venv
    echo "      creado."
else
    echo "      ya existe, se reutiliza."
fi

echo "[2/4] Instalando dependencias ..."
venv/bin/python -m pip install --upgrade pip --quiet
venv/bin/python -m pip install -r requirements.txt --quiet
echo "      mcp + requests instalados."

echo "[3/4] Archivo .env ..."
if [[ ! -f ".env" ]]; then
    cp .env.example .env
    echo "      se creo .env: abrelo y pega tu API key."
else
    echo "      .env ya existe, no se modifica."
fi

echo "[4/5] Registrando el servidor MCP (Cursor y Cline) ..."
venv/bin/python scripts/registrar_mcp.py

echo "[5/5] Verificando el servidor MCP y la fabrica de proyectos ..."
venv/bin/python scripts/verificar_servidor.py
venv/bin/python scripts/verificar_fabrica.py

echo ""
echo "Instalacion terminada."
echo "Interprete para Cursor:"
echo "  $RAIZ/venv/bin/python"
echo "Configuracion MCP: .cursor/mcp.json y los settings de Cline."
echo ""
echo "Siguiente paso: pega tu API key en .env y ejecuta"
echo "  venv/bin/python arquitecto_mcp.py --check"
echo "Para lanzar una idea completa de principio a fin:"
echo "  venv/bin/python orquestador.py --idea \"tu idea\""
