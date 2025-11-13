#!/usr/bin/env python3
"""
Script para fazer upload dos arquivos de dados para o S3 nos caminhos corretos.

Usage:
    python upload_to_s3.py <key> [environment]

Example:
    python upload_to_s3.py employee-survey-demo dev
"""

import os
import sys
import boto3
from botocore.exceptions import ClientError

def resolve_bucket(env):
    """Resolve o nome do bucket baseado no ambiente."""
    if env in ["dev", "development"]:
        return "ai2c-genai-dev"
    elif env in ["prod", "production"]:
        return "ai2c-genai"
    else:
        return "ai2c-genai"  # default

def upload_file(s3_client, local_path, bucket, s3_key):
    """Faz upload de um arquivo para o S3."""
    try:
        print(f"[UPLOAD] {local_path} -> s3://{bucket}/{s3_key}")
        s3_client.upload_file(local_path, bucket, s3_key)
        print(f"[OK] Upload concluído: s3://{bucket}/{s3_key}")
        return True
    except ClientError as e:
        print(f"[ERRO] Falha no upload de {local_path}: {e}")
        return False
    except FileNotFoundError:
        print(f"[ERRO] Arquivo não encontrado: {local_path}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Uso: python upload_to_s3.py <key> [environment]")
        print("Exemplo: python upload_to_s3.py employee-survey-demo dev")
        sys.exit(1)

    key = sys.argv[1]
    env = sys.argv[2] if len(sys.argv) > 2 else "dev"

    # Resolve bucket
    bucket = resolve_bucket(env)
    base_bucket = "ai2c-genai"

    # Configuração AWS
    region = os.getenv("AWS_REGION", "sa-east-1")
    s3 = boto3.client("s3", region_name=region)

    print(f"\n{'='*60}")
    print(f"Upload de dados para S3")
    print(f"Key: {key}")
    print(f"Ambiente: {env}")
    print(f"Bucket do ambiente: {bucket}")
    print(f"Bucket base: {base_bucket}")
    print(f"Região: {region}")
    print(f"{'='*60}\n")

    # Arquivos a serem enviados
    files_to_upload = [
        {
            "local": f"{key}_analytics_cube.csv",
            "bucket": bucket,
            "s3_key": f"ai2c-reports/reports/{key}/{key}_analytics_cube.csv",
            "description": "Analytics Cube (dados processados com IA)"
        },
        {
            "local": f"{key}-questionnaires.csv",
            "bucket": base_bucket,  # questionnaires vão para o bucket base
            "s3_key": f"integrador-inputs/{key}-questionnaires.csv",
            "description": "Questionnaires (metadados das perguntas)"
        },
        {
            "local": f"{key}-answers.csv",
            "bucket": base_bucket,  # answers vão para o bucket base
            "s3_key": f"integrador-inputs/{key}-answers.csv",
            "description": "Answers (respostas brutas da pesquisa)"
        }
    ]

    # Verifica quais arquivos existem localmente
    print("Verificando arquivos locais...\n")
    existing_files = []
    for file_info in files_to_upload:
        local_path = file_info["local"]
        if os.path.exists(local_path):
            size = os.path.getsize(local_path)
            print(f"[✓] {local_path} ({size} bytes) - {file_info['description']}")
            existing_files.append(file_info)
        else:
            print(f"[✗] {local_path} - NÃO ENCONTRADO")

    if not existing_files:
        print("\n[ERRO] Nenhum arquivo encontrado para upload!")
        sys.exit(1)

    print(f"\n{len(existing_files)} arquivo(s) será(ão) enviado(s).\n")

    # Pergunta confirmação
    response = input("Deseja prosseguir com o upload? (s/N): ")
    if response.lower() not in ['s', 'sim', 'y', 'yes']:
        print("Upload cancelado.")
        sys.exit(0)

    # Faz upload dos arquivos
    print("\nIniciando uploads...\n")
    success_count = 0
    for file_info in existing_files:
        if upload_file(s3, file_info["local"], file_info["bucket"], file_info["s3_key"]):
            success_count += 1
        print()  # linha em branco

    # Resumo
    print(f"{'='*60}")
    print(f"Resumo: {success_count}/{len(existing_files)} upload(s) bem-sucedido(s)")
    print(f"{'='*60}\n")

    if success_count == len(existing_files):
        print("[✓] Todos os arquivos foram enviados com sucesso!")
        print(f"\nAgora você pode acessar a aplicação com:")
        print(f"  KEY={key} python app.py")
    else:
        print("[!] Alguns uploads falharam. Verifique os erros acima.")
        sys.exit(1)

if __name__ == "__main__":
    main()
