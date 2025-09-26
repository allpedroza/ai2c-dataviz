import os, re, csv, glob, argparse, warnings
from typing import List, Optional, Dict, Tuple
from datetime import datetime

warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import dash
from dash import dcc, html, Input, Output, State, MATCH
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objs as go
import plotly.io as pio
import io, base64
import boto3

from functools import lru_cache
import boto3

DF_CACHE = {}  # {key: pd.DataFrame}

def s3_path_for_key(key: str) -> str:
    bucket = os.getenv("S3_BUCKET", "ai2c-genai-dev")
    prefix = os.getenv("S3_REPORTS_PREFIX", "ai2c-reports/reports")
    return f"s3://{bucket}/{prefix}/{key}/{key}_analytics_cube.csv"

def load_df_for_key(key: str) -> pd.DataFrame:
    # cache em memória por KEY
    if key in DF_CACHE:
        return DF_CACHE[key]
    path = s3_path_for_key(key)
    # download para /tmp e reaproveita read_csv_robust existente
    if path.startswith("s3://"):
        _, _, rest = path.partition("s3://")
        bucket, _, keypath = rest.partition("/")
        local = f"/tmp/{os.path.basename(keypath)}"
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "sa-east-1"))
        s3.download_file(bucket, keypath, local)
        df = read_csv_robust(local)
    else:
        df = read_csv_robust(path)

    # normalizações iguais ao load_cube()
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes no CUBE: {missing}")
    for c in REQUIRED_COLS:
        df[c] = df[c].astype(str).map(lambda x: x.strip() if isinstance(x,str) else x)

    df["answer"] = df["orig_answer"].astype(str).map(fix_mojibake)
    for c in ["question_description","category","topic","sentiment","intention"]:
        df[c] = df[c].astype(str).map(fix_mojibake)
    df["sentiment"] = df["sentiment"].map(normalize_sentiment)
    df["date_of_response"] = pd.to_datetime(df["date_of_response"], errors="coerce")
    df["confidence_level"] = pd.to_numeric(df["confidence_level"], errors="coerce")

    DF_CACHE[key] = df
    return df

def build_state(df: pd.DataFrame):
    # tudo que antes era global e dependia do df
    def _allowed_segment_cols(d: pd.DataFrame) -> list[str]:
        cols = []
        for c in d.columns:
            if c in NON_SEGMENTABLE: continue
            if is_pii(c): continue
            if high_cardinality(d, c): continue
            cols.append(c)
        return sorted(cols)

    stats = {
        "total_responses": len(df),
        "unique_respondents": df["respondent_id"].nunique(),
        "unique_questions": df["question_id"].nunique(),
        "start": df["date_of_response"].min(),
        "end": df["date_of_response"].max(),
    } if not df.empty else {}

    qdf = pd.DataFrame(columns=["question_id","question_description"])
    if not df.empty:
        qdf = df[["question_id","question_description"]].drop_duplicates()
        qdf["__ord"] = qdf["question_id"].apply(numeric_suffix)
        qdf = qdf.sort_values(["__ord","question_id"]).drop(columns="__ord")

    qdesc_map = {str(r["question_id"]): (r["question_description"] or str(r["question_id"]))
                 for _, r in qdf.iterrows()}

    allowed_cols = _allowed_segment_cols(df)

    return {
        "stats": stats,
        "questions_df": qdf,
        "QDESC_MAP": qdesc_map,
        "ALLOWED_SEGMENT_COLS": allowed_cols,
    }


AWS_REGION = os.getenv("AWS_REGION", "sa-east-1")
S3_BUCKET  = os.getenv("S3_BUCKET", "ai2c-genai-dev")
S3_REPORTS_PREFIX = os.getenv("S3_REPORTS_PREFIX", "ai2c-reports/reports")
S3_INPUTS_PREFIX  = os.getenv("S3_INPUTS_PREFIX",  "integrador-inputs")



try:
    from wordcloud import WordCloud, STOPWORDS
    HAS_WORDCLOUD = True
except Exception:
    HAS_WORDCLOUD = False
    STOPWORDS = set()

# ==============================
# 0) Estilo Plotly (AI2C style)
# ==============================
pio.templates["modern"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(
            family="Poppins, system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif",
            size=13,
            color="#111111"  # ink
        ),
        title=dict(x=0, xanchor="left", font=dict(size=18, color="#111111")),
        margin=dict(l=40, r=20, t=60, b=40),
        # Paleta AI2C (laranjas + apoio)
        colorway=["#FF9800", "#FFB74D", "#FFA726", "#FB8C00", "#EF6C00", "#6C757D", "#111111"],
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            bgcolor="rgba(255,255,255,0)"
        ),
        xaxis=dict(
            showgrid=False, zeroline=False,
            showline=True, linecolor="#ECECEC", linewidth=1,
            ticks="outside", tickcolor="#ECECEC"
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#F3F4F6", gridwidth=1,
            zeroline=False, showline=False
        ),
        hoverlabel=dict(bgcolor="white", font=dict(color="#111111"), bordercolor="#ECECEC"),
    )
)
pio.templates.default = "modern"


# ==============================
# 1) Config & CLI
# ==============================
KEY = os.getenv("KEY", "68792c47e0b9668ef6f6ab5e")
EXPORT_HTML = os.getenv("EXPORT_HTML", "0") == "1"

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--export", action="store_true", default=False, help="Exporta HTML estático report_<KEY>.html")
parser.add_argument("--port", type=int, default=8050, help="Porta do servidor Dash")
args, _ = parser.parse_known_args()
EXPORT_HTML = EXPORT_HTML or args.export

# PORT: prioriza env PORT (App Runner/containers) e cai para argumento
PORT = int(os.getenv("PORT", args.port))

# localizar CUBE
CUBE_FILE = os.getenv("CUBE_FILE", f"{KEY}_analytics_cube.csv")
if not os.path.exists(CUBE_FILE):
    for pat in [f"{KEY}_analytics_cube*.csv", f"{KEY}-analytics_cube*.csv", "*analytics_cube*.csv"]:
        m = sorted(glob.glob(pat))
        if m:
            CUBE_FILE = m[0]
            break

# ==============================
# 2) Utilidades (I/O + limpeza)
# ==============================
def read_csv_robust(path: str) -> pd.DataFrame:
    # tenta detectar encoding e separador automaticamente
    for enc in ["utf-8","utf-8-sig","latin1","iso-8859-1"]:
        try:
            with open(path, "r", encoding=enc, errors="ignore") as f:
                sample = f.read(4096)
                delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            df = pd.read_csv(path, sep=delim, encoding=enc, dtype=str, na_values=["","NA","N/A","null","NULL","None"])
            df.columns = df.columns.str.strip()
            print(f"✓ CSV: {os.path.basename(path)} | enc={enc} sep='{delim}'")
            return df
        except Exception:
            continue
    # fallback
    return pd.read_csv(path, sep=None, engine="python", encoding="utf-8", on_bad_lines="skip", dtype=str)

def fix_mojibake(s: str) -> str:
    if not isinstance(s, str): return s
    rep = {"√£":"ã","√≥":"ó","√°":"á","√©":"é","√™":"ê","√∫":"ú","√º":"ú","√ß":"ç",
           "Ã£":"ã","Ã¡":"á","Ã©":"é","Ãª":"ê","Ãº":"ú","Ã³":"ó","Ã§":"ç","Ãñ":"ñ",
           "N√£o":"Não","n√£o":"não"}
    for k,v in rep.items(): s = s.replace(k,v)
    return s

SENTIMENT_ORDER = ["negativo", "neutro", "positivo"]
SENTIMENT_COLORS = {"positivo": "#10B981", "negativo": "#EF4444", "neutro": "#9CA3AF"}
SENTIMENT_MAP = {
    "pos": "positivo", "positivo": "positivo", "positive": "positivo",
    "neg": "negativo", "negativo": "negativo", "negative": "negativo",
    "neu": "neutro",   "neutro":   "neutro",   "neutral":  "neutro",
    "": None, "nan": None, "none": None
}
def normalize_sentiment(val: str) -> Optional[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    v = str(val).strip().lower()
    return SENTIMENT_MAP.get(v, v)

# ==============================
# 3) Carregamento & Validação (inputs obrigatórios)
# ==============================
REQUIRED_COLS = [
    "questionnaire_id","survey_id","respondent_id","date_of_response",
    "question_id","orig_answer","category","topic","sentiment","intention",
    "confidence_level","question_description"
]

def load_cube() -> pd.DataFrame:
    if not os.path.exists(CUBE_FILE):
        raise FileNotFoundError(f"CUBE não encontrado: {CUBE_FILE}")
    df = read_csv_robust(CUBE_FILE)

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes no CUBE: {missing}")

    # normalização básica
    for c in REQUIRED_COLS:
        df[c] = df[c].astype(str).map(lambda x: x.strip() if isinstance(x,str) else x)

    df["answer"] = df["orig_answer"].astype(str).map(fix_mojibake)
    for c in ["question_description","category","topic","sentiment","intention"]:
        df[c] = df[c].astype(str).map(fix_mojibake)

    df["sentiment"] = df["sentiment"].map(normalize_sentiment)
    df["date_of_response"] = pd.to_datetime(df["date_of_response"], errors="coerce")
    df["confidence_level"] = pd.to_numeric(df["confidence_level"], errors="coerce")

    return df

def s3_download_if_needed():
    """
    Se o CUBE não estiver local, baixa de s3://{S3_BUCKET}/{S3_REPORTS_PREFIX}/{KEY}/{KEY}_analytics_cube.csv
    e ajusta CUBE_FILE para o caminho baixado.
    """
    global CUBE_FILE
    if os.path.exists(CUBE_FILE):
        return

    s3_key = f"{S3_REPORTS_PREFIX}/{KEY}/{KEY}_analytics_cube.csv"
    local_dir = os.getenv("DATA_DIR", "/tmp")  # Lambda/ECS amigável
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, f"{KEY}_analytics_cube.csv")

    print(f"[S3] tentando baixar s3://{S3_BUCKET}/{s3_key} -> {local_path}")
    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        s3.download_file(S3_BUCKET, s3_key, local_path)
        CUBE_FILE = local_path
        print(f"[S3] OK, arquivo salvo em {local_path}")
    except Exception as e:
        print(f"[S3] Falha ao baixar {s3_key}: {e}")

# chame s3_download_if_needed() antes do load_cube()
s3_download_if_needed()

try:
    df_main = load_cube()
    print(f"[BOOT] KEY={KEY} | CUBE_FILE={CUBE_FILE} | rows={len(df_main)} | cols={len(df_main.columns) if not df_main.empty else 0}")
except Exception as e:
    print("❌ Erro ao carregar CUBE:", e)
    df_main = pd.DataFrame()

# ==============================
# 4) PII / Segmentação segura
# ==============================
def is_pii(col: str) -> bool:
    c = (col or "").lower()
    if c == "respondent_id":  # permitido (já vem hash/pseudonimizado do backend)
        return False
    patterns = [
        r"\bcpf\b", r"\bcnpj\b", r"\brg\b", r"\bdoc", r"document", r"\bpassport\b",
        r"e[-_ ]?mail", r"\bemail\b", r"\btelefone\b", r"\bphone\b", r"\bcelular\b",
        r"\bwhatsapp\b", r"\bendere", r"\baddress\b", r"\bcep\b", r"\bzipcode\b",
        r"\bnome\b", r"\bname\b", r"\bid\b", r"\bip\b",
        r"lat", r"lon", r"longitude", r"latitude", r"device", r"imei"
    ]
    return any(re.search(p, c) for p in patterns)

def high_cardinality(df: pd.DataFrame, col: str, max_ratio: float = 0.2, min_unique: int = 50) -> bool:
    try:
        n = len(df)
        u = df[col].astype(str).nunique(dropna=True)
        return (u >= min_unique) and (u / max(1, n) > max_ratio)
    except Exception:
        return True

NON_SEGMENTABLE = set(REQUIRED_COLS + ["answer", "orig_answer","respondent_id"])

def allowed_segment_cols(df: pd.DataFrame) -> List[str]:
    if df.empty: return []
    cols = []
    for c in df.columns:
        if c in NON_SEGMENTABLE: continue
        if is_pii(c): continue
        if high_cardinality(df, c): continue
        cols.append(c)
    return sorted(cols)

ALLOWED_SEGMENT_COLS = allowed_segment_cols(df_main)

# ==============================
# 5) Métricas + Perguntas
# ==============================
def dataset_stats(df: pd.DataFrame) -> Dict:
    if df.empty: return {}
    return {
        "total_responses": len(df),
        "unique_respondents": df["respondent_id"].nunique(),
        "unique_questions": df["question_id"].nunique(),
        "start": df["date_of_response"].min(),
        "end": df["date_of_response"].max(),
    }

stats = dataset_stats(df_main)

def numeric_suffix(s: str):
    m = re.search(r"(\d+)$", str(s))
    return int(m.group(1)) if m else float("inf")

questions_df = pd.DataFrame(columns=["question_id","question_description"])
if not df_main.empty:
    questions_df = df_main[["question_id","question_description"]].drop_duplicates()
    questions_df["__ord"] = questions_df["question_id"].apply(numeric_suffix)
    questions_df = questions_df.sort_values(["__ord","question_id"]).drop(columns="__ord")

# Mapa para título por id
QDESC_MAP = {str(r["question_id"]): (r["question_description"] or str(r["question_id"]))
             for _, r in questions_df.iterrows()}

# (opcional) conjunto de perguntas likert 1–5 — mantido como estava
LIKERT_1_5_IDS: set = set()
try:
    third_qid = str(questions_df.iloc[2]["question_id"])
    LIKERT_1_5_IDS.add(third_qid)
except Exception:
    pass

# ==============================
# 6) Helpers de visualização
# ==============================
STOPWORDS_PT = set()

def build_topics_wordcloud_component(d: pd.DataFrame, width: int = 900, height: int = 520):
    """
    Gera uma wordcloud dinâmica a partir da coluna 'topic' do DataFrame filtrado.
    - Não mostra NaN/None/vazio.
    - Usa pesos por frequência (value_counts).
    - Retorna um html.Img (ou um empty_state, se indisponível).
    """
    if not HAS_WORDCLOUD:
        return empty_state("Para a nuvem, instale: pip install wordcloud pillow")

    if d.empty or "topic" not in d.columns:
        return empty_state("Sem tópicos na seleção atual.")

    s = d["topic"].dropna().astype(str).str.strip()
    s = s[s.ne("") & ~s.str.lower().isin({"nan","none","null"})]
    if s.empty:
        return empty_state("Sem tópicos válidos para gerar a nuvem.")

    freq = s.value_counts()
    if freq.empty:
        return empty_state("Sem tópicos válidos para gerar a nuvem.")

    stop = STOPWORDS.union(STOPWORDS_PT)

    wc = WordCloud(
        width=width, height=height,
        background_color="white",
        colormap="tab20c",
        prefer_horizontal=0.95,
        random_state=42,
        collocations=False,
        normalize_plurals=True,
        max_words=200,
        min_font_size=10,
        stopwords=stop
    ).generate_from_frequencies(freq.to_dict())

    buf = io.BytesIO()
    wc.to_image().save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return html.Div([
        html.Img(
            src=f"data:image/png;base64,{b64}",
            alt="Nuvem de tópicos (dinâmica)",
            style={"width":"100%","height":"auto","display":"block"}
        ),
        html.Small("Nuvem de tópicos baseada na seleção atual", className="text-muted")
    ])

def responsive_axis(fig: go.Figure, labels=None, axis: str = "x"):
    n = 0; maxlen = 0
    if labels is not None:
        lab_list = list(map(str, labels))
        n = len(lab_list)
        maxlen = max((len(s) for s in lab_list), default=0)
    if n >= 12 or maxlen > 16:
        angle, size = -45, 10
    elif n >= 7 or maxlen > 12:
        angle, size = -25, 11
    else:
        angle, size = 0, 12
    if axis == "x":
        fig.update_xaxes(tickangle=angle, automargin=True, tickfont=dict(size=size))
    else:
        fig.update_yaxes(automargin=True, tickfont=dict(size=size))
    fig.update_layout(uniformtext_minsize=9, uniformtext_mode="hide")
    return fig

def create_fig_style(fig, title="", x="", y="", tickangle=None, showlegend=True):
    fig.update_layout(title=title, xaxis_title=x, yaxis_title=y,
                      showlegend=showlegend, hovermode="x unified")
    if tickangle is not None:
        fig.update_xaxes(tickangle=tickangle)
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    fig.update_traces(marker=dict(line=dict(color="#E5E7EB", width=1)), selector=dict(type="bar"))
    return fig

def _clean_series_for_counts(s: pd.Series) -> pd.Series:
    s = s.astype(str)
    s = s[s.str.strip().ne("") & ~s.str.strip().str.lower().isin({"nan","none","null"})]
    return s

def analyze_qtype(series: pd.Series) -> str:
    s = series.dropna().astype(str)
    if s.empty: return "empty"
    if pd.to_numeric(s, errors="coerce").notna().mean() > 0.8: return "numeric"
    if s.str.contains(r"[,;/|]").mean() > 0.3: return "multiple"
    if s.nunique() <= 20: return "categorical"
    return "text"

def parse_multi(ans: str) -> List[str]:
    if not isinstance(ans, str) or ans.strip()=="":
        return []
    return [t.strip() for t in re.split(r"[,;/|]", ans) if t.strip()]

def explode_multiple(sub: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in sub.iterrows():
        items = parse_multi(row["answer"])
        for it in items:
            r = row.copy()
            r["answer_item"] = it
            rows.append(r)
    return pd.DataFrame(rows)

def make_pv_answer(df_q: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    """
    Retorna df com a coluna __pv_answer__ pronta para uso como dimensão de pivot.
    - multiple: explode por separadores
    - numeric: binning em N faixas
    - text/categorical: usa string limpa (apenas se NÃO for o caso especial da Pivot para abertas)
    """
    out = df_q.copy()
    if out.empty or "answer" not in out.columns:
        out["__pv_answer__"] = pd.Series(dtype=str)
        return out

    qtype = analyze_qtype(out["answer"])

    if qtype == "multiple":
        out["__pv_answer__"] = out["answer"].astype(str).str.split(r"[,;/|]")
        out = out.explode("__pv_answer__")
        out["__pv_answer__"] = _clean_series_for_counts(out["__pv_answer__"])
        out = out[out["__pv_answer__"].notna() & out["__pv_answer__"].ne("")]

    elif qtype == "numeric":
        vals = pd.to_numeric(out["answer"], errors="coerce")
        bins = 10 if bins in [5, 10, 20] else 10
        out["__pv_answer__"] = pd.cut(vals, bins=bins)
        out = out.dropna(subset=["__pv_answer__"])

    else:
        out["__pv_answer__"] = _clean_series_for_counts(out["answer"])
        out = out[out["__pv_answer__"].notna() & out["__pv_answer__"].ne("")]

    return out

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

def empty_state(msg: str):
    return html.Div(
        [html.Div("ⓘ", style={"fontSize":"18px","marginRight":"6px"}), html.Span(msg)],
        className="muted-box"
    )

def _extract_click_label(clickData):
    if not clickData or "points" not in clickData or not clickData["points"]:
        return None
    p = clickData["points"][0]
    return p.get("label") or p.get("id") or p.get("text") or p.get("x")

def _apply_qfilter(sub: pd.DataFrame, qfilter: Dict[str, Optional[str]]) -> pd.DataFrame:
    qfilter = qfilter or {}
    if qfilter.get("category"):
        sub = sub[sub["category"].astype(str) == str(qfilter["category"])]
    if qfilter.get("topic"):
        sub = sub[sub["topic"].astype(str) == str(qfilter["topic"])]
    return sub

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
    fig = px.bar(df.head(50), x="topic", y="Qtde", text="%", title="Tópicos — Distribuição")
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
# 7) Criação do App Dash + CSS
# ==============================
import os

BASE_PATH = os.getenv("BASE_PATH", "/")
# normaliza: começa com "/" e termina com "/"
if not BASE_PATH.startswith("/"):
    BASE_PATH = "/" + BASE_PATH
if not BASE_PATH.endswith("/"):
    BASE_PATH = BASE_PATH + "/"

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    requests_pathname_prefix=BASE_PATH,
    routes_pathname_prefix=BASE_PATH,
)
server = app.server

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

  /* ===============================
     Paleta/variáveis – AI2C style
     =============================== */
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

  /* Base */
  *{box-sizing:border-box}
  body{
    background:var(--page-bg);
    color:var(--ink);
    font-family:'Poppins',system-ui,-apple-system,Segoe UI,Roboto,'Helvetica Neue',Arial,sans-serif;
  }

  /* Navbar/Tabs */
  .navbar { border-bottom:1px solid var(--line); background:var(--card-bg); }
  .nav-tabs .nav-link{
    border-radius:12px 12px 0 0;
    font-weight:600; color:var(--muted);
    border:none; padding:12px 24px;
  }
  .nav-tabs .nav-link.active{
    background:var(--card-bg); color:var(--ink);
    border-bottom:3px solid var(--brand);
  }
  .nav-tabs .nav-link:hover{ color:var(--ink) }

  /* Cards/KPIs (aplica nos seus painéis/containers) */
  .dash-card{
    background:var(--card-bg);
    border-radius:16px;
    border:1px solid var(--line);
    box-shadow:0 2px 10px rgba(0,0,0,.05);
    transition: box-shadow .2s ease, transform .05s ease;
  }
  .dash-card:hover{ box-shadow:0 4px 16px rgba(0,0,0,.08) }

  /* Controles (grid e botões com “pílula” laranja) */
  .ctrl-grid{
    display:grid; grid-template-columns:repeat(3,minmax(0,1fr));
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

  /* Badges e estados */
  .badge{ border-radius:999px; }
  .text-muted{ color:var(--muted)!important; }

  /* Empty state */
  .muted-box{
    display:flex; align-items:center; gap:6px;
    padding:16px; border:1px dashed var(--line);
    border-radius:12px; color:var(--muted); background:#FAFAFA;
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

# Healthcheck (útil para App Runner / ALB)
@server.get("/health")
def health():
    try:
        rows = int(len(df_main)) if isinstance(df_main, pd.DataFrame) else 0
    except Exception:
        rows = 0
    return {"status": "ok", "key": KEY, "cube": os.path.basename(os.getenv("CUBE_FILE", CUBE_FILE)), "rows": rows}, 200

# Navbar mínima (vazia por enquanto)
header = dbc.Navbar(
)

# === TABS ===
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
    dcc.Store(id="current-key"),   # <- carrega a KEY da URL
    tabs,
    html.Div(id="tab-content", className="mt-3"),
], fluid=True)

# ==============================
# 8) UI: Card por Pergunta
# ==============================
def question_card(qid: str, qdesc: str, allowed_cols: List[str]) -> dbc.Col:
    qtype = analyze_qtype(df_main[df_main["question_id"] == qid]["answer"]) if not df_main.empty else "empty"
    type_badge = {
        "numeric": ("🔢", "primary", "Numérica"),
        "categorical": ("📝", "success", "Categórica"),
        "multiple": ("☑️", "info", "Múltipla escolha"),
        "text": ("💬", "warning", "Campo aberto"),
        "empty": ("❌", "secondary", "Vazia")
    }.get(qtype, ("❓", "secondary", "Desconhecido"))

    seg_opts = [{"label": c, "value": c} for c in (allowed_cols or [])]

    controls = html.Div([
        html.Div(className="ctrl-grid", children=[
            html.Div([
                html.Label("Variáveis", className="fw-bold"),
                dcc.Dropdown(
                    id={"type":"q-segcol","qid":qid},
                    options=seg_opts, placeholder="Escolha coluna...", clearable=True
                ),
            ]),
            html.Div([
                html.Label("Valores (opcional)", className="fw-bold"),
                dcc.Dropdown(
                    id={"type":"q-segvals","qid":qid},
                    multi=True, placeholder="Todos os valores", clearable=True,
                    maxHeight=320, optionHeight=32
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
                        dbc.Badge(type_badge[0] + " " + type_badge[2], color=type_badge[1], className="me-2"),
                        html.Div(id={"type":"q-filterpill","qid":qid}, style={"display":"inline-block"}),
                    ], style={"display":"flex","alignItems":"center","gap":"8px"}),
                    html.P(qdesc or "", className="text-muted mb-0 mt-2", style={"fontSize":"0.9rem"}),
                ], style={"flex":"1"}),
            ]),
            dbc.CardBody([
                # estado local de filtro (categoria/tópico)
                dcc.Store(id={"type":"q-filter","qid":qid}, data={"category": None, "topic": None}),
                dcc.Store(id={"type":"q-drill","qid":qid}, data={"level": 0, "seg_value": None, "category": None}),

                # controles (collapse)
                html.Div([
                    dbc.Button("🔍 Filtros", id={"type":"q-collapse-btn","qid":qid},
                               color="light", size="sm", className="mb-3"),
                    dbc.Collapse(controls, id={"type":"q-collapse","qid":qid}, is_open=False),
                ]),

                # botão para limpar filtro local
                dbc.Button("🗑️ Limpar filtros", id={"type":"q-clear","qid":qid},
                           size="sm", color="secondary", outline=True,
                           className="mb-3", style={"display":"none"}),

                # gráfico principal da pergunta
                dcc.Loading(
                    dcc.Graph(id={"type":"q-fig","qid":qid}, config={"displayModeBar": False}),
                    type="dot"
                ),

                # extras (apenas para campo aberto)
                dcc.Graph(id={"type":"q-catfig","qid":qid}, config={"displayModeBar": False}, style={"marginTop":"12px"}),
                dcc.Graph(id={"type":"q-topicsfig","qid":qid}, config={"displayModeBar": False}, style={"marginTop":"12px"}),
                dcc.Graph(id={"type":"q-answers","qid":qid}, config={"displayModeBar": False}, style={"marginTop":"12px","display":"none"}),
            ])
        ], className="mb-4 dash-card"),
        md=6
    )

# ==============================
# 9) Pivot (Análises personalizadas)
# ==============================
def to_date_str(x):
    try:
        if x is None or (hasattr(pd, "isna") and pd.isna(x)):
            return None
        return pd.to_datetime(x, errors="coerce").date().isoformat()  # 'YYYY-MM-DD'
    except Exception:
        return None

def pivot_controls(df: pd.DataFrame, state: Dict):
    if df.empty:
        return empty_state("Sem dados para montar a pivot.")

    # 1. PREPARAÇÃO DAS VARIÁVEIS E OPÇÕES (FEITA APENAS UMA VEZ)
    numeric_cols = sorted([
        c for c in df.columns
        if c not in NON_SEGMENTABLE and not is_pii(c)
        and pd.to_numeric(df[c], errors="coerce").notna().mean() > 0.7
    ])

    dims_base = (state.get("ALLOWED_SEGMENT_COLS") or []) + ["sentiment", "category", "topic"]
    dims = sorted(list(set([c for c in dims_base if c not in numeric_cols])))

    dims_options = [{"label": c, "value": c} for c in dims] + [
        {"label": "Resposta (da pergunta selecionada)", "value": "__pv_answer__"}
    ]

    qdf = state.get("questions_df")
    if qdf is None or qdf.empty:
        qdf = pd.DataFrame(columns=["question_id","question_description"])

    def _label_for_row(r):
        qd = r.get("question_description")
        if pd.isna(qd):
            return str(r["question_id"])
        qd_str = str(qd).strip()
        if qd_str == "" or qd_str.lower() in {"nan","none","null"}:
            return str(r["question_id"])
        return qd_str[:120]

    q_opts = [
        {"label": _label_for_row(r), "value": str(r["question_id"])}
        for _, r in qdf.iterrows()
    ]
    
    # ✅ CORREÇÃO: Defina stats_local ANTES do return
    stats_local = state.get("stats", {})

    return dbc.Card([
        dbc.CardHeader(html.H5("🧭 Pivot (tabela dinâmica + gráfico)", className="mb-0")),
        dbc.CardBody([
            html.Div(className="ctrl-grid", children=[
                html.Div([
                    html.Label("Pergunta para explorar respostas (opcional)", className="fw-bold"),
                    dcc.Dropdown(id="pv-qid", options=q_opts, placeholder="Selecione a pergunta...")
                ]),
                html.Div([
                    html.Label("Usar respostas como dimensão", className="fw-bold"),
                    dcc.Checklist(id="pv-use-answer",
                                  options=[{"label": "Adicionar 'Resposta (da pergunta)' às dimensões", "value": "on"}],
                                  value=["on"],
                                  inputStyle={"marginRight":"6px"})
                ]),
                html.Div([
                    html.Label("Binning para respostas numéricas", className="fw-bold"),
                    dcc.RadioItems(id="pv-answer-binning",
                                   options=[{"label":"5 faixas","value":"5"},
                                            {"label":"10 faixas","value":"10"},
                                            {"label":"20 faixas","value":"20"}],
                                   value="10", inline=True)
                ]),
            ]),
            html.Div(className="ctrl-grid", children=[
                html.Div([
                    html.Label("Linhas (index)", className="fw-bold"),
                    dcc.Dropdown(id="pv-rows", options=dims_options, multi=True, placeholder="Escolha 1–2 dimensões…")
                ]),
                html.Div([
                    html.Label("Colunas (columns)", className="fw-bold"),
                    dcc.Dropdown(id="pv-cols", options=dims_options, multi=False, placeholder="(opcional)")
                ]),
                html.Div([
                    html.Label("Métrica", className="fw-bold"),
                    dcc.Dropdown(id="pv-metric",
                                 options=([{"label":"Contagem de respostas", "value":"__count__"}] +
                                          [{"label":c, "value":c} for c in numeric_cols]),
                                 value="__count__")
                ]),
            ]),
            html.Div(className="ctrl-grid", children=[
                html.Div([
                    html.Label("Agregação", className="fw-bold"),
                    dcc.RadioItems(id="pv-agg",
                                   options=[{"label":"Soma","value":"sum"},
                                            {"label":"Média","value":"mean"},
                                            {"label":"Mediana","value":"median"},
                                            {"label":"Mín","value":"min"},
                                            {"label":"Máx","value":"max"}],
                                   value="sum", inline=True)
                ]),
                html.Div([
                    html.Label("Tipo de gráfico", className="fw-bold"),
                    dcc.RadioItems(id="pv-chart",
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
            # bloco 4 (filtros dimensionais adicionais)
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
                html.Div(),  # filler
            ]),
            # saída
            dbc.Row([
                dbc.Col(dbc.Card([dbc.CardHeader("Tabela Dinâmica"),
                                  dbc.CardBody(id="pv-out-table")], className="dash-card"), md=5),
                dbc.Col(dbc.Card([dbc.CardHeader("Nuvem de tópicos (dinâmica)"),
                                  dbc.CardBody(id="pv-topics-cloud")], className="dash-card"), md=3),
                dbc.Col(dbc.Card([dbc.CardHeader("Gráfico (clique nas barras para ver respostas)"),
                                  dbc.CardBody(dcc.Loading(dcc.Graph(id="pv-out-chart-graph"), type="dot"))],
                                  className="dash-card"), md=4),
            ]),
            modal_drill
        ])
    ], className="mb-4 dash-card")

# ==============================
# 10) Callbacks — Pivot principal
# ==============================

from urllib.parse import parse_qs

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
    # (opcional) validar/precachear o DF
    try:
        _ = load_df_for_key(key)
    except Exception as e:
        print(f"[warn] falha ao carregar KEY={key}: {e}")
    return key




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
)
def update_pivot(rows, cols, metric, agg, chart, ds, de, pv_qid, pv_use_answer, pv_bins,
                 dim_filter_col, dim_filter_vals, key):
    key = key or os.getenv("KEY","")
    df = load_df_for_key(key) if key else pd.DataFrame()
    if df.empty:
        return empty_state("Sem dados."), go.Figure(), empty_state("Sem dados.")
    d = df.copy()

    if ds and de and "date_of_response" in d.columns:
        d = d[(d["date_of_response"] >= ds) & (d["date_of_response"] <= de)]

    rows = rows if isinstance(rows, list) else ([rows] if rows else [])
    # CORREÇÃO 1: A linha que normalizava 'cols' foi removida.
    # Agora 'cols' será uma string (ex: "sentiment") ou None.

    if not rows:
        return empty_state("Escolha ao menos 1 dimensão em Linhas."), go.Figure(), empty_state("Escolha ao menos 1 dimensão.")

    base_qtype = None
    if pv_qid:
        all_q = df[df["question_id"].astype(str) == str(pv_qid)]
        if not all_q.empty:
            base_qtype = analyze_qtype(all_q["answer"])

    wants_answer_dim = pv_use_answer and ("on" in (pv_use_answer or []))

    if pv_qid:
        d = d[d["question_id"].astype(str) == str(pv_qid)].copy()
        if d.empty:
            return empty_state("A pergunta selecionada não possui dados no período/recorte atual."), go.Figure(), empty_state("Sem dados para nuvem.")
        if wants_answer_dim and base_qtype != "text":
            try:
                bins = int(pv_bins) if str(pv_bins) in {"5", "10", "20"} else 10
            except Exception:
                bins = 10
            d = make_pv_answer(d, bins=bins)

    if dim_filter_col and dim_filter_vals and dim_filter_col in d.columns:
        chosen = dim_filter_vals if isinstance(dim_filter_vals, list) else [dim_filter_vals]
        d = d[d[dim_filter_col].astype(str).isin([str(v) for v in chosen])]

    if metric == "__count__":
        d["__count__"] = 1
        val, aggfunc = "__count__", "sum"
    else:
        d[metric] = pd.to_numeric(d[metric], errors="coerce")
        val, aggfunc = metric, (agg or "mean")

    if ("__pv_answer__" in rows or cols == "__pv_answer__") and "__pv_answer__" not in d.columns:
        return empty_state("Ative 'Usar respostas como dimensão' e selecione a pergunta."), go.Figure(), empty_state("Selecione a pergunta para a nuvem.")

    # CORREÇÃO 2: A chamada da pivot_table agora usa 'cols' diretamente.
    piv = pd.pivot_table(
        d, index=rows, columns=cols,
        values=val, aggfunc=aggfunc, fill_value=0, dropna=False
    )
    piv_disp = piv.reset_index()
    table = dbc.Table.from_dataframe(piv_disp.head(500), striped=True, bordered=False, hover=True, size="sm", responsive=True)

    fig = go.Figure()
    if chart == "bar":
        # A condicional 'if cols:' funciona perfeitamente com string ou None.
        if cols:
            # CORREÇÃO 3: O 'melt' e o 'px.bar' usam 'cols' diretamente.
            piv_m = piv.reset_index().melt(id_vars=rows, var_name=cols, value_name="value")
            x = rows[-1]
            fig = px.bar(piv_m, x=x, y="value", color=cols, barmode="group", title="Pivot — Barras")
            fig = create_fig_style(fig, x="Dimensão", y="Valor")
            fig = responsive_axis(fig, labels=piv_m[x].unique().tolist())
        else:
            piv_s = piv.reset_index()
            x = rows[-1]
            val_cols = [c for c in piv_s.columns if c not in rows]
            ycol = val_cols[0] if val_cols else None
            if ycol:
                fig = px.bar(piv_s, x=x, y=ycol, title="Pivot — Barras")
                fig = create_fig_style(fig, x="Dimensão", y="Valor")
                fig = responsive_axis(fig, labels=piv_s[x].unique().tolist())
            else:
                fig = go.Figure()
    else:
        if cols and len(rows) == 1:
            hm = piv.copy()
            # CORREÇÃO 4: O label do heatmap também usa 'cols' diretamente.
            fig = px.imshow(hm, labels=dict(x=cols, y=rows[0], color="Valor"), title="Pivot — Heatmap")
        else:
            fig = go.Figure()

    if pv_qid and base_qtype == "text":
        cloud_child = build_topics_wordcloud_component(d)
    else:
        cloud_child = empty_state("Disponível apenas para perguntas de texto livre.")

    return table, fig, cloud_child


# Popular coluna do filtro dimensional com base em Linhas/Colunas
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
    dims = list(dict.fromkeys(dims))  # remove duplicatas preservando ordem
    return [{"label": c, "value": c} for c in dims], None

# Popular valores possíveis da dimensão escolhida (respeita período, pergunta e __pv_answer__)

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
)
def sync_dim_filter_values(dim_col, pv_qid, pv_use_answer, pv_bins, ds, de, key):
    key = key or os.getenv("KEY","")
    df = load_df_for_key(key) if key else pd.DataFrame()

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
    prevent_initial_call=False
)
def render_tab(active, key):
    key = key or os.getenv("KEY", "")
    df = load_df_for_key(key) if key else pd.DataFrame()
    state = build_state(df)

    if df.empty:
        return html.Div("Nenhum dado disponível...", className="alert alert-warning")

    if active == "questions":
            cards = [
                # AJUSTE AQUI: O terceiro argumento agora vem de state.
                question_card(r["question_id"], r["question_description"], state["ALLOWED_SEGMENT_COLS"])
                for _, r in state["questions_df"].iterrows()
            ]
            return dbc.Row(cards) if cards else empty_state("Sem perguntas para exibir.")

    if active == "pivot":
            try:
                # AJUSTE CRÍTICO: Passe os argumentos 'df' e 'state' para a função.
                ui = pivot_controls(df, state)
                return html.Div([ui])
            except Exception as e:
                # É uma boa prática adicionar um traceback para depuração.
                import traceback
                print("[pivot_controls ERROR]", repr(e))
                traceback.print_exc()
                return html.Div(f"Erro ao montar Pivot: {e}", className="alert alert-danger")

    if active == "raw":
        cols_show = [c for c in df.columns if c not in {"orig_answer","survey_id"} and not is_pii(c)]
        if "respondent_id" in cols_show:
            cols_show = ["respondent_id"] + [c for c in cols_show if c != "respondent_id"]
        sample = df[cols_show].copy()
        return html.Div([
            html.H5(f"📋 Amostra sem PII (até 300 linhas de {len(df)} registros)"),
            dbc.Table.from_dataframe(sample.head(300), striped=True, bordered=True, hover=True, size="sm", responsive=True)
        ])

    return html.Div("Selecione uma aba.", className="text-muted")

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

)
def update_seg_values_per_q(seg_col, key):
    key = key or os.getenv("KEY","")
    df = load_df_for_key(key) if key else pd.DataFrame()

    if not seg_col or df.empty or seg_col not in df.columns:
        return [], None
    vals = sorted(df[seg_col].dropna().astype(str).unique().tolist())
    return [{"label": v, "value": v} for v in vals], None


# (corrigido) sincroniza filtro local do card (categoria/tópico)
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
    Input({"type":"q-fig","qid":MATCH}, "clickData"),      # clique no gráfico principal (sentimento)
    Input({"type":"q-catfig","qid":MATCH}, "clickData"),   # clique no gráfico de categoria
    Input({"type":"q-clear","qid":MATCH}, "n_clicks"),     # limpar
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

    # limpar tudo
    if prop.endswith(".n_clicks"):
        return {"level":0, "sentiment":None, "category":None}

    # clique no gráfico principal: SENTIMENTO
    if '"q-fig"' in prop and prop.endswith(".clickData"):
        label = _extract_click_label(main_click)
        if not label:
            return curr
        # toggle do mesmo sentimento volta ao nível 0
        if str(curr.get("sentiment")) == str(label) and (curr.get("level") or 0) >= 1:
            return {"level":0, "sentiment":None, "category":None}
        return {"level":1, "sentiment":str(label), "category":None}

    # clique no gráfico de CATEGORIA → desce para TÓPICO
    if '"q-catfig"' in prop and prop.endswith(".clickData"):
        label = _extract_click_label(cat_click)
        if not label:
            return curr
        # toggle da mesma categoria volta ao nível 1 (somente sentimento)
        if str(curr.get("category")) == str(label) and (curr.get("level") or 0) >= 2:
            return {"level":1, "sentiment":curr.get("sentiment"), "category":None}
        return {"level":2, "sentiment":curr.get("sentiment"), "category":str(label)}

    return curr

@dash.callback(
    Output({"type":"q-fig","qid":MATCH}, "figure"),
    Output({"type":"q-catfig","qid":MATCH}, "figure"),
    Output({"type":"q-topicsfig","qid":MATCH}, "figure"),
    Output({"type":"q-answers","qid":MATCH}, "figure"),
    Output({"type":"q-catfig","qid":MATCH}, "style"),
    Output({"type":"q-topicsfig","qid":MATCH}, "style"),
    Output({"type":"q-answers","qid":MATCH}, "style"),
    Output({"type":"q-clear","qid":MATCH}, "style"),
    Input({"type":"q-segcol","qid":MATCH}, "value"),
    Input({"type":"q-segvals","qid":MATCH}, "value"),
    Input({"type":"q-filter","qid":MATCH}, "data"),
    Input({"type":"q-drill","qid":MATCH}, "data"),
    State({"type":"q-fig","qid":MATCH}, "id"),
    Input("current-key","data"),
)
def update_question_graph(seg_col, seg_vals, qfilter, qdrill, fig_id, key):
    key = key or os.getenv("KEY","")
    df = load_df_for_key(key) if key else pd.DataFrame()
    qid = fig_id["qid"]
    sub_all = df[df["question_id"] == qid].copy()
    sub = sub_all.copy()
    if seg_col and seg_vals and seg_col in sub.columns:
        sub = sub[sub[seg_col].astype(str).isin([str(v) for v in seg_vals])]
    sub = _apply_qfilter(sub, qfilter)

    base_qtype = analyze_qtype(sub_all["answer"] if "answer" in sub_all.columns else pd.Series(dtype=str))

    # figuras de saída
    main_fig, cat_fig, topics_fig, answers_fig = go.Figure(), go.Figure(), go.Figure(), go.Figure()
    cat_has = topics_has = False
    style_show, style_hide = {"marginTop":"12px"}, {"display":"none"}

    # Likert (1–5) — contagem
    is_likert = str(qid) in LIKERT_1_5_IDS and base_qtype in {"numeric","categorical","text"}
    if is_likert:
        vals = pd.to_numeric(sub["answer"], errors="coerce").round().clip(1,5).astype("Int64")
        d = sub.assign(val=vals).dropna(subset=["val"])
        cat_order = [1,2,3,4,5]; labels_15 = [str(i) for i in cat_order]
        vc = d["val"].astype(int).value_counts().reindex(cat_order, fill_value=0)
        main_fig = px.bar(x=labels_15, y=vc.values, title="Distribuição (escala 1–5)")
        main_fig = create_fig_style(main_fig, x="Escala (1–5)", y="Qtde")
        main_fig.update_xaxes(tickmode="array", tickvals=labels_15, ticktext=labels_15)
        main_fig = responsive_axis(main_fig, labels_15)

        has_local_filter = bool(qfilter and (qfilter.get("category") or qfilter.get("topic")))
        clear_style = {"display":"inline-block","marginBottom":"12px"} if has_local_filter else {"display":"none"}
        return (main_fig, go.Figure(), go.Figure(), go.Figure(),
                style_hide, style_hide, style_hide, clear_style)

    # Não-texto — sempre contagem
    if base_qtype == "numeric":
        vals = pd.to_numeric(sub["answer"], errors="coerce")
        main_fig = px.histogram(vals.dropna(), nbins=20, title="Distribuição")
        main_fig = create_fig_style(main_fig, x="Valor", y="Frequência")

    elif base_qtype == "multiple":
        exploded = explode_multiple(sub)
        if not exploded.empty:
            exploded["answer_item"] = _clean_series_for_counts(exploded["answer_item"])
            exploded = exploded[exploded["answer_item"].notna() & exploded["answer_item"].ne("")]
            vc = exploded["answer_item"].value_counts().head(20)
            main_fig = px.bar(x=vc.index, y=vc.values, title="Ocorrências por opção")
            main_fig = responsive_axis(main_fig, labels=list(vc.index))
        main_fig = create_fig_style(main_fig, x="Opção", y="Qtde")

    elif base_qtype == "categorical":
        s = _clean_series_for_counts(sub["answer"])
        if not s.empty:
            vc = s.value_counts().head(20)
            main_fig = px.bar(x=vc.index, y=vc.values, title="Ocorrências por opção")
            main_fig = responsive_axis(main_fig, labels=list(vc.index))
        main_fig = create_fig_style(main_fig, x="Opção", y="Qtde")

    # Texto — Drill: Sentimento → Categoria → Tópico
    elif base_qtype == "text":
        qdrill = (qdrill or {"level":0,"sentiment":None,"category":None})
        level = int(qdrill.get("level") or 0)
        sent_clicked = qdrill.get("sentiment")
        cat_clicked  = qdrill.get("category")

        # Sentimento (cores fixas)
        if "sentiment" in sub.columns:
            s_norm = sub["sentiment"].astype(str).str.lower().map(SENTIMENT_MAP).fillna(sub["sentiment"])
            vc = s_norm.value_counts().reindex(SENTIMENT_ORDER, fill_value=0)
            df_sent = pd.DataFrame({"sentiment": vc.index, "count": vc.values})
            main_fig = px.bar(
                df_sent, x="sentiment", y="count",
                color="sentiment",
                category_orders={"sentiment": SENTIMENT_ORDER},
                color_discrete_map=SENTIMENT_COLORS,
                title="Sentimento"
            )
            main_fig = create_fig_style(main_fig, x="Sentimento", y="Qtde")
            main_fig = responsive_axis(main_fig, labels=SENTIMENT_ORDER)

        # Categorias (após clicar em sentimento)
        if level >= 1 and sent_clicked:
            d_cat = sub.copy()
            d_cat["__sent__"] = d_cat["sentiment"].astype(str).str.lower().map(SENTIMENT_MAP).fillna(d_cat["sentiment"])
            d_cat = d_cat[d_cat["__sent__"].astype(str) == str(sent_clicked)]
            if "category" in d_cat.columns:
                sc = _clean_series_for_counts(d_cat["category"])
                if not sc.empty:
                    vc = sc.value_counts().head(60)
                    cat_fig = px.bar(x=vc.index, y=vc.values, title=f"Categorias — {sent_clicked}")
                    cat_fig = create_fig_style(cat_fig, x="Categoria", y="Qtde")
                    cat_fig = responsive_axis(cat_fig, labels=list(vc.index))
                    cat_has = True

        # Tópicos (após clicar em categoria) — nunca respostas finais
        if level >= 2 and sent_clicked and cat_clicked:
            d_top = sub.copy()
            d_top["__sent__"] = d_top["sentiment"].astype(str).str.lower().map(SENTIMENT_MAP).fillna(d_top["sentiment"])
            d_top = d_top[
                (d_top["__sent__"].astype(str) == str(sent_clicked)) &
                (d_top["category"].astype(str) == str(cat_clicked))
            ]
            if "topic" in d_top.columns:
                st = _clean_series_for_counts(d_top["topic"])
                if not st.empty:
                    vc = st.value_counts().head(100)
                    topics_fig = px.bar(x=vc.index, y=vc.values, title=f"Tópicos — {cat_clicked}")
                    topics_fig = create_fig_style(topics_fig, x="Tópico", y="Qtde")
                    topics_fig = responsive_axis(topics_fig, labels=list(vc.index))
                    topics_has = True

        answers_fig = go.Figure()  # nunca mostramos respostas finais em abertas

    # visibilidade do botão "Limpar"
    has_local_filter = bool(qfilter and (qfilter.get("category") or qfilter.get("topic")))
    has_drill = bool(base_qtype == "text" and (qdrill or {}).get("level", 0) > 0)
    clear_style = {"display":"inline-block","marginBottom":"12px"} if (has_local_filter or has_drill) else {"display":"none"}

    return (
        main_fig,
        cat_fig, topics_fig, answers_fig,
        (style_show if (base_qtype == "text" and cat_has) else style_hide),
        (style_show if (base_qtype == "text" and topics_has) else style_hide),
        style_hide,  # respostas finais sempre ocultas
        clear_style
    )

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

    prevent_initial_call=True
)
def pivot_drill(clickData, rows, cols, pv_qid, pv_use_answer, pv_bins, ds, de, key):
    key = key or os.getenv("KEY","")
    df = load_df_for_key(key) if key else pd.DataFrame()
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
        # para abertas, dimensões já são categoria/tópico

    rows = rows if isinstance(rows, list) else ([rows] if rows else [])
    cols = cols if isinstance(cols, list) else ([cols] if cols else [])

    pt = clickData["points"][0]
    custom = pt.get("customdata") or []
    xval = custom[0] if len(custom) >= 1 else pt.get("x")
    cval = custom[1] if len(custom) >= 2 else None

    # aplica filtros conforme dimensões selecionadas
    if rows:
        dimx = rows[-1]
        if dimx in d.columns:
            d = d[d[dimx].astype(str) == str(xval)]
    if cols:
        dimc = cols[0]
        if dimc in d.columns and cval is not None:
            d = d[d[dimc].astype(str) == str(cval)]

    # prepara tabela de respostas
    title = QDESC_MAP.get(str(pv_qid), "Respostas") if pv_qid else "Respostas"
    if d.empty:
        return True, f"Respostas — {title}", html.Div("Nenhum registro para este ponto.", className="text-muted")

    show_cols = ["date_of_response","category","topic","sentiment","answer"]
    show_cols = [c for c in show_cols if c in d.columns]
    tbl = d[show_cols].copy().sort_values("date_of_response", na_position="last")
    if "date_of_response" in tbl.columns:
        tbl["date_of_response"] = pd.to_datetime(tbl["date_of_response"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")

    table = dbc.Table.from_dataframe(tbl.head(1000), striped=True, bordered=False, hover=True, size="sm", responsive=True)
    return True, f"Respostas — {title}", table

# ==============================
# 14) Export (opcional)
# ==============================
def export_html(path=None):
    path = path or f"report_{KEY}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    from plotly.io import to_html
    charts_html = []
    sent_fig = sentiment_timeline(df_main, "W")
    if sent_fig:
        charts_html.append(to_html(sent_fig, include_plotlyjs="cdn", full_html=False))

    html_content = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Relatório — {KEY}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
  <style>body{{font-family:'Inter',system-ui,-apple-system,Segoe UI,Roboto,'Helvetica Neue',Arial;}}</style>
</head>
<body>
  <h1 style="margin:8px 0">Relatório de Análise</h1>
  <div>Fonte: {os.path.basename(CUBE_FILE)} — Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</div>
  <hr/>
  {''.join(charts_html)}
</body></html>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[OK] Exportado: {path}")

# ==============================
# 15) Run
# ==============================
if __name__ == "__main__":
    if EXPORT_HTML:
        export_html()
    else:
        # Bind 0.0.0.0 e porta do env/arg
        print(f"[RUN] Starting Dash on 0.0.0.0:{PORT} | KEY={KEY} | CUBE_FILE={CUBE_FILE}")
        app.run(debug=False, host="0.0.0.0", port=PORT)
