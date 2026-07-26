"""Engenharia de features para os modelos de ML.

O conjunto de preditoras é o MESMO para prever `iqa` ou `od_mg_l` (inclui os
lags de ambas as variáveis, não só do alvo) — IQA e OD são fortemente
correlacionados (0,96 Pearson na série real, ver relatório de EDA), então
usar os lags de uma para ajudar a prever a outra é uma escolha deliberada, e
mantém a mesma linha de entrada utilizável para os dois modelos em
`predict_iqa.prever_iqa`.

Duas granularidades, DUAS matrizes de features:
  - `PREDITORAS_NUMERICAS` / `montar_matriz_features` — MENSAL, a partir de
    `gold.feature_store_ml`. MANTIDA por compatibilidade, mas não é mais a
    usada para treino (ver ACHADO DE AUDITORIA DE ML em
    `transform.gold_features`): como iqa/od_mg_l são repetidos nos 12 meses
    do ano na fonte mensal, `iqa_lag1m` é quase sempre igual ao próprio alvo.
  - `PREDITORAS_NUMERICAS_ANUAL` / `montar_matriz_features_anual` — ANUAL, a
    partir de `gold.feature_store_ml_anual`. Sem repetição — é a que
    `models.ml.train` e `models.ml.shap_analysis` usam hoje.
"""
from __future__ import annotations

import pandas as pd

PREDITORA_CATEGORICA = "trecho_id"

# --- Granularidade mensal (legado — ver docstring do módulo) ---------------
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
    """Separa (X, y) em granularidade MENSAL — legado, ver docstring do módulo."""
    colunas_necessarias = [*TODAS_PREDITORAS, alvo]
    completo = gold_df.dropna(subset=colunas_necessarias)
    return completo[TODAS_PREDITORAS], completo[alvo]


# --- Granularidade anual (atual — corrige o vazamento do lag mensal) -------
# "ano" entra como preditora numérica direta: as tendências de Mann-Kendall
# (ver relatório analítico) mostram queda estatisticamente significativa de
# IQA/OD nos 3 trechos, então o ano-calendário carrega sinal real de
# tendência secular. Ressalva: RandomForest não extrapola além do range de
# "ano" visto no treino — para anos futuros muito além de ANO_CORTE_TESTE, o
# modelo tende a saturar no valor do ano-limite treinado, não a projetar a
# tendência linearmente. Ver módulo `models.ml.predict_iqa` para como isso é
# tratado na previsão recursiva.
PREDITORAS_NUMERICAS_ANUAL = [
    "ano",
    "vazao_m3s_medio",
    "chuva_mm_media",
    "iqa_lag1a",
    "iqa_lag2a",
    "iqa_lag3a",
    "iqa_media_movel_5a",
    "od_mg_l_lag1a",
    "od_mg_l_lag2a",
    "od_mg_l_lag3a",
    "od_mg_l_media_movel_5a",
]

TODAS_PREDITORAS_ANUAL = [PREDITORA_CATEGORICA, *PREDITORAS_NUMERICAS_ANUAL]


def montar_matriz_features_anual(gold_df: pd.DataFrame, alvo: str) -> tuple[pd.DataFrame, pd.Series]:
    """Separa (X, y) em granularidade ANUAL — uma linha por (trecho, ano), sem repetição
    mensal do valor anual. Fonte de treino atual dos modelos (ver `models.ml.train`)."""
    colunas_necessarias = [*TODAS_PREDITORAS_ANUAL, alvo]
    completo = gold_df.dropna(subset=colunas_necessarias)
    return completo[TODAS_PREDITORAS_ANUAL], completo[alvo]


def montar_matriz_features_anual_por_trecho(gold_df: pd.DataFrame, alvo: str, trecho_id: str) -> tuple[pd.DataFrame, pd.Series]:
    """Mesma matriz anual, mas filtrada a UM trecho e sem a coluna categórica `trecho_id`
    (redundante quando o modelo já é específico de um trecho).

    ACHADO DE AUDITORIA DE ML (2026-07, item 2 — generalização espacial): o teste de
    generalização cruzada entre trechos (Seção 23 do relatório de EDA) mostrou R² negativo
    em TODA transferência Alto↔Médio↔Baixo Tietê — um único modelo com `trecho_id` como
    feature categórica está tentando aprender uma relação que muda de patamar/inclinação
    entre trechos. Modelos separados por trecho (`models.ml.train`) evitam essa mistura."""
    colunas_necessarias = [*PREDITORAS_NUMERICAS_ANUAL, alvo]
    subconjunto = gold_df[gold_df["trecho_id"] == trecho_id]
    completo = subconjunto.dropna(subset=colunas_necessarias)
    return completo[PREDITORAS_NUMERICAS_ANUAL], completo[alvo]
