"""Engenharia de features para os modelos de ML a partir de `gold.feature_store_ml`.

O conjunto de preditoras é o MESMO para prever `iqa` ou `od_mg_l` (inclui os
lags de ambas as variáveis, não só do alvo) — IQA e OD são fortemente
correlacionados na fonte simulada, então usar os lags de uma para ajudar a
prever a outra é uma escolha deliberada, e mantém a mesma linha de entrada
utilizável para os dois modelos em `predict_iqa.prever_iqa`.
"""
from __future__ import annotations

import pandas as pd

PREDITORA_CATEGORICA = "trecho_id"

PREDITORAS_NUMERICAS = [
    "mes",
    "vazao_m3s_medio",
    "chuva_mm_media",
    "iqa_lag1m",
    "iqa_lag3m",
    "iqa_lag12m",
    "iqa_media_movel_12m",
    "od_mg_l_lag1m",
    "od_mg_l_lag3m",
    "od_mg_l_lag12m",
    "od_mg_l_media_movel_12m",
]

TODAS_PREDITORAS = [PREDITORA_CATEGORICA, *PREDITORAS_NUMERICAS]


def montar_matriz_features(gold_df: pd.DataFrame, alvo: str) -> tuple[pd.DataFrame, pd.Series]:
    """Separa (X, y) para treino de um modelo que prevê a coluna `alvo` (ex.: 'od_mg_l')."""
    colunas_necessarias = [*TODAS_PREDITORAS, alvo]
    completo = gold_df.dropna(subset=colunas_necessarias)
    return completo[TODAS_PREDITORAS], completo[alvo]
