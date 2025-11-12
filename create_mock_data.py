"""
Script para criar dados mock para teste local (sem dependências externas)
"""
import csv
import os
from datetime import datetime, timedelta
import random

# Criar diretório tmp para dados mock
os.makedirs("/tmp", exist_ok=True)

# Mock key
KEY = "mock-test-123"

# 1. Criar mock de answers.csv (modo Raw)
print("Criando mock de answers.csv...")
questions = [
    ("Q1", "Como você avalia nosso atendimento?"),
    ("Q2", "Qual sua principal sugestão de melhoria?"),
    ("Q3", "Você recomendaria nosso serviço?"),
]

with open(f"/tmp/{KEY}-answers.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "respondent_id", "question_id", "question_description", "answer", "date_of_response"
    ])
    writer.writeheader()
    
    for i in range(100):
        for qid, qdesc in questions:
            writer.writerow({
                "respondent_id": f"RESP_{i:04d}",
                "question_id": qid,
                "question_description": qdesc,
                "answer": random.choice([
                    "Muito bom", "Bom", "Regular", "Ruim", "Muito ruim"
                ]) if qid == "Q1" else (
                    random.choice(["Sim", "Não", "Talvez"]) if qid == "Q3" else
                    random.choice([
                        "Melhorar o atendimento",
                        "Reduzir preços",
                        "Mais agilidade",
                        "Ampliar horários"
                    ])
                ),
                "date_of_response": (datetime.now() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d %H:%M:%S")
            })

print(f"✅ Criado: /tmp/{KEY}-answers.csv (300 registros)")

# 2. Criar mock de analytics_cube.csv (modo AI)
print("\nCriando mock de analytics_cube.csv...")

with open(f"/tmp/{KEY}_analytics_cube.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "questionnaire_id", "survey_id", "respondent_id", "date_of_response",
        "question_id", "question_description", "orig_answer", "answer",
        "category", "topic", "sentiment", "intention", "confidence_level"
    ])
    writer.writeheader()
    
    for i in range(100):
        for qid, qdesc in questions:
            answer = random.choice(["Muito bom", "Bom", "Regular", "Ruim"])
            writer.writerow({
                "questionnaire_id": "QUEST_001",
                "survey_id": "SURVEY_001",
                "respondent_id": f"RESP_{i:04d}",
                "date_of_response": (datetime.now() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d %H:%M:%S"),
                "question_id": qid,
                "question_description": qdesc,
                "orig_answer": answer,
                "answer": answer,
                "category": random.choice(["Atendimento", "Preço", "Qualidade", "Entrega"]),
                "topic": random.choice(["Satisfação", "Reclamação", "Sugestão", "Elogio"]),
                "sentiment": random.choice(["positivo", "negativo", "neutro"]),
                "intention": random.choice(["comprar", "reclamar", "informar", "cancelar"]),
                "confidence_level": f"{random.uniform(0.7, 1.0):.2f}"
            })

print(f"✅ Criado: /tmp/{KEY}_analytics_cube.csv (300 registros)")

print("\n" + "="*60)
print("🎉 Dados mock criados com sucesso!")
print("="*60)
print(f"\nPara testar, use:")
print(f"  export KEY={KEY}")
print(f"  export DATA_DIR=/tmp")
print(f"  python3 app.py")
print(f"\nAcesse: http://localhost:8080/dataviz-svc/?key={KEY}")
