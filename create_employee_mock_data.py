"""
Gerador de dados mock para Employee Information Form
Baseado no questionário real fornecido
"""
import csv
import os
from datetime import datetime, timedelta
import random

# Criar diretório tmp
os.makedirs("/tmp", exist_ok=True)

KEY = "employee-survey-demo"

# Dados fictícios realistas
FIRST_NAMES = ["João", "Maria", "Pedro", "Ana", "Carlos", "Juliana", "Lucas", "Fernanda", 
               "Rafael", "Beatriz", "Gabriel", "Carolina", "Felipe", "Amanda", "Bruno"]
LAST_NAMES = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", 
              "Pereira", "Lima", "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho"]

ROLES = ["Full time", "Part time", "Casual", "Seasonal"]
WORK_FREQUENCIES = ["Day", "Week", "Fortnight", "Month", "Year"]
CITIES = ["São Paulo", "Rio de Janeiro", "Belo Horizonte", "Brasília", "Curitiba", "Porto Alegre"]
STREETS = ["Rua das Flores", "Av. Principal", "Rua Central", "Av. Paulista", "Rua Augusta"]

# Categorias para análise AI
CATEGORIES_BY_ROLE = {
    "Full time": ["Benefícios", "Carga horária", "Salário", "Ambiente de trabalho"],
    "Part time": ["Flexibilidade", "Remuneração", "Oportunidades"],
    "Casual": ["Horários", "Pagamento", "Estabilidade"],
    "Seasonal": ["Temporada", "Compensação", "Contratos"]
}

TOPICS = ["Satisfação", "Preocupações", "Sugestões", "Feedback positivo", "Reclamação"]
SENTIMENTS = ["positivo", "negativo", "neutro"]

def generate_phone():
    return f"(11) 9{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"

def generate_ssn():
    return f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}"

def generate_email(first, last):
    return f"{first.lower()}.{last.lower()}@empresa.com"

def generate_address():
    street = random.choice(STREETS)
    number = random.randint(10, 9999)
    city = random.choice(CITIES)
    return f"{street}, {number}, {city}"

def generate_hours_by_role(role):
    if role == "Full time":
        return random.randint(35, 44), "Week"
    elif role == "Part time":
        return random.randint(15, 30), "Week"
    elif role == "Casual":
        return random.randint(5, 20), "Week"
    else:  # Seasonal
        return random.randint(20, 40), "Week"

def generate_income_by_role(role, hours, freq):
    # Calcular baseado em horas e tipo
    hourly_rates = {
        "Full time": random.randint(25, 60),
        "Part time": random.randint(20, 45),
        "Casual": random.randint(18, 35),
        "Seasonal": random.randint(22, 40)
    }
    
    hourly = hourly_rates[role]
    
    if freq == "Week":
        return hours * hourly, "Week"
    elif freq == "Month":
        return hours * hourly * 4, "Month"
    else:
        return hours * hourly * 52, "Year"

def generate_comment(role):
    comments = {
        "Full time": [
            "Gosto da estabilidade do trabalho full time",
            "Os benefícios são muito bons",
            "Gostaria de mais flexibilidade no horário",
            "O ambiente de trabalho é excelente",
            "Salário competitivo para o mercado"
        ],
        "Part time": [
            "A flexibilidade é ótima para minha rotina",
            "Gostaria de mais horas disponíveis",
            "Ambiente acolhedor",
            "Poderia ter mais benefícios",
            "Equilibro bem trabalho e estudos"
        ],
        "Casual": [
            "Bom para complementar renda",
            "Gostaria de mais estabilidade",
            "Horários flexíveis ajudam muito",
            "Poderia pagar melhor",
            "Boa experiência inicial"
        ],
        "Seasonal": [
            "Ótima oportunidade temporária",
            "Gostaria de contrato mais longo",
            "Compensação justa",
            "Boa equipe",
            "Experiência valiosa"
        ]
    }
    return random.choice(comments[role])

# ============================================================
# GERAR DADOS RAW (answers.csv)
# ============================================================
print("Criando employee survey - answers.csv...")

questions = [
    ("Q1", "Qual seu nome completo?"),
    ("Q2", "Qual seu email corporativo?"),
    ("Q3", "Qual seu endereço?"),
    ("Q4", "Qual seu telefone?"),
    ("Q5", "Qual seu SSN?"),
    ("Q6", "Qual seu tipo de contrato?"),
    ("Q7", "Quantas horas você trabalha por semana?"),
    ("Q8", "Qual sua renda?"),
    ("Q9", "Como você avalia sua experiência? (1-5)"),
    ("Q10", "Comentários adicionais sobre sua experiência:")
]

answers_data = []
num_employees = 50  # 50 funcionários

for i in range(num_employees):
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    name = f"{first} {last}"
    email = generate_email(first, last)
    address = generate_address()
    phone = generate_phone()
    ssn = generate_ssn()
    role = random.choice(ROLES)
    hours, freq = generate_hours_by_role(role)
    income, inc_freq = generate_income_by_role(role, hours, freq)
    rating = random.randint(3, 5)
    comment = generate_comment(role)
    
    date = (datetime.now() - timedelta(days=random.randint(0, 60))).strftime("%Y-%m-%d %H:%M:%S")
    resp_id = f"EMP_{i:04d}"
    
    # Adicionar resposta para cada pergunta
    answers_data.append({
        "respondent_id": resp_id,
        "question_id": "Q1",
        "question_description": questions[0][1],
        "answer": name,
        "date_of_response": date
    })
    
    answers_data.append({
        "respondent_id": resp_id,
        "question_id": "Q2",
        "question_description": questions[1][1],
        "answer": email,
        "date_of_response": date
    })
    
    answers_data.append({
        "respondent_id": resp_id,
        "question_id": "Q3",
        "question_description": questions[2][1],
        "answer": address,
        "date_of_response": date
    })
    
    answers_data.append({
        "respondent_id": resp_id,
        "question_id": "Q4",
        "question_description": questions[3][1],
        "answer": phone,
        "date_of_response": date
    })
    
    answers_data.append({
        "respondent_id": resp_id,
        "question_id": "Q5",
        "question_description": questions[4][1],
        "answer": ssn,
        "date_of_response": date
    })
    
    answers_data.append({
        "respondent_id": resp_id,
        "question_id": "Q6",
        "question_description": questions[5][1],
        "answer": role,
        "date_of_response": date
    })
    
    answers_data.append({
        "respondent_id": resp_id,
        "question_id": "Q7",
        "question_description": questions[6][1],
        "answer": f"{hours} horas por {freq.lower()}",
        "date_of_response": date
    })
    
    answers_data.append({
        "respondent_id": resp_id,
        "question_id": "Q8",
        "question_description": questions[7][1],
        "answer": f"R$ {income:.2f} por {inc_freq.lower()}",
        "date_of_response": date
    })
    
    answers_data.append({
        "respondent_id": resp_id,
        "question_id": "Q9",
        "question_description": questions[8][1],
        "answer": str(rating),
        "date_of_response": date
    })
    
    answers_data.append({
        "respondent_id": resp_id,
        "question_id": "Q10",
        "question_description": questions[9][1],
        "answer": comment,
        "date_of_response": date
    })

# Salvar answers.csv
with open(f"/tmp/{KEY}-answers.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "respondent_id", "question_id", "question_description", "answer", "date_of_response"
    ])
    writer.writeheader()
    writer.writerows(answers_data)

print(f"✅ Criado: /tmp/{KEY}-answers.csv ({len(answers_data)} registros)")

# ============================================================
# GERAR DADOS AI (analytics_cube.csv)
# ============================================================
print("\nCriando employee survey - analytics_cube.csv...")

cube_data = []

for i in range(num_employees):
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    name = f"{first} {last}"
    email = generate_email(first, last)
    address = generate_address()
    phone = generate_phone()
    ssn = generate_ssn()
    role = random.choice(ROLES)
    hours, freq = generate_hours_by_role(role)
    income, inc_freq = generate_income_by_role(role, hours, freq)
    rating = random.randint(3, 5)
    comment = generate_comment(role)
    
    date = (datetime.now() - timedelta(days=random.randint(0, 60))).strftime("%Y-%m-%d %H:%M:%S")
    resp_id = f"EMP_{i:04d}"
    
    # Determinar sentiment baseado no rating
    if rating >= 4:
        sentiment = "positivo"
    elif rating == 3:
        sentiment = "neutro"
    else:
        sentiment = "negativo"
    
    category = random.choice(CATEGORIES_BY_ROLE[role])
    topic = random.choice(TOPICS)
    
    # Q6 - Tipo de contrato (com AI insights)
    cube_data.append({
        "questionnaire_id": "QUEST_EMP_001",
        "survey_id": "SURV_EMP_2024",
        "respondent_id": resp_id,
        "date_of_response": date,
        "question_id": "Q6",
        "question_description": questions[5][1],
        "orig_answer": role,
        "answer": role,
        "category": "Tipo de contrato",
        "topic": "Modalidade de trabalho",
        "sentiment": sentiment,
        "intention": "informar",
        "confidence_level": f"{random.uniform(0.85, 0.99):.2f}"
    })
    
    # Q9 - Avaliação (com AI insights)
    cube_data.append({
        "questionnaire_id": "QUEST_EMP_001",
        "survey_id": "SURV_EMP_2024",
        "respondent_id": resp_id,
        "date_of_response": date,
        "question_id": "Q9",
        "question_description": questions[8][1],
        "orig_answer": str(rating),
        "answer": str(rating),
        "category": "Satisfação geral",
        "topic": "Avaliação",
        "sentiment": sentiment,
        "intention": "avaliar",
        "confidence_level": f"{random.uniform(0.90, 0.99):.2f}"
    })
    
    # Q10 - Comentários (com AI insights)
    cube_data.append({
        "questionnaire_id": "QUEST_EMP_001",
        "survey_id": "SURV_EMP_2024",
        "respondent_id": resp_id,
        "date_of_response": date,
        "question_id": "Q10",
        "question_description": questions[9][1],
        "orig_answer": comment,
        "answer": comment,
        "category": category,
        "topic": topic,
        "sentiment": sentiment,
        "intention": random.choice(["sugerir", "reclamar", "elogiar", "informar"]),
        "confidence_level": f"{random.uniform(0.75, 0.95):.2f}"
    })

# Salvar analytics_cube.csv
with open(f"/tmp/{KEY}_analytics_cube.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "questionnaire_id", "survey_id", "respondent_id", "date_of_response",
        "question_id", "question_description", "orig_answer", "answer",
        "category", "topic", "sentiment", "intention", "confidence_level"
    ])
    writer.writeheader()
    writer.writerows(cube_data)

print(f"✅ Criado: /tmp/{KEY}_analytics_cube.csv ({len(cube_data)} registros)")

# ============================================================
# GERAR QUESTIONÁRIO METADATA
# ============================================================
print("\nCriando questionnaire metadata...")

with open(f"/tmp/{KEY}-questionnaires.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "question_id", "question_description", "question_type", "answer_options"
    ])
    writer.writeheader()
    
    writer.writerow({
        "question_id": "Q1",
        "question_description": "Qual seu nome completo?",
        "question_type": "text",
        "answer_options": ""
    })
    
    writer.writerow({
        "question_id": "Q2",
        "question_description": "Qual seu email corporativo?",
        "question_type": "text",
        "answer_options": ""
    })
    
    writer.writerow({
        "question_id": "Q3",
        "question_description": "Qual seu endereço?",
        "question_type": "text",
        "answer_options": ""
    })
    
    writer.writerow({
        "question_id": "Q4",
        "question_description": "Qual seu telefone?",
        "question_type": "text",
        "answer_options": ""
    })
    
    writer.writerow({
        "question_id": "Q5",
        "question_description": "Qual seu SSN?",
        "question_type": "text",
        "answer_options": ""
    })
    
    writer.writerow({
        "question_id": "Q6",
        "question_description": "Qual seu tipo de contrato?",
        "question_type": "single-choice",
        "answer_options": "Full time|Part time|Casual|Seasonal"
    })
    
    writer.writerow({
        "question_id": "Q7",
        "question_description": "Quantas horas você trabalha por semana?",
        "question_type": "text",
        "answer_options": ""
    })
    
    writer.writerow({
        "question_id": "Q8",
        "question_description": "Qual sua renda?",
        "question_type": "text",
        "answer_options": ""
    })
    
    writer.writerow({
        "question_id": "Q9",
        "question_description": "Como você avalia sua experiência? (1-5)",
        "question_type": "numeric",
        "answer_options": "1|2|3|4|5"
    })
    
    writer.writerow({
        "question_id": "Q10",
        "question_description": "Comentários adicionais sobre sua experiência:",
        "question_type": "open-ended",
        "answer_options": ""
    })

print(f"✅ Criado: /tmp/{KEY}-questionnaires.csv")

print("\n" + "="*60)
print("🎉 Dados do Employee Survey criados com sucesso!")
print("="*60)
print(f"\n📊 Resumo:")
print(f"  - {num_employees} funcionários")
print(f"  - {len(answers_data)} respostas no total")
print(f"  - 10 perguntas")
print(f"  - Mix de Full time, Part time, Casual e Seasonal")
print(f"\n🚀 Para testar, use:")
print(f"  export KEY={KEY}")
print(f"  export DATA_DIR=/tmp")
print(f"  python3 app.py")
print(f"\n🌐 Acesse: http://localhost:8080/dataviz-svc/?key={KEY}")
