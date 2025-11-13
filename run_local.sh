#!/bin/bash

# Script para rodar o DataViz em modo 100% local
# Não requer conexão com S3 ou AWS

set -e  # Para em caso de erro

echo "=========================================="
echo "  DataViz - Modo Local"
echo "=========================================="
echo ""

# Define a KEY (pode ser sobrescrita via argumento)
KEY="${1:-employee-survey-demo}"

echo "Configurações:"
echo "  KEY: $KEY"
echo "  MODO: LOCAL (sem S3)"
echo "  PORTA: 8080"
echo "  DIRETÓRIO DE DADOS: local_data/"
echo ""

# Verifica se os arquivos necessários existem
CUBE_FILE="local_data/${KEY}_analytics_cube.csv"
QUESTIONNAIRES_FILE="local_data/${KEY}-questionnaires.csv"

echo "Verificando arquivos..."
if [ ! -f "$CUBE_FILE" ]; then
    echo "❌ ERRO: Arquivo não encontrado: $CUBE_FILE"
    echo ""
    echo "Arquivos disponíveis em local_data/:"
    ls -1 local_data/ 2>/dev/null || echo "  (vazio)"
    echo ""
    echo "Para criar dados para outra key, copie os arquivos de exemplo:"
    echo "  cp employee-survey-demo_analytics_cube.csv local_data/sua-key_analytics_cube.csv"
    echo "  cp employee-survey-demo-questionnaires.csv local_data/sua-key-questionnaires.csv"
    exit 1
fi

echo "✓ Analytics Cube encontrado: $CUBE_FILE"

if [ -f "$QUESTIONNAIRES_FILE" ]; then
    echo "✓ Questionnaires encontrado: $QUESTIONNAIRES_FILE"
else
    echo "⚠ Questionnaires não encontrado: $QUESTIONNAIRES_FILE (opcional)"
fi

echo ""
echo "Iniciando servidor..."
echo ""
echo "Acesse no navegador:"
echo "  http://localhost:8080/dataviz-svc/?key=$KEY"
echo ""
echo "Pressione Ctrl+C para parar o servidor"
echo ""
echo "=========================================="
echo ""

# Exporta variáveis de ambiente e roda o app
export KEY="$KEY"
export LOCAL_MODE="true"
export LOCAL_DATA_DIR="local_data"
export PORT=8080
export DATA_DIR=/tmp

# Roda a aplicação
python3 app.py
