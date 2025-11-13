#!/bin/bash

# ==============================================================================
# Script para disponibilizar o DataViz na rede local
# ==============================================================================
#
# Este script inicia o servidor de forma que ele possa ser acessado por outros
# dispositivos na mesma rede (ex: stakeholders em validação).
#
# Uso:
#   ./run_network.sh
#
# ==============================================================================

set -e

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "  DataViz - Modo Rede Local"
echo "=========================================="
echo ""

# Configurações padrão (podem ser sobrescritas por variáveis de ambiente)
export KEY="${KEY:-employee-survey-demo}"
export LOCAL_MODE="${LOCAL_MODE:-true}"
export LOCAL_DATA_DIR="${LOCAL_DATA_DIR:-local_data}"
export PORT="${PORT:-8080}"
export HOST="${HOST:-0.0.0.0}"  # 0.0.0.0 permite acesso externo
export DATA_DIR="${DATA_DIR:-/tmp}"

echo -e "${BLUE}Configurações:${NC}"
echo "  KEY: $KEY"
echo "  MODO: $([ "$LOCAL_MODE" = "true" ] && echo "LOCAL (sem S3)" || echo "PRODUÇÃO (com S3)")"
echo "  PORTA: $PORT"
echo "  HOST: $HOST"
if [ "$LOCAL_MODE" = "true" ]; then
    echo "  DIRETÓRIO DE DADOS: $LOCAL_DATA_DIR/"
fi
echo ""

# Verifica arquivos no modo local
if [ "$LOCAL_MODE" = "true" ]; then
    echo -e "${BLUE}Verificando arquivos...${NC}"

    CUBE_FILE="${LOCAL_DATA_DIR}/${KEY}_analytics_cube.csv"
    QUEST_FILE="${LOCAL_DATA_DIR}/${KEY}-questionnaires.csv"

    if [ -f "$CUBE_FILE" ]; then
        echo -e "${GREEN}✓${NC} Analytics Cube encontrado: $CUBE_FILE"
    else
        echo -e "${YELLOW}⚠${NC} Analytics Cube não encontrado: $CUBE_FILE"
    fi

    if [ -f "$QUEST_FILE" ]; then
        echo -e "${GREEN}✓${NC} Questionnaires encontrado: $QUEST_FILE"
    else
        echo -e "${YELLOW}⚠${NC} Questionnaires não encontrado: $QUEST_FILE"
    fi
    echo ""
fi

# Detecta IP local
echo -e "${BLUE}Detectando endereços de rede...${NC}"
echo ""

# Para Mac/Linux
if command -v ifconfig &> /dev/null; then
    LOCAL_IPS=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -3)
elif command -v ip &> /dev/null; then
    LOCAL_IPS=$(ip addr show | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | cut -d/ -f1 | head -3)
else
    LOCAL_IPS="(não detectado - use ipconfig/ifconfig para descobrir)"
fi

echo -e "${BLUE}Iniciando servidor...${NC}"
echo ""
echo "=========================================="
echo -e "${GREEN}Servidor iniciado!${NC}"
echo "=========================================="
echo ""
echo -e "${BLUE}Acesso local:${NC}"
echo "  http://localhost:$PORT/dataviz-svc/?key=$KEY"
echo "  http://127.0.0.1:$PORT/dataviz-svc/?key=$KEY"
echo ""
echo -e "${BLUE}Acesso pela rede (compartilhe com stakeholders):${NC}"

for ip in $LOCAL_IPS; do
    echo -e "  ${GREEN}http://${ip}:${PORT}/dataviz-svc/?key=${KEY}${NC}"
done

echo ""
echo -e "${YELLOW}Dica de segurança:${NC}"
echo "  - Certifique-se de que o firewall permite conexões na porta $PORT"
echo "  - Este servidor é apenas para desenvolvimento/validação"
echo "  - Não exponha à internet pública sem proteção adequada"
echo ""
echo "Pressione Ctrl+C para parar o servidor"
echo ""
echo "=========================================="
echo ""

# Inicia o servidor Python
python3 app.py
