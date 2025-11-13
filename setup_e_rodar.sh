#!/bin/bash

# ==============================================================================
# Script Automático: Setup + Rodar DataViz
# ==============================================================================
# Este script faz TUDO automaticamente:
# 1. Cria ambiente virtual se não existir
# 2. Ativa o ambiente
# 3. Instala dependências
# 4. Roda o servidor na rede local
# ==============================================================================

set -e

# Cores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "=========================================="
echo "  DataViz - Setup Automático"
echo "=========================================="
echo ""

# 1. Verifica se Python está instalado
echo -e "${BLUE}[1/5]${NC} Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python3 não encontrado!${NC}"
    echo ""
    echo "Por favor, instale Python 3:"
    echo "  Mac: brew install python3"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  Windows: https://www.python.org/downloads/"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✓${NC} $PYTHON_VERSION encontrado"
echo ""

# 2. Cria ambiente virtual se não existir
echo -e "${BLUE}[2/5]${NC} Verificando ambiente virtual..."
if [ ! -d "venv" ]; then
    echo "  Criando ambiente virtual..."
    python3 -m venv venv
    echo -e "${GREEN}✓${NC} Ambiente virtual criado"
else
    echo -e "${GREEN}✓${NC} Ambiente virtual já existe"
fi
echo ""

# 3. Ativa ambiente virtual
echo -e "${BLUE}[3/5]${NC} Ativando ambiente virtual..."
source venv/bin/activate
echo -e "${GREEN}✓${NC} Ambiente ativado"
echo ""

# 4. Instala/atualiza dependências
echo -e "${BLUE}[4/5]${NC} Instalando dependências..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo -e "${GREEN}✓${NC} Dependências instaladas"
echo ""

# 5. Verifica arquivos de dados
echo -e "${BLUE}[5/5]${NC} Verificando arquivos de dados..."
export LOCAL_MODE="${LOCAL_MODE:-true}"
export LOCAL_DATA_DIR="${LOCAL_DATA_DIR:-local_data}"
export KEY="${KEY:-employee-survey-demo}"

if [ "$LOCAL_MODE" = "true" ]; then
    CUBE_FILE="${LOCAL_DATA_DIR}/${KEY}_analytics_cube.csv"
    if [ -f "$CUBE_FILE" ]; then
        echo -e "${GREEN}✓${NC} Dados encontrados: $CUBE_FILE"
    else
        echo -e "${YELLOW}⚠${NC} Dados não encontrados: $CUBE_FILE"
        echo "  Certifique-se de ter os arquivos CSV em $LOCAL_DATA_DIR/"
    fi
fi
echo ""

echo "=========================================="
echo -e "${GREEN}Setup completo!${NC}"
echo "=========================================="
echo ""

# Pergunta ao usuário como quer rodar
echo "Como você quer rodar o servidor?"
echo ""
echo "  1) Apenas na minha máquina (localhost)"
echo "  2) Compartilhar na rede local (Wi-Fi)"
echo "  3) Sair (vou rodar manualmente)"
echo ""
read -p "Escolha [1-3]: " choice

case $choice in
    1)
        echo ""
        echo -e "${BLUE}Iniciando servidor local...${NC}"
        echo ""
        export PORT="${PORT:-8080}"
        export HOST="127.0.0.1"

        echo "Acesse: http://localhost:$PORT/dataviz-svc/?key=$KEY"
        echo ""
        python3 app.py
        ;;
    2)
        echo ""
        echo -e "${BLUE}Iniciando servidor na rede...${NC}"
        echo ""
        ./run_network.sh
        ;;
    3)
        echo ""
        echo -e "${GREEN}Ambiente preparado!${NC}"
        echo ""
        echo "Para rodar manualmente:"
        echo "  Apenas local:    ./run_local.sh"
        echo "  Na rede:         ./run_network.sh"
        echo ""
        echo "Lembre-se: o ambiente virtual está ATIVO."
        echo "Para desativar: deactivate"
        echo ""
        ;;
    *)
        echo ""
        echo -e "${RED}Opção inválida${NC}"
        exit 1
        ;;
esac
