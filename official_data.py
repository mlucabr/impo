from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd
import requests
import streamlit as st

TEC_URL = "https://www.gov.br/mdic/pt-br/assuntos/camex/estrategia-comercial/arquivos-listas/anexos-i-a-ix-resolucao-gecex-272-21-8.xlsx"
TIPI_URL = "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/legislacao/documentos-e-arquivos/tipi.xlsx"
NCM_JSON_URL = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"


@dataclass
class OfficialTaxRates:
    ncm: str
    description: str | None
    ii_rate: float | None
    ipi_rate: float | None
    source_ii: str
    source_ipi: str
    source_ncm: str


def normalize_ncm(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(8)[:8]


def _download_bytes(url: str, timeout: int = 60) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ImportAssistant/2.0)"}
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.content


def _detect_header_row(raw: pd.DataFrame, max_rows: int = 50) -> int:
    for idx in range(min(max_rows, len(raw))):
        row_text = " | ".join([str(v).strip().upper() for v in raw.iloc[idx].tolist() if pd.notna(v)])
        if "NCM" in row_text and ("ALÍQUOTA" in row_text or "ALIQ" in row_text or "%" in row_text):
            return idx
    return 0


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def load_tec_dataframe() -> pd.DataFrame:
    content = _download_bytes(TEC_URL)
    xls = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")

    target_sheet = None
    for sheet in xls.sheet_names:
        up = str(sheet).upper()
        if "ANEXO I" in up or ("TEC" in up and "ANEXO" in up):
            target_sheet = sheet
            break
    target_sheet = target_sheet or xls.sheet_names[0]

    raw = pd.read_excel(io.BytesIO(content), sheet_name=target_sheet, engine="openpyxl", header=None)
    header_row = _detect_header_row(raw)
    df = pd.read_excel(io.BytesIO(content), sheet_name=target_sheet, engine="openpyxl", header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    ncm_col = next((c for c in df.columns if str(c).strip().upper() == "NCM"), None)
    ncm_col = ncm_col or next((c for c in df.columns if "NCM" in str(c).upper()), None)
    rate_col = next((c for c in df.columns if "ALÍQUOTA" in str(c).upper() or "ALIQ" in str(c).upper()), None)
    rate_col = rate_col or next((c for c in df.columns if "%" in str(c)), None)

    if ncm_col is None or rate_col is None:
        raise ValueError("Não foi possível localizar as colunas de NCM/Alíquota na planilha TEC oficial.")

    out = df[[ncm_col, rate_col]].copy()
    out.columns = ["NCM", "ALIQ_II"]
    out["NCM"] = out["NCM"].apply(normalize_ncm)
    out["ALIQ_II"] = pd.to_numeric(out["ALIQ_II"], errors="coerce")
    out = out.dropna(subset=["ALIQ_II"]).drop_duplicates(subset=["NCM"], keep="first").reset_index(drop=True)
    return out


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def load_tipi_dataframe() -> pd.DataFrame:
    content = _download_bytes(TIPI_URL)
    xls = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")

    target_sheet = None
    for sheet in xls.sheet_names:
        up = str(sheet).upper()
        if "TIPI" in up:
            target_sheet = sheet
            break
    target_sheet = target_sheet or xls.sheet_names[0]

    raw = pd.read_excel(io.BytesIO(content), sheet_name=target_sheet, engine="openpyxl", header=None)
    header_row = _detect_header_row(raw)
    df = pd.read_excel(io.BytesIO(content), sheet_name=target_sheet, engine="openpyxl", header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    ncm_col = next((c for c in df.columns if str(c).strip().upper() == "NCM"), None)
    ncm_col = ncm_col or next((c for c in df.columns if "NCM" in str(c).upper()), None)
    rate_col = next((c for c in df.columns if "ALÍQUOTA" in str(c).upper() or "ALIQ" in str(c).upper()), None)
    rate_col = rate_col or next((c for c in df.columns if "%" in str(c)), None)

    if ncm_col is None or rate_col is None:
        raise ValueError("Não foi possível localizar as colunas de NCM/Alíquota na planilha TIPI oficial.")

    out = df[[ncm_col, rate_col]].copy()
    out.columns = ["NCM", "ALIQ_IPI"]
    out["NCM"] = out["NCM"].apply(normalize_ncm)
    out["ALIQ_IPI"] = out["ALIQ_IPI"].astype(str).str.replace("%", "", regex=False).str.replace(",", ".", regex=False)
    out["ALIQ_IPI"] = pd.to_numeric(out["ALIQ_IPI"], errors="coerce")
    out = out.dropna(subset=["ALIQ_IPI"]).drop_duplicates(subset=["NCM"], keep="first").reset_index(drop=True)
    return out


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def load_ncm_catalog() -> pd.DataFrame:
    content = _download_bytes(NCM_JSON_URL)
    df = pd.read_json(io.BytesIO(content))
    cols = {c.lower(): c for c in df.columns}

    code_col = None
    for cand in ["codigo", "codigoncm", "ncm", "code"]:
        if cand in cols:
            code_col = cols[cand]
            break
    code_col = code_col or df.columns[0]

    desc_col = None
    for cand in ["descricao", "descricaocompleta", "descricaoformatada", "description"]:
        if cand in cols:
            desc_col = cols[cand]
            break
    desc_col = desc_col or (df.columns[1] if len(df.columns) > 1 else df.columns[0])

    out = df[[code_col, desc_col]].copy()
    out.columns = ["NCM", "DESCRICAO"]
    out["NCM"] = out["NCM"].apply(normalize_ncm)
    out["DESCRICAO"] = out["DESCRICAO"].astype(str)
    out = out.drop_duplicates(subset=["NCM"], keep="first")
    return out


def get_official_rates(ncm: str) -> OfficialTaxRates:
    n = normalize_ncm(ncm)
    tec = load_tec_dataframe()
    tipi = load_tipi_dataframe()
    ncm_catalog = load_ncm_catalog()

    ii_row = tec.loc[tec["NCM"] == n]
    ipi_row = tipi.loc[tipi["NCM"] == n]
    desc_row = ncm_catalog.loc[ncm_catalog["NCM"] == n]

    ii_rate = float(ii_row.iloc[0]["ALIQ_II"]) if not ii_row.empty else None
    ipi_rate = float(ipi_row.iloc[0]["ALIQ_IPI"]) if not ipi_row.empty else None
    description = str(desc_row.iloc[0]["DESCRICAO"]) if not desc_row.empty else None

    return OfficialTaxRates(
        ncm=n,
        description=description,
        ii_rate=ii_rate,
        ipi_rate=ipi_rate,
        source_ii=TEC_URL,
        source_ipi=TIPI_URL,
        source_ncm=NCM_JSON_URL,
    )
