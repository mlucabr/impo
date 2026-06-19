from __future__ import annotations

from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
ICMS_CSV = BASE_DIR / "data_icms_uf.csv"
PORT_CSV = BASE_DIR / "data_port_defaults.csv"


def load_icms_defaults() -> pd.DataFrame:
    df = pd.read_csv(ICMS_CSV)
    df.columns = [c.strip() for c in df.columns]
    df["UF"] = df["UF"].astype(str).str.upper().str.strip()
    df["ICMS_IMPORTACAO_PCT"] = pd.to_numeric(df["ICMS_IMPORTACAO_PCT"], errors="coerce").fillna(17.0)
    df["OBS"] = df.get("OBS", "").astype(str)
    return df


def load_port_defaults() -> pd.DataFrame:
    df = pd.read_csv(PORT_CSV)
    df.columns = [c.strip() for c in df.columns]
    df["PORTO_CODIGO"] = df["PORTO_CODIGO"].astype(str).str.upper().str.strip()
    numeric_cols = [
        "CUSTO_PORTUARIO_BASE_BRL",
        "DESEMBARACO_BASE_BRL",
        "FRETE_PORTO_PLANTA_BASE_BRL",
        "SEGURO_NACIONAL_ADVAL_PCT",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["OBS"] = df.get("OBS", "").astype(str)
    return df


def get_icms_rate_by_uf(uf: str, icms_df: pd.DataFrame) -> float:
    uf = str(uf or "").upper().strip()
    row = icms_df.loc[icms_df["UF"] == uf]
    if row.empty:
        return 17.0
    return float(row.iloc[0]["ICMS_IMPORTACAO_PCT"])


def get_port_defaults(port_code: str, port_df: pd.DataFrame) -> dict:
    code = str(port_code or "").upper().strip()
    row = port_df.loc[port_df["PORTO_CODIGO"] == code]
    if row.empty:
        return {
            "CUSTO_PORTUARIO_BASE_BRL": 0.0,
            "DESEMBARACO_BASE_BRL": 0.0,
            "FRETE_PORTO_PLANTA_BASE_BRL": 0.0,
            "SEGURO_NACIONAL_ADVAL_PCT": 0.0,
            "OBS": "Porto sem premissas pré-cadastradas.",
        }
    item = row.iloc[0]
    return {
        "CUSTO_PORTUARIO_BASE_BRL": float(item["CUSTO_PORTUARIO_BASE_BRL"]),
        "DESEMBARACO_BASE_BRL": float(item["DESEMBARACO_BASE_BRL"]),
        "FRETE_PORTO_PLANTA_BASE_BRL": float(item["FRETE_PORTO_PLANTA_BASE_BRL"]),
        "SEGURO_NACIONAL_ADVAL_PCT": float(item["SEGURO_NACIONAL_ADVAL_PCT"]),
        "OBS": str(item.get("OBS", "")),
    }
