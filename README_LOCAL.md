# Modo Local - DataViz

## Visão Geral

O modo local permite rodar a aplicação DataViz **sem dependências de S3 ou AWS**, ideal para:
- Desenvolvimento e testes locais
- Validação da interface antes do deploy
- Demonstrações offline
- Desenvolvimento sem acesso à infraestrutura AWS

## Início Rápido

### 1. Execute o script

```bash
./run_local.sh
```

Isso iniciará o servidor com os dados de exemplo `employee-survey-demo`.

### 2. Acesse no navegador

```
http://localhost:8080/dataviz-svc/?key=employee-survey-demo
```

### 3. Para parar o servidor

Pressione `Ctrl+C` no terminal.

## Usando com Outra Key

Para testar com seus próprios dados:

```bash
./run_local.sh minha-pesquisa
```

Certifique-se de que os arquivos existem em `local_data/`:
- `minha-pesquisa_analytics_cube.csv`
- `minha-pesquisa-questionnaires.csv` (opcional)

## Estrutura de Diretórios

```
ai2c-dataviz/
├── local_data/                              # Dados locais (não commitados no git)
│   ├── employee-survey-demo_analytics_cube.csv
│   ├── employee-survey-demo-questionnaires.csv
│   └── employee-survey-demo-answers.csv
├── run_local.sh                             # Script de execução local
├── app.py                                   # Aplicação principal
└── README_LOCAL.md                          # Este arquivo
```

## Preparando Seus Dados

### 1. Analytics Cube (obrigatório)

Arquivo: `local_data/{key}_analytics_cube.csv`

Formato: CSV com separador `;`

Colunas obrigatórias:
```
questionnaire_id;survey_id;respondent_id;date_of_response;question_id;
orig_answer;category;topic;sentiment;intention;question_description;confidence_level
```

### 2. Questionnaires (opcional)

Arquivo: `local_data/{key}-questionnaires.csv`

Formato: CSV com separador `;`

Colunas:
```
topic;questionnaire_id;survey_id;question_id;question_description;
question_type;answer_options;marked
```

### 3. Answers (opcional, não usado no modo atual)

Arquivo: `local_data/{key}-answers.csv`

Formato: CSV com separador `;`

## Modo Manual

Se preferir não usar o script, rode manualmente:

```bash
export KEY=employee-survey-demo
export LOCAL_MODE=true
export LOCAL_DATA_DIR=local_data
export PORT=8080

python3 app.py
```

## Como Funciona

Quando `LOCAL_MODE=true`:

1. **Analytics Cube**: Carrega de `local_data/{key}_analytics_cube.csv` ou `{key}_analytics_cube.csv`
2. **Questionnaires**: Carrega de `local_data/{key}-questionnaires.csv` ou `{key}-questionnaires.csv`
3. **S3 é completamente ignorado**: Nenhuma chamada ao boto3 ou AWS

O sistema tenta carregar na seguinte ordem:
1. `local_data/{filename}`
2. `{filename}` (raiz do projeto)

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `KEY` | - | Key da pesquisa (obrigatório) |
| `LOCAL_MODE` | false | Ativa modo local (true/1/yes/sim) |
| `LOCAL_DATA_DIR` | local_data | Diretório com os dados locais |
| `PORT` | 8080 | Porta do servidor |
| `DATA_DIR` | /tmp | Diretório para cache (não usado no modo local) |

## Troubleshooting

### Erro: "Arquivo não encontrado"
```
[LOCAL] Nenhum arquivo local encontrado para key=minha-pesquisa
```

**Solução:** Verifique se o arquivo existe em `local_data/` com o nome exato:
```bash
ls -la local_data/minha-pesquisa_analytics_cube.csv
```

### Erro: "Colunas obrigatórias ausentes"
```
ValueError: Colunas obrigatórias ausentes no CUBE: ['sentiment', 'intention']
```

**Solução:** Verifique se o arquivo CSV tem todas as colunas obrigatórias. Use o arquivo de exemplo como referência:
```bash
head -1 local_data/employee-survey-demo_analytics_cube.csv
```

### Porta 8080 já em uso
```
OSError: [Errno 48] Address already in use
```

**Solução:** Mate o processo que está usando a porta ou use outra porta:
```bash
# Opção 1: Encontrar e matar o processo
lsof -ti:8080 | xargs kill -9

# Opção 2: Usar outra porta
export PORT=8081
./run_local.sh
```

### Caracteres estranhos (mojibake)
```
Pergunta: VocÃª conhece...
```

**Solução:** Salve o arquivo CSV com encoding UTF-8:
```bash
file -I local_data/sua-pesquisa_analytics_cube.csv
# Deve mostrar: charset=utf-8
```

## Migração para Produção

Após validar localmente, faça upload para o S3:

```bash
python upload_to_s3.py employee-survey-demo dev
```

Veja `COMO_ADICIONAR_DADOS.md` para mais detalhes sobre deploy em produção.

## Exemplos

### Exemplo 1: Testar dados de exemplo

```bash
./run_local.sh
# Acesse: http://localhost:8080/dataviz-svc/?key=employee-survey-demo
```

### Exemplo 2: Criar nova pesquisa local

```bash
# 1. Copie os arquivos de exemplo como template
cp local_data/employee-survey-demo_analytics_cube.csv \
   local_data/minha-pesquisa_analytics_cube.csv

# 2. Edite o arquivo com seus dados
nano local_data/minha-pesquisa_analytics_cube.csv

# 3. Execute
./run_local.sh minha-pesquisa
```

### Exemplo 3: Rodar em porta diferente

```bash
export PORT=3000
./run_local.sh
# Acesse: http://localhost:3000/dataviz-svc/?key=employee-survey-demo
```

## Logs

Durante a execução, você verá logs indicando o modo local:

```
[BOOT] BASE_PATH=/dataviz-svc/ | ASSETS_URL_PATH=/dataviz-svc/assets
[RUN] Starting Dash on 0.0.0.0:8080 | BASE_PATH=/dataviz-svc/
[LOCAL] Carregando cube de local_data/employee-survey-demo_analytics_cube.csv
[LOCAL] Lido local_data/employee-survey-demo-questionnaires.csv. Tamanho: 749 bytes.
```

Se você ver logs `[S3]`, significa que o modo local não está ativado corretamente.

## Arquivos de Exemplo Inclusos

- ✅ `employee-survey-demo_analytics_cube.csv` - 17 respostas de exemplo
- ✅ `employee-survey-demo-questionnaires.csv` - 4 perguntas
- ✅ `employee-survey-demo-answers.csv` - 5 respondentes

Use estes arquivos como referência para criar seus próprios dados.
