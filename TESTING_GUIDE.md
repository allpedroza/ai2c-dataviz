# 🧪 Guia de Testes - Toggle Raw Data vs AI Insights

Este guia explica como testar as novas funcionalidades sem afetar produção.

---

## 📋 **O que foi implementado**

- ✅ Toggle no header: "📋 Dados Brutos" ↔️ "🤖 Análise Inteligente"
- ✅ Detecção automática de modo inicial (baseado em dados disponíveis)
- ✅ Carregamento de dados específico por modo
- ✅ Visualizações adaptadas para cada modo

---

## 🎯 **Opções de Teste**

### **Opção 1: Teste Local com Dados Mock** ⭐ (Mais Rápido)

**Passo a passo:**

```bash
# 1. Gerar dados mock
python3 create_mock_data.py

# 2. Configurar ambiente
export KEY=mock-test-123
export DATA_DIR=/tmp
export PORT=8080

# 3. Rodar aplicação
python3 app.py

# 4. Acessar no navegador
# http://localhost:8080/dataviz-svc/?key=mock-test-123
```

**Verificações:**
- [ ] Dashboard carrega sem erros
- [ ] Toggle aparece no header com 2 botões
- [ ] Modo inicial: "🤖 Análise Inteligente" (verde ativo)
- [ ] Ao clicar em "📋 Dados Brutos": alterna visual e dados
- [ ] Badge no topo muda: "Modo: Dados Brutos" → "Modo: Análise Inteligente"
- [ ] Tab "Análise por Pergunta": visualizações diferentes nos 2 modos
- [ ] Perguntas abertas no modo Raw: mostra top respostas
- [ ] Perguntas abertas no modo AI: mostra sentiment cards + categorias

---

### **Opção 2: Teste Local com Dados Reais do S3**

**Requisitos:**
- AWS CLI configurado (`aws configure`)
- Credenciais com acesso ao bucket S3
- KEY válida com dados

**Passo a passo:**

```bash
# 1. Configurar KEY real
export KEY="sua-key-aqui"  # Ex: 6864dcc63d7d7502472acc62
export AWS_REGION=sa-east-1

# 2. Rodar script de teste
./test_local.sh

# 3. Acessar no navegador
# http://localhost:8080/dataviz-svc/?key=sua-key-aqui&env=dev
```

**Cenários para testar:**

**a) KEY com dados AI disponíveis:**
- [ ] Inicializa em modo "Análise Inteligente"
- [ ] Ambos botões clicáveis
- [ ] Dados carregam do `_analytics_cube.csv`
- [ ] Categorias, sentimento e tópicos aparecem

**b) KEY apenas com answers.csv:**
- [ ] Inicializa em modo "Dados Brutos"
- [ ] Botão "Análise Inteligente" está desabilitado (cinza)
- [ ] Dados carregam de `answers.csv` + metadata
- [ ] Sem colunas de IA na visualização

---

### **Opção 3: Teste em Ambiente Staging/QA**

**Se você tem um ambiente de staging:**

```bash
# 1. Fazer deploy para staging (não produção!)
# Exemplo com AWS Copilot:
copilot svc deploy --name dataviz-svc --env staging

# 2. Acessar URL de staging
# https://staging.seu-dominio.com/dataviz-svc/?key=...
```

---

## 🔍 **Checklist Completo de Testes**

### **Interface do Toggle**
- [ ] Toggle aparece no header, alinhado à direita
- [ ] Labels claros: "📋 Dados Brutos" e "🤖 Análise Inteligente"
- [ ] Botão ativo tem cor sólida (primary/light)
- [ ] Botão inativo tem outline
- [ ] Transição suave ao clicar
- [ ] Tooltip/hover mostra estado atual

### **Lógica de Modo**
- [ ] Com dados AI: inicia em modo "Análise Inteligente"
- [ ] Sem dados AI: inicia em modo "Dados Brutos"
- [ ] Botão AI desabilitado quando dados não disponíveis
- [ ] Badge visual no topo indica modo ativo
- [ ] URL persiste modo ao recarregar (opcional para v2)

### **Tab: Análise por Pergunta**
- [ ] **Modo Raw:**
  - Cards mostram tipo de pergunta
  - Perguntas abertas: top 20 respostas
  - Perguntas fechadas: distribuição de respostas
  - SEM sentiment cards
  - SEM gráficos de categoria/tópico
  
- [ ] **Modo AI:**
  - Cards de sentimento aparecem (abertas)
  - Gráfico de categorias (abertas)
  - Filtros de categoria/tópico clicáveis
  - Drill-down funciona

### **Tab: Análises Personalizadas (Pivot)**
- [ ] **Modo Raw:**
  - Dimensões: apenas colunas originais
  - SEM sentiment, category, topic nas opções
  
- [ ] **Modo AI:**
  - Dimensões incluem: sentiment, category, topic
  - Filtros por dimensões AI funcionam
  - Drill-down mostra dados enriquecidos

### **Tab: Dados Brutos**
- [ ] **Modo Raw:**
  - Colunas AI ocultas
  - Apenas dados originais visíveis
  
- [ ] **Modo AI:**
  - Todas colunas visíveis
  - Colunas category, topic, sentiment, intention aparecem

### **Performance**
- [ ] Troca de modo é instantânea (< 1s)
- [ ] Cache funciona (não recarrega dados desnecessariamente)
- [ ] Sem erros no console do navegador
- [ ] Sem erros no terminal Python

---

## 🐛 **Problemas Comuns e Soluções**

### **Erro: ModuleNotFoundError**
```bash
# Instalar dependências
pip3 install -r requirements.txt
```

### **Erro: S3 Access Denied**
```bash
# Verificar credenciais AWS
aws sts get-caller-identity

# Verificar acesso ao bucket
aws s3 ls s3://ai2c-genai-dev/ai2c-reports/reports/
```

### **Erro: FileNotFoundError**
```bash
# Verificar se arquivo existe localmente
ls /tmp/mock-test-123*

# Ou no S3
aws s3 ls s3://ai2c-genai-dev/integrador-inputs/ | grep sua-key
```

### **Toggle não aparece**
- Verificar que `app.py` foi atualizado corretamente
- Limpar cache do navegador (Ctrl+Shift+R)
- Verificar console do navegador para erros JS

### **Modo não alterna**
- Verificar console Python para erros
- Verificar que callbacks foram atualizados
- Testar com dados mock primeiro

---

## 📊 **Como Validar Sucesso**

✅ **Teste passou se:**
1. Dashboard carrega sem erros
2. Toggle aparece e é clicável
3. Visualizações mudam ao alternar modo
4. Dados corretos aparecem em cada modo
5. Performance é aceitável (< 2s para trocar)
6. Sem regressões em funcionalidades existentes

❌ **Teste falhou se:**
1. Erros aparecem no console Python ou navegador
2. Toggle não responde a cliques
3. Dados errados aparecem
4. Visualizações quebram ao alternar
5. Cache não funciona (recarrega sempre)

---

## 🚀 **Próximos Passos Após Testes**

Se tudo funcionou:
1. ✅ Aprovar Pull Request
2. ✅ Merge para branch de staging
3. ✅ Deploy em staging e validar novamente
4. ✅ Deploy em produção fora do horário de pico
5. ✅ Monitorar logs e métricas

Se algo falhou:
1. 🐛 Criar issue descrevendo problema
2. 🔍 Compartilhar logs e screenshots
3. 🛠️ Ajustar código conforme necessário
4. 🔄 Re-testar

---

## 📞 **Suporte**

- Documentação: Ver comentários em `app.py`
- Logs: `tail -f /var/log/app.log` (produção)
- Métricas: CloudWatch / Datadog

