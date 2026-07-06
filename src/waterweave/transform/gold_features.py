"""Camada Gold: agregações finais consumidas por ML, ABM e dashboard.

Tabelas produzidas:
  - `gold.serie_temporal_trecho_mes`: uma linha por (trecho, mês) com vazão e
    chuva médias entre todos os postos do trecho, mais os indicadores de
    qualidade da água do ano correspondente (a série de qualidade é anual,
    então é repetida em todos os meses daquele ano — granularidade real,
    não inventada). É a tabela que o dashboard consome diretamente.
  - `gold.feature_store_ml`: mesma granularidade, com lags e média móvel de
    IQA/OD para os modelos de ML.
  - `gold.estado_inicial_abm`: snapshot mais recente por trecho, usado para
    inicializar o `Model` do Mesa a cada rodada de simulação.
"""
from __future__ import annotations

import pandas as pd

from waterweave.config import GOLD_DIR, SILVER_DIR, TRECHOS
from waterweave.io_delta import read_table, write_table

LAGS_MESES = (1, 3, 12)


def build_serie_temporal_trecho_mes() -> pd.DataFrame:
    """Junta vazão + chuva (agregadas por trecho/mês) com qualidade da água (anual, repetida por mês)."""
    vazao = read_table(SILVER_DIR / "vazao_mensal")
    chuva = read_table(SILVER_DIR / "chuva_mensal")
    qualidade = read_table(SILVER_DIR / "qualidade")

    vazao_trecho = vazao.groupby(["trecho_id", "ano", "mes"], as_index=False).agg(
        vazao_m3s_medio=("vazao_m3s", "mean"), n_postos_vazao=("codigo_posto", "nunique")
    )
    chuva_trecho = chuva.groupby(["trecho_id", "ano", "mes"], as_index=False).agg(
        chuva_mm_media=("altura_mm", "mean"), n_postos_chuva=("codigo_posto", "nunique")
    )

    serie = pd.merge(vazao_trecho, chuva_trecho, on=["trecho_id", "ano", "mes"], how="outer")
    serie = serie.merge(qualidade, on=["trecho_id", "ano"], how="left", suffixes=("", "_qualidade"))
    serie["mes_data"] = pd.to_datetime(dict(year=serie["ano"], month=serie["mes"], day=1))
    return serie.sort_values(["trecho_id", "mes_data"]).reset_index(drop=True)


def build_feature_store_ml(serie: pd.DataFrame) -> pd.DataFrame:
    """Deriva lags e média móvel de IQA/OD a partir de `serie_temporal_trecho_mes`, por trecho."""
    tabela = serie.sort_values(["trecho_id", "mes_data"]).copy()
    for coluna in ("iqa", "od_mg_l"):
        grupo = tabela.groupby("trecho_id")[coluna]
        for lag in LAGS_MESES:
            tabela[f"{coluna}_lag{lag}m"] = grupo.shift(lag)
        tabela[f"{coluna}_media_movel_12m"] = grupo.transform(lambda s: s.rolling(12, min_periods=3).mean())
    return tabela


def build_estado_inicial_abm(serie: pd.DataFrame) -> pd.DataFrame:
    """Snapshot mais recente (com qualidade da água disponível) por trecho, para inicializar o ABM."""
    valido = serie.dropna(subset=["iqa"]).sort_values("mes_data")
    ultimo_por_trecho = valido.groupby("trecho_id", as_index=False).tail(1)
    return ultimo_por_trecho.reset_index(drop=True)


def run() -> dict[str, pd.DataFrame]:
    """Constrói e grava as três tabelas Gold, nessa ordem de dependência."""
    serie = build_serie_temporal_trecho_mes()
    write_table(GOLD_DIR / "serie_temporal_trecho_mes", serie, partition_by=["trecho_id"])

    features = build_feature_store_ml(serie)
    write_table(GOLD_DIR / "feature_store_ml", features, partition_by=["trecho_id"])

    estado_inicial = build_estado_inicial_abm(serie)
    write_table(GOLD_DIR / "estado_inicial_abm", estado_inicial)

    return {"serie_temporal_trecho_mes": serie, "feature_store_ml": features, "estado_inicial_abm": estado_inicial}


if __name__ == "__main__":
    run()
