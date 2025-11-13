# 🚀 Início Rápido - DataViz

Guia simples para rodar o painel na sua máquina e compartilhar com outras pessoas.

---

## 📦 Passo 1: Preparar o Ambiente (só precisa fazer UMA VEZ)

### Mac/Linux

```bash
# 1. Entre na pasta do projeto
cd ai2c-dataviz

# 2. Crie o ambiente virtual (se ainda não existe)
python3 -m venv venv

# 3. Ative o ambiente virtual
source venv/bin/activate

# 4. Instale as dependências
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
# 1. Entre na pasta do projeto
cd ai2c-dataviz

# 2. Crie o ambiente virtual (se ainda não existe)
python -m venv venv

# 3. Ative o ambiente virtual
.\venv\Scripts\Activate.ps1

# 4. Instale as dependências
pip install -r requirements.txt
```

**💡 Dica**: Você saberá que o ambiente está ativo quando ver `(venv)` no início da linha do terminal.

---

## ▶️ Passo 2: Rodar o Painel

### Opção A: Apenas na sua máquina (localhost)

```bash
# Ative o ambiente (se ainda não estiver ativo)
source venv/bin/activate  # Mac/Linux
# OU
.\venv\Scripts\Activate.ps1  # Windows

# Execute
./run_local.sh
```

Acesse: http://localhost:8080/dataviz-svc/?key=employee-survey-demo

---

### Opção B: Compartilhar na rede local (Wi-Fi)

```bash
# Ative o ambiente
source venv/bin/activate  # Mac/Linux

# Execute
./run_network.sh
```

O script vai mostrar os URLs para compartilhar, exemplo:
```
Acesso pela rede (compartilhe com stakeholders):
  http://192.168.1.100:8080/dataviz-svc/?key=employee-survey-demo
```

**Copie esse URL e envie** para quem precisa acessar (precisa estar na mesma rede Wi-Fi).

---

### Opção C: Compartilhar com QUALQUER pessoa (Internet)

Use ngrok! Veja instruções detalhadas abaixo. ⬇️

---

## 🌐 Como Usar Ngrok (Compartilhar pela Internet)

### 1. Instalar o Ngrok

#### Mac (com Homebrew)
```bash
brew install ngrok/ngrok/ngrok
```

#### Linux
```bash
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | \
  sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && \
  echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | \
  sudo tee /etc/apt/sources.list.d/ngrok.list && \
  sudo apt update && sudo apt install ngrok
```

#### Windows
1. Baixe em: https://ngrok.com/download
2. Descompacte o arquivo
3. Coloque o `ngrok.exe` numa pasta (ex: `C:\ngrok\`)
4. Adicione essa pasta ao PATH do Windows

---

### 2. Criar Conta Grátis no Ngrok

1. Acesse: https://dashboard.ngrok.com/signup
2. Crie uma conta (pode usar Google/GitHub)
3. Após login, vá em: https://dashboard.ngrok.com/get-started/your-authtoken
4. **Copie seu authtoken** (aparece como `2gXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`)

---

### 3. Configurar o Ngrok (só precisa fazer UMA VEZ)

```bash
# Cole seu token aqui (substitua pelo token real)
ngrok config add-authtoken SEU_TOKEN_AQUI
```

Exemplo:
```bash
ngrok config add-authtoken 2gXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

---

### 4. Rodar o Painel + Ngrok

Você precisa de **2 terminais abertos**:

#### Terminal 1 - Rodar o servidor:
```bash
cd ai2c-dataviz
source venv/bin/activate  # Mac/Linux
./run_network.sh
```

Espere aparecer a mensagem:
```
Dash is running on http://0.0.0.0:8080/dataviz-svc/
```

#### Terminal 2 - Rodar o ngrok:
```bash
ngrok http 8080
```

Você verá algo assim:
```
Session Status    online
Forwarding        https://abc123xyz.ngrok.io -> http://localhost:8080
```

---

### 5. Compartilhar o Link

Copie a URL que aparece em `Forwarding` e adicione o caminho completo:

```
https://abc123xyz.ngrok.io/dataviz-svc/?key=employee-survey-demo
```

**Envie esse link** para qualquer pessoa! Elas podem acessar de qualquer lugar do mundo.

---

## 🛑 Para Parar Tudo

1. No terminal do ngrok: pressione `Ctrl+C`
2. No terminal do servidor: pressione `Ctrl+C`
3. Desative o ambiente virtual: `deactivate`

---

## 🆘 Problemas Comuns

### "comando não encontrado: python3"

Use `python` ao invés de `python3`:
```bash
python -m venv venv
```

### "Não consigo ativar o ambiente virtual no Windows"

Se der erro de permissão, execute no PowerShell **como Administrador**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Depois tente novamente:
```powershell
.\venv\Scripts\Activate.ps1
```

### "Porta 8080 já está em uso"

Mate o processo anterior:
```bash
# Mac/Linux
lsof -ti:8080 | xargs kill -9

# Windows (PowerShell como Admin)
Get-Process -Id (Get-NetTCPConnection -LocalPort 8080).OwningProcess | Stop-Process -Force
```

### "Ngrok não funciona / link expirou"

A conta gratuita do ngrok tem algumas limitações:
- Link muda toda vez que você reinicia
- Sessão expira após 2 horas (precisa reiniciar)

Para link fixo, considere upgrade: https://ngrok.com/pricing

### "phoneNumber ainda aparece"

Certifique-se de que está na branch correta e puxou as últimas mudanças:
```bash
git pull origin claude/fix-s3-data-loading-errors-011CV4whsKkwoPVV9EejmVRB
```

---

## 📝 Checklist Rápido

Antes de compartilhar, verifique:

- [ ] Ambiente virtual está ativo? (vê `(venv)` no terminal?)
- [ ] Servidor está rodando? (vê "Dash is running..."?)
- [ ] Consegue acessar localhost primeiro? http://localhost:8080/dataviz-svc/
- [ ] Se usando ngrok: URL está completo com `/dataviz-svc/?key=...`?
- [ ] Testou o link antes de compartilhar?

---

## 💡 Resumo Visual

```
┌─────────────────────────────────────────────┐
│  VOCÊ QUER COMPARTILHAR COM...              │
└─────────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
    Mesma rede Wi-Fi      Internet (qualquer lugar)
        │                       │
        ▼                       ▼
  ./run_network.sh      Terminal 1: ./run_network.sh
  Compartilhe o IP      Terminal 2: ngrok http 8080
  192.168.x.x:8080     Compartilhe URL do ngrok
```

---

## 🎯 Comandos Essenciais (Cola)

```bash
# Ativar ambiente
source venv/bin/activate        # Mac/Linux
.\venv\Scripts\Activate.ps1     # Windows

# Rodar painel localmente
./run_local.sh

# Rodar painel na rede
./run_network.sh

# Rodar ngrok (em outro terminal)
ngrok http 8080

# Desativar ambiente
deactivate
```

---

Pronto! Agora é só seguir o passo a passo. 🚀
