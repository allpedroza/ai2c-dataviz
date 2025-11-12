#!/bin/bash
# Script de teste local para o dashboard

echo "🚀 Iniciando Dashboard em modo de desenvolvimento..."
echo ""
echo "Configuração:"
echo "  - Porta: 8080"
echo "  - Ambiente: dev"
echo "  - BASE_PATH: /dataviz-svc/"
echo ""
echo "Para testar com dados reais, configure:"
echo "  export KEY='sua-key-aqui'"
echo "  export AWS_REGION='sa-east-1'"
echo ""
echo "Para testar SEM dados (modo demo):"
echo "  - Acesse: http://localhost:8080/dataviz-svc/"
echo ""

# Variáveis de ambiente para teste local
export PORT=8080
export BASE_PATH="/dataviz-svc/"
export APP_DEFAULT_ENV="dev"
export AWS_REGION="${AWS_REGION:-sa-east-1}"
export S3_BUCKET="ai2c-genai"
export S3_REPORTS_PREFIX="ai2c-reports/reports"
export S3_INPUTS_PREFIX="integrador-inputs"
export KEY="${KEY:-}"

# Rodar app
python3 app.py
