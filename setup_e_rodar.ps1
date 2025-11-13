# ==============================================================================
# Script Automático para Windows: Setup + Rodar DataViz
# ==============================================================================
# Execute no PowerShell: .\setup_e_rodar.ps1
# ==============================================================================

Write-Host ""
Write-Host "==========================================" -ForegroundColor Blue
Write-Host "  DataViz - Setup Automático (Windows)"
Write-Host "==========================================" -ForegroundColor Blue
Write-Host ""

# 1. Verifica Python
Write-Host "[1/5] Verificando Python..." -ForegroundColor Blue
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ $pythonVersion encontrado" -ForegroundColor Green
} catch {
    Write-Host "✗ Python não encontrado!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Por favor, instale Python 3 de: https://www.python.org/downloads/"
    Write-Host "IMPORTANTE: Marque a opção 'Add Python to PATH' durante a instalação"
    exit 1
}
Write-Host ""

# 2. Cria ambiente virtual se não existir
Write-Host "[2/5] Verificando ambiente virtual..." -ForegroundColor Blue
if (-Not (Test-Path "venv")) {
    Write-Host "  Criando ambiente virtual..."
    python -m venv venv
    Write-Host "✓ Ambiente virtual criado" -ForegroundColor Green
} else {
    Write-Host "✓ Ambiente virtual já existe" -ForegroundColor Green
}
Write-Host ""

# 3. Ativa ambiente virtual
Write-Host "[3/5] Ativando ambiente virtual..." -ForegroundColor Blue
try {
    & .\venv\Scripts\Activate.ps1
    Write-Host "✓ Ambiente ativado" -ForegroundColor Green
} catch {
    Write-Host "✗ Erro ao ativar ambiente virtual" -ForegroundColor Red
    Write-Host ""
    Write-Host "Execute este comando no PowerShell como ADMINISTRADOR:" -ForegroundColor Yellow
    Write-Host "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser"
    Write-Host ""
    Write-Host "Depois execute este script novamente."
    exit 1
}
Write-Host ""

# 4. Instala dependências
Write-Host "[4/5] Instalando dependências..." -ForegroundColor Blue
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
Write-Host "✓ Dependências instaladas" -ForegroundColor Green
Write-Host ""

# 5. Verifica arquivos
Write-Host "[5/5] Verificando arquivos de dados..." -ForegroundColor Blue
$env:LOCAL_MODE = if ($env:LOCAL_MODE) { $env:LOCAL_MODE } else { "true" }
$env:LOCAL_DATA_DIR = if ($env:LOCAL_DATA_DIR) { $env:LOCAL_DATA_DIR } else { "local_data" }
$env:KEY = if ($env:KEY) { $env:KEY } else { "employee-survey-demo" }

if ($env:LOCAL_MODE -eq "true") {
    $cubeFile = Join-Path $env:LOCAL_DATA_DIR "$($env:KEY)_analytics_cube.csv"
    if (Test-Path $cubeFile) {
        Write-Host "✓ Dados encontrados: $cubeFile" -ForegroundColor Green
    } else {
        Write-Host "⚠ Dados não encontrados: $cubeFile" -ForegroundColor Yellow
        Write-Host "  Certifique-se de ter os arquivos CSV em $($env:LOCAL_DATA_DIR)/"
    }
}
Write-Host ""

Write-Host "==========================================" -ForegroundColor Blue
Write-Host "Setup completo!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Blue
Write-Host ""

# Pergunta ao usuário
Write-Host "Como você quer rodar o servidor?"
Write-Host ""
Write-Host "  1) Apenas na minha máquina (localhost)"
Write-Host "  2) Compartilhar na rede local (Wi-Fi)"
Write-Host "  3) Sair (vou rodar manualmente)"
Write-Host ""
$choice = Read-Host "Escolha [1-3]"

switch ($choice) {
    1 {
        Write-Host ""
        Write-Host "Iniciando servidor local..." -ForegroundColor Blue
        Write-Host ""
        $env:PORT = if ($env:PORT) { $env:PORT } else { "8080" }
        $env:HOST = "127.0.0.1"

        Write-Host "Acesse: http://localhost:$($env:PORT)/dataviz-svc/?key=$($env:KEY)"
        Write-Host ""
        python app.py
    }
    2 {
        Write-Host ""
        Write-Host "Iniciando servidor na rede..." -ForegroundColor Blue
        Write-Host ""
        $env:PORT = if ($env:PORT) { $env:PORT } else { "8080" }
        $env:HOST = "0.0.0.0"

        # Detecta IP local
        $localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^127\.' -and $_.IPAddress -notmatch '^169\.254\.' } | Select-Object -First 1).IPAddress

        Write-Host "==========================================" -ForegroundColor Blue
        Write-Host "Servidor iniciado!" -ForegroundColor Green
        Write-Host "==========================================" -ForegroundColor Blue
        Write-Host ""
        Write-Host "Acesso local:" -ForegroundColor Blue
        Write-Host "  http://localhost:$($env:PORT)/dataviz-svc/?key=$($env:KEY)"
        Write-Host ""
        Write-Host "Acesso pela rede (compartilhe com stakeholders):" -ForegroundColor Blue
        Write-Host "  http://${localIP}:$($env:PORT)/dataviz-svc/?key=$($env:KEY)" -ForegroundColor Green
        Write-Host ""
        Write-Host "Pressione Ctrl+C para parar o servidor"
        Write-Host ""
        Write-Host "==========================================" -ForegroundColor Blue
        Write-Host ""

        python app.py
    }
    3 {
        Write-Host ""
        Write-Host "Ambiente preparado!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Para rodar manualmente:"
        Write-Host "  python app.py"
        Write-Host ""
        Write-Host "Lembre-se: o ambiente virtual está ATIVO."
        Write-Host "Para desativar: deactivate"
        Write-Host ""
    }
    default {
        Write-Host ""
        Write-Host "Opção inválida" -ForegroundColor Red
        exit 1
    }
}
