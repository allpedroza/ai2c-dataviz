# 🌐 Disponibilizando o DataViz na Rede Local

Este guia explica como disponibilizar o painel DataViz na rede local para validação com stakeholders.

## 🚀 Início Rápido

```bash
./run_network.sh
```

O script irá:
1. ✅ Verificar os arquivos de dados necessários
2. 🔍 Detectar automaticamente o IP da sua máquina na rede
3. 🌐 Iniciar o servidor acessível para toda a rede local
4. 📋 Mostrar os URLs de acesso

## 📱 Compartilhando com Stakeholders

Após executar `./run_network.sh`, você verá URLs como:

```
Acesso pela rede (compartilhe com stakeholders):
  http://192.168.1.100:8080/dataviz-svc/?key=employee-survey-demo
  http://10.0.0.50:8080/dataviz-svc/?key=employee-survey-demo
```

**Compartilhe esses URLs** com os stakeholders que estão na mesma rede Wi-Fi/LAN.

## 🔒 Configuração de Firewall

### macOS

```bash
# Permite conexões na porta 8080
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /usr/local/bin/python3
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp /usr/local/bin/python3
```

### Linux (Ubuntu/Debian)

```bash
# UFW
sudo ufw allow 8080/tcp

# Firewalld (CentOS/RHEL)
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --reload
```

### Windows

1. Abra "Firewall do Windows Defender"
2. Clique em "Configurações avançadas"
3. Selecione "Regras de Entrada" → "Nova Regra"
4. Tipo: Porta → TCP → Porta específica: 8080
5. Ação: Permitir conexão
6. Perfil: Marque "Privado" e "Domínio"
7. Nome: "DataViz - Porta 8080"

## 🔧 Configurações Avançadas

### Mudar a Porta

```bash
PORT=9000 ./run_network.sh
```

### Usar Dados de Produção (S3)

```bash
LOCAL_MODE=false API_EMAIL=email@example.com API_PASSWORD=senha ./run_network.sh
```

### Usar Outra Key

```bash
KEY=outra-pesquisa ./run_network.sh
```

## 🌍 Expondo para a Internet (Ngrok)

Para compartilhar com stakeholders **fora** da rede local, use [ngrok](https://ngrok.com/):

### 1. Instalar Ngrok

```bash
# macOS (Homebrew)
brew install ngrok/ngrok/ngrok

# Linux
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok
```

### 2. Criar Conta e Autenticar

```bash
# Cadastre-se em https://dashboard.ngrok.com/signup
# Copie seu authtoken e execute:
ngrok config add-authtoken SEU_TOKEN_AQUI
```

### 3. Expor o Servidor

Em um terminal, execute:
```bash
./run_network.sh
```

Em **outro terminal**, execute:
```bash
ngrok http 8080
```

Você verá algo como:
```
Forwarding  https://abc123.ngrok.io -> http://localhost:8080
```

Compartilhe o URL: `https://abc123.ngrok.io/dataviz-svc/?key=employee-survey-demo`

## 🔐 Segurança

### ⚠️ Importante

- Este servidor é **apenas para desenvolvimento/validação**
- Não use em produção sem proteção adequada
- No modo local (`LOCAL_MODE=true`), dados sensíveis são filtrados automaticamente
- Colunas PII (nome, email, telefone, etc.) são **removidas** automaticamente

### ✅ Modo Local (Padrão)

```bash
# Seguro para compartilhar - usa apenas dados de exemplo
LOCAL_MODE=true ./run_network.sh
```

### 🔒 Modo Produção

```bash
# Requer credenciais - cuidado ao compartilhar
LOCAL_MODE=false API_EMAIL=... API_PASSWORD=... ./run_network.sh
```

## 🆘 Troubleshooting

### "Não consigo acessar pela rede"

1. ✅ Verifique se o firewall está configurado (ver seção acima)
2. ✅ Confirme que está na mesma rede Wi-Fi/LAN
3. ✅ Teste acessar de outro dispositivo: `ping 192.168.x.x`
4. ✅ Verifique se o servidor está rodando: terminal deve mostrar "Dash is running..."

### "Porta já em uso"

```bash
# Use outra porta
PORT=9000 ./run_network.sh
```

### "Arquivos não encontrados"

```bash
# Verifique se os arquivos estão no local correto
ls local_data/

# Deve ter:
# - employee-survey-demo_analytics_cube.csv
# - employee-survey-demo-questionnaires.csv
# - employee-survey-demo-answers.csv
```

### "IPs não detectados automaticamente"

Execute manualmente:
```bash
# macOS/Linux
ifconfig | grep "inet "

# Linux alternativo
ip addr show

# Windows (PowerShell)
ipconfig
```

Use o IP listado para montar o URL: `http://SEU_IP:8080/dataviz-svc/?key=employee-survey-demo`

## 📞 Suporte

Problemas? Verifique:
1. Terminal mostra erros? Leia a mensagem de erro
2. Console do navegador (F12) mostra erros?
3. Testou acesso local primeiro? `http://localhost:8080/dataviz-svc/`
