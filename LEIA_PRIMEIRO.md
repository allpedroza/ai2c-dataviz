# 👋 Bem-vindo ao DataViz!

## 🎯 Início SUPER Rápido (3 passos)

### Mac/Linux

```bash
# 1. Entre na pasta
cd ai2c-dataviz

# 2. Execute o script automático
./setup_e_rodar.sh

# 3. Escolha a opção 1 ou 2 e pronto! 🎉
```

### Windows (PowerShell)

```powershell
# 1. Entre na pasta
cd ai2c-dataviz

# 2. Execute o script automático
.\setup_e_rodar.ps1

# 3. Escolha a opção 1 ou 2 e pronto! 🎉
```

---

## 📚 Documentação

Temos guias completos para cada necessidade:

| Documento | O que é | Quando usar |
|-----------|---------|-------------|
| **[INICIO_RAPIDO.md](INICIO_RAPIDO.md)** | Guia completo passo a passo | Se você quer entender cada comando |
| **[README_REDE.md](README_REDE.md)** | Como compartilhar na rede | Para validação com stakeholders |
| **[README_LOCAL.md](README_LOCAL.md)** | Modo local sem S3 | Desenvolvimento e testes |

---

## 🚀 Compartilhar com Stakeholders

### Opção 1: Mesma rede Wi-Fi (mais fácil)

```bash
./setup_e_rodar.sh
# Escolha opção 2

# Compartilhe o URL que aparecer:
# http://192.168.x.x:8080/dataviz-svc/?key=...
```

### Opção 2: Internet (ngrok)

**Terminal 1:**
```bash
./setup_e_rodar.sh
# Escolha opção 2
```

**Terminal 2:**
```bash
# Primeiro configure o ngrok (só UMA VEZ):
ngrok config add-authtoken SEU_TOKEN_AQUI

# Depois rode:
ngrok http 8080

# Compartilhe o URL:
# https://xxxxx.ngrok.io/dataviz-svc/?key=...
```

**Pegar token do ngrok:**
1. Crie conta grátis: https://dashboard.ngrok.com/signup
2. Copie o token em: https://dashboard.ngrok.com/get-started/your-authtoken

---

## ❓ FAQ (Problemas Comuns)

### "Não consigo ativar o ambiente virtual no Windows"

Execute no PowerShell **como Administrador**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "Porta 8080 já está em uso"

```bash
# Mac/Linux
lsof -ti:8080 | xargs kill -9

# Windows (PowerShell como Admin)
Get-Process -Id (Get-NetTCPConnection -LocalPort 8080).OwningProcess | Stop-Process -Force
```

### "phoneNumber ainda aparece nos dados"

Atualize o código:
```bash
git pull origin claude/fix-s3-data-loading-errors-011CV4whsKkwoPVV9EejmVRB
```

### "Como sei se o ambiente virtual está ativo?"

Você verá `(venv)` no início da linha do terminal:
```
(venv) usuario@maquina:~/ai2c-dataviz$
```

### "Como desativar o ambiente virtual?"

```bash
deactivate
```

---

## 🎨 O que o Painel Faz

### Modo "Dados Processados" (padrão)
- Análise de sentimentos
- Categorização automática
- Tópicos principais
- Intenções detectadas

### Modo "Pesquisa" (toggle)
- Respostas brutas da pesquisa
- Estatísticas descritivas
- Distribuições por pergunta
- **Sem colunas PII** (nome, email, telefone removidos automaticamente)

---

## 🔒 Segurança

✅ **Colunas removidas automaticamente:**
- Nome, sobrenome, label
- Email, telefone
- CPF, RG, documentos
- Endereço, CEP
- IP, geolocalização

✅ **Modo local seguro** (padrão) - usa apenas dados de exemplo

---

## 📞 Precisa de Ajuda?

1. Leia o [INICIO_RAPIDO.md](INICIO_RAPIDO.md) completo
2. Verifique se o erro está no FAQ acima
3. Veja os logs no terminal (copie a mensagem de erro)

---

## 🎯 Comandos Úteis (Cola)

```bash
# Setup + rodar (faz tudo automaticamente)
./setup_e_rodar.sh

# Ativar ambiente manualmente
source venv/bin/activate              # Mac/Linux
.\venv\Scripts\Activate.ps1           # Windows

# Rodar apenas local
./run_local.sh

# Rodar na rede
./run_network.sh

# Ngrok (compartilhar na internet)
ngrok http 8080

# Desativar ambiente
deactivate

# Ver arquivos de dados
ls local_data/
```

---

## 🗂️ Estrutura do Projeto

```
ai2c-dataviz/
├── app.py                    # Aplicação principal
├── requirements.txt          # Dependências Python
├── local_data/              # Dados de exemplo (modo local)
│   ├── *_analytics_cube.csv
│   ├── *-answers.csv
│   └── *-questionnaires.csv
├── setup_e_rodar.sh         # Script automático (Mac/Linux) ⭐
├── setup_e_rodar.ps1        # Script automático (Windows) ⭐
├── run_local.sh             # Servidor local
├── run_network.sh           # Servidor na rede
├── LEIA_PRIMEIRO.md         # Este arquivo
├── INICIO_RAPIDO.md         # Guia completo
└── README_REDE.md           # Como compartilhar
```

---

Pronto! É só seguir os 3 passos lá em cima. 🚀

**Dica:** Use o script `setup_e_rodar.sh` (Mac/Linux) ou `setup_e_rodar.ps1` (Windows) - ele faz TUDO automaticamente!
