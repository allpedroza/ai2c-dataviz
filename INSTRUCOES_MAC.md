# 🚀 Como Rodar o DataViz Localmente no seu Mac

## Pré-requisitos

1. **Python 3** (você já tem instalado)
2. **Git** (você já tem instalado)

## Passo a Passo

### 1️⃣ Clone o repositório (se ainda não clonou)

```bash
cd ~/Projects  # ou o diretório que preferir
git clone https://github.com/allpedroza/ai2c-dataviz.git
cd ai2c-dataviz
```

### 2️⃣ Faça checkout da branch com as alterações

```bash
git fetch origin
git checkout claude/fix-s3-data-loading-errors-011CV4whsKkwoPVV9EejmVRB
```

### 3️⃣ Crie os arquivos de dados locais

```bash
# Cria o diretório
mkdir -p local_data

# Copia os arquivos de exemplo que já existem no repositório
cp employee-survey-demo_analytics_cube.csv local_data/
cp employee-survey-demo-questionnaires.csv local_data/
cp employee-survey-demo-answers.csv local_data/
```

### 4️⃣ Instale as dependências Python

```bash
# Opção 1: Instalação global (mais simples)
pip3 install -r requirements.txt

# Opção 2: Usando virtual environment (recomendado)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5️⃣ Execute o servidor

```bash
# Torne o script executável (apenas na primeira vez)
chmod +x run_local.sh

# Execute
./run_local.sh
```

Você verá algo como:

```
==========================================
  DataViz - Modo Local
==========================================

Configurações:
  KEY: employee-survey-demo
  MODO: LOCAL (sem S3)
  PORTA: 8080
  DIRETÓRIO DE DADOS: local_data/

Verificando arquivos...
✓ Analytics Cube encontrado: local_data/employee-survey-demo_analytics_cube.csv
✓ Questionnaires encontrado: local_data/employee-survey-demo-questionnaires.csv

Iniciando servidor...

Acesse no navegador:
  http://localhost:8080/dataviz-svc/?key=employee-survey-demo
```

### 6️⃣ Abra no navegador

Abra o Chrome, Safari ou Firefox e acesse:

```
http://localhost:8080/dataviz-svc/?key=employee-survey-demo
```

### 7️⃣ Para parar o servidor

No terminal onde o servidor está rodando, pressione:

```
Ctrl + C
```

## 🎛️ Dois Modos de Visualização

A aplicação agora oferece **dois modos complementares**:

### 📊 Modo "Dados Processados" (Padrão)
Visualize dados enriquecidos com análises automáticas de IA:
- **Categorias** - Agrupamentos automáticos de respostas similares
- **Sentimentos** - Análise de polaridade (Positivo, Negativo, Neutro)
- **Intenções** - Identificação do objetivo por trás de cada resposta
- **Tópicos** - Temas principais extraídos das respostas
- **Confidence Level** - Nível de confiança de cada análise

**Arquivo usado:** `{key}_analytics_cube.csv`

### 📋 Modo "Pesquisa" (Novo)
Visualize respostas brutas com estatísticas descritivas:
- **Total de respostas** por pergunta
- **Respostas únicas** - Quantas variações existem
- **Taxa de resposta** - Percentual de respondentes
- **Distribuição** - Gráfico top 10 respostas mais comuns
- **Lista completa** - Todas as respostas em formato expansível

**Arquivo usado:** `{key}-answers.csv`

### Como Alternar Entre Modos

No topo da página, você verá um toggle:

```
[📊 Dados Processados]  [📋 Pesquisa (Respostas Brutas)]
```

Clique em qualquer botão para alternar. A descrição abaixo do toggle
e todo o conteúdo da página será atualizado automaticamente.

## 🎯 Testando com Seus Próprios Dados

### Para criar uma nova pesquisa local:

```bash
# 1. Copie os arquivos de exemplo como template
cp local_data/employee-survey-demo_analytics_cube.csv \
   local_data/minha-pesquisa_analytics_cube.csv

cp local_data/employee-survey-demo-questionnaires.csv \
   local_data/minha-pesquisa-questionnaires.csv

# 2. Edite os arquivos com seus dados
# Use Excel, LibreOffice ou qualquer editor de CSV
open -a "Microsoft Excel" local_data/minha-pesquisa_analytics_cube.csv

# 3. Salve como CSV com encoding UTF-8 e separador ";"

# 4. Execute com sua key
./run_local.sh minha-pesquisa
```

### Acesse:
```
http://localhost:8080/dataviz-svc/?key=minha-pesquisa
```

## 📝 Formato dos Dados

### Analytics Cube (obrigatório)

Arquivo: `local_data/{key}_analytics_cube.csv`

Separador: `;` (ponto e vírgula)

Colunas obrigatórias:
```
questionnaire_id;survey_id;respondent_id;date_of_response;question_id;
orig_answer;category;topic;sentiment;intention;question_description;confidence_level
```

Veja `local_data/employee-survey-demo_analytics_cube.csv` como exemplo.

### Questionnaires (opcional)

Arquivo: `local_data/{key}-questionnaires.csv`

Separador: `;`

Colunas:
```
topic;questionnaire_id;survey_id;question_id;question_description;
question_type;answer_options;marked
```

Veja `local_data/employee-survey-demo-questionnaires.csv` como exemplo.

## 🔧 Troubleshooting

### Porta 8080 já está em uso

```bash
# Descubra o processo
lsof -ti:8080

# Mate o processo
lsof -ti:8080 | xargs kill -9

# Ou use outra porta
export PORT=3000
./run_local.sh
# Acesse: http://localhost:3000/dataviz-svc/?key=employee-survey-demo
```

### Erro: "command not found: python3"

```bash
# Use python ao invés de python3
python run_local.sh
```

### Erro: "ModuleNotFoundError: No module named 'pandas'"

```bash
# Instale as dependências
pip3 install -r requirements.txt

# Ou se estiver usando venv
source venv/bin/activate
pip install -r requirements.txt
```

### Caracteres estranhos na visualização

Certifique-se de salvar o CSV com encoding UTF-8:

```bash
# Verificar encoding
file -I local_data/sua-pesquisa_analytics_cube.csv

# Deve mostrar: charset=utf-8
```

No Excel/LibreOffice, ao salvar:
1. Escolha "CSV UTF-8 (delimitado por vírgula)"
2. Mas use `;` como separador (não `,`)

## 📚 Documentação Completa

- `README_LOCAL.md` - Documentação completa do modo local
- `COMO_ADICIONAR_DADOS.md` - Como adicionar dados no S3 (produção)

## 🆘 Precisa de Ajuda?

Se encontrar problemas:

1. Verifique se está na branch correta: `git branch`
2. Verifique os logs no terminal onde o servidor está rodando
3. Confira se os arquivos estão em `local_data/` com os nomes corretos
4. Veja a documentação completa em `README_LOCAL.md`

## ✅ Checklist Rápido

- [ ] Clonei o repositório
- [ ] Fiz checkout da branch correta
- [ ] Criei o diretório `local_data/`
- [ ] Copiei os arquivos de exemplo para `local_data/`
- [ ] Instalei as dependências (`pip3 install -r requirements.txt`)
- [ ] Executei `./run_local.sh`
- [ ] Acessei http://localhost:8080/dataviz-svc/?key=employee-survey-demo
- [ ] Consegui visualizar o painel!

## 🎉 Pronto!

Agora você pode:
- Visualizar os dados de exemplo
- Criar seus próprios datasets locais
- Testar modificações na interface
- Validar antes de fazer deploy

Quando estiver satisfeito, você pode fazer upload dos dados para o S3:

```bash
python upload_to_s3.py employee-survey-demo dev
```

Boa visualização! 📊
