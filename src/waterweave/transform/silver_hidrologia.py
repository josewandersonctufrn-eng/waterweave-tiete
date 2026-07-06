"""Silver de hidrologia: regulariza vazão + chuva Bronze para série mensal por posto.

Produz DUAS tabelas Silver (`vazao_mensal`, `chuva_mensal`), não uma única
tabela unificada — os postos fluviométricos e pluviométricos são redes
físicas diferentes (não a mesma estação medindo as duas grandezas), então
forçar um join por posto criaria uma correspondência falsa. A junção
legítima entre as duas só acontece na Gold, agregada por trecho/mês.

Responsabilidades:
  - Regularizar medições de vazão (eventos irregulares, e também arquivos
    já mensais do formato "consolidado") para média mensal por posto.
  - Converter latitude/longitude de GMS para decimal quando a linha não já
    trouxer coordenada decimal (formato "consolidado").
  - Descartar duplicidade entre arquivos que reemitem o mesmo período para
    o mesmo posto, fazendo média em vez de escolher arbitrariamente um.
"""
from __future__ import annotations

import re

import pandas as pd

from waterweave.config import BRONZE_DIR, SILVER_DIR
from waterweave.io_delta import read_table, write_table

_GMS_RE = re.compile(r"(\d+)G(\d+)M(\d+)S")


def gms_para_decimal(valor_gms: str | None) -> float | None:
    """Converte string 'GMS' (ex.: '23G31M35S') para grau decimal.

    Assume hemisfério sul/oeste (todo o projeto está no estado de SP,
    Brasil), por isso o resultado é sempre negativo.
    """
    if not isinstance(valor_gms, str):
        return None
    m = _GMS_RE.search(valor_gms)
    if not m:
        return None
    graus, minutos, segundos = (float(x) for x in m.groups())
    return -(graus + minutos / 60 + segundos / 3600)


def _completar_coordenadas_decimais(df: pd.DataFrame) -> pd.DataFrame:
    """Preenche `latitude`/`longitude` a partir de `latitude_gms`/`longitude_gms` onde faltar."""
    df = df.copy()
    if "latitude" not in df.columns:
        df["latitude"] = pd.NA
    if "longitude" not in df.columns:
        df["longitude"] = pd.NA
    if "latitude_gms" in df.columns:
        faltantes = df["latitude"].isna()
        df.loc[faltantes, "latitude"] = df.loc[faltantes, "latitude_gms"].apply(gms_para_decimal)
    if "longitude_gms" in df.columns:
        faltantes = df["longitude"].isna()
        df.loc[faltantes, "longitude"] = df.loc[faltantes, "longitude_gms"].apply(gms_para_decimal)
    return df


def regularizar_vazao_mensal(bronze_vazao: pd.DataFrame) -> pd.DataFrame:
    """Agrega medições (irregulares ou já mensais) de vazão para médias mensais por posto."""
    df = _completar_coordenadas_decimais(bronze_vazao)
    df["ano"] = df["data"].dt.year
    df["mes"] = df["data"].dt.month
    return df.groupby(["trecho_id", "codigo_posto", "ano", "mes"], as_index=False).agg(
        vazao_m3s=("vazao_m3s", "mean"),
        n_medicoes=("vazao_m3s", "size"),
        latitude=("latitude", "first"),
        longitude=("longitude", "first"),
        fonte_tipo=("_fonte_tipo", "first"),
    )


def regularizar_chuva_mensal(bronze_chuva: pd.DataFrame) -> pd.DataFrame:
    """Agrega leituras mensais de chuva por posto, fazendo média entre arquivos que reemitem o mesmo período."""
    df = _completar_coordenadas_decimais(bronze_chuva)
    return df.groupby(["trecho_id", "codigo_posto", "ano", "mes"], as_index=False).agg(
        altura_mm=("altura_mm", "mean"),
        latitude=("latitude", "first"),
        longitude=("longitude", "first"),
        fonte_tipo=("_fonte_tipo", "first"),
    )


def build_silver_hidrologia() -> dict[str, pd.DataFrame]:
    """Constrói e grava as tabelas Silver de vazão mensal e chuva mensal a partir da Bronze."""
    vazao = regularizar_vazao_mensal(read_table(BRONZE_DIR / "fluviometria"))
    chuva = regularizar_chuva_mensal(read_table(BRONZE_DIR / "pluviometria"))
    write_table(SILVER_DIR / "vazao_mensal", vazao, partition_by=["trecho_id"])
    write_table(SILVER_DIR / "chuva_mensal", chuva, partition_by=["trecho_id"])
    return {"vazao_mensal": vazao, "chuva_mensal": chuva}


if __name__ == "__main__":
    build_silver_hidrologia()
