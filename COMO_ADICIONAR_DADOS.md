# Como Adicionar Dados para Visualização

## Visão Geral

O sistema de visualização de dados (DataViz) carrega dados do S3 seguindo uma estrutura específica. Este guia explica como preparar e fazer upload dos arquivos corretamente.

## Estrutura de Arquivos Necessários

Para cada pesquisa (identificada por uma `key`), você precisa de 3 arquivos:

### 1. Analytics Cube (`{key}_analytics_cube.csv`)

**Descrição:** Dados processados com categorização, sentimentos e intenções já analisados pela IA.

**Formato:** CSV com separador `;`

**Colunas Obrigatórias:**
- `questionnaire_id` - ID do questionário
- `survey_id` - ID da pesquisa
- `respondent_id` - ID do respondente
- `date_of_response` - Data da resposta (formato: YYYY-MM-DD)
- `question_id` - ID da pergunta
- `orig_answer` - Resposta original do usuário
- `category` - Categoria da resposta (ex: "Barreira Técnica", "Preferência Pessoal")
- `topic` - Tópico principal (ex: "Dificuldade de Uso", "Hábito Analógico")
- `sentiment` - Sentimento (Positivo, Negativo, Neutro)
- `intention` - Intenção identificada
- `question_description` - Texto completo da pergunta

**Colunas Opcionais:**
- `confidence_level` - Nível de confiança da análise (0.0 a 1.0)

**Local no S3:**
```
s3://{bucket}/ai2c-reports/reports/{key}/{key}_analytics_cube.csv
```
Onde `{bucket}` é `ai2c-genai-dev` (desenvolvimento) ou `ai2c-genai` (produção).

### 2. Questionnaires (`{key}-questionnaires.csv`)

**Descrição:** Metadados sobre as perguntas do questionário.

**Formato:** CSV com separador `;`

**Colunas:**
- `topic` - Tópico da pergunta (pode ser vazio)
- `questionnaire_id` - ID do questionário
- `survey_id` - ID da pesquisa (pode ser vazio)
- `question_id` - ID único da pergunta
- `question_description` - Texto completo da pergunta
- `question_type` - Tipo da pergunta: `open-ended`, `single-choice`, `multiple-choice`
- `answer_options` - Opções de resposta separadas por `|` (ex: "Sim|Não|Não sei")
- `marked` - Marcador (geralmente "1")

**Exemplo:**
```csv
"topic";"questionnaire_id";"survey_id";"question_id";"question_description";"question_type";"answer_options";"marked"
"";"employee-survey-demo";"";"pergunta1";"Você conhece o serviço?";"multiple-choice";"Sim|Não";"1"
"";"employee-survey-demo";"";"pergunta2";"Por quê?";"open-ended";"";"1"
```

**Local no S3:**
```
s3://ai2c-genai/integrador-inputs/{key}-questionnaires.csv
```

### 3. Answers (`{key}-answers.csv`)

**Descrição:** Respostas brutas da pesquisa, exportadas do sistema de coleta.

**Formato:** CSV com separador `;`

**Colunas Fixas:**
- `updatedAt` - Data/hora da resposta
- `label` - Label da campanha
- `name` - Nome do respondente
- `lastName` - Sobrenome
- `email` - Email
- `phoneNumber` - Telefone
- `cdc` - CDC (pode ser vazio)
- `allowEnterpriseToContact` - Permissão de contato

**Colunas Dinâmicas:**
- Cada pergunta do questionário aparece como uma coluna adicional
- O nome da coluna é o texto completo da pergunta

**Exemplo:**
```csv
"updatedAt";"label";"name";"lastName";"email";"phoneNumber";"cdc";"allowEnterpriseToContact";"Você conhece o serviço?";"Por quê?"
"8/21/2025, 12:45:44 AM";"campanha1";"João";"Silva";"joao@email.com";"+5521999999999";"";"Sim";"Sim";"Porque é útil"
```

**Local no S3:**
```
s3://ai2c-genai/integrador-inputs/{key}-answers.csv
```

## Fluxo de Carregamento

O sistema tenta carregar os dados na seguinte ordem:

1. **Cube:** Tenta baixar do S3 do ambiente, se falhar tenta o arquivo local na raiz do projeto
2. **Questionnaires:** Tenta JSON no bucket do ambiente, depois CSV no bucket do ambiente, depois bucket base
3. **Answers:** (se aplicável) Tenta no bucket do ambiente, depois no bucket base

## Como Fazer Upload para o S3

### Opção 1: Usando o script Python

```bash
python upload_to_s3.py employee-survey-demo dev
```

O script irá:
1. Verificar se os arquivos existem localmente
2. Mostrar quais arquivos serão enviados
3. Pedir confirmação
4. Fazer upload para os caminhos corretos no S3

### Opção 2: Manualmente via AWS CLI

```bash
# Analytics Cube
aws s3 cp employee-survey-demo_analytics_cube.csv \
  s3://ai2c-genai-dev/ai2c-reports/reports/employee-survey-demo/

# Questionnaires
aws s3 cp employee-survey-demo-questionnaires.csv \
  s3://ai2c-genai/integrador-inputs/

# Answers
aws s3 cp employee-survey-demo-answers.csv \
  s3://ai2c-genai/integrador-inputs/
```

### Opção 3: Fallback Local (Desenvolvimento)

Para testes locais, você pode colocar apenas o arquivo `{key}_analytics_cube.csv` na raiz do projeto:

```
/home/user/ai2c-dataviz/employee-survey-demo_analytics_cube.csv
```

O sistema tentará carregar deste local se o download do S3 falhar.

## Testando Localmente

Depois de criar os arquivos, você pode testar localmente:

```bash
export KEY=employee-survey-demo
export DATA_DIR=/tmp
export PORT=8080
python3 app.py
```

Acesse: http://localhost:8080/dataviz-svc/?key=employee-survey-demo

## Arquivos de Exemplo

Este repositório inclui arquivos de exemplo para `employee-survey-demo`:
- ✓ `employee-survey-demo_analytics_cube.csv`
- ✓ `employee-survey-demo-questionnaires.csv`
- ✓ `employee-survey-demo-answers.csv`

Use-os como referência para criar dados para outras pesquisas.

## Troubleshooting

### Erro: "Cubo de dados não encontrado"
- Verifique se o arquivo `{key}_analytics_cube.csv` existe no S3 ou localmente
- Verifique se o nome do arquivo segue o padrão exato: `{key}_analytics_cube.csv`

### Erro: "Colunas obrigatórias ausentes no CUBE"
- Verifique se todas as colunas obrigatórias estão presentes no analytics cube
- Veja a lista completa em `REQUIRED_COLS` no app.py

### Erro 404 ao baixar do S3
- Verifique suas credenciais AWS (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- Verifique se os arquivos existem nos caminhos corretos no S3
- Verifique as permissões de leitura no bucket

### Caracteres estranhos (mojibake)
- O sistema tenta detectar e corrigir automaticamente
- Use encoding UTF-8 ao salvar os arquivos CSV
- O separador deve ser `;` (ponto e vírgula)

## Variáveis de Ambiente

```bash
# Obrigatórias
KEY=employee-survey-demo          # Key da pesquisa a carregar

# Opcionais
ENVIRONMENT=dev                   # dev ou prod (default: dev)
AWS_REGION=sa-east-1             # Região AWS (default: sa-east-1)
DATA_DIR=/tmp                     # Diretório para cache local (default: /tmp)
PORT=8080                         # Porta do servidor (default: 8080)
BASE_PATH=/dataviz-svc/          # Caminho base da aplicação
```

## Mais Informações

- Ver código em `app.py` (linhas 679-723 para carregamento do cube)
- Ver função `load_questionnaire_meta` (linha 308) para questionários
- Ver função `_s3_download_to_tmp` (linha 255) para lógica de download
