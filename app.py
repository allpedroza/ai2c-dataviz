import os, re, csv, glob, argparse, warnings
from typing import List, Optional, Dict, Tuple
from datetime import datetime
import traceback

warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import dash
from dash import dcc, html, Input, Output, State, MATCH, ALL
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objs as go
import plotly.io as pio
import io, base64
import boto3
import json

# ==============================
# 0) Helper para exibir erros na UI
# ==============================
# PATCH: máscara sem reindex
def _non_empty_mask(s: pd.Series) -> pd.Series:
    s2 = s.astype(str)
    return s2.str.strip().ne("") & ~s2.str.strip().str.lower().isin({"nan","none","null"})

# PATCH: pega o primeiro campo não-vazio para usar no gráfico
def _first_nonempty_series(sub: pd.DataFrame, candidates: list[str]) -> tuple[pd.Series, str|None]:
    for c in candidates:
        if c in sub.columns:
            s = sub[c].dropna().astype(str)
            m = _non_empty_mask(s)
            s = s[m]
            if not s.empty:
                return s, c
    return pd.Series(dtype=str), None


def _error_box(title: str, exc: Exception) -> html.Div:
    """Retorna um componente Dash exibindo o stack trace completo."""
    return html.Div(
        [
            html.H4(title, className="mb-2 text-danger"),
            html.Pre(
                traceback.format_exc(),
                style={
                    "whiteSpace": "pre-wrap",
                    "backgroundColor": "#f8f9fa",
                    "padding": "1rem",
                    "borderRadius": "8px",
                    "fontSize": "0.85rem",
                    "border": "1px solid #dee2e6"
                }
            )
        ],
        className="muted-box",
    )

# ==============================
# 1) Inicialização de Variáveis Globais
# ==============================
KEY = os.getenv("KEY", "")
EXPORT_HTML = False
PORT = int(os.getenv("PORT", "8080"))
LIKERT_1_5_IDS = set()
QDESC_MAP = {}
df_main = pd.DataFrame()

# ==============================
# 2) Setup e Constantes
# ==============================
try:
    from wordcloud import WordCloud, STOPWORDS
    HAS_WORDCLOUD = True
except ImportError:
    HAS_WORDCLOUD = False
    STOPWORDS = set()

# Cache para DataFrames carregados, chaveado por (ambiente, key)
DF_CACHE: Dict[Tuple[str, str], pd.DataFrame] = {}

# Configurações de S3 a partir de variáveis de ambiente
S3_BUCKET_BASE = os.getenv("S3_BUCKET_BASE", "ai2c-genai").strip()
S3_REPORTS_PREFIX = os.getenv("S3_REPORTS_PREFIX", "ai2c-reports/reports").strip().strip("/")
S3_INPUTS_PREFIX = os.getenv("S3_INPUTS_PREFIX", "integrador-inputs").strip().strip("/")
AWS_REGION = os.getenv("AWS_REGION", "sa-east-1")

# Modo local: se definido, carrega arquivos do diretório local sem usar S3
LOCAL_MODE = os.getenv("LOCAL_MODE", "").lower() in ("true", "1", "yes", "sim")
LOCAL_DATA_DIR = os.getenv("LOCAL_DATA_DIR", "local_data")

#. s3://ai2c-genai/integrador-inputs/6864dcc63d7d7502472acc62-questionnaires.csv


# Colunas obrigatórias no CUBE
REQUIRED_COLS = [
    "questionnaire_id","survey_id","respondent_id","date_of_response",
    "question_id","orig_answer","category","topic","sentiment","intention",
    "question_description"
]

# Colunas opcionais + valores padrão
OPTIONAL_COL_DEFAULTS = {
    "confidence_level": None,
}

NON_SEGMENTABLE = set(REQUIRED_COLS + list(OPTIONAL_COL_DEFAULTS.keys()) + ["answer", "orig_answer", "respondent_id"])

RAW_FILTER_COLS = ["category","topic","sentiment","intention","question_description","canal adesao","cluster"]

def raw_controls(df: pd.DataFrame):
    ops = {}
    for c in RAW_FILTER_COLS:
        if c in df.columns:
            vals = (df[c].dropna().astype(str).str.strip()
                    .loc[lambda s: s.ne("") & ~s.str.lower().isin({"nan","none","null"})]
                    .unique().tolist())
            vals.sort()
            ops[c] = [{"label": v, "value": v} for v in vals]
        else:
            ops[c] = []
    grid = []
    for c in RAW_FILTER_COLS:
        grid.append(
            html.Div([
                html.Label(c, className="fw-bold"),
                dcc.Dropdown(id={"type":"raw-filter","col":c},
                             options=ops[c], multi=True, placeholder=f"Filtrar {c}...")
            ])
        )
    return html.Div(className="ctrl-grid", children=grid)

# Mapeamento e estilo para Sentimento
SENTIMENT_ORDER = ["negativo", "neutro", "positivo"]
SENTIMENT_COLORS = {"positivo": "#10B981", "negativo": "#EF4444", "neutro": "#9CA3AF"}

SENTIMENT_MAP = {
    "pos": "positivo", "positivo": "positivo", "positive": "positivo",
    "neg": "negativo", "negativo": "negativo", "negative": "negativo",
    "neu": "neutro",   "neutro":   "neutro",   "neutral":  "neutro",
}

def normalize_sentiment(val) -> Optional[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    v = str(val).strip().lower()
    return SENTIMENT_MAP.get(v, v)

# ===== Helpers de normalização do questionário (PATCH NOVO) =====
def _norm_txt(x: str) -> str:
    if x is None:
        return ""
    x = str(x)
    x = x.strip().strip('"').strip("'")
    x = re.sub(r"\s+", " ", x)
    return x

def apply_bar_labels(fig: go.Figure) -> go.Figure:
    fig.update_traces(texttemplate="%{y}", textposition="outside", cliponaxis=False)
    fig.update_layout(uniformtext_minsize=8, uniformtext_mode="hide")
    return fig
 

def _norm_qtype(qt: str) -> str:
    qt = _norm_txt(qt).lower().replace("_", "-")
    # sinonímias comuns (pt/en)
    if qt in {"open-ended","open ended","texto","texto livre","campo aberto","aberta","comment","text"}:
        return "open-ended"
    if qt in {"multiple-choice","multiple choice","múltipla escolha","multipla escolha","checkbox","multi"}:
        return "multiple-choice"
    if qt in {"single-choice","single choice","categorica","categórica","categoria","radiogroup","dropdown"}:
        return "single-choice"
    if qt in {"number","numeric","rating","nps","escala"}:
        return "numeric"
    return qt


# Filtros da aba "Dados Brutos"
RAW_FILTER_SPECS = [
    ("category",              "Categoria",              "raw-dd-category"),
    ("topic",                 "Tópico",                 "raw-dd-topic"),
    ("sentiment",             "Sentimento",             "raw-dd-sentiment"),
    ("intention",             "Intenção",               "raw-dd-intention"),
    ("question_description",  "Pergunta",               "raw-dd-qdesc"),
    ("canal adesao",          "Canal adesão",           "raw-dd-canal"),
    ("cluster",               "Cluster",                "raw-dd-cluster"),
]

def _dropdown_options(df: pd.DataFrame, col: str, shorten: bool = False):
    if col not in df.columns:
        return []
    s = (df[col]
         .dropna()
         .astype(str)
         .map(lambda x: x.strip())
         .loc[lambda s: s.ne("") & ~s.str.lower().isin({"nan", "none", "null"})]
         .unique()
    )
    vals = sorted(s.tolist())
    if shorten:
        return [{"label": (v[:120] + "…" if len(v) > 120 else v), "value": v} for v in vals]
    return [{"label": v, "value": v} for v in vals]

def raw_filters_view(df: pd.DataFrame) -> dbc.Card:
    """Card de filtros do Raw."""
    rows = []
    for col, label, cid in RAW_FILTER_SPECS:
        opts = _dropdown_options(df, col, shorten=(col == "question_description"))
        ctrl = dbc.Col([
            html.Label(label, className="fw-bold"),
            dcc.Dropdown(
                id=cid, multi=True, options=opts, placeholder=f"Todos(as) {label.lower()}",
                clearable=True, maxHeight=320, optionHeight=32, disabled=(len(opts) == 0)
            )
        ], md=4)
        rows.append(ctrl)

    return dbc.Card([
        dbc.CardHeader(html.H5("Filtros", className="mb-0")),
        dbc.CardBody([
            html.Div(dbc.Row(rows, className="g-3")),
            html.Div(id="raw-filter-summary", className="text-muted mt-2", style={"fontSize": ".9rem"})
        ])
    ], className="mb-3 dash-card")

# ==============================
# 3) Estilo Plotly (AI2C style)
# ==============================
pio.templates["modern"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Poppins, system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif", size=13, color="#111111"),
        title=dict(x=0, xanchor="left", font=dict(size=18, color="#111111")),
        margin=dict(l=40, r=20, t=60, b=40),
        colorway=["#FF9800", "#FFB74D", "#FFA726", "#FB8C00", "#EF6C00", "#6C757D", "#111111"],
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, bgcolor="rgba(255,255,255,0)"),
        xaxis=dict(showgrid=False, zeroline=False, showline=True, linecolor="#ECECEC", linewidth=1, ticks="outside", tickcolor="#ECECEC"),
        yaxis=dict(showgrid=True, gridcolor="#F3F4F6", gridwidth=1, zeroline=False, showline=False),
        hoverlabel=dict(bgcolor="white", font=dict(color="#111111"), bordercolor="#ECECEC"),
    )
)
pio.templates.default = "modern"

# ==============================
# 4) Funções de Carregamento e Preparação de Dados
# ==============================
def normalize_env(env_in: str) -> str:
    e = (env_in or "").strip().lower()
    return "prod" if e in {"prd", "prod"} else "dev"

def resolve_bucket(env_resolved: str) -> str:
    return S3_BUCKET_BASE if env_resolved == "prod" else f"{S3_BUCKET_BASE}-{env_resolved}"

def s3_path_for_key(env_resolved: str, key: str) -> str:
    bucket = resolve_bucket(env_resolved)
    return f"s3://{bucket}/{S3_REPORTS_PREFIX}/{key}/{key}_analytics_cube.csv"

def _s3_download_to_tmp(env_resolved: str, key: str) -> Optional[str]:
    """Baixa s3://.../{key}_analytics_cube.csv p/ /tmp e retorna caminho local, ou None se falhar."""
    # MODO LOCAL: Tenta carregar do diretório local primeiro
    if LOCAL_MODE:
        local_candidates = [
            os.path.join(LOCAL_DATA_DIR, f"{key}_analytics_cube.csv"),
            f"{key}_analytics_cube.csv",  # raiz do projeto
        ]
        for local_path in local_candidates:
            if os.path.exists(local_path):
                print(f"[LOCAL] Carregando cube de {local_path}")
                return local_path
        print(f"[LOCAL] Nenhum arquivo local encontrado para key={key}")
        return None

    # MODO S3: Download do S3
    s3_uri = s3_path_for_key(env_resolved, key)
    _, _, rest = s3_uri.partition("s3://")
    bucket, _, keypath = rest.partition("/")
    local_dir = os.getenv("DATA_DIR", "/tmp")
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, f"{key}_analytics_cube.csv")
    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        print(f"[S3] Baixando {s3_uri} para {local_path}")
        s3.download_file(bucket, keypath, local_path)
        print(f"[S3] Download de {s3_uri} concluído.")
        return local_path
    except Exception as e:
        print(f"[S3] Falha ao baixar {s3_uri}: {e}")
        return None

def read_csv_robust(path: str) -> pd.DataFrame:
    for enc in ["utf-8", "utf-8-sig", "latin1", "iso-8859-1"]:
        try:
            with open(path, "r", encoding=enc, errors="ignore") as f:
                sample = f.read(4096)
                delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            df = pd.read_csv(path, sep=delim, encoding=enc, dtype=str, na_values=["", "NA", "N/A", "null", "NULL", "None"])
            df.columns = df.columns.str.strip()
            print(f"✓ CSV lido: {os.path.basename(path)} | enc={enc} sep='{delim}'")
            return df
        except Exception:
            continue
    return pd.read_csv(path, sep=None, engine="python", encoding="utf-8", on_bad_lines="skip", dtype=str)



def _s3_read_text(bucket: str, key: str) -> Optional[str]:
    # MODO LOCAL: Tenta ler do diretório local primeiro
    if LOCAL_MODE:
        # key geralmente é algo como "integrador-inputs/employee-survey-demo-questionnaires.csv"
        # vamos tentar tanto o caminho completo quanto apenas o nome do arquivo
        filename = key.split("/")[-1]  # pega só o nome do arquivo
        local_candidates = [
            os.path.join(LOCAL_DATA_DIR, filename),
            filename,  # raiz do projeto
        ]
        for local_path in local_candidates:
            if os.path.exists(local_path):
                try:
                    with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    print(f"[LOCAL] Lido {local_path}. Tamanho: {len(content)} bytes.")
                    return content
                except Exception as e:
                    print(f"[LOCAL] Erro ao ler {local_path}: {e}")
        print(f"[LOCAL] Arquivo não encontrado localmente: {key}")
        return None

    # MODO S3: Lê do S3
    try:
        s3 = boto3.client("s3", region_name=AWS_REGION)
        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read().decode("utf-8", errors="ignore")
        print(f"[DEBUG] SUCESSO ao ler s3://{bucket}/{key}. Tamanho: {len(content)} bytes.")
        return content
    except Exception as e:
        print(f"[S3] not found: s3://{bucket}/{key} ({e})")
        return None

# ==============================
# SEÇÃO: Metadados de Questionários (REFATORADO)
# ==============================


# Cache unificado para metadados de questionários
QUESTION_META_CACHE = {}

def load_questionnaire_meta(env_resolved: str, key: str) -> dict:
    """Carrega tipos/opções/títulos do questionário.
       Prioridade: JSON > CSV. Busca no bucket do ambiente e, se faltar, no bucket base (ai2c-genai)."""
    cache_key = (env_resolved, key)
    if cache_key in QUESTION_META_CACHE:
        return QUESTION_META_CACHE[cache_key]

    env_bucket  = resolve_bucket(env_resolved)        # ex.: ai2c-genai-dev
    base_bucket = S3_BUCKET_BASE                      # ex.: ai2c-genai
    paths = [
        f"{S3_INPUTS_PREFIX}/{key}-questionnaires.json",
        f"{S3_INPUTS_PREFIX}/{key}-questionnaires.csv",
    ]

    def _from_parsed_dict(parsed: dict) -> dict:
        raw_qtypes  = parsed.get("qtypes", {}) or {}
        qtypes_norm = {}
        for qid, qt in raw_qtypes.items():
            qt_n = _norm_qtype(qt)
            if qt_n == "text":        qt_n = "open-ended"
            if qt_n == "categorical": qt_n = "single-choice"
            if qt_n == "multiple":    qt_n = "multiple-choice"
            qtypes_norm[str(qid)] = qt_n

        qopts   = parsed.get("qopts", {}) or {}
        qtitles = parsed.get("qtitles", {}) or {}
        return {
            "qtype_map":    qtypes_norm,
            "options_map":  {str(k): list(v) for k, v in qopts.items()},
            "title_map":    {str(k): str(v) for k, v in qtitles.items()},
            "open_questions": {str(k) for k, v in qtypes_norm.items() if v == "open-ended"},
        }

    # 1) TENTA JSON nos dois buckets (env depois base). Se achar, retorna imediatamente.
    for bucket in (env_bucket, base_bucket):
        skey = paths[0]  # JSON
        txt = _s3_read_text(bucket, skey)
        if txt:
            try:
                parsed = _parse_questionnaires_json(txt)
                meta = _from_parsed_dict(parsed)
                QUESTION_META_CACHE[cache_key] = meta
                print(f"[META] OK JSON em s3://{bucket}/{skey} ⇒ tipos: {meta.get('qtype_map')}")
                return meta
            except Exception as e:
                print("[questionnaire meta] parse JSON error:", skey, e)

    # 2) Se JSON não existir, TENTA CSV nos dois buckets.
    for bucket in (env_bucket, base_bucket):
        skey = paths[1]  # CSV
        txt = _s3_read_text(bucket, skey)
        if txt:
            try:
                parsed = _parse_questionnaires_csv(txt)
                meta = _from_parsed_dict(parsed)
                QUESTION_META_CACHE[cache_key] = meta
                print(f"[META] OK CSV em s3://{bucket}/{skey} ⇒ tipos: {meta.get('qtype_map')}")
                return meta
            except Exception as e:
                print("[questionnaire meta] parse CSV error:", skey, e)

    # 3) Fallback vazio (vai cair na heurística só se for necessário)
    empty = {"qtype_map": {}, "options_map": {}, "title_map": {}, "open_questions": set()}
    QUESTION_META_CACHE[cache_key] = empty
    print("[META] Não encontrado JSON/CSV de questionário; usando heurística como fallback.")
    return empty



def _csv_options_looks_broken(parsed: dict) -> bool:
    """Detecta CSV exportado com answer_options='[object Object]'."""
    qopts = (parsed or {}).get("qopts", {}) or {}
    for opts in qopts.values():
        for o in opts:
            if str(o).strip() == "[object Object]":
                return True
    return False

def _parse_questionnaires_json(text: str) -> dict:
    import json as _json
    data = _json.loads(text)

    def _normtype(t: str, max_sel, choices) -> str:
        t = (t or "").strip().lower()
        # regras alinhadas com o jq:
        if t in {"text", "comment", "open-ended"}:
            return "open-ended"
        if t in {"radiogroup", "dropdown"}:
            return "single-choice"
        if t in {"checkbox"}:
            try:
                m = int(max_sel) if max_sel is not None else 99
            except Exception:
                m = 99
            return "single-choice" if m == 1 else "multiple-choice"
        if t in {"rating", "number", "numeric"}:
            return "numeric"
        # fallback: se tem choices, assume single-choice; senão open-ended
        if (choices or []):
            return "single-choice"
        return "open-ended"

    qtypes, qopts, qtitles = {}, {}, {}
    try:
        pages = (data.get("content") or {}).get("pages") or []
        for p in pages:
            for el in p.get("elements", []) or []:
                qid = str(el.get("name", "")).strip()
                if not qid:
                    continue
                raw_type = el.get("type")
                max_sel  = el.get("maxSelectedChoices")
                choices  = el.get("choices") or []
                # mapeia títulos/opções
                qtitles[qid] = (el.get("title") or qid)
                labels = []
                for ch in choices:
                    if isinstance(ch, dict):
                        labels.append(str(ch.get("text") or ch.get("value") or "").strip())
                    else:
                        labels.append(str(ch).strip())
                labels = [x for x in labels if x]
                if labels:
                    qopts[qid] = labels
                # tipo normalizado
                qtypes[qid] = _normtype(raw_type, max_sel, choices)
    except Exception as e:
        print("[parse questionnaires json] error:", e)

    return {"qtypes": qtypes, "qopts": qopts, "qtitles": qtitles}


def _parse_questionnaires_csv(text: str) -> dict:
    """
    Parser para formato CSV do questionário.
    Fallback quando JSON não está disponível.
    """
    from io import StringIO
    
    qtype_map = {}
    options_map = {}
    title_map = {}
    open_questions = set()
    scale_questions = set()
    
    try:
        # CSV com ; e SEM converter "" em NaN
        dfq = pd.read_csv(StringIO(text), sep=";", dtype=str, keep_default_na=False, encoding="utf-8")
        
        # Normaliza colunas básicas
        for col in ["topic", "questionnaire_id", "survey_id", "question_id",
                    "question_description", "question_type", "answer_options", "marked"]:
            if col not in dfq.columns:
                dfq[col] = ""
            dfq[col] = dfq[col].map(_norm_txt)

        for _, r in dfq.iterrows():
            qid = _norm_txt(r.get("question_id", ""))
            if not qid:
                continue
            
            qdesc = _norm_txt(r.get("question_description", ""))
            qtype_raw = _norm_qtype(r.get("question_type", ""))
            opts_raw = _norm_txt(r.get("answer_options", ""))

            # Fallback: se não veio tipo, infere por presença de opções
            if not qtype_raw:
                qtype_raw = "multiple-choice" if bool(opts_raw) else "open-ended"

            # Mapeia para tipos de visualização padronizados
            if qtype_raw in {"open-ended", "comment", "text"}:
                viz_type = "open-ended"
                open_questions.add(qid)
            elif qtype_raw in {"multiple-choice", "checkbox", "multi"}:
                viz_type = "multiple-choice"
            elif qtype_raw in {"single-choice", "radiogroup", "dropdown", "categorical"}:
                viz_type = "single-choice"
            elif qtype_raw in {"rating", "numeric", "number"}:
                viz_type = "rating-scale"
                scale_questions.add(qid)
            else:
                viz_type = qtype_raw  # mantém o original se não reconhecido

            # Detecta escalas de satisfação pelo título
            title_lower = qdesc.lower()
            if any(word in title_lower for word in ["satisfeito", "satisfação", "avalia", "escala"]):
                viz_type = "rating-scale"
                scale_questions.add(qid)
            
            qtype_map[qid] = viz_type
            title_map[qid] = qdesc

            # Parse das opções (se existirem)
            if opts_raw:
                opts_list = [o.strip() for o in re.split(r"[|;,/]", opts_raw) if o.strip()]
                # Remove "[object Object]" inválidos
                opts_list = [o for o in opts_list if "object" not in o.lower()]
                if opts_list:
                    options_map[qid] = opts_list

    except Exception as e:
        print(f"[_parse_questionnaires_csv] Erro: {e}")
        import traceback
        traceback.print_exc()
    
    return {
        "qtype_map": qtype_map,
        "options_map": options_map,
        "title_map": title_map,
        "open_questions": open_questions,
        "scale_questions": scale_questions
    }


# Função auxiliar para obter tipo de visualização
def get_visualization_type(question_id: str, meta: dict) -> str:
    """
    Retorna o tipo de visualização apropriado para uma pergunta.
    
    Tipos possíveis:
    - "open-ended": wordcloud, análise de sentimentos
    - "rating-scale": gráfico de barras horizontal (escala de satisfação)
    - "single-choice": gráfico de pizza ou barras
    - "multiple-choice": gráfico de barras (múltiplas seleções)
    - "yes-no": gráfico de pizza simples
    - "numeric": histograma
    """
    return meta.get("qtype_map", {}).get(question_id, "open-ended")


def qtype_for(env_resolved: str, key: str, qid: str, df: Optional[pd.DataFrame] = None) -> str:
    """
    Prioriza metadado do questionário; cai para analyze_qtype(df) se necessário.
    
    COMPATIBILIDADE: Mantém a interface original mas usa o novo load_questionnaire_meta.
    """
    meta = load_questionnaire_meta(env_resolved, key)
    qt = (meta.get("qtype_map") or {}).get(str(qid), "").lower()
    
    if qt:
        # Já vem normalizado
        return qt
    
    if df is None or df.empty:
        return "unknown"
    
    # Fallback: analisa heuristicamente
    guessed = analyze_qtype(df["answer"]) if "answer" in df.columns else "unknown"
    
    # Converte heurística para os nomes usados na UI
    mapper = {
        "numeric": "numeric",
        "categorical": "single-choice",
        "multiple": "multiple-choice",
        "text": "open-ended",
        "open-ended": "open-ended"
    }
    return mapper.get(guessed, guessed)

def get_qtype_for_question_with_meta(env_resolved: str, qid: str, series: pd.Series, key: str) -> str:
    meta = load_questionnaire_meta(env_resolved, key)
    qt = (meta.get("qtype_map", {}) or {}).get(str(qid))
    if qt:
        return qt
    # fallback só se não houver meta
    guessed = analyze_qtype(series)
    mapper = {"numeric":"numeric","categorical":"single-choice","multiple":"multiple-choice","text":"open-ended","open-ended":"open-ended"}
    return mapper.get(guessed, "open-ended")



def build_state(df: pd.DataFrame, env_resolved: Optional[str] = None, key: Optional[str] = None) -> Dict:
    """Cria um dicionário de estado a partir de um DataFrame + metadados do questionário."""
    if df.empty:
        return {
            "stats": {},
            "questions_df": pd.DataFrame(),
            "QDESC_MAP": {},
            "ALLOWED_SEGMENT_COLS": [],
            "QTYPE_MAP": {},
            "QOPTIONS_MAP": {}
        }

    def _allowed_segment_cols(d: pd.DataFrame) -> list[str]:
        cols = []
        for c in d.columns:
            if c in NON_SEGMENTABLE or is_pii(c) or high_cardinality(d, c):
                continue
            cols.append(c)
        return sorted(cols)

    stats = {
        "total_responses": len(df),
        "unique_respondents": df["respondent_id"].nunique() if "respondent_id" in df.columns else 0,
        "unique_questions": df["question_id"].nunique() if "question_id" in df.columns else 0,
        "start": df["date_of_response"].min() if "date_of_response" in df.columns else None,
        "end": df["date_of_response"].max() if "date_of_response" in df.columns else None,
    }

    qdf = df[["question_id", "question_description"]].drop_duplicates()
    qdf["__ord"] = qdf["question_id"].apply(numeric_suffix)
    qdf = qdf.sort_values(["__ord", "question_id"]).drop(columns="__ord")

    qdesc_map = {
        str(r["question_id"]): (r["question_description"] or str(r["question_id"]))
        for _, r in qdf.iterrows()
    }

    qtype_map, qopts_map = {}, {}
    
    if env_resolved and key:
        meta = load_questionnaire_meta(env_resolved, key)
        qtype_map = (meta.get("qtype_map") or {}).copy()
        qopts_map = (meta.get("options_map") or {}).copy()
        
        # Enriquece qdesc_map com títulos do questionário
        for qid, title in (meta.get("title_map") or {}).items():
            if title and qid in qdesc_map:
                # Usa título do questionário se a descrição estiver vazia
                if not qdesc_map[qid].strip():
                    qdesc_map[qid] = title

    return {
        "stats": stats,
        "questions_df": qdf,
        "QDESC_MAP": qdesc_map,
        "ALLOWED_SEGMENT_COLS": _allowed_segment_cols(df),
        "QTYPE_MAP": qtype_map,
        "QOPTIONS_MAP": qopts_map,
    }


def fix_mojibake(s: str) -> str:
    if not isinstance(s, str): return s
    rep = {"√£":"ã","√≥":"ó","√°":"á","√©":"é","√™":"ê","√∫":"ú","√º":"ú","√ß":"ç",
           "ƒÂ£":"ã","ƒÂ¡":"á","ƒÂ©":"é","ƒÂª":"ê","ƒÂº":"ú","ƒÂ³":"ó","ƒÂ§":"ç","ƒÃ±":"ñ",
           "N√£o":"Não","n√£o":"não"}
    for k,v in rep.items(): s = s.replace(k,v)
    return s

def coerce_sentiment_series(s: pd.Series) -> pd.Series:
    if s is None or s.empty:
        return pd.Series(dtype=str)
    s_base = s.astype(str).str.strip().str.lower()
    return s_base.map(SENTIMENT_MAP).fillna(s_base)

def intention_bar_fig(sub_df: pd.DataFrame, top_n: int = 20) -> Optional[go.Figure]:
    if sub_df.empty:
        return None
    intent_col = None
    for name in ["intention","intent","intencao"]:
        if name in sub_df.columns:
            intent_col = name
            break
    if not intent_col:
        return None

    s = _clean_series_for_counts(sub_df[intent_col])
    if s.empty:
        return None

    vc = s.value_counts().head(top_n)
    df_bar = pd.DataFrame({"Intenção": vc.index, "Qtde": vc.values})
    fig = px.bar(df_bar, x="Intenção", y="Qtde", title="Intenções – Top respostas")
    fig.update_traces(text=df_bar["Qtde"], textposition="outside", cliponaxis=False)
    fig = create_fig_style(fig, x="Intenção", y="Qtde")
    fig.update_xaxes(showgrid=False, showticklabels=True)
    fig.update_yaxes(showgrid=False, showticklabels=True)
    return responsive_axis(fig, labels=df_bar["Intenção"].tolist())


def load_df_for_key(env_resolved: str, key: str) -> pd.DataFrame:
    """Carrega DF do CUBE para (env, key) com cache em memória e download do S3 se necessário."""
    k = (env_resolved, key)
    if k in DF_CACHE:
        return DF_CACHE[k]

    local_path = _s3_download_to_tmp(env_resolved, key)
    if not local_path or not os.path.exists(local_path):
        fallback_path = f"{key}_analytics_cube.csv"
        print(f"Download do S3 falhou. Tentando fallback local: {fallback_path}")
        if os.path.exists(fallback_path):
            local_path = fallback_path
        else:
            raise FileNotFoundError(f"Cubo de dados não encontrado para key='{key}' no ambiente='{env_resolved}'")

    df = read_csv_robust(local_path)
    
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes no CUBE: {missing}")

    for col, default in OPTIONAL_COL_DEFAULTS.items():
        if col not in df.columns:
            df[col] = default

    for c in REQUIRED_COLS:
        df[c] = df[c].astype(str).map(lambda x: x.strip() if isinstance(x, str) else x).replace({"nan": None, "None": None})

    for c in ["question_description","category","topic","sentiment","intention"]:
        if c in df.columns:
            df[c] = df[c].astype(str).map(fix_mojibake)

    if "sentiment" in df.columns:
        df["sentiment"] = df["sentiment"].map(normalize_sentiment)

    if "date_of_response" in df.columns:
        df["date_of_response"] = pd.to_datetime(df["date_of_response"], errors="coerce")

    if "confidence_level" in df.columns:
        df["confidence_level"] = pd.to_numeric(df["confidence_level"], errors="coerce")

    df["answer"] = df["orig_answer"].astype(str).map(fix_mojibake)

    DF_CACHE[k] = df
    return df

# ==============================
# 5) Funções de Análise e Helpers
# ==============================
def is_pii(col: str) -> bool:
    c = (col or "").lower()
    if c == "respondent_id": return False
    patterns = [
        r"\bcpf\b", r"\bcnpj\b", r"\brg\b", r"\bdoc", r"document", r"\bpassport\b", r"e[-_ ]?mail",
        r"\bemail\b", r"\btelefone\b", r"\bphone\b", r"\bcelular\b", r"\bwhatsapp\b", r"\bendere",
        r"\baddress\b", r"\bcep\b", r"\bzipcode\b", r"\bnome\b", r"\bname\b", r"\bid\b", r"\bip\b",
        r"lat", r"lon", r"longitude", r"latitude", r"device", r"imei"
    ]
    return any(re.search(p, c) for p in patterns)

def intents_by_question(df_cube, qid: str):
    sub = df_cube[df_cube['question_id'] == qid]
    if 'intent' not in sub.columns:
        for alt in ('intencao', 'topic', 'classe_intencao'):
            if alt in sub.columns:
                sub = sub.rename(columns={alt: 'intent'})
                break
    if 'intent' not in sub.columns:
        return pd.DataFrame(columns=['intent','count','pct'])

    ct = (sub.assign(intent=sub['intent'].fillna('Sem classificação'))
             .groupby('intent', dropna=False)
             .size()
             .reset_index(name='count')
             .sort_values('count', ascending=False))
    total = ct['count'].sum() or 1
    ct['pct'] = (ct['count'] / total * 100).round(1)
    return ct

def make_minimal(fig: go.Figure) -> go.Figure:
    fig.update_xaxes(showgrid=False, zeroline=False, showline=False, showticklabels=False)
    fig.update_yaxes(showgrid=False, zeroline=False, showline=False, showticklabels=False)
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    return fig

def high_cardinality(df: pd.DataFrame, col: str, max_ratio: float = 0.2, min_unique: int = 50) -> bool:
    try:
        n = len(df)
        u = df[col].astype(str).nunique(dropna=True)
        return (u >= min_unique) and (u / max(1, n) > max_ratio)
    except Exception:
        return True

def numeric_suffix(s: str):
    m = re.search(r"(\d+)$", str(s))
    return int(m.group(1)) if m else float("inf")


def analyze_qtype(series: pd.Series) -> str:
    """Versão aprimorada que considera a cardinalidade para evitar falsos positivos de 'multiple'."""
    s = series.dropna().astype(str)
    if s.empty:
        return "empty"

    num_unique = s.nunique()
    total_count = len(s)

    # Heurística 1: Se for numérico, é numérico.
    if pd.to_numeric(s, errors="coerce").notna().mean() > 0.8:
        return "numeric"

    # Heurística 2: Se tiver alta cardinalidade, é texto livre.
    # (Ex: mais de 60% das respostas são únicas)
    if total_count > 10 and (num_unique / total_count > 0.6):
        return "text"

    # Heurística 3: Verifica separadores, mas apenas se a cardinalidade não for muito alta.
    has_sep = s.str.contains(r"[;,/|]").mean() > 0.02
    if has_sep and num_unique < (total_count * 0.5): # Só considera 'multiple' se não for quase tudo único
        return "multiple"

    # Heurística 4: Baixa cardinalidade sugere categórico.
    if num_unique <= 25:
        return "categorical"

    # Fallback final: é texto livre.
    return "text"


def parse_multi(ans: str) -> List[str]:
    if not isinstance(ans, str) or not ans.strip():
        return []
    cleaned = re.sub(r"[,/|]", ";", ans)
    return [t.strip() for t in cleaned.split(";") if t.strip()]

def explode_multiple(sub: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in sub.iterrows():
        items = parse_multi(row.get("answer", ""))
        for it in items:
            r = row.copy()
            r["answer_item"] = it
            rows.append(r)
    return pd.DataFrame(rows).reset_index(drop=True) if rows else pd.DataFrame(columns=list(sub.columns) + ["answer_item"])

def _clean_series_for_counts(s: pd.Series) -> pd.Series:
    # mantém o comprimento; apenas normaliza e marca inválidos como NaN
    s = s.astype(str)
    s = s.str.strip()
    s = s.mask(s.eq(""), np.nan)
    s = s.mask(s.str.lower().isin({"nan","none","null"}), np.nan)
    return s


def make_pv_answer(df_q: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    out = df_q.copy()
    if out.empty or "answer" not in out.columns:
        out["__pv_answer__"] = pd.Series(dtype=str)
        return out
    qtype = analyze_qtype(out["answer"])
    if qtype == "multiple":
        out["__pv_answer__"] = out["answer"].astype(str).str.split(r"[,;/|]")
        out = out.explode("__pv_answer__")
        out["__pv_answer__"] = _clean_series_for_counts(out["__pv_answer__"])
        out = out.dropna(subset=["__pv_answer__"])
    elif qtype == "numeric":
        vals = pd.to_numeric(out["answer"], errors="coerce")
        out["__pv_answer__"] = pd.cut(vals, bins=bins, labels=[f"Faixa {i+1}" for i in range(bins)])
        out = out.dropna(subset=["__pv_answer__"])
    else:
        out["__pv_answer__"] = _clean_series_for_counts(out["answer"])
        out = out.dropna(subset=["__pv_answer__"])
    return out

def build_topics_wordcloud_component(d: pd.DataFrame, width: int = 900, height: int = 520):
    if not HAS_WORDCLOUD: return html.Div("Para a nuvem, instale: pip install wordcloud pillow")
    if d.empty or "topic" not in d.columns: return html.Div("Sem tópicos na seleção atual.")
    s = d["topic"].dropna().astype(str).str.strip()
    s = s[s.ne("") & ~s.str.lower().isin({"nan","none","null"})]
    if s.empty: return html.Div("Sem tópicos válidos para gerar a nuvem.")
    freq = s.value_counts()
    if freq.empty: return html.Div("Sem tópicos válidos para gerar a nuvem.")
    wc = WordCloud(width=width, height=height, background_color="white", colormap="tab20c", prefer_horizontal=0.95, random_state=42, collocations=False, normalize_plurals=True, max_words=200, min_font_size=10, stopwords=STOPWORDS).generate_from_frequencies(freq.to_dict())
    buf = io.BytesIO(); wc.to_image().save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return html.Img(src=f"data:image/png;base64,{b64}", style={"width":"100%","height":"auto"})

def responsive_axis(fig: go.Figure, labels=None, axis: str = "x"):
    n = len(labels) if labels is not None else 0
    maxlen = max((len(str(s)) for s in labels), default=0) if n > 0 else 0
    if n >= 12 or maxlen > 16: angle, size = -45, 10
    elif n >= 7 or maxlen > 12: angle, size = -25, 11
    else: angle, size = 0, 12
    if axis == "x": fig.update_xaxes(tickangle=angle, automargin=True, tickfont=dict(size=size))
    else: fig.update_yaxes(automargin=True, tickfont=dict(size=size))
    return fig

def create_fig_style(fig, title="", x="", y="", tickangle=None, showlegend=True):
    fig.update_layout(title=title, xaxis_title=x, yaxis_title=y, showlegend=showlegend, hovermode="x unified")
    if tickangle is not None: fig.update_xaxes(tickangle=tickangle)
    fig.update_xaxes(automargin=True); fig.update_yaxes(automargin=True)
    return fig

def empty_state(msg: str):
    return html.Div([html.Div("ⓘ", style={"fontSize":"18px"}), html.Span(msg)], className="muted-box")

def _extract_click_label(clickData):
    if not clickData or not clickData.get("points"): return None
    p = clickData["points"][0]
    return p.get("label", p.get("x"))

def _apply_qfilter(sub: pd.DataFrame, qfilter: Dict[str, Optional[str]]) -> pd.DataFrame:
    qfilter = qfilter or {}
    if qfilter.get("category"): sub = sub[sub["category"].astype(str) == str(qfilter["category"])]
    if qfilter.get("topic"): sub = sub[sub["topic"].astype(str) == str(qfilter["topic"])]
    return sub

def sentiment_timeline(df: pd.DataFrame, granularity: str) -> Optional[go.Figure]:
    if df.empty or "sentiment" not in df.columns or "date_of_response" not in df.columns:
        return None
    d = df.dropna(subset=["date_of_response", "sentiment"]).copy()
    if d.empty: return None
    gran = (granularity or "W")
    d["period"] = pd.to_datetime(d["date_of_response"]).dt.to_period(gran)
    trend = d.groupby(["period","sentiment"]).size().reset_index(name="count")
    if trend.empty: return None
    trend = trend.sort_values(["period","sentiment"])
    trend["period_str"] = trend["period"].astype(str)
    period_order = trend["period_str"].drop_duplicates().tolist()
    fig = px.bar(
        trend, x="period_str", y="count", color="sentiment",
        barmode="group",
        category_orders={"period_str": period_order, "sentiment": SENTIMENT_ORDER},
        color_discrete_map=SENTIMENT_COLORS,
        title=f"Tendência de Sentimento ({ {'D':'Diário','W':'Semanal','M':'Mensal'}.get(gran, gran) })"
    )
    return create_fig_style(fig, x="Período", y="Qtde", tickangle=-30, showlegend=True)

def sentiment_percentages(df: pd.DataFrame) -> dict:
    """
    Retorna dicionário com total e percentuais de cada sentimento.
    Inclui automaticamente todos os sentimentos encontrados no DataFrame.
    """
    if df.empty or "sentiment" not in df.columns:
        return {
            "total": 0,
            "positivo": 0.0,
            "negativo": 0.0,
            "neutro": 0.0,
            "não aplicável": 0.0
        }
    
    # Normaliza os sentimentos usando a função existente
    s = coerce_sentiment_series(df["sentiment"])
    total = int(len(s))
    
    if total == 0:
        return {
            "total": 0,
            "positivo": 0.0,
            "negativo": 0.0,
            "neutro": 0.0,
            "não aplicável": 0.0
        }
    
    # Conta cada sentimento
    sentiment_counts = s.value_counts().to_dict()
    
    # Calcula percentuais
    result = {"total": total}
    
    # Lista de sentimentos esperados (pode adicionar mais se necessário)
    expected_sentiments = ["positivo", "negativo", "neutro", "não aplicável"]
    
    for sentiment in expected_sentiments:
        count = sentiment_counts.get(sentiment, 0)
        percentage = round(100.0 * count / total, 1)
        result[sentiment] = percentage
    
    # Adiciona qualquer outro sentimento não esperado que apareça nos dados
    for sentiment, count in sentiment_counts.items():
        if sentiment not in expected_sentiments:
            percentage = round(100.0 * count / total, 1)
            result[sentiment] = percentage
    
    # Verifica se a soma está próxima de 100% (pode haver pequenas diferenças por arredondamento)
    total_percentage = sum(v for k, v in result.items() if k != "total")
    
    return result


# Versão alternativa mantendo a assinatura original (tuple) mas com 4 valores:
def sentiment_percentages_tuple(df: pd.DataFrame) -> tuple[int, float, float, float, float]:
    """
    Retorna (total, %pos, %neg, %neu, %nao_aplicavel).
    """
    if df.empty or "sentiment" not in df.columns:
        return 0, 0.0, 0.0, 0.0, 0.0
    
    s = coerce_sentiment_series(df["sentiment"])
    total = int(len(s))
    
    if total == 0:
        return 0, 0.0, 0.0, 0.0, 0.0
    
    pos = int((s == "positivo").sum())
    neg = int((s == "negativo").sum())
    neu = int((s == "neutro").sum())
    nao_aplic = int((s == "não aplicável").sum())
    
    f = lambda x: round(100.0 * x / max(1, total), 1)
    
    return total, f(pos), f(neg), f(neu), f(nao_aplic)

def render_sentiment_cards(df: pd.DataFrame):
    # Agora usando a versão com 5 valores que inclui não aplicável
    total, ppos, pneg, pneu, pna = sentiment_percentages_tuple(df)
    if total == 0:
        return html.Div(className="muted-box", children="Sem dados de sentimento nesta seleção.")

    def _kpi_card(title, value, color):
        return dbc.Card(
            dbc.CardBody([
                html.Div(title, className="text-muted", style={"fontSize":"0.85rem"}),
                html.H3(f"{value:.1f}%", className="mb-0", style={"fontWeight":700}),
            ]),
            className="dash-card",
            style={"borderLeft": f"4px solid {color}"}
        )

    # Badges para neutro e N/A lado a lado
    neutro_badge = dbc.Badge(f"Neutro: {pneu:.1f}%", color="secondary", className="ms-2")
    na_badge = dbc.Badge(f"N/A: {pna:.1f}%", color="secondary", className="ms-2")

    return dbc.Row([
        dbc.Col(_kpi_card("👍 Positivo", ppos, "#10B981"), md=6),
        dbc.Col(_kpi_card("👎 Negativo", pneg, "#EF4444"), md=6),
        html.Div([neutro_badge, na_badge], className="mt-2")
    ], className="mb-3")

def topics_bar_fig(sub_df: pd.DataFrame) -> go.Figure:
    if sub_df.empty or "topic" not in sub_df.columns:
        return go.Figure()
    s = _clean_series_for_counts(sub_df["topic"])
    if s.empty:
        return go.Figure()
    vc = s.value_counts()
    total = int(vc.sum())
    df = pd.DataFrame({"topic": vc.index, "Qtde": vc.values})
    df["%"] = (df["Qtde"] / max(1, total) * 100).round(1)
    fig = px.bar(df.head(50), x="topic", y="Qtde", text="%", title="Tópicos – Distribuição")
    fig.update_traces(texttemplate="%{text:.1f}%")
    return create_fig_style(fig, x="Tópico", y="Qtde", tickangle=-25)

def answers_top_tokens_fig(sub_df: pd.DataFrame, top_n: int = 20) -> Optional[go.Figure]:
    if sub_df.empty or "answer" not in sub_df.columns: return None
    s = sub_df["answer"].dropna().astype(str).str.lower()
    if s.empty: return None
    tokens, rx = [], re.compile(r"\b[^\W\d_]{3,}\b", flags=re.UNICODE)
    for text in s: tokens.extend(rx.findall(text))
    stop = {
        "que","com","para","uma","numa","não","sim","de","da","do","das","dos","em","no","na","os","as","o","a","e",
        "é","se","por","um","uns","uma","umas","ao","à","às","aos","foi","ser","esta","este","esse","isso","isto",
        "tá","está","pra","pro","mais","menos","muito","pouco","the","and","for","with","you","not","are","your",
        "this","that","was","have","has","had","from","into","about","out","her","his","their","our"
    }
    tokens = [t for t in tokens if t not in stop]
    if not tokens: return None
    vc = pd.Series(tokens).value_counts().head(top_n)
    fig = px.bar(x=vc.index, y=vc.values, title="Palavras mais frequentes (campo aberto)")
    return create_fig_style(fig, x="Palavra", y="Ocorrências", tickangle=-25)

# ==============================
# 6) Criação do App Dash + CSS
# ==============================
BASE_PATH = os.getenv("BASE_PATH", "/dataviz-svc/")
if not BASE_PATH.startswith("/"):
    BASE_PATH = "/" + BASE_PATH
if not BASE_PATH.endswith("/"):
    BASE_PATH = BASE_PATH + "/"

ASSETS_URL_PATH = BASE_PATH.rstrip("/") + "/assets"

print(f"[BOOT] BASE_PATH={BASE_PATH} | ASSETS_URL_PATH={ASSETS_URL_PATH}")

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
server = Flask(__name__)

server.wsgi_app = ProxyFix(
    server.wsgi_app,
    x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
)

app = dash.Dash(
    __name__,
    server=server,
    url_base_pathname=BASE_PATH,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    assets_url_path=ASSETS_URL_PATH,
    serve_locally=True,
)

# OPCIONAL: Habilite para debug (desabilite em produção)
#app.enable_dev_tools(
#    debug=True,
#    dev_tools_props_check=True,
#    dev_tools_silence_routes_logging=False,
#)

app.index_string = """
<!DOCTYPE html>
<html>
  <head>
    {%metas%}
    <title>Analytics Dashboard</title>
    {%favicon%}
    {%css%}
<style>
  @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap');
  :root{
    --brand:#FF9800;
    --ink:#111111;
    --muted:#6c757d;
    --page-bg:#F7F7F7;
    --card-bg:#FFFFFF;
    --line:#ECECEC;
    --success:#16A34A;
    --danger:#EF4444;
  }
  *{box-sizing:border-box}
  body{
    background:var(--page-bg);
    color:var(--ink);
    font-family:'Poppins',system-ui,-apple-system,Segoe UI,Roboto,'Helvetica Neue',Arial,sans-serif;
  }
  .navbar { border-bottom:1px solid var(--line); background:var(--card-bg); }
  .nav-tabs .nav-link{
    border-radius:12px 12px 0 0;
    font-weight:600; color:var(--muted);
    border:none; padding:12px 24px;
  }
  .nav-tabs .nav-link.active{
    background:var(--card-bg); color:var(--ink);
    border-bottom:3px solid var(--brand) !important;
  }
  .nav-tabs .nav-link:hover{ color:var(--ink) }
  .dash-card{
    background:var(--card-bg);
    border-radius:16px;
    border:1px solid var(--line);
    box-shadow:0 2px 10px rgba(0,0,0,.05);
    transition: box-shadow .2s ease, transform .05s ease;
  }
  .dash-card:hover{ box-shadow:0 4px 16px rgba(0,0,0,.08) }
  .ctrl-grid{
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:16px; margin-bottom:12px;
  }
  @media (max-width: 992px){ .ctrl-grid{grid-template-columns:1fr} }
  label{ font-size:.9rem; margin-bottom:6px; color:#374151; }
  .btn{
    border-radius:999px; font-weight:600;
    border:1.5px solid var(--brand);
    background:#fff; color:var(--ink);
  }
  .btn:hover{ box-shadow:0 4px 12px rgba(0,0,0,.08) }
  .btn:active{ transform:translateY(1px) }
  .btn-primary{
    background:var(--brand); border-color:var(--brand); color:var(--ink);
  }
  .badge{ border-radius:999px; }
  .text-muted{ color:var(--muted)!important; }
  .muted-box{
    display:flex; align-items:center; gap:6px;
    padding:16px; border:1px dashed var(--line);
    border-radius:12px; color:var(--muted);
    background:#FAFAFA;
  }
</style>
  </head>
  <body>
    {%app_entry%}
    <footer>
      {%config%}
      {%scripts%}
      {%renderer%}
    </footer>
  </body>
</html>
"""

server = app.server

health_path = (BASE_PATH.rstrip("/") + "/health") if BASE_PATH != "/" else "/health"

@server.route("/health")
def health_root():
    return {"status": "ok", "service": "dataviz-svc"}, 200

@server.route(health_path)
def health_base():
    return {"status": "ok", "service": "dataviz-svc"}, 200

# Navbar
header = dbc.Navbar()

# Tabs
tabs = dbc.Tabs(
    [
        dbc.Tab(label="Análise por Pergunta", tab_id="questions"),
        dbc.Tab(label="Análises personalizadas", tab_id="pivot"),
        dbc.Tab(label="Dados Brutos", tab_id="raw"),
    ], id="main-tabs", active_tab="questions"
)

# Modal de drill (Pivot)
modal_drill = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle(id="pv-drill-title")),
    dbc.ModalBody(id="pv-drill-content"),
], id="pv-drill-modal", size="xl", is_open=False)

app.layout = dbc.Container([
    header,
    dcc.Location(id="url", refresh=False),
    dcc.Store(id="current-env"),
    dcc.Store(id="current-key"),
    tabs,
    html.Div(id="tab-content", className="mt-3"),
], fluid=True)

# ==============================
# 7) UI: Card por Pergunta
# ==============================
def question_card(qid: str, qdesc: str, allowed_cols: List[str], df: pd.DataFrame,
                  env_resolved: str, key: str) -> dbc.Col:
    try:
        series = df.loc[df["question_id"].astype(str) == str(qid), "answer"]
        qtype_meta = get_qtype_for_question_with_meta(env_resolved, qid, series, key)
    except Exception:
        qtype_meta = None

    type_badge = {
        "numeric":         ("🔢", "primary",  "Numérica"),
        "single-choice":   ("🗳️", "success",  "Categórica"),
        "multiple-choice": ("☑️", "info",     "Múltipla escolha"),
        "open-ended":      ("💬", "warning",  "Campo aberto"),
    }.get(qtype_meta, ("❓", "secondary", "Desconhecido"))

    seg_opts = [{"label": c, "value": c} for c in (allowed_cols or [])]

    controls = html.Div([
        html.Div(className="ctrl-grid", children=[
            html.Div([
                html.Label("Variáveis", className="fw-bold"),
                dcc.Dropdown(
                    id={"type": "q-segcol", "qid": qid},
                    options=seg_opts,
                    placeholder="Escolha coluna...",
                    clearable=True
                ),
            ]),
            html.Div([
                html.Label("Valores (opcional)", className="fw-bold"),
                dcc.Dropdown(
                    id={"type": "q-segvals", "qid": qid},
                    multi=True,
                    placeholder="Todos os valores",
                    clearable=True,
                    maxHeight=320,
                    optionHeight=32
                ),
            ]),
        ])
    ])

    return dbc.Col(
        dbc.Card([
            dbc.CardHeader([
                html.Div([
                    html.Div([
                        html.Strong(str(qid), className="me-2"),
                        dbc.Badge(type_badge[0] + " " + type_badge[2],
                                  color=type_badge[1], className="me-2"),
                        html.Div(id={"type": "q-filterpill", "qid": qid},
                                 style={"display": "inline-block"}),
                    ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
                    html.P(qdesc or "", className="text-muted mb-0 mt-2",
                           style={"fontSize": "0.9rem"}),
                ], style={"flex": "1"}),
            ]),

            dbc.CardBody([
                dcc.Store(id={"type":"q-filter","qid": qid}, data={"category": None, "topic": None}),
                dcc.Store(id={"type":"q-drill","qid": qid},  data={"level": 0, "seg_value": None, "category": None}),

                html.Div([
                    dbc.Button("🔍 Filtros", id={"type":"q-collapse-btn","qid": qid}, color="light", size="sm", className="mb-3"),
                    dbc.Collapse(controls, id={"type":"q-collapse","qid": qid}, is_open=False),
                ]),

                dbc.Button("🗑️ Limpar filtros", id={"type":"q-clear","qid": qid}, size="sm", color="secondary", outline=True,
                        className="mb-3", style={"display": "none"}),

                # ▶️ Cards de sentimento ficam aqui
                html.Div(id={"type":"q-sentcards","qid": qid}, className="mb-3"),

                # Gráfico principal, que vamos ocultar em perguntas abertas
                html.Div(id={"type":"q-fig-wrap","qid": qid},
                        children=dcc.Loading(dcc.Graph(id={"type":"q-fig","qid": qid}, config={"displayModeBar": False}), type="dot")),


                dcc.Graph(id={"type": "q-catfig", "qid": qid},
                          config={"displayModeBar": False},
                          style={"marginTop": "12px"}),

                dcc.Graph(id={"type": "q-topicsfig", "qid": qid},
                          config={"displayModeBar": False},
                          style={"marginTop": "12px"}),

                dcc.Graph(id={"type": "q-answers", "qid": qid},
                          config={"displayModeBar": False},
                          style={"marginTop": "12px", "display": "none"}),
            ])
        ], className="mb-4 dash-card"),
        md=6
    )

# ==============================
# 8) Pivot (Análises personalizadas)
# ==============================
def to_date_str(x):
    try:
        if x is None or (hasattr(pd, "isna") and pd.isna(x)):
            return None
        return pd.to_datetime(x, errors="coerce").date().isoformat()
    except Exception:
        return None
 
def pivot_controls(df: pd.DataFrame, state: Dict):
    """UI da aba Pivot – cartões do mesmo tamanho, pergunta1 e sentiment pré-selecionados."""
    if df.empty:
        return empty_state("Sem dados para montar a pivot.")

    # colunas numéricas para métricas
    numeric_cols = sorted([
        c for c in df.columns
        if c not in NON_SEGMENTABLE and not is_pii(c)
        and pd.to_numeric(df[c], errors="coerce").notna().mean() > 0.7
    ])

    # dimensões seguras
    dims_base = (state.get("ALLOWED_SEGMENT_COLS") or []) + ["sentiment", "category", "topic"]
    dims = sorted(list(set([c for c in dims_base if c not in numeric_cols])))
    dims_options = [{"label": c, "value": c} for c in dims] + [
        {"label": "Resposta (da pergunta selecionada)", "value": "__pv_answer__"}
    ]

    # perguntas e default = primeira (pergunta1)
    qdf = state.get("questions_df")
    if qdf is None or (hasattr(qdf, "empty") and qdf.empty):
        qdf = pd.DataFrame(columns=["question_id", "question_description"])

    def _label_for_row(row):
        qd = row.get("question_description")
        if pd.isna(qd) or str(qd).strip().lower() in {"", "nan", "none", "null"}:
            return str(row["question_id"])
        return str(qd)[:120]

    q_opts = [{"label": _label_for_row(r), "value": str(r["question_id"])}
              for _, r in qdf.iterrows()]
    default_qid = q_opts[0]["value"] if q_opts else None

    stats_local = state.get("stats", {})
    CARD_HEIGHT = 420  # px

    return dbc.Card([
        dbc.CardHeader(html.H5("🧭 Pivot (tabela dinâmica + gráfico)", className="mb-0")),
        dbc.CardBody([
            html.Div(className="ctrl-grid", children=[
                html.Div([
                    html.Label("Pergunta para explorar respostas (opcional)", className="fw-bold"),
                    dcc.Dropdown(id="pv-qid", options=q_opts, value=default_qid,
                                 placeholder="Selecione a pergunta…")
                ]),
                html.Div([
                    html.Label("Usar respostas como dimensão", className="fw-bold"),
                    dcc.Checklist(
                        id="pv-use-answer",
                        options=[{"label": "Adicionar 'Resposta (da pergunta)' às dimensões", "value": "on"}],
                        value=["on"], inputStyle={"marginRight": "6px"}
                    )
                ]),
                html.Div([
                    html.Label("Binning para respostas numéricas", className="fw-bold"),
                    dcc.RadioItems(
                        id="pv-answer-binning",
                        options=[{"label": "5 faixas", "value": "5"},
                                 {"label": "10 faixas", "value": "10"},
                                 {"label": "20 faixas", "value": "20"}],
                        value="10", inline=True
                    )
                ]),
            ]),
            html.Div(className="ctrl-grid", children=[
                html.Div([
                    html.Label("Linhas (index)", className="fw-bold"),
                    dcc.Dropdown(
                        id="pv-rows", options=dims_options, multi=True,
                        value=["sentiment"],  # default para não ficar vazio
                        placeholder="Escolha 1–2 dimensões…"
                    )
                ]),
                html.Div([
                    html.Label("Colunas (columns)", className="fw-bold"),
                    dcc.Dropdown(id="pv-cols", options=dims_options, multi=False, placeholder="(opcional)")
                ]),
                html.Div([
                    html.Label("Métrica", className="fw-bold"),
                    dcc.Dropdown(
                        id="pv-metric",
                        options=([{"label": "Contagem de respostas", "value": "__count__"}] +
                                 [{"label": c, "value": c} for c in numeric_cols]),
                        value="__count__"
                    )
                ]),
            ]),
            html.Div(className="ctrl-grid", children=[
                html.Div([
                    html.Label("Agregação", className="fw-bold"),
                    dcc.RadioItems(
                        id="pv-agg",
                        options=[{"label":"Soma","value":"sum"},
                                 {"label":"Média","value":"mean"},
                                 {"label":"Mediana","value":"median"},
                                 {"label":"Mín","value":"min"},
                                 {"label":"Máx","value":"max"}],
                        value="sum", inline=True)
                ]),
                html.Div([
                    html.Label("Tipo de gráfico", className="fw-bold"),
                    dcc.RadioItems(
                        id="pv-chart",
                        options=[{"label":"Barras","value":"bar"},
                                 {"label":"Heatmap","value":"heatmap"}],
                        value="bar", inline=True)
                ]),
                html.Div([
                    html.Label("Filtro de período", className="fw-bold"),
                    dcc.DatePickerRange(
                        id="pv-daterange",
                        start_date=to_date_str(stats_local.get("start")),
                        end_date=to_date_str(stats_local.get("end")),
                        display_format="DD/MM/YYYY",
                        className="w-100"
                    )
                ]),
            ]),
            html.Div(className="ctrl-grid", children=[
                html.Div([
                    html.Label("Filtrar por dimensão (opcional)", className="fw-bold"),
                    dcc.Dropdown(
                        id="pv-dim-filter-col",
                        options=[], placeholder="Escolha uma dimensão de Linhas/Colunas",
                        clearable=True
                    ),
                ]),
                html.Div([
                    html.Label("Valores da dimensão", className="fw-bold"),
                    dcc.Dropdown(
                        id="pv-dim-filter-values",
                        options=[], multi=True,
                        placeholder="Selecione 1+ valores…",
                        clearable=True, maxHeight=320, optionHeight=32
                    ),
                ]),
                html.Div(),
            ]),
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("Tabela Dinâmica"),
                        dbc.CardBody(
                            id="pv-out-table",
                            style={"maxHeight": f"{CARD_HEIGHT}px", "overflowY": "auto"}
                        )
                    ], style={"height": "100%"}), md=4
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("Nuvem de tópicos (dinâmica)"),
                        dbc.CardBody(
                            id="pv-topics-cloud",
                            style={"height": f"{CARD_HEIGHT}px",
                                   "display": "flex", "alignItems": "center", "justifyContent": "center"}
                        )
                    ], style={"height": "100%"}), md=4
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("Gráfico (clique nas barras para ver respostas)"),
                        dbc.CardBody(
                            dcc.Loading(
                                dcc.Graph(id="pv-out-chart-graph",
                                          style={"height": f"{CARD_HEIGHT}px"},
                                          config={"displayModeBar": False}),
                                type="dot"))
                    ], style={"height": "100%"}), md=4
                ),
            ], className="g-3 align-items-stretch"),
            modal_drill
        ])
    ], className="mb-4 dash-card")


# ==============================
# 9) Callbacks – Captura ENV e KEY da URL
# ==============================
from urllib.parse import parse_qs

@dash.callback(
    Output("current-env", "data"),
    Input("url", "search"),
    prevent_initial_call=False
)
def set_current_env(search):
    default_env = normalize_env(os.getenv("APP_DEFAULT_ENV", "dev"))
    env = default_env
    if search and "env=" in search:
        qs = parse_qs(search.lstrip("?"))
        env = normalize_env((qs.get("env", [default_env]) or [default_env])[0])
    return env

@dash.callback(
    Output("current-key", "data"),
    Input("url", "search"),
    prevent_initial_call=False
)
def set_current_key(search):
    default_key = os.getenv("KEY", "")
    key = default_key
    if search and "key=" in search:
        qs = parse_qs(search.lstrip("?"))
        key = (qs.get("key", [default_key]) or [default_key])[0]
    return key


# ==============================
# 10) Callbacks – Pivot principal
# ==============================

@dash.callback(
  Output("pv-out-table","children"),
  Output("pv-out-chart-graph","figure"),
  Output("pv-topics-cloud","children"),
  Input("pv-rows","value"),
  Input("pv-cols","value"),
  Input("pv-metric","value"),
  Input("pv-agg","value"),
  Input("pv-chart","value"),
  Input("pv-daterange","start_date"),
  Input("pv-daterange","end_date"),
  Input("pv-qid","value"),
  Input("pv-use-answer","value"),
  Input("pv-answer-binning","value"),
  Input("pv-dim-filter-col","value"),
  Input("pv-dim-filter-values","value"),
  Input("current-key","data"),
  Input("current-env","data"),
)

def update_pivot(rows, cols, metric, agg, chart, ds, de, pv_qid, pv_use_answer, pv_bins,
                 dim_filter_col, dim_filter_vals, key, env_resolved):
    try:
        key = key or os.getenv("KEY","")
        env_resolved = normalize_env(env_resolved or os.getenv("APP_DEFAULT_ENV","dev"))

        df = load_df_for_key(env_resolved, key) if key else pd.DataFrame()
        if df.empty:
            return empty_state("Sem dados."), go.Figure(), empty_state("Sem dados.")
        d = df.copy()

        # período
        if ds and de and "date_of_response" in d.columns:
            d = d[(d["date_of_response"] >= ds) & (d["date_of_response"] <= de)]

        # normaliza seleção
        rows = rows if isinstance(rows, list) else ([rows] if rows else [])
        if not rows:
            return empty_state("Escolha ao menos 1 dimensão em Linhas."), go.Figure(), empty_state("Escolha ao menos 1 dimensão.")

        # se uma pergunta foi escolhida, restringe DF e (se aplicável) cria __pv_answer__
        base_qtype = None
        wants_answer_dim = pv_use_answer and ("on" in (pv_use_answer or []))
        if pv_qid:
            d = d[d["question_id"].astype(str) == str(pv_qid)].copy()
            if d.empty:
                return empty_state("A pergunta selecionada não possui dados no período/recorte atual."), go.Figure(), empty_state("Sem dados para nuvem.")
            base_qtype = get_qtype_for_question_with_meta(env_resolved, pv_qid, d["answer"], key)
            if wants_answer_dim and base_qtype != "text":
                try:
                    bins = int(pv_bins) if str(pv_bins) in {"5","10","20"} else 10
                except Exception:
                    bins = 10
                d = make_pv_answer(d, bins=bins)

        # filtro por dimensão (apenas se a coluna existe após possíveis explodes/cuts)
        if dim_filter_col and dim_filter_vals and dim_filter_col in d.columns:
            chosen = dim_filter_vals if isinstance(dim_filter_vals, list) else [dim_filter_vals]
            d = d[d[dim_filter_col].astype(str).isin([str(v) for v in chosen])]

        # garante que __pv_answer__ existe quando solicitado nas dimensões
        if ("__pv_answer__" in rows or cols == "__pv_answer__") and "__pv_answer__" not in d.columns:
            return empty_state("Ative 'Usar respostas como dimensão' e selecione a pergunta."), go.Figure(), empty_state("Selecione a pergunta para a nuvem.")

        # métrica
        if metric == "__count__":
            d["__count__"] = 1
            val, aggfunc = "__count__", "sum"
        else:
            d[metric] = pd.to_numeric(d[metric], errors="coerce")
            val, aggfunc = metric, (agg or "mean")

        # pivot
        piv = pd.pivot_table(
            d, index=rows, columns=cols,
            values=val, aggfunc=aggfunc, fill_value=0, dropna=False
        )

        # >>> RENOMEIA COLUNAS SÓ PARA EXIBIÇÃO
        piv_disp = (
            piv.reset_index()
               .rename(columns={"__count__": "#", "__pv_answer__": "Respostas"})
        )

        table = dbc.Table.from_dataframe(
            piv_disp.head(500), striped=True, bordered=False, hover=True,
            size="sm", responsive=True
        )

        fig = go.Figure()
        if chart == "bar":
            if cols:
                piv_m = piv.reset_index().melt(id_vars=rows, var_name=cols, value_name="value")
                x = rows[-1]
                x_title = "Respostas" if x == "__pv_answer__" else "Dimensão"
                fig = px.bar(piv_m, x=x, y="value", color=cols, barmode="group", title="Pivot – Barras")
                fig.update_traces(text=piv_m["value"], textposition="outside", cliponaxis=False)
                fig = create_fig_style(fig, x=x_title, y="")
                fig.update_yaxes(showticklabels=False)  # remove rótulos do eixo Y
                fig = responsive_axis(fig, labels=piv_m[x].unique().tolist())
            else:
                piv_s = piv.reset_index()
                x = rows[-1]
                x_title = "Respostas" if x == "__pv_answer__" else "Dimensão"
                val_cols = [c for c in piv_s.columns if c not in rows]
                ycol = val_cols[0] if val_cols else None
                if ycol:
                    fig = px.bar(piv_s, x=x, y=ycol, title="Pivot – Barras")
                    fig.update_traces(text=piv_s[ycol], textposition="outside", cliponaxis=False)
                    fig = create_fig_style(fig, x=x_title, y="")
                    fig.update_yaxes(showticklabels=False)  # remove rótulos do eixo Y
                    fig = responsive_axis(fig, labels=piv_s[x].unique().tolist())
                else:
                    fig = go.Figure()
        else:
            if cols and len(rows) == 1:
                hm = piv.copy()
                fig = px.imshow(hm, labels=dict(x=cols, y=(rows[0] if rows else ""), color="Valor"),
                                title="Pivot – Heatmap")
            else:
                fig = go.Figure()

        fig.update_yaxes(showticklabels=False)

        # Mostra a nuvem sempre que a pergunta for campo aberto
        if pv_qid and (base_qtype in {"open-ended", "text"}):
            cloud_child = build_topics_wordcloud_component(d)  # usa a coluna 'topic'
        else:
            cloud_child = empty_state("Disponível apenas para perguntas de texto livre.")

        return table, fig, cloud_child

    except Exception as e:
        app.server.logger.exception("Erro no callback update_pivot")
        return _error_box("Erro no callback update_pivot", e), go.Figure(), _error_box("Erro", e)


@dash.callback(
    Output("pv-dim-filter-col", "options"),
    Output("pv-dim-filter-col", "value"),
    Input("pv-rows", "value"),
    Input("pv-cols", "value"),
)
def sync_dim_filter_col(rows, cols):
    rows = rows if isinstance(rows, list) else ([rows] if rows else [])
    cols = cols if isinstance(cols, list) else ([cols] if cols else [])
    dims = [c for c in rows + cols if c]
    dims = list(dict.fromkeys(dims))
    return [{"label": c, "value": c} for c in dims], None

@dash.callback(
    Output("pv-dim-filter-values", "options"),
    Output("pv-dim-filter-values", "value"),
    Input("pv-dim-filter-col", "value"),
    Input("pv-qid", "value"),
    Input("pv-use-answer", "value"),
    Input("pv-answer-binning", "value"),
    Input("pv-daterange", "start_date"),
    Input("pv-daterange", "end_date"),
    Input("current-key","data"),
    Input("current-env","data"),
)
def sync_dim_filter_values(dim_col, pv_qid, pv_use_answer, pv_bins, ds, de, key, env_resolved):
    key = key or os.getenv("KEY","")
    env_resolved = normalize_env(env_resolved or "dev")

    df = load_df_for_key(env_resolved, key) if key else pd.DataFrame()

    if not dim_col or df.empty:
        return [], None

    d = df.copy()
    if ds and de and "date_of_response" in d.columns:
        d = d[(d["date_of_response"] >= ds) & (d["date_of_response"] <= de)]

    if pv_qid:
        d = d[d["question_id"].astype(str) == str(pv_qid)].copy()
        qtype = analyze_qtype(d["answer"]) if not d.empty else None
        wants_answer_dim = pv_use_answer and ("on" in (pv_use_answer or []))
        if wants_answer_dim and qtype != "text":
            try:
                bins = int(pv_bins) if str(pv_bins) in {"5","10","20"} else 10
            except Exception:
                bins = 10
            d = make_pv_answer(d, bins=bins)
        if dim_col == "__pv_answer__" and "__pv_answer__" not in d.columns:
            return [], None

    if dim_col not in d.columns:
        return [], None

    vals = (d[dim_col].dropna().astype(str).str.strip()
            .loc[lambda s: s.ne("") & ~s.str.lower().isin({"nan","none","null"})]
            .unique().tolist())
    vals.sort()
    return [{"label": v, "value": v} for v in vals], None


# ==============================
# 11) Renderização das Abas
# ==============================
@dash.callback(
    Output("tab-content", "children"),
    Input("main-tabs", "active_tab"),
    Input("current-key", "data"),
    Input("current-env", "data"),
    prevent_initial_call=False
)
def render_tab(active, key, env_resolved):
    try:
        key = key or os.getenv("KEY", "")
        env_resolved = normalize_env(env_resolved or "dev")

        try:
            df = load_df_for_key(env_resolved, key) if key else pd.DataFrame()
        except Exception as e:
            msg = f"Erro ao carregar CUBE para env={env_resolved} key={key}: {e}"
            print("[render_tab]", msg)
            return html.Div(msg, className="alert alert-danger")

        state = build_state(df, env_resolved=env_resolved, key=key)

        if df.empty:
            return html.Div("Estamos aguardando dados para gerar insights sobre seu caso de uso...", className="alert alert-warning")

        if active == "questions":
            cards = [
                question_card(
                    r["question_id"],
                    r["question_description"],
                    state["ALLOWED_SEGMENT_COLS"],
                    df,
                    env_resolved,
                    key
                )
                for _, r in state["questions_df"].iterrows()
            ]
            return dbc.Row(cards) if cards else empty_state("Sem perguntas para exibir.")

        if active == "pivot":
            try:
                ui = pivot_controls(df, state)
                return html.Div([ui])
            except Exception as e:
                import traceback
                print("[pivot_controls ERROR]", repr(e))
                traceback.print_exc()
                return html.Div(f"Erro ao montar Pivot: {e}", className="alert alert-danger")

        if active == "raw":
            cols_show = [c for c in df.columns if c not in {"orig_answer","survey_id"} and not is_pii(c)]
            if "respondent_id" in cols_show:
                cols_show = ["respondent_id"] + [c for c in cols_show if c != "respondent_id"]
            return html.Div([
                html.H5("📋 Dados brutos"),
                raw_controls(df),
                html.Div(id="raw-table")
            ])

        return html.Div("Selecione uma aba.", className="text-muted")
    
    except Exception as e:
        app.server.logger.exception("Erro no callback render_tab")
        return _error_box("Erro no callback render_tab", e)


# ==============================
# 12) Callbacks de UX e Drill por Pergunta
# ==============================
@dash.callback(
    Output({"type":"q-collapse","qid":MATCH}, "is_open"),
    Input({"type":"q-collapse-btn","qid":MATCH}, "n_clicks"),
    State({"type":"q-collapse","qid":MATCH}, "is_open"),
    prevent_initial_call=True
)
def toggle_collapse(n, is_open):
    if n:
        return not is_open
    return is_open

@dash.callback(
    Output({"type":"q-segvals","qid":MATCH}, "options"),
    Output({"type":"q-segvals","qid":MATCH}, "value"),
    Input({"type":"q-segcol","qid":MATCH}, "value"),
    Input("current-key","data"),
    Input("current-env","data"),
)
def update_seg_values_per_q(seg_col, key, env_resolved):
    key = key or os.getenv("KEY","")
    env_resolved = normalize_env(env_resolved or "dev")
    df = load_df_for_key(env_resolved, key) if key else pd.DataFrame()

    if not seg_col or df.empty or seg_col not in df.columns:
        return [], None
    vals = sorted(df[seg_col].dropna().astype(str).unique().tolist())
    return [{"label": v, "value": v} for v in vals], None

@dash.callback(
    Output({"type":"q-filter","qid":MATCH}, "data"),
    Input({"type":"q-catfig","qid":MATCH}, "clickData"),
    Input({"type":"q-topicsfig","qid":MATCH}, "clickData"),
    Input({"type":"q-clear","qid":MATCH}, "n_clicks"),
    State({"type":"q-filter","qid":MATCH}, "data"),
    prevent_initial_call=True
)
def sync_qfilter(cat_click, topic_click, clear_clicks, current):
    current = current or {"category": None, "topic": None}
    ctx = dash.callback_context
    if not ctx.triggered:
        return current
    prop = ctx.triggered[0]["prop_id"]

    if prop.endswith(".n_clicks"):
        return {"category": None, "topic": None}

    if '"q-catfig"' in prop and prop.endswith(".clickData"):
        label = _extract_click_label(cat_click)
        if not label:
            return current
        return {"category": None if current.get("category") == str(label) else str(label), "topic": None}

    if '"q-topicsfig"' in prop and prop.endswith(".clickData"):
        label = _extract_click_label(topic_click)
        if not label:
            return current
        return {"category": None, "topic": None if current.get("topic") == str(label) else str(label)}

    return current

@dash.callback(
    Output({"type":"q-drill","qid":MATCH}, "data"),
    Input({"type":"q-fig","qid":MATCH}, "clickData"),
    Input({"type":"q-catfig","qid":MATCH}, "clickData"),
    Input({"type":"q-clear","qid":MATCH}, "n_clicks"),
    State({"type":"q-drill","qid":MATCH}, "data"),
    State({"type":"q-fig","qid":MATCH}, "id"),
    prevent_initial_call=True
)
def update_drill_state(main_click, cat_click, clear_clicks, curr, fig_id):
    curr = curr or {"level":0, "sentiment":None, "category":None}
    ctx = dash.callback_context
    if not ctx.triggered:
        return curr
    prop = ctx.triggered[0]["prop_id"]

    if prop.endswith(".n_clicks"):
        return {"level":0, "sentiment":None, "category":None}

    if '"q-fig"' in prop and prop.endswith(".clickData"):
        label = _extract_click_label(main_click)
        if not label:
            return curr
        if str(curr.get("sentiment")) == str(label) and (curr.get("level") or 0) >= 1:
            return {"level":0, "sentiment":None, "category":None}
        return {"level":1, "sentiment":str(label), "category":None}

    if '"q-catfig"' in prop and prop.endswith(".clickData"):
        label = _extract_click_label(cat_click)
        if not label:
            return curr
        if str(curr.get("category")) == str(label) and (curr.get("level") or 0) >= 2:
            return {"level":1, "sentiment":curr.get("sentiment"), "category":None}
        return {"level":2, "sentiment":curr.get("sentiment"), "category":str(label)}

    return curr

@dash.callback(
    Output({"type":"q-fig","qid":MATCH}, "figure"),
    Output({"type":"q-fig-wrap","qid":MATCH}, "style"),
    Output({"type":"q-catfig","qid":MATCH}, "figure"),
    Output({"type":"q-topicsfig","qid":MATCH}, "figure"),
    Output({"type":"q-answers","qid":MATCH}, "figure"),
    Output({"type":"q-catfig","qid":MATCH}, "style"),
    Output({"type":"q-topicsfig","qid":MATCH}, "style"),
    Output({"type":"q-answers","qid":MATCH}, "style"),
    Output({"type":"q-clear","qid":MATCH}, "style"),
    Output({"type":"q-sentcards","qid":MATCH}, "children"),
    Input({"type":"q-segcol","qid":MATCH}, "value"),
    Input({"type":"q-segvals","qid":MATCH}, "value"),
    Input({"type":"q-filter","qid":MATCH}, "data"),
    Input({"type":"q-drill","qid":MATCH}, "data"),
    State({"type":"q-fig","qid":MATCH}, "id"),
    Input("current-key","data"),
    Input("current-env","data"),
)

def update_question_graph(seg_col, seg_vals, qfilter, qdrill, fig_id, key, env_resolved):
    # 10 saídas SEMPRE
    main_fig   = go.Figure()
    cat_fig    = go.Figure()
    topics_fig = go.Figure()
    answers_fig= go.Figure()

    style_show = {"marginTop":"12px"}
    style_hide = {"display":"none"}

    fig_wrap_style = {"marginTop":"12px"}   # padrão: mostrar
    fig_wrap_style = style_show

    cat_style      = style_hide
    topics_style   = style_hide
    answers_style  = style_hide
    clear_style    = {"display":"none"}
    sent_cards     = html.Div()

    try:
        key = key or os.getenv("KEY","")
        env_resolved = normalize_env(env_resolved or "dev")
        df = load_df_for_key(env_resolved, key) if key else pd.DataFrame()

        if not fig_id or "qid" not in fig_id:
            return (main_fig, fig_wrap_style, cat_fig, topics_fig, answers_fig,
                    {"display":"none"}, {"display":"none"}, {"display":"none"},
                    {"display":"none"}, sent_cards)
 
        qid = fig_id["qid"]
        sub_all = df[df["question_id"] == qid].copy()
        sub = sub_all.copy()

        if seg_col and seg_vals and seg_col in sub.columns:
            sub = sub[sub[seg_col].astype(str).isin([str(v) for v in seg_vals])]
        sub = _apply_qfilter(sub, qfilter)

        base_qtype = get_qtype_for_question_with_meta(
            env_resolved,
            qid,
            sub_all["answer"] if "answer" in sub_all.columns else pd.Series(dtype=str),
            key
        )

        meta = load_questionnaire_meta(env_resolved, key)
        opts = (meta.get("options_map", {}) or {}).get(str(qid)) or []

        # --- LIKERT 1–5 (se houver)
        is_likert = (str(qid) in LIKERT_1_5_IDS) and (base_qtype in {"numeric","categorical","text"})
        if is_likert:
            vals = pd.to_numeric(sub["answer"], errors="coerce").round().clip(1,5).astype("Int64")
            d = sub.assign(val=vals).dropna(subset=["val"])
            cat_order = [1,2,3,4,5]
            labels_15 = [str(i) for i in cat_order]
            vc = d["val"].astype(int).value_counts().reindex(cat_order, fill_value=0)
            main_fig = px.bar(x=labels_15, y=vc.values, title="Distribuição (escala 1–5)")
            main_fig = create_fig_style(main_fig, x="Escala (1–5)", y="Qtde")
            main_fig.update_traces(text=list(vc.values), textposition="outside", cliponaxis=False)
            main_fig.update_xaxes(showgrid=False, showticklabels=True)
            main_fig.update_yaxes(showgrid=False, showticklabels=True)

            # cards só para abertas
            sent_cards = render_sentiment_cards(sub) if (base_qtype in {"open-ended","text"}) else html.Div()
            clear_style = {"display":"inline-block","marginBottom":"12px"} if (qfilter and (qfilter.get("category") or qfilter.get("topic"))) else {"display":"none"}

            return (main_fig, fig_wrap_style, cat_fig, topics_fig, answers_fig,
                    cat_style, topics_style, answers_style, clear_style, sent_cards)

        # --- NUMÉRICA
        if base_qtype == "numeric":
            vals = pd.to_numeric(sub["answer"], errors="coerce")
            main_fig = px.histogram(vals.dropna(), nbins=20, title="Distribuição")
            main_fig = create_fig_style(main_fig, x="Valor", y="Frequência")
            main_fig.update_xaxes(showgrid=False, showticklabels=True)
            main_fig.update_yaxes(showgrid=False, showticklabels=True)

        # --- MÚLTIPLA
        elif base_qtype in ["multiple-choice", "multiple"]:
            sent_cards = html.Div()

            exploded = explode_multiple(sub)
            if not exploded.empty and "answer_item" in exploded.columns:
                # limpeza sem reindex
                exploded["answer_item"] = exploded["answer_item"].astype(str)
                m = _non_empty_mask(exploded["answer_item"])
                exploded = exploded[m].copy()

                if not exploded.empty:
                    vc = exploded["answer_item"].value_counts().head(20)
                    df_bar = pd.DataFrame({"opcao": vc.index.astype(str), "qtde": vc.values})
                    main_fig = px.bar(df_bar, x="opcao", y="qtde", title="Ocorrências por opção")
                    main_fig.update_traces(text=df_bar["qtde"], textposition="outside", cliponaxis=False)
                    main_fig = create_fig_style(main_fig, x="Opção", y="Qtde")
                    main_fig = responsive_axis(main_fig, labels=df_bar["opcao"].tolist())
                else:
                    main_fig = make_minimal(go.Figure())
            else:
                main_fig = make_minimal(go.Figure())

            main_fig.update_xaxes(showgrid=False, ticks="")
            main_fig.update_yaxes(showgrid=False, ticks="", showticklabels=False)

        # --- CATEGÓRICA
        elif base_qtype in ("single-choice", "categorical"):
            sent_cards = html.Div()

            # Tenta na ordem: answer -> orig_answer -> option/choice -> category (fallback duro)
            s, used_col = _first_nonempty_series(
                sub, ["answer", "orig_answer", "option", "choice", "resposta", "category"]
            )
            print(f"[DEBUG] CATEGORICA qid={qid} fonte={used_col} n={len(s)}")

            if not s.empty:
                vc = s.value_counts()

                # respeita opções do questionário, se existirem
                meta = load_questionnaire_meta(env_resolved, key)
                opts = (meta.get("options_map", {}) or {}).get(str(qid)) or []
                if opts:
                    order = [o for o in opts if o in vc.index]
                    outros = [o for o in vc.index if o not in order]
                    vc = vc.reindex(order + outros)

                vc = vc.head(30)
                df_bar = pd.DataFrame({"opcao": vc.index.astype(str), "qtde": vc.values})
                main_fig = px.bar(
                    df_bar, x="opcao", y="qtde",
                    title="Ocorrências por opção",
                    category_orders={"opcao": df_bar["opcao"].tolist()}
                )
                main_fig.update_traces(text=df_bar["qtde"], textposition="outside", cliponaxis=False)
                main_fig = create_fig_style(main_fig, x="Opção", y="Qtde")
                main_fig = responsive_axis(main_fig, labels=df_bar["opcao"].tolist())
            else:
                main_fig = make_minimal(go.Figure())

            main_fig.update_xaxes(showgrid=False, ticks="")
            main_fig.update_yaxes(showgrid=False, ticks="", showticklabels=False)

        elif base_qtype == "open-ended":
            # esconder o gráfico principal
            fig_wrap_style = {"display":"none"}
            main_fig = go.Figure()

            # cards de sentimento
            sent_cards = render_sentiment_cards(sub) if not sub.empty else html.Div()


            # ---- NOVO: gráfico por CATEGORIA no lugar de "Intenção"
            s_cat = sub["category"].dropna().astype(str).str.strip() if "category" in sub.columns else pd.Series([], dtype=str)
            s_cat = s_cat[s_cat.ne("") & ~s_cat.str.lower().isin({"nan", "none", "null"})]

            if not s_cat.empty:
                vc = s_cat.value_counts().head(30)
                df_bar = pd.DataFrame({"Categoria": vc.index.astype(str), "Qtde": vc.values})
                cat_fig = px.bar(df_bar, x="Categoria", y="Qtde", title="Categorias – Distribuição")
                cat_fig.update_traces(text=df_bar["Qtde"], textposition="outside", cliponaxis=False)
                cat_fig = create_fig_style(cat_fig, x="Categoria", y="Qtde")
                cat_fig = responsive_axis(cat_fig, labels=df_bar["Categoria"].tolist())
                cat_style = {"marginTop": "12px"}
            else:
                cat_fig = go.Figure()
                cat_style = {"display": "none"}

            # Mantemos os outros slots ocultos para não duplicar gráfico
            topics_fig = go.Figure()
            topics_style = {"display": "none"}
            answers_fig = go.Figure()
            answers_style = {"display": "none"}

            # Botão "Limpar filtros" quando houver filtro local ou drill
            has_local_filter = bool(qfilter and (qfilter.get("category") or qfilter.get("topic")))
            has_drill = bool((qdrill or {}).get("level", 0) > 0)
            clear_style = {"display": "inline-block", "marginBottom": "12px"} if (has_local_filter or has_drill) else {"display": "none"}

            return (
                main_fig,                     # q-fig
                fig_wrap_style,               # q-fig-wrap style (escondido)
                cat_fig,                      # q-catfig  (AGORA o gráfico principal p/ abertas)
                topics_fig,                   # q-topicsfig
                answers_fig,                  # q-answers
                cat_style,                    # style catfig (mostrar/ocultar)
                topics_style,                 # style topicsfig
                answers_style,                # style answersfig
                clear_style,                  # style botão limpar
                sent_cards                    # cards de sentimento
            )

        # Retorno padrão para todos os outros tipos (numeric, categorical, multiple)
        # Botão "Limpar filtros" quando houver filtro local
        has_local_filter = bool(qfilter and (qfilter.get("category") or qfilter.get("topic")))
        clear_style = {"display": "inline-block", "marginBottom": "12px"} if has_local_filter else {"display": "none"}

        return (
            main_fig,                     # q-fig
            fig_wrap_style,               # q-fig-wrap style
            cat_fig,                      # q-catfig
            topics_fig,                   # q-topicsfig
            answers_fig,                  # q-answers
            cat_style,                    # style catfig
            topics_style,                 # style topicsfig
            answers_style,                # style answersfig
            clear_style,                  # style botão limpar
            sent_cards                    # cards de sentimento
        )

    except Exception as e:
        app.server.logger.exception("Erro no callback update_question_graph")
        empty = go.Figure()
        error_msg = _error_box("Erro no callback update_question_graph", e)
        return (empty, style_hide, empty, empty, empty,
                style_hide, style_hide, style_hide, {"display":"none"}, error_msg)


@dash.callback(
    Output({"type":"q-filterpill","qid":MATCH}, "children"),
    Input({"type":"q-filter","qid":MATCH}, "data")
)
def show_filter_pill(qfilter):
    if not qfilter:
        return ""
    if qfilter.get("category"):
        return dbc.Badge(f'Categoria: {qfilter["category"]}', color="info", className="me-2")
    if qfilter.get("topic"):
        return dbc.Badge(f'Tópico: {qfilter["topic"]}', color="info", className="me-2")
    return ""

@dash.callback(
    Output("raw-table", "children"),
    Input({"type": "raw-filter", "col": ALL}, "value"),
    State({"type": "raw-filter", "col": ALL}, "id"),
    State("current-key", "data"),
    State("current-env", "data"),
    prevent_initial_call=False,
)
def update_raw_table(filter_values, filter_ids, key, env_resolved):
    try:
        # Mapeia colunas => valores escolhidos
        active_filters = {}
        for val, fid in zip(filter_values or [], filter_ids or []):
            col = (fid or {}).get("col")
            if not col:
                continue
            if isinstance(val, list):
                sel = [str(v) for v in val if v not in (None, "")]
            elif val not in (None, ""):
                sel = [str(val)]
            else:
                sel = []
            if sel:
                active_filters[col] = sel

        # carrega DF
        env_resolved = normalize_env(env_resolved or "dev")
        df = load_df_for_key(env_resolved, key or os.getenv("KEY","")) if key or os.getenv("KEY","") else pd.DataFrame()

        if df.empty:
            return html.Div("Sem dados.", className="alert alert-warning")

        # aplica filtros
        d = df.copy()
        for col, sel in active_filters.items():
            if col in d.columns:
                d = d[d[col].astype(str).isin(sel)]

        # escolhe colunas seguras (sem PII)
        cols_show = [c for c in d.columns if c not in {"orig_answer","survey_id"} and not is_pii(c)]
        if "respondent_id" in cols_show:
            cols_show = ["respondent_id"] + [c for c in cols_show if c != "respondent_id"]

        sample = d[cols_show].copy() if cols_show else d.head(0)
        return dbc.Table.from_dataframe(sample.head(300), striped=True, bordered=True, hover=True, size="sm", responsive=True)
    
    except Exception as e:
        app.server.logger.exception("Erro no callback update_raw_table")
        return _error_box("Erro no callback update_raw_table", e)



# ==============================
# 13) Drill da Pivot (modal)
# ==============================
@dash.callback(
    Output("pv-drill-modal", "is_open"),
    Output("pv-drill-title", "children"),
    Output("pv-drill-content", "children"),
    Input("pv-out-chart-graph", "clickData"),
    State("pv-rows", "value"),
    State("pv-cols", "value"),
    State("pv-qid", "value"),
    State("pv-use-answer", "value"),
    State("pv-answer-binning", "value"),
    State("pv-daterange", "start_date"),
    State("pv-daterange", "end_date"),
    Input("current-key","data"),
    Input("current-env","data"),
    prevent_initial_call=True
)
def pivot_drill(clickData, rows, cols, pv_qid, pv_use_answer, pv_bins, ds, de, key, env_resolved):
    try:
        key = key or os.getenv("KEY","")
        env_resolved = normalize_env(env_resolved or "dev")

        df = load_df_for_key(env_resolved, key) if key else pd.DataFrame()
        if not clickData or df.empty:
            return False, "", ""
        d = df.copy()

        if ds and de and "date_of_response" in d.columns:
            d = d[(d["date_of_response"] >= ds) & (d["date_of_response"] <= de)]
        if pv_qid:
            d = d[d["question_id"].astype(str) == str(pv_qid)].copy()
            qtype = analyze_qtype(d["answer"]) if not d.empty else None
            wants_answer_dim = pv_use_answer and ("on" in (pv_use_answer or []))
            if wants_answer_dim and qtype != "text":
                try:
                    bins = int(pv_bins) if str(pv_bins) in {"5","10","20"} else 10
                except Exception:
                    bins = 10
                d = make_pv_answer(d, bins=bins)

        rows = rows if isinstance(rows, list) else ([rows] if rows else [])
        cols = cols if isinstance(cols, list) else ([cols] if cols else [])

        pt = clickData["points"][0]
        custom = pt.get("customdata") or []
        xval = custom[0] if len(custom) >= 1 else pt.get("x")
        cval = custom[1] if len(custom) >= 2 else None

        if rows:
            dimx = rows[-1]
            if dimx in d.columns:
                d = d[d[dimx].astype(str) == str(xval)]
        if cols:
            dimc = cols[0]
            if dimc in d.columns and cval is not None:
                d = d[d[dimc].astype(str) == str(cval)]

        state = build_state(df)
        qdesc_map = state.get("QDESC_MAP", {})
        title = qdesc_map.get(str(pv_qid), "Respostas") if pv_qid else "Respostas"
        if d.empty:
            return True, f"Respostas – {title}", html.Div("Nenhum registro para este ponto.", className="text-muted")

        show_cols = ["date_of_response","category","topic","sentiment","answer"]
        show_cols = [c for c in show_cols if c in d.columns]
        tbl = d[show_cols].copy().sort_values("date_of_response", na_position="last")
        if "date_of_response" in tbl.columns:
            tbl["date_of_response"] = pd.to_datetime(tbl["date_of_response"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")

        table = dbc.Table.from_dataframe(tbl.head(1000), striped=True, bordered=False, hover=True, size="sm", responsive=True)
        return True, f"Respostas – {title}", table
    
    except Exception as e:
        app.server.logger.exception("Erro no callback pivot_drill")
        return True, "Erro", _error_box("Erro no callback pivot_drill", e)

# ==============================
# 14) Run
# ==============================
if __name__ == "__main__":
    print(f"[RUN] Starting Dash on 0.0.0.0:{PORT} | BASE_PATH={BASE_PATH}")
    app.run(debug=False, host="0.0.0.0", port=PORT)
