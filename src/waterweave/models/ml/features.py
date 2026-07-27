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

ACHADO DE AUDITORIA DE ML (item 5 — qualidade desigual de vazão entre
trechos): o relatório de análise hidrológica avançada mostrou que a série de
vazão do Baixo Tietê tem inconsistência estrutural (curva de dupla massa com
quebra abrupta ~1980; razão Q5/Q95 de 3.473x na curva de permanência, contra
115-212x nos outros trechos) — sintoma de mistura de postos com escala
diferente ao longo do tempo, não um regime hidrológico real. Usar
`vazao_m3s_medio` como preditora nesse trecho arrisca injetar ruído
estrutural, não sinal. `TRECHOS_SEM_VAZAO_CONFIAVEL` remove essa preditora
só para os trechos marcados — `chuva_mm_media` não tem esse problema (0% de
nulos, série internamente consistente nos 3 trechos) e continua em todos.

ACHADO DE PESQUISA (2026-07, uso do solo REAL como preditora — ver ACHADO DE PESQUISA "uso do
solo REAL" em `transform.gold_features`): `pct_natural`/`pct_agropecuaria`/
`pct_urbano_industrial`/`pct_agua` (percentual de área por macro-categoria, MapBiomas real,
1985-2023 com preenchimento limitado nas bordas) entram como preditora, em `PREDITORAS_NUMERICAS_ANUAL`
E em `PREDITORAS_DRIVERS_ANUAL` — ao contrário de vazão/chuva, uso do solo é exatamente o tipo
de driver "causal-adjacente" que a matriz de drivers (item 8 abaixo) existe para isolar: não é
lag do próprio alvo, e mudança de uso do solo é uma alavanca de política real (diferente de
vazão/chuva, que ninguém "decide"). `pct_nao_vegetado_outro`/`pct_nao_observado` (categorias
catch-all/ruído de classificação do MapBiomas) ficam de fora de propósito — ver
`transform.gold_features.COLUNAS_USO_SOLO`.

ACHADO DE AUDITORIA DE ML (item 8 — SHAP dominado por autocorrelação):
mesmo sem o vazamento mensal (item 1), `{alvo}_lag1a` domina o SHAP dos
modelos por ser, genuinamente, a feature mais forte numa série com
autocorrelação temporal real. Isso é adequado para PREVISÃO, mas inútil para
perguntar "o que reduz a poluição" — para isso, `PREDITORAS_DRIVERS_ANUAL` /
`montar_matriz_features_drivers_por_trecho` monta uma matriz SEM os lags do
próprio alvo (só ano, vazão, chuva), usada por
`models.ml.shap_analysis.explicar_modelo_drivers` para um SHAP de
interpretação causal-adjacente — NUNCA para o modelo de produção, que
continua usando `PREDITORAS_NUMERICAS_ANUAL` (com lags) por ser mais preciso
para previsão de curto prazo.
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
    "pct_natural",
    "pct_agropecuaria",
    "pct_urbano_industrial",
    "pct_agua",
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


# Trechos cuja série de vazão tem inconsistência estrutural documentada (ver ACHADO DE
# AUDITORIA DE ML item 5, docstring do módulo) — `vazao_m3s_medio` é removida das preditoras
# só para esses trechos.
TRECHOS_SEM_VAZAO_CONFIAVEL = {"baixo_tiete"}


def preditoras_anuais_do_trecho(trecho_id: str) -> list[str]:
    """Lista de preditoras numéricas anuais para `trecho_id` — igual a `PREDITORAS_NUMERICAS_ANUAL`,
    exceto `vazao_m3s_medio` removida para trechos em `TRECHOS_SEM_VAZAO_CONFIAVEL`."""
    if trecho_id in TRECHOS_SEM_VAZAO_CONFIAVEL:
        return [p for p in PREDITORAS_NUMERICAS_ANUAL if p != "vazao_m3s_medio"]
    return list(PREDITORAS_NUMERICAS_ANUAL)


def montar_matriz_features_anual_por_trecho(gold_df: pd.DataFrame, alvo: str, trecho_id: str) -> tuple[pd.DataFrame, pd.Series]:
    """Mesma matriz anual, mas filtrada a UM trecho e sem a coluna categórica `trecho_id`
    (redundante quando o modelo já é específico de um trecho). Para trechos em
    `TRECHOS_SEM_VAZAO_CONFIAVEL`, `vazao_m3s_medio` não entra como preditora (item 5).

    ACHADO DE AUDITORIA DE ML (2026-07, item 2 — generalização espacial): o teste de
    generalização cruzada entre trechos (Seção 23 do relatório de EDA) mostrou R² negativo
    em TODA transferência Alto↔Médio↔Baixo Tietê — um único modelo com `trecho_id` como
    feature categórica está tentando aprender uma relação que muda de patamar/inclinação
    entre trechos. Modelos separados por trecho (`models.ml.train`) evitam essa mistura."""
    preditoras = preditoras_anuais_do_trecho(trecho_id)
    colunas_necessarias = [*preditoras, alvo]
    subconjunto = gold_df[gold_df["trecho_id"] == trecho_id]
    completo = subconjunto.dropna(subset=colunas_necessarias)
    return completo[preditoras], completo[alvo]


# --- Preditoras "drivers" (sem lags do próprio alvo) — item 8, ver docstring do módulo -----
PREDITORAS_DRIVERS_ANUAL = [
    "ano", "vazao_m3s_medio", "chuva_mm_media",
    "pct_natural", "pct_agropecuaria", "pct_urbano_industrial", "pct_agua",
]


def preditoras_drivers_do_trecho(trecho_id: str) -> list[str]:
    """Igual a `PREDITORAS_DRIVERS_ANUAL`, exceto `vazao_m3s_medio` removida para trechos em
    `TRECHOS_SEM_VAZAO_CONFIAVEL` (mesma lógica do item 5, aplicada aqui também)."""
    if trecho_id in TRECHOS_SEM_VAZAO_CONFIAVEL:
        return [p for p in PREDITORAS_DRIVERS_ANUAL if p != "vazao_m3s_medio"]
    return list(PREDITORAS_DRIVERS_ANUAL)


def montar_matriz_features_drivers_por_trecho(gold_df: pd.DataFrame, alvo: str, trecho_id: str) -> tuple[pd.DataFrame, pd.Series]:
    """Matriz anual SEM os lags do próprio alvo — só ano/vazão/chuva. Usada exclusivamente
    por `models.ml.shap_analysis.explicar_modelo_drivers` para uma leitura de
    interpretabilidade menos dominada por autocorrelação (item 8) — NÃO usada para o modelo
    de produção (`models.ml.train`), que precisa dos lags para ter precisão de previsão."""
    preditoras = preditoras_drivers_do_trecho(trecho_id)
    colunas_necessarias = [*preditoras, alvo]
    subconjunto = gold_df[gold_df["trecho_id"] == trecho_id]
    completo = subconjunto.dropna(subset=colunas_necessarias)
    return completo[preditoras], completo[alvo]
